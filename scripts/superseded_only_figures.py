"""Which report figures trace only to a *superseded* artefact?

`check_report.py` scans `artifacts/superseded/` on purpose: the report quotes overturned
numbers in before/after comparisons, and a superseded figure should trace to the record of
its own supersession rather than to an allowlist entry saying a human checked it once.

The cost of that choice is a hole. A figure that goes stale does not stop tracing -- it
traces to the artefact recording what it used to be -- so the number guard reports a clean
run on a document quoting last month's result as this month's.

This partitions the pool and classifies what lands in the gap. Three outcomes:

  paired with a live figure   The line carries another figure that *is* in a current
                              artefact. That is the shape of a before/after row or
                              sentence, and it is the common case: 19 of 23 at the time of
                              writing. A stale figure replacing a live one would take its
                              partner with it, so the pairing is evidence and not an excuse.
  declared                    Both figures on the line are superseded, which happens where
                              the whole comparison is historical -- an experiment variant
                              run on the 16-agent corpus, or the narrative of a false
                              finding. Each one is named below with its reason.
  undeclared                  Neither. Read it.

The classification is a rule rather than a list of 23 strings, because a list that long is
maintained by adding to it, and adding to it is how a stale figure gets silenced.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from check_report import (  # noqa: E402
    INLINE, NUMBER, _normalize_signs, _presentation_variants,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adctox.provenance import write_json  # noqa: E402

SCAN = [ROOT / "artifacts", ROOT / "data" / "processed"]

# Figures the report quotes *because* they were superseded, where no live figure shares the
# line. The reason, not a bare allowlist: a figure that went stale must not be silenceable
# by adding its string here without saying what it is.
DELIBERATE: dict[str, str] = {
    "0.1332": "the 16-agent corpus's across-agent rho, quoted in full in the sentence that "
              "retracts it and in the paragraph on the false finding it produced",
    "0.2118": "the other half of that false finding: the headline the corpus mismatch "
              "produced, quoted only to say it was not real",
    "1.989": "section 4.0b's agent-by-axis experiment, run on the earlier corpus and kept "
             "as a comparison of model structures rather than of corpora",
    "1.064": "the other cell of that same agent-by-axis table -- the thick cell, against "
             "the thin one above it, which is the comparison the experiment was for",
}


def _values_of(paths: list[pathlib.Path]) -> set[str]:
    """Every numeric value in these JSON files, in the guard's own presentation forms."""
    out: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            for places in (2, 3, 4):
                out.add(f"{round(float(node), places):.{places}f}")
                out.add(f"{round(float(node) * 100, places):.{places}f}")

    for path in paths:
        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _partition() -> tuple[set[str], set[str]]:
    """(live values, superseded values), split per file rather than per directory.

    Per file matters: `artifacts/superseded/` is a subdirectory of `artifacts/`, which the
    guard reaches through a `*/*.json` glob, so splitting by directory would drag every
    superseded value into the live pool.
    """
    live_paths, sup_paths = [], []
    for d in SCAN:
        if not d.exists():
            continue
        for path in [*d.glob("*.json"), *d.glob("*/*.json")]:
            (sup_paths if "superseded" in path.parts else live_paths).append(path)
    return _values_of(live_paths), _values_of(sup_paths)


def _figures(doc: pathlib.Path) -> list[tuple[str, int, str]]:
    """(figure, line number, the line) for every decimal figure the guard would see."""
    out = []
    for lineno, line in enumerate(
        _normalize_signs(doc.read_text(encoding="utf-8")).splitlines(), start=1
    ):
        if line.lstrip().startswith("<!--"):
            continue
        clean = INLINE.sub(" ", line)
        for raw in NUMBER.findall(clean):
            out.append((raw, lineno, clean))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=pathlib.Path, nargs="+",
                    default=[ROOT / "report" / "findings.md",
                             ROOT / "docs" / "MODEL_CARD.md"])
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "superseded_only_figures.json")
    args = ap.parse_args()

    live, sup = _partition()
    if not sup:
        print("no superseded artefact in this tree; nothing to partition")
        write_json(args.out, {"figures": [], "n_superseded_only": 0, "n_undeclared": 0}, {})
        return 0

    rows = []
    for doc in args.report:
        if not doc.exists():
            continue
        for raw, lineno, line in _figures(doc):
            variants = _presentation_variants(raw)
            if not (variants & sup) or (variants & live):
                continue
            others = [x for x in NUMBER.findall(line) if x != raw]
            paired = any(_presentation_variants(x) & live for x in others)
            rows.append({
                "figure": raw,
                "document": doc.name,
                "line": lineno,
                "classification": (
                    "paired with a live figure" if paired
                    else "declared" if raw in DELIBERATE
                    else "undeclared"
                ),
                "reason": None if paired else DELIBERATE.get(raw),
            })

    undeclared = [r for r in rows if r["classification"] == "undeclared"]
    out = {
        "n_live_values": len(live),
        "n_superseded_values": len(sup),
        "figures": rows,
        "n_superseded_only": len(rows),
        "n_paired": sum(1 for r in rows if r["classification"].startswith("paired")),
        "n_declared": sum(1 for r in rows if r["classification"] == "declared"),
        "n_undeclared": len(undeclared),
        "reading": (
            "A figure here appears in a superseded artefact and in no current one, so the "
            "number guard reports it as traced. That is either a deliberate before/after "
            "quotation or a figure that went stale and kept its trace, and the guard "
            "cannot tell the difference because both do trace."
        ),
    }
    write_json(args.out, out, {})
    print(f"{len(rows)} figures trace only to a superseded artefact: "
          f"{out['n_paired']} paired with a live figure on the same line, "
          f"{out['n_declared']} declared, {out['n_undeclared']} undeclared")
    for r in undeclared:
        print(f"  UNDECLARED  {r['document']}:{r['line']}  {r['figure']}")
    print(f"-> {args.out}")
    return 1 if undeclared else 0


if __name__ == "__main__":
    raise SystemExit(main())
