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

# The censoring sensitivity table moves with Monte Carlo noise on every rerun -- three of
# its six figures were stale after one -- so it is generated too.
CENS_BEGIN = "<!-- generated: censoring-sensitivity -->"
CENS_END = "<!-- /generated: censoring-sensitivity -->"
CENS_ROWS = [
    ("censored", "censored"),
    ("zero_imputed", "zero-imputed"),
    ("threshold_0_only", "completely-reported subset only"),
]

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


def build_censoring_block(doc: dict) -> str | None:
    """The b_thresh sensitivity table, from artifacts/censoring_sensitivity.json."""
    if not all(k in doc for k in (k for k, _ in CENS_ROWS)):
        return None
    lines = [CENS_BEGIN, "", "| treatment | `b_thresh` |", "|---|---|"]
    for key, label in CENS_ROWS:
        cell = doc[key].get("b_thresh")
        if not cell:
            return None
        lines.append(
            f"| {label} | {cell['mean']:+.4f} "
            f"[{cell['q05']:+.4f}, {cell['q95']:+.4f}] |"
        )
    sub = doc["threshold_0_only"].get("b_thresh", {})
    pa = doc.get("profile_agreement", {})
    n_arms = pa.get("n_arms_in_complete_subset")
    lines += [
        "",
        f"The completely-reported subset is only {n_arms} arms, so its own interval for "
        f"this coefficient spans [{sub.get('q05', float('nan')):+.4f}, "
        f"{sub.get('q95', float('nan')):+.4f}] -- which is why agreement between the "
        "corpora is assessed on the mechanism profiles rather than on coefficients.",
        CENS_END,
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path,
                    default=Path("artifacts/forward_other_metrics.json"))
    ap.add_argument("--censoring", type=Path,
                    default=Path("artifacts/censoring_sensitivity.json"))
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

    cens_block = None
    if args.censoring.exists():
        cens_block = build_censoring_block(
            json.loads(args.censoring.read_text(encoding="utf-8"))
        )

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    cens_pattern = re.compile(
        re.escape(CENS_BEGIN) + r".*?" + re.escape(CENS_END), re.S
    )
    rc = 0
    for doc in args.report:
        text = doc.read_text(encoding="utf-8")
        if cens_block and cens_pattern.search(text):
            replaced = cens_pattern.sub(lambda _: cens_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: censoring-sensitivity block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: censoring-sensitivity block regenerated")
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
