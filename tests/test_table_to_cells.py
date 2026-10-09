"""Tests for arm attribution and cell extraction.

The plan measured this as the project's largest risk. Detecting an agent's papers loosely
gave 52 of 54 agents "an extractable AE table"; requiring the agent in the title and a
primary-report signature left 13. The other 39 were reviews carrying other drugs' tables --
a 75% false-positive rate whose failure is silent, because a misattributed table does not
look wrong, it looks like data, and the arithmetic gate cannot catch it: that gate verifies
a count against its percentage, not against the drug it belongs to.

So these tests are about refusal. Most of them assert that a table is rejected.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest
from lxml import etree

from adctox.extract.jats_tables import parse_table_wrap
from adctox.extract.table_to_cells import attribute_column, extract
from adctox.taxonomy import default_taxonomy

PT_DICT = pathlib.Path("data/processed/pt_soc_dictionary.json")

MINE = {"brentuximab", "brentuximab vedotin", "adcetris", "sgn-35"}
OTHERS = {
    "trastuzumab_deruxtecan": {"trastuzumab deruxtecan", "t-dxd", "enhertu"},
    "polatuzumab_vedotin": {"polatuzumab", "polivy"},
    "nivolumab": {"nivolumab", "opdivo"},
}


@pytest.fixture(scope="module")
def tax():
    t = default_taxonomy()
    t.load_pt_dictionary(PT_DICT)
    return t


def _table(xml: str):
    return parse_table_wrap(etree.fromstring(textwrap.dedent(xml).strip().encode()))


SINGLE_ARM = """
<table-wrap>
  <label>Table 2</label>
  <caption><p>Treatment-emergent adverse events occurring in ≥10% of patients</p></caption>
  <table>
    <thead><tr><th>Event</th><th>Brentuximab vedotin 1.8 mg/kg (N = 100)</th></tr></thead>
    <tbody>
      <tr><td>Nausea</td><td>40 (40.0)</td></tr>
      <tr><td>Peripheral sensory neuropathy</td><td>52 (52.0)</td></tr>
      <tr><td>Neutropenia</td><td>21 (21.0)</td></tr>
      <tr><td>Any treatment-emergent adverse event</td><td>98 (98.0)</td></tr>
    </tbody>
  </table>
</table-wrap>
"""


def test_a_single_arm_table_extracts_and_drops_its_aggregate_row(tax) -> None:
    out = extract(_table(SINGLE_ARM), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert {c.axis for c in out.cells} == {
        "gastrointestinal", "neurologic", "haematologic"
    }
    # The 98% aggregate row must not appear. It is the largest count in the table and
    # would dominate whatever axis it reached.
    assert all(c.n != 98 for c in out.cells)
    assert out.counters["row_aggregate"] == 1
    assert all(c.denominator == 100 for c in out.cells)
    assert all(c.arithmetic_ok for c in out.cells)
    assert out.threshold is not None and out.threshold.value == 10.0
    assert out.threshold.is_explicit


def test_the_aggregate_rows_rate_still_informs_the_threshold(tax) -> None:
    """The cut applies to the whole table, so an aggregate row's rate cleared it too.
    Excluding aggregate rows from the rate pool would bound the cut too loosely."""
    t = _table(SINGLE_ARM.replace(
        "Treatment-emergent adverse events occurring in ≥10% of patients",
        "Treatment-emergent adverse events"))
    out = extract(t, "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.threshold is not None
    assert out.threshold.value == 21.0           # min over all printed rates
    assert out.threshold.is_upper_bound


def test_a_comparator_arm_is_dropped_while_the_agent_arm_survives(tax) -> None:
    """A randomised ADC-versus-chemotherapy trial is a legitimate source for the ADC's
    arm, so a named comparator does not reject the table -- but none of its counts may
    reach the corpus."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>Brentuximab vedotin (N = 100)</th>
                   <th>Physician's choice (N = 50)</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td><td>10 (20.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert [(c.n, c.denominator) for c in out.cells] == [(40, 100)]
    kinds = {a.col: a.kind for a in out.columns}
    assert kinds[1] == "agent" and kinds[2] == "comparator"


