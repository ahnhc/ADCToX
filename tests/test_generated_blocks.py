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


def test_regenerating_twice_changes_nothing() -> None:
    """Idempotence, which staleness does not imply.

    A block that grows by four spaces on every regeneration is never stale -- each run
    produces exactly what the next check compares against, one run later. Two new blocks
    did exactly that: the substitution matches from the opening marker, so the marker's own
    leading whitespace stays in the document, and prefixing the indent to the first line
    too added it again each time. Four spaces, then eight, and eight spaces inside a
    numbered list item is a markdown code fence, so the table rendered as literal text
    with its pipes showing.

    The check is the generator applied twice with no artefact change between: if the second
    run reports a rewrite, the generator is not a function of the artefacts alone.
    """
    if not (ROOT / "artifacts" / "forward_other_metrics.json").exists():
        return
    before = {d: d.read_text(encoding="utf-8") for d in _docs()}
    try:
        first = subprocess.run(
            [sys.executable, "scripts/sync_report_numbers.py"],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert first.returncode == 0, first.stderr[-600:]
        after_one = {d: d.read_text(encoding="utf-8") for d in _docs()}
        second = subprocess.run(
            [sys.executable, "scripts/sync_report_numbers.py"],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert second.returncode == 0, second.stderr[-600:]
        for doc in _docs():
            assert doc.read_text(encoding="utf-8") == after_one[doc], (
                f"{doc.name} changed on a second run with the same artefacts, so a block "
                "is a function of the document as well as of its artefact:\n"
                + second.stdout
            )
    finally:
        for doc, text in before.items():
            if doc.read_text(encoding="utf-8") != text:
                doc.write_text(text, encoding="utf-8")


def test_a_block_inside_a_list_item_stays_at_the_list_indent() -> None:
    """Four spaces continues the item; eight is a code fence.

    The compounding bug above rendered a table as literal text. The symptom is mechanical
    and checkable without running the generator: no generated marker may sit deeper than
    the indent of the list item it belongs to.
    """
    for doc in _docs():
        for line in doc.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([ \t]*)<!-- /?generated: ([a-z-]+) -->", line)
            if not m:
                continue
            indent, name = m.group(1), m.group(2)
            assert "\t" not in indent, f"{doc.name}: block '{name}' is tab-indented"
            assert len(indent) in (0, 4), (
                f"{doc.name}: block '{name}' sits at {len(indent)} spaces. Zero is section "
                "top level and four continues a numbered list item; anything else is a "
                "markdown code fence, which renders the block as literal text."
            )


def test_each_generated_block_holds_its_own_content() -> None:
    """A block must contain what its name says, not another block's text.

    Two names in the generator were shadowed by a loop variable in the same sitting. The
    first, `pattern`, made the model card report "has no generated block" while carrying
    twelve. The second, `block`, wrote the threshold-accuracy table over the
    fitted-parameter list in both documents -- nine paragraphs of parameter interpretation
    replaced by a table about reporting cuts, under the heading "Calibration and
    uncertainty". The idempotence test above did not see it, because the wrong content was
    written consistently.

    So each block is checked for a string only it would carry.
    """
    FINGERPRINT = {
        "fitted-parameters": ("tau_cleav", "tau_mech", "sigma_agent"),
        "threshold-accuracy": ("stated cut", "overshoot"),
        "rank1": ("rank-1 scale", "worst organ"),
        "across-agent-trend": ("across-agent rho", "identification"),
        "across-agent-per-axis": ("organ axis", "across-agent rho"),
        "posterior-choice": ("queries compared",),
        "objective-label-gap": ("median", "display resolution"),
        "rank-resolution": ("queries swept",),
        "corpus-ablation": ("stage",),
    }
    for doc in _docs():
        text = doc.read_text(encoding="utf-8")
        for name, needles in FINGERPRINT.items():
            m = re.search(
                re.escape(f"<!-- generated: {name} -->")
                + r"(.*?)"
                + re.escape(f"<!-- /generated: {name} -->"),
                text, re.S,
            )
            if not m:
                continue
            body = m.group(1)
            missing = [n for n in needles if n not in body]
            assert not missing, (
                f"{doc.name}: the '{name}' block does not contain {missing}. Another "
                "block's text was written into it -- check for a shadowed name in "
                "sync_report_numbers.py."
            )
