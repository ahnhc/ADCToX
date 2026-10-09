"""Tests for trial identification and duplicate-source handling.

The failure this prevents is not a wrong number, it is a wrong *weight*. Four of the first
eight articles fetched report NCT03589469, and the registry already holds a fifth record of
the same patients. Admitting all five gives that trial five times its weight, and the
hierarchical model cannot repair it -- the duplicates are the same arm with correlated
counts, so their agreement reads as precision.
"""

from __future__ import annotations

import textwrap

from lxml import etree

from adctox.extract.trial_dedup import group_sources, primary_trial, trial_ids


def _article(xml: str):
    return etree.fromstring(textwrap.dedent(xml).strip().encode("utf-8"))


XLINK = 'xmlns:xlink="http://www.w3.org/1999/xlink"'


def test_a_primary_report_resolves_to_its_registration_link() -> None:
    root = _article(f"""
    <article {XLINK}>
      <front><article-meta><title-group><article-title>LOTIS-2</article-title>
      </title-group></article-meta></front>
      <body><p>This trial is registered as
        <ext-link ext-link-type="clintrialgov" xlink:href="NCT03589469">NCT03589469</ext-link>.
      </p></body>
    </article>
    """)
    nct, why = primary_trial(trial_ids(root))
    assert nct == "NCT03589469"
    assert why == "ext_link"


def test_a_pooled_analysis_is_flagged_rather_than_assigned() -> None:
    """Three trials pooled into one correlative analysis. Assigning its tables to any one
    of them would attribute other trials' patients to that trial's arm."""
    links = "".join(
        f'<ext-link xlink:href="{n}">{n}</ext-link>'
        for n in ("NCT02348216", "NCT02669017", "NCT03589469")
    )
    root = _article(f"<article {XLINK}><body><p>Pooled from {links}.</p></body></article>")
    nct, why = primary_trial(trial_ids(root))
    assert nct is None
    assert why == "ext_link_names_3_trials"


def test_a_cited_trial_does_not_make_a_paper_look_pooled() -> None:
    """A reference-list id belongs to somebody else's trial. Counting it would turn every
    primary report with a comparison in its discussion into an unassignable pooled one."""
    root = _article(f"""
    <article {XLINK}>
      <body><p>Registered as
        <ext-link xlink:href="NCT03589469">NCT03589469</ext-link>.</p></body>
      <back><ref-list><ref><element-citation>
        <ext-link xlink:href="NCT01234567">NCT01234567</ext-link>
      </element-citation></ref></ref-list></back>
    </article>
    """)
    loc = trial_ids(root)
    assert loc["ext_link"] == ["NCT03589469"]
    assert loc["citation"] == ["NCT01234567"]
    nct, _ = primary_trial(loc)
    assert nct == "NCT03589469"


def test_a_paper_with_no_trial_id_is_declined() -> None:
    root = _article(f"<article {XLINK}><body><p>A case report.</p></body></article>")
    nct, why = primary_trial(trial_ids(root))
    assert nct is None and why == "no_trial_id"


SOURCES = [
    {"pmcid": "10431093", "agent": "lonca", "nct_id": "NCT03589469",
     "max_denominator": 145, "n_cells": 20},
    {"pmcid": "10787240", "agent": "lonca", "nct_id": "NCT03589469",
     "max_denominator": 145, "n_cells": 31},
    {"pmcid": "10985439", "agent": "lonca", "nct_id": "NCT03589469",
     "max_denominator": 145, "n_cells": 12},
    {"pmcid": "11443381", "agent": "lonca", "nct_id": "NCT05053659",
     "max_denominator": 60, "n_cells": 8},
    {"pmcid": "11480243", "agent": "lonca", "nct_id": None,
     "max_denominator": 1, "n_cells": 3},
]


def test_three_reports_of_one_trial_collapse_to_one_source() -> None:
    groups, unresolved = group_sources(SOURCES, registry_ncts=set())
    lotis = [g for g in groups if g.nct_id == "NCT03589469"]
    assert len(lotis) == 1
    assert len(lotis[0].candidates) == 3
    # Equal denominators, so the cell count breaks the tie.
    assert lotis[0].chosen_pmcid == "10787240"
    assert "3 sources" in lotis[0].reason
    assert [u["pmcid"] for u in unresolved] == ["11480243"]


def test_the_largest_denominator_wins_before_the_cell_count() -> None:
    """Largest N is the fullest safety population, which is the closest available thing to
    the trial's complete record. A paper reporting more rows of a smaller subgroup is not a
    better source for the arm."""
    sources = [
        {"pmcid": "1", "agent": "a", "nct_id": "NCT1", "max_denominator": 145,
         "n_cells": 5},
        {"pmcid": "2", "agent": "a", "nct_id": "NCT1", "max_denominator": 70,
         "n_cells": 40},
    ]
    groups, _ = group_sources(sources, registry_ncts=set())
    assert groups[0].chosen_pmcid == "1"


def test_the_choice_is_deterministic_under_a_full_tie() -> None:
    """A non-deterministic choice would make the corpus unreproducible, and the tie-break
    must not depend on the order the directory happened to list files in."""
    tied = [
        {"pmcid": "900", "agent": "a", "nct_id": "NCT1", "max_denominator": 50,
         "n_cells": 5},
        {"pmcid": "100", "agent": "a", "nct_id": "NCT1", "max_denominator": 50,
         "n_cells": 5},
    ]
    first, _ = group_sources(tied, registry_ncts=set())
    second, _ = group_sources(list(reversed(tied)), registry_ncts=set())
    assert first[0].chosen_pmcid == second[0].chosen_pmcid == "100"


def test_registry_overlap_is_reported_and_not_acted_on() -> None:
    """The same overlap is the point of a validation corpus and a duplicate in an expansion
    corpus, so the module reports it and the caller decides. Every one of the 18 registry
    agents already has ClinicalTrials.gov arms, which is what makes this run a validation
    set rather than an expansion."""
    groups, _ = group_sources(SOURCES, registry_ncts={"NCT03589469"})
    by_nct = {g.nct_id: g for g in groups}
    assert by_nct["NCT03589469"].overlaps_registry
    assert not by_nct["NCT05053659"].overlaps_registry
    # Reported, not dropped.
    assert by_nct["NCT03589469"].chosen_pmcid is not None


def test_two_agents_in_one_trial_are_separate_groups() -> None:
    """A head-to-head trial legitimately contributes an arm for each agent, so the key is
    (trial, agent) rather than the trial alone."""
    sources = [
        {"pmcid": "1", "agent": "t_dxd", "nct_id": "NCT03529110",
         "max_denominator": 257, "n_cells": 20},
        {"pmcid": "1", "agent": "t_dm1", "nct_id": "NCT03529110",
         "max_denominator": 261, "n_cells": 20},
    ]
    groups, _ = group_sources(sources, registry_ncts=set())
    assert len(groups) == 2
    assert {g.agent for g in groups} == {"t_dxd", "t_dm1"}
