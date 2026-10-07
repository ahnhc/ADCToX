#!/usr/bin/env python
"""Fail if the report quotes a number that no artefact supports.

Why this guard exists: a four-week report whose numbers were typed by hand drifts from the
code the moment a model is refit, and the drift is invisible -- the prose still reads
plausibly. This project has already had one evaluation round invalidated by a bug, so
every figure in the report must be traceable to a JSON artefact or it is a liability.

The check is deliberately crude and loud rather than clever: it extracts every decimal
number from the report, looks for it among the values in `artifacts/*.json`, and reports
the ones it cannot find. False positives are expected -- a year, a count stated in prose,
a number from the literature -- so an allowlist file carries the ones a human has
checked, with a reason. An unexplained number is the failure.

It also measures and prints its own power, because it had none and said nothing. A
"tolerate presentation differences" clause used to retry each figure rounded down to two
and three decimals (`f"{float(raw):.2f}"`). Against a pool of ~8,400 artefact values
rounded to 2, 3 and 4 places, nearly every two-decimal string in [0,1) is present, so the
retry matched almost anything: measured, the check passed **99.1%** of randomly fabricated
four-decimal numbers. The guard underpinning "no figure in this report was typed by hand"
was a no-op, and every previous clean run of it meant nothing.

Dropping the downgrade takes the false-pass rate on fabricated four-decimal figures to
about 16%. Three-decimal figures stay weak (~64%) because the value pool is dense at that
precision -- a membership test cannot fix that, so the residual rate is printed on every
run rather than left implicit. Quote a figure to four decimals where traceability is the
point.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Decimals with at least two places: the shape of a measured quantity rather than a count.
NUMBER = re.compile(r"(?<![\w.])(-?\d+\.\d{2,})(?![\w.])")
# Skip fenced code and inline code, which quote commands rather than results.
FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`]*`")


def artefact_values(dirs: list[Path]) -> set[str]:
    """Every numeric value anywhere in the artefact JSONs, as rounded strings."""
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

    for d in dirs:
        for path in sorted(d.glob("*.json")):
            try:
                walk(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def _presentation_variants(raw: str) -> set[str]:
    """The same number written differently -- NOT the same number written less precisely."""
    return {raw, raw.lstrip("+-"), raw.lstrip("-"), raw.rstrip("0").rstrip(".")}


def measured_false_pass_rate(
    values: set[str], allow: dict[str, str], places: int, n: int = 4000
) -> float:
    """How often a fabricated figure of this precision slips through.

    Printed on every run. A guard that cannot state its own power invites exactly the
    false confidence this project has already been bitten by twice.
    """
    import random

    rng = random.Random(20261007)
    pool = values | set(allow)
    hits = 0
    for _ in range(n):
        raw = f"{rng.random():.{places}f}"
        if _presentation_variants(raw) & pool:
            hits += 1
    return hits / n


def load_allowlist(path: Path) -> dict[str, str]:
    """number -> reason it is allowed to appear without an artefact behind it."""
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in doc.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path, nargs="?", default=Path("report"))
    # The report draws on both locations: fitted metrics live in artifacts/ and corpus
    # statistics in data/processed/. Scanning only one leaves real figures unexplained.
    ap.add_argument("--artifacts", type=Path, nargs="+",
                    default=[Path("artifacts"), Path("data/processed")])
    ap.add_argument("--allowlist", type=Path,
                    default=Path("report/number_allowlist.json"))
    args = ap.parse_args()

    values = artefact_values(args.artifacts)
    allow = load_allowlist(args.allowlist)
    n_files = sum(len(list(d.glob("*.json"))) for d in args.artifacts)
    print(f"{len(values):,} numeric values across {n_files} artefacts in "
          f"{', '.join(str(d) for d in args.artifacts)}; {len(allow)} allowlisted")
    rates = {d: measured_false_pass_rate(values, allow, d) for d in (2, 3, 4)}
    print(
        "  measured false-pass rate on fabricated figures: "
        + ", ".join(f"{d}dp {100 * r:.0f}%" for d, r in rates.items())
        + "  <- a clean run means less at low precision"
    )

    unexplained: list[tuple[str, int, str]] = []
    checked = 0
    for doc in sorted(args.report.rglob("*.md")):
        text = FENCE.sub(" ", doc.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), 1):
            line = INLINE.sub(" ", line)
            for m in NUMBER.finditer(line):
                raw = m.group(1)
                checked += 1
                if raw.lstrip("-") in values or raw in values or raw in allow:
                    continue
                # Tolerate a sign or trailing-zero difference in presentation, and
                # nothing else. Retrying at lower precision is what made this check
                # vacuous: it turns "does this exact figure exist" into "does something
                # roughly like it exist", and in a pool this dense the answer is always
                # yes.
                if _presentation_variants(raw) & (values | set(allow)):
                    continue
                unexplained.append((doc.name, lineno, raw))

    print(f"{checked} decimal figures checked across the report")
    if not unexplained:
        print("every figure traces to an artefact or the allowlist")
        return 0

    print(f"\n{len(unexplained)} figures with no artefact behind them:")
    for name, lineno, raw in unexplained[:40]:
        print(f"  {name}:{lineno}  {raw}")
    if len(unexplained) > 40:
        print(f"  ... and {len(unexplained) - 40} more")
    print(
        "\nEach one is either a number that should come from an artefact -- generate it and "
        "reference it -- or a legitimate constant, in which case add it to "
        f"{args.allowlist} with the reason it is there."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
