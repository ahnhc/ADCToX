"""A literature column is comparable to `otherEvents` only if it reports the same outcome.

ClinicalTrials.gov's `otherEvents` is any-grade, all-cause incidence. 106 of the 414
literature arms report something else and were being merged in as though they did not:

* 100 a severity-restricted tail -- "Grade >=3", "Grade 3-4" -- whose rates are five to ten
  times lower;
* 3 deaths, headed "Grade 5";
* 1 a serious-event column, which belongs to the other table;
* 2 a clinical action per organ -- "EV Dose Reduction", "Permanent Discontinuation" -- which
  is not an incidence at all.

The clearest single case: a trastuzumab deruxtecan arm reporting nausea at 1.4%, against a
median of 67% across the agent's other 79 arms. It survived every check the project had,
because 2/142 is arithmetically consistent, the row label maps cleanly, the denominator is
stated in the header, and nothing anywhere asked what the column was counting.

Found by looking for duplicate cells and noticing that the duplicates were not duplicates:
the same row and the same parent column header with two different counts, which is what a
grade-stratified table looks like once the grade is dropped from the column identity.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "merge_literature_corpus", ROOT / "scripts" / "merge_literature_corpus.py"
)
merge = importlib.util.module_from_spec(SPEC)
sys.modules["merge_literature_corpus"] = merge
SPEC.loader.exec_module(merge)

PAPER = ROOT / "data" / "processed" / "paper_arms.parquet"
FULL = ROOT / "data" / "processed" / "with_literature_final"
REGISTRY = ROOT / "data" / "processed" / "arms.parquet"


@pytest.mark.parametrize(("header", "expected"), [
    # The two pattern bugs a sweep of all 516 column headers exposed. The first version
    # caught only the severe tail, so the low grades went through untouched, and it missed
    # even some severe ones: `grade\s*` cannot cross the "s" of "Grades", and `3\b` fails
    # before the letter in "3n".
    ("Grades 3-4, n %", "grade_restricted"),
    ("Grade 3n (%)", "grade_restricted"),
    ("N = 17 Grade 1", "grade_restricted"),
    ("Grade 1-2", "grade_restricted"),
    ("N = 57 Grade 4", "grade_restricted"),
    ("HER2-low expression (n=41, %) Grade I-II", "grade_restricted"),
    # Actions, named for the category rather than one member: hospitalisation is not a dose
    # modification.
    ("Hospitalization", "clinical_action"),
    ("Temporary Hold/Delay", "clinical_action"),
    ("Systemic Corticosteroid Use Beyond Routine Premedication, n (%)", "clinical_action"),
    # A cross-tab stub and the table's own label column.
    ("Yes, n (%)", "not_an_arm"),
    ("Adverse event", "not_an_arm"),
    # And the near misses the narrow patterns must not take: these are arms.
    ("Total (N = 66)", "any_grade"),
    ("No primary prophylaxis group (n = 203)", "any_grade"),
    ("Maximum grade Grade 1", "any_grade"),
    ("Patients, n (%) All grades", "any_grade"),
    ("Overall cohort, n = 120", "any_grade"),
    ("All patients (n=28), n (%) Grade 3-4", "grade_restricted"),
    ("2.4 mg/kg Q3W (n = 16) Grade ≥3", "grade_restricted"),
    ("Depatux-m (n=323) n (%) Grade 3", "grade_restricted"),
    ("EV-301N = 296n (%) Grade 3/4", "grade_restricted"),
    ("N = 137, No. (%) Grade 5", "fatal"),
    ("Seriousness and CTCAE grade Serious neutropenia/FN", "serious"),
    ("EV Dose Reduction", "clinical_action"),
    ("Permanent Discontinuation EV", "clinical_action"),
    # A spanning header naming both ends was split upstream, so it is not restricted.
    ("All grades and grade 3-4", "any_grade"),
    # And the fatal reading wins over the grade reading when both are present, because a
    # grade-5 column is deaths however it is also described.
    ("Grade 3-5 deaths", "fatal"),
])
def test_the_classifier_names_the_outcome(header: str, expected: str) -> None:
    assert merge.column_outcome(header) == expected, header


@pytest.mark.skipif(not PAPER.exists(), reason="run `make pmc-merge`")
def test_the_counts_are_what_the_corpus_reports() -> None:
    arms = pd.read_parquet(PAPER)
    counts = arms["column_outcome"].value_counts().to_dict()
    assert counts.get("grade_restricted", 0) >= 140, counts
    assert counts.get("fatal", 0) >= 3, counts
    assert counts.get("clinical_action", 0) >= 5, counts
    assert counts.get("not_an_arm", 0) >= 3, counts
    assert sum(v for k, v in counts.items() if k != "any_grade") >= 150, counts


@pytest.mark.skipif(not REGISTRY.exists(), reason="run `make corpus`")
def test_no_registry_arm_is_reclassified() -> None:
    """A ClinicalTrials.gov event group has no outcome qualifier in its title, so this must
    change nothing about the registry corpus. If it ever does, the pattern is over-matching
    and the registry results move with it."""
    arms = pd.read_parquet(REGISTRY)
    titles = arms["title"].astype(str) if "title" in arms else arms["arm_key"].astype(str)
    offenders = [t for t in titles if merge.column_outcome(t) != "any_grade"]
    assert not offenders, offenders[:5]


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_any_grade_grid_excludes_them_and_loses_no_agent() -> None:
    """The reason this is a correction rather than a trade-off. Every agent carrying a
    non-any-grade arm also has an any-grade one, so the 32-agent count survives."""
    from adctox.model.dataset import load
    from adctox.taxonomy import default_taxonomy

    axes = list(default_taxonomy().axis_order)
    data = load(FULL, axes, kind="other")
    # 31 and not 32. naratuximab emtansine's only table splits the grade scale into
    # Grade 1-2, Grade 3 and Grade 4 columns with no any-grade column, so the agent has no
    # any-grade evidence at all. The sum of the strata would reconstruct it, and does not,
    # because the partition omits grade 5. Every other agent with a non-any-grade arm also
    # has an any-grade one.
    assert data.n_contributing_agents == 31, data.summary()
    assert data.n_arms < 500, data.summary()
    # The three mechanism folds survive, which is the thing this could have cost and did
    # not: dna_crosslink stays above the three-agent floor.
    by_mech: dict[str, set[int]] = {}
    for mi, ai in zip(data.arm_mech_idx, data.arm_agent_idx):
        by_mech.setdefault(data.mechanisms[int(mi)], set()).add(int(ai))
    viable = {m for m, a in by_mech.items() if len(a) >= 3}
    assert {"tubulin", "topo1", "dna_crosslink"} <= viable, sorted(viable)

    arms = pd.read_parquet(FULL / "arms.parquet")
    off = arms[arms["column_outcome"].fillna("any_grade") != "any_grade"]
    assert len(off) > 150
    lost = set(off["agent"].dropna()) - set(
        arms.loc[arms["column_outcome"].fillna("any_grade") == "any_grade", "agent"]
        .dropna()
    )
    assert lost == {"naratuximab_emtansine"}, sorted(lost)


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_arm_that_reported_nausea_at_one_percent_is_gone() -> None:
    """The case this started from, pinned by name."""
    import numpy as np

    from adctox.model.dataset import load
    from adctox.taxonomy import default_taxonomy

    axes = list(default_taxonomy().axis_order)
    data = load(FULL, axes, kind="other")
    gi = axes.index("gastrointestinal")
    arms = pd.read_parquet(FULL / "arms.parquet")
    key_to_pos = {k: i for i, k in enumerate(data.arm_keys)}
    bad = [
        key_to_pos[k] for k in arms.loc[
            arms["arm_key"].astype(str).str.contains("13187561", na=False), "arm_key"
        ] if k in key_to_pos
    ]
    cells = np.flatnonzero(
        (data.axis_idx == gi) & np.isin(data.arm_idx, bad)
    )
    assert cells.size == 0, (
        "the grade-3-only trastuzumab deruxtecan arm is still contributing an any-grade "
        "gastrointestinal rate of 1.4%"
    )


@pytest.mark.parametrize(("header", "is_class"), [
    ("Novel anti-HER2 ADCs (n = 73) Any grade", True),
    ("antibody-drug conjugates (n=50)", True),
    ("Other agents (n=12)", True),
    # Pooling cohorts of one agent is a legitimate arm; `pooled` alone is not a signal.
    ("Pooled RDE 5.6 mg/kg (n = 57), n (%)", False),
    # A singular "ADC" is how a paper refers to the one it is about.
    ("T-DXd ADC (n=40)", False),
    ("Patients, n (%) All grades", False),
    ("EV-301N = 296n (%)", False),
])
def test_a_class_of_agents_is_not_an_agent(header: str, is_class: bool) -> None:
    """The failure the title gate cannot see.

    "Novel anti-HER2 ADCs (n = 73)" is the comparator arm of a paper about trastuzumab
    emtansine, and every check passed: the title names the agent, no other ADC appears by
    name anywhere in the table, the column has its own denominator, and the arithmetic is
    consistent. 22 cells were attributed to trastuzumab emtansine, 11 of them any-grade and
    in the corpus. This is the 75%-false-positive attribution trap arriving through a door
    the project had already locked twice.

    The plural is what carries the meaning, and it has to be a plural of *agents*.
    """
    assert merge.names_an_agent_class(header) is is_class, header


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_pooled_class_arm_is_out_of_both_grids() -> None:
    """Attribution, not outcome, so it applies to the serious table too."""
    import numpy as np

    from adctox.model.dataset import load
    from adctox.taxonomy import default_taxonomy

    arms = pd.read_parquet(FULL / "arms.parquet")
    flagged = arms[arms["agent_class_column"].fillna(False).astype(bool)]
    assert len(flagged) >= 1, "nothing is flagged, so this test proves nothing"
    assert all("10546815" in str(k) for k in flagged["arm_key"]), (
        flagged["arm_key"].tolist()
    )

    axes = list(default_taxonomy().axis_order)
    for kind in ("other", "serious"):
        data = load(FULL, axes, kind=kind)
        pos = {k: i for i, k in enumerate(data.arm_keys)}
        bad = [pos[k] for k in flagged["arm_key"] if k in pos]
        assert not np.isin(data.arm_idx, bad).any(), (
            f"a class-pooling column still contributes to the {kind} grid"
        )


def test_a_grade_in_the_row_label_decides_almost_nothing() -> None:
    """The same defect one level down, bounded instead of filtered.

    A grade restriction usually sits in the column header, which the outcome classifier
    handles. It can also sit in the row: "CRS, grade >=3", "Keratopathy, grade 3-4". 14 cells
    carry one. The merge takes the maximum count across an axis's rows -- matching the
    registry, which stores an axis as "any event in this organ" -- so such a row is
    harmlessly dominated whenever the same axis has an any-grade row with a larger count.

    The exposure is the remainder, and it is 6 of 2,696 observations, with the worst
    understatement 20% (a maximum of 20 against a row sum of 24). A row-level filter would
    cost more than it fixes: dropping "Keratopathy, grade 2" where it is the only keratopathy
    row would discard a real signal from the agent that axis is named for, which has 124
    observations on it.

    So the bound is held rather than the rows removed, and a corpus change that makes this
    worse fails here instead of passing quietly.
    """
    import json

    artefact = ROOT / "artifacts" / "row_grade_exposure.json"
    if not artefact.exists():
        pytest.skip("run `make row-grade-exposure`")
    summary = json.loads(artefact.read_text(encoding="utf-8"))["summary"]
    assert summary["observations"] > 2000, summary
    assert summary["share"] < summary["bound_the_test_holds"], summary
    # And the thing it bounds has to still exist, or the bound is vacuous.
    assert summary["cells_with_a_grade_in_the_row_label"] > 0, summary


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_severe_tail_becomes_its_own_table_and_cannot_carry_the_model() -> None:
    """The set-aside data, labelled rather than discarded, and measured rather than fitted.

    112 of the 142 grade-restricted columns report grade 3 and above, which is the threshold
    clinical practice acts on, so they become `kind="grade3"`. The table is literature-only
    -- the registry has no grade split at all -- which makes it the clean form of the
    question the corpus ablation asks: can literature arms support a model with no registry
    arms mixed in to carry them?

    No. It reaches 21 agents, more than the registry's 16, at 1.55 observed cells per
    identifying cell against the any-grade table's 9.97 and the 8:1 floor the plan set. More
    agents, each contributing four or five observed axes instead of nine, because a grade >=3
    table lists only the organs that reached grade 3. The mirror image of section 5g: there,
    more arms bought no agents; here, more agents buy no observations.
    """
    from adctox.model.dataset import load
    from adctox.taxonomy import default_taxonomy

    axes = list(default_taxonomy().axis_order)
    g3 = load(FULL, axes, kind="grade3")
    other = load(FULL, axes, kind="other")

    # The table exists and is not trivial.
    assert g3.n_contributing_agents >= 20, g3.summary()
    assert g3.n_arms >= 80, g3.summary()
    # And it has more agents than the registry while being far thinner per agent.
    g3_obs = int((g3.status == 0).sum())
    other_obs = int((other.status == 0).sum())
    g3_ratio = g3_obs / (g3.n_contributing_agents * len(axes))
    other_ratio = other_obs / (other.n_contributing_agents * len(axes))
    assert g3_ratio < 3.0, g3_ratio
    assert other_ratio > 8.0, other_ratio
    # The low-grade remainder stays out of every table: a rate restricted to the mild end is
    # not an outcome anything would act on.
    arms = pd.read_parquet(FULL / "arms.parquet")
    low = arms[
        (arms["column_outcome"] == "grade_restricted")
        & arms["n_at_risk_grade3"].isna()
        & arms["source"].notna()
    ]
    assert len(low) >= 25, len(low)
