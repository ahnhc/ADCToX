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
PAGE = ROOT / "web" / "index.html"


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


def test_the_page_does_not_hold_its_own_target_list() -> None:
    page = PAGE.read_text(encoding="utf-8")
    assert "ont.targets" in page, "the page is not reading the served list"
    # Two gene symbols that only ever appeared inside the hardcoded array.
    for literal in ('"TNFRSF17"', '"IL3RA"', '"CD79B"'):
        assert literal not in page, (
            f"{literal} is still written into the page; the list is hardcoded again"
        )


def test_the_model_card_is_served() -> None:
    """The plan listed `/model-card` and it was never built, so the one document opening
    with "the model does not beat a base-rate baseline on any of six evaluations" was
    reachable only by reading the repository."""
    r = TestClient(app).get("/api/v1/model-card")
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert body.startswith("# Model card"), body[:80]
    # Served verbatim: a summary of a limitations document is what such a document exists
    # to prevent.
    assert body == (ROOT / "docs" / "MODEL_CARD.md").read_text(encoding="utf-8")
    assert "does not beat a base-rate baseline" in body
    assert "It does not rank" in body
