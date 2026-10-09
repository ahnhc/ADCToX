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

    Measured on the 12 agents with arms from both sources -- which holds the chemistry fixed,
    so the gap is reporting and not drug -- the literature-minus-registry gap runs from
    -1.16 logit on cardiovascular to +1.79 on ocular, heterogeneity Q = 80 on 11 degrees of
    freedom, p = 1.5e-12, between-axis standard deviation about 0.72.

    The direction is what makes it a specification error rather than noise: papers report
    *more* than the registry on ocular and dermatologic, which are the signature findings
    those papers are about, and *less* on cardiovascular and the other background organs,
    which fall below a "most common adverse events" cut. With one shift the remainder goes
    into `mech_axis`, because literature arms are not spread evenly across mechanisms.
    """
    import json

    artefact = ROOT / "artifacts" / "source_axis_heterogeneity.json"
    if not artefact.exists():
        pytest.skip("run `make source-axis`")
    summary = json.loads(artefact.read_text(encoding="utf-8"))["summary"]
    assert summary["agents_with_both_sources"] >= 10, summary
    assert summary["p"] < 1e-6, summary
    assert summary["between_axis_sd"] > 0.4, summary
    # The two ends, which are the interpretable part.
    assert summary["min_axis"] == "cardiovascular", summary
    assert summary["max_axis"] == "ocular", summary


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
