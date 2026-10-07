"""Tests for the label-derived override layer.

Why this layer is tested as carefully as the model: it is the only part of the system that
can put a red band on an organ without a fitted number behind it, which makes it both the
most defensible component (a regulator wrote it) and the easiest to misread as a
prediction. Two properties therefore have to hold -- a rule can only raise a concern, and
the output must always say which bands came from a rule.
"""

from __future__ import annotations

import yaml

from adctox.comorbidity.hard_flags import (
    CONF,
    applicable,
    load_flags,
    override_band,
)


def test_every_flag_carries_a_verbatim_source() -> None:
    """A flag without a citation is an assertion. The whole defence of this layer is that
    a regulator wrote it down, so the quotation and its section are mandatory."""
    flags, _ = load_flags()
    assert flags
    for f in flags:
        assert f.source_label.strip(), f.id
        assert f.source_section.strip(), f.id
        assert len(f.quote.split()) >= 8, f"{f.id} quote is too short to be verbatim"
        assert f.axis and f.tier


def test_flags_fire_only_for_the_matching_chemistry_and_comorbidity() -> None:
    hit = applicable("topo1", "DXd", {"interstitial_lung_disease"})
    assert [f.id for f in hit["pulmonary"]] == ["dxd_prior_ild"]
    # Right comorbidity, wrong chemistry.
    assert applicable("tubulin", "DM1", {"interstitial_lung_disease"}) == {}
    # Right chemistry, wrong comorbidity.
    assert applicable("topo1", "DXd", {"type_2_diabetes"}) == {}


def test_the_cross_organ_rule_fires_on_a_renal_comorbidity() -> None:
    """The one cross-organ statement in the corpus: a renal impairment raising a
    *pulmonary* risk. It is the coupling the comorbidity layer has no data to learn, so
    losing it to a refactor would matter."""
    hit = applicable("topo1", "DXd", {"ckd_stage_3"})
    assert "pulmonary" in hit
    assert [f.id for f in hit["pulmonary"]] == ["dxd_moderate_renal_pulmonary"]


def test_a_rule_can_raise_a_band_but_never_lower_one() -> None:
    flags, _ = load_flags()
    avoid = [f for f in flags if f.tier == "avoid"][0]
    monitor = [f for f in flags if f.tier == "monitor"][0]
    assert override_band("low", [avoid]) == "high"
    assert override_band("high", [monitor]) == "high"      # not lowered to moderate
    assert override_band("moderate", [monitor]) == "moderate"
    assert override_band("high", []) == "high"


def test_a_rule_overrides_no_evidence() -> None:
    """A label warning *is* evidence. An organ a regulator names must not render as
    unstudied, which would be the one case where the grey hatching misleads."""
    flags, _ = load_flags()
    avoid = [f for f in flags if f.tier == "avoid"][0]
    assert override_band("no_evidence", [avoid]) == "high"


def test_the_strongest_applicable_flag_wins() -> None:
    flags, _ = load_flags()
    avoid = [f for f in flags if f.tier == "avoid"][0]
    monitor = [f for f in flags if f.tier == "monitor"][0]
    assert override_band("low", [monitor, avoid]) == "high"


def test_the_layer_can_be_switched_off() -> None:
    """The case-study evaluation needs this. A rule encoding "prior ILD plus a deruxtecan
    payload is high risk" would make the deruxtecan case study pass with no contribution
    from the model, and a reviewer would be right to discount that result."""
    assert applicable("topo1", "DXd", {"interstitial_lung_disease"}, enabled=False) == {}


def test_a_rule_driver_is_marked_and_carries_no_fitted_contribution() -> None:
    """A rule has no logit term. Reporting a number would imply it was fitted alongside
    the model's own contributions."""
    hit = applicable("topo1", "DXd", {"interstitial_lung_disease"})
    driver = hit["pulmonary"][0].as_driver()
    assert driver["source"] == "rule"
    assert driver["contribution"] is None
    assert "ENHERTU" in driver["detail"]


def test_flag_comorbidities_exist_in_the_registry() -> None:
    """A flag keyed on a condition the API cannot accept is unreachable."""
    from adctox.schemas import comorbidity_registry

    known = set(comorbidity_registry())
    flags, _ = load_flags()
    for f in flags:
        unknown = f.comorbidities - known
        assert not unknown, f"{f.id} references unknown comorbidities {sorted(unknown)}"


def test_flag_payloads_and_mechanisms_exist() -> None:
    """Likewise for chemistry: a flag naming a payload the enumerator cannot produce
    would never fire."""
    from adctox.design.enumerate import DesignSpace

    space = DesignSpace()
    known_payloads = set(space.payloads)
    known_mechs = {p["mechanism"] for p in space.payloads.values()}
    flags, _ = load_flags()
    for f in flags:
        assert not (f.payloads - known_payloads), f.id
        assert not (f.mechanisms - known_mechs), f.id


def test_tier_values_are_declared_in_the_config() -> None:
    doc = yaml.safe_load(CONF.read_text(encoding="utf-8"))
    declared = set(doc["tier_order"])
    assert {f["tier"] for f in doc["flags"]} <= declared


def test_every_flag_fires_for_its_own_declared_inputs() -> None:
    """A rule that never fires on its own declaration is dead and looks alive.

    This caught a real mistake: a hand-run necessity check passed condition ids the flags
    do not key on and reported two rules as "confirmatory" when they had simply not
    applied -- a false reassurance that the model was covering those cases by itself.
    """
    flags, _ = load_flags()
    for spec in flags:
        mech = sorted(spec.mechanisms)[0]
        payload = sorted(spec.payloads)[0]
        applied = applicable(mech, payload, set(spec.comorbidities), enabled=True)
        assert spec.axis in applied, (
            f"{spec.id} declares mechanism {mech}, payload {payload} and comorbidities "
            f"{sorted(spec.comorbidities)}, yet does not fire on {spec.axis} for exactly "
            "those inputs"
        )
        assert any(f.id == spec.id for f in applied[spec.axis])
