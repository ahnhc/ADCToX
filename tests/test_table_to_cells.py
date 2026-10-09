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


def test_a_combination_column_is_not_attributed_to_the_agent() -> None:
    """A combination rate belongs to neither drug alone, and the corpus models combination
    as a binary covariate on an arm rather than as a shared row. Without this check,
    "Enfortumab vedotin + pembrolizumab (N = 440)" attributes to enfortumab and the EV-302
    combination profile enters the corpus as monotherapy."""
    ev = {"enfortumab", "enfortumab vedotin", "padcev"}
    a = attribute_column("Enfortumab vedotin + pembrolizumab (N = 440)", 1, 440, ev, {})
    assert a.kind == "ambiguous"
    assert "pembrolizumab" in a.reason
    # The monotherapy arm of the same trial is still ours.
    b = attribute_column("Enfortumab vedotin (N = 301)", 2, 301, ev, {})
    assert b.kind == "agent"


def test_a_regimen_acronym_is_recognised_without_any_drug_name() -> None:
    """Haematology headers name the regimen, not its parts. "A+AVD" carries `+` and would
    not match a \\b-delimited pattern, which is why the boundary is non-alphanumeric."""
    bv = {"brentuximab", "brentuximab vedotin", "adcetris"}
    for header in ["A+AVD (N = 664)", "ABVD (N = 670)", "R-CHP (N = 440)"]:
        a = attribute_column(header, 1, 100, bv, {})
        assert a.kind == "comparator", f"{header} -> {a.kind}"


def test_a_trial_of_two_combination_regimens_yields_nothing(tax) -> None:
    """ECHELON-1 is A+AVD versus ABVD: brentuximab appears in the trial but in no
    monotherapy column. The table must be declined rather than contribute a combination
    rate as if it were the drug alone."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>A+AVD (N = 664)</th><th>ABVD (N = 670)</th></tr></thead>
        <tbody><tr><td>Neutropenia</td><td>389 (58.6)</td><td>300 (44.8)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert not out.accepted and out.reason == "no_usable_column"
    assert out.cells == []


SERIOUS_CAPTIONS = [
    "Serious adverse events",
    "Summary of serious treatment-related adverse events",
    "Treatment-related serious adverse events",
    "Table 3. Serious TEAEs",
]
COMMON_CAPTIONS = [
    "Treatment-emergent adverse events occurring in ≥10% of patients",
    "All-grade adverse events",
    "Grade 3-4 adverse events",
    "Adverse events of special interest",
    "Adverse events occurring in ≥20% of patients, including serious adverse events",
]


@pytest.mark.parametrize("caption", SERIOUS_CAPTIONS)
def test_a_serious_event_table_is_filed_as_serious(caption: str) -> None:
    """The two tables rank organs differently -- measured mean rho +0.1455 on the registry
    corpus -- and the model fits them separately, with `serious` treated as complete
    reporting. A common-events table misfiled as serious would have its unreported axes
    recorded as true zeros instead of censored."""
    from adctox.extract.table_to_cells import table_kind
    t = _table(f"""
    <table-wrap><caption><p>{caption}</p></caption>
      <table><tbody><tr><td>Nausea</td><td>4 (4.0)</td></tr></tbody></table>
    </table-wrap>
    """)
    assert table_kind(t) == "serious", caption


@pytest.mark.parametrize("caption", COMMON_CAPTIONS)
def test_a_common_event_table_is_not_claimed_as_serious(caption: str) -> None:
    """The last of these is the case the override exists for: a common-events table whose
    caption mentions serious events in passing."""
    from adctox.extract.table_to_cells import table_kind
    t = _table(f"""
    <table-wrap><caption><p>{caption}</p></caption>
      <table><tbody><tr><td>Nausea</td><td>4 (4.0)</td></tr></tbody></table>
    </table-wrap>
    """)
    assert table_kind(t) == "other", caption


def test_the_row_phrase_and_the_caption_phrase_are_told_apart(tax) -> None:
    """"Serious adverse events" is a table subject in a caption and an aggregate row
    inside a common-events table. The same four words, two meanings, and getting it
    backwards either drops a whole serious table or admits a 30% aggregate as an organ
    rate."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Treatment-emergent adverse events occurring in ≥10% of patients</p></caption>
      <table>
        <thead><tr><th>Event</th><th>Brentuximab vedotin (N = 100)</th></tr></thead>
        <tbody>
          <tr><td>Nausea</td><td>40 (40.0)</td></tr>
          <tr><td>Serious adverse events</td><td>30 (30.0)</td></tr>
        </tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.kind == "other"
    assert [c.n for c in out.cells] == [40]


