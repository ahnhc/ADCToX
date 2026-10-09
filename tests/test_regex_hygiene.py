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
