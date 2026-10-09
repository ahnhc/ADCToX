"""End-to-end pipeline: (comorbidity profile + target) -> proposed designs with risks.

This is the thing the Week-2 gate asks for -- a single call that turns the two product
inputs into fourteen numbers per candidate, of whatever quality the model currently
supports. It deliberately contains no modelling: it wires the enumerator, the constraint
engine, the posterior and the scorer together, so each can be tested on its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from .comorbidity.exclusion_prior import driver as exclusion_driver
from .comorbidity.hard_flags import applicable as applicable_flags
from .comorbidity.target_expression import (
    applicable as applicable_expression,
    evaluable as target_evaluable,
)
from .comorbidity.hard_flags import override_band
from .design.constraints import ConstraintEngine
from .design.enumerate import Design, DesignSpace
from .design.search import (
    comorbidity_weights,
    rank_and_group,
    score_designs,
    why_not_the_obvious_one,
)
from .model.predict import (
    MIN_ARMS_FOR_A_BAND,
    Posterior,
    decompose,
    predict_draws,
    risk_band,
)
from .taxonomy import default_taxonomy

CONF = Path(__file__).resolve().parents[2] / "conf"

# Payload -> family, the level nested inside mechanism.
#
# Built from the design space first and the registry second. The registry lists only the 18
# agents that exist, so a design-space payload no agent carries -- exatecan -- got no family
# from it, and the gap was not inert: /assess reported the design as novelty tier 2, which
# the documentation says is unsupported, while the enumerator had already admitted it under
# a Tier-1 gate. The registry still contributes PE38, which is a real agent's payload that
# the design space deliberately excludes.
_FAMILY_OF: dict[str, str] = {}
for _payload, _spec in yaml.safe_load(
    (CONF / "design_space.yaml").read_text(encoding="utf-8")
)["payloads"].items():
    _FAMILY_OF[_payload] = _spec["family"]
for _spec in yaml.safe_load(
    (CONF / "adc_registry.yaml").read_text(encoding="utf-8")
)["agents"].values():
    _FAMILY_OF.setdefault(_spec["payload"], _spec["payload_family"])


@dataclass
class ComorbidityResolution:
    """Comorbidity ids resolved to axis severities, with provenance kept."""

    severity_by_axis: dict[str, float]
    at_risk_axes: set[str]
    per_condition: list[dict]


def resolve_comorbidities(condition_ids: list[str]) -> ComorbidityResolution:
    """Map condition ids onto axis severities.

    Where several conditions hit one axis the maximum is taken, not the sum: two kinds of
    liver disease do not make the liver twice as fragile, and summing would let a long
    condition list dominate the objective purely by length.
    """
    # The validated loader, not a second CSV parse. Two independent readers of one file
    # is how a validation guard ends up protecting only one of them.
    from .schemas import comorbidity_registry

    rows = comorbidity_registry()

    severity: dict[str, float] = {}
    per_condition: list[dict] = []
    for cid in condition_ids:
        row = rows[cid]
        axes = list(row["organ_axes"])   # already split and validated at load
        sev = float(row["severity"])
        for axis in axes:
            severity[axis] = max(severity.get(axis, 0.0), sev)
        per_condition.append(
            {
                "condition": cid, "label": row["label"], "organ_axes": axes,
                "severity": sev, "severity_basis": row["severity_basis"],
            }
        )
    return ComorbidityResolution(severity, set(severity), per_condition)


def _precedent_scores(
    designs: list[Design], space: dict | None = None
) -> dict[tuple, float]:
    """log(1 + clinical ADCs sharing the configuration), the anti-degeneracy objective.

    Scored at component level rather than whole-configuration level, because almost no
    exact configuration has been built more than once -- of 5,822 cartesian
    payload-linker combinations in the reference corpus, only 135 (2.3%) exist at all.
    """
    # `space` lets a caller supply counts with one agent's own contribution removed. The
    # inverse-retrieval evaluation needs that: O3 rewards configurations clinical ADCs
    # already use, and the agent being searched for is one of them, so leaving its counts
    # in would let memory pass for prediction.
    doc = space or yaml.safe_load(
        (CONF / "design_space.yaml").read_text(encoding="utf-8")
    )
    out: dict[tuple, float] = {}
    for d in designs:
        n = min(
            doc["payloads"][d.payload].get("clinical_adcs", 0),
            doc["linkers"][d.linker].get("clinical_adcs", 0),
            doc["conjugation_dar"][d.conjugation].get("clinical_adcs", 0),
        )
        out[d.key()] = float(np.log1p(n))
    return out


def _nearest_real_adc(design: Design, registry: dict) -> tuple[str | None, str | None]:
    """Closest approved ADC by slot Hamming distance, and how the candidate differs.

    Rendering the difference as one sentence is what makes a candidate legible: "this is
    enfortumab vedotin with DAR 4 instead of 3.8" says more than seven slot values.
    """
    best, best_d, best_diffs = None, 99, []
    for key, spec in registry.items():
        if not spec.get("conventional_adc"):
            continue
        diffs = []
        if spec["payload"] != design.payload:
            diffs.append(f"payload {spec['payload']} -> {design.payload}")
        if spec["linker_type"] != design.linker:
            diffs.append(f"linker {spec['linker_type']} -> {design.linker}")
        if spec.get("dar") is None:
            # An agent whose DAR no source states cannot be confirmed as matching, so the
            # slot counts as a difference. Letting it pass silently would make an agent
            # with missing data look *closer* to the design than one with a complete
            # record -- the comparison is a Hamming distance over slots, so an unknown
            # slot has to cost something. Registry agents curated from the literature
            # routinely have no stated DAR; 11 of the 16 added from the stem sweep do not.
            diffs.append(f"DAR unknown -> {design.dar}")
        elif abs(float(spec["dar"]) - design.dar) > 0.25:
            diffs.append(f"DAR {spec['dar']} -> {design.dar}")
        if spec["isotype"] != design.isotype:
            diffs.append(f"isotype {spec['isotype']} -> {design.isotype}")
        if spec["target"] != design.target:
            diffs.append(f"target {spec['target_label']} -> {design.target}")
        if len(diffs) < best_d:
            best, best_d, best_diffs = spec["inn"], len(diffs), diffs
    if best is None:
        return None, None
    return best, ("identical slots" if not best_diffs else "; ".join(best_diffs[:3]))


def propose(
    target_antigen: str,
    condition_ids: list[str],
    posterior: Posterior,
    top_k: int = 6,
    lam: float = 2.0,
    hard_flags: bool = True,
    serious_posterior: Posterior | None = None,
    design_space_override: dict | None = None,
) -> dict:
    """The primary product path.

    `hard_flags=False` switches off the label-derived override layer, which the case-study
    evaluation needs: a rule that hardcodes "prior ILD plus a deruxtecan payload is high
    risk" would make the deruxtecan case study pass with no contribution from the model.

    `serious_posterior` makes the ranking answer the question the user actually asked. A
    declared comorbidity is a question about serious harm. Measured on this corpus, the
    two event tables rank organs differently -- topo-I payloads sit 10th of 14 on
    pulmonary in the common table and 2nd in the serious one -- so ranking on the common
    table alone put T-DXd's boxed-warning organ in the bottom third for an ILD patient.
    When supplied: O1 and the bands on at-risk axes come from the serious table, O2 and
    the bands elsewhere stay on the common one, and both numbers are reported per axis.
    Omitting it keeps the earlier single-table behaviour, and every number says which
    table produced it.
    """
    # Shared read-only singleton; see default_taxonomy() on why builders do not use it.
    tax = default_taxonomy()
    axes = list(tax.axis_order)
    space = DesignSpace()
    engine = ConstraintEngine()
    registry = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))["agents"]

    designs, _rejections = space.enumerate(target_antigen, tier=1)
    comorb = resolve_comorbidities(condition_ids)
    # On-target off-tumour: is the target abundant in an organ this patient cannot afford
    # to lose? Target-level, so it cannot separate candidates that share a target -- it
    # raises the band and names a driver, which is what the evidence supports. See
    # adctox.comorbidity.target_expression for why it is not a constraint.
    target_known = target_evaluable(target_antigen)

    def evidence_for(mechanism: str, axis: str) -> tuple[int, int]:
        """Agents and arms behind a (mechanism, axis) estimate, 0 if the corpus is silent."""
        if mechanism not in posterior.mechanisms or axis not in axes:
            return (0, 0)
        mi, ai = posterior.mechanisms.index(mechanism), axes.index(axis)
        return (
            int(posterior.evidence_agents[mi, ai]),
            int(posterior.evidence_arms[mi, ai]),
        )
    def evidence_map(mechanism: str) -> dict[str, int]:
        return {a: evidence_for(mechanism, a)[1] for a in axes}

    def serious_evidence_for(mechanism: str, axis: str) -> tuple[int, int]:
        sp = serious_posterior
        if sp is None or mechanism not in sp.mechanisms or axis not in sp.axes:
            return (0, 0)
        mi, ai = sp.mechanisms.index(mechanism), sp.axes.index(axis)
        return (int(sp.evidence_agents[mi, ai]), int(sp.evidence_arms[mi, ai]))

    def table_for(axis: str) -> str:
        """Which event table answers the question asked about this axis.

        An axis the patient is vulnerable on is a serious-harm question; the rest are
        tolerability. This is the single decision the dual-table design turns on.
        """
        if serious_posterior is not None and axis in comorb.at_risk_axes:
            return "serious"
        return "common"

    def scoring_evidence(mechanism: str) -> dict[str, int]:
        """Evidence counts from whichever table each axis is scored on.

        C6 must gate on the evidence behind the number being shown. Gating an at-risk
        axis on common-table evidence while banding it from the serious table would let a
        design through on evidence that does not support the figure the user reads.
        """
        return {
            a: (serious_evidence_for(mechanism, a)[1] if table_for(a) == "serious"
                else evidence_for(mechanism, a)[1])
            for a in axes
        }

    # Constraints are evaluated with the evidence in hand, so C6 can fire.
    passing = [
        d for d in designs
        if engine.check(
            d, at_risk_axes=comorb.at_risk_axes,
            evidence_arms=scoring_evidence(d.mechanism),
        ).passed
    ]
    if not passing:
        raise ValueError(
            f"no design for {target_antigen} both passes the chemistry and potency "
            "constraints and has usable evidence on the organs this profile flags as at "
            f"risk ({', '.join(sorted(comorb.at_risk_axes)) or 'none'}). The corpus "
            "cannot speak to the question as asked."
        )

    weights = comorbidity_weights(axes, comorb.severity_by_axis, lam=lam)

    def draws_for(ds: list[Design], post: Posterior | None = None) -> np.ndarray:
        return predict_draws(
            post or posterior,
            mechanisms=[d.mechanism for d in ds],
            families=[_FAMILY_OF.get(d.payload, "") for d in ds],
            dars=np.array([d.dar for d in ds]),
            cleavables=np.array([float(d.cleavable) for d in ds]),
        )

    def serious_draws_for(ds: list[Design]) -> np.ndarray | None:
        if serious_posterior is None:
            return None
        d = draws_for(ds, serious_posterior)
        # The two fits are independent runs, so their draw counts need not match. O1 is a
        # mean over draws, and the tie test pairs draws WITHIN one objective, so a
        # truncation to the common length keeps both valid.
        return d

    evidence_arg = {m: scoring_evidence(m) for m in posterior.mechanisms}
    sd_passing = serious_draws_for(passing)
    common_passing = draws_for(passing)
    if sd_passing is not None and sd_passing.shape[0] != common_passing.shape[0]:
        n = min(sd_passing.shape[0], common_passing.shape[0])
        sd_passing, common_passing = sd_passing[:n], common_passing[:n]
    scored = score_designs(
        passing, common_passing, axes, weights,
        _precedent_scores(passing, design_space_override), engine,
        at_risk_axes=comorb.at_risk_axes,
        evidence_by_mechanism=evidence_arg,
        serious_draws=sd_passing,
    )
    ordered, pareto, groups = rank_and_group(scored)
    sd_all = serious_draws_for(designs)
    common_all = draws_for(designs)
    if sd_all is not None and sd_all.shape[0] != common_all.shape[0]:
        n = min(sd_all.shape[0], common_all.shape[0])
        sd_all, common_all = sd_all[:n], common_all[:n]
    why_not = why_not_the_obvious_one(
        designs, common_all, axes, weights, engine,
        at_risk_axes=comorb.at_risk_axes,
        evidence_by_mechanism=evidence_arg,
        serious_draws=sd_all,
    )

    # O1 is the ranking key, but a candidate can minimise patient-weighted risk while
    # carrying a high peak on an axis the patient has no stated vulnerability on. That is
    # the objective working as specified, not a bug -- yet shown as "rank 1" with no
    # further signal it would mislead. So the peak is surfaced explicitly, and Pareto
    # membership (which does account for O2) is attached per candidate.
    pareto_set = set(pareto)
    # Which candidates to show. The first `top_k` by O1 is wrong once the head group is
    # large: on the HER2 query above, 49 of 74 candidates sit in one indistinguishable
    # group, and taking the first six by their secondary order displayed three dominated
    # designs while hiding five non-dominated ones. Showing a candidate that is beaten on
    # all three objectives, in place of one that is beaten on none, cannot be defended
    # whatever the ordering inside the group.
    #
    # So the Pareto front comes first, in the order already established, and the remainder
    # fills any slots left over. Where O1 does separate the candidates the front contains
    # the leader anyway, so this changes nothing in the case the ranking works.
    #
    # Within the front, one per payload before a second of anything. The ordering inside a
    # tie group is a secondary preference, and taking the first six of it showed DGN549
    # twice, DM1 twice and DM4 twice -- three payloads of the front's six, and two of those
    # pairs are designs this model cannot tell apart at all -- while MMAE, MMAF and the
    # pyrrolobenzodiazepine never appeared despite being non-dominated. Payload is the
    # dominant lever in this model, so spanning it is what shows the reader the choice they
    # actually have. `shown_selection` states the rule in the response.
    front = [i for i in range(len(ordered)) if i in pareto_set]
    shown_idx: list[int] = []
    seen_payload: set[str] = set()
    for i in front:
        payload = ordered[i].design.payload
        if payload not in seen_payload:
            seen_payload.add(payload)
            shown_idx.append(i)
        if len(shown_idx) == top_k:
            break
    if len(shown_idx) < top_k:
        shown_idx += [i for i in front if i not in shown_idx][
            : top_k - len(shown_idx)
        ]
    if len(shown_idx) < top_k:
        shown_idx += [
            i for i in range(len(ordered)) if i not in pareto_set
        ][: top_k - len(shown_idx)]
    conditions = set(condition_ids)
    candidates = []
    for idx in shown_idx:
        s = ordered[idx]
        flags_by_axis = applicable_flags(
            s.design.mechanism, s.design.payload, conditions, enabled=hard_flags
        )
        expr_by_axis = applicable_expression(
            target_antigen, comorb.at_risk_axes,
            permeable_payload=bool(space.payloads[s.design.payload].get("membrane_permeable")),
            enabled=hard_flags,
        )
        nearest, diff = _nearest_real_adc(s.design, registry)
        def band_for(axis: str) -> str:
            """Model band, raised where a label rule applies. A rule can only raise.

            Banded against whichever table answers the question asked about this axis,
            and on that table's own measured edges. The edges differ by an order of
            magnitude between tables, so banding a serious rate on common-table edges
            renders a 4% serious rate as "low" -- the error this replaces.
            """
            if table_for(axis) == "serious" and s.serious_risk is not None:
                base = risk_band(
                    s.serious_risk[axis],
                    serious_evidence_for(s.design.mechanism, axis)[1],
                    serious_posterior.band_edges,
                )
            else:
                base = risk_band(
                    s.organ_risk[axis],
                    evidence_for(s.design.mechanism, axis)[1],
                    posterior.band_edges,
                )
            raised = override_band(base, flags_by_axis.get(axis, []))
            # An abundant target in a compromised organ raises the band one step, and
            # never lowers it. One step rather than straight to `high`, because the
            # aggregate evidence is weak: expression does not predict labelled toxicity
            # (AUROC 0.52-0.58), it only locates the organ a target could reach.
            if axis in expr_by_axis and raised != "no_evidence":
                ladder = ["low", "moderate", "high"]
                if raised in ladder:
                    raised = ladder[min(ladder.index(raised) + 1, len(ladder) - 1)]
            return raised

        high_axes = [
            a for a in axes
            if band_for(a) == "high" and a not in comorb.at_risk_axes
        ]
        candidates.append(
            {
                "rank": s.rank, "tie_group": s.tie_group,
                "on_pareto_front": idx in pareto_set,
                # Axes in the high band that the patient-weighted objective did not
                # penalise, because no stated comorbidity touches them.
                "unweighted_high_axes": high_axes,
                "distinguishable": s.distinguishable,
                # Head of the list only, and None elsewhere. A leader can be
                # separable from the runner-up and still not beat it on enough
                # paired draws to print a winner.
                "lead_is_decisive": s.lead_is_decisive,
                "group_size": s.group_size,
                "secondary_order_basis": s.secondary_order_basis,
                "lead_p": (
                    round(s.lead_p, 3) if s.lead_p is not None else None
                ),
                "design": s.design.slots,
                "mechanism": s.design.mechanism,
                "organ_risks": [
                    {
                        "organ_axis": a, "label": tax.axes[a],
                        # Suppressed where the corpus has too little to say: a point
                        # estimate on an unevidenced axis is the prior wearing a number.
                        "point_estimate": (
                            round(s.organ_risk[a], 4)
                            if evidence_for(s.design.mechanism, a)[1]
                            >= MIN_ARMS_FOR_A_BAND
                            else None
                        ),
                        "interval": {
                            "lo": round(s.organ_interval[a][0], 4),
                            "hi": round(s.organ_interval[a][1], 4),
                            "kind": "credible_90",
                        },
                        # Every number carries an interval, including the serious one.
                        # A serious-basis row was showing a bare point while the rules
                        # this project set for itself require an interval beside it --
                        # and it is the row a vulnerable patient reads first.
                        "serious_interval": (
                            None if s.serious_interval is None
                            or serious_evidence_for(s.design.mechanism, a)[1]
                            < MIN_ARMS_FOR_A_BAND
                            else {
                                "lo": round(s.serious_interval[a][0], 4),
                                "hi": round(s.serious_interval[a][1], 4),
                                "kind": "credible_90",
                            }
                        ),
                        # The serious-event rate for the same axis. Reported alongside
                        # rather than instead of `point_estimate`: they answer different
                        # questions and, measured on this corpus, rank organs differently.
                        "serious_estimate": (
                            None if s.serious_risk is None
                            or serious_evidence_for(s.design.mechanism, a)[1]
                            < MIN_ARMS_FOR_A_BAND
                            else round(s.serious_risk[a], 4)
                        ),
                        "risk_band": band_for(a),
                        # Which event table the band was computed on. An axis the patient
                        # is vulnerable on is a serious-harm question; the rest are
                        # tolerability. Stated because the two are not comparable.
                        "band_basis": table_for(a),
                        # Stated separately so a reader can see whether a band came from
                        # the fit or from a label rule, which is the first thing a reviewer
                        # will ask about a red axis.
                        "band_source": (
                            "rule" if flags_by_axis.get(a)
                            else "target_expression" if a in expr_by_axis
                            else "model"
                        ),
                        # The fitted terms come first and always, because the model is
                        # the source that always applies. Listing only the other three
                        # left a model-banded axis with an empty driver list -- the
                        # patient's at-risk organ showing a band and a weight with no
                        # account of either.
                        #
                        # `decompose` is the same function `/assess` uses, deliberately. A
                        # first attempt added a second, thinner driver builder here, which
                        # would have made the two endpoints explain one number two
                        # different ways -- the inconsistency `test_propose_and_assess_
                        # cannot_disagree_about_novelty_tier` already guards against for
                        # the novelty tier.
                        "drivers": (
                            decompose(
                                posterior, s.design.mechanism,
                                _FAMILY_OF.get(s.design.payload, s.design.mechanism),
                                float(s.design.dar), bool(s.design.cleavable), a,
                            )
                            + [f.as_driver() for f in flags_by_axis.get(a, [])]
                            + ([expr_by_axis[a].as_driver()] if a in expr_by_axis else [])
                            + [
                                d for d in
                                [exclusion_driver(s.design.mechanism, a)]
                                if d is not None
                            ]
                        ),
                        # Evidence from the table this axis is scored on, so the count
                        # supports the figure shown rather than a different one. C6
                        # already gates on this same count.
                        "n_supporting_agents": (
                            serious_evidence_for(s.design.mechanism, a)[0]
                            if table_for(a) == "serious"
                            else evidence_for(s.design.mechanism, a)[0]
                        ),
                        "n_supporting_arms": (
                            serious_evidence_for(s.design.mechanism, a)[1]
                            if table_for(a) == "serious"
                            else evidence_for(s.design.mechanism, a)[1]
                        ),
                        "weight_applied": weights[a],
                        "at_risk_for_patient": a in comorb.at_risk_axes,
                    }
                    for a in axes
                ],
                "weighted_risk": round(s.o1_weighted_risk, 4),
                # O1 and O2 are deliberately computed on different tables, so each number
                # states its own. Comparing them to each other is meaningless -- serious
                # rates are an order of magnitude smaller.
                "weighted_risk_basis": s.o1_basis,
                "worst_axis": s.o2_worst_axis,
                "worst_axis_risk": round(s.o2_worst_axis_risk, 4),
                "worst_axis_risk_basis": "common",
                "precedent_score": round(s.o3_precedent, 3),
                "binding_constraint": s.binding_constraint,
                "nearest_real_adc": nearest,
                "nearest_real_diff": diff,
                # Every enumerated design is Tier 1 by construction: the enumerator admits
                # a component only if some ADC carrying it reached at least phase 1, and
                # only the combination is new. Components with clinical but no *approved*
                # precedent are flagged rather than excluded.
                "novelty_tier": 1,
                "has_unapproved_component": s.design.has_unapproved_component,
            }
        )

    return {
        "proposal_id": f"prp_{uuid.uuid4().hex[:12]}",
        "target_antigen": target_antigen,
        "n_enumerated": len(designs),
        "n_passed_constraints": len(passing),
        "candidates": candidates,
        # Positions within `candidates`, not indices into the full ordering: a
        # consumer can only resolve what it was sent.
        "pareto_front": [
            pos for pos, i in enumerate(shown_idx) if i in pareto_set
        ],
        "n_pareto_front": len(pareto),
        "shown_selection": (
            "non-dominated candidates, one per payload chemistry before a second "
            "of any, since the ranking does not resolve and payload is the "
            "dominant lever"
        ),
        "tie_groups": groups,
        "weights_applied": weights,
        "comorbidity_resolution": comorb.per_condition,
        "why_not_the_obvious_one": why_not,
        "hard_flags_enabled": hard_flags,
    }