def test_a_comparator_with_a_typographic_apostrophe_is_still_a_comparator() -> None:
    """Found by validating against the registry, and it put chemotherapy toxicity into the
    corpus as ADC toxicity. "Physician's choice" was already in the pattern, but papers
    write it with U+2019, which `'?` does not match -- so the header is apostrophe-
    normalised before any pattern runs rather than each pattern being widened."""
    for header in [
        "Physician’s choice (n = 49)",
        "Physician's choice (N = 50)",
        "Investigator’s choice (n = 30)",
        "SoC (n = 143), No. (%) Any Grade",      # bare, not "SoC arm"
        "BSC (n = 20)",
        "Chemo (n = 44)",
    ]:
        a = attribute_column(header, 1, 100, MINE, OTHERS)
        assert a.kind == "comparator", f"{header!r} -> {a.kind}"


def test_a_combination_joined_by_a_plus_is_caught_without_naming_the_partner() -> None:
    """The enumerated partner list will always be behind the literature. Validating against
    the registry caught "Pola + BR (N = 35)" -- polatuzumab plus bendamustine-rituximab --
    entering the corpus as polatuzumab monotherapy, because "BR" is a regimen abbreviation
    no list had. So any "+" between two treatment-looking words makes the column a
    combination whether or not either name is recognised."""
    pola = {"polatuzumab", "polatuzumab vedotin", "polivy"}
    for header in ["Pola + BR (N = 35) All grades", "ADC + XYZ-123 (n = 40)"]:
        a = attribute_column(header, 1, 35, pola, {})
        assert a.kind == "ambiguous", f"{header!r} -> {a.kind}"
        assert "+" in a.reason


def test_a_plus_that_is_not_a_combination_is_left_alone() -> None:
    """Receptor status, grade ceilings and prior-line counts all use "+"."""
    pola = {"polatuzumab", "polivy"}
    for header in ["HR+/HER2- MBC (n = 56)", "Grade 3+ events (n = 20)",
                   "2+ prior lines (n = 44)"]:
        a = attribute_column(header, 1, 56, pola, {})
        assert "+" not in a.reason, f"{header!r} -> {a.reason}"


