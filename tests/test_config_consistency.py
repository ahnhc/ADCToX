"""Cross-file consistency between the config files.

These exist because a gap between two of them was not inert. `conf/design_space.yaml`
listed exatecan while `conf/adc_registry.yaml` -- which holds only the 18 agents that
exist -- did not, and the payload -> family map was built from the registry alone. So
exatecan had no family, and the product contradicted itself out loud: the enumerator
admitted exatecan designs under its Tier-1 gate and ranked them, while /assess called the
same chemistry novelty tier 2, a tier the documentation says is not supported, and emitted
a warning naming the empty string as a payload family.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONF = Path(__file__).resolve().parents[1] / "conf"


def _load(name: str) -> dict:
    return yaml.safe_load((CONF / name).read_text(encoding="utf-8"))


def test_every_design_space_payload_declares_a_family():
    """Without this the family is silently empty and the novelty tier goes wrong."""
    for payload, spec in _load("design_space.yaml")["payloads"].items():
        assert spec.get("family"), f"{payload} has no family in design_space.yaml"
        assert spec.get("mechanism"), f"{payload} has no mechanism"


def test_design_space_and_registry_agree_on_family_and_mechanism():
    """The registry stays the cross-check on the design space wherever both define a
    payload. Either file alone could drift; disagreeing is the failure."""
    ds = _load("design_space.yaml")["payloads"]
    for agent, spec in _load("adc_registry.yaml")["agents"].items():
        payload = spec.get("payload")
        if payload not in ds:
            continue
        assert ds[payload]["family"] == spec["payload_family"], (
            f"{payload}: design_space says {ds[payload]['family']}, registry says "
            f"{spec['payload_family']} (via {agent})"
        )
        assert ds[payload]["mechanism"] == spec["mechanism"], (
            f"{payload}: mechanism disagrees between the two files (via {agent})"
        )


def test_every_payload_mechanism_is_declared_in_the_frozen_taxonomy():
    """The mechanism taxonomy was frozen before extraction; a payload naming a mechanism
    outside it would be silently unmodelled."""
    known = set(_load("mechanism_taxonomy.yaml")["mechanisms"])
    for payload, spec in _load("design_space.yaml")["payloads"].items():
        assert spec["mechanism"] in known, (
            f"{payload} declares mechanism {spec['mechanism']!r}, absent from the frozen "
            f"taxonomy {sorted(known)}"
        )
    for agent, spec in _load("adc_registry.yaml")["agents"].items():
        assert spec["mechanism"] in known, f"{agent}: {spec['mechanism']!r} not in taxonomy"


def test_the_family_map_covers_both_files():
    """The runtime map must resolve every payload either file can produce."""
    from adctox.pipeline import _FAMILY_OF

    for payload in _load("design_space.yaml")["payloads"]:
        assert _FAMILY_OF.get(payload), f"{payload} unresolved by _FAMILY_OF"
    for spec in _load("adc_registry.yaml")["agents"].values():
        if spec.get("payload"):
            assert _FAMILY_OF.get(spec["payload"]), f"{spec['payload']} unresolved"


def test_a_payload_no_agent_carries_still_resolves_to_a_real_family():
    """The exatecan case, pinned by name because it is the one that broke.

    It is clinically precedented, so the enumerator is right to admit it; it is a
    camptothecin, so its estimate should come from that family rather than from nothing.
    """
    from adctox.pipeline import _FAMILY_OF

    registry = _load("adc_registry.yaml")["agents"]
    carried = {s.get("payload") for s in registry.values()}
    uncarried = set(_load("design_space.yaml")["payloads"]) - carried
    assert "exatecan" in uncarried, (
        "exatecan is now carried by a registry agent; this test's premise has changed"
    )
    for payload in uncarried:
        fam = _FAMILY_OF[payload]
        families = {s["payload_family"] for s in registry.values()}
        assert fam in families, (
            f"{payload} resolves to family {fam!r}, which no corpus agent has, so its "
            "estimate would fall back to the mechanism without saying so"
        )


def test_every_linker_handle_pairing_is_reachable():
    """A payload whose handle no linker accepts can never be enumerated, which would make
    it dead config that looks like an option."""
    ds = _load("design_space.yaml")
    # Each linker declares one `handle`, the payload attachment chemistry it accepts.
    accepted = {spec["handle"] for spec in ds["linkers"].values()}
    for payload, spec in ds["payloads"].items():
        assert spec["handle"] in accepted, (
            f"{payload} has handle {spec['handle']!r}, which no linker accepts, so it can "
            "never be enumerated -- dead config that reads as an available option"
        )
    # And the reverse: a linker whose handle no payload has is equally unreachable.
    payload_handles = {spec["handle"] for spec in ds["payloads"].values()}
    for linker, spec in ds["linkers"].items():
        assert spec["handle"] in payload_handles, (
            f"linker {linker} accepts handle {spec['handle']!r}, which no payload has"
        )


def test_propose_and_assess_cannot_disagree_about_novelty_tier():
    """`propose` hardcodes tier 1; `assess` derives it from the fitted corpus.

    Both are right today, and nothing holds them together. `propose` says tier 1 because
    the enumerator admits a component only with clinical precedent; `assess` says tier 1
    only when the payload's family is in the fitted corpus. Add a design-space payload
    whose family no fitted agent carries and the product would offer a ranked candidate
    as tier 1 while calling the same chemistry tier 2 on the other endpoint -- which is
    exactly the contradiction the exatecan gap produced, in a new place.

    The fitted corpus is the posterior's family list, not the registry's: the registry has
    an immunotoxin that the design matrix cannot represent and the model therefore drops.
    """
    from pathlib import Path

    from adctox.model.predict import Posterior

    art = Path(__file__).resolve().parents[1] / "artifacts" / "posterior_other.npz"
    if not art.exists():
        pytest.skip("no posterior built")
    fitted = set(Posterior.load(art).families)
    ds = _load("design_space.yaml")["payloads"]
    missing = {
        payload: spec["family"]
        for payload, spec in ds.items()
        if spec["family"] not in fitted
    }
    assert not missing, (
        f"these design-space payloads have families absent from the fitted corpus: "
        f"{missing}. The enumerator would rank them as tier 1 while /assess reports them "
        f"as tier 2. Fitted families: {sorted(fitted)}"
    )


def test_a_registry_agent_may_have_no_stated_dar() -> None:
    """A latent assumption that new data broke.

    `_nearest_real_adc` called `float(spec["dar"])` unconditionally, which held while the
    registry contained only approved drugs whose labels state a DAR. Curating 16 agents
    from the primary literature put 11 entries in with `dar: null` -- the figure is simply
    not stated in their papers, and guessing one would feed a regression coefficient a
    number presented as measured. The call then raised TypeError on every proposal.

    An unknown DAR counts as a *difference*, not a match. The comparison is a Hamming
    distance over design slots, so letting an unknown slot pass free would make an agent
    with missing data look closer to a design than one with a complete record.
    """
    from adctox.design.enumerate import Design
    from adctox.pipeline import _nearest_real_adc

    registry = _load("adc_registry.yaml")["agents"]
    without_dar = [k for k, v in registry.items() if v.get("dar") is None]
    assert without_dar, (
        "this test is vacuous unless some registry agent lacks a DAR; if the registry "
        "ever becomes complete, keep the None branch anyway -- the next curated agent "
        "will reintroduce it"
    )

    design = Design(
        target="ERBB2", payload="MMAE", mechanism="tubulin", linker="vc_PABC",
        cleavable=True, conjugation="interchain_cysteine", dar=4.0, isotype="IgG1",
        masking="none", has_unapproved_component=False,
    )
    sentence, diffs = _nearest_real_adc(design, registry)
    assert sentence and isinstance(diffs, str)
    # And an agent with no DAR never wins on a design whose DAR is known, because the
    # unknown slot costs it a difference.
    for agent in without_dar:
        _, lone = _nearest_real_adc(design, {agent: registry[agent]})
        assert "DAR unknown" in lone, (agent, lone)


def test_propose_and_assess_explain_a_number_the_same_way() -> None:
    """A gap that became a worse gap before it was fixed.

    `/propose` listed only the three driver sources that fire *sometimes* -- a label rule,
    a target-expression flag, an exclusion enrichment -- and omitted the one that always
    applies. So an axis reporting `band_source: "model"` came back with an empty driver
    list: a patient's at-risk organ showing a band, a point estimate and a weight of 3.0
    with no account of any of them.

    The first fix was to add a driver builder to `/propose`, which would have left the two
    endpoints explaining one number two different ways -- `/assess` already had a full
    waterfall from `decompose`. Both now call `decompose`, and this test is the reason that
    stays true.
    """
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    profile = {
        "conditions": ["interstitial_lung_disease", "ckd_stage_3"],
        "cohort": {"age_band": "65_74", "sex": "female"},
    }
    proposed = client.post("/api/v1/propose", json={
        "comorbidity_profile": profile, "target_antigen": "ERBB2", "top_k": 3,
    })
    assert proposed.status_code == 200, proposed.text[:400]
    candidate = proposed.json()["candidates"][0]
    design = candidate["design"]

    assessed = client.post("/api/v1/assess", json={
        "design": {
            "target_antigen": design["target"], "payload": design["payload"],
            "linker": design["linker"], "conjugation": design["conjugation"],
            "dar": design["dar"], "isotype": design["isotype"],
            "masking": design["masking"],
        },
        "comorbidity_profile": profile,
    })
    assert assessed.status_code == 200, assessed.text[:400]

    def model_terms(organ_risks: list[dict], axis: str) -> list[tuple]:
        row = next(o for o in organ_risks if o["organ_axis"] == axis)
        return [
            (d["factor"], d["contribution"])
            for d in row["drivers"] if d["source"] == "model"
        ], row["point_estimate"]

    for axis in ("pulmonary", "renal", "haematologic"):
        p_terms, p_rate = model_terms(candidate["organ_risks"], axis)
        a_terms, a_rate = model_terms(assessed.json()["organ_risks"], axis)
        assert p_terms == a_terms, (axis, p_terms, a_terms)
        assert p_rate == a_rate, (axis, p_rate, a_rate)
        # And the model source must actually be present, which is the original defect.
        assert p_terms, f"{axis} has no model driver"
