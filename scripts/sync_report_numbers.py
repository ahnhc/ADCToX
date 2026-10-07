#!/usr/bin/env python
"""Regenerate the report's fitted-parameter block from the metrics artefact.

Why this exists: the report quoted `tau_mech` 0.592 [0.503, 0.711] in "What the model does
support" while the artefact said 0.5816 [0.4926, 0.6863], and quoted the same 0.592
elsewhere as a *pre-fix* value -- so the report contradicted itself about one number. Three
parameters were stale the same way. The guard that should have caught it, check_report.py,
was passing 99% of fabricated figures.

Typing these by hand loses every time a model is refit, and refits are frequent here. So
the numbers come from the artefact and the prose stays in this file, next to the parameter
it interprets. Run it after `make forward`; `make check-report` depends on it.

The interpretations are deliberately kept here rather than in the markdown: an
interpretation that outlives its number is the same bug in prose form, and keeping them
together means a sign flip forces the sentence to be rewritten.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BEGIN = "<!-- generated: fitted-parameters -->"
END = "<!-- /generated: fitted-parameters -->"

# parameter -> (source, sentence). `{v}` is substituted with "mean [q05, q95]".
NOTES: dict[str, tuple[str, str]] = {
    "tau_mech": (
        "tau_mech",
        "the mechanism x axis interaction is supported by the data rather than asserted "
        "by a parameter count.",
    ),
    "sigma_agent": (
        "coefficients",
        "small, so the design slots account for much of the between-agent variation.",
    ),
    "b_combo": ("coefficients", "combination arms do report higher rates."),
    "b_log_n": (
        "coefficients",
        "an ascertainment effect that would have been attributed to the design had it not "
        "been controlled.",
    ),
    "b_dar": (
        "coefficients",
        "includes zero. DAR is an agent-level constant and is confounded with agent "
        "identity here. The pharmacokinetic literature supports a DAR effect; this corpus "
        "does not resolve one.",
    ),
    "b_thresh": (
        "coefficients",
        "the reporting-threshold covariate. Not the censoring correction: it is four times "
        "larger on the seriousEvents table, which has no censored cells at all, so it is "
        "substantially absorbing trial-level reporting practice.",
    ),
}


def _fmt(cell: dict, signed: bool) -> str:
    """Four decimals, so check_report.py has power on these figures.

    `signed` is False for scale parameters: tau and sigma are positive by construction, so
    a leading "+" on them implies a sign that could have gone the other way.
    """
    if not signed:
        return f"{cell['mean']:.4f} [{cell['q05']:.4f}, {cell['q95']:.4f}]"
    return f"{cell['mean']:+.4f} [{cell['q05']:+.4f}, {cell['q95']:+.4f}]"


def build_block(metrics: dict) -> str:
    lines = [BEGIN]
    for name, (where, note) in NOTES.items():
        cell = metrics.get(name) if where == "tau_mech" else (
            metrics.get("coefficients", {}).get(name)
        )
        if not cell or "mean" not in cell:
            continue
        signed = name.startswith("b_")
        lines.append(f"`{name}` {_fmt(cell, signed)} -- {note}")
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines.append(END)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path,
                    default=Path("artifacts/forward_other_metrics.json"))
    # Both documents quoted the same parameters and both were stale. The model card was
    # worse off: check_report.py only scanned report/, so its figures were never checked
    # at all.
    ap.add_argument("--report", type=Path, nargs="+",
                    default=[Path("report/findings.md"), Path("docs/MODEL_CARD.md")])
    ap.add_argument("--check", action="store_true",
                    help="fail if the block is out of date instead of rewriting it")
    args = ap.parse_args()

    if not args.metrics.exists():
        print(f"{args.metrics} absent; run `make forward` first")
        return 1
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    block = build_block(metrics)

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    rc = 0
    for doc in args.report:
        text = doc.read_text(encoding="utf-8")
        if not pattern.search(text):
            print(
                f"{doc} has no generated block. Insert these two markers around the "
                f"fitted-parameter list:\n  {BEGIN}\n  {END}"
            )
            rc = 1
            continue
        updated = pattern.sub(lambda _: block, text)
        if updated == text:
            print(f"{doc}: fitted-parameter block already current")
            continue
        if args.check:
            print(
                f"{doc}: fitted-parameter block is STALE against {args.metrics}. "
                "Run `python scripts/sync_report_numbers.py` to regenerate it."
            )
            rc = 1
            continue
        doc.write_text(updated, encoding="utf-8")
        print(f"{doc}: fitted-parameter block regenerated from {args.metrics}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
