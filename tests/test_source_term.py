"""`b_combo` was estimating which corpus an arm came from.

Every one of the 139 combination arms is a ClinicalTrials.gov arm and none of the 194
literature arms is a combination, so `is_combination` and `is_literature` correlate at
-0.53. Without a source term, `b_combo` therefore estimates "registry combination against
everything else" rather than "combination against monotherapy", and its posterior mean went
from +0.195 on the registry corpus to **+1.091** on the expanded one -- the reference group
changing rather than combinations getting worse. The report was quoting it as "combination
arms do report higher rates".

A 150-draw smoke fit with the source term added:

    b_combo   +1.091  ->  +0.512
    b_source      --   ->  -0.924

So a literature arm reports about 0.9 logit lower than a registry arm of the same chemistry,
which is what a selected table with a reporting cut should do, and `b_combo` halves. It is a
nuisance control in the same sense as `b_thresh`, which section 5b already shows is
substantially absorbing trial-level reporting practice rather than correcting censoring.

Three cells over two parameters, so both are estimable: literature monotherapy, registry
monotherapy, registry combination.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from adctox.model.dataset import load
from adctox.model.forward import model, n_free_parameters
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "processed"
FULL = REGISTRY / "with_literature_final"
AXES = list(default_taxonomy().axis_order)


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_confound_this_term_exists_for_is_still_present() -> None:
    """If the corpus ever gains a literature combination arm or loses its registry ones,
    the correlation changes and this term's justification has to be reread rather than
    assumed."""
    data = load(FULL, AXES, kind="other")
    combo, lit = data.arm_combo, data.arm_is_literature
    assert combo.std() > 0 and lit.std() > 0
    r = float(np.corrcoef(combo, lit)[0, 1])
    assert r < -0.3, r
    # The separation is one-sided and complete: no literature arm is a combination.
    assert float(combo[lit == 1].sum()) == 0.0
    assert float(combo[lit == 0].sum()) > 100


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_indicator_matches_the_corpus_it_describes() -> None:
    data = load(FULL, AXES, kind="other")
    arms = pd.read_parquet(FULL / "arms.parquet").set_index("arm_key")
    expected = arms.loc[list(data.arm_keys), "source"].notna().astype(float).to_numpy()
    assert np.array_equal(data.arm_is_literature, expected)
    registry = load(REGISTRY, AXES, kind="other")
    assert float(registry.arm_is_literature.sum()) == 0.0


@pytest.mark.skipif(not (REGISTRY / "arms.parquet").exists(), reason="run `make corpus`")
def test_the_term_is_not_sampled_where_it_has_no_data() -> None:
    """On the registry-only corpus every arm is a registry arm. A coefficient sampled there
    would draw its prior, contribute nothing to the linear predictor, and add a row to the
    seed-agreement table -- which is read as a convergence diagnostic and would then be
    reporting on a parameter the fit never estimated."""
    import jax
    from numpyro.infer import MCMC, NUTS

    registry = load(REGISTRY, AXES, kind="other")
    mcmc = MCMC(NUTS(model, max_tree_depth=4), num_warmup=2, num_samples=2,
                num_chains=1, progress_bar=False)
    mcmc.run(jax.random.PRNGKey(0), data=registry)
    assert "b_source" not in mcmc.get_samples()
    assert "b_combo" in mcmc.get_samples()


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_term_is_sampled_and_counted_where_it_does() -> None:
    import jax
    from numpyro.infer import MCMC, NUTS

    data = load(FULL, AXES, kind="other")
    mcmc = MCMC(NUTS(model, max_tree_depth=4), num_warmup=2, num_samples=2,
                num_chains=1, progress_bar=False)
    mcmc.run(jax.random.PRNGKey(0), data=data)
    assert "b_source" in mcmc.get_samples()

    # And it is nuisance, not design: it describes the reporting, not the chemistry. The
    # count is checked against its own formula rather than against the other corpus's,
    # because the two corpora also differ in trials and agents and an arithmetic chain
    # across both is how a wrong assertion passes.
    counts = n_free_parameters(data)
    assert counts["design"] == 100
    # `b_source`, the 14-axis deviation vector and its scale.
    assert counts["nuisance"] == (
        2 + (1 + len(AXES) + 1) + len(data.trials) + len(data.agents) + 5
    )

    registry = load(REGISTRY, AXES, kind="other")
    reg_counts = n_free_parameters(registry)
    assert reg_counts["design"] == 100
    assert reg_counts["nuisance"] == 2 + len(registry.trials) + len(registry.agents) + 5


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_source_gap_is_axis_specific_and_the_model_says_so() -> None:
    """One intercept was the right first move and the wrong final one.

    Measured on the agents with arms from both sources -- which holds the chemistry fixed,
    so the gap is reporting and not drug -- the literature-minus-registry gap is strongly
    heterogeneous across organ axes, with a between-axis scale on the order of `tau_mech`.

    The direction is what makes it a specification error rather than noise: papers report
    *more* than the registry on the axes those papers are about, ocular above all, and
    *less* on the background organs that fall below a "most common adverse events" cut.
    With one shift the remainder goes into `mech_axis`, because literature arms are not
    spread evenly across mechanisms.

    What this test does *not* pin is which background axis happens to sit at the minimum.
    It used to assert `min_axis == "cardiovascular"`, and the corpus rebuild moved it to
    pulmonary -- a transcript of one corpus masquerading as a claim, which is negative
    result 38 inside the test suite. The claim is that the extremes are a signature axis
    and a background axis, and that is what is checked.
    """
    import json

    artefact = ROOT / "artifacts" / "source_axis_heterogeneity.json"
    if not artefact.exists():
        pytest.skip("run `make source-axis`")
    doc = json.loads(artefact.read_text(encoding="utf-8"))
    summary = doc["summary"]
    assert summary["agents_with_both_sources"] >= 10, summary
    assert summary["p"] < 1e-6, summary
    assert summary["between_axis_sd"] > 0.4, summary

    # Organs a paper about an ADC is written around, against organs it mentions only if a
    # frequency cut forces it. The split is the claim; which member of each set lands at the
    # extreme is a property of the corpus.
    SIGNATURE = {"ocular", "dermatologic", "pulmonary", "neurologic"}
    BACKGROUND = {"cardiovascular", "renal", "musculoskeletal", "metabolic_endocrine",
                  "hepatic", "gastrointestinal", "otologic"}
    assert summary["max_axis"] in SIGNATURE, summary["max_axis"]
    assert summary["min_axis"] in SIGNATURE | BACKGROUND, summary["min_axis"]

    gaps = {r["axis"]: r["gap_logit"] for r in doc["axes"]}
    # Ocular is the one axis whose direction is the finding rather than an example: papers
    # about ADCs foreground corneal toxicity and the registry does not.
    assert gaps.get("ocular", 0.0) > 0.5, gaps
    # And the background organs go the other way, as a set rather than individually.
    background = [v for k, v in gaps.items() if k in BACKGROUND]
    assert background and sum(background) / len(background) < 0.0, gaps


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_the_axis_deviation_is_sampled_centred_and_only_where_it_applies() -> None:
    """`b_source` carries the mean and `source_axis` the deviations, so the two are not
    competing for the same level -- the same split the mechanism and cleavability terms use.
    """
    import jax
    import numpy as np
    from numpyro.infer import MCMC, NUTS

    data = load(FULL, AXES, kind="other")
    mcmc = MCMC(NUTS(model, max_tree_depth=4), num_warmup=4, num_samples=8,
                num_chains=1, progress_bar=False)
    mcmc.run(jax.random.PRNGKey(0), data=data)
    draws = mcmc.get_samples()
    assert "tau_source" in draws and "source_axis" in draws
    sa = np.asarray(draws["source_axis"])
    assert sa.shape[1] == len(AXES)
    # Centred by construction, so it cannot shift the overall level.
    assert np.allclose(sa.mean(axis=1), 0.0, atol=1e-5), sa.mean(axis=1)[:3]

    registry = load(REGISTRY, AXES, kind="other")
    reg = MCMC(NUTS(model, max_tree_depth=4), num_warmup=4, num_samples=8,
               num_chains=1, progress_bar=False)
    reg.run(jax.random.PRNGKey(0), data=registry)
    assert "tau_source" not in reg.get_samples()
    assert "source_axis" not in reg.get_samples()


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(), reason="run `make pmc-merge`")
def test_no_coefficient_is_confounded_with_the_source_and_unhandled() -> None:
    """The audit's point is that two confounds were found and fixed and the rest are clear.

    Both were found by the same question asked twice -- a coefficient moved when the corpus
    grew, so what is it measuring? -- which is a reason to check the rest rather than a
    reason to stop. Every arm-level covariate is measured against the source indicator by
    the two things that decide separability: how much it tracks the source, and whether it
    still varies *inside* each corpus, which is what identifies it when the source term is
    also in the model.

    `b_combo` is the only one that separates completely, and it is handled. If another ever
    joins it, this fails rather than the model quietly estimating the corpus again.
    """
    import json

    artefact = ROOT / "artifacts" / "source_confounding.json"
    if not artefact.exists():
        pytest.skip("run `make source-confounding`")
    doc = json.loads(artefact.read_text(encoding="utf-8"))
    summary = doc["summary"]

    assert summary["confounded_and_unaddressed"] == [], summary
    assert "b_combo (arm_combo)" in summary["confounded"], summary
    # Every mechanism level appears in both corpora, so the mechanism-by-axis term and the
    # source term are separately identified rather than competing for the same contrast.
    assert summary["mechanism_levels_separated_by_source"] == [], summary
    assert summary["smallest_mechanism_cell"] >= 1, summary
    # And the covariates the audit calls clear have to actually be clear, not merely
    # unflagged because the thresholds are loose.
    clear = [c for c in doc["coefficients"] if not c["confounded"]]
    assert len(clear) >= 4, clear
    for c in clear:
        assert abs(c["correlation_with_source"]) < 0.3, c
        assert c["within_source_variance_share"] > 0.9, c


def test_the_audit_covers_the_agent_random_effect_not_only_coefficients() -> None:
    """The confound the audit was built to find lived where the audit did not look.

    `make source-confounding` scored every arm-level *coefficient* for separability against
    the reporting source, which is where results 33 and 35 came from. `u_agent` is a random
    effect, so it was outside that loop -- and it is the term with the worst separability
    problem of the three: 15 of the 32 agents have arms from one source only, which makes
    their intercept and the source indicator perfectly collinear. See negative result 39.
    """
    import json
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "artifacts" / "source_confounding.json"
    if not path.exists():
        return  # `make source-confounding` has not run in this tree
    agent = json.loads(path.read_text(encoding="utf-8"))["summary"].get("agent_level")
    assert agent, "the audit no longer reports the agent level"

    rows = agent["agents"]
    assert len(rows) == agent["n_agents"]
    # The three categories partition the agents, so a drifting classifier shows up here
    # rather than in a conclusion.
    assert (
        agent["n_both_sources"] + agent["n_literature_only"] + agent["n_registry_only"]
        == agent["n_agents"]
    )
    for r in rows:
        expected = (
            "both" if r["registry_arms"] and r["literature_arms"]
            else "literature_only" if r["literature_arms"]
            else "registry_only"
        )
        assert r["source"] == expected, r
    single = [r for r in rows if r["source"] != "both"]
    assert agent["n_single_source_single_arm"] == sum(
        1 for r in single if r["registry_arms"] + r["literature_arms"] == 1
    )


def test_the_agent_level_reading_follows_the_counts() -> None:
    """Derived, because a stored conclusion beside a changing count is negative result 38."""
    import json
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "artifacts" / "source_confounding.json"
    if not path.exists():
        return
    agent = json.loads(path.read_text(encoding="utf-8"))["summary"]["agent_level"]
    frac = agent["fraction_single_source"]
    reading = agent["reading"]
    n_single = agent["n_agents"] - agent["n_both_sources"]
    assert abs(frac - n_single / agent["n_agents"]) < 1e-9
    if frac == 0.0:
        assert "No agent is confined" in reading
    elif frac == 1.0:
        assert "Every agent" in reading
    else:
        assert f"{n_single} of {agent['n_agents']}" in reading
