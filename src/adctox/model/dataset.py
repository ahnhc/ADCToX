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
    # 1.0 for an arm extracted from a paper, 0.0 for a ClinicalTrials.gov record.
    #
    # Needed because `arm_combo` was carrying it. Every one of the 139 combination arms is a
    # registry arm and none of the 194 literature arms is a combination, so the two
    # indicators correlate at -0.53 and `b_combo` estimates "registry combination against
    # everything else" rather than "combination against monotherapy". Its posterior mean
    # went from +0.195 on the registry corpus to +1.091 on the expanded one, which is the
    # reference group changing rather than combinations getting worse.
    #
    # Three cells over two parameters, so both are estimable: literature monotherapy,
    # registry monotherapy, registry combination.
    arm_is_literature: np.ndarray
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
        """Arms that contribute at least one cell.

        This is smaller than ``len(arm_keys)`` for the serious table, because an arm that
        published only a common-events table contributes nothing there. The summary must
        count what the fit actually sees: reporting 594 arms for a serious grid built from
        290 of them would overstate the corpus by a factor of two.

        An earlier version of this note claimed the index arrays kept every arm so that an
        arm's position was the same under both tables. That stopped being true once the
        any-grade grid began excluding columns reporting a severity-restricted or
        non-incidence outcome, and it was never load-bearing: each fit builds its own
        ``ModelData``, the agent and trial effects are indexed within one fit, and a saved
        posterior carries agent labels rather than positions.
        """
        return int(np.unique(self.arm_idx).size)

    @property
    def n_contributing_agents(self) -> int:
        """Agents with at least one cell -- see :attr:`n_arms`."""
        return int(np.unique(self.arm_agent_idx[np.unique(self.arm_idx)]).size)

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
            f"{self.n_contributing_agents} agents, {len(self.mechanisms)} mechanisms, "
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
    drop_agents: list[str] | None = None,
    drop_uninformative_absences: bool = False,
) -> ModelData:
    """Assemble the full (arm x axis) grid for one event table.

    ``kind='other'`` is the primary analysis: it carries far more signal than the serious
    table, and the censoring above is what makes it usable. ``kind='serious'`` is the
    robustness check, where every missing cell is a true zero and no censoring model is
    needed -- if the two disagree, the censoring treatment is doing the work and must be
    reported as such.
    """
    arms = arms.copy()
    if drop_agents:
        # Holding an agent out for an honest out-of-corpus prediction, which is what the
        # inverse-retrieval evaluation needs: the model must not have seen the drug whose
        # design it is being asked to propose.
        #
        # Arms sharing a trial with the dropped agent go too. NCT03529110 is a T-DXd
        # versus T-DM1 head-to-head, so dropping one arm leaves a comparator whose
        # trial-level intercept was fitted partly from the arm just removed -- the leak
        # splits.py documents, and it would flatter the retrieval exactly where the
        # retrieval is hardest.
        drop = set(drop_agents)
        held = arms["agent"].isin(drop)
        shared = set(
            arms.loc[held & (arms["nct_id"].notna()), "nct_id"].unique().tolist()
        )
        multi = arms["nct_id"].value_counts()
        shared = {t for t in shared if multi.get(t, 0) >= 2}
        arms = arms[~(held | arms["nct_id"].isin(shared))].reset_index(drop=True)
        obs = obs[obs["arm_key"].isin(set(arms["arm_key"]))]
    # The arm-level fallback denominator, across whichever outcome tables this corpus
    # carries. Enumerated rather than hardcoded to two, because the severe-tail columns the
    # any-grade grid excludes form a third table and the list has to grow with them.
    risk_cols = [c for c in arms.columns if c.startswith("n_at_risk_")]
    arms["n_at_risk"] = arms[risk_cols].max(axis=1)
    keep = arms["agent"].notna() & (arms["n_at_risk"] >= min_n)
    if "agent_class_column" in arms.columns:
        # Not an outcome question but an attribution one, so it applies to both tables. A
        # column headed "Novel anti-HER2 ADCs (n = 73)" is the comparator arm of a paper
        # about trastuzumab emtansine, and the title gate admitted it because the title
        # named the agent and no other ADC appeared by name in the table.
        keep &= ~arms["agent_class_column"].fillna(False).astype(bool)
    if kind == "other" and "column_outcome" in arms.columns:
        # `otherEvents` is any-grade, all-cause incidence, and a literature column is only
        # comparable to it if it reports the same thing. 106 of 414 literature arms do not:
        # a severity-restricted tail ("Grade >=3"), deaths ("Grade 5"), a serious-event
        # column, or a clinical action per organ ("EV Dose Reduction", "Permanent
        # Discontinuation") -- the last of which is not an incidence at all. All were being
        # merged in as though they were any-grade, the clearest case a trastuzumab
        # deruxtecan arm reporting nausea at 1.4% against a median of 67% across its other
        # 79 arms.
        #
        # Dropped rather than adjusted, because an adjustment would be a guess at a grade
        # distribution the papers do not report. It costs no agents: every agent with such
        # an arm also has an any-grade one. No registry arm is affected -- a
        # ClinicalTrials.gov event group has no outcome qualifier in its title.
        keep &= arms["column_outcome"].fillna("any_grade") == "any_grade"
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

    # Whether an absent organ is *informative* for this arm, which is not the same question
    # as whether a threshold exists.
    #
    # A ClinicalTrials.gov record with `frequencyThreshold = 5` means every event above 5%
    # is listed, so an organ that does not appear has a rate below 5% and the censored
    # likelihood is exactly right. A paper table captioned "most common adverse events"
    # with no stated cut means the author *selected* some organs, and absence then carries
    # almost nothing -- the selection was not a threshold on the rate.
    #
    # Treating the second as the first is what the first ablation round measured as harmful.
    # Literature arms took the observed share from 86.2% to 60.3%, about 2,200 of their
    # 3,360 cells are censored, and 83% of them carry a boundary derived from the minimum
    # printed rate rather than a stated cut -- so the model was told "below X" with X too
    # large, thousands of times, and the leave-one-agent-out delta went from -0.0422 to
    # -0.0782.
    #
    # `drop_uninformative_absences` keeps those arms' observed cells and drops only the
    # absences that are selection rather than censoring. That is different from dropping
    # the arms, which is what the explicit-threshold-only corpus does and which costs 362
    # of 414 paper arms.
    bounded = (
        arms["threshold_is_upper_bound"].fillna(False).astype(bool).to_numpy()
        if "threshold_is_upper_bound" in arms.columns
        else np.zeros(len(arms), dtype=bool)
    )

    sub = obs[(obs["kind"] == kind) & obs["arm_key"].isin(set(arm_keys))]
    observed = {
        (r.arm_key, r.axis): (int(r.n_affected), int(r.n_at_risk))
        for r in sub.itertuples()
    }

    # `arms.n_at_risk` is the maximum of the two table denominators, so an arm that
    # published only a common-events table still carries a positive denominator when the
    # serious grid is built. Taken literally that puts 405 of the 414 literature arms into
    # the serious grid on the strength of a denominator from a different table, where every
    # axis is absent -- about 5,600 cells asserting either a zero or a bound for a table
    # the paper never printed. An arm belongs in a kind's grid only if the corpus reported
    # that kind for it: a denominator of its own, or at least one observation. The
    # observation test is required, because 8 registry arms report serious events without a
    # serious denominator and must keep the arm-level fallback.
    reporting = {arm_key for arm_key, _ in observed}

    status_l, k_l, n_l, cens_l, ax_l, arm_l = [], [], [], [], [], []
    for i, row in arms.iterrows():
        arm_key = row["arm_key"]
        n_risk = int(row["n_at_risk"])
        # Prefer the table-specific denominator where the corpus gave one.
        col = f"n_at_risk_{kind}"
        has_denominator = pd.notna(row.get(col)) and bool(row[col])
        if has_denominator:
            n_risk = int(row[col])
        elif arm_key not in reporting:
            continue
        if n_risk <= 0:
            continue
        # ClinicalTrials.gov `seriousEvents` are complete -- the registry lists every
        # serious event with no frequency cut -- so an absent organ is a true zero there.
        # A *paper's* serious-adverse-event table is not complete: it is selected like any
        # other table, and 9 literature arms report a median of 5 axes each, which would
        # assert about 81 zeros the papers never claim. A zero is a stronger false
        # statement than a censoring bound, so the completeness assumption is withdrawn
        # for any arm whose reporting cut is only a bound.
        #
        # Registry arms have no `threshold_is_upper_bound`, so `bounded` is False for them
        # and this changes nothing about the registry corpus.
        # Only `seriousEvents` is complete, and only on the registry: see the note above.
        # A grade-restricted table is selected exactly like a common-events one, so its
        # absences are censored rather than zero.
        complete = (kind == "serious" and not bounded[i]) or (thresh[i] <= 0)
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
            elif drop_uninformative_absences and bounded[i]:
                # Selection, not censoring: this arm's cut is a bound derived from its own
                # printed rates, so an absent organ says nothing about its rate. Dropping
                # the cell is the honest encoding of "no information", and it is why this
                # option exists.
                continue
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
        arm_is_literature=(
            arms["source"].notna().astype(float).to_numpy()
            if "source" in arms.columns
            else np.zeros(len(arms), dtype=float)
        ),
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
