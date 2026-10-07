"""Taxonomy tests, each pinned to a bug or a measured property of the real corpus."""

from __future__ import annotations

import math

import pytest

from adctox.taxonomy import (
    AXIS_DROPPED,
    AXIS_EXCLUDED,
    AXIS_UNMAPPED,
    Taxonomy,
    build_pt_dictionary,
    normalize_text,
    parse_frequency_threshold,
)


@pytest.fixture(scope="module")
def tax() -> Taxonomy:
    return Taxonomy()


def test_fourteen_axes(tax: Taxonomy) -> None:
    assert len(tax.axes) == 14
    assert len(set(tax.axis_order)) == 14


def test_soc_names_survive_yaml_flow_sequences(tax: Taxonomy) -> None:
    """Regression: an unquoted YAML `[a, b]` split a SOC name on its internal comma.

    "Respiratory, thoracic and mediastinal disorders" became "respiratory" plus
    "thoracic and mediastinal disorders", so the pulmonary axis silently matched nothing
    and lost all 4,963 of its events without raising.
    """
    assert tax.soc_axis("Respiratory, thoracic and mediastinal disorders") == "pulmonary"
    assert tax.soc_axis("Neoplasms benign, malignant and unspecified (incl cysts and polyps)") == AXIS_EXCLUDED
    assert all(len(s) >= 12 for s in tax.canonical_socs if s)


def test_allcaps_and_whitespace_variants_normalize(tax: Taxonomy) -> None:
    """Measured in the corpus: 22 ALL-CAPS SOC renderings alongside title case."""
    for variant in (
        "INFECTIONS AND INFESTATIONS",
        "Infections and infestations",
        "  infections   and infestations  ",
    ):
        assert tax.soc_axis(variant) == "infectious_immune"


def test_general_disorders_alias_pair_merges(tax: Taxonomy) -> None:
    """Both renderings occur (6,303 vs 78 events) and are the same SOC."""
    assert tax.soc_axis("General disorders") == "constitutional"
    assert tax.soc_axis("General disorders and administration site conditions") == "constitutional"


def test_investigations_redistributed_not_dropped(tax: Taxonomy) -> None:
    """Investigations is organ signal under a lab-test label, not a throwaway SOC."""
    cases = {
        "Alanine aminotransferase increased": "hepatic",
        "Neutrophil count decreased": "haematologic",
        "Platelet count decreased": "haematologic",
        "Blood creatinine increased": "renal",
        "Ejection fraction decreased": "cardiovascular",
        "Lipase increased": "gastrointestinal",
        "Weight decreased": "constitutional",
        "Blood thyroid stimulating hormone increased": "metabolic_endocrine",
    }
    for term, expected in cases.items():
        assert tax.resolve(term, "Investigations")[0] == expected, term


def test_ctcae_era_bare_terms_map(tax: Taxonomy) -> None:
    """CTCAE v2/v3 reported bare cell names; these carried 2,543 haematologic events
    that MedDRA-shaped patterns alone missed."""
    for term in (
        "Platelets",
        "Neutrophils/granulocytes (ANC/AGC)",
        "Leukocytes (total WBC)",
        "Lymphopenia",
    ):
        assert tax.resolve(term, "Investigations")[0] == "haematologic", term


def test_source_typos_still_map(tax: Taxonomy) -> None:
    """These spellings are verbatim in ClinicalTrials.gov, not our own transcription."""
    assert tax.resolve("Alanine aminotranseferase increased", "Investigations")[0] == "hepatic"
    assert tax.resolve("Gamma- glutamyltranseferase increased", "Investigations")[0] == "hepatic"
    assert tax.resolve("Gamma-glutamyl transferase increased", "Investigations")[0] == "hepatic"


def test_soc_gates_the_term(tax: Taxonomy) -> None:
    """An Investigations rule must not fire on a term that already has a real SOC.

    Without the gate, the renal pattern would steal "Blood creatinine increased" from
    whatever SOC the source filed it under.
    """
    axis, prov = tax.resolve("Blood creatinine increased", "Renal and urinary disorders")
    assert axis == "renal"
    assert prov.startswith("soc:")


def test_aggregate_rows_dropped_not_assigned(tax: Taxonomy) -> None:
    for term in ("Investigations - Other, specify", "Metabolic/Laboratory-Other"):
        assert tax.resolve(term, "Investigations")[0] == AXIS_DROPPED, term


def test_unknown_soc_is_unmapped_not_silently_binned(tax: Taxonomy) -> None:
    axis, prov = tax.resolve("Some term", "Entirely Invented Disorders")
    assert axis == AXIS_UNMAPPED
    assert "unknown_soc" in prov


def test_pt_dictionary_fallback_does_not_recurse(tax: Taxonomy) -> None:
    """Regression: the dictionary fallback recursed until the stack overflowed when it
    returned a SOC the config also did not know."""
    doc = build_pt_dictionary([("Mystery event", "Still Unknown Disorders")] * 3)
    import json
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "d.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        t = Taxonomy()
        t.load_pt_dictionary(p)
        axis, _ = t.resolve("Mystery event", "Also Unknown Disorders")
        assert axis == AXIS_UNMAPPED


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5", 5.0), ("5.0", 5.0), ("5.00", 5.0), ("4.98", 4.98), ("4.9", 4.9),
        ("0", 0.0), ("1", 1.0), (" 5 ", 5.0), ("5%", 5.0), (5, 5.0), (None, None),
        ("", None), ("not a number", None),
    ],
)
def test_frequency_threshold_formats(raw, expected) -> None:
    """All of these string forms occur in the corpus. Treating '5' and '5.0' as
    different values is a silent correctness bug."""
    got = parse_frequency_threshold(raw)
    if expected is None:
        assert got is None
    else:
        assert got is not None and math.isclose(got, expected)


def test_normalize_text_is_idempotent() -> None:
    for s in ("Fatigue", "  FATIGUE. ", "Fatigué"):
        once = normalize_text(s)
        assert normalize_text(once) == once


def test_pt_dictionary_majority_vote_records_contest() -> None:
    records = [("Rash", "Skin and subcutaneous tissue disorders")] * 7
    records += [("Rash", "Immune system disorders")] * 3
    doc = build_pt_dictionary(records)
    entry = doc["terms"]["Rash"]
    assert entry["soc"] == "skin and subcutaneous tissue disorders"
    assert entry["n"] == 10
    assert math.isclose(entry["majority_share"], 0.7)
    # The losing votes are kept so a contested term can be audited, not hidden.
    assert entry["votes"]["immune system disorders"] == 3
