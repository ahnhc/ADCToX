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
    # Serious-event rates for the same design, when the serious posterior is supplied.
    # Kept alongside rather than instead of `organ_risk`: the two answer different
    # questions ("does this chemistry irritate this organ" vs "does it damage it") and
    # the corpus shows they rank organs differently -- topo-I payloads sit 10th of 14 on
    # pulmonary in the common table and 2nd in the serious one, and the second is the one
    # that matches T-DXd's boxed warning.
    serious_risk: dict[str, float] | None = None
    serious_interval: dict[str, tuple[float, float]] | None = None
    # Which table O1 was computed on, so the ranking number is self-describing.
    o1_basis: str = "common"
    nearest_real_adc: str | None = None
    nearest_real_diff: str | None = None
    rank: int | None = None
    tie_group: int | None = None
    # Two different statements, which one flag used to carry and which read as a
    # contradiction whenever the leader sat alone in its tie group: the interface said
    # "not distinguishable from its group" about a group of one.
    #
    # `distinguishable` is pairwise: this candidate's tie group holds only itself, so it is
    # separable from its immediate neighbours.
    distinguishable: bool | None = None
    # `lead_is_decisive` is about the head of the list only, and is None for everything
    # else. The leader can be separable from the runner-up and still win on too few paired
    # draws to print a winner, which is the case the decisive threshold exists for.
    lead_is_decisive: bool | None = None
    # P(this candidate's weighted risk < the runner-up's), on paired draws. Head only.
    lead_p: float | None = None
    # How many candidates share this one's rank, so a reader does not have to count them.
    group_size: int | None = None
    # Set only where the group holds more than one candidate: what the display order inside
    # it means, since O1 has stopped discriminating and something still had to order them.
    secondary_order_basis: str | None = None
    draws_o1: np.ndarray | None = field(default=None, repr=False)


def _p_better(a: np.ndarray, b: np.ndarray) -> float:
    """P(a beats b) on paired draws, splitting exact ties.

    A strict ``(a < b).mean()`` reads an exact tie as a loss, and exact ties are the normal
    case here rather than a corner: the model has no term separating DM1 from DM4, both
    maytansinoids on the same linker, so their predicted risk is identical in every draw.
    The strict form returned 0.0 for such a pair, which `min(p, 1-p)` then read as decisive
    separation -- so two designs the model considers the same were printed as rank 1 and
    rank 2, while pairs that genuinely overlapped at P = 0.53 were correctly merged. The
    comparison was inverted precisely where it mattered most.

    Splitting the tied mass sends an identical pair to 0.5, which is both the right answer
    and the most strongly tied value the thresholds can see.
    """
    return float((a < b).mean() + 0.5 * (a == b).mean())


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
    # Evidence per axis for each mechanism, so the engine's C6 check can fire: a
    # candidate whose chemistry is unstudied on an at-risk organ must not be ranked as
    # though it were safe there.
    evidence_by_mechanism: dict[str, dict[str, int]] | None = None,
    # Serious-event rate draws for the same designs in the same order. When supplied, O1
    # -- the patient-weighted risk that the ranking is keyed on -- is computed from THESE
    # rather than from `rate_draws`.
    #
    # Why: O1 exists to answer "how much does this design threaten this patient". A
    # declared comorbidity is a question about serious harm, not about whether the patient
    # will also feel nauseated. Keying O1 on the common table ranked designs by
    # tolerability and then presented the result as patient risk. O2 stays on the common
    # table, where "worst single axis" is the tolerability guard it was meant to be.
    serious_draws: np.ndarray | None = None,
) -> list[ScoredDesign]:
    """Score candidates. `rate_draws` is (n_draws, n_designs, n_axes), paired across designs."""
    if rate_draws.shape[1] != len(designs) or rate_draws.shape[2] != len(axes):
        raise ValueError(
            f"rate_draws shape {rate_draws.shape} does not match "
            f"{len(designs)} designs x {len(axes)} axes"
        )
    if serious_draws is not None and serious_draws.shape != rate_draws.shape:
        raise ValueError(
            f"serious_draws shape {serious_draws.shape} must match rate_draws "
            f"{rate_draws.shape}; the two must be paired design-for-design and "
            "draw-for-draw or the tie test is meaningless"
        )
    w = np.array([weights[a] for a in axes])
    o1_source = rate_draws if serious_draws is None else serious_draws
    o1_basis = "common" if serious_draws is None else "serious"
    o1_draws = (o1_source * w[None, None, :]).sum(axis=2)   # (draws, designs)
    o2_draws = rate_draws.max(axis=2)

    out: list[ScoredDesign] = []
    for j, design in enumerate(designs):
        mean_rates = rate_draws[:, j, :].mean(axis=0)
        lo = np.percentile(rate_draws[:, j, :], 5, axis=0)
        hi = np.percentile(rate_draws[:, j, :], 95, axis=0)
        worst = int(np.argmax(mean_rates))
        res = engine.check(
            design, at_risk_axes=at_risk_axes, selectivity=selectivity,
            evidence_arms=(evidence_by_mechanism or {}).get(design.mechanism),
        )
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
                serious_risk=(
                    None if serious_draws is None
                    else {a: float(serious_draws[:, j, i].mean())
                          for i, a in enumerate(axes)}
                ),
                serious_interval=(
                    None if serious_draws is None
                    else {
                        a: (
                            float(np.percentile(serious_draws[:, j, i], 5)),
                            float(np.percentile(serious_draws[:, j, i], 95)),
                        )
                        for i, a in enumerate(axes)
                    }
                ),
                o1_basis=o1_basis,
                draws_o1=o1_draws[:, j],
            )
        )
    return out


