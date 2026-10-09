"""Tests for denominator recovery.

Measured on the first 239 fetched articles: of the machine-readable AE tables carrying
counts, 35 state a denominator in the header and 28 do not, so losing the latter is a 44%
loss on exactly the tables that can feed a binomial -- worse than the image-only loss the
plan worried about. Searching captions and footnotes recovered 5 of the 28, because 78.6%
state no N anywhere in the table's own text.

Inference from the cells themselves recovers far more, and the headline number is why it
is not used alone: on the 162 columns that *do* state a denominator, inference produced a
value for 143 and got 19 wrong -- 88.3% precision, with errors mostly of one or two
patients, which is undetectable downstream because the arithmetic gate would re-derive
both the count and the percentage from the same wrong N. Requiring the integer to appear
independently elsewhere in the article gave 124 of 124 correct with all 19 errors rejected.
"""

from __future__ import annotations

import textwrap

from lxml import etree

from adctox.extract.denominator import fill, infer, propose, stated_denominators
from adctox.extract.jats_tables import parse_table_wrap


def _t(xml: str):
    return parse_table_wrap(etree.fromstring(textwrap.dedent(xml).strip().encode()))


NO_HEADER_N = """
<table-wrap>
  <label>Table 3</label>
  <caption><p>Treatment-emergent adverse events</p></caption>
  <table>
    <thead><tr><th>Event</th><th>ADC</th></tr></thead>
    <tbody>
      <tr><td>Nausea</td><td>40 (40.0)</td></tr>
      <tr><td>Fatigue</td><td>33 (33.0)</td></tr>
      <tr><td>Neutropenia</td><td>21 (21.0)</td></tr>
      <tr><td>Rash</td><td>9 (9.0)</td></tr>
    </tbody>
  </table>
</table-wrap>
"""
BASELINE = """
<table-wrap>
  <label>Table 1</label>
  <caption><p>Baseline characteristics (N = 100)</p></caption>
  <table>
    <thead><tr><th>Characteristic</th><th>All patients (N = 100)</th></tr></thead>
    <tbody><tr><td>Female</td><td>55 (55.0)</td></tr></tbody>
  </table>
</table-wrap>
"""


def test_the_denominator_is_identifiable_from_the_cells() -> None:
    """`40 (40.0)` says N is about 100, and four such cells pin it."""
    best, support, total = propose(_t(NO_HEADER_N).cells)
    assert best == 100
    assert support == total == 4


def test_a_candidate_is_rejected_without_independent_corroboration() -> None:
    """The load-bearing refusal. Inference alone was 88.3% precise on the measured sample,
    and its errors are off by one or two -- invisible downstream, because the arithmetic
    gate would re-derive the count and the percentage from the same wrong N."""
    table = _t(NO_HEADER_N)
    assert infer(table, 1, [table]) is None            # nothing else states 100
    got = infer(table, 1, [table, _t(BASELINE)])       # Table 1 does
    assert got is not None
    assert got.value == 100
    assert got.source == "inferred_corroborated"
    assert "Table 1" in got.corroborated_by


def test_a_column_cannot_corroborate_its_own_inference() -> None:
    """Without excluding the column's own header the check is circular: every correct
    inference is corroborated by construction, and the measurement reports perfect
    precision for free. I wrote it that way first and the 100% was meaningless."""
    with_n = NO_HEADER_N.replace("<th>ADC</th>", "<th>ADC (N = 100)</th>")
    table = _t(with_n)
    assert table.column_denominators == {1: 100}
    excluded = stated_denominators([table], exclude=(table, 1))
    assert 100 not in excluded
    assert stated_denominators([table])[100]


def test_prose_and_captions_both_corroborate() -> None:
    for text in [
        "<caption><p>Safety population (n = 100)</p></caption>",
        "<caption><p>Outcomes in 100 patients treated with the ADC</p></caption>",
    ]:
        other = _t(f"<table-wrap><label>Table 1</label>{text}"
                   "<table><tbody><tr><td>x</td><td>1</td></tr></tbody></table>"
                   "</table-wrap>")
        table = _t(NO_HEADER_N)
        got = infer(table, 1, [table, other])
        assert got is not None and got.value == 100, text


def test_identical_counts_do_not_identify_a_denominator() -> None:
    """A column of "1 (1.0)" rows fits N = 100 and N = 101 and N = 99 equally. Requiring
    three distinct counts is what stops a sparse column producing a confident wrong N."""
    flat = _t("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table><tbody>
        <tr><td>Event</td><td>Patients</td></tr>
        <tr><td>Nausea</td><td>1 (1.0)</td></tr>
        <tr><td>Rash</td><td>1 (1.0)</td></tr>
        <tr><td>Fatigue</td><td>1 (1.0)</td></tr>
      </tbody></table>
    </table-wrap>
    """)
    assert propose(flat.cells)[0] is None


def test_too_few_cells_do_not_identify_a_denominator() -> None:
    two = _t("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table><tbody>
        <tr><td>Event</td><td>Patients</td></tr>
        <tr><td>Nausea</td><td>40 (40.0)</td></tr>
        <tr><td>Rash</td><td>9 (9.0)</td></tr>
      </tbody></table>
    </table-wrap>
    """)
    assert propose(two.cells)[0] is None


def test_a_count_above_its_candidate_denominator_rejects_it() -> None:
    """A column holding something other than `n (%)` of N can fit the percentages while
    implying a denominator smaller than one of its own counts."""
    weird = _t("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table><tbody>
        <tr><td>Event</td><td>Value</td></tr>
        <tr><td>Nausea</td><td>400 (40.0)</td></tr>
        <tr><td>Fatigue</td><td>33 (33.0)</td></tr>
        <tr><td>Rash</td><td>9 (9.0)</td></tr>
      </tbody></table>
    </table-wrap>
    """)
    best, _, _ = propose(weird.cells)
    assert best is None


def test_least_squares_breaks_the_tie_rather_than_the_larger_integer() -> None:
    """At a 0.6pp tolerance a large column is only identified to within a patient or two,
    so several integers tie on support. Breaking that tie by preferring the larger one was
    wrong about half the time: on the measured sample it reported 258 as 260 and 73 as 75,
    with every cell supporting both."""
    t = _t("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table><tbody>
        <tr><td>Event</td><td>Patients</td></tr>
        <tr><td>a</td><td>129 (50.0)</td></tr>
        <tr><td>b</td><td>65 (25.2)</td></tr>
        <tr><td>c</td><td>26 (10.1)</td></tr>
        <tr><td>d</td><td>13 (5.0)</td></tr>
      </tbody></table>
    </table-wrap>
    """)
    best, support, total = propose(t.cells)
    assert best == 258
    assert support == total


def test_fill_leaves_a_stated_denominator_alone() -> None:
    """A header that states N is authoritative; re-inferring it could only disagree."""
    with_n = NO_HEADER_N.replace("<th>ADC</th>", "<th>ADC (N = 100)</th>")
    table = _t(with_n)
    assert fill(table, [table, _t(BASELINE)]) == {}


def test_fill_returns_only_corroborated_columns() -> None:
    table = _t(NO_HEADER_N)
    assert fill(table, [table]) == {}
    filled = fill(table, [table, _t(BASELINE)])
    assert set(filled) == {1}
    assert filled[1].value == 100
