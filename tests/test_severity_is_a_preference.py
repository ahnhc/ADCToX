"""The severity column is unvalidated, and the product must present it as such.

Measured on the registry: **34 of 41 severity values cite trial exclusion criteria as
their basis** -- "Child-Pugh B/C excluded in ADC protocols", "HBV exclusion present in 54%
of ADC protocols". So severity cannot be validated against exclusion criteria, because it
was assigned from them. One value of 41 cites a label.

The MONDO layer solved exactly this circularity for the `organ_axes` column, giving it an
independent derivation that recovers exclusion concern at AUROC 0.675. Severity has no such
derivation, and the plan's designated alternative -- the FDA label impairment ordinal --
turned out to measure clearance rather than organ event rates, so that path is closed too.

That is acceptable only because of a design decision the plan made for a different reason:
severity enters as a displayed *weight*, `w_o = 1 + lambda * severity_o`, never as a logit.
The plan's words are that a term with zero training rows must not drive a core function, and
that the weight must be shown on screen. An unvalidated number presented as a transparent
preference is honest; the same number presented as a prediction would not be. These tests
are what keep the distinction.
"""

from __future__ import annotations

import csv
import pathlib
import re

from fastapi.testclient import TestClient

from adctox.api.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "comorbidity_registry.csv"
PROFILE = {
    "conditions": ["interstitial_lung_disease", "ckd_stage_3"],
    "cohort": {"age_band": "65_74", "sex": "female"},
}


def test_severity_bases_are_mostly_exclusion_derived_so_the_claim_stays_bounded() -> None:
    """Pins the circularity rather than the fix, because there is no fix available from
    the current sources. If a future round gives severity an independent derivation, this
    test should fail and be replaced by one that scores it."""
    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    exclusion = re.compile(r"exclu|protocol|trial|crcl|cut|floor|criteria", re.I)
    cited = sum(1 for r in rows if exclusion.search(r["severity_basis"]))
    assert cited > 0.5 * len(rows), (
        "severity no longer looks exclusion-derived; if it has an independent basis now, "
        "validate it against exclusions and delete this test"
    )
    # And every value must at least say where it came from.
    for r in rows:
        assert r["severity_basis"].strip(), r["id"]


def test_the_weight_is_never_presented_as_a_model_output() -> None:
    """The load-bearing one. `/assess` reports the comorbidity weighting as an
    `elicited_prior` driver and `/propose` as `weight_applied`; neither may label it
    `model`, because a reader separating fitted from asserted quantities by the `source`
    field would then be misled about the one quantity in the response that has no training
    data behind it."""
    client = TestClient(app)
    proposed = client.post("/api/v1/propose", json={
        "comorbidity_profile": PROFILE, "target_antigen": "ERBB2", "top_k": 2,
    })
    assert proposed.status_code == 200, proposed.text[:300]
    for candidate in proposed.json()["candidates"]:
        for organ in candidate["organ_risks"]:
            for driver in organ["drivers"]:
                if driver["source"] == "model":
                    assert "weight" not in driver["factor"].lower(), driver
                    assert "comorbidit" not in driver["factor"].lower(), driver

    design = proposed.json()["candidates"][0]["design"]
    assessed = client.post("/api/v1/assess", json={
        "design": {
            "target_antigen": design["target"], "payload": design["payload"],
            "linker": design["linker"], "conjugation": design["conjugation"],
            "dar": design["dar"], "isotype": design["isotype"],
            "masking": design["masking"],
        },
        "comorbidity_profile": PROFILE,
    })
    assert assessed.status_code == 200, assessed.text[:300]
    weighting = [
        d for o in assessed.json()["organ_risks"] for d in o["drivers"]
        if "comorbidity weighting" in d["factor"]
    ]
    assert weighting, "the comorbidity weighting is not reported as a driver at all"
    for d in weighting:
        assert d["source"] == "elicited_prior", d


def test_the_weight_is_visible_wherever_it_is_applied() -> None:
    """A weight that changes a ranking without appearing on screen is the failure mode the
    plan's "display w" instruction exists to prevent."""
    client = TestClient(app)
    body = client.post("/api/v1/propose", json={
        "comorbidity_profile": PROFILE, "target_antigen": "ERBB2", "top_k": 2,
    }).json()
    assert body["weights_applied"], "response-level weights missing"
    # Every axis the patient is at risk on must carry its own weight, and it must differ
    # from 1.0 -- otherwise the profile had no effect and saying it did would be wrong.
    for candidate in body["candidates"]:
        at_risk = [o for o in candidate["organ_risks"] if o.get("at_risk_for_patient")]
        assert at_risk, "a profile naming two organs produced no at-risk axis"
        for organ in at_risk:
            assert organ["weight_applied"] > 1.0, organ["organ_axis"]


def test_the_severity_scale_is_coarser_than_it_looks() -> None:
    """17 of 41 values sit at exactly 1.0 and 13 at 0.6, so the scale is effectively three
    levels and the second decimal is not a measurement. Recorded so nobody reads 0.6 and
    0.7 as a resolved distinction."""
    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    values = sorted({float(r["severity"]) for r in rows})
    assert len(values) <= 8, values
    counts = {v: sum(1 for r in rows if float(r["severity"]) == v) for v in values}
    top_two = sorted(counts.values(), reverse=True)[:2]
    assert sum(top_two) > 0.6 * len(rows), counts
