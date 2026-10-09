"""An ordinal position for a rate, because a rate on its own is close to unreadable.

"Gastrointestinal 0.59, high" says less than "the third highest of the twenty-three
chemistries in this corpus". The plan asked for exactly this and banned percentiles: on
roughly twenty reference chemistries a percentile invents resolution the sample cannot
carry, so the figure is an ordinal with its denominator printed beside it.

The two rules that make it honest rather than decorative:

* it follows the band's table. An at-risk axis is banded on the serious table, and
  comparing a serious rate against common-table chemistries -- an order of magnitude larger
  -- would make every such row read as unusually safe.
* a registry agent with no stated DAR is left out, not given the corpus mean. Substituting
  a mean seats an agent at the centre of the comparison on the strength of a missing value,
  and twelve of the registry's conventional conjugates have no DAR in any source.
"""

from __future__ import annotations

import pathlib

import pytest

from adctox.api.main import _posterior, _serious_posterior
from adctox.model.comparator import (
    _registry_designs,
    axis_comparator,
    reference_count,
)

ROOT_ARMS = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "processed"
    / "arms.parquet"
)


def test_the_rank_is_an_ordinal_with_its_denominator() -> None:
    post = _posterior()
    n = reference_count(post)
    assert n > 10, n
    c = axis_comparator(post, "hepatic", 1.0)
    assert c["rank"] == 1, "a rate of 1.0 must be the highest"
    assert c["n"] == n + 1, "the denominator counts the queried design too"
    assert axis_comparator(post, "hepatic", 0.0)["rank"] == n + 1
    assert c["interpretation"] == "relative_ranking_only"
    assert "percentile" not in str(c).lower()


def test_a_tie_does_not_count_as_beating_the_tied_chemistry() -> None:
    """`>` and not `>=`: a design that exactly equals a reference rate is not above it."""
    post = _posterior()
    import numpy as np

    from adctox.model.comparator import _reference_matrix

    mat, names, _ = _reference_matrix(post)
    axis = "hepatic"
    col = mat[:, post.axes.index(axis)]
    worst = float(np.max(col))
    assert axis_comparator(post, axis, worst)["rank"] == 1


def test_an_agent_without_a_dar_is_excluded_and_counted() -> None:
    usable, n_conventional = _registry_designs()
    assert n_conventional > len(usable), (
        "no agent is being excluded, so the exclusion count cannot be meaningful"
    )
    c = axis_comparator(_posterior(), "hepatic", 0.2)
    assert c["n_excluded_for_missing_slots"] == n_conventional - len(usable)
    assert c["n_excluded_for_missing_slots"] > 0


def test_an_unknown_axis_returns_nothing_rather_than_a_number() -> None:
    assert axis_comparator(_posterior(), "not_an_axis", 0.2) is None


@pytest.mark.parametrize("endpoint", ["propose", "assess"])
def test_both_endpoints_compare_on_the_table_they_banded(endpoint: str) -> None:
    """The rule that stops a serious rate being ranked against common-table chemistries."""
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    if endpoint == "propose":
        body = {
            "comorbidity_profile": {
                "conditions": ["ckd_stage_4_5", "interstitial_lung_disease"],
            },
            "target_antigen": "ERBB2", "top_k": 3,
        }
        rows = client.post("/api/v1/propose", json=body).json()["candidates"][0][
            "organ_risks"
        ]
    else:
        body = {
            "design": {
                "target_antigen": "ERBB2", "payload": "DXd", "linker": "GGFG",
                "conjugation": "interchain_cysteine", "dar": 8.0,
                "isotype": "IgG1", "masking": "none",
            },
            "comorbidity_profile": {"conditions": ["interstitial_lung_disease"]},
        }
        rows = client.post("/api/v1/assess", json=body).json()["organ_risks"]

    seen_serious = False
    for r in rows:
        cm = r.get("comparator")
        if cm is None:
            continue
        expected = "serious" if r["band_basis"] == "serious" else "other"
        assert cm["table"] == expected, (r["organ_axis"], r["band_basis"], cm["table"])
        seen_serious |= r["band_basis"] == "serious"
    assert seen_serious, "the at-risk axes should be banded on the serious table"


