"""A served posterior has to name the corpus it was fitted on.

`/version` reported the corpus named in `forward_other_metrics.json`. That is the *fit's
evaluation* artefact, and the posterior the product predicts from is written by a separate
run -- so the two can describe different corpora, and the endpoint would name one this
deployment does not predict from.

That became load-bearing when the corpora multiplied. Five exist now -- registry,
literature-extended, explicit-cuts-only, agent-restricted, and merged with a
hand-transcribed database -- and they disagree about `sigma_agent` by a factor of three,
which is the parameter the prediction path draws from for every new design. Two deployments
serving different posteriors were indistinguishable through the API.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adctox.model.predict import Posterior  # noqa: E402


def _tiny(**over) -> Posterior:
    n, a, m = 4, 3, 2
    kw = dict(
        mu_axis=np.zeros((n, a)), mech_axis=np.zeros((n, m, a)),
        family_axis=np.zeros((n, m, a)), cleav_axis=np.zeros((n, a)),
        b_dar=np.zeros(n), b_combo=np.zeros(n), sigma_agent=np.ones(n),
        axes=["x", "y", "z"], mechanisms=["p", "q"], families=["p", "q"],
        dar_mean=4.0, cleavable_mean=0.5,
        evidence_agents=np.zeros((m, a), dtype=int),
        evidence_arms=np.zeros((m, a), dtype=int),
        kind="other", band_edges=(0.1, 0.3), agents=["one", "two"],
    )
    kw.update(over)
    return Posterior(**kw)


def test_the_stamp_survives_a_round_trip(tmp_path) -> None:
    stamp = {"revision": "abc123", "dirty": False, "snapshot": "2026-10-07",
             "corpus": "4,186 cells over 299 arms", "n_agents": 22, "kind": "other"}
    p = tmp_path / "post.npz"
    _tiny(provenance=stamp).save(p)
    assert Posterior.load(p).provenance == stamp


def test_a_posterior_without_a_stamp_still_loads(tmp_path) -> None:
    """Tolerant like `agents`: a posterior written before the field existed must not fail.

    An empty stamp and a missing posterior are different statements, and the endpoint
    distinguishes them, so loading has to succeed in order for it to be able to.
    """
    p = tmp_path / "post.npz"
    _tiny().save(p)
    z = dict(np.load(p, allow_pickle=False))
    z.pop("provenance")
    np.savez_compressed(p, **z)
    loaded = Posterior.load(p)
    assert loaded.provenance == {}


def test_the_npz_stays_unpicklable(tmp_path) -> None:
    """The stamp is JSON in an array, not an object, so `allow_pickle=False` still holds.

    A pickled dict in an artefact is a code-execution surface in a file the product loads
    at startup, which is not a trade this needs to make for a provenance block.
    """
    p = tmp_path / "post.npz"
    _tiny(provenance={"revision": "abc", "nested": {"a": 1}}).save(p)
    z = np.load(p, allow_pickle=False)  # raises if anything in it needs pickling
    assert "provenance" in z.files
    assert Posterior.load(p).provenance["nested"] == {"a": 1}


def test_version_reports_the_served_posterior_and_flags_disagreement() -> None:
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    doc = TestClient(app).get("/api/v1/version").json()
    served = doc["served_posterior"]
    assert set(served) >= {"corpus", "n_agents", "revision", "snapshot", "stamped"}
    # The agreement flag is a three-valued answer and `None` means "cannot tell", which is
    # the honest value while a posterior predates the stamp.
    assert doc["served_and_evaluated_agree"] in (True, False, None)
    if not served["stamped"]:
        assert served["corpus"] is None
        assert doc["served_and_evaluated_agree"] is None
    # `corpus` is kept for existing callers and must name the served posterior wherever that
    # is known, never the evaluated fit in preference to it.
    if served["corpus"]:
        assert doc["corpus"] == served["corpus"]
    # And the agent count is derivable from the posterior itself, so it is never unknown.
    assert served["n_agents"] is None or served["n_agents"] > 0


def test_a_disagreement_between_served_and_evaluated_is_not_silent() -> None:
    """The failure mode the field exists for, constructed directly.

    If the served posterior says one corpus and the evaluation artefact says another, the
    endpoint must say so rather than print one of them.
    """
    import adctox.api.main as main

    served = {"corpus": "A", "n_agents": 7, "revision": "r", "snapshot": "s",
              "written_utc": "t", "script": "x"}
    fake = _tiny(provenance=served)
    main._version_info.cache_clear()
    original = main._posterior
    try:
        main._posterior = lambda: fake  # type: ignore[assignment]
        doc = main._version_info()
    finally:
        main._posterior = original  # type: ignore[assignment]
        main._version_info.cache_clear()
    assert doc["served_posterior"]["corpus"] == "A"
    assert doc["corpus"] == "A"
    evaluated = doc.get("evaluated_fit")
    if evaluated and evaluated.get("corpus"):
        assert doc["served_and_evaluated_agree"] is (evaluated["corpus"] == "A")


def test_a_target_is_recognised_by_either_of_its_names() -> None:
    """The registry keys on the gene symbol and a caller types the clinical name.

    14 of the registry's 26 target pairs differ -- ERBB2/HER2, TACSTD2/TROP2,
    TNFRSF17/BCMA, TNFRSF8/CD30, FOLR1/FRalpha among them -- and matching only the symbol
    told a caller asking about HER2 that the target was absent from a corpus holding eight
    HER2 ADCs. The membership question is whether an ADC has been built against the
    antigen, and the antigen has two names.
    """
    from adctox.api.main import _registry, _registry_targets

    targets = _registry_targets()
    pairs = {
        (str(spec["target"]).upper(), str(spec.get("target_label") or "").upper())
        for spec in _registry().values() if spec.get("target")
    }
    differing = [(g, l) for g, l in pairs if l and l != g]
    assert differing, "no target carries a label distinct from its symbol any more"
    for gene, label in pairs:
        assert gene in targets, gene
        if label:
            assert label in targets, (gene, label)


def test_a_target_nobody_has_built_against_is_still_reported_absent() -> None:
    """Widening the match must not make the check vacuous."""
    from adctox.api.main import _registry_targets

    assert "NOTATARGET" not in _registry_targets()
    assert "" not in _registry_targets()


def test_the_coverage_block_agrees_with_the_target_list() -> None:
    from fastapi.testclient import TestClient

    from adctox.api.main import _registry_targets, app

    client = TestClient(app)
    targets = _registry_targets()
    for name, expected in (("HER2", True), ("ERBB2", True), ("NOTATARGET", False)):
        resp = client.post("/api/v1/assess", json={
            "design": {"target_antigen": name, "payload": "DXd", "linker": "GGFG",
                       "conjugation": "interchain_cysteine", "dar": 8.0},
            "comorbidity_profile": {"conditions": []},
        })
        assert resp.status_code == 200, (name, resp.text[:200])
        assert resp.json()["coverage"]["target_in_corpus"] is expected, name
        assert (name.upper() in targets) is expected, name


def test_the_interface_posts_the_identifier_the_endpoint_matches_on() -> None:
    """The web page sends the gene symbol, which is why it never saw negative result 57.

    It posts `t.id` from `/ontology` and displays `label (symbol)`, so the page and the
    endpoint agreed and only direct API callers were told HER2 was absent. Pinned because
    the page switching to the label would be a silent behaviour change for every caller --
    and because the opposite direction, the endpoint narrowing again, is what the test above
    guards.
    """
    import pathlib as _p
    import re

    page = (_p.Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(
        encoding="utf-8"
    )
    # The option carries the symbol as its value and the label as its text.
    assert re.search(r'<option value="\$\{t\.id\}"', page), (
        "the target select no longer posts the gene symbol; the coverage check accepts "
        "both spellings now, but a change here is a change for every caller and should be "
        "deliberate"
    )
    assert "target_antigen: document.getElementById(\"target\").value" in page
