"""Schema tests that make the scope constraint checkable rather than promised.

The project claims it cannot represent a patient identifier. That claim is only worth
anything if it is enforced by the type system and verified automatically, so the central
test here walks every request model and fails on any unbounded string field. A reader can
confirm the claim by running one test instead of reading the code.
"""

from __future__ import annotations

import pydantic
import pytest
from pydantic import BaseModel

from adctox.schemas import (
    ADCDesign,
    AssessRequest,
    Cohort,
    ComorbidityProfile,
    ProposeRequest,
    comorbidity_registry,
)

REQUEST_MODELS = [ProposeRequest, AssessRequest, ComorbidityProfile, ADCDesign, Cohort]

# The one field in any request that is legitimately free-form chemistry rather than
# anything about a person. Listed explicitly so adding another needs a deliberate edit.
ALLOWED_PATTERNED_STRINGS = {
    ("ADCDesign", "target_antigen"),
    ("ADCDesign", "payload"),
    ("ADCDesign", "linker"),
    ("ProposeRequest", "target_antigen"),
}


def _string_fields(model: type[BaseModel]):
    for name, field in model.model_fields.items():
        ann = field.annotation
        if ann is str:
            yield name, field
        elif getattr(ann, "__args__", None) and str in ann.__args__:
            # Optional[str] and friends.
            yield name, field


@pytest.mark.parametrize("model", REQUEST_MODELS, ids=lambda m: m.__name__)
def test_no_unbounded_string_in_any_request_model(model: type[BaseModel]) -> None:
    """A patient identifier must not be representable anywhere in a request.

    Every string field has to be either length-capped with a restrictive pattern, or
    explicitly listed above. An enum field is fine by construction and never reaches here.
    """
    for name, field in _string_fields(model):
        key = (model.__name__, name)
        constraints = {type(m).__name__: m for m in (field.metadata or [])}
        has_pattern = "_PydanticGeneralMetadata" in constraints or any(
            getattr(m, "pattern", None) for m in (field.metadata or [])
        )
        has_max = any(getattr(m, "max_length", None) for m in (field.metadata or []))
        assert key in ALLOWED_PATTERNED_STRINGS, (
            f"{model.__name__}.{name} is a free string field. Patient-side input must be "
            "an enum or a bounded number so that an identifier is not representable."
        )
        assert has_max or has_pattern, f"{model.__name__}.{name} is unbounded"


@pytest.mark.parametrize("model", REQUEST_MODELS, ids=lambda m: m.__name__)
def test_extra_fields_forbidden(model: type[BaseModel]) -> None:
    """A caller must not be able to smuggle a field past the schema."""
    assert model.model_config.get("extra") == "forbid", model.__name__


def test_comorbidity_list_is_closed() -> None:
    """Closed at the type level: `conditions` is an enum generated from the registry, so
    an out-of-list value cannot be constructed at all."""
    with pytest.raises(pydantic.ValidationError):
        ComorbidityProfile(conditions=["patient has bad kidneys"])
    ok = ComorbidityProfile(conditions=["interstitial_lung_disease"])
    assert ok.condition_ids == ["interstitial_lung_disease"]


def test_comorbidity_enum_matches_the_registry() -> None:
    """The enum is generated, so it cannot drift from the CSV."""
    from adctox.schemas import ComorbidityId

    assert {m.value for m in ComorbidityId} == set(comorbidity_registry())


def test_registry_entries_are_well_formed() -> None:
    """Every row needs an organ mapping and a cited severity basis.

    A severity without a basis is a number someone picked, and the whole defence of the
    comorbidity layer is that its magnitudes come from the quantitative thresholds inside
    trial exclusion criteria.
    """
    registry = comorbidity_registry()
    assert len(registry) >= 40
    for cid, row in registry.items():
        assert row["organ_axes"], cid
        assert row["severity_basis"].strip(), f"{cid} has no cited severity basis"
        assert 0.0 < row["severity"] <= 1.0, cid


def test_dar_is_bounded_by_the_hard_cap() -> None:
    """DAR above 8 is refused. Polymer-masked high-DAR ADCs reached the clinic and
    failed: upifitamab rilsodotin (DAR 10-15) produced five grade-5 bleeding events and
    was discontinued, so masking is not a licence to exceed the cap."""
    ADCDesign(
        target_antigen="ERBB2", payload="DXd", linker="GGFG",
        conjugation="interchain_cysteine", dar=8.0,
    )
    with pytest.raises(pydantic.ValidationError):
        ADCDesign(
            target_antigen="ERBB2", payload="DXd", linker="GGFG",
            conjugation="interchain_cysteine", dar=12.0,
        )


def test_fc_engineering_is_not_a_design_slot() -> None:
    """Deliberately absent: zero approved ADCs use it, zero training arms carry it, and
    the primary literature on the mechanism is mutually contradictory. Offering it would
    be a knob with no coefficient behind it."""
    assert "fc_engineering" not in ADCDesign.model_fields
    with pytest.raises(pydantic.ValidationError):
        ADCDesign(
            target_antigen="ERBB2", payload="DXd", linker="GGFG",
            conjugation="interchain_cysteine", dar=8.0, fc_engineering="LALA",
        )
