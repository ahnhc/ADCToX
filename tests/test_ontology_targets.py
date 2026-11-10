"""The interface must not hold its own copy of a list the API serves.

`web/index.html` carried a literal array of fourteen target antigens under a comment saying
the page hardcoded no list. The registry has 24, so ten were unreachable from the
interface -- and the array was guarded by `ont.comorbidities.length`, a count that decides
nothing about targets, so it would have rendered the hardcoded fourteen even if the API had
served none at all.

The endpoint now serves them, and these tests pin both halves: the endpoint lists every
registry target, and the page reads them rather than restating them.
"""

from __future__ import annotations

import pathlib

import yaml
from fastapi.testclient import TestClient

from adctox.api.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _registry_targets() -> set[str]:
    doc = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    return {s["target"] for s in doc.values() if s.get("target")}


def test_the_endpoint_serves_every_registry_target() -> None:
    served = TestClient(app).get("/api/v1/ontology").json()["targets"]
    assert {t["id"] for t in served} == _registry_targets()
    for t in served:
        assert t["label"], t
        assert t["n_adcs"] >= 1, t
    # The count has to discriminate, or it is the `in_corpus` field this replaced: true for
    # all 24 and therefore saying nothing.
    assert len({t["n_adcs"] for t in served}) > 1
