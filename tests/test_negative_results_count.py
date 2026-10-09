"""The contents table states how many negative results there are, so it has to be right.

Two items landed inside section 9b rather than section 9, because they were inserted before
`## 10. Limitations` and the clean-clone section sits between the two. Nothing noticed: the
numbering ran 1 to 26 continuously, the items read correctly in sequence, and only counting
them under their own heading showed that 25 and 26 were in the wrong section.

The count in the contents table is an integer, so `check_report.py` cannot see it, which is
the same hole that let "16 are allowlisted" sit beside a 19-entry allowlist.
"""

from __future__ import annotations

import pathlib
import re

REPORT = pathlib.Path(__file__).resolve().parents[1] / "report" / "findings.md"
ITEM = re.compile(r"^(\d+[a-z]?)\. \*\*", re.M)


def _section_nine() -> str:
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## 9. Measured negative results")
    end = text.index("## 9b.", start)
    return text[start:end]


def test_the_contents_count_matches_the_section() -> None:
    items = ITEM.findall(_section_nine())
    text = REPORT.read_text(encoding="utf-8")
    stated = re.search(r"(\d+) results, each reproducible", text)
    assert stated, "the contents table no longer states a count"
    assert int(stated.group(1)) == len(items), (
        f"contents says {stated.group(1)}, section 9 holds {len(items)}"
    )


def test_the_numbering_has_no_gaps() -> None:
    """A gap means an item was moved out of the section and its number went with it."""
    items = ITEM.findall(_section_nine())
    plain = [int(i) for i in items if i.isdigit()]
    assert plain == sorted(plain), plain
    assert plain[0] == 1
    assert plain[-1] == len(plain), (
        f"numbers run to {plain[-1]} over {len(plain)} plain-numbered items, so one is "
        "missing from this section"
    )
