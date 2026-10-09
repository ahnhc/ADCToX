"""Concatenate the per-snapshot cell files, dropping the articles two snapshots share.

The three PMC snapshots were fetched with three different agent lists -- the registry's
INNs, the payload-linker stem sweep, and the code names an INN search missed -- and 25 of
the 1,471 articles answer to more than one list. A plain `cat` therefore emitted their cells
twice: 277 of 6,535, or 4.2%.

The corpus itself was never affected, because `merge_literature_corpus.py` keys observations
by (arm, axis, kind) and a duplicate collapses. What was affected is every statistic
computed per cell: `pmc_validation.json` reported 6,535 paper cells and sized its rate
comparison at 1,372, both inflated by copies of the same row, and a duplicated cell agrees
with itself so the inflation does not show up as disagreement.

The count of dropped rows is printed and written, rather than the duplicates being removed
quietly. A snapshot overlap growing is a signal about the fetch lists, and a silent
deduplication would hide it.
"""

from __future__ import annotations

import argparse
import json
import pathlib

# What makes two rows the same observation. Not the whole record: `is_chosen_source` and
# the provenance strings can differ between snapshots for the same printed cell, and the
# printed cell is the thing there is only one of.
KEY = (
    "pmcid", "table_label", "row_label", "column_header", "agent", "axis",
    "n", "denominator",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", type=pathlib.Path, nargs="+")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    seen: set[tuple] = set()
    kept: list[str] = []
    dropped = 0
    per_file: list[dict] = []
    for path in args.inputs:
        if not path.exists():
            continue
        n_in = n_drop = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n_in += 1
            row = json.loads(line)
            key = tuple(row.get(k) for k in KEY)
            if key in seen:
                n_drop += 1
                dropped += 1
                continue
            seen.add(key)
            kept.append(line)
        per_file.append({"file": path.name, "rows": n_in, "dropped": n_drop})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(kept) + "\n", encoding="utf-8")

    for row in per_file:
        print(f"  {row['file']:28s} {row['rows']:6d} rows, {row['dropped']:5d} already seen")
    print(f"  {'total':28s} {len(kept):6d} kept, {dropped:5d} dropped as duplicates")


if __name__ == "__main__":
    main()
