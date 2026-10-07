"""End-to-end pipeline: (comorbidity profile + target) -> proposed designs with risks.

This is the thing the Week-2 gate asks for -- a single call that turns the two product
inputs into fourteen numbers per candidate, of whatever quality the model currently
supports. It deliberately contains no modelling: it wires the enumerator, the constraint
engine, the posterior and the scorer together, so each can be tested on its own.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from .comorbidity.exclusion_prior import driver as exclusion_driver
from .comorbidity.hard_flags import applicable as applicable_flags
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
    predict_draws,
    risk_band,
)
from .taxonomy import Taxonomy

CONF = Path(__file__).resolve().parents[2] / "conf"

# Payload -> family, the level nested inside mechanism. Derived from the registry so the
# two cannot drift apart.
_FAMILY_OF: dict[str, str] = {}
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
    rows: dict[str, dict] = {}
    with (CONF / "comorbidity_registry.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows[row["id"]] = row

    severity: dict[str, float] = {}
    per_condition: list[dict] = []
    for cid in condition_ids:
        row = rows[cid]
        axes = [a for a in row["organ_axes"].split(";") if a]
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


def _precedent_scores(designs: list[Design]) -> dict[tuple, float]:
    """log(1 + clinical ADCs sharing the configuration), the anti-degeneracy objective.

    Scored at component level rather than whole-configuration level, because almost no
    exact configuration has been built more than once -- of 5,822 cartesian
    payload-linker combinations in the reference corpus, only 135 (2.3%) exist at all.
    """
    doc = yaml.safe_load((CONF / "design_space.yaml").read_text(encoding="utf-8"))
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
        if abs(float(spec["dar"]) - design.dar) > 0.25:
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
    tax = Taxonomy()
    axes = list(tax.axis_order)
    space = DesignSpace()
    engine = ConstraintEngine()
    registry = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))["agents"]

    designs, _rejections = space.enumerate(target_antigen, tier=1)
    comorb = resolve_comorbidities(condition_ids)

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
        _precedent_scores(passing), engine,
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
    conditions = set(condition_ids)
    candidates = []
    for idx, s in enumerate(ordered[:top_k]):
        flags_by_axis = applicable_flags(
            s.design.mechanism, s.design.payload, conditions, enabled=hard_flags
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
            return override_band(base, flags_by_axis.get(axis, []))

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
                            "rule" if flags_by_axis.get(a) else "model"
                        ),
                        "drivers": (
                            [f.as_driver() for f in flags_by_axis.get(a, [])]
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
        "pareto_front": [i for i in pareto if i < top_k],
        "tie_groups": groups,
        "weights_applied": weights,
        "comorbidity_resolution": comorb.per_condition,
        "why_not_the_obvious_one": why_not,
        "hard_flags_enabled": hard_flags,
    }
