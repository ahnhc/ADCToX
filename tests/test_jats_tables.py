"""Tests for the JATS adverse-event table parser.

The parser is the one place in the literature pipeline where a silent error is invisible:
a mis-expanded header binds a count to the wrong denominator, the arithmetic still looks
plausible, and the resulting rate enters the corpus as data. So the span expansion is
tested against the exact failure the project plan measured -- ignoring colspan drops the
arithmetic agreement from 86.8% to 41.3% -- rather than against a convenient example.
"""

from __future__ import annotations

import textwrap

from lxml import etree

from adctox.extract.jats_tables import (
    ARITHMETIC_TOLERANCE_PP,
    parse_table_wrap,
)


def _wrap(xml: str):
    return etree.fromstring(textwrap.dedent(xml).strip().encode("utf-8"))


SPANNING_HEADER = """
<table-wrap id="tbl1">
  <label>Table 2</label>
  <caption><p>Treatment-emergent adverse events in the safety population</p></caption>
  <table>
    <thead>
      <tr>
        <th rowspan="2">Event</th>
        <th colspan="2">Arm A (N = 100)</th>
        <th colspan="2">Arm B (N = 50)</th>
      </tr>
      <tr>
        <th>Any grade</th><th>Grade 3-4</th>
        <th>Any grade</th><th>Grade 3-4</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>Nausea</td><td>40 (40.0)</td><td>5 (5.0)</td><td>10 (20.0)</td><td>1 (2.0)</td></tr>
      <tr><td>Neutropenia</td><td>25 (25.0)</td><td>20 (20.0)</td><td>6 (12.0)</td><td>4 (8.0)</td></tr>
    </tbody>
  </table>
</table-wrap>
"""


def test_a_spanning_header_binds_each_count_to_its_own_denominator() -> None:
    """The measured failure mode. `colspan="2"` over "Arm A (N = 100)" means columns 1 and 2
    both carry N=100; without expansion column 2 inherits nothing and column 3's N=50 slides
    left, so Arm B's counts get checked against Arm A's denominator and pass or fail at
    random. Here every one of the eight counts must reproduce its printed percentage."""
    t = parse_table_wrap(_wrap(SPANNING_HEADER))
    assert t.header_rows == 2
    # The rowspan on "Event" must occupy both header rows, keeping the stub column at 0.
    assert t.column_denominators == {1: 100, 2: 100, 3: 50, 4: 50}
    checked = t.checkable
    assert len(checked) == 8
    assert all(c.arithmetic_ok for c in checked), [
        (c.text, c.denominator, c.arithmetic_delta_pp) for c in checked if not c.arithmetic_ok
    ]
    assert t.arithmetic_pass_rate == 1.0
    assert t.looks_like_ae_table


def test_ignoring_colspan_is_what_breaks_it() -> None:
    """A guard on the guard: if the expansion silently regressed to one column per cell,
    the denominators would land on columns 1 and 2 instead of 1-4, and the test above would
    be the only thing catching it. State the wrong answer explicitly so the regression is
    legible rather than just a failed assertion."""
    t = parse_table_wrap(_wrap(SPANNING_HEADER))
    naive = {1: 100, 2: 50}
    assert t.column_denominators != naive


def test_a_fabricated_count_fails_the_arithmetic_gate() -> None:
    """The hallucination detector, stated as a test. 40 of 100 is 40.0%, not 61.5%."""
    bad = SPANNING_HEADER.replace("<td>40 (40.0)</td>", "<td>40 (61.5)</td>")
    t = parse_table_wrap(_wrap(bad))
    failed = [c for c in t.checkable if not c.arithmetic_ok]
    assert len(failed) == 1
    assert failed[0].n == 40 and failed[0].pct == 61.5
    assert failed[0].arithmetic_delta_pp is not None
    assert failed[0].arithmetic_delta_pp > ARITHMETIC_TOLERANCE_PP
    # And the table-level rate reports it rather than hiding it.
    assert t.arithmetic_pass_rate == 7 / 8


def test_rounding_to_a_whole_percent_still_passes() -> None:
    """The tolerance exists for printing, not for wrong numerators. 25/100 printed as "25"
    and 4/50 printed as "8" must both pass, and the tolerance must be tight enough that an
    off-by-one numerator on a small denominator does not: 5 of 50 is 10%, not 8%."""
    ok = SPANNING_HEADER.replace("<td>25 (25.0)</td>", "<td>25 (25)</td>")
    assert all(c.arithmetic_ok for c in parse_table_wrap(_wrap(ok)).checkable)
    off = SPANNING_HEADER.replace("<td>4 (8.0)</td>", "<td>5 (8.0)</td>")
    assert any(not c.arithmetic_ok for c in parse_table_wrap(_wrap(off)).checkable)


def test_a_rowspan_stub_label_reaches_every_row_it_covers() -> None:
    """SOC-grouped tables put the organ class in a spanning stub cell. Losing it means the
    row label for the second and third PT rows becomes the count, and the row maps to no
    axis at all."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <caption><p>Adverse events by system organ class</p></caption>
      <table>
        <thead><tr><th>SOC</th><th>Event</th><th>Total (N = 80)</th></tr></thead>
        <tbody>
          <tr><td rowspan="2">Blood disorders</td><td>Anaemia</td><td>16 (20.0)</td></tr>
          <tr><td>Neutropenia</td><td>8 (10.0)</td></tr>
        </tbody>
      </table>
    </table-wrap>
    """))
    assert t.row_labels[1] == "Blood disorders"
    assert t.row_labels[2] == "Blood disorders"
    assert t.n_cols == 3
    assert all(c.arithmetic_ok for c in t.checkable)


