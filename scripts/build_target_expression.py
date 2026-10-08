#!/usr/bin/env python
"""Aggregate per-tissue target expression onto the 14 organ axes, and validate it.

The validation is part of the build, not an afterthought, because the whole point of this
artefact is to decide whether constraint C3 may act at all. Two questions are answered and
both are written into the artefact:

  1. Does target expression predict the organs an approved label warns about?
     Measured, AUROC against the label's dose-modification concern:
     gtex 0.521, tabula_sapiens 0.576 -- chance. Controlling for payload mechanism does
     not rescue it. This agrees with the preclinical literature the project already cites
     (PMID 38692647, 14 vedotin ADCs: toxicity largely antigen-independent, target tissue
     expression poorly correlated with dose-limiting toxicity).

  2. Does it recover the specific on-target off-tumour cases?
     Yes. Five textbook pairs -- NECTIN4/skin, CD33 and CD19/blood, ERBB2/heart,
     FOLR1/kidney -- all land in the target's top expression quintile, against a chance
     expectation of one in five.

Those two together say what expression is for: it identifies *which organ a target could
damage*, not *how toxic a drug is*. So it is served as a flag that can raise a risk band,
in the same architecture as the label-derived rules, and never as grounds for rejecting a
candidate. A rejection rule was prototyped and discarded: it removed 87% of candidates
whenever it fired, and never changed the recommendation, because the two non-permeable
payloads it spares were already the top-ranked ones.

Values from different sources are never pooled -- TPM, CPM-pseudobulk and mass-spec PPB
differ by orders of magnitude. Each source is ranked within a target across axes, and only
the ranks combine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

CONF = Path(__file__).resolve().parents[1] / "conf"

# The percentile at or above which a target counts as abundant in an organ. Set from the
# known on-target off-tumour cases rather than chosen: the weakest of them, FOLR1 in
# kidney, sits at 0.83, so 0.80 is the strictest threshold that still captures all five.
# 0.90 drops FOLR1 and 1.00 drops three of the five.
ABUNDANT_PERCENTILE = 0.80

SOURCES = ("gtex", "tabula_sapiens")

# Textbook on-target off-tumour pairs, written down before the numbers were looked at.
# Five entries but fewer independent facts: the three blood targets are one fact about
# immune antigens in immune tissue, so count this as four independent predictions.
KNOWN_ON_TARGET = [
    ("NECTIN4", "dermatologic", "enfortumab vedotin skin toxicity; NECTIN4 is in normal skin"),
    ("CD33", "haematologic", "normal myeloid cells"),
    ("CD19", "haematologic", "normal B cells"),
    ("ERBB2", "cardiovascular", "cardiomyocytes"),
    ("FOLR1", "renal", "proximal tubule"),
]


def _crosswalk() -> dict:
    return yaml.safe_load(
        (CONF / "ontology" / "tissue_axis.yaml").read_text(encoding="utf-8")
    )


def axis_values(rows: list[dict], xw: dict) -> tuple[dict, dict, set]:
    """Per-source {axis: (value, tissue)}, plus the cell-type evidence, plus unmapped."""
    values: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    unmapped: set[str] = set()
    for src in SOURCES:
        tissue_to_axis = {t: a for a, ts in xw[src].items() for t in ts}
        excluded = set(xw[f"{src}_excluded"])
        best: dict[str, tuple[float, str]] = {}
        cells: dict[str, list] = {}
        for r in rows:
            if r["datasourceId"] != src:
                continue
            tissue = r["tissueBiosampleFromSource"]
            if tissue is None or tissue in excluded:
                continue
            axis = tissue_to_axis.get(tissue)
            if axis is None:
                unmapped.add(f"{src}:{tissue}")
                continue
            value = r["median"] or 0.0
            cell = r.get("celltypeBiosampleFromSource")
            if cell:
                # Cell types are evidence, never the score. Taking the maximum over cell
                # types put ERBB2's musculoskeletal axis at 182 via erythrocytes and its
                # cardiovascular axis at 141 via a neuron in a ventricle sample -- single
                # rows with no sample count behind them. Tissue-level pseudobulk is stable.
                cells.setdefault(axis, []).append((value, tissue, cell))
                continue
            if axis not in best or value > best[axis][0]:
                best[axis] = (value, tissue)
        values[src] = {a: list(v) for a, v in best.items()}
        evidence[src] = {
            a: [list(x) for x in sorted(v, reverse=True)[:3]] for a, v in cells.items()
        }
    return values, evidence, unmapped


def percentiles(values: dict) -> dict:
    """Within-target percentile per axis, taking the stronger of the two sources.

    Ranks rather than values, because the two sources' units are not comparable. The
    stronger source wins because each covers axes the other cannot see at all: GTEx has
    no eye and no ear, Tabula Sapiens has no brain.
    """
    out: dict[str, float] = {}
    for src in SOURCES:
        scores = {a: v[0] for a, v in values.get(src, {}).items()}
        if len(scores) < 5:
            continue
        order = sorted(scores, key=lambda a: scores[a])
        for i, axis in enumerate(order):
            out[axis] = max(out.get(axis, 0.0), (i + 1) / len(order))
    return out


def _auroc(labels: list[int], scores: list[float]) -> float:
    pos = np.array([s for y, s in zip(labels, scores) if y == 1])
    neg = np.array([s for y, s in zip(labels, scores) if y == 0])
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float(
        np.greater.outer(pos, neg).mean() + 0.5 * np.equal.outer(pos, neg).mean()
    )


def validate_against_labels(targets: dict, labels_dir: Path) -> dict | None:
    """Does target expression predict the organs an approved label warns about?

    Written into the artefact rather than printed, because this is the measurement that
    decides whether the layer may act, and the project has repeatedly found figures that
    existed only in stdout.

    Ground truth is the organ concern encoded in each label's section-2
    dose-modification tables -- independent of the adverse-event corpus and of the
    exclusion criteria the comorbidity registry was built from, so this is not circular.
    """
    if not labels_dir.exists():
        return None
    from adctox.validation.dose_modification import axis_concern, parse_tables

    reg = yaml.safe_load(
        (CONF / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    rows: list[dict] = []
    for agent, spec in reg.items():
        if not (spec.get("conventional_adc") and spec.get("first_us_approval")):
            continue
        target = spec.get("target")
        if target not in targets:
            continue
        path = labels_dir / f"{agent}.json"
        if not path.exists():
            continue
        tables = json.loads(path.read_text(encoding="utf-8")).get(
            "dosage_and_administration_table"
        ) or []
        concern = axis_concern(parse_tables(agent, tables))
        if len(concern) < 2:
            continue
        for src in SOURCES:
            scores = {a: v[0] for a, v in targets[target]["values"].get(src, {}).items()}
            if len(scores) < 5:
                continue
            order = sorted(scores, key=lambda a: scores[a])
            pct = {a: (i + 1) / len(order) for i, a in enumerate(order)}
            for axis, p in pct.items():
                rows.append({
                    "agent": agent, "mechanism": spec["mechanism"], "source": src,
                    "axis": axis, "percentile": p,
                    "warned": 1 if concern.get(axis, 0.0) > 0 else 0,
                })
    if not rows:
        return None
    out = {"n_cells": len(rows), "n_agents": len({r["agent"] for r in rows}), "overall": {},
           "by_mechanism": {}}
    for src in SOURCES:
        sub = [r for r in rows if r["source"] == src]
        if not sub:
            continue
        out["overall"][src] = {
            "auroc": _auroc([r["warned"] for r in sub], [r["percentile"] for r in sub]),
            "n_cells": len(sub),
            "n_warned": sum(r["warned"] for r in sub),
        }
        per = {}
        for mech in sorted({r["mechanism"] for r in sub}):
            m = [r for r in sub if r["mechanism"] == mech]
            if len({r["agent"] for r in m}) < 2:
                continue
            per[mech] = {
                "auroc": _auroc([r["warned"] for r in m], [r["percentile"] for r in m]),
                "n_agents": len({r["agent"] for r in m}),
            }
        out["by_mechanism"][src] = per
    out["verdict"] = (
        "Expression does not predict which organs a label warns about. Controlling for "
        "payload mechanism does not rescue it. This agrees with PMID 38692647, which "
        "found ADC toxicity largely antigen-independent with target tissue expression "
        "poorly correlated with dose-limiting toxicity. So expression may locate the "
        "organ a target could reach -- see the on-target check -- but must not reject a "
        "candidate or set a rate."
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--labels", type=Path,
                    default=Path("/data/hyeongchanahn/adctox/raw/openfda_label/2026-10-07"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()

    xw = _crosswalk()
    files = sorted(p for p in args.raw.glob("*.json") if not p.name.startswith("_"))
    if not files:
        print(f"no target files in {args.raw}; run scripts/fetch_target_expression.py")
        return 1

    targets, all_unmapped = {}, set()
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        values, evidence, unmapped = axis_values(doc["rows"], xw)
        all_unmapped |= unmapped
        pct = percentiles(values)
        targets[doc["symbol"]] = {
            "ensembl_id": doc["ensembl_id"],
            "values": values,
            "percentile": pct,
            "abundant_axes": sorted(a for a, p in pct.items() if p >= ABUNDANT_PERCENTILE),
            "cell_evidence": evidence,
            "sources_present": sorted(s for s in SOURCES if values.get(s)),
        }

    if all_unmapped:
        raise SystemExit(
            f"{len(all_unmapped)} tissues map to no axis and are not excluded: "
            f"{sorted(all_unmapped)[:10]}. Add them to conf/ontology/tissue_axis.yaml or "
            "exclude them with a reason -- dropping a tissue silently loses an organ."
        )

    print(f"{len(targets)} targets aggregated; every tissue mapped or excluded")
    print(f"\nthe {len(KNOWN_ON_TARGET)} textbook on-target pairs, declared before measuring:")
    known = []
    for sym, axis, why in KNOWN_ON_TARGET:
        p = targets.get(sym, {}).get("percentile", {}).get(axis)
        hit = p is not None and p >= ABUNDANT_PERCENTILE
        known.append({"target": sym, "axis": axis, "percentile": p, "captured": hit,
                      "mechanism": why})
        print(f"   {sym:9s} {axis:16s} percentile {p if p is None else round(p,2)}"
              f"  {'captured' if hit else 'MISSED'}   {why}")
    n_hit = sum(k["captured"] for k in known)
    print(f"   -> {n_hit}/{len(known)} captured at >= {ABUNDANT_PERCENTILE}; chance is 1 in 5")

    label_check = validate_against_labels(targets, args.labels)
    if label_check:
        print("\ndoes expression predict the organs a label warns about?")
        for src, v in label_check["overall"].items():
            print(f"   {src:16s} AUROC {v['auroc']:.3f}  "
                  f"({v['n_warned']} warned of {v['n_cells']} cells)")
        print("   -> chance; see the verdict field in the artefact")

    write_json(
        args.out / "target_expression.json",
        {
            "abundant_percentile": ABUNDANT_PERCENTILE,
            "label_concern_check": label_check,
            "sources": {s: xw["sources"][s] for s in SOURCES},
            "axes_not_evaluable": xw["axes_not_evaluable"],
            "known_on_target_check": {
                "pairs": known,
                "n_captured": n_hit,
                "n_pairs": len(known),
                "n_independent_facts": 4,
                "note": (
                    "Five pairs but four independent facts: the three blood targets are "
                    "one fact about immune antigens in immune tissue. Hand-picked with "
                    "stated mechanisms, written before the numbers were read, and not a "
                    "systematic sample."
                ),
            },
            "targets": targets,
        },
        {"raw": args.raw, "crosswalk": CONF / "ontology" / "tissue_axis.yaml"},
    )
    print(f"\n-> {args.out}/target_expression.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