def test_the_serious_table_is_not_ranked_against_the_common_one() -> None:
    """The failure the table rule prevents, stated as a number.

    Serious rates are an order of magnitude smaller, so a serious rate compared against
    common-table chemistries lands at or near the bottom of the ranking whatever it is.
    """
    post, spost = _posterior(), _serious_posterior()
    if spost is None:
        pytest.skip("no serious posterior")
    axis = "pulmonary"
    # A serious rate that is in fact the worst in the corpus on the serious table.
    import numpy as np

    from adctox.model.comparator import _reference_matrix

    s_mat, _, _ = _reference_matrix(spost)
    worst_serious = float(np.max(s_mat[:, spost.axes.index(axis)]))
    assert axis_comparator(spost, axis, worst_serious)["rank"] == 1
    wrong = axis_comparator(post, axis, worst_serious)
    assert wrong["rank"] > 1, (
        "the worst serious rate looks unremarkable against common-table chemistries, "
        "which is why the comparator follows the band's table"
    )


def test_the_interface_says_what_the_ordinal_is_not() -> None:
    """Law 7 of the project's own uncertainty rules: one sentence per screen says what the
    number is not.

    An ordinal position asserts that the ordering means something, and the measured skill of
    that ordering is a per-axis across-agent correlation of about 0.17 after the reporting
    conditions are removed from both series. Printing `#1 of 23` without that is the kind of
    false precision the rest of this interface was built to avoid.
    """
    import pathlib

    page = (
        pathlib.Path(__file__).resolve().parents[1] / "web" / "index.html"
    ).read_text(encoding="utf-8")
    block = page[page.index('class="cmp" title='):]
    block = block[: block.index("</span>")]
    assert "What this is not" in block
    assert "0.17" in block, "the measured correlation is not stated beside the rank"
    assert "noise" in block or "only the extremes" in block


def test_the_reference_set_is_the_registry_and_says_so() -> None:
    """Five of the 22 reference chemistries are absent from the 16-agent fit, so calling
    them "corpus chemistries" was wrong. They belong in the comparison -- their rates are
    out-of-corpus predictions exactly as the queried design's is, which is the consistent
    footing -- but the field has to say which it is."""
    import pandas as pd

    from adctox.model.comparator import _reference_matrix

    post = _posterior()
    _, names, _ = _reference_matrix(post)
    arms = pd.read_parquet(ROOT_ARMS) if ROOT_ARMS.exists() else None
    c = axis_comparator(post, "hepatic", 0.2)
    assert "corpus agent" not in c["basis"], c["basis"]
    assert "registry" in c["basis"]
    if arms is not None:
        fitted = set(arms["agent"].dropna().unique())
        outside = [n for n in names if n not in fitted]
        assert outside, "no reference chemistry is outside the fit; the claim is stale"
    # The split is reported where the posterior records which agents it saw, and is null
    # rather than zero where it does not.
    assert c["n_reference_in_fitted_corpus"] is None or (
        0 < c["n_reference_in_fitted_corpus"] <= c["n_reference_chemistries"]
    )


def test_the_split_is_reported_once_the_posterior_carries_its_agents() -> None:
    """A posterior written before the agent list existed loads with an empty list, and
    empty must read as "not recorded" rather than "none of them"."""
    import dataclasses

    post = _posterior()
    assert post.agents == [] or isinstance(post.agents[0], str)
    with_agents = dataclasses.replace(post, agents=["trastuzumab emtansine"])
    c = axis_comparator(with_agents, "hepatic", 0.2)
    assert c["n_reference_in_fitted_corpus"] == 1, c["n_reference_in_fitted_corpus"]
