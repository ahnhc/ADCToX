"""The contents table has to list every section, and no section it does not have.

The report is 1,580 lines across twenty top-level sections, and it grew by insertion -- the
lettering runs 5, 5b, 5c, 5d, 5e, 5e-b, 5e-c, 5f and on, in the order the sections were
written. A hand-maintained contents table in a document that grows that way drifts within a
day, and a contents table that silently omits a section is worse than none: a reader takes
it as the document's shape.

So this is the same guard as the number check, applied to structure rather than to figures,
and it was written at the same time as the table rather than after the first drift.
"""

from __future__ import annotations

import pathlib
import re

REPORT = pathlib.Path(__file__).resolve().parents[1] / "report" / "findings.md"
HEADING = re.compile(r"^## (?P<title>.+)$", re.M)
# A contents row: `| 5e-b. Ranking | ... |`, with optional bold around the label.
ROW = re.compile(r"^\|\s*\*{0,2}(?P<label>[0-9][0-9a-z-]*\.[^|*]+?)\*{0,2}\s*\|", re.M)


def _sections() -> list[str]:
    text = REPORT.read_text(encoding="utf-8")
    body = text[text.index("## 1. What was built"):]
    return [m.group("title").strip() for m in HEADING.finditer(body)]


def _contents() -> list[str]:
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## Contents, and what each section found")
    end = text.index("## 1. What was built")
    return [m.group("label").strip() for m in ROW.finditer(text[start:end])]


def _number(label: str) -> str:
    return label.split(".", 1)[0].strip().lower()


def test_every_section_is_in_the_contents() -> None:
    listed = {_number(x) for x in _contents()}
    missing = [s for s in _sections() if _number(s) not in listed]
    assert not missing, f"sections absent from the contents table: {missing}"


def test_the_contents_lists_no_section_that_does_not_exist() -> None:
    present = {_number(s) for s in _sections()}
    extra = [x for x in _contents() if _number(x) not in present]
    assert not extra, f"contents rows with no section behind them: {extra}"


def test_each_row_says_what_the_section_found() -> None:
    """A contents table of titles is a navigation aid; one of findings is the summary a
    reviewer reads first. Every row must carry a second cell with substance in it."""
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## Contents, and what each section found")
    end = text.index("## 1. What was built")
    rows = [
        line for line in text[start:end].splitlines()
        if line.startswith("|") and not set(line) <= set("|- ")
    ][1:]  # drop the header row
    assert len(rows) >= len(_sections())
    for line in rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert len(cells) == 2, line
        assert len(cells[1]) > 30, f"contents row says nothing: {line}"