def test_a_table_naming_another_adc_is_rejected_whole(tax) -> None:
    """The 75% trap. Keeping our column and dropping theirs depends on having read the
    header correctly, and a misattribution means that is the one thing you did not do.
    Measured consequence of getting it wrong: one table corrupts every row of an agent
    that may have only a handful of papers."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events across antibody-drug conjugates</p></caption>
      <table>
        <thead><tr><th>Event</th><th>Brentuximab vedotin (N = 100)</th>
                   <th>Polatuzumab vedotin (N = 80)</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td><td>24 (30.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert not out.accepted
    assert out.reason.startswith("ambiguous_column")
    assert "polatuzumab_vedotin" in out.reason
    assert out.cells == []


def test_a_single_unidentifiable_data_column_rejects_the_table(tax) -> None:
    """A two-arm table whose arms cannot be told apart is worse than no table: it
    contributes a plausible rate to the wrong arm and nothing downstream can detect it."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>Brentuximab vedotin (N = 100)</th>
                   <th>Arm B (N = 60)</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td><td>18 (30.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert not out.accepted
    assert "unidentifiable header" in out.reason
    assert out.cells == []


def test_a_column_naming_both_this_agent_and_another_is_ambiguous() -> None:
    """A combination column. The rate belongs to neither drug alone, and the corpus models
    combination as a binary covariate on an arm -- not as a shared row."""
    a = attribute_column(
        "Brentuximab vedotin + nivolumab (N = 40)", 1, 40, MINE, OTHERS
    )
    assert a.kind == "ambiguous"
    assert "nivolumab" in a.reason


def test_a_pooled_total_column_is_usable(tax) -> None:
    """For a monotherapy paper a pooled column is what ClinicalTrials.gov reports anyway."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Treatment-related adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>All patients (N = 160)</th></tr></thead>
        <tbody><tr><td>Fatigue</td><td>80 (50.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert out.columns[1].kind == "total"
    assert [c.n for c in out.cells] == [80]


def test_a_statistic_column_is_not_an_arm(tax) -> None:
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>Brentuximab vedotin (N = 100)</th>
                   <th>P value</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td><td>0.03</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert out.columns[2].kind == "non_arm"
    assert [c.n for c in out.cells] == [40]


def test_an_image_only_table_is_declined_with_its_reason(tax) -> None:
    out = extract(_table("""
    <table-wrap><caption><p>Adverse events</p></caption>
      <graphic xlink:href="t.jpg" xmlns:xlink="http://www.w3.org/1999/xlink"/>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert not out.accepted and out.reason == "image_only"


def test_a_table_of_only_aggregate_rows_yields_nothing(tax) -> None:
    """A safety-summary table is real, attributable and useless: every row is an
    aggregate. It must be declined rather than contribute an empty arm."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Summary of adverse events</p></caption>
      <table>
        <thead><tr><th>Category</th><th>Brentuximab vedotin (N = 100)</th></tr></thead>
        <tbody>
          <tr><td>Any TEAE</td><td>98 (98.0)</td></tr>
          <tr><td>Serious adverse events</td><td>30 (30.0)</td></tr>
          <tr><td>AEs leading to discontinuation</td><td>12 (12.0)</td></tr>
        </tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert not out.accepted and out.reason == "no_mapped_rows"
    assert out.counters["row_aggregate"] == 3
    assert out.cells == []


def test_the_dose_string_is_carried_but_not_parsed(tax) -> None:
    """Dose is modelled by the corpus, but a paper's dose string is free text and getting
    it wrong silently shifts a dose coefficient. It travels unparsed for a separate pass."""
    out = extract(_table(SINGLE_ARM), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert "1.8 mg/kg" in out.columns[1].dose_text
    assert all(not hasattr(c, "dose_mg_kg") for c in out.cells)


def test_a_spanning_header_keeps_each_grade_column_with_its_own_arm(tax) -> None:
    """The colspan case, end to end: both of the agent's grade columns must carry N=100
    and both of the comparator's must be dropped, which only works if the span expanded."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead>
          <tr><th rowspan="2">Event</th>
              <th colspan="2">Brentuximab vedotin (N = 100)</th>
              <th colspan="2">Placebo (N = 50)</th></tr>
          <tr><th>Any grade</th><th>Grade 3-4</th>
              <th>Any grade</th><th>Grade 3-4</th></tr>
        </thead>
        <tbody><tr><td>Nausea</td><td>40 (40.0)</td><td>5 (5.0)</td>
                   <td>10 (20.0)</td><td>1 (2.0)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert sorted(c.n for c in out.cells) == [5, 40]
    assert all(c.denominator == 100 for c in out.cells)
    kinds = {a.col: a.kind for a in out.columns}
    assert kinds[1] == kinds[2] == "agent"
    assert kinds[3] == kinds[4] == "comparator"
