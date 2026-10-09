"""How often does a grade restriction in a *row* label decide an axis?

The outcome filter works on column headers, which is where the grade usually sits. It can
also sit in the row: "CRS, grade >=3", "Keratopathy, grade 3-4", "Febrile neutropenia,
grade >= 3". 14 cells carry one.

The merge takes the maximum count across an axis's rows -- matching the registry, which
stores an axis as "any event in this organ" -- so a grade-restricted row is harmlessly
dominated whenever the same axis has an any-grade row with a larger count, which is the
normal case. The exposure is the remainder: an (arm, axis) observation whose maximum is
attained *only* by a grade-restricted row.

Measured rather than filtered. It is 6 of 2,696 observations, and a row-level filter would
cost more than it fixes: dropping "Keratopathy, grade 2" where it is the only keratopathy
row would discard a real signal to avoid a 2x understatement in four observations of an
agent that has 124 on that axis.

The test built on this holds the share under 1%, so a corpus change that makes it worse
fails rather than passing quietly.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]

GRADE = re.compile(
    r"grades?\s*[>=≥≤<]*\s*(?:[1-5](?![0-9])|I{1,3}V?\b)", re.I
)
ANY_GRADE = re.compile(r"any[-\s]*grade|all[-\s]*grade|overall", re.I)


def grade_restricted(label: str) -> bool:
    text = str(label or "")
    return bool(GRADE.search(text)) and not ANY_GRADE.search(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cells", type=pathlib.Path,
        default=pathlib.Path("/data/hyeongchanahn/adctox/processed/all_cells.jsonl"),
    )
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "row_grade_exposure.json")
    args = ap.parse_args()

    rows = [
        json.loads(line) for line in args.cells.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # The merge's own grouping: one observation per (arm, axis), the arm keyed by article,
    # table and the first 40 characters of its column header.
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for d in rows:
        groups[(
            d["pmcid"], d["table_label"], (d["column_header"] or "")[:40],
            d["agent"], d["axis"],
        )].append(d)

    affected = []
    for key, cells in groups.items():
        top = max(c["n"] for c in cells)
        winners = [c for c in cells if c["n"] == top]
        if all(grade_restricted(c["row_label"]) for c in winners):
            siblings = sum(c["n"] for c in cells)
            affected.append({
                "agent": key[3], "axis": key[4], "pmcid": key[0],
                "table": key[1], "max": top, "sum_of_rows": siblings,
                "rows": len(cells),
                "deciding_row": winners[0]["row_label"],
            })

    n_grade_cells = sum(1 for d in rows if grade_restricted(d["row_label"]))
    by_agent = collections.Counter(a["agent"] for a in affected)
    summary = {
        "observations": len(groups),
        "cells_with_a_grade_in_the_row_label": n_grade_cells,
        "observations_decided_by_one": len(affected),
        "share": len(affected) / len(groups) if groups else None,
        "bound_the_test_holds": 0.01,
        "by_agent": dict(by_agent),
    }

    print(f"  {'agent':24s} {'axis':16s} {'max':>5s} {'sum':>5s}  deciding row")
    for a in affected:
        print(f"  {a['agent']:24s} {a['axis']:16s} {a['max']:5d} "
              f"{a['sum_of_rows']:5d}  {a['deciding_row'][:46]}")
    print()
    for k, v in summary.items():
        print(f"  {k:36s} {v}")
    write_json(args.out, {"summary": summary, "affected": affected})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
