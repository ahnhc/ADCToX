"""Hierarchical binomial forward model: ADC design features -> per-organ-axis AE rate.

Scale discipline, which is the whole reason this model is small: design features
(mechanism, linker, DAR, isotype, target) are **agent-level constants**. Trastuzumab
emtansine's 48 arms are 48 observations of T-DM1's trial population but *one* observation
of DM1 chemistry. So the data identifying a design coefficient is
`n_agents x n_axes` -- measured at 16 x 14 = 224 cells -- not the 3,990 arm-axis cells.
Fitting the 420-parameter design matrix an earlier draft proposed would be 0.57:1
against that, fewer data points than parameters.

Hence: the mechanism x axis interaction is kept but given a hierarchical scale, so the
data decides how much of it survives rather than the parameter count asserting it. With
one or two agents in a mechanism the prior pulls that interaction toward zero, which is
the honest answer. The posterior scale is reported, so a reader can see how much the
interaction was actually supported.

Likelihood. Three cell types, from `dataset.py`:
  OBSERVED  Binomial(n, p) at the reported count.
  ZERO      Binomial(n, p) at 0 -- a genuine zero from a completely-reported table.
  CENSORED  log P(X < cut | n, p), via the regularized incomplete beta. These are the
            cells a truncated `otherEvents` table suppressed; treating them as zeros is
            the single most likely silent bug in this project.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
from jax.scipy.special import betainc

from .dataset import ModelData


def _family_term(data, mech_axis, n_axes: int, hold_family: int | None):
    """Nested payload-family deviations around their mechanism's effect.

    Retained so the finding can be reproduced, not because it is used by default; see
    USE_PAYLOAD_FAMILY.
    """
    tau_family = numpyro.sample("tau_family", dist.HalfNormal(0.3))
    family_dev_raw = numpyro.sample(
        "family_dev_raw",
        dist.Normal(0.0, 1.0).expand([len(data.families), n_axes]).to_event(2),
    )
    family_axis = mech_axis[data.family_to_mech, :] + tau_family * family_dev_raw
    if hold_family is not None:
        family_axis = family_axis.at[hold_family, :].set(
            mech_axis[data.family_to_mech[hold_family], :]
        )
    return family_axis


def _log_binom_cdf_below(cut: jnp.ndarray, n: jnp.ndarray, p: jnp.ndarray) -> jnp.ndarray:
    """log P(X < cut) for X ~ Binomial(n, p), i.e. log P(X <= cut-1).

    Uses the identity P(X <= m) = I_{1-p}(n-m, m+1) with the regularized incomplete beta.
    `cut` is clamped into [1, n] so a threshold above the denominator degrades to
    probability 1 (log 0) rather than producing an invalid beta call.
    """
    cut = jnp.clip(cut, 1, n)
    m = cut - 1.0
    a = n - m
    b = m + 1.0
    prob = betainc(a, b, 1.0 - p)
    return jnp.log(jnp.clip(prob, 1e-30, 1.0))


# Payload family is off by default. It is not identifiable at this corpus size, in
# either parameterization tried, and both failures are recorded because the measurement is
# the point:
#
#   mechanism only            worst standardized seed gap 0.239  converged
#   + family, additive        worst gap 0.686, tau_mech fell 0.592 -> 0.436 as
#                             tau_family took 0.396; LOMO delta worsened -0.016 -> -0.022
#   + family, nested          worst gap 0.577, tau_mech 0.453 / tau_family 0.391
#
# The diagnosis that motivated trying it was wrong, and the measurement that replaced it
# makes the case for the family level weaker rather than stronger. The old reading was
# that every large cross-validation miss is an agent which is the sole representative of
# its payload family; on split-corrected folds none of the four worst folds is, and the
# two worst are each other's only family sibling (see scripts/fold_difficulty.py). What
# actually tracks fold difficulty is how many agents share the held-out agent's PAYLOAD,
# at a rank correlation of +0.771 against +0.694 for anything about families.
#
# So the level that would help is payload, not family -- and payload is the one level this
# corpus provably cannot reach, because its vocabulary grows as fast as the corpus does.
# Family at least stops growing, which is why it was worth trying; it is still not
# separable from mechanism given 7 families across 5 mechanisms and 16 agents. The
# project's central structural finding appears again, and tighter than before.
USE_PAYLOAD_FAMILY = False

# Agent x axis deviation. Off until measured; see the block in `model` for the diagnosis
# it is meant to address and the numbers behind it.
USE_AGENT_AXIS = False


def model(
    data: ModelData,
    hold_mech: int | None = None,
    hold_family: int | None = None,
    use_family: bool | None = None,
    use_agent_axis: bool = USE_AGENT_AXIS,
) -> None:
    """NumPyro model.

    `hold_mech` and `hold_family` zero out one level's interaction, which is how a
    held-out fold predicts a class it was not allowed to learn.
    """
    n_axes = len(data.axes)
    n_mech = len(data.mechanisms)

    # --- axis baselines: "every cytotoxic hits GI and blood" lives here, and must, so
    # that the design terms are estimated against it rather than reproducing it.
    mu_axis = numpyro.sample("mu_axis", dist.Normal(-3.0, 2.0).expand([n_axes]).to_event(1))

    # --- payload chemistry, nested: family inside mechanism.
    #
    # An earlier version added mechanism x axis and family x axis as two independent terms.
    # That is not identified, because family determines mechanism: the two competed for the
    # same variance, the sampler stopped converging (worst seed gap 0.686), and tau_mech
    # fell from 0.592 to 0.436 as tau_family took 0.396 off it.
    #
    # Nesting fixes the identification. A family's effect is drawn around its mechanism's
    # effect, only the family term enters the predictor, and the two scales then mean
    # different things: tau_mech is spread between mechanisms, tau_family is spread of
    # families within their mechanism. A family with one agent has nothing to pull it away
    # from its mechanism and shrinks back to it, which is the right answer rather than a
    # limitation.
    tau_mech = numpyro.sample("tau_mech", dist.HalfNormal(0.5))
    mech_axis_raw = numpyro.sample(
        "mech_axis_raw", dist.Normal(0.0, 1.0).expand([n_mech, n_axes]).to_event(2)
    )
    mech_axis = tau_mech * mech_axis_raw
    if hold_mech is not None:
        # The held-out mechanism contributes nothing, so prediction for it falls back to
        # the axis baseline plus the delivery terms. That is exactly the question
        # leave-one-mechanism-out asks.
        mech_axis = mech_axis.at[hold_mech, :].set(0.0)

    # --- payload family x axis, nested inside mechanism.
    # Added because the cross-validation misses concentrate on agents that are the sole
    # representative of their payload family within a mechanism class: trastuzumab
    # emtansine's platelet and ocular profile cannot be predicted from MMAE's neuropathy,
    # yet both are "tubulin". Family adds two splits over mechanism among surviving
    # agents, tubulin -> auristatin (5 agents) + maytansinoid (2) and
    # dna_crosslink -> pbd (1) + ign (1). Its own scale decides how much survives: the
    # first split has the agents to support an effect, the second does not and shrinks
    # back toward its mechanism, which is the correct answer rather than a limitation.
    if use_family is None:
        use_family = USE_PAYLOAD_FAMILY
    if not use_family:
        # Mechanism carries the chemistry on its own.
        family_axis = mech_axis[data.family_to_mech, :]
        if hold_family is not None:
            family_axis = family_axis.at[hold_family, :].set(
                mech_axis[data.family_to_mech[hold_family], :]
            )
    else:
        family_axis = _family_term(data, mech_axis, n_axes, hold_family)


    # --- linker cleavability x axis. Measured direction, worth stating because an earlier
    # draft had it backwards: non-cleavable linkers associate with ocular toxicity and
    # cleavable ones with pulmonary and infectious events. Cleavability does *not* split
    # haematologic toxicity, which tracks the payload instead.
    # Cleavability enters as a *centered* contrast. Only 2 of 16 agents carry a
    # non-cleavable linker, so an uncentered indicator is nearly constant and behaves as a
    # second per-axis intercept, unidentified against mu_axis. Centering leaves it able to
    # express a contrast without being able to shift the overall level.
    tau_cleav = numpyro.sample("tau_cleav", dist.HalfNormal(0.5))
    cleav_axis_raw = numpyro.sample(
        "cleav_axis_raw", dist.Normal(0.0, 1.0).expand([n_axes]).to_event(1)
    )
    cleav_axis = tau_cleav * cleav_axis_raw
    cleav_centered = data.arm_cleavable - float(data.arm_cleavable.mean())

    # --- scalar design and nuisance effects. All covariates arrive centered, so zero is
    # the training mean rather than a nonsensical edge (log n = 0 would be a 1-patient arm).
    b_dar = numpyro.sample("b_dar", dist.Normal(0.0, 0.5))
    b_combo = numpyro.sample("b_combo", dist.Normal(0.0, 1.0))
    # Which corpus the arm came from. A nuisance control in the same sense as `b_thresh`:
    # a journal table and a registry posting are different data cuts of the same events,
    # selected differently and reported to different cuts, and without this term `b_combo`
    # absorbs the difference because every combination arm is a registry arm.
    #
    # Sampled only where the indicator varies. On the registry-only corpus every arm is a
    # registry arm, so the coefficient would see no data, draw its prior, and contribute
    # nothing but a spurious row to the seed-agreement table -- which is read as a
    # convergence diagnostic and would then be reporting on a parameter the fit never
    # estimated.
    has_both_sources = float(data.arm_is_literature.std()) > 0
    if has_both_sources:
        b_source = numpyro.sample("b_source", dist.Normal(0.0, 1.0))
    else:
        b_source = 0.0

    # --- and the gap is not one number. Measured on the 12 agents with arms from both
    # sources, which holds the chemistry fixed so the difference is reporting rather than
    # drug, it runs from -1.16 logit on cardiovascular to +1.79 on ocular, with
    # heterogeneity Q = 80 on 11 degrees of freedom and p = 1.5e-12. The between-axis
    # standard deviation is about 0.72, larger than `tau_mech`.
    #
    # The direction is what makes it a specification error rather than noise. A paper's
    # adverse-event table is selected for what is notable about that drug, so papers report
    # *more* than the registry on ocular and dermatologic -- belantamab's keratopathy and
    # enfortumab's skin toxicity are what those papers are about -- and *less* on
    # cardiovascular, pulmonary, gastrointestinal and metabolic, which are background and
    # fall below a "most common adverse events" cut.
    #
    # With one shift the axis-varying remainder has to go somewhere, and it goes into
    # `mech_axis`, because literature arms are not spread evenly across mechanisms. So this
    # is a confound on the model's central parameter, not a nuisance refinement.
    #
    # Centered like the mechanism and cleavability terms: `b_source` carries the mean shift
    # and this carries the deviations, so the two are not competing for the same level.
    if has_both_sources:
        tau_source = numpyro.sample("tau_source", dist.HalfNormal(0.5))
        source_axis_raw = numpyro.sample(
            "source_axis_raw", dist.Normal(0.0, 1.0).expand([n_axes]).to_event(1)
        )
        source_axis = tau_source * (source_axis_raw - source_axis_raw.mean())
        numpyro.deterministic("source_axis", source_axis)
    else:
        source_axis = jnp.zeros(n_axes)
    b_thresh = numpyro.sample("b_thresh", dist.Normal(0.0, 0.5))
    b_log_n = numpyro.sample("b_log_n", dist.Normal(0.0, 0.5))

    # --- random intercepts, centered to sum to zero.
    #
    # This centering is not cosmetic. A non-centered `sigma * u` with `u ~ Normal(0, 1)`
    # lets the random effects carry a common offset, and that offset is exactly collinear
    # with the axis intercept. The fit can then put `mu_axis` far from the data and pull
    # every observed arm back with its random effect -- harmless in sample, and ruinous out
    # of it, because predicting a design that has no trial and no agent drops the random
    # effects and inherits the uncompensated intercept.
    #
    # Measured before this fix, on a 153-arm corpus: tau_cleav ran to 3.87 against a
    # HalfNormal(0.5) prior, cleav_axis spanned -6.2 to +7.5, and the otologic axis -- whose
    # observed rate is 0.04 -- was predicted at 0.9997. Enforcing the constraint removes
    # the degeneracy.
    sigma_trial = numpyro.sample("sigma_trial", dist.HalfNormal(1.0))
    u_trial_raw = numpyro.sample(
        # +1 for the sentinel slot that single-arm-trial arms point at; it is sampled and
        # then masked out of the linear predictor, so it stays at its prior.
        "u_trial_raw", dist.Normal(0.0, 1.0).expand([len(data.trials) + 1]).to_event(1)
    )
    # Centre over the REAL trials only. The sum-to-zero constraint is load-bearing here
    # -- without it a common offset rides along collinear with the axis intercept, which
    # is harmless in sample and ruinous out of it -- so the sentinel's prior noise must
    # not enter the mean it is computed from. The sentinel keeps its raw draw and is
    # masked out of the linear predictor below.
    n_real_trials = len(data.trials)
    u_trial = u_trial_raw.at[:n_real_trials].add(
        -u_trial_raw[:n_real_trials].mean()
    )
    sigma_agent = numpyro.sample("sigma_agent", dist.HalfNormal(1.0))
    u_agent_raw = numpyro.sample(
        "u_agent_raw", dist.Normal(0.0, 1.0).expand([len(data.agents)]).to_event(1)
    )
    u_agent = u_agent_raw - u_agent_raw.mean()

    # Agent x axis deviation, off by default and measured rather than assumed.
    #
    # Diagnosis it addresses (scripts/design_effect_size.py): `u_agent` is a scalar per
    # agent, so it cannot absorb an agent's idiosyncratic *organ profile*. An agent whose
    # ocular rate is unusual has nowhere to put that except `mech_axis[its mechanism,
    # ocular]`. For a mechanism carried by one drug, the mechanism coefficient therefore
    # IS that drug's agent effect, and the fitted effects show it: dna_alkyl's ocular
    # coefficient reaches +1.98 on 2 arms of one agent, while tubulin's neurologic sits at
    # +1.06 on 163 arms of seven. Effect size falls monotonically as agents accumulate --
    # ratio to the baseline spread 0.71, 0.61, 0.36, 0.36, 0.29 for 1, 2, 2, 4 and 7
    # agents -- which is what overfitting on thin data looks like.
    #
    # With this term, an agent's own organ profile has a home and `mech_axis` is left with
    # what agents of a mechanism share. A held-out agent drops the term, which is the
    # point: only the shared part should generalise.
    #
    # Centred over agents within each axis. Without that it is collinear with `mu_axis`,
    # which is the degeneracy that already invalidated one whole evaluation round here.
    if use_agent_axis:
        sigma_agent_axis = numpyro.sample("sigma_agent_axis", dist.HalfNormal(0.5))
        u_agent_axis_raw = numpyro.sample(
            "u_agent_axis_raw",
            dist.Normal(0.0, 1.0).expand([len(data.agents), n_axes]).to_event(2),
        )
        u_agent_axis = u_agent_axis_raw - u_agent_axis_raw.mean(axis=0, keepdims=True)
        agent_axis = sigma_agent_axis * u_agent_axis
        numpyro.deterministic("agent_axis", agent_axis)
    else:
        agent_axis = None
    numpyro.deterministic("u_trial", u_trial)
    numpyro.deterministic("u_agent", u_agent)

    arm_lin = (
        b_dar * data.arm_dar_c
        + b_combo * data.arm_combo
        + b_source * data.arm_is_literature
        + b_thresh * data.arm_thresh_c
        + b_log_n * data.arm_log_n_c
        # Masked: a single-arm trial's effect is confounded with that arm's residual.
        + sigma_trial * u_trial[data.arm_trial_idx] * data.arm_has_trial_effect
        + sigma_agent * u_agent[data.arm_agent_idx]
    )

    ai, xi = data.arm_idx, data.axis_idx
    logit = (
        mu_axis[xi]
        + family_axis[data.arm_family_idx[ai], xi]
        + cleav_axis[xi] * cleav_centered[ai]
        + source_axis[xi] * data.arm_is_literature[ai]
        + arm_lin[ai]
    )
    if agent_axis is not None:
        logit = logit + agent_axis[data.arm_agent_idx[ai], xi]
    p = jax.nn.sigmoid(logit)
    # No `numpyro.deterministic` on p. Storing a 3,990-cell array per draw makes
    # get_samples() dominate the run time (measured: >85s against a 23s fit), and nothing
    # needs it -- prediction recomputes rates from the parameter draws in predict.py.

    n = data.n_at_risk.astype(jnp.float32)

    # Each likelihood term is evaluated only on the cells it applies to, via precomputed
    # index arrays. This matters a great deal: the incomplete-beta gradient costs ~15x an
    # ordinary binomial gradient, and only ~12% of cells are censored, so masking a
    # full-length betainc would throw away roughly 8x the work.
    pi, ci = data.point_idx, data.censored_idx

    if pi.size:
        numpyro.factor(
            "ll_point",
            jnp.sum(
                dist.Binomial(total_count=n[pi], probs=p[pi]).log_prob(
                    data.n_affected[pi].astype(jnp.float32)
                )
            ),
        )

    if ci.size:
        numpyro.factor(
            "ll_censored",
            jnp.sum(
                _log_binom_cdf_below(
                    data.censor_below[ci].astype(jnp.float32), n[ci], p[ci]
                )
            ),
        )


def n_free_parameters(data: ModelData) -> dict[str, int]:
    """Nominal free parameters, split by whether the design matrix or the data supports them."""
    n_axes, n_mech = len(data.axes), len(data.mechanisms)
    n_fam = len(data.families)
    # mu, mech x axis, cleav x axis, dar + combo. Family deviations are excluded because
    # they are not identifiable here (see USE_PAYLOAD_FAMILY).
    design = n_axes + n_mech * n_axes + n_axes + 2
    if USE_PAYLOAD_FAMILY:
        design += n_fam * n_axes
    # thresh, log_n, source, random intercepts, scales. Counted over the REAL trials: the
    # model samples one extra trial slot as a sentinel for arms from single-arm trials, but
    # it is masked out of the linear predictor and sees no data, so counting it would
    # overstate the nuisance load against the identifying cells.
    #
    # `b_source` is nuisance and not design: it describes which corpus an arm was read from,
    # which is a property of the reporting rather than of the chemistry. It exists because
    # `b_combo` was carrying it.
    # `b_source` plus the 14-axis source deviation vector and its scale, where the corpus
    # carries both sources. Nuisance and not design: it describes which corpus an arm was
    # read from, which is a property of the reporting rather than of the chemistry.
    both_sources = int(float(data.arm_is_literature.std()) > 0)
    nuisance = (
        2 + both_sources * (1 + n_axes + 1)
        + len(data.trials) + len(data.agents) + 5
    )
    return {
        "design": design,
        "nuisance": nuisance,
        "total": design + nuisance,
        "identifying_cells": len(data.agents) * n_axes,
        "arm_axis_cells": data.n_cells,
        "design_ratio_vs_identifying": round(len(data.agents) * n_axes / design, 2),
    }
