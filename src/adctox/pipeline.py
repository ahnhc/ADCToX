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

from .design.constraints import ConstraintEngine
from .design.enumerate import Design, DesignSpace
from .design.search import (
    comorbidity_weights,
    rank_and_group,
    score_designs,
    why_not_the_obvious_one,
)
from .model.predict import Posterior, predict_draws, risk_band
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
    include_tier_1_5: bool = False,
    lam: float = 2.0,
) -> dict:
    """The primary product path."""
    tax = Taxonomy()
    axes = list(tax.axis_order)
    space = DesignSpace()
    engine = ConstraintEngine()
    registry = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))["agents"]

    designs, _rejections = space.enumerate(
        target_antigen, tier=1, include_unapproved_conjugation=include_tier_1_5
    )
    passing = [d for d in designs if engine.check(d).passed]
    if not passing:
        raise ValueError(
            f"no chemically valid, precedented design passes the constraints for "
            f"{target_antigen}"
        )

    comorb = resolve_comorbidities(condition_ids)
    weights = comorbidity_weights(axes, comorb.severity_by_axis, lam=lam)

    def draws_for(ds: list[Design]) -> np.ndarray:
        return predict_draws(
            posterior,
            mechanisms=[d.mechanism for d in ds],
            families=[_FAMILY_OF.get(d.payload, "") for d in ds],
            dars=np.array([d.dar for d in ds]),
            cleavables=np.array([float(d.cleavable) for d in ds]),
        )

    scored = score_designs(
        passing, draws_for(passing), axes, weights,
        _precedent_scores(passing), engine,
        at_risk_axes=comorb.at_risk_axes,
    )
    ordered, pareto, groups = rank_and_group(scored)
    why_not = why_not_the_obvious_one(
        designs, draws_for(designs), axes, weights, engine,
        at_risk_axes=comorb.at_risk_axes,
    )

    # O1 is the ranking key, but a candidate can minimise patient-weighted risk while
    # carrying a high peak on an axis the patient has no stated vulnerability on. That is
    # the objective working as specified, not a bug -- yet shown as "rank 1" with no
    # further signal it would mislead. So the peak is surfaced explicitly, and Pareto
    # membership (which does account for O2) is attached per candidate.
    pareto_set = set(pareto)
    candidates = []
    for idx, s in enumerate(ordered[:top_k]):
        nearest, diff = _nearest_real_adc(s.design, registry)
        high_axes = [
            a for a in axes
            if risk_band(s.organ_risk[a], 1) == "high" and a not in comorb.at_risk_axes
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
                        "point_estimate": round(s.organ_risk[a], 4),
                        "interval": {
                            "lo": round(s.organ_interval[a][0], 4),
                            "hi": round(s.organ_interval[a][1], 4),
                            "kind": "credible_90",
                        },
                        "risk_band": risk_band(s.organ_risk[a], 1),
                        "weight_applied": weights[a],
                        "at_risk_for_patient": a in comorb.at_risk_axes,
                    }
                    for a in axes
                ],
                "weighted_risk": round(s.o1_weighted_risk, 4),
                "worst_axis": s.o2_worst_axis,
                "worst_axis_risk": round(s.o2_worst_axis_risk, 4),
                "precedent_score": round(s.o3_precedent, 3),
                "binding_constraint": s.binding_constraint,
                "nearest_real_adc": nearest,
                "nearest_real_diff": diff,
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
    }