def test_a_subgroup_column_is_dropped_in_favour_of_its_parent_arm(tax) -> None:
    """Found as a run of denominator mismatches against the registry, every one smaller
    than the registry's. A table reporting "Brentuximab vedotin (n = 50) CD30 < 10%"
    beside "... CD30 >= 10%" has two columns naming one arm with denominators of 22 and 28
    against a registry arm of 66. Both are real data about subsets, and admitting them as
    arms puts two correlated partial populations into one trial.

    The signal has to be structural, because the qualifier wording is unbounded -- "CD30min
    < 10%", "Phase I", "Japanese population", "<65 years". A column whose arm identity
    extends another's while carrying a smaller denominator can only be a subset of it."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th rowspan="2">Event</th>
          <th colspan="2">Brentuximab vedotin (n = 50)</th>
          <th>Brentuximab vedotin (n = 22) CD30min &lt; 10%</th>
          <th>Brentuximab vedotin (n = 28) CD30min ≥ 10%</th></tr>
        <tr><th>Any grade</th><th>Grade 3/4</th><th>Any grade</th><th>Any grade</th></tr>
        </thead>
        <tbody>
          <tr><td>Nausea</td><td>20 (40.0)</td><td>5 (10.0)</td>
              <td>9 (40.9)</td><td>11 (39.3)</td></tr>
          <tr><td>Neutropenia</td><td>15 (30.0)</td><td>10 (20.0)</td>
              <td>7 (31.8)</td><td>8 (28.6)</td></tr>
          <tr><td>Fatigue</td><td>25 (50.0)</td><td>3 (6.0)</td>
              <td>11 (50.0)</td><td>14 (50.0)</td></tr>
        </tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert out.counters["column_dropped_as_subgroup"] == 2
    assert {c.denominator for c in out.cells} == {50}


def test_two_different_dose_arms_are_not_mistaken_for_subgroups(tax) -> None:
    """The risk the structural rule runs: a 1.2 mg/kg arm and a 1.8 mg/kg arm are different
    arms, not a subgroup of each other, and neither identity is a prefix of the other."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th>
          <th>Brentuximab vedotin 1.2 mg/kg (n = 40)</th>
          <th>Brentuximab vedotin 1.8 mg/kg (n = 60)</th></tr></thead>
        <tbody>
          <tr><td>Nausea</td><td>16 (40.0)</td><td>24 (40.0)</td></tr>
          <tr><td>Neutropenia</td><td>12 (30.0)</td><td>18 (30.0)</td></tr>
          <tr><td>Fatigue</td><td>20 (50.0)</td><td>30 (50.0)</td></tr>
        </tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax)
    assert out.accepted, out.reason
    assert out.counters.get("column_dropped_as_subgroup", 0) == 0
    assert {c.denominator for c in out.cells} == {40, 60}


def test_the_title_path_is_blocked_when_another_adc_is_in_the_table(tax) -> None:
    """The title path is the loosest thing in the pipeline, so its guard is the one that
    matters: a review's comparison table names the other drugs in its caption even when the
    columns do not, and that is the measured 75% false-positive trap."""
    xml = """
    <table-wrap>
      <caption><p>Adverse events reported with %s</p></caption>
      <table>
        <thead><tr><th>Event</th><th>N = 57 Any grade</th></tr></thead>
        <tbody>
          <tr><td>Nausea</td><td>23 (40.4)</td></tr>
          <tr><td>Neutropenia</td><td>17 (29.8)</td></tr>
          <tr><td>Fatigue</td><td>29 (50.9)</td></tr>
        </tbody>
      </table>
    </table-wrap>
    """
    clean = extract(_table(xml % "this agent"), "brentuximab_vedotin", MINE, OTHERS, tax,
                    title_names_agent=True)
    assert clean.accepted, clean.reason
    assert clean.columns[1].kind == "agent_by_title"

    tainted = extract(_table(xml % "polatuzumab vedotin"), "brentuximab_vedotin",
                      MINE, OTHERS, tax, title_names_agent=True)
    assert not tainted.accepted
    assert tainted.counters["title_path_blocked_by_foreign_agent"] == 1
    assert tainted.cells == []


def test_without_the_title_the_same_table_is_refused(tax) -> None:
    """The second path has to be an explicit decision by the caller, not a default."""
    out = extract(_table("""
    <table-wrap>
      <caption><p>Adverse events</p></caption>
      <table>
        <thead><tr><th>Event</th><th>N = 57 Any grade</th></tr></thead>
        <tbody><tr><td>Nausea</td><td>23 (40.4)</td></tr></tbody>
      </table>
    </table-wrap>
    """), "brentuximab_vedotin", MINE, OTHERS, tax, title_names_agent=False)
    assert not out.accepted
    assert "unidentifiable header" in out.reason


