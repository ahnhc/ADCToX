"""Score and rank candidate designs, and refuse to rank what cannot be distinguished.

Three objectives, not fourteen:

* **O1** patient-weighted organ risk, sum over axes of w_o * p_o
* **O2** worst single axis, max over axes of p_o. Without it, a candidate that smears
  risk thinly across all fourteen axes outranks one with a single manageable peak.
* **O3** precedent, log(1 + clinical ADCs sharing the configuration). This is the
  anti-degeneracy term and the Tier-1 enforcer.

Comorbidity enters through **w_o**, not through the logit. This is the most important
epistemic choice in the module. There is no public dataset of (ADC, comorbidity,
outcome) -- zero trials report comorbidity-stratified organ AE rates -- so a learned
interaction term would be an unfalsifiable prior wearing a coefficient's clothes. As a
weight it is a declared preference:

    "we weighted the renal axis 3x because you told us creatinine clearance is 25"

rather than

    "we predict +0.8 logit on renal for creatinine clearance 25".

Same arithmetic, and only one of them is honest. The weights are returned so the UI can
show them.

Tie handling uses **paired** posterior draws: the same draw index across candidates, so
the correlation between them is preserved. Independent draws would make almost every
pair look distinguishable, which is precisely the false precision this is meant to stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .constraints import ConstraintEngine
from .enumerate import Design


@dataclass
class ScoredDesign:
    design: Design
    organ_risk: dict[str, float]            # posterior-mean rate per axis
    organ_interval: dict[str, tuple[float, float]]
    o1_weighted_risk: float
    o2_worst_axis_risk: float
    o2_worst_axis: str
    o3_precedent: float
    binding_constraint: str | None
    nearest_real_adc: str | None = None
    nearest_real_diff: str | None = None
    rank: int | None = None
    tie_group: int | None = None
    distinguishable: bool | None = None
    draws_o1: np.ndarray | None = field(default=None, repr=False)


def _pareto_front(points: np.ndarray) -> np.ndarray:
    """Boolean mask of non-dominated rows. Columns are minimized."""
    n = len(points)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        dominated = np.all(points <= points[i], axis=1) & np.any(points < points[i], axis=1)
        if dominated.any():
            keep[i] = False
    return keep


def comorbidity_weights(
    axes: list[str],
    severity_by_axis: dict[str, float],
    lam: float = 2.0,
) -> dict[str, float]:
    """w_o = 1 + lam * severity_o, with severity read off a curated registry.

    Severities are derived from the quantitative thresholds inside trial exclusion
    criteria ("LVEF < 50%", "creatinine clearance < 30"), so the magnitudes have a cited
    basis rather than being chosen by hand -- but they remain an elicited prior, not a
    fitted quantity, and must be labelled as such wherever they are displayed.
    """
    return {a: 1.0 + lam * float(severity_by_axis.get(a, 0.0)) for a in axes}


def score_designs(
    designs: list[Design],
    rate_draws: np.ndarray,
    axes: list[str],
    weights: dict[str, float],
    precedent: dict[tuple, float],
    engine: ConstraintEngine,
    at_risk_axes: set[str] | None = None,
    selectivity: dict[str, float] | None = None,
) -> list[ScoredDesign]:
    """Score candidates. `rate_draws` is (n_draws, n_designs, n_axes), paired across designs."""
    if rate_draws.shape[1] != len(designs) or rate_draws.shape[2] != len(axes):
        raise ValueError(
            f"rate_draws shape {rate_draws.shape} does not match "
            f"{len(designs)} designs x {len(axes)} axes"
        )
    w = np.array([weights[a] for a in axes])
    o1_draws = (rate_draws * w[None, None, :]).sum(axis=2)   # (draws, designs)
    o2_draws = rate_draws.max(axis=2)

    out: list[ScoredDesign] = []
    for j, design in enumerate(designs):
        mean_rates = rate_draws[:, j, :].mean(axis=0)
        lo = np.percentile(rate_draws[:, j, :], 5, axis=0)
        hi = np.percentile(rate_draws[:, j, :], 95, axis=0)
        worst = int(np.argmax(mean_rates))
        res = engine.check(design, at_risk_axes=at_risk_axes, selectivity=selectivity)
        out.append(
            ScoredDesign(
                design=design,
                organ_risk={a: float(mean_rates[i]) for i, a in enumerate(axes)},
                organ_interval={a: (float(lo[i]), float(hi[i])) for i, a in enumerate(axes)},
                o1_weighted_risk=float(o1_draws[:, j].mean()),
                o2_worst_axis_risk=float(o2_draws[:, j].mean()),
                o2_worst_axis=axes[worst],
                o3_precedent=float(precedent.get(design.key(), 0.0)),
                binding_constraint=res.binding,
                draws_o1=o1_draws[:, j],
            )
        )
    return out


def rank_and_group(
    scored: list[ScoredDesign],
    tie_threshold: float = 0.35,
    decisive_threshold: float = 0.80,
) -> tuple[list[ScoredDesign], list[int], list[list[int]]]:
    """Order by O1, then collapse adjacent candidates whose posteriors overlap.

    `tie_threshold`: if P(i better than j) sits within [1-t, t] for an adjacent pair,
    the two are not distinguishable and share a rank.
    `decisive_threshold`: a ranked list is only emitted when the leader beats the runner-up
    on this fraction of paired draws; otherwise the head of the list is an unordered set.

    Returns (ordered, pareto_indices, tie_groups).
    """
    order = sorted(range(len(scored)), key=lambda j: scored[j].o1_weighted_risk)
    ordered = [scored[j] for j in order]

    groups: list[list[int]] = []
    current = [0]
    for i in range(1, len(ordered)):
        a, b = ordered[i - 1].draws_o1, ordered[i].draws_o1
        if a is None or b is None:
            p_better = 1.0
        else:
            p_better = float((a < b).mean())
        if min(p_better, 1.0 - p_better) > tie_threshold:
            current.append(i)
        else:
            groups.append(current)
            current = [i]
    groups.append(current)

    for gi, group in enumerate(groups):
        rank = group[0] + 1
        for i in group:
            ordered[i].rank = rank
            ordered[i].tie_group = gi
            ordered[i].distinguishable = len(group) == 1

    if len(ordered) >= 2 and ordered[0].draws_o1 is not None:
        lead = float((ordered[0].draws_o1 < ordered[1].draws_o1).mean())
        if lead < decisive_threshold:
            # The leader is not decisive; mark the head group as unordered so the UI
            # presents a set rather than a winner.
            for i in groups[0]:
                ordered[i].distinguishable = False

    pts = np.array(
        [[s.o1_weighted_risk, s.o2_worst_axis_risk, -s.o3_precedent] for s in ordered]
    )
    pareto = np.where(_pareto_front(pts))[0].tolist()
    return ordered, pareto, groups


def why_not_the_obvious_one(
    designs: list[Design],
    rate_draws: np.ndarray,
    axes: list[str],
    weights: dict[str, float],
    engine: ConstraintEngine,
    at_risk_axes: set[str] | None = None,
    selectivity: dict[str, float] | None = None,
) -> dict | None:
    """The best-*scoring* candidate that a constraint excluded, and which one excluded it.

    Ten lines of code, and the single most convincing thing the output can show: it
    demonstrates the constraints actually bind rather than decorating a ranking that
    would have come out the same way without them.
    """
    w = np.array([weights[a] for a in axes])
    o1 = (rate_draws * w[None, None, :]).sum(axis=2).mean(axis=0)
    best, best_o1, best_res = None, np.inf, None
    for j, design in enumerate(designs):
        res = engine.check(design, at_risk_axes=at_risk_axes, selectivity=selectivity)
        if res.passed:
            continue
        if o1[j] < best_o1:
            best, best_o1, best_res = design, float(o1[j]), res
    if best is None:
        return None
    passing_o1 = [
        float(o1[j]) for j, d in enumerate(designs) if engine.check(
            d, at_risk_axes=at_risk_axes, selectivity=selectivity
        ).passed
    ]
    return {
        "design": best.slots,
        "weighted_risk": best_o1,
        "excluded_by": best_res.failures,
        # Whether it would actually have placed, had the constraint not excluded it.
        # Without this the row implies a constraint cost us the best candidate even when
        # the excluded design scored worse than everything that passed.
        "would_have_ranked_first": bool(passing_o1 and best_o1 < min(passing_o1)),
        "best_passing_weighted_risk": float(min(passing_o1)) if passing_o1 else None,
    }
