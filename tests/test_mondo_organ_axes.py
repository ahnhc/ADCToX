"""Tests for the MONDO-derived organ axis layer.

The layer's purpose is independence. The registry's `organ_axes` column was hand-assigned
by reading trial exclusion criteria, so recovering exclusion criteria from it is circular;
a MONDO `is_a` closure touches no exclusion text, which turns 1,741 trials into a
legitimate holdout instead of 28 cells of label text.

Its realised value so far was different and larger: it audited the registry. The plan
required all 40 MONDO identifiers to be hand-pinned into a checked-in CSV, precisely
because a search API had silently mis-resolved 3 of 36 test conditions. The pinning was
done and it did not help -- 8 of 41 pins named an unrelated disease, which is a worse rate
than the API's. Nothing had broken only because nothing read the column until this layer
did.
"""

from __future__ import annotations

import csv
import json
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "comorbidity_registry.csv"
CROSSWALK = ROOT / "conf" / "ontology" / "mondo_organ_axis.yaml"
DERIVED = ROOT / "artifacts" / "mondo_organ_axes.json"
AUDIT = ROOT / "artifacts" / "mondo_id_audit.json"


def _registry() -> list[dict]:
    return list(csv.DictReader(REGISTRY.open(encoding="utf-8")))


def test_every_condition_pins_an_identifier() -> None:
    for row in _registry():
        assert row["mondo_id"].strip(), row["id"]


def test_no_pin_names_an_unrelated_disease() -> None:
    """The guard the hand-pinning was supposed to be. A pin is wrong when the organs its
    `is_a` closure implies do not intersect the organs the hand map assigns -- which is how
    `ckd_stage_3` pointing at cardiomyopathy and `interstitial_lung_disease` pointing at
    cervix squamous papilloma were found. A broader term on the same organ is fine, and the
    ontology root is a deliberate marker for the five conditions that are prior exposures
    rather than diseases."""
    if not AUDIT.exists():
        pytest.skip("run `make mondo-audit`")
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["n_pin_wrong"] == 0, [
        (f["id"], f["pinned"], f["pinned_names"])
        for f in audit["findings"]
        if f["verdict"] == "pin_names_unrelated_disease"
    ]
    assert audit["n_pin_absent"] == 0


def test_the_crosswalk_only_targets_real_axes() -> None:
    from adctox.taxonomy import default_taxonomy

    axes = set(default_taxonomy().axis_order)
    cross = yaml.safe_load(CROSSWALK.read_text(encoding="utf-8"))
    for ancestor, axis in cross["ancestor_to_axis"].items():
        assert axis in axes, f"{ancestor!r} maps to unknown axis {axis!r}"


def test_the_undeivable_axis_is_declared_rather_than_silently_empty() -> None:
    """`constitutional` is a MedDRA reporting class -- fatigue, pyrexia, weight loss -- not
    an organ, so no disease ontology can place a comorbidity on it. An axis that is simply
    absent from the output looks like a gap in the crosswalk."""
    cross = yaml.safe_load(CROSSWALK.read_text(encoding="utf-8"))
    assert "constitutional" in cross["axes_not_derivable"]
    assert "constitutional" not in set(cross["ancestor_to_axis"].values())


def test_every_unmapped_organ_shaped_ancestor_carries_a_reason() -> None:
    """An ancestor that looks like an organ and is not mapped has to be a decision. The
    ones here are groupings ("disease by body system or component", present for 31 of 41
    conditions), aetiologies, and `neoplasm` -- which every comorbidity in an oncology
    trial coexists with, so it separates nothing."""
    cross = yaml.safe_load(CROSSWALK.read_text(encoding="utf-8"))
    for term, reason in cross["not_mapped"].items():
        assert len(str(reason).split()) >= 3, f"{term} has no real reason"


@pytest.mark.skipif(not DERIVED.exists(), reason="run `make mondo-axes`")
def test_the_derivation_resolves_every_condition() -> None:
    d = json.loads(DERIVED.read_text(encoding="utf-8"))
    assert d["n_unresolvable"] == 0, d["unresolvable"]
    assert d["n_resolved"] == d["n_conditions"]


@pytest.mark.skipif(not DERIVED.exists(), reason="run `make mondo-axes`")
def test_only_the_non_diseases_derive_no_organ() -> None:
    """Six conditions derive nothing, and all six should: five are prior exposures -- an
    anthracycline, chest radiation, corneal surgery, a transplant, a bowel resection -- and
    the sixth is QT prolongation, a drug-induced ECG finding. MONDO has `long QT syndrome`,
    but that is a hereditary channelopathy, and pinning it is the exact mis-resolution the
    plan flagged. A seventh condition appearing here would mean a real gap."""
    d = json.loads(DERIVED.read_text(encoding="utf-8"))
    empty = set(d["conditions_with_no_derived_axis"])
    expected = {
        "prior_anthracycline", "prior_chest_radiation", "prior_corneal_surgery",
        "prior_hsct", "prior_bowel_resection", "qt_prolongation",
    }
    assert empty == expected, {"unexpected": empty - expected, "missing": expected - empty}


@pytest.mark.skipif(not DERIVED.exists(), reason="run `make mondo-axes`")
def test_the_extra_axes_are_not_independent_evidence() -> None:
    """The measured limit on this layer, and the reason it is an audit rather than a
    replacement for the hand map.

    MONDO adds 21 axes the hand map does not have, and 12 of them are hepatic conditions
    acquiring `gastrointestinal` and `metabolic_endocrine` through two ancestors --
    "digestive system disorder" and "endocrine system disorder" -- because MONDO places the
    liver in both systems. That is upper-ontology placement, not a claim that a cirrhotic
    patient faces elevated gastrointestinal adverse-event risk. Twelve axes from one
    placement are one piece of evidence, not twelve, so the plan's "multiple parents are a
    feature" is half right: a feature when it reflects multi-organ involvement (hepatitis B
    is hepatic and immune) and an artifact when it reflects where a curator filed an organ.
    """
    d = json.loads(DERIVED.read_text(encoding="utf-8"))
    mondo_only = d["mondo_only_axis_counts"]
    from_upper_ontology = (
        mondo_only.get("gastrointestinal", 0) + mondo_only.get("metabolic_endocrine", 0)
    )
    total = sum(mondo_only.values())
    assert total > 0
    assert from_upper_ontology / total > 0.5, (
        "if this ever drops below half, the extra axes are no longer dominated by one "
        "ontological placement and the caveat in section 5h needs re-measuring"
    )


@pytest.mark.skipif(not DERIVED.exists(), reason="run `make mondo-axes`")
def test_the_hand_map_and_the_ontology_mostly_agree() -> None:
    """Not a pass criterion, a sanity floor. The hand map was not expected to be arbitrary,
    and an independent ontology sharing no axis with it on most conditions would mean one
    of the two is badly wrong."""
    d = json.loads(DERIVED.read_text(encoding="utf-8"))
    assert d["sharing_rate"] > 0.75, d["sharing_rate"]
