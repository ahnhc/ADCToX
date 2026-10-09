"""Validate whole responses against the declared models, on the inputs that exercise them.

`OrganRisk.model_validate` was already applied to both product paths, and it still missed
`band_source: "target_expression"` sitting outside the field's `Literal`. The reason is the
input: both tests query an interstitial-lung-disease profile, where the target-expression
flag does not fire, so no response they build ever carried the value. A contract test is
only as wide as the responses it is given.

So this does two things the existing tests do not. It validates the *whole* response rather
than one list inside it, and it parameterises over profiles chosen so that each optional
field is populated by at least one of them -- the expression flag by a dermatologic profile
against a skin-expressed target, the serious band basis by an at-risk axis, the label rules
by a liver profile.

Responses are built as raw dicts and returned through `JSONResponse`, so Pydantic never sees
them at runtime. The schema is documentation plus the source the TypeScript client is
generated from, which is exactly the situation in which it drifts silently.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adctox.api.main import app
from adctox.schemas import AssessResponse, ProposeResponse

CLIENT = TestClient(app)

# Each profile is here to populate something a blander one leaves empty.
PROFILES = {
    "dermatologic/NECTIN4": (["severe_psoriasis", "prior_sjs_ten"], "NECTIN4"),
    "renal+pulmonary/ERBB2": (["ckd_stage_4_5", "interstitial_lung_disease"], "ERBB2"),
    "hepatic/CD33": (["cirrhosis", "hepatic_vod_history"], "CD33"),
    "none/TACSTD2": ([], "TACSTD2"),
    "four organs/ERBB3": (
        ["cirrhosis", "ckd_stage_4_5", "heart_failure", "dry_eye"], "ERBB3",
    ),
}


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_propose_response_validates_whole(name: str) -> None:
    conditions, target = PROFILES[name]
    r = CLIENT.post("/api/v1/propose", json={
        "comorbidity_profile": {"conditions": conditions},
        "target_antigen": target, "top_k": 3,
    })
    if r.status_code == 503:
        pytest.skip("posterior artefact absent")
    assert r.status_code == 200, r.text[:300]
    ProposeResponse.model_validate(r.json())


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_assess_response_validates_whole(name: str) -> None:
    conditions, target = PROFILES[name]
    r = CLIENT.post("/api/v1/assess", json={
        "design": {
            "target_antigen": target, "payload": "MMAE", "linker": "vc_PABC",
            "conjugation": "interchain_cysteine", "dar": 4.0,
            "isotype": "IgG1", "masking": "none",
        },
        "comorbidity_profile": {"conditions": conditions},
    })
    if r.status_code == 503:
        pytest.skip("posterior artefact absent")
    assert r.status_code == 200, r.text[:300]
    AssessResponse.model_validate(r.json())


def test_the_profiles_between_them_populate_every_band_source() -> None:
    """The guard on the guard. If no profile here produces a `target_expression` band, this
    file is back to the blind spot it was written for."""
    seen: set[str] = set()
    for conditions, target in PROFILES.values():
        r = CLIENT.post("/api/v1/propose", json={
            "comorbidity_profile": {"conditions": conditions},
            "target_antigen": target, "top_k": 3,
        })
        if r.status_code != 200:
            continue
        for c in r.json()["candidates"]:
            seen |= {row["band_source"] for row in c["organ_risks"]}
    assert "target_expression" in seen, seen
    assert "model" in seen, seen


def test_every_driver_source_has_a_colour_in_the_interface() -> None:
    """The rule the schema's `source` field exists to serve: learned and elicited numbers
    must be visually separable. A member with no colour renders unstyled, which reads as
    neither."""
    import pathlib
    import typing

    from adctox.schemas import Driver

    page = (
        pathlib.Path(__file__).resolve().parents[1] / "web" / "index.html"
    ).read_text(encoding="utf-8")
    members = typing.get_args(Driver.model_fields["source"].annotation)
    assert members
    missing = [m for m in members if f"--src-{m}" not in page]
    assert not missing, f"driver sources with no colour defined: {missing}"
