"""Build the model matrix from the arm corpus, with reporting-threshold censoring.

The subtlety this module exists for: a missing (arm, axis) cell does not mean zero, and
what it *does* mean differs by event table.

``otherEvents`` are reported only above a per-trial ``frequencyThreshold`` (measured:
'5' in 402 studies, '0' in 182, plus '1', '2', '3', '4', '4.9', '4.98', '5.0', '5.00').
So an axis absent from that table means *every* term in it fell below the threshold --
left-censored, not zero. Imputing zero biases every axis toward zero in proportion to
each trial's reporting cut, and because the threshold is sponsor-chosen while agents nest
inside sponsors, a trial random effect does **not** absorb it: it partially aliases the
payload-mechanism effect the model is trying to estimate. Measured consequence of getting
this wrong: threshold=0 trials show a summed AE burden of 42.2% against 32.5% for
threshold=5 trials, for the same axes.

``seriousEvents`` carry no threshold -- they are reported completely (verified: in
threshold=5 trials, 96.7% of serious terms have a max rate below 5%, i.e. they were
reported despite falling under the cut). A missing axis there is a genuine zero.

Trials with ``frequencyThreshold == 0`` report otherEvents completely too, so their
missing cells are also genuine zeros.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Cell status codes.
OBSERVED = 0  # a count was reported: binomial likelihood
CENSORED = 1  # absent from a truncated table: rate is below the threshold
ZERO = 2      # absent from a complete table: a genuine zero count


@dataclass
class ModelData:
    """Everything the forward model needs, as aligned arrays."""

    # Cell-level
    status: np.ndarray        # (n_cells,) OBSERVED / CENSORED / ZERO
    n_affected: np.ndarray    # (n_cells,) observed successes; 0 for ZERO; unused for CENSORED
    n_at_risk: np.ndarray     # (n_cells,)
    censor_below: np.ndarray  # (n_cells,) successes strictly below this count; CENSORED only
    axis_idx: np.ndarray      # (n_cells,)
    arm_idx: np.ndarray       # (n_cells,)

    # Arm-level
    arm_mech_idx: np.ndarray  # (n_arms,)
    arm_family_idx: np.ndarray
    arm_trial_idx: np.ndarray
    arm_agent_idx: np.ndarray
    arm_dar_c: np.ndarray     # centered
    arm_cleavable: np.ndarray
    arm_combo: np.ndarray
    arm_thresh_c: np.ndarray  # centered
    arm_log_n_c: np.ndarray   # centered log denominator
    # 1.0 where the arm's trial contributes two or more arms, else 0.0. A trial that
    # contributes a single arm has a trial effect perfectly confounded with that arm's
    # residual: it is a per-observation random effect, which is unidentified and gives
    # the sampler a long thin posterior to crawl along. Measured here, 128 of 189 trials
    # (68%) contribute one arm, so masking them removes two thirds of the trial
    # parameters and the geometry problem with them.
    arm_has_trial_effect: np.ndarray

    # Labels
    axes: list[str]
    mechanisms: list[str]
    families: list[str]
    # Mechanism index for each family, so the model can nest one inside the other.
    family_to_mech: np.ndarray
    agents: list[str]
    trials: list[str]
    arm_keys: list[str]

    # Centering constants, kept so inference can reproduce the training reference point.
    # Zeroing a covariate at inference instead of centering it is a real bug: log(n)=0
    # means a one-patient arm, the extreme edge of the observed range.
    dar_mean: float
    thresh_mean: float
    log_n_mean: float
    cleavable_mean: float
    # Which event table this grid was built from. Recorded rather than inferred because
    # downstream code bands rates against the scale of the outcome, and the two tables
    # differ by an order of magnitude.
    kind: str = "other"

    @property
    def n_cells(self) -> int:
        return len(self.status)

    @property
    def point_idx(self) -> np.ndarray:
        """Indices of cells with a point-mass likelihood (observed counts and true zeros)."""
        return np.flatnonzero((self.status == OBSERVED) | (self.status == ZERO))

    @property
    def censored_idx(self) -> np.ndarray:
        """Indices of cells whose count was suppressed below the reporting threshold."""
        return np.flatnonzero(self.status == CENSORED)

    @property
    def n_arms(self) -> int:
        return len(self.arm_keys)

    def summary(self) -> str:
        counts = {
            "observed": int((self.status == OBSERVED).sum()),
            "censored": int((self.status == CENSORED).sum()),
            "zero": int((self.status == ZERO).sum()),
        }
        return (
            f"{self.n_cells:,} cells over {self.n_arms:,} arms x {len(self.axes)} axes "
            f"({counts['observed']:,} observed, {counts['censored']:,} censored, "
            f"{counts['zero']:,} structural zero) | "
            f"{len(self.agents)} agents, {len(self.mechanisms)} mechanisms, "
            f"{len(self.families)} payload families, "
            f"{len(self.trials)} multi-arm trials "
            f"({int((self.arm_has_trial_effect == 0).sum())} arms from single-arm trials "
            f"carry no trial effect)"
        )


def build(
    arms: pd.DataFrame,
    obs: pd.DataFrame,
    axes: list[str],
    kind: str = "other",
    min_n: int = 30,
    conventional_only: bool = True,
) -> ModelData:
    """Assemble the full (arm x axis) grid for one event table.

    ``kind='other'`` is the primary analysis: it carries far more signal than the serious
    table, and the censoring above is what makes it usable. ``kind='serious'`` is the
    robustness check, where every missing cell is a true zero and no censoring model is
    needed -- if the two disagree, the censoring treatment is doing the work and must be
    reported as such.
    """
    arms = arms.copy()
    arms["n_at_risk"] = arms[["n_at_risk_other", "n_at_risk_serious"]].max(axis=1)
    keep = arms["agent"].notna() & (arms["n_at_risk"] >= min_n)
    if conventional_only:
        # moxetumomab pasudotox is a recombinant immunotoxin fusion, not a chemically
        # conjugated ADC: it has no linker and DAR is 1 by construction, so it cannot
        # inform the delivery terms.
        keep &= arms["conventional_adc"] == True  # noqa: E712
    arms = arms[keep].reset_index(drop=True)
    if arms.empty:
        raise ValueError("no arms survive the filters")

    mechanisms = sorted(arms["mechanism"].dropna().unique())
    families = sorted(arms["payload_family"].dropna().unique())
    agents = sorted(arms["agent"].unique())
    # Only multi-arm trials get a trial effect; see `arm_has_trial_effect`.
    arms_per_trial = arms["nct_id"].value_counts()
    multi_arm_trials = sorted(arms_per_trial[arms_per_trial >= 2].index)
    trials = multi_arm_trials
    arm_keys = arms["arm_key"].tolist()

    mech_of = {m: i for i, m in enumerate(mechanisms)}
    family_of = {f: i for i, f in enumerate(families)}
    agent_of = {a: i for i, a in enumerate(agents)}
    trial_of = {t: i for i, t in enumerate(trials)}
    axis_of = {a: i for i, a in enumerate(axes)}
    arm_of = {k: i for i, k in enumerate(arm_keys)}

    # Threshold semantics. None means the field was absent -- unknown, not zero. Treat it
    # conservatively as the corpus mode (5), and flag it, rather than assuming complete
    # reporting we cannot verify.
    thresh = arms["frequency_threshold"].to_numpy(dtype=float)
    thresh_known = ~np.isnan(thresh)
    thresh = np.where(thresh_known, thresh, 5.0)

    sub = obs[(obs["kind"] == kind) & obs["arm_key"].isin(set(arm_keys))]
    observed = {
        (r.arm_key, r.axis): (int(r.n_affected), int(r.n_at_risk))
        for r in sub.itertuples()
    }

    status_l, k_l, n_l, cens_l, ax_l, arm_l = [], [], [], [], [], []
    for i, row in arms.iterrows():
        arm_key = row["arm_key"]
        n_risk = int(row["n_at_risk"])
        # Prefer the table-specific denominator where the corpus gave one.
        col = "n_at_risk_other" if kind == "other" else "n_at_risk_serious"
        if pd.notna(row.get(col)) and row[col]:
            n_risk = int(row[col])
        if n_risk <= 0:
            continue
        # seriousEvents are complete; otherEvents are complete only at threshold 0.
        complete = (kind == "serious") or (thresh[i] <= 0)
        # Successes strictly below this count were suppressed by the reporting cut.
        cut = int(np.ceil(n_risk * thresh[i] / 100.0))

        for axis in axes:
            hit = observed.get((arm_key, axis))
            if hit is not None:
                k, n_obs = hit
                status_l.append(OBSERVED)
                k_l.append(k)
                n_l.append(n_obs or n_risk)
                cens_l.append(0)
            elif complete or cut <= 0:
                # Nothing reported from a complete table, or a threshold so small that
                # "below the cut" excludes nothing: a genuine zero.
                status_l.append(ZERO)
                k_l.append(0)
                n_l.append(n_risk)
                cens_l.append(0)
            else:
                status_l.append(CENSORED)
                k_l.append(0)
                n_l.append(n_risk)
                cens_l.append(cut)
            ax_l.append(axis_of[axis])
            arm_l.append(arm_of[arm_key])

    dar = arms["dar"].to_numpy(dtype=float)
    dar_mean = float(np.nanmean(dar))
    dar = np.where(np.isnan(dar), dar_mean, dar)
    log_n = np.log(arms["n_at_risk"].to_numpy(dtype=float))
    thresh_mean = float(thresh.mean())
    log_n_mean = float(log_n.mean())

    return ModelData(
        kind=kind,
        status=np.asarray(status_l, dtype=np.int32),
        n_affected=np.asarray(k_l, dtype=np.int32),
        n_at_risk=np.asarray(n_l, dtype=np.int32),
        censor_below=np.asarray(cens_l, dtype=np.int32),
        axis_idx=np.asarray(ax_l, dtype=np.int32),
        arm_idx=np.asarray(arm_l, dtype=np.int32),
        arm_mech_idx=arms["mechanism"].map(mech_of).to_numpy(dtype=np.int32),
        arm_family_idx=arms["payload_family"].map(family_of).to_numpy(dtype=np.int32),
        # Arms from single-arm trials get a dedicated sentinel slot one past the last
        # real trial, not 0. They used to land on 0, which is a real trial
        # (NCT00085709), and the collision was harmless only because
        # `arm_has_trial_effect` masks their contribution. It stopped being harmless the
        # moment a split masked on this index: holding out any agent with a single-arm
        # trial then matched the sentinel and discarded all 128 effect-free arms from
        # training, halving the training set in every leave-one-agent-out fold. The
        # sentinel slot is sampled and never used, which costs one parameter and removes
        # the whole class of bug.
        arm_trial_idx=(
            arms["nct_id"].map(trial_of).fillna(len(trials)).to_numpy(dtype=np.int32)
        ),
        arm_has_trial_effect=arms["nct_id"]
        .isin(set(trials))
        .astype(float)
        .to_numpy(),
        arm_agent_idx=arms["agent"].map(agent_of).to_numpy(dtype=np.int32),
        arm_dar_c=dar - dar_mean,
        arm_cleavable=arms["linker_cleavable"].fillna(False).astype(float).to_numpy(),
        arm_combo=(arms["is_monotherapy"] == False).astype(float).to_numpy(),  # noqa: E712
        arm_thresh_c=thresh - thresh_mean,
        arm_log_n_c=log_n - log_n_mean,
        axes=list(axes),
        mechanisms=mechanisms,
        families=families,
        family_to_mech=np.array(
            [
                mech_of[
                    arms.loc[arms["payload_family"] == f, "mechanism"].iloc[0]
                ]
                for f in families
            ],
            dtype=np.int32,
        ),
        agents=agents,
        trials=trials,
        arm_keys=arm_keys,
        dar_mean=dar_mean,
        thresh_mean=thresh_mean,
        log_n_mean=log_n_mean,
        cleavable_mean=float(
            arms["linker_cleavable"].fillna(False).astype(float).mean()
        ),
    )


def load(processed: Path, axes: list[str], **kw) -> ModelData:
    arms = pd.read_parquet(processed / "arms.parquet")
    obs = pd.read_parquet(processed / "observations.parquet")
    return build(arms, obs, axes, **kw)
