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
    assert counts["nuisance"] == 3 + len(data.trials) + len(data.agents) + 5

    registry = load(REGISTRY, AXES, kind="other")
    reg_counts = n_free_parameters(registry)
    assert reg_counts["design"] == 100
    assert reg_counts["nuisance"] == 2 + len(registry.trials) + len(registry.agents) + 5
