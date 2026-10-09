"""A cached posterior is reused only if it was fitted on exactly this corpus.

`_ensure_posterior` returned any file that existed. The corpus changed four times in one
session -- the serious-grid fix, two recovered DAR values, the outcome filter, the
agent-class filter -- and each time `make propose` would have served a posterior fitted on
the corpus before it, with nothing in the response to say so.

This project has already paid for that class of error once. A stale set of fold predictions,
adjusted against a different corpus's nuisance conditions, produced a permutation p-value of
0.0010 that was not real; the tell was that one mean matched the unadjusted one to four
decimal places. The guard built then checked fold predictions. This is the same guard on the
artefact the product actually serves.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "propose_demo", ROOT / "scripts" / "propose_demo.py"
)
demo = importlib.util.module_from_spec(SPEC)
sys.modules["propose_demo"] = demo
SPEC.loader.exec_module(demo)

from adctox.model.dataset import load  # noqa: E402
from adctox.model.predict import Posterior  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
AXES = list(default_taxonomy().axis_order)


@pytest.fixture(scope="module")
def data():
    if not (PROCESSED / "arms.parquet").exists():
        pytest.skip("run `make corpus`")
    return load(PROCESSED, AXES, kind="other")


def test_an_absent_posterior_is_refit(tmp_path, data) -> None:
    assert demo._why_refit(tmp_path / "nothing.npz", data) == "absent"


def test_a_posterior_with_no_agent_list_is_not_trusted(tmp_path, data) -> None:
    """The pre-existing artefacts are in this state, so the first run after this change
    refits once and every run after it can answer the question."""
    post = _fake(data, agents=[])
    path = tmp_path / "p.npz"
    post.save(path)
    why = demo._why_refit(path, data)
    assert why and "records no agent list" in why, why


def test_a_posterior_fitted_on_a_different_corpus_is_refit(tmp_path, data) -> None:
    post = _fake(data, agents=list(data.agents)[:-1] + ["an_agent_that_left"])
    path = tmp_path / "p.npz"
    post.save(path)
    why = demo._why_refit(path, data)
    assert why and "gone:" in why and "new:" in why, why


def test_a_posterior_fitted_on_this_corpus_is_reused(tmp_path, data) -> None:
    """The guard has to be satisfiable, or it is just a refit on every build."""
    post = _fake(data, agents=list(data.agents))
    path = tmp_path / "p.npz"
    post.save(path)
    assert demo._why_refit(path, data) is None


def test_a_changed_axis_order_is_caught(tmp_path, data) -> None:
    """Axis order is positional in every array the posterior carries, so a reordering that
    went unnoticed would silently permute fourteen organ systems."""
    post = _fake(data, agents=list(data.agents))
    post = dataclasses.replace(post, axes=list(reversed(post.axes)))
    path = tmp_path / "p.npz"
    post.save(path)
    assert demo._why_refit(path, data) == "the axis order has changed"


def _fake(data, agents: list[str], corpus: str | None = None) -> Posterior:
    """A posterior with the right shapes and arbitrary values. The guard reads labels
    only, so the draws need not come from a fit.

    `corpus` defaults to this data's own summary, because the guard now also requires a
    provenance stamp naming the corpus -- an unstamped posterior was served indefinitely
    while `/version` reported `corpus: null`, since the agent list matched (result 61).
    Passing a different string is how a test exercises the mismatch.
    """
    import numpy as np

    s, a = 4, len(data.axes)
    m, f = len(data.mechanisms), len(data.families)
    return Posterior(
        provenance={"corpus": data.summary() if corpus is None else corpus,
                    "n_agents": len(agents), "kind": "other"},
        mu_axis=np.zeros((s, a)), mech_axis=np.zeros((s, m, a)),
        family_axis=np.zeros((s, f, a)), cleav_axis=np.zeros((s, a)),
        b_dar=np.zeros(s), b_combo=np.zeros(s), sigma_agent=np.zeros(s),
        axes=list(data.axes), mechanisms=list(data.mechanisms),
        families=list(data.families), dar_mean=4.0, cleavable_mean=0.5,
        evidence_agents=np.zeros((m, a)), evidence_arms=np.zeros((m, a)),
        kind="other", band_edges=(0.01, 0.05), agents=agents,
    )


def test_an_unstamped_posterior_is_refitted(tmp_path, data) -> None:
    """Result 61: the field `/version` calls authoritative was empty and stayed empty.

    The guard compared the agent list and nothing else, so a posterior written before the
    stamp existed satisfied it on every build and the product served numbers it could not
    attribute to a corpus.
    """
    post = _fake(data, agents=list(data.agents))
    post.provenance = {}
    path = tmp_path / "p.npz"
    post.save(path)
    reason = demo._why_refit(path, data)
    assert reason and "no provenance stamp" in reason


def test_a_posterior_stamped_with_another_corpus_is_refitted(tmp_path, data) -> None:
    """Same agents, different corpus -- which is exactly the absences-dropped pair."""
    post = _fake(data, agents=list(data.agents), corpus="SOME OTHER CORPUS")
    path = tmp_path / "p.npz"
    post.save(path)
    reason = demo._why_refit(path, data)
    assert reason and "different corpus" in reason


def test_the_served_posterior_on_disk_is_stamped_and_agrees_with_the_evaluated_fit() -> None:
    """The product's own state rather than a fixture.

    `/version` reports `served_and_evaluated_agree`, and it can only be `true` if the
    posterior carries a stamp. This is the assertion behind that field.
    """
    import json

    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "posterior_other.npz"
    metrics = root / "artifacts" / "forward_other_metrics.json"
    if not path.exists() or not metrics.exists():
        return
    post = Posterior.load(path)
    assert post.provenance.get("corpus"), (
        "the served posterior carries no corpus stamp, so the product cannot say which "
        "corpus produced the numbers it serves"
    )
    evaluated = json.loads(metrics.read_text(encoding="utf-8")).get("corpus")
    assert post.provenance["corpus"] == evaluated, (
        "the served posterior and the evaluated fit describe different corpora:\n"
        f"    served:    {post.provenance['corpus']}\n"
        f"    evaluated: {evaluated}"
    )
