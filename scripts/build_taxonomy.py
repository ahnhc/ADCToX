#!/usr/bin/env python
"""Build the PT -> SOC dictionary and report axis-mapping coverage.

This is the Week-1 Day-1 deliverable and the Gate 1a check: at least 85% of AE *mass*
(sum of numAffected, not row count) must land on a real organ axis rather than on a
sentinel. Row-count coverage is reported too, but mass is what the model is fit on.

Usage:
    python scripts/build_taxonomy.py --studies <dir> --out data/processed
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.taxonomy import (  # noqa: E402
    AXIS_DROPPED,
    AXIS_EXCLUDED,
    AXIS_UNMAPPED,
    Taxonomy,
    build_pt_dictionary,
    parse_frequency_threshold,
)

SENTINELS = (AXIS_UNMAPPED, AXIS_EXCLUDED, AXIS_DROPPED)


def iter_ae_records(studies_dir: Path):
    """Yield one record per (event, SOC) from every study's adverseEventsModule."""
    for path in sorted(studies_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! skipping {path.name}: {exc}", file=sys.stderr)
            continue
        ae = (doc.get("resultsSection") or {}).get("adverseEventsModule") or {}
        if not ae:
            continue
        nct = ((doc.get("protocolSection") or {}).get("identificationModule") or {}).get(
            "nctId", path.stem
        )
        threshold = parse_frequency_threshold(ae.get("frequencyThreshold"))
        for kind in ("otherEvents", "seriousEvents"):
            for event in ae.get(kind) or []:
                affected = sum(
                    (s.get("numAffected") or 0) for s in (event.get("stats") or [])
                )
                yield {
                    "nct_id": nct,
                    "kind": "serious" if kind == "seriousEvents" else "other",
                    "term": event.get("term"),
                    "raw_soc": event.get("organSystem"),
                    "vocabulary": event.get("sourceVocabulary"),
                    "assessment": event.get("assessmentType"),
                    "threshold": threshold,
                    "n_stats": len(event.get("stats") or []),
                    "affected": affected,
                }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/processed"))
    ap.add_argument("--gate", type=float, default=85.0, help="minimum %% AE mass mapped")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    tax = Taxonomy()

    print(f"Reading studies from {args.studies} ...")
    records = list(iter_ae_records(args.studies))
    print(f"  {len(records):,} AE event rows from {len({r['nct_id'] for r in records}):,} studies")

    # --- PT -> SOC dictionary -------------------------------------------------
    doc = build_pt_dictionary((r["term"], r["raw_soc"]) for r in records)
    dict_path = args.out / "pt_soc_dictionary.json"
    dict_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    st = doc["stats"]
    print(f"\nPT -> SOC dictionary -> {dict_path}")
    print(f"  distinct terms   : {st['distinct_terms']:,}")
    print(f"  retained         : {st['retained_terms']:,}")
    print(
        f"  multi-SOC        : {st['multi_soc_terms']:,} "
        f"({100 * st['multi_soc_terms'] / max(st['distinct_terms'], 1):.1f}%)"
    )
    print(
        f"  contested (<90%) : {st['contested_terms']:,} "
        f"({100 * st['contested_terms'] / max(st['distinct_terms'], 1):.1f}%)"
    )
    tax.load_pt_dictionary(dict_path)

    # --- SOC inventory --------------------------------------------------------
    raw_socs = {r["raw_soc"] for r in records if r["raw_soc"]}
    canon = {tax.canonical_soc(s) for s in raw_socs}
    unknown = sorted(canon - tax.canonical_socs)
    print(f"\nSOC inventory")
    print(f"  raw exact strings: {len(raw_socs)}")
    print(f"  canonical SOCs   : {len(canon)}")
    print(f"  unknown to config: {len(unknown)}")
    for soc in unknown:
        print(f"    ! {soc!r}")

    # --- axis resolution + coverage -------------------------------------------
    by_axis_rows: Counter[str] = Counter()
    by_axis_mass: Counter[str] = Counter()
    unmapped_terms: Counter[str] = Counter()
    inv_unmapped: Counter[str] = Counter()
    provenance: Counter[str] = Counter()

    for r in records:
        axis, prov = tax.resolve(r["term"], r["raw_soc"])
        by_axis_rows[axis] += 1
        by_axis_mass[axis] += r["affected"]
        provenance[prov.split(":")[0]] += 1
        if axis == AXIS_UNMAPPED:
            unmapped_terms[f"{r['raw_soc']} || {r['term']}"] += r["affected"]
            if tax.canonical_soc(r["raw_soc"]) == "investigations":
                inv_unmapped[str(r["term"])] += r["affected"]

    total_mass = sum(by_axis_mass.values())
    total_rows = sum(by_axis_rows.values())
    mapped_mass = sum(v for k, v in by_axis_mass.items() if k not in SENTINELS)
    mapped_rows = sum(v for k, v in by_axis_rows.items() if k not in SENTINELS)
    # Excluded SOCs are a deliberate design choice, so report coverage both ways.
    eligible_mass = total_mass - by_axis_mass[AXIS_EXCLUDED] - by_axis_mass[AXIS_DROPPED]

    print(f"\nAxis coverage  (mass = sum of numAffected)")
    print(f"  {'axis':22s} {'rows':>8s} {'mass':>12s}  {'% mass':>7s}")
    for axis in tax.axis_order:
        print(
            f"  {axis:22s} {by_axis_rows[axis]:8,d} {by_axis_mass[axis]:12,d}"
            f"  {100 * by_axis_mass[axis] / max(total_mass, 1):6.2f}%"
        )
    for s in SENTINELS:
        print(
            f"  {s:22s} {by_axis_rows[s]:8,d} {by_axis_mass[s]:12,d}"
            f"  {100 * by_axis_mass[s] / max(total_mass, 1):6.2f}%"
        )

    pct_all = 100 * mapped_mass / max(total_mass, 1)
    pct_eligible = 100 * mapped_mass / max(eligible_mass, 1)
    print(f"\n  mapped mass / all mass      : {pct_all:.2f}%")
    print(f"  mapped mass / eligible mass : {pct_eligible:.2f}%  (excludes by-design drops)")
    print(f"  mapped rows / all rows      : {100 * mapped_rows / max(total_rows, 1):.2f}%")

    print(f"\nResolution routes")
    for route, n in provenance.most_common():
        print(f"  {n:8,d}  {route}")

    if inv_unmapped:
        print(f"\nTop unmapped Investigations terms ({len(inv_unmapped)} distinct)")
        for term, mass in inv_unmapped.most_common(15):
            print(f"  {mass:7,d}  {term}")

    if unmapped_terms:
        print(f"\nTop unmapped overall ({len(unmapped_terms)} distinct)")
        for key, mass in unmapped_terms.most_common(10):
            print(f"  {mass:7,d}  {key}")

    report = {
        "n_event_rows": len(records),
        "n_studies": len({r["nct_id"] for r in records}),
        "raw_soc_strings": len(raw_socs),
        "canonical_socs": len(canon),
        "unknown_socs": unknown,
        "dictionary": st,
        "mass_by_axis": dict(by_axis_mass),
        "rows_by_axis": dict(by_axis_rows),
        "pct_mass_mapped_all": round(pct_all, 3),
        "pct_mass_mapped_eligible": round(pct_eligible, 3),
        "gate": args.gate,
        "gate_pass": pct_eligible >= args.gate,
    }
    report_path = args.out / "taxonomy_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nreport -> {report_path}")

    if pct_eligible >= args.gate:
        print(f"\nGATE 1a PASS: {pct_eligible:.2f}% >= {args.gate}%")
        return 0
    print(f"\nGATE 1a FAIL: {pct_eligible:.2f}% < {args.gate}%", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
