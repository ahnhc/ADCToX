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

from .dataset import ModelData


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
        )

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            mu_axis=self.mu_axis, mech_axis=self.mech_axis,
            family_axis=self.family_axis, cleav_axis=self.cleav_axis,
            b_dar=self.b_dar, b_combo=self.b_combo, sigma_agent=self.sigma_agent,
            axes=np.array(self.axes), mechanisms=np.array(self.mechanisms),
            dar_mean=np.array([self.dar_mean]),
        )

    @classmethod
    def load(cls, path: Path) -> "Posterior":
        z = np.load(path, allow_pickle=False)
        return cls(
            mu_axis=z["mu_axis"], mech_axis=z["mech_axis"],
            family_axis=z["family_axis"], cleav_axis=z["cleav_axis"],
            b_dar=z["b_dar"], b_combo=z["b_combo"], sigma_agent=z["sigma_agent"],
            axes=[str(s) for s in z["axes"]],
            mechanisms=[str(s) for s in z["mechanisms"]],
            families=[str(s) for s in z["families"]],
            dar_mean=float(z["dar_mean"][0]),
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
        + post.cleav_axis[:, None, :] * cleavables[None, :, None]
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


def risk_band(point: float, n_supporting_arms: int) -> str:
    """Band a rate, with no-evidence kept visually distinct from low risk.

    An axis with no supporting arms must never render as "low": absence of evidence and
    evidence of safety look identical in a colour scale and are not the same thing.
    """
    if n_supporting_arms == 0:
        return "no_evidence"
    if point < 0.05:
        return "low"
    if point < 0.20:
        return "moderate"
    return "high"
