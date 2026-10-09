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


def test_no_numbered_item_lives_outside_section_nine() -> None:
    """The failure mode, caught directly rather than through a count.

    Items were inserted before `## 10. Limitations` twice, and the clean-clone section sits
    between 9 and 10, so both times they landed inside it. Neither of the tests above saw
    it: the numbering stayed contiguous and the contents count was updated to the number of
    items the author believed they had added, so the two agreed about a document neither
    had looked at.
    """
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## 9. Measured negative results")
    end = text.index("## 9b.", start)
    after = text[end:]
    stray = ITEM.findall(after)
    assert not stray, (
        f"numbered items after section 9 ends: {stray}. They were meant for section 9 and "
        "the section between it and the limitations swallowed them."
    )
    # And nothing numbered sits before the section either.
    assert not ITEM.findall(text[:start])


def test_the_name_mismatch_table_points_at_results_that_exist() -> None:
    """Section 9 opens by naming a defect ten of its findings share, with a table.

    The table cites result numbers, and a citation to a result that does not exist is the
    same defect the table is about -- a label pointing somewhere other than where it says.
    """
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## 9. Measured negative results")
    end = text.index("\n1. **", start)
    preamble = text[start:end]
    cited = {
        int(m) for m in re.findall(r"\| (\d+) \|", preamble)
    }
    assert cited, "the opening table no longer cites any result"
    items = {int(i) for i in ITEM.findall(_section_nine()) if i.isdigit()}
    missing = sorted(cited - items)
    assert not missing, f"the opening table cites results that do not exist: {missing}"


def test_the_stated_count_of_shared_defects_matches_the_table() -> None:
    """The count in the prose and the rows in the table are the same claim twice."""
    text = REPORT.read_text(encoding="utf-8")
    start = text.index("## 9. Measured negative results")
    end = text.index("\n1. **", start)
    preamble = text[start:end]
    # Whitespace-normalised: the sentence is bold and wraps, so a line break can fall
    # inside the match. It did, and the test read it as "the opening no longer states a
    # count" -- a guard reporting a missing claim because the claim moved onto two lines.
    flat = re.sub(r"\s+", " ", preamble)
    stated = re.search(r"\*\*(\w+) of these findings are the same defect\*\*", flat)
    assert stated, "the opening no longer states how many findings share the defect"
    words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
             "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
             "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20}
    n = words.get(stated.group(1).lower())
    assert n is not None, f"unrecognised number word {stated.group(1)!r}"
    rows = [
        ln for ln in preamble.splitlines()
        if ln.startswith("| ") and "---" not in ln and not ln.startswith("| the name")
    ]
    assert len(rows) == n, (
        f"the opening says {n} findings share the defect and the table has {len(rows)} rows"
    )


def test_the_prose_count_matches_the_section_too() -> None:
    """The same hole, one layer out.

    The contents table's count is checked above. The report's opening paragraph states the
    count a second time and spells it as a word -- "section 9 is the forty-three measured
    negative results" -- which neither the number guard nor the test above can see, because
    one looks for decimals and the other looks in the table. It sat at forty-three while the
    section held fifty-eight.
    """
    text = REPORT.read_text(encoding="utf-8")
    words = {
        "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
        "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    }
    units = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9}
    m = re.search(r"section 9 is the ([a-z]+(?:-[a-z]+)?) measured negative results", text)
    assert m, "the opening paragraph no longer states the count in words"
    spelled = m.group(1)
    if "-" in spelled:
        tens, ones = spelled.split("-")
        value = words[tens] + units[ones]
    else:
        value = words.get(spelled, units.get(spelled))
    assert value is not None, f"unrecognised number word {spelled!r}"
    items = ITEM.findall(_section_nine())
    assert value == len(items), (
        f"the opening paragraph says {spelled} ({value}), section 9 holds {len(items)}"
    )
