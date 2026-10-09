"""Two DAR values the registry said did not exist, and the reading that hid them.

Twelve of the registry's 34 conventional conjugates had no drug-to-antibody ratio, which is
what caps the comparator's reference set. The question was whether the 1,496 open-access
articles already on disk state it, and a previous pass answered no for tusamitamab
ravtansine in those words: "102 DAR mentions in the fetched corpus and none states a figure
for this agent".

The figure is there. Its population-pharmacokinetic paper says "an average DAR of 3.8",
three times -- and the same paper labels its conjugate species `DAR0` through `DAR8`, which
outnumber the real statement seven to one and sit beside the agent's name in the same
sentences. Read naively those give the agent a DAR of 0, 1 or 8.

Three readings have to be told apart, and all three tests here are about the separation
rather than about the search:

* an average statement, which is what a registry field wants;
* a species label, which describes a mixture;
* an unqualified `DARn`, which is how a review tabulates the nominal value and also how a
  PK paper names a species -- so it needs the other signals.

And a fourth guard, from the extraction pipeline: the article has to be *about* the agent.
PMC12146481 is a preclinical paper on mecbotamab vedotin that mentions enapotamab vedotin in
its introduction with "DAR4" attached. That is not enapotamab vedotin's primary report, and
the loose version of this test is what turned 13 attributable agents into 52.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dar_gap", ROOT / "scripts" / "dar_gap.py"
)
dar_gap = importlib.util.module_from_spec(SPEC)
sys.modules["dar_gap"] = dar_gap
SPEC.loader.exec_module(dar_gap)


def _reading(fragment: str, lookback: str) -> str:
    """The classifier, applied the way the script applies it."""
    if dar_gap.AVERAGE.search(lookback) and not dar_gap.BARE.match(fragment):
        return "average"
    if dar_gap.BARE.match(fragment):
        return "bare"
    return "unqualified"


def test_an_average_statement_is_recognised() -> None:
    assert _reading("DAR of 3.8", "bound to the antibody, with an average ") == "average"


def test_a_species_label_is_not_an_average_statement() -> None:
    """The exact sentence that defeated the first version. `average` appears thirty
    characters ahead of two species labels, so a window-wide test called both of them
    average statements and the agent's three "average" matches then disagreed."""
    sentence = (
        "The maximum average DAR reduces slightly from 3.3 to 2.8 after repeated doses "
        "due to the accumulation of DAR0 and DAR1."
    )
    start = sentence.index("DAR0")
    lookback = sentence[max(0, start - dar_gap.LOOKBACK):start]
    assert _reading("DAR0", lookback) == "bare"


def test_the_species_gloss_and_not_a_sentence_span_does_the_work() -> None:
    """A dedicated span pattern was tried and dropped.

    `DAR1 ... to DAR8` looks like something a regex can bracket, but the sentence it was
    written for is "species from DAR1 (i.e. ADC with one DM4 molecule) to DAR8", and `i.e.`
    ends in a dot before a space exactly as a sentence does. Every variant either stopped at
    the abbreviation or ran past real sentence breaks, so the check never fired on its own
    motivating example -- and a guard that silently does nothing is worse than none. The
    gloss decides it on the words instead.
    """
    assert not hasattr(dar_gap, "SPECIES_SPAN")
    assert dar_gap.SPECIES_GLOSS.search(
        "species from DAR1 (i.e. ADC with one DM4 molecule) to DAR8"
    )
    assert not dar_gap.SPECIES_GLOSS.search(
        "conjugated via a cleavable linker with a drug-to-antibody ratio of 8"
    )


def test_the_pattern_finds_the_figure_it_is_for() -> None:
    m = dar_gap.DAR.search(
        "a potent topoisomerase I inhibitor with a drug-to-antibody ratio of 8."
    )
    assert m and float(m.group(1)) == 8.0


def test_the_registry_carries_both_recovered_values_with_their_source() -> None:
    """The outcome, pinned. A value without a citable source is not an improvement on null.
    """
    doc = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    for key, dar, pmcid in (
        ("tusamitamab_ravtansine", 3.8, "PMC9098589"),
        ("izalontamab_brengitecan", 8.0, "PMC13011950"),
    ):
        spec = doc[key]
        assert spec["dar"] == pytest.approx(dar), (key, spec["dar"])
        assert spec["dar_source"] == f"pmc:{pmcid}", (key, spec["dar_source"])
        assert spec["dar_note"], key


def test_the_agent_whose_only_source_is_another_drug_s_paper_stays_null() -> None:
    """enapotamab vedotin's DAR4 comes from a paper about mecbotamab vedotin. The number is
    probably right; it is not the agent's own primary report, and this project's attribution
    standard is the reason the discovery sweep found 32 agents rather than 52."""
    doc = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    assert doc["enapotamab_vedotin"]["dar"] is None
