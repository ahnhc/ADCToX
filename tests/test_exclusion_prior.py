"""The exclusion-criteria prior is served as a driver, separately from the fitted model.

Why these tests exist: the schema declares four driver sources and for a long while only
two were ever produced, so a promised field was dead. These lock the fourth one in and,
more importantly, lock in the boilerplate filter -- the measured fact that cardiovascular
and infectious exclusions are near-universal in oncology protocols and therefore carry no
mechanism information, while ocular exclusions vary by two orders of magnitude.
"""

from __future__ import annotations

import json

import pytest

from adctox.comorbidity import exclusion_prior as ep


def test_informative_cell_yields_a_driver():
    d = ep.driver("topo1", "pulmonary")
    assert d is not None, "topo-I/pulmonary is the measured 5.75x cell; it must be served"
    assert d["source"] == "exclusion_head"
    assert d["odds_ratio"] >= ep.MIN_INFORMATIVE_ODDS_RATIO


def test_contribution_is_none_not_zero():
    """A prior is not a term in the linear predictor.

    None renders as "no additive contribution"; 0.0 would render as a measured
    contribution of nothing, which is a different and false statement.
    """
    d = ep.driver("tubulin", "ocular")
    assert d is not None
    assert d["contribution"] is None


def test_boilerplate_cell_is_suppressed():
    """Cardiovascular exclusions are boilerplate: every oncology protocol has an LVEF
    floor, so the enrichment there is ~1x and conveys nothing about the payload."""
    assert ep.driver("topo1", "cardiovascular") is None


def test_unknown_mechanism_and_axis_return_none():
    assert ep.driver("not_a_mechanism", "pulmonary") is None
    assert ep.driver("topo1", "not_an_axis") is None


def test_known_signals_are_present_and_ordered():
    """The strongest measured signals must survive the filter, and ocular must dominate
    for tubulin -- that is the MMAF keratopathy signal, the sharpest in the corpus."""
    ocular = ep.driver("tubulin", "ocular")
    neuro = ep.driver("tubulin", "neurologic")
    assert ocular is not None and neuro is not None
    assert ocular["odds_ratio"] > neuro["odds_ratio"] > 2.0


def test_threshold_is_actually_enforced_at_the_boundary(monkeypatch):
    """A cell just under the cut is suppressed; just over it is served."""
    fake = {"m": {"a": {"odds_ratio": ep.MIN_INFORMATIVE_ODDS_RATIO - 0.01,
                        "rate": 0.5, "n_trials": 10, "p": 0.1},
                  "b": {"odds_ratio": ep.MIN_INFORMATIVE_ODDS_RATIO + 0.01,
                        "rate": 0.5, "n_trials": 10, "p": 0.1}}}
    monkeypatch.setattr(ep, "_load", lambda *a, **k: fake)
    assert ep.driver("m", "a") is None
    assert ep.driver("m", "b") is not None


def test_missing_artifact_degrades_to_no_drivers(tmp_path, monkeypatch):
    """A clean clone without the artefact must yield no drivers, not an exception."""
    monkeypatch.setattr(ep, "_load", lambda *a, **k: {})
    assert ep.driver("topo1", "pulmonary") is None


def test_detail_does_not_claim_prediction():
    """The wording is load-bearing: this is consistency with an expert prior, and the
    enrichment is negatively coupled with the outcome model. Saying 'predicts' here would
    be the single most misleading sentence in the product."""
    d = ep.driver("topo1", "pulmonary")
    assert d is not None
    assert "not a prediction" in d["detail"]
    assert "negatively coupled" in d["detail"]


def test_api_emits_all_four_declared_driver_sources():
    """The schema declares four sources; for a long time only two were produced.

    This is the regression guard for that class of bug -- a field promised in the contract
    and never populated by any code path.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    declared = {"model", "exclusion_head", "elicited_prior", "rule"}
    c = TestClient(app)
    r = c.post(
        "/api/v1/assess",
        json={
            "design": {
                "target_antigen": "ERBB2", "payload": "DXd", "linker": "GGFG",
                "conjugation": "interchain_cysteine", "dar": 8.0,
            },
            "comorbidity_profile": {"conditions": ["interstitial_lung_disease"]},
        },
    )
    if r.status_code == 503:
        pytest.skip("posterior artefact absent; run scripts/propose_demo.py")
    assert r.status_code == 200, r.text
    seen = {
        d["source"]
        for axis in r.json()["organ_risks"]
        for d in axis["drivers"]
    }
    assert seen == declared, f"declared {declared}, emitted {seen}"
