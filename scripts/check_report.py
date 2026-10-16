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

One thing this check cannot do, and it is worth naming rather than discovering later:
`artifacts/superseded/` keeps results a later fix overturned, so the report can quote them
in before/after comparisons and have them trace. That also means a *stale* figure quoted as
current will pass, because it genuinely exists in a record. Whether a number is being
quoted as history or as the present is a semantic judgement no membership test makes. It
has already happened once: a sentence reading "it comes back at +0.054" kept passing after
the live value moved to +0.0966, because the superseded record held the old one.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Decimals with at least two places: the shape of a measured quantity rather than a count.
# The trailing guard excludes a following *digit* after a dot, not every dot. The first
# version excluded any following period, which silently skipped every figure that ends a
# sentence -- 18 of them in the report, including `0.0345`, `0.2120` and `3.872`. A guard
# that cannot see the most common position for a number in prose is not checking the prose.
# `1.2.3` is still excluded, which is what the guard was for.
NUMBER = re.compile(r"(?<![\w.])(-?\d+\.\d{2,})(?!\w)(?!\.\d)")

# The documents are typeset with a Unicode minus (U+2212), which the pattern above cannot
# see, so every negative figure was extracted without its sign -- checked as positive and
# matched against whatever unrelated positive value happened to be in the pool. A second
# silent false-pass channel alongside the precision downgrade. Normalized before matching;
# the en dash is left alone because it separates ranges rather than negating anything.
def _normalize_signs(text: str) -> str:
    return text.replace("\u2212", "-")
# Figures this guard structurally cannot check, counted so it can state its own reach.
#
# At one decimal place there are about a thousand distinct values and the pool holds
# fifteen thousand, so every one of them matches something: extending `NUMBER` downward
# would not check these figures, it would pass them. Integer percentages are worse. So they
# are not checked and the right response is to say how many there are -- a guard that
# reports "every figure traces" while a fifth of the report's figures are invisible to it
# is making a narrower claim than it sounds like.
#
# This is not hypothetical. "the leader wins a median 52.2% of paired draws" and "the head
# tie group holds a median 73%" were both stale, in the report and in the model card, and
# both sat below this floor. They were found by reading the model card, not by the guard.
ONE_DECIMAL = re.compile(r"(?<![\w.])(-?\d+\.\d)(?!\d)(?!\w)")
INTEGER_PERCENT = re.compile(r"(?<![\w.])(\d{1,3})%")
GENERATED = re.compile(r"<!-- generated:.*?<!-- /generated:[^>]*-->", re.S)

# Skip fenced code and inline code, which quote commands rather than results.
FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`]*`")


