"""Every `<!-- generated: -->` block in the report must match what the generator produces.

There was no check on this. `make check-report` runs `sync-report` first, so it rewrites a
stale block instead of reporting one, and `check_report.py` only asks whether each figure
traces to an artefact -- a block built from last week's artefact passes that, because the
artefact is still on disk. The gap was not hypothetical: section 34's figures were written
by hand and were wrong about five things at once by the time anyone looked (negative result
38), and nothing in the test suite could have said so.

So the invariant is the generator's own `--check` mode: refuse to pass if regenerating any
block would change the document. That makes "no figure in this report was typed by hand"
machine-checked for the generated blocks specifically, which is where the claim is strongest.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKER = re.compile(r"<!-- generated: ([a-z-]+) -->")


def _docs() -> list[pathlib.Path]:
    return [ROOT / "report" / "findings.md", ROOT / "docs" / "MODEL_CARD.md"]


def test_no_generated_block_is_stale() -> None:
    if not (ROOT / "artifacts" / "forward_other_metrics.json").exists():
        return  # no fit in this tree; `make forward` first
    proc = subprocess.run(
        [sys.executable, "scripts/sync_report_numbers.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        "a generated block does not match its artefact; run `make sync-report`.\n"
        + proc.stdout + proc.stderr
    )


def test_every_marker_is_balanced() -> None:
    """An unclosed marker makes the block invisible to the generator rather than stale.

    The regex that rewrites a block matches BEGIN through END. A typo in the closing marker
    leaves the opening one in place and the block frozen at whatever it said, with no error
    anywhere -- the failure mode is silence, so it is checked directly.
    """
    for doc in _docs():
        text = doc.read_text(encoding="utf-8")
        for name in MARKER.findall(text):
            assert f"<!-- /generated: {name} -->" in text, (
                f"{doc.name}: block '{name}' is opened and never closed, so nothing "
                "regenerates it"
            )


def test_the_source_axis_block_is_generated_and_not_typed() -> None:
    """Section 34 specifically, because it is the one that was hand-typed and went stale."""
    text = (ROOT / "report" / "findings.md").read_text(encoding="utf-8")
    assert "<!-- generated: source-axis -->" in text
    start = text.index("<!-- generated: source-axis -->")
    end = text.index("<!-- /generated: source-axis -->")
    block = text[start:end]
    # The figures the old paragraph got wrong, now in the block because they are read from
    # the artefact: the both-source agent count and the widest negative axis.
    assert "agents with arms from" in block
    assert "logit on" in block
