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
