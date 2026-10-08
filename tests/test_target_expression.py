"""The target antigen must change the output, and only where the evidence supports it.

Before this layer the target was a completely inert input. Measured: swapping ERBB2 for
CD33, for NECTIN4, or for an invented name left the 106 candidates, the 74 constraint
passes, every organ estimate and every objective score bit-identical. The one thing it
touched was a sentence naming the nearest existing ADC.

The reason was that the only route by which a target could matter -- per-organ target
expression, constraint C3 -- was declared in the code and never ingested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adctox.comorbidity import target_expression as tx

ART = Path(__file__).resolve().parents[1] / "artifacts" / "target_expression.json"
pytestmark = pytest.mark.skipif(
    not ART.exists(), reason="target expression artefact not built"
)


def _doc():
    return json.loads(ART.read_text(encoding="utf-8"))


def test_the_five_declared_on_target_cases_are_all_captured():
    """The evidence that licenses this layer at all.

    Expression does not predict labelled organ toxicity in aggregate -- AUROC 0.52 to
    0.58 across 14 approved ADCs. What it does is locate the organ a target could reach,
    and these five textbook pairs are the check on that. If they stop being captured, the
    layer has no justification and should be switched off rather than retuned.
    """
    check = _doc()["known_on_target_check"]
    assert check["n_captured"] == check["n_pairs"], [
        p for p in check["pairs"] if not p["captured"]
    ]
    assert check["n_pairs"] >= 5
    # Recorded honestly: fewer independent facts than pairs.
    assert check["n_independent_facts"] < check["n_pairs"]


def test_the_threshold_is_set_by_the_weakest_known_case():
    """0.80 is the strictest cut that still captures all five, not a round number.

    FOLR1 in kidney is the weakest at 0.83. A cut of 0.90 drops it and 1.00 drops three.
    """
    doc = _doc()
    cut = doc["abundant_percentile"]
    weakest = min(p["percentile"] for p in doc["known_on_target_check"]["pairs"])
    assert cut <= weakest, f"cut {cut} excludes the weakest known case at {weakest}"
    assert cut > weakest - 0.1, (
        f"cut {cut} is far looser than the weakest known case at {weakest}; it should be "
        "the strictest threshold that still captures them"
    )


def test_an_unknown_target_reports_not_evaluable_rather_than_passing():
    assert tx.evaluable("ERBB2")
    assert not tx.evaluable("NOTAREALTARGET")
    assert tx.applicable("NOTAREALTARGET", {"pulmonary"}, permeable_payload=True) == {}


def test_flags_only_fire_on_axes_the_patient_is_vulnerable_on():
    """A target abundant in an organ the patient is fine with is not a finding."""
    assert tx.applicable("NECTIN4", set(), permeable_payload=True) == {}
    fired = tx.applicable("NECTIN4", {"dermatologic", "neurologic"}, permeable_payload=True)
    assert set(fired) == {"dermatologic"}, (
        "NECTIN4 is top-percentile in skin and not in brain; only skin should fire"
    )


def test_the_driver_states_its_own_weakness():
    """The wording is load-bearing. A flag from an AUROC-0.52 signal that reads like a
    prediction would be the most misleading sentence in the product."""
    d = tx.applicable("NECTIN4", {"dermatologic"}, permeable_payload=True)[
        "dermatologic"
    ].as_driver()
    assert d["source"] == "target_expression"
    assert d["contribution"] is None
    assert "flag, not a prediction" in d["detail"]
    assert "0.52" in d["detail"]


def test_permeability_is_reported_because_it_is_the_candidate_level_part():
    """The expression flag is target-level and identical across candidates sharing a
    target. Bystander permeability is the part that varies by candidate, so it is named
    rather than folded in silently."""
    yes = tx.applicable("NECTIN4", {"dermatologic"}, permeable_payload=True)["dermatologic"]
    no = tx.applicable("NECTIN4", {"dermatologic"}, permeable_payload=False)["dermatologic"]
    assert "not confined" in yes.as_driver()["detail"]
    assert "confined to" in no.as_driver()["detail"]
    assert yes.as_driver()["detail"] != no.as_driver()["detail"]


def test_percentile_one_does_not_print_as_top_zero_percent():
    """Cosmetic but it reaches a reader: 100th percentile rendered as "top 0%"."""
    d = tx.applicable("NECTIN4", {"dermatologic"}, permeable_payload=True)[
        "dermatologic"
    ].as_driver()
    assert "top 0%" not in d["factor"]
    assert "most abundant" in d["factor"]


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "artifacts" / "posterior_serious.npz").exists(),
    reason="posteriors not built",
)
def test_the_target_now_changes_the_reported_output():
    """The regression this whole layer exists for."""
    from adctox.model.predict import Posterior
    from adctox.pipeline import propose

    art = Path(__file__).resolve().parents[1] / "artifacts"
    po = Posterior.load(art / "posterior_other.npz")
    ps = Posterior.load(art / "posterior_serious.npz")

    def derm_band(target):
        r = propose(target, ["severe_psoriasis"], po, top_k=1, serious_posterior=ps)
        row = next(
            o for o in r["candidates"][0]["organ_risks"]
            if o["organ_axis"] == "dermatologic"
        )
        return row["risk_band"], row["band_source"]

    abundant = derm_band("NECTIN4")
    absent = derm_band("CD19")
    assert abundant != absent, (
        "a skin-abundant target and a skin-absent one still produce the same skin row; "
        "the target is inert again"
    )
    assert abundant[1] == "target_expression"
    assert absent[1] == "model"


def test_every_axis_is_covered_by_at_least_one_source():
    """GTEx has no eye and no ear; Tabula Sapiens has no brain. Dropping either source
    would leave an axis the product is asked about with no data at all."""
    doc = _doc()
    not_evaluable = set(doc["axes_not_evaluable"])
    for symbol, spec in doc["targets"].items():
        if len(spec["sources_present"]) < 2:
            continue   # IL3RA has no Tabula Sapiens profile
        covered = set(spec["percentile"])
        for axis in ("ocular", "otologic", "neurologic"):
            assert axis in covered or axis in not_evaluable, (
                f"{symbol} has no value for {axis}, which only one source covers"
            )
