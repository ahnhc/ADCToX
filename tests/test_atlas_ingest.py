"""The teammate-supplied database, and the two things that nearly went wrong ingesting it.

The first was a filter. "A row is usable if it has a numerator, a denominator and a
percentage" discarded 1,748 of 6,181 organ-specific any-grade rows -- 28% -- and among them
every one of the 883 regulatory-label rows, because a label table prints a percentage and a
denominator and no numerator. Usability and verifiability are different questions and the
first version asked only the second.

The second was counting. Their `Payload` field holds 33 distinct strings for 19 payloads:
five spellings of calicheamicin, seven of the tesirine/PBD/SG3199 family. Counting strings
would have inflated the payload vocabulary by 70% and manufactured a confirmation of
negative result 6, which is a claim about exactly that vocabulary's growth rate.

Skipped rather than failed where the workbook is absent: it is not redistributed, so a clean
clone does not have it.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "data" / "raw" / "atlas" / "2026-10-10" / "adc_db.xlsx"
INGEST = ROOT / "artifacts" / "atlas_ingest.json"
SCALE = ROOT / "artifacts" / "merged_corpus_scale.json"
DOMAINS = ROOT / "conf" / "ontology" / "atlas_domains.yaml"
SLOTS = ROOT / "conf" / "ontology" / "atlas_design_slots.yaml"


def _axes() -> set[str]:
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from adctox.taxonomy import Taxonomy
    return set(Taxonomy().axis_order)


def test_the_domain_crosswalk_targets_only_this_projects_axes() -> None:
    doc = yaml.safe_load(DOMAINS.read_text(encoding="utf-8"))
    unknown = set(doc["axis_of_domain"].values()) - _axes()
    assert not unknown, unknown


def test_every_dropped_domain_states_a_reason() -> None:
    """A domain that falls out of the corpus without a reason is invisible."""
    doc = yaml.safe_load(DOMAINS.read_text(encoding="utf-8"))
    for label, entry in (doc.get("dropped") or {}).items():
        assert entry.get("reason", "").strip(), label
        assert isinstance(entry.get("rows"), int), label


def test_the_crosswalk_covers_every_axis() -> None:
    """Not a requirement in principle, but true here, and a regression if it stops being.

    If a future edit leaves an axis with no source domain, that axis silently gets no cells
    from this corpus -- which is what happened to otologic for a different reason, and was
    only noticed by counting.
    """
    doc = yaml.safe_load(DOMAINS.read_text(encoding="utf-8"))
    assert set(doc["axis_of_domain"].values()) == _axes()


def test_payload_strings_collapse_and_every_identity_has_a_mechanism() -> None:
    doc = yaml.safe_load(SLOTS.read_text(encoding="utf-8"))
    strings = doc["payload_identity"]
    identities = set(strings.values())
    assert len(strings) > len(identities), (
        "the normalisation table no longer collapses anything, so either the source "
        "stopped using alternative spellings or the table lost its entries"
    )
    assert not identities - set(doc["mechanism_of_payload"]), (
        identities - set(doc["mechanism_of_payload"])
    )
    assert not identities - set(doc["family_of_payload"]), (
        identities - set(doc["family_of_payload"])
    )


def test_only_one_linker_label_is_non_cleavable() -> None:
    """Their fourteen linker strings name a cleavage route or say "Non-cleavable".

    If a second non-cleavable label appears, the binary is no longer a lookup and the
    mapping needs a human, not a default.
    """
    doc = yaml.safe_load(SLOTS.read_text(encoding="utf-8"))
    non = [k for k, v in doc["cleavable_of_linker_type"].items() if not v]
    assert non == ["Non-cleavable"], non


def test_a_post_freeze_mechanism_addition_carries_a_date_and_a_reason() -> None:
    """The mechanism taxonomy is frozen; its own rule is that additions are recorded."""
    doc = yaml.safe_load(SLOTS.read_text(encoding="utf-8"))
    for name, entry in (doc.get("post_freeze_additions") or {}).items():
        assert entry.get("added"), name
        assert entry.get("justification", "").strip(), name
        # A single-agent level cannot be a held-out fold, and saying so is what separates a
        # genuine new mechanism from taxonomy inflation.
        assert "holdout_viable" in entry, name


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_label_rows_survive_the_gate() -> None:
    """The regression that matters: percentage-and-denominator rows must be kept.

    883 of them exist, all from regulatory labels, and the first version of the filter
    dropped every one.
    """
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    assert doc["source_tiers"].get("label", 0) > 0, (
        "no label-derived arms survived ingestion; the usability filter is requiring a "
        "numerator that label tables do not print"
    )
    assert doc["arithmetic_gate"]["numerator_reconstructed_from_percentage"] > 0


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_a_reconstructed_numerator_is_not_counted_as_verified() -> None:
    """Checking a derived numerator against the percentage it came from is circular."""
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    gate = doc["arithmetic_gate"]
    assert gate["verifiable"] + gate["not_verifiable"] > 0
    assert gate["numerator_reconstructed_from_percentage"] <= gate["not_verifiable"], (
        "reconstructed numerators are being counted among the verifiable rows, which makes "
        "the pass rate pass by construction"
    )


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_the_source_tier_has_more_than_two_levels() -> None:
    """The reason the field exists. Negative result 34 measured the reporting-source gap at
    up to 1.85 logit on one axis, larger than the mechanism effect, so four document kinds
    cannot be absorbed by a registry/literature binary."""
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    assert len(doc["source_tiers"]) >= 3, doc["source_tiers"]


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_the_funnel_only_ever_loses_rows() -> None:
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    rows = [f["rows"] for f in doc["funnel"]]
    assert rows == sorted(rows, reverse=True), doc["funnel"]


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_the_merged_corpus_is_a_superset_of_both() -> None:
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    by = {r["corpus"]: r for r in doc["corpora"]}
    merged = by["merged"]
    for name in ("registry + literature (ours)", "atlas only"):
        assert merged["agents"] >= by[name]["agents"], name
        assert merged["identifying_cells"] >= by[name]["identifying_cells"], name
        assert merged["payload_identities"] >= by[name]["payload_identities"], name


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_the_identification_floor_is_reported_and_not_assumed_met() -> None:
    """Doubling the agents raised the ratio and did not reach the floor, which is the
    honest result and the one a reader is most likely to assume away."""
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    by = {r["corpus"]: r for r in doc["corpora"]}
    merged = by["merged"]
    assert merged["cells_per_design_parameter"] == pytest.approx(
        merged["identifying_cells"] / doc["design_parameters"], abs=0.01
    )
    assert merged["meets_identification_floor"] == (
        merged["cells_per_design_parameter"] >= doc["identification_floor"]
    )


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_negative_result_six_is_measured_not_projected() -> None:
    """The payload vocabulary's growth rate, which result 6 turns on.

    The claim is that it grows as fast as the corpus. Measured across the two corpus sizes,
    payloads per agent should be reported for each, and the merged payload-level ratio
    should still be far below the identification floor -- that is the claim, and if it ever
    stops holding the report's most load-bearing structural result has changed.
    """
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    by = {r["corpus"]: r for r in doc["corpora"]}
    for r in doc["corpora"]:
        assert r["payloads_per_agent"] > 0
    merged = by["merged"]
    payload_parameters = (merged["payload_identities"] - 1) * 14
    payload_ratio = merged["identifying_cells"] / payload_parameters
    assert payload_ratio < doc["identification_floor"], (
        f"payload-level ratio reached {payload_ratio:.2f}, at or above the "
        f"{doc['identification_floor']}:1 floor. Negative result 6 says this cannot happen "
        "at any reachable corpus size; re-derive it before the report keeps the claim."
    )