def rank_and_group(
    scored: list[ScoredDesign],
    tie_threshold: float = 0.35,
    decisive_threshold: float = 0.80,
) -> tuple[list[ScoredDesign], list[int], list[list[int]]]:
    """Order by O1, then collapse candidates whose posteriors overlap with their group's best.

    `tie_threshold`: a candidate joins the open group if P(group leader beats it) sits
    within [t, 1-t]. Measured against the **leader** and not the immediate predecessor:
    chaining on adjacent pairs is transitive, so A~B and B~C put A and C in one group even
    where A beats C on nearly every draw, and on a real query that swallowed all 74
    candidates into a single set. Leader-anchored, the same query gives two groups of 49
    and 25.
    `decisive_threshold`: a ranked list is only emitted when the leader beats the runner-up
    on this fraction of paired draws; otherwise the head of the list is an unordered set.

    Returns (ordered, pareto_indices, tie_groups).
    """
    order = sorted(range(len(scored)), key=lambda j: scored[j].o1_weighted_risk)
    ordered = [scored[j] for j in order]

    groups: list[list[int]] = []
    current = [0]
    for i in range(1, len(ordered)):
        a, b = ordered[current[0]].draws_o1, ordered[i].draws_o1
        if a is None or b is None:
            p_better = 1.0
        else:
            p_better = _p_better(a, b)
        if min(p_better, 1.0 - p_better) > tie_threshold:
            current.append(i)
        else:
            groups.append(current)
            current = [i]
    groups.append(current)

    # Within a group O1 has said all it can, so the display order comes from the other two
    # objectives: worst single organ first, then precedent. This is a stated preference and
    # not a confidence ordering, which is why `distinguishable` stays False for all of them
    # and `secondary_order_basis` names the criterion on every card.
    for group in groups:
        if len(group) > 1:
            inner = sorted(
                group,
                key=lambda i: (ordered[i].o2_worst_axis_risk, -ordered[i].o3_precedent),
            )
            reordered = [ordered[i] for i in inner]
            for slot, item in zip(group, reordered):
                ordered[slot] = item

    for gi, group in enumerate(groups):
        rank = group[0] + 1
        for i in group:
            ordered[i].rank = rank
            ordered[i].tie_group = gi
            ordered[i].distinguishable = len(group) == 1
            ordered[i].group_size = len(group)
            if len(group) > 1:
                ordered[i].secondary_order_basis = (
                    "worst single organ, then precedent -- O1 cannot separate this group"
                )

    if len(ordered) >= 2 and ordered[0].draws_o1 is not None:
        lead = _p_better(ordered[0].draws_o1, ordered[1].draws_o1)
        # The head group carries the decisiveness verdict separately from the pairwise one.
        # Collapsing the two into `distinguishable` made a singleton head group report that
        # it was indistinguishable from a group containing nothing else.
        for i in groups[0]:
            ordered[i].lead_is_decisive = lead >= decisive_threshold
            ordered[i].lead_p = lead

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
    # Evidence per axis for each mechanism, so the engine's C6 check can fire: a
    # candidate whose chemistry is unstudied on an at-risk organ must not be ranked as
    # though it were safe there.
    evidence_by_mechanism: dict[str, dict[str, int]] | None = None,
    # Must be the same basis `score_designs` used, or the claim "this would have ranked
    # first" is made on a different objective from the ranking it refers to.
    serious_draws: np.ndarray | None = None,
) -> dict | None:
    """The best-*scoring* candidate that a constraint excluded, and which one excluded it.

    Ten lines of code, and the single most convincing thing the output can show: it
    demonstrates the constraints actually bind rather than decorating a ranking that
    would have come out the same way without them.
    """
    w = np.array([weights[a] for a in axes])
    o1_source = rate_draws if serious_draws is None else serious_draws
    o1 = (o1_source * w[None, None, :]).sum(axis=2).mean(axis=0)
    best, best_o1, best_res = None, np.inf, None
    for j, design in enumerate(designs):
        res = engine.check(
            design, at_risk_axes=at_risk_axes, selectivity=selectivity,
            evidence_arms=(evidence_by_mechanism or {}).get(design.mechanism),
        )
        if res.passed:
            continue
        if o1[j] < best_o1:
            best, best_o1, best_res = design, float(o1[j]), res
    if best is None:
        return None
    passing_o1 = [
        float(o1[j]) for j, d in enumerate(designs) if engine.check(
            d, at_risk_axes=at_risk_axes, selectivity=selectivity,
            evidence_arms=(evidence_by_mechanism or {}).get(d.mechanism),
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