def test_an_image_only_table_is_reported_not_reconstructed() -> None:
    """Haematologica deposits every table as a .jpg. The parser must say so, because a
    quietly empty parse looks identical to a journal that publishes no AE tables."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <label>Table 1</label>
      <caption><p>Treatment-related adverse events</p></caption>
      <graphic xlink:href="tbl1.jpg" xmlns:xlink="http://www.w3.org/1999/xlink"/>
    </table-wrap>
    """))
    assert t.is_image_only
    assert t.looks_like_ae_table
    assert t.cells == []
    assert t.arithmetic_pass_rate is None


def test_a_table_with_no_stated_denominator_parses_but_is_not_checkable() -> None:
    """11.3% of tables state no N anywhere. Those cells are still data -- the percentage is
    the quantity the model consumes -- but they cannot be arithmetic-verified, and claiming
    an 86.8% pass rate over them would inflate it."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <caption><p>Grade 3 or higher toxicity</p></caption>
      <table>
        <thead><tr><th>Event</th><th>Patients</th></tr></thead>
        <tbody><tr><td>Fatigue</td><td>12 (15.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """))
    cell = [c for c in t.cells if c.n == 12][0]
    assert cell.pct == 15.0
    assert cell.denominator is None
    assert cell.arithmetic_ok is None
    assert t.checkable == []
    assert t.arithmetic_pass_rate is None


def test_a_header_row_without_a_thead_is_still_treated_as_a_header() -> None:
    """Some publishers emit the denominator row inside <tbody>. Parsing it as data would
    read "(N = 60)" as a count of 60 patients with the event named in column 0."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <caption><p>Safety summary</p></caption>
      <table><tbody>
        <tr><td>Event</td><td>ADC (N = 60)</td></tr>
        <tr><td>Rash</td><td>9 (15.0)</td></tr>
      </tbody></table>
    </table-wrap>
    """))
    assert t.header_rows == 1
    assert t.column_denominators == {1: 60}
    assert all(c.arithmetic_ok for c in t.checkable)


def test_n_over_n_carries_its_own_denominator() -> None:
    t = parse_table_wrap(_wrap("""
    <table-wrap><caption><p>Adverse events</p></caption><table><tbody>
      <tr><td>Event</td><td>Rate</td></tr>
      <tr><td>Keratopathy</td><td>34/45</td></tr>
    </tbody></table></table-wrap>
    """))
    cell = [c for c in t.cells if c.n == 34][0]
    assert cell.denominator == 45


def test_a_non_ae_table_is_not_claimed_as_one() -> None:
    """Baseline-characteristics tables have the same shape and would otherwise contribute
    "Female 40 (40.0)" as an adverse event."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <label>Table 1</label>
      <caption><p>Baseline demographics and disease characteristics</p></caption>
      <table><thead><tr><th>Characteristic</th><th>All (N = 100)</th></tr></thead>
      <tbody><tr><td>Female</td><td>40 (40.0)</td></tr></tbody></table>
    </table-wrap>
    """))
    assert not t.looks_like_ae_table


def test_an_ae_table_is_recognised_from_its_contents_when_the_caption_is_vague() -> None:
    """Captions like "Table 3" carry nothing. The vocabulary fallback needs a grade token
    and at least two AE terms, which a demographics table does not have."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <label>Table 3</label>
      <caption><p>Summary by grade</p></caption>
      <table><thead><tr><th>Term</th><th>Grade 3 (N = 70)</th></tr></thead>
      <tbody>
        <tr><td>Neutropenia</td><td>14 (20.0)</td></tr>
        <tr><td>Diarrhoea</td><td>7 (10.0)</td></tr>
      </tbody></table>
    </table-wrap>
    """))
    assert t.looks_like_ae_table


def test_a_drug_name_followed_by_a_dose_is_not_read_as_a_denominator() -> None:
    """A real bug, caught by an attribution test rather than by this file.

    The first denominator pattern allowed a bare `N` with an optional separator, so
    "Brentuximab vedotin 1.8 mg/kg (N = 100)" matched at "...vedoti[n] [1].8" and gave a
    denominator of 1. Every count in the column then failed the arithmetic gate for the
    wrong reason -- and on a column whose real denominator happened to be small, a wrong
    one could have passed instead."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <caption><p>Treatment-emergent adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th>
          <th>Brentuximab vedotin 1.8 mg/kg (N = 100)</th>
          <th>Trastuzumab deruxtecan 5.4 mg/kg (N=184)</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td><td>138 (75.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """))
    assert t.column_denominators == {1: 100, 2: 184}
    assert all(c.arithmetic_ok for c in t.checkable)


def test_a_header_with_no_separator_yields_no_denominator() -> None:
    """The cost of the fix, stated. "N 100" without an `=` or `:` is now ignored, which
    loses a rare phrasing in exchange for never inventing a denominator from a drug name.
    The cells still parse; they are simply not arithmetic-checkable."""
    t = parse_table_wrap(_wrap("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>ADC N 100</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """))
    assert t.column_denominators == {}
    assert t.checkable == []
    assert [c.n for c in t.cells if c.n] == [40]