def test_strata_that_partition_a_parent_column_are_dropped(tax) -> None:
    """The subgroup rule needs the subgroup's header to extend its parent's, which fails
    when the strata are named independently: "Normal (BMI 18.5 to <25) n = 117" and
    "Obese (BMI >=30) n = 66" beside a safety population of 258 share no arm name with it.
    The registry comparison surfaced these as denominator mismatches, all smaller than the
    registry's.

    Arithmetic finds them without reading the labels. Columns whose denominators sum
    exactly to another column's are a stratification of it, and admitting them as arms
    would put correlated partial populations into one trial, which the hierarchical model
    would read as independent evidence."""
    from adctox.extract.table_to_cells import _partition_columns

    def col(c: int, n: int):
        from adctox.extract.table_to_cells import ColumnAttribution
        return ColumnAttribution(c, f"arm {c} (n = {n})", "agent", "x", n)

    # Two strata and their parent.
    assert _partition_columns([col(1, 144), col(2, 173), col(3, 317)]) == {1, 2}
    # Three strata and their parent.
    assert _partition_columns(
        [col(1, 117), col(2, 66), col(3, 75), col(4, 258)]
    ) == {1, 2, 3}


def test_a_pooled_total_that_is_not_a_sum_drops_nothing(tax) -> None:
    """The risk the arithmetic runs. Two dose arms of 40 and 60 beside a pooled column of
    120 are not a partition -- 40 + 60 is 100 -- and all three must survive. A partition
    rule that fired on "there is a bigger column" would delete real arms."""
    from adctox.extract.table_to_cells import ColumnAttribution, _partition_columns

    def col(c: int, n: int):
        return ColumnAttribution(c, f"arm {c} (n = {n})", "agent", "x", n)

    assert _partition_columns([col(1, 40), col(2, 60), col(3, 120)]) == set()
    # Fewer than three distinct denominators cannot show a partition at all.
    assert _partition_columns([col(1, 40), col(2, 60)]) == set()


def test_a_header_stating_two_denominators_is_a_subgroup_column() -> None:
    """A two-row header joining "SG (n = 243)" to "*1/*1 wild type (n = 113)" declares the
    arm and then a stratum of it in one string. The denominator parse keeps the last match,
    so the column carries 113 and the parent 243 never becomes a column -- which puts both
    the subgroup rule and the partition rule out of reach, since neither can see a parent
    that is not a column.

    Two `N =` statements in one header is the signal by itself. Found by validating against
    the registry, where three UGT1A1 genotype strata of one sacituzumab arm (113, 96 and
    34 against a registry arm of 258) each carried a header that also said 243."""
    from adctox.extract.table_to_cells import (
        ColumnAttribution,
        _nested_denominator_columns,
    )

    def col(c: int, n: int, header: str):
        return ColumnAttribution(c, header, "agent", "x", n)

    cols = [
        col(1, 113, "SG (n = 243)1 *1/*1 wild type (n = 113) All grades"),
        col(2, 96, "SG (n = 243)1 *1/*28 heterozygous (n = 96) All grades"),
        col(3, 50, "Brentuximab vedotin (n = 50) Any grade"),
    ]
    assert _nested_denominator_columns(cols) == {1, 2}


def test_a_hyphen_joined_combination_regimen_is_caught() -> None:
    """The "+"-based rule cannot see "G-atezo-pola", and only the full INN was listed, so
    "R/R FLG-atezo-pola (N = 13)" put an atezolizumab combination into the corpus as
    polatuzumab monotherapy. The short forms are how trial arm names actually write them."""
    pola = {"polatuzumab", "polatuzumab vedotin", "pola", "polivy"}
    for header in ["R/R FLG-atezo-pola(N = 13) Pola 1.8 mg(N = 10)",
                   "G-atezo-pola (n = 21)"]:
        a = attribute_column(header, 1, 20, pola, {})
        assert a.kind == "ambiguous", f"{header!r} -> {a.kind}"
        assert "atezo" in a.reason
    # And the monotherapy column of the same trial is still ours.
    assert attribute_column("Polatuzumab vedotin (n = 50)", 2, 50, pola, {}).kind == "agent"