def artefact_values(dirs: list[Path]) -> tuple[set[str], dict[str, int]]:
    """Every numeric value in the artefact JSONs, and how many values each string matches.

    The multiplicity is the honest part. "Traces to an artefact" means the figure's string
    appears somewhere in the pool, and with 19,000 values a three-decimal number appears by
    coincidence almost always -- which the guard's own measured false-pass rate says, at 88%
    for three decimals. A figure matching one or two pool entries was probably copied from
    the artefact it claims. One matching four hundred was not checked by anything.

    So the count travels with the set, and the summary reports how much of the report the
    guard is actually verifying rather than only that nothing failed.
    """
    out: set[str] = set()
    multiplicity: dict[str, int] = {}

    def walk(node) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            for places in (2, 3, 4):
                for form in (
                    f"{round(float(node), places):.{places}f}",
                    f"{round(float(node) * 100, places):.{places}f}",
                ):
                    out.add(form)
                    multiplicity[form] = multiplicity.get(form, 0) + 1

    for d in dirs:
        # One level of subdirectory is scanned as well as the top level.
        # `artifacts/superseded/` holds results a later fix overturned, quoted deliberately
        # in before/after comparisons, and a superseded number should trace to a record
        # rather than to an allowlist entry saying a human checked it once. The corpus
        # ablation then added `artifacts/with_literature/` and
        # `artifacts/with_literature_final/`, whose fitted metrics the report quotes --
        # and those went unscanned until the guard failed on `0.7213`, which is a real
        # figure from a real artefact it simply could not see.
        for path in sorted([*d.glob("*.json"), *d.glob("*/*.json")]):
            try:
                walk(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return out, multiplicity


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
    # docs/ is scanned as well. It was not, so every figure in the model card -- which
    # quotes the same fitted parameters as the report -- went unchecked, and all of them
    # were stale.
    ap.add_argument("report", type=Path, nargs="*", default=[Path("report"), Path("docs")])
    # The report draws on both locations: fitted metrics live in artifacts/ and corpus
    # statistics in data/processed/. Scanning only one leaves real figures unexplained.
    ap.add_argument("--artifacts", type=Path, nargs="+",
                    default=[Path("artifacts"), Path("data/processed")])
    ap.add_argument("--allowlist", type=Path,
                    default=Path("report/number_allowlist.json"))
    args = ap.parse_args()

    values, multiplicity = artefact_values(args.artifacts)
    allow = load_allowlist(args.allowlist)
    # Counted with the same glob the scan uses, or the header understates the pool.
    n_files = sum(
        len(list(d.glob("*.json"))) + len(list(d.glob("*/*.json")))
        for d in args.artifacts
    )
    print(f"{len(values):,} numeric values across {n_files} artefacts in "
          f"{', '.join(str(d) for d in args.artifacts)}; {len(allow)} allowlisted")
    rates = {d: measured_false_pass_rate(values, allow, d) for d in (2, 3, 4)}
    print(
        "  measured false-pass rate on fabricated figures: "
        + ", ".join(f"{d}dp {100 * r:.0f}%" for d, r in rates.items())
        + "  <- a clean run means less at low precision"
    )

    unexplained: list[tuple[str, int, str]] = []
    # How many pool entries each passing figure matched, so the summary can say how much
    # of the report the guard actually verified.
    verified: list[tuple[str, int, str, int]] = []
    checked = 0
    # docs/archive/ holds superseded documents kept for the record; their figures come from
    # experiments whose outputs are not in artifacts/, so they are not checked here.
    docs = sorted(d for root in args.report for d in root.rglob("*.md")
                  if "archive" not in d.relative_to(root).parts)
    for doc in docs:
        text = _normalize_signs(FENCE.sub(" ", doc.read_text(encoding="utf-8")))
        for lineno, line in enumerate(text.splitlines(), 1):
            line = INLINE.sub(" ", line)
            for m in NUMBER.finditer(line):
                raw = m.group(1)
                checked += 1
                if raw in allow:
                    verified.append((doc.name, lineno, raw, 0))
                    continue
                if raw.lstrip("-") in values or raw in values:
                    verified.append((
                        doc.name, lineno, raw,
                        multiplicity.get(raw, multiplicity.get(raw.lstrip("-"), 0)),
                    ))
                    continue
                # Tolerate a sign or trailing-zero difference in presentation, and
                # nothing else. Retrying at lower precision is what made this check
                # vacuous: it turns "does this exact figure exist" into "does something
                # roughly like it exist", and in a pool this dense the answer is always
                # yes.
                hit = _presentation_variants(raw) & (values | set(allow))
                if hit:
                    verified.append((
                        doc.name, lineno, raw,
                        max(multiplicity.get(h, 0) for h in hit),
                    ))
                    continue
                unexplained.append((doc.name, lineno, raw))

    print(
        f"{checked} decimal figures checked across {len(docs)} documents in "
        f"{', '.join(str(d) for d in args.report)}"
    )

    # What the guard cannot see, measured on the same documents. Generated blocks are
    # excluded: a figure inside one is regenerated from its artefact on every sync, so its
    # precision is irrelevant to whether it can go stale.
    below_floor = {"one_decimal": 0, "integer_percent": 0}
    for doc in docs:
        text = GENERATED.sub(" ", doc.read_text(encoding="utf-8"))
        text = INLINE.sub(" ", FENCE.sub(" ", _normalize_signs(text)))
        below_floor["one_decimal"] += len(ONE_DECIMAL.findall(text))
        below_floor["integer_percent"] += len(INTEGER_PERCENT.findall(text))
    invisible = below_floor["one_decimal"] + below_floor["integer_percent"]
    if invisible:
        reach = 100.0 * checked / (checked + invisible)
        print(
            f"  below this guard's precision floor and therefore unchecked: "
            f"{below_floor['one_decimal']} one-decimal figures and "
            f"{below_floor['integer_percent']} integer percentages outside generated "
            f"blocks, so the guard reaches {reach:.0f}% of the hand-written figures.\n"
            "    Extending it downward would pass them rather than check them: at one "
            "decimal the pool saturates. The remedy is a generated block, not a wider "
            "pattern."
        )
    # How much of the report the guard actually verified. "Traces to an artefact" means
    # the string appears somewhere in the pool, and a figure matching hundreds of pool
    # entries was checked by nothing -- the 88% three-decimal false-pass rate above is the
    # same fact stated as a rate. Reporting the distribution turns a reassuring "all clear"
    # into a statement about coverage.
    if verified:
        buckets = {"allowlisted": 0, "unique (1)": 0, "few (2-5)": 0,
                   "many (6-50)": 0, "coincidental (>50)": 0}
        for _, _, _, n in verified:
            if n == 0:
                buckets["allowlisted"] += 1
            elif n == 1:
                buckets["unique (1)"] += 1
            elif n <= 5:
                buckets["few (2-5)"] += 1
            elif n <= 50:
                buckets["many (6-50)"] += 1
            else:
                buckets["coincidental (>50)"] += 1
        total = len(verified)
        print("  how tightly each passing figure is pinned, by how many artefact values "
              "it matches:")
        for name, n in buckets.items():
            print(f"    {name:20s} {n:4d}  {100.0 * n / total:5.1f}%")
        weak = sorted(
            (n, name, line, raw) for name, line, raw, n in verified if n > 50
        )
        if weak:
            print(f"  the {len(weak)} loosest, which this guard is not really checking:")
            for n, name, line, raw in sorted(weak, reverse=True)[:8]:
                print(f"    {name}:{line}  {raw}  matches {n} artefact values")

    # The guard's description of itself. `N are allowlisted` is an integer, and this guard
    # only checks decimals, so the sentence drifted from 16 to a real 19 without anything
    # noticing -- a hand-typed figure in the very paragraph that promises none are. Cheap to
    # pin, and the failure it prevents is embarrassing in a way a wrong decimal is not.
    stale_self_description: list[tuple[str, int, str]] = []
    for doc in sorted(d for root in args.report for d in root.glob("*.md")):
        for lineno, line in enumerate(
            doc.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for m in re.finditer(r"(\d+) are allowlisted", line):
                if int(m.group(1)) != len(allow):
                    stale_self_description.append(
                        (doc.name, lineno,
                         f"says {m.group(1)} allowlisted, the allowlist holds {len(allow)}")
                    )

    if not unexplained and not stale_self_description:
        print("every figure traces to an artefact or the allowlist")
        return 0

    for name, lineno, why in stale_self_description:
        print(f"\n{name}:{lineno}  {why}")
    if not unexplained:
        return 1

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


# Run this WITHOUT a pipe. `check_report.py | tail -2; echo $?` reports `tail`'s status,
# not this script's, so a failing guard reads as a passing one. That mistake was made five
# times in one session -- on this script, on the unused-import check, and on pytest -- and
# twice it put a commit in with the tree red. The guard returns 1 on an untraceable figure;
# the shell has to be allowed to see it.
if __name__ == "__main__":
    raise SystemExit(main())
