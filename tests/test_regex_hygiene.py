"""No lookaround-anchored alternation may be left ungrouped.

The failure mode, measured once and expensive:

    (?<![a-z])alt1|alt2|alt3(?![a-z])

`|` binds loosest, so the lookbehind guards `alt1` only and the lookahead `alt3` only.
Every alternative in between matches with no word boundary at all. In `exclusion_holdout.py`
that let condition names match inside longer words, and because the alternatives came out
of a `set`, whichever one sorted first received the protection -- so the match count moved
with the per-process string hash seed and two consecutive runs of the same command returned
different AUROCs. The bug was found by chasing a 0.0004 difference in a reported figure,
which is a slow and lucky way to find it.

The project builds alternations from configuration in several places -- combination
partners, payload-linker stems, condition name forms -- so the pattern is easy to
reintroduce. This sweeps every `re.compile` in the source tree instead of trusting review.
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOOKAROUND = re.compile(r"\(\?(?:<[=!]|[=!])")


def _top_level_alternation(pattern: str) -> bool:
    """True when a `|` sits outside every group and character class."""
    depth = 0
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            # A `|` inside a character class is a literal, so skip the whole class.
            j = i + 1
            if j < len(pattern) and pattern[j] == "^":
                j += 1
            if j < len(pattern) and pattern[j] == "]":
                j += 1
            while j < len(pattern) and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            return True
        i += 1
    return False


def _compiled_patterns() -> list[tuple[pathlib.Path, int, str]]:
    """Every `re.compile` whose pattern is assembled from string literals.

    A pattern built from a name or a call is reported by the sweep script for manual
    inspection but skipped here, since its literal parts alone would misrepresent it.
    """
    out: list[tuple[pathlib.Path, int, str]] = []
    for base in ("src", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and getattr(node.func, "attr", "") == "compile"):
                    continue
                if not node.args:
                    continue
                literal = "".join(
                    sub.value for sub in ast.walk(node.args[0])
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                )
                if literal:
                    out.append((path, node.lineno, literal))
    return out


def test_the_sweep_sees_something() -> None:
    """A sweep that matches nothing would pass the next test vacuously."""
    patterns = _compiled_patterns()
    assert len(patterns) > 20, len(patterns)
    assert any(LOOKAROUND.search(p) for _, _, p in patterns), (
        "no lookarounds found at all; the walk is probably broken"
    )


def test_no_lookaround_anchors_an_ungrouped_alternation() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{line}  {pattern[:120]}"
        for path, line, pattern in _compiled_patterns()
        if LOOKAROUND.search(pattern) and _top_level_alternation(pattern)
    ]
    assert not offenders, (
        "wrap the alternation in (?:...) so the lookaround applies to all of it:\n  "
        + "\n  ".join(offenders)
    )


def test_the_detector_catches_the_shape_it_is_looking_for() -> None:
    """Guards the guard, with the exact pattern that was wrong."""
    bad = r"(?<![a-z])autoimmune disease|autoimmune disorder(?![a-z])"
    good = r"(?<![a-z])(?:autoimmune disease|autoimmune disorder)(?![a-z])"
    assert LOOKAROUND.search(bad) and _top_level_alternation(bad)
    assert LOOKAROUND.search(good) and not _top_level_alternation(good)
    # A `|` inside a character class is a literal and must not be flagged.
    assert not _top_level_alternation(r"(?<![a-z])[a|b]+(?![a-z])")


def test_the_number_guard_reports_how_tightly_each_figure_is_pinned() -> None:
    """A guard that only ever says "all clear" hides how much it checked.

    "Every figure traces to an artefact" means the figure's string appears somewhere in a
    pool of around 19,000 values, and in a pool that dense a three-decimal number appears
    by coincidence most of the time -- the guard's own measured false-pass rate on
    fabricated figures is 88% at three decimals. The coverage breakdown is what turns that
    from a footnote into a per-figure statement, and it is what shows that figures of the
    form `1.00` match 15,688 pool entries and are therefore verified by nothing.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_report.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout[-1500:]
    out = result.stdout
    assert "how tightly each passing figure is pinned" in out
    for bucket in ("unique (1)", "few (2-5)", "many (6-50)", "coincidental (>50)"):
        assert bucket in out, bucket
    # And the loosest figures are named, not just counted -- a count alone cannot be acted
    # on.
    assert "matches" in out and "artefact values" in out


def test_the_number_guard_still_fails_on_a_fabricated_figure() -> None:
    """The coverage reporting must not have softened the guard. Checked by planting a
    figure rather than by reading the code, because an earlier attempt to test this used a
    `sed` pattern that never matched the report's wording, fabricated nothing, and was read
    as the guard passing something it had never seen."""
    import subprocess
    import sys
    import tempfile

    findings = ROOT / "report" / "findings.md"
    original = findings.read_text(encoding="utf-8")
    planted = original + "\n\nA figure with no artefact behind it: 0.63197 and nothing more.\n"
    try:
        findings.write_text(planted, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_report.py")],
            capture_output=True, text=True, cwd=ROOT,
        )
    finally:
        findings.write_text(original, encoding="utf-8")
    assert result.returncode == 1, result.stdout[-1000:]
    assert "0.63197" in result.stdout
    _ = tempfile


def test_a_figure_that_ends_a_sentence_is_checked() -> None:
    """A coverage hole that hid 18 report figures.

    The figure pattern ended with `(?![\\w.])`, which excludes a following period -- so
    every figure in the most common position for a number in prose, at the end of a
    sentence, was skipped entirely. `0.0345`, `0.2120` and `3.872` among them. The trailing
    guard exists to avoid matching inside a version string, so it now excludes a following
    *digit* after a dot rather than every dot.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from check_report import NUMBER

    assert [m.group(1) for m in NUMBER.finditer("the value is 0.63197.")] == ["0.63197"]
    assert [m.group(1) for m in NUMBER.finditer("rho 0.666, and p 0.0005.")] == [
        "0.666", "0.0005"
    ]
    # Still not a version string, which is what the guard was for.
    assert NUMBER.findall("version 1.2.3 here") == []
    assert NUMBER.findall("see section 2.10.4") == []
    # And not part of a word.
    assert NUMBER.findall("x0.4567y") == []
