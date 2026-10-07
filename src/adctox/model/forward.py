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

from .dataset import CENSORED, OBSERVED, ZERO, ModelData


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


def model(data: ModelData, hold_mech: int | None = None) -> None:
    """NumPyro model. Pass `hold_mech` to zero out one mechanism's interaction, which is
    how leave-one-mechanism-out predicts a class it was not allowed to learn."""
    n_axes = len(data.axes)
    n_mech = len(data.mechanisms)

    # --- axis baselines: "every cytotoxic hits GI and blood" lives here, and must, so
    # that the design terms are estimated against it rather than reproducing it.
    mu_axis = numpyro.sample("mu_axis", dist.Normal(-3.0, 2.0).expand([n_axes]).to_event(1))

    # --- mechanism x axis, with a learned scale (the shrinkage that makes this fit)
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

    # --- linker cleavability x axis. Measured direction, worth stating because an earlier
    # draft had it backwards: non-cleavable linkers associate with ocular toxicity and
    # cleavable ones with pulmonary and infectious events. Cleavability does *not* split
    # haematologic toxicity, which tracks the payload instead.
    tau_cleav = numpyro.sample("tau_cleav", dist.HalfNormal(0.5))
    cleav_axis_raw = numpyro.sample(
        "cleav_axis_raw", dist.Normal(0.0, 1.0).expand([n_axes]).to_event(1)
    )
    cleav_axis = tau_cleav * cleav_axis_raw

    # --- scalar design and nuisance effects. All covariates arrive centered, so zero is
    # the training mean rather than a nonsensical edge (log n = 0 would be a 1-patient arm).
    b_dar = numpyro.sample("b_dar", dist.Normal(0.0, 0.5))
    b_combo = numpyro.sample("b_combo", dist.Normal(0.0, 1.0))
    b_thresh = numpyro.sample("b_thresh", dist.Normal(0.0, 0.5))
    b_log_n = numpyro.sample("b_log_n", dist.Normal(0.0, 0.5))

    # --- random intercepts. Trial absorbs population and era; agent absorbs whatever is
    # specific to a molecule beyond its design slots.
    sigma_trial = numpyro.sample("sigma_trial", dist.HalfNormal(1.0))
    u_trial = numpyro.sample(
        "u_trial", dist.Normal(0.0, 1.0).expand([len(data.trials)]).to_event(1)
    )
    sigma_agent = numpyro.sample("sigma_agent", dist.HalfNormal(1.0))
    u_agent = numpyro.sample(
        "u_agent", dist.Normal(0.0, 1.0).expand([len(data.agents)]).to_event(1)
    )

    arm_lin = (
        b_dar * data.arm_dar_c
        + b_combo * data.arm_combo
        + b_thresh * data.arm_thresh_c
        + b_log_n * data.arm_log_n_c
        + sigma_trial * u_trial[data.arm_trial_idx]
        + sigma_agent * u_agent[data.arm_agent_idx]
    )

    ai, xi = data.arm_idx, data.axis_idx
    logit = (
        mu_axis[xi]
        + mech_axis[data.arm_mech_idx[ai], xi]
        + cleav_axis[xi] * data.arm_cleavable[ai]
        + arm_lin[ai]
    )
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
    design = n_axes + n_mech * n_axes + n_axes + 2  # mu, mech x axis, cleav x axis, dar+combo
    nuisance = 2 + len(data.trials) + len(data.agents) + 4  # thresh, log_n, REs, scales
    return {
        "design": design,
        "nuisance": nuisance,
        "total": design + nuisance,
        "identifying_cells": len(data.agents) * n_axes,
        "arm_axis_cells": data.n_cells,
        "design_ratio_vs_identifying": round(len(data.agents) * n_axes / design, 2),
    }
