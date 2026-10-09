"""Tests for paper row-label resolution.

The asymmetry that shapes these tests: a dictionary miss loses one row, while an aggregate
row misread as an organ row corrupts an axis. "Any treatment-emergent adverse event" sits
at 90-100% in nearly every ADC table, so if it landed on an axis it would outweigh every
real row in that table and the resulting rate would look like a catastrophic organ
toxicity. So the aggregate tests are exhaustive over the forms seen in practice, while the
rewrite tests only have to show the rules fire.
"""

from __future__ import annotations

import pathlib

import pytest

from adctox.extract.row_labels import (
    classify,
    map_row,
    rewrite_candidates,
    strip_decoration,
)
from adctox.taxonomy import AXIS_UNMAPPED, default_taxonomy

PT_DICT = pathlib.Path("data/processed/pt_soc_dictionary.json")


@pytest.fixture(scope="module")
def tax():
    t = default_taxonomy()
    t.load_pt_dictionary(PT_DICT)
    return t


AGGREGATE_LABELS = [
    "Any treatment-emergent adverse event",
    "Any TEAE",
    "Any grade ≥3 adverse event",
    "All adverse events",
    "Overall",
    "Total",
    "Treatment-related adverse events",
    "Drug-related AEs",
    "Serious adverse events",
    "Serious TEAEs",
    "At least one adverse event",
    "≥1 treatment-emergent adverse event",
    "Adverse events leading to discontinuation",
    "TEAEs leading to dose reduction",
    "AEs resulting in death",
    "Any event leading to treatment discontinuation",
    "Dose reduction",
    "Dose interruptions",
    "Treatment discontinuation",
    "Death",
    "Patients with at least one TEAE",
    "Number of patients with any adverse event",
    "TEAEs of special interest",
    "Grade 3 adverse events",
    "Adverse events of any grade",
]


@pytest.mark.parametrize("label", AGGREGATE_LABELS)
def test_an_aggregate_row_never_reaches_an_axis(label: str, tax) -> None:
    """The load-bearing test. These rows carry the table's largest counts; one of them
    assigned to an organ would dominate that axis and read as a catastrophic toxicity."""
    row = map_row(label, tax)
    assert row.kind == "aggregate", f"{label!r} classified as {row.kind}"
    assert row.axis == AXIS_UNMAPPED


ORGAN_LABELS = [
    ("Nausea", "gastrointestinal"),
    ("Vomiting", "gastrointestinal"),
    ("Neutropenia", "haematologic"),
    ("Anaemia", "haematologic"),
    ("Thrombocytopenia", "haematologic"),
    ("Peripheral sensory neuropathy", "neurologic"),
    ("Interstitial lung disease", "pulmonary"),
    ("Pneumonitis", "pulmonary"),
    ("Keratopathy", "ocular"),
    ("Alopecia", "dermatologic"),
    ("Fatigue", "constitutional"),
]


@pytest.mark.parametrize("label,axis", ORGAN_LABELS)
def test_a_plain_organ_term_resolves_verbatim(label: str, axis: str, tax) -> None:
    """These must not need a rewrite. A rule firing on a label the dictionary already
    knows would mean the rewrite order is wrong, and a wrong rewrite can change the axis."""
    row = map_row(label, tax)
    assert row.kind == "pt"
    assert row.axis == axis, f"{label} -> {row.axis} via {row.provenance}"
    assert row.provenance.startswith("verbatim:")


REWRITES = [
    ("Increased ALT", "hepatic"),
    ("Elevated alanine aminotransferase", "hepatic"),
    ("Decreased neutrophil count", "haematologic"),
    ("Febrile neutropaenia", "haematologic"),
    ("Leucopenia", "haematologic"),
    ("Hypokalaemia", "metabolic_endocrine"),
    ("Diarrhoea", "gastrointestinal"),
]


@pytest.mark.parametrize("label,axis", REWRITES)
def test_a_clerical_rewrite_recovers_the_term(label: str, axis: str, tax) -> None:
    """The plan measured 23% of unmapped labels as recoverable this way. Each of these is a
    spelling, an abbreviation or a word order -- never a clinical inference."""
    row = map_row(label, tax)
    assert row.axis == axis, f"{label} -> {row.axis} via {row.provenance}"


def test_decoration_is_stripped_without_touching_the_term() -> None:
    assert strip_decoration("Anaemia*") == "Anaemia"
    assert strip_decoration("Interstitial lung disease¹") == "Interstitial lung disease"
    assert strip_decoration("Neutropenia, grade ≥3") == "Neutropenia"
    assert strip_decoration("Diarrhoea, any grade") == "Diarrhoea"
    assert strip_decoration("Nausea†,") == "Nausea"
    assert strip_decoration("Fatigue (all grades)") == "Fatigue"
    # A parenthesis that is part of the term must survive.
    assert "ALT" in strip_decoration("Increased ALT (SGPT)†")


def test_a_soc_header_is_used_directly_and_not_read_as_an_aggregate() -> None:
    """Several canonical SOC names start with a word the aggregate pattern claims, so the
    header check runs first. "General disorders and administration site conditions" is the
    case that forced the ordering."""
    t = default_taxonomy()
    t.load_pt_dictionary(PT_DICT)
    for soc in sorted(t.canonical_socs):
        row = map_row(soc, t)
        assert row.kind == "soc_header", f"{soc!r} classified as {row.kind}"


def test_the_most_faithful_spelling_is_tried_first() -> None:
    """A rewrite must never pre-empt the printed term, because the rewrites are lossy:
    "low" becomes "decreased", and a term containing "low" for another reason would be
    mangled. The verbatim label is always candidate zero."""
    cands = rewrite_candidates("Increased ALT")
    assert cands[0] == "Increased ALT"
    assert "ALT increased" in cands
    assert any("alanine aminotransferase" in c.lower() for c in cands)


def test_an_unknown_term_is_declined_rather_than_guessed() -> None:
    t = default_taxonomy()
    t.load_pt_dictionary(PT_DICT)
    row = map_row("Bartholin's cyst removal", t)
    assert row.axis == AXIS_UNMAPPED
    assert row.provenance == "pt_dict_miss"
    # Still classified as a PT attempt, so it lands in the residual count rather than
    # being silently absorbed into the aggregate bucket.
    assert row.kind == "pt"


def test_an_empty_or_decoration_only_label_is_other() -> None:
    t = default_taxonomy()
    t.load_pt_dictionary(PT_DICT)
    for label in ["", "   ", "*", "†"]:
        row = map_row(label, t)
        assert row.kind == "other"
        assert row.axis == AXIS_UNMAPPED


def test_classify_agrees_with_map_row_on_the_aggregate_question() -> None:
    """`classify` is the cheap text-only path used when no taxonomy is loaded. If the two
    disagreed, a caller choosing the cheap path would admit aggregate rows."""
    t = default_taxonomy()
    t.load_pt_dictionary(PT_DICT)
    for label in AGGREGATE_LABELS:
        assert classify(label) == "aggregate"
    for label, _ in ORGAN_LABELS + REWRITES:
        assert classify(label) == "pt", label
