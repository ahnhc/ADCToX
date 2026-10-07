"""Predict organ-axis rates for a design that is not in the training corpus.

The one subtlety that matters: a novel design has no agent and no trial, so the random
intercepts `u_agent` and `u_trial` have nothing to condition on. The correct behaviour is
to set them to their prior mean of zero -- the design's prediction is the population-level
one, not borrowed from whichever molecule happens to be nearby. Substituting a fitted
agent effect would quietly attribute another drug's residual to the candidate.

Nuisance covariates get the training reference point, which is zero after centering. That
is why `dataset.build` keeps the centering constants: zeroing an *uncentered* covariate
would mean log(n)=0, a one-patient arm at the extreme edge of the observed range, and
would shift every prediction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dataset import OBSERVED, ModelData


def _evidence_counts(data: ModelData) -> dict[str, np.ndarray]:
    """Agents and arms with an *observed* count, per (mechanism, axis).

    Censored and structurally-zero cells are excluded on purpose. A cell suppressed below
    a reporting threshold tells you the rate was small; it does not tell you an organ was
    examined and found affected, so counting it as evidence would let a thinly reported
    axis masquerade as a well-studied one.
    """
    n_mech, n_axes = len(data.mechanisms), len(data.axes)
    agents = np.zeros((n_mech, n_axes), dtype=np.int32)
    arms = np.zeros((n_mech, n_axes), dtype=np.int32)
    observed = data.status == OBSERVED
    for m in range(n_mech):
        arm_in_mech = data.arm_mech_idx == m
        for a in range(n_axes):
            sel = observed & (data.axis_idx == a) & arm_in_mech[data.arm_idx]
            if not sel.any():
                continue
            arm_ids = np.unique(data.arm_idx[sel])
            arms[m, a] = len(arm_ids)
            agents[m, a] = len(np.unique(data.arm_agent_idx[arm_ids]))
    return {"evidence_agents": agents, "evidence_arms": arms}


@dataclass
class Posterior:
    """Posterior draws of the parameters needed for out-of-corpus prediction."""

    mu_axis: np.ndarray        # (S, A)
    mech_axis: np.ndarray      # (S, M, A)
    family_axis: np.ndarray    # (S, F, A)
    cleav_axis: np.ndarray     # (S, A)
    b_dar: np.ndarray          # (S,)
    b_combo: np.ndarray
    sigma_agent: np.ndarray
    axes: list[str]
    mechanisms: list[str]
    families: list[str]
    dar_mean: float
    # Training-corpus mean of the cleavability indicator. Prediction must centre on the
    # same value the fit used, or the contrast silently becomes an intercept shift.
    cleavable_mean: float
    # Observed-evidence counts per (mechanism, axis): agents, arms and cells that actually
    # carried a reported count. Without these, prediction cannot distinguish "the model
    # estimates a low rate" from "nothing in the corpus speaks to this organ for this
    # chemistry", and those must never render the same way.
    evidence_agents: np.ndarray   # (M, A)
    evidence_arms: np.ndarray     # (M, A)

    @classmethod
    def from_samples(cls, post: dict, data: ModelData) -> "Posterior":
        tau_m = np.asarray(post["tau_mech"])[:, None, None]
        tau_f = (np.asarray(post["tau_family"])[:, None, None]
                 if "tau_family" in post else None)
        tau_c = np.asarray(post["tau_cleav"])[:, None]
        mech = tau_m * np.asarray(post["mech_axis_raw"])
        family = mech[:, data.family_to_mech, :]
        if "tau_family" in post:
            family = family + tau_f * np.asarray(post["family_dev_raw"])
        return cls(
            mu_axis=np.asarray(post["mu_axis"]),
            mech_axis=mech,
            family_axis=family,
            cleav_axis=tau_c * np.asarray(post["cleav_axis_raw"]),
            b_dar=np.asarray(post["b_dar"]),
            b_combo=np.asarray(post["b_combo"]),
            sigma_agent=np.asarray(post["sigma_agent"]),
            axes=list(data.axes),
            mechanisms=list(data.mechanisms),
            families=list(data.families),
            dar_mean=float(data.dar_mean),
            cleavable_mean=float(data.cleavable_mean),
            **_evidence_counts(data),
        )

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            mu_axis=self.mu_axis, mech_axis=self.mech_axis,
            family_axis=self.family_axis, cleav_axis=self.cleav_axis,
            b_dar=self.b_dar, b_combo=self.b_combo, sigma_agent=self.sigma_agent,
            axes=np.array(self.axes), mechanisms=np.array(self.mechanisms),
            families=np.array(self.families),
            dar_mean=np.array([self.dar_mean]),
            cleavable_mean=np.array([self.cleavable_mean]),
            evidence_agents=self.evidence_agents,
            evidence_arms=self.evidence_arms,
        )

    # Bumped whenever the saved field set changes, so a stale artefact fails with a
    # sentence rather than a KeyError from deep inside numpy.
    FORMAT = 4

    @classmethod
    def load(cls, path: Path) -> "Posterior":
        z = np.load(path, allow_pickle=False)
        missing = {
            "family_axis", "families", "cleavable_mean",
            "evidence_agents", "evidence_arms",
        } - set(z.files)
        if missing:
            raise ValueError(
                f"{path} was written by an older format and is missing {sorted(missing)}. "
                "Regenerate it with `make forward` or `python scripts/propose_demo.py`; "
                "a posterior must not be mixed with a model it was not fitted under."
            )
        return cls(
            mu_axis=z["mu_axis"], mech_axis=z["mech_axis"],
            family_axis=z["family_axis"], cleav_axis=z["cleav_axis"],
            b_dar=z["b_dar"], b_combo=z["b_combo"], sigma_agent=z["sigma_agent"],
            axes=[str(s) for s in z["axes"]],
            mechanisms=[str(s) for s in z["mechanisms"]],
            families=[str(s) for s in z["families"]],
            dar_mean=float(z["dar_mean"][0]),
            cleavable_mean=float(z["cleavable_mean"][0]),
            evidence_agents=z["evidence_agents"],
            evidence_arms=z["evidence_arms"],
        )

    @property
    def n_draws(self) -> int:
        return len(self.b_dar)


def predict_draws(
    post: Posterior,
    mechanisms: list[str],
    families: list[str],
    dars: np.ndarray,
    cleavables: np.ndarray,
    include_agent_variation: bool = True,
    seed: int = 0,
) -> np.ndarray:
    """Rate draws for a batch of designs, shaped (n_draws, n_designs, n_axes).

    Draws are **paired** across designs: draw index s uses the same parameter vector for
    every candidate, so the correlation between candidates survives into the ranking.
    Independent draws would make nearly every pair look distinguishable, which is exactly
    the false precision the tie logic exists to prevent.

    `include_agent_variation` adds a draw from the fitted agent-level residual
    distribution. It belongs in a prediction for a *new* molecule: two ADCs with identical
    slots still differ, and omitting that term would state the interval more tightly than
    the evidence supports. Measured here, the term is small (sigma_agent posterior mean
    around 0.08), which is itself the finding that the design slots explain most of the
    between-agent variation.
    """
    n_designs = len(mechanisms)
    if not (len(dars) == len(cleavables) == n_designs):
        raise ValueError("mechanisms, dars and cleavables must be the same length")
    unknown = set(mechanisms) - set(post.mechanisms)
    if unknown:
        raise ValueError(
            f"mechanism(s) {sorted(unknown)} are absent from the training corpus; the "
            "model has no coefficient for them and must refuse rather than extrapolate"
        )

    mech_idx = np.array([post.mechanisms.index(m) for m in mechanisms])
    fam_idx = np.array(
        [post.families.index(f) if f in post.families else -1 for f in families]
    )
    S, A = post.n_draws, len(post.axes)

    logit = (
        post.mu_axis[:, None, :]                             # (S,1,A)
        # Family already carries its mechanism's effect through the nesting, so only one
        # of the two is added. A family absent from the corpus falls back to the bare
        # mechanism effect rather than borrowing a sibling's deviation.
        + np.where(
            (fam_idx >= 0)[None, :, None],
            post.family_axis[:, np.clip(fam_idx, 0, None), :],
            post.mech_axis[:, mech_idx, :],
        )
        + post.cleav_axis[:, None, :]
        * (cleavables - post.cleavable_mean)[None, :, None]
        + (post.b_dar[:, None] * (dars[None, :] - post.dar_mean))[:, :, None]
        # b_combo is intentionally not applied: a proposal is a monotherapy design, and
        # the combination covariate sits at its reference level of zero.
    )
    if include_agent_variation:
        rng = np.random.default_rng(seed)
        logit = logit + (
            post.sigma_agent[:, None] * rng.standard_normal((S, n_designs))
        )[:, :, None]
    return 1.0 / (1.0 + np.exp(-logit))


# Below this many arms an axis is reported as having no usable evidence rather than a
# low rate. Three is the smallest number at which a rate is worth banding at all; with
# one or two arms the estimate is the prior wearing a number.
MIN_ARMS_FOR_A_BAND = 3


def decompose(
    post: Posterior,
    mechanism: str,
    family: str,
    dar: float,
    cleavable: bool,
    axis: str,
) -> list[dict]:
    """Additive contributions to one axis's logit, as a waterfall that sums to the total.

    The model is linear in logit space, so this is an exact decomposition rather than an
    attribution heuristic. Each term is reported with its source, because the chemistry
    terms are fitted and the comorbidity weighting is not, and a reader must be able to
    tell them apart.

    `family` carries its mechanism through the nesting, so the mechanism's own effect is
    not listed separately -- doing so would double-count it.

    One caveat the caller must not paper over: the terms are posterior *means* in logit
    space, so `sigmoid(sum of terms)` is close to, but not identical with, the reported
    point estimate, which is the mean of `sigmoid` over draws. The gap is Jensen's
    inequality and is small here (about 0.0004 on a rate of 0.14), but the waterfall is
    an exact decomposition of the mean logit, not of the mean rate. `decompose_summary`
    reports both numbers so the difference is visible rather than assumed away.
    """
    ai = post.axes.index(axis)
    terms: list[dict] = []

    mu = float(post.mu_axis[:, ai].mean())
    terms.append(
        {
            "factor": "axis baseline",
            "detail": "the rate a cytotoxic ADC shows on this organ regardless of design",
            "source": "model",
            "contribution": round(mu, 4),
        }
    )

    if family in post.families:
        fi = post.families.index(family)
        terms.append(
            {
                "factor": f"payload chemistry ({family}, {mechanism})",
                "detail": "payload family effect, which carries its mechanism",
                "source": "model",
                "contribution": round(float(post.family_axis[:, fi, ai].mean()), 4),
            }
        )
    elif mechanism in post.mechanisms:
        mi = post.mechanisms.index(mechanism)
        terms.append(
            {
                "factor": f"payload mechanism ({mechanism})",
                "detail": "payload family absent from the corpus; falls back to mechanism",
                "source": "model",
                "contribution": round(float(post.mech_axis[:, mi, ai].mean()), 4),
            }
        )

    terms.append(
        {
            "factor": f"linker {'cleavable' if cleavable else 'non-cleavable'}",
            "detail": (
                "centred contrast, so it expresses a difference from the corpus mix "
                f"({post.cleavable_mean:.2f} cleavable) rather than a level"
            ),
            "source": "model",
            "contribution": round(
                float(post.cleav_axis[:, ai].mean())
                * (float(cleavable) - post.cleavable_mean),
                4,
            ),
        }
    )
    terms.append(
        {
            "factor": f"DAR {dar}",
            "detail": f"centred on the corpus mean of {post.dar_mean:.2f}",
            "source": "model",
            "contribution": round(float(post.b_dar.mean()) * (dar - post.dar_mean), 4),
        }
    )
    return terms


def decompose_summary(terms: list[dict], reported_rate: float) -> dict:
    """The waterfall's total alongside the reported rate, with the gap stated.

    Exists so a caller rendering a driver list cannot silently imply that the terms add up
    to the number printed next to them.
    """
    total = sum(float(t["contribution"]) for t in terms)
    implied = 1.0 / (1.0 + np.exp(-total))
    return {
        "logit_total": round(total, 4),
        "rate_implied_by_terms": round(float(implied), 4),
        "rate_reported": round(float(reported_rate), 4),
        "gap": round(float(implied - reported_rate), 5),
        "note": (
            "Terms are posterior means in logit space, so they decompose the mean logit "
            "exactly and the mean rate only approximately; the difference is Jensen's "
            "inequality, not an error."
        ),
    }


def risk_band(point: float, n_supporting_arms: int) -> str:
    """Band a rate, with no-evidence kept visually distinct from low risk.

    An axis with no supporting arms must never render as "low": absence of evidence and
    evidence of safety look identical in a colour scale and are not the same thing.
    """
    if n_supporting_arms < MIN_ARMS_FOR_A_BAND:
        return "no_evidence"
    if point < 0.05:
        return "low"
    if point < 0.20:
        return "moderate"
    return "high"
