"""Run the literature extraction over the fetched PMC corpus and report the funnel.

Every stage declines rows, and the declines are the output that matters as much as the
cells: the plan's measured failure mode is a 75% false-positive attribution rate, and the
only way to see that the guards are working rather than merely present is to count what
each one rejected and on what grounds.

The funnel, in the order a table passes through it:

    article                 -> parsed, or malformed
    table                   -> AE-captioned, or not an AE table
    AE table                -> machine-readable, or image-only
    readable AE table       -> attributable, or ambiguous / comparator-only
    attributable table      -> has mapped organ rows, or only aggregates
    mapped row              -> an axis, or a dictionary miss
    cell                    -> arithmetic verified, or flagged

Nothing is dropped silently. A rejected table is recorded with its reason, its journal and
its PMCID, so a yield that comes out too low can be diagnosed as a journal problem, a
dictionary problem or an attribution problem rather than guessed at.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.extract.jats_tables import parse_article  # noqa: E402
from adctox.extract.table_to_cells import extract  # noqa: E402
from adctox.provenance import stamp  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"
PT_DICT = ROOT / "data" / "processed" / "pt_soc_dictionary.json"


def aliases_for(spec: dict) -> set[str]:
    """Names identifying this agent in a column header.

    The same rule the fetcher uses, and for the same reason: `trastuzumab` alone names
    three different ADCs plus the naked antibody, so a bare antibody stem is rejected.
    Here the stakes are higher than in the fetcher -- a stem matching the wrong column
    attributes a rate to the wrong drug, where in the fetcher it only costs a download.
    """
    out = {str(spec["inn"]).lower(), str(spec.get("brand", "")).lower()}
    for a in spec.get("aliases", []):
        a = str(a).lower().strip()
        if not a:
            continue
        if " " not in a and not any(ch.isdigit() or ch == "-" for ch in a) \
                and len(a) > 6 and a.endswith("mab"):
            continue
        out.add(a)
    return {x for x in out if len(x) >= 4}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--cells-out", type=pathlib.Path, default=None)
    args = ap.parse_args()

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]
    alias_map = {k: aliases_for(v) for k, v in registry.items() if v.get("inn")}

    tax = default_taxonomy()
    tax.load_pt_dictionary(PT_DICT)

    manifest = json.loads(
        (args.raw_dir / "_manifest.json").read_text(encoding="utf-8")
    )
    records: dict[str, dict] = manifest["records"]
    paths = sorted((args.raw_dir / "xml").glob("*.xml"))
    if not paths:
        print(f"no xml under {args.raw_dir / 'xml'}", file=sys.stderr)
        return 1

    funnel = collections.Counter()
    reject: dict[str, list[dict]] = collections.defaultdict(list)
    per_agent = collections.defaultdict(collections.Counter)
    axis_cells = collections.Counter()
    row_misses = collections.Counter()
    cells_out: list[dict] = []

    for path in paths:
        pmcid = path.stem.removeprefix("PMC")
        rec = records.get(pmcid, {})
        agent = rec.get("agent_hint")
        if agent not in alias_map:
            funnel["article_unattributed"] += 1
            continue
        try:
            meta, tables = parse_article(path)
        except Exception as exc:
            funnel["article_malformed"] += 1
            reject["article_malformed"].append(
                {"pmcid": pmcid, "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        funnel["articles"] += 1
        per_agent[agent]["articles"] += 1
        others = {k: v for k, v in alias_map.items() if k != agent}

        for ti, table in enumerate(tables):
            funnel["tables"] += 1
            if not table.looks_like_ae_table:
                funnel["not_ae_table"] += 1
                continue
            funnel["ae_tables"] += 1
            per_agent[agent]["ae_tables"] += 1
            out = extract(table, agent, alias_map[agent], others, tax)
            for key, val in out.counters.items():
                funnel[f"row_or_cell:{key}"] += val
            for row in out.rows:
                if row.kind == "pt" and row.axis.startswith("__"):
                    row_misses[row.normalized or row.label] += 1
            if not out.accepted:
                bucket = out.reason.split(":")[0]
                funnel[f"table_rejected:{bucket}"] += 1
                per_agent[agent][f"rejected_{bucket}"] += 1
                reject[bucket].append({
                    "pmcid": pmcid, "agent": agent, "journal": meta["journal"],
                    "table": table.label or f"#{ti}",
                    "caption": table.caption[:160], "reason": out.reason[:240],
                })
                continue
            funnel["tables_accepted"] += 1
            per_agent[agent]["tables_accepted"] += 1
            thr = out.threshold
            for c in out.cells:
                funnel["cells"] += 1
                funnel["cells_arith_ok" if c.arithmetic_ok else "cells_arith_fail"] += 1
                axis_cells[c.axis] += 1
                per_agent[agent]["cells"] += 1
                cells_out.append({
                    "agent": agent, "axis": c.axis, "n": c.n,
                    "denominator": c.denominator, "percentage": c.percentage,
                    "arithmetic_ok": c.arithmetic_ok,
                    "row_label": c.row_label, "normalized_term": c.normalized_term,
                    "row_provenance": c.row_provenance,
                    "column_header": c.column_header, "column_kind": c.column_kind,
                    "threshold_pct": (thr.value if thr else None),
                    "threshold_explicit": (thr.is_explicit if thr else False),
                    "threshold_is_upper_bound": (thr.is_upper_bound if thr else False),
                    "threshold_source": (thr.source if thr else "none"),
                    "pmcid": pmcid, "table_label": table.label or f"#{ti}",
                    "journal": meta["journal"],
                    "license_code": rec.get("license_code"),
                })

    def pct(n: int, d: int) -> str:
        return f"{100.0 * n / d:5.1f}%" if d else "    --"

    agents_recovered = sorted(a for a, c in per_agent.items() if c["cells"] > 0)
    print(f"논문 {funnel['articles']}편 → 표 {funnel['tables']}개 "
          f"→ AE 표 {funnel['ae_tables']}개 → 채택 {funnel['tables_accepted']}개 "
          f"({pct(funnel['tables_accepted'], funnel['ae_tables'])}) "
          f"→ 셀 {funnel['cells']}개")
    print(f"★ 셀을 1개 이상 얻은 약물 {len(agents_recovered)}/{len(alias_map)}")
    print(f"  산술 게이트 {funnel['cells_arith_ok']}/"
          f"{funnel['cells_arith_ok'] + funnel['cells_arith_fail']} "
          f"({pct(funnel['cells_arith_ok'], funnel['cells_arith_ok'] + funnel['cells_arith_fail'])})"
          f"   [계획서 실측 86.8%]")

    print("\nAE 표 거부 사유")
    for key in sorted(k for k in funnel if k.startswith("table_rejected:")):
        print(f"  {key.split(':', 1)[1]:28s} {funnel[key]:5d}  "
              f"{pct(funnel[key], funnel['ae_tables'])}")

    print("\n행 분류")
    for key in sorted(k for k in funnel if k.startswith("row_or_cell:row_")):
        print(f"  {key.rsplit('_', 1)[-1]:28s} {funnel[key]:5d}")

    print(f"\n약물별 (셀 0인 약물에 ✗)")
    print(f"  {'agent':30s} {'논문':>4s} {'AE표':>5s} {'채택':>5s} {'셀':>6s}")
    for a in sorted(alias_map):
        c = per_agent[a]
        mark = " " if c["cells"] else "✗"
        print(f"{mark} {a:30s} {c['articles']:4d} {c['ae_tables']:5d} "
              f"{c['tables_accepted']:5d} {c['cells']:6d}")

    print("\n축별 셀")
    for axis, n in axis_cells.most_common():
        print(f"  {axis:24s} {n:6d}")

    print(f"\n미매핑 행 상위 20 (총 {sum(row_misses.values())}건, "
          f"{len(row_misses)}종)")
    for term, n in row_misses.most_common(20):
        print(f"  {n:4d}  {term[:72]}")

    out = {
        "provenance": stamp({"registry": REGISTRY, "pt_dictionary": PT_DICT}),
        "funnel": dict(funnel),
        "agents_recovered": agents_recovered,
        "agents_sought": sorted(alias_map),
        "per_agent": {a: dict(per_agent[a]) for a in sorted(alias_map)},
        "axis_cells": dict(axis_cells),
        "unmapped_rows": dict(row_misses.most_common(300)),
        "rejected": {k: v[:60] for k, v in reject.items()},
        "rejected_counts": {k: len(v) for k, v in reject.items()},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    if args.cells_out:
        args.cells_out.parent.mkdir(parents=True, exist_ok=True)
        args.cells_out.write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in cells_out) + "\n",
            encoding="utf-8",
        )
        print(f"→ {args.cells_out}  ({len(cells_out)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
