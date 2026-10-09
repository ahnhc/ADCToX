"""Tier 3 is unreachable with the shipped posterior, and that is the stronger property.

The plan asked for a three-tier novelty judgement, with tier 3 -- a mechanism the fit has no
coefficient for -- returning intervals and no point estimate. The implemented refusal is
earlier and harder: `payload` is a closed enumeration, so a chemistry the model has never
seen cannot be named in a request at all and is rejected by the schema with a 422. Every one
of the design space's eleven payloads has a mechanism the full fit covers, so the tier-3
branch never fires in production.

That makes it defensive rather than dead. Any posterior fitted on fewer mechanisms than the
design space offers -- every leave-one-mechanism-out fold, and the registry-only fit if a
mechanism drops below its floor -- puts a design-space payload outside the fit, and then the
branch is the only thing between a caller and fourteen extrapolated numbers. These tests pin
both halves, because a branch nothing can reach and nothing tests is how
`nearest_reference_adcs` came to be declared in the schema and returned empty by every code
path.
"""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from adctox.api import main as api
from adctox.design.enumerate import DesignSpace

DESIGN = {
    "target_antigen": "ERBB2", "payload": "DXd", "linker": "GGFG",
    "conjugation": "interchain_cysteine", "dar": 8.0,
    "isotype": "IgG1", "masking": "none",
}
PROFILE = {"conditions": ["cirrhosis"]}


def test_an_unnamed_chemistry_is_refused_by_the_schema() -> None:
    """The closed vocabulary, which is why tier 3 does not arise in practice."""
    body = {"design": {**DESIGN, "payload": "NotAPayload"},
            "comorbidity_profile": PROFILE}
    r = TestClient(api.app).post("/api/v1/assess", json=body)
    assert r.status_code == 422
    assert "unknown payload" in r.json()["detail"]


def test_every_design_space_payload_has_a_fitted_mechanism() -> None:
    """The reason the tier-3 branch is unreachable with the shipped posterior. If this ever
    fails, the branch has become live for ordinary callers and the model card's claim about
    refusing outside tier 1 needs rereading, not just this test."""
    post = api._posterior()
    outside = [
        (name, spec.get("mechanism"))
        for name, spec in DesignSpace().payloads.items()
        if spec.get("mechanism") not in post.mechanisms
    ]
    assert not outside, outside


def test_a_posterior_missing_a_mechanism_refuses_rather_than_extrapolates() -> None:
    """The branch, exercised the only way it can be: a fit that covers fewer mechanisms
    than the design space, which is what every leave-one-mechanism-out fold is."""
    post = api._posterior()
    keep = [i for i, m in enumerate(post.mechanisms) if m != "topo1"]
    assert len(keep) == len(post.mechanisms) - 1, "topo1 is not in this posterior"
    reduced = dataclasses.replace(
        post,
        mechanisms=[post.mechanisms[i] for i in keep],
        mech_axis=post.mech_axis[:, keep, :],
    )
    original = api._posterior
    try:
        api._posterior = lambda: reduced
        body = {"design": DESIGN, "comorbidity_profile": PROFILE}
        d = TestClient(api.app).post("/api/v1/assess", json=body).json()
    finally:
        api._posterior = original

    assert d["coverage"]["novelty_tier"] == 3
    assert d["coverage"]["in_distribution"] is False
    assert d["organ_risks"] == [], "a tier-3 response must carry no organ estimate"
    assert any("absent from the training corpus" in w
               for w in d["coverage"]["warnings"])
    # And the response still carries the things every response must.
    assert d["disclaimer"] and d["limitations"]
