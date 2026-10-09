"""A figure that goes stale keeps tracing, so the guard's clean run needs this partition.

`check_report.py` scans `artifacts/superseded/` on purpose. The cost is that a figure which
goes out of date traces to the artefact recording what it used to be, and the guard reports
a clean run. Two real stale figures passed that way for a month (negative result 62).

What is pinned: nothing is undeclared, the declarations carry reasons rather than being a
bare allowlist, and the classification is a rule applied to the document rather than a list
of strings -- a list that long is maintained by adding to it, and adding to it is how a
stale figure gets silenced.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import superseded_only_figures as sof  # noqa: E402

ART = ROOT / "artifacts" / "superseded_only_figures.json"


def _doc() -> dict:
    assert ART.exists(), "run `make superseded-figures`"
    return json.loads(ART.read_text(encoding="utf-8"))


def test_nothing_is_undeclared() -> None:
    doc = _doc()
    undeclared = [r for r in doc["figures"] if r["classification"] == "undeclared"]
    assert not undeclared, (
        "these figures appear in a superseded artefact and in no current one, and are "
        "neither paired with a live figure nor declared. Each is either a deliberate "
        "before/after quotation -- add it to DELIBERATE with its reason -- or a figure that "
        f"went stale and kept its trace: {[(r['document'], r['line'], r['figure']) for r in undeclared]}"
    )


def test_every_declaration_says_why() -> None:
    """A bare allowlist would let a stale figure be silenced by adding its string."""
    for figure, reason in sof.DELIBERATE.items():
        assert reason and len(reason) > 30, (
            f"{figure} is declared with no reason worth reading; the declaration is the "
            "only thing distinguishing it from a stale number"
        )


def test_the_declarations_are_all_still_used() -> None:
    """A declaration for a figure the report no longer carries hides its replacement."""
    doc = _doc()
    present = {r["figure"] for r in doc["figures"]}
    stale = sorted(set(sof.DELIBERATE) - present)
    assert not stale, (
        f"declared figures that no longer appear as superseded-only: {stale}. Remove them, "
        "or the next figure to take that value is declared before anyone looks at it."
    )


def test_the_partition_splits_per_file_not_per_directory() -> None:
    """`artifacts/superseded/` is a subdirectory of `artifacts/`.

    Splitting the pool by directory would drag every superseded value into the live pool
    through the guard's own `*/*.json` glob, and the script would report zero figures while
    checking nothing.
    """
    live, sup = sof._partition()
    assert sup, "the superseded pool is empty; the split is not reaching the subdirectory"
    assert live, "the live pool is empty"
    # The two overlap -- many values appear in both -- but neither may contain the other.
    assert not sup <= live, (
        "every superseded value is also in the live pool, which is what splitting by "
        "directory looks like"
    )


def test_the_script_fails_on_an_undeclared_figure() -> None:
    """Exit code, not just output: `make all` has to stop on this."""
    proc = subprocess.run(
        [sys.executable, "scripts/superseded_only_figures.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "undeclared" in proc.stdout
