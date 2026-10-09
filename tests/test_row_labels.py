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


NOT_EVENTS = [
    # Bare values and punctuation, from tables whose stub column is not an event name.
    "1", "2", "0", "3", "+", "−", "–", "≥ 75",
    # Presence/absence and missingness.
    "Yes", "No", "None", "Other", "Unknown", "Missing", "Unknown/missing", "N/A",
    # Grade labels in every form the corpus uses, including the glyph that is not U+2265.
    "Grade 0", "Grade 3", "Grade ≥3", "⩾Grade 3", "Grade 1–2",
    "G1", "G4", "G I–II", "G III–IV",
    # Severity strata.
    "Mild", "Moderate", "Severe",
    # Statistics and analysis rows.
    "Median (range)", "Mean (SD)", "Logistic regression (AEs)",
    # Demographics and performance status.
    "Female", "Male", "White", "Asian", "ECOG PS", "Normal",
    # Attribution and prior therapy.
    "Drug-related", "Related to study treatment", "Related to any study treatment",
    "Chemotherapy", "Palliative systemic therapy", "Non-hematological",
    # Disease sites, which appear as strata in cross-tabs.
    "Bone", "Liver", "Brain",
    # Operational rows.
    "Treatment interruption", "Treatment delays",
]


@pytest.mark.parametrize("label", NOT_EVENTS)
def test_a_label_that_is_not_an_event_is_not_a_dictionary_miss(label: str, tax) -> None:
    """Measured on 4,378 rows from denominator-bearing AE tables: labels like these were
    being classified as preferred terms and counted as dictionary misses, which made the
    mapping rate look like a vocabulary problem and would have sent the next round of work
    hunting for terms that do not exist. A table's stub column is not always an event name
    -- cross-tabs, over-caught baseline tables and grade-stratified blocks all put
    something else there. Separating them moved the measured mapping rate from 40.7% to
    53.7%, against the plan's 50.5%, without a single new dictionary entry."""
    row = map_row(label, tax)
    assert row.kind == "not_an_event", f"{label!r} classified as {row.kind}"
    assert row.axis == AXIS_UNMAPPED


def test_a_grade_stratum_is_dropped_whichever_bucket_claims_it(tax) -> None:
    """"Any grade" and "All grades" are claimed by the aggregate pattern before the
    not-an-event one gets to them. The bucket differs; the two properties that matter do
    not -- the row never reaches an axis and is never counted as a dictionary miss."""
    for label in ["Any grade", "All grades", "Any-grade", "All grade"]:
        row = map_row(label, tax)
        assert row.kind in ("aggregate", "not_an_event"), f"{label!r} -> {row.kind}"
        assert row.axis == AXIS_UNMAPPED


def test_a_real_event_is_not_swept_up_by_the_not_an_event_patterns(tax) -> None:
    """The patterns are broad, so the risk runs the other way. These must survive."""
    for label, axis in [
        ("Nausea", "gastrointestinal"),
        ("Neutropenia", "haematologic"),
        ("Febrile neutropenia", "haematologic"),
        ("Interstitial lung disease", "pulmonary"),
        ("Keratopathy", "ocular"),
        ("Peripheral sensory neuropathy", "neurologic"),
        ("Alopecia", "dermatologic"),
    ]:
        row = map_row(label, tax)
        assert row.kind == "pt", f"{label} classified as {row.kind}"
        assert row.axis == axis


def test_a_soc_abbreviation_and_an_oxford_comma_both_resolve(tax) -> None:
    """Two clerical SOC failures from the residual. "GI disorders" is an abbreviation, and
    "Respiratory, thoracic, and mediastinal disorders" is correctly spelled apart from a
    comma MedDRA does not use -- so an exact match fails on a perfectly good header."""
    gi = map_row("GI disorders", tax)
    assert gi.kind == "soc_header" and gi.axis == "gastrointestinal"
    oxford = map_row("Respiratory, thoracic, and mediastinal disorders", tax)
    assert oxford.kind == "soc_header" and oxford.axis == "pulmonary"


def test_an_event_abbreviation_expands(tax) -> None:
    for label, axis in [("ILD", "pulmonary"), ("AKI", "renal")]:
        assert map_row(label, tax).axis == axis, label


def test_a_plural_and_a_compound_label_resolve(tax) -> None:
    """Papers pluralise and MedDRA does not, and an author writing "a/b" means the two are
    the same thing -- so either side places the axis."""
    assert map_row("Oral mucositis/stomatitis", tax).axis == "gastrointestinal"
    assert map_row("ALT/AST increased", tax).axis == "hepatic"
