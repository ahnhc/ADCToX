"""An absent organ is only informative when the reporting cut was stated.

A ClinicalTrials.gov record with `frequencyThreshold = 5` means every event above 5% is
listed, so an organ that does not appear has a rate below 5% and the censored likelihood is
exactly right. A paper table captioned "most common adverse events" with no stated cut
means the author *selected* rows, and absence then says almost nothing -- the selection was
not a threshold on the rate.

The first ablation round measured the cost of conflating them. Literature arms took the
observed share from 86.2% to 63.6%, about 1,560 of their 2,450 cells are censored, 83% of
those carry a boundary derived from the arm's own minimum printed rate, and the
leave-one-agent-out delta went from -0.0422 to -0.0782. The model was told "below X" with X
too large, thousands of times.

Dropping those absences is not the same as dropping the arms. The explicit-threshold-only
corpus keeps 67 of 414 paper arms and lands at 21 agents; this keeps every arm and every
observed cell, and lands at 31 agents with the registry's own observed/censored balance.
(32 agents publish a machine-readable per-organ table; one of them publishes no any-grade
column anywhere, so the any-grade corpus holds 31. The two counts answer different
questions and both appear in the report.)
"""

from __future__ import annotations

import pathlib

import pytest

import adctox.model.dataset as ds
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
FULL = ROOT / "data" / "processed" / "with_literature_final"


@pytest.fixture(scope="module")
def axes() -> list[str]:
    return list(default_taxonomy().axis_order)


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(),
                    reason="run `make pmc-merge`")
def test_dropping_absences_keeps_every_arm_and_every_observation(axes) -> None:
    """The point of the option. Dropping arms would cost agents, which is the one thing
    the corpus is short of."""
    kept = ds.load(FULL, axes, kind="other", drop_uninformative_absences=False)
    dropped = ds.load(FULL, axes, kind="other", drop_uninformative_absences=True)

    assert dropped.n_arms == kept.n_arms
    assert len(dropped.agents) == len(kept.agents)
    observed_kept = int((kept.status == 0).sum())
    observed_dropped = int((dropped.status == 0).sum())
    assert observed_dropped == observed_kept, "no observation may be lost"
    # Only censored cells go.
    assert dropped.n_cells < kept.n_cells
    assert len(dropped.censored_idx) < len(kept.censored_idx)


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(),
                    reason="run `make pmc-merge`")
def test_it_restores_the_registry_s_observed_share(axes) -> None:
    """The diagnosis, stated as a threshold. The registry corpus is 86.2% observed; the
    literature-augmented one falls to 63.6%, which is what made it worse than its baseline.
    Dropping the uninformative absences brings it back above 80%."""
    dropped = ds.load(FULL, axes, kind="other", drop_uninformative_absences=True)
    share = int((dropped.status == 0).sum()) / int(dropped.n_cells)
    assert share > 0.78, share


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(),
                    reason="run `make pmc-merge`")
def test_registry_arms_keep_their_censored_cells(axes) -> None:
    """The option must not touch arms whose cut was stated. Those absences are real
    information and removing them would throw away the censoring treatment that section 5b
    measured as load-bearing."""
    import pandas as pd

    arms = pd.read_parquet(FULL / "arms.parquet")
    registry_arms = arms[arms.get("source").isna()] if "source" in arms else arms
    assert len(registry_arms) > 0
    # Every registry arm has a stated threshold or none at all, never a bounded one.
    if "threshold_is_upper_bound" in arms.columns:
        bounded = arms["threshold_is_upper_bound"].fillna(False).astype(bool)
        assert not bounded[registry_arms.index].any(), (
            "a ClinicalTrials.gov arm is marked as having a bounded threshold, which "
            "would make this option drop informative absences"
        )
    dropped = ds.load(FULL, axes, kind="other", drop_uninformative_absences=True)
    # Censoring survives for the arms that deserve it.
    assert len(dropped.censored_idx) > 500


def test_the_option_is_off_by_default(axes) -> None:
    """A modelling choice this consequential must be asked for. The default keeps the
    previous behaviour so the ablation's two arms stay comparable."""
    import inspect

    sig = inspect.signature(ds.build)
    assert sig.parameters["drop_uninformative_absences"].default is False


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(),
                    reason="run `make pmc-merge`")
def test_a_paper_s_serious_table_is_not_treated_as_complete(axes) -> None:
    """`seriousEvents` is complete on ClinicalTrials.gov, where the registry lists every
    serious event with no frequency cut, so an absent organ there is a true zero. A
    *paper's* serious-adverse-event table is selected like any other table. Asserting a
    zero is a stronger false statement than asserting a bound, so the completeness
    assumption holds only for arms whose cut is not merely a bound."""
    import pandas as pd

    arms = pd.read_parquet(FULL / "arms.parquet")
    bounded = arms["threshold_is_upper_bound"].fillna(False).astype(bool)
    paper_serious = arms[bounded & arms["n_at_risk_serious"].notna()]
    assert len(paper_serious) > 0, "no bounded arm publishes a serious table"

    kept = ds.load(FULL, axes, kind="serious", drop_uninformative_absences=False)
    # Their absences are censored, not zero.
    assert len(kept.censored_idx) > 0, (
        "a bounded paper arm's absent organ is still being asserted as a zero"
    )
    dropped = ds.load(FULL, axes, kind="serious", drop_uninformative_absences=True)
    assert len(dropped.censored_idx) == 0
    assert int((dropped.status == 0).sum()) == int((kept.status == 0).sum())


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "arms.parquet").exists(),
                    reason="run `make corpus`")
def test_the_registry_s_serious_zeros_survive(axes) -> None:
    """The counterpart. A registry serious table really is complete, and its roughly 1,025
    structural zeros are the reason the serious fit is a usable robustness check at all."""
    registry = ds.load(ROOT / "data" / "processed", axes, kind="serious")
    assert len(registry.censored_idx) == 0, "a registry serious arm must need no censoring"
    assert int((registry.status == 2).sum()) > 900


@pytest.mark.skipif(not (FULL / "arms.parquet").exists(),
                    reason="run `make pmc-merge`")
def test_an_arm_only_enters_the_grid_for_a_table_it_published(axes) -> None:
    """`arms.n_at_risk` is the maximum of the two table denominators, so a literature arm
    that published only a common-events table still carries a positive denominator when the
    serious grid is built. Taken literally that put 405 of 414 paper arms into the serious
    grid on a denominator from a different table.

    The consequence is a real result and not only a bug fix: the literature expansion buys
    the common-events table (16 agents -> 32) and buys the serious table almost nothing
    (16 -> 17). The serious fit cannot serve as the robustness check for the expanded
    corpus, and the fabricated cells were hiding that."""
    other = ds.load(FULL, axes, kind="other")
    serious = ds.load(FULL, axes, kind="serious")

    # The claim is about agents, not arms. An earlier version asserted that the any-grade
    # grid held more than twice the arms of the serious one, which was true at 588 against
    # 290 and stopped being true at 507 -- because excluding the columns that report a
    # severity-restricted or non-incidence outcome shrinks the any-grade grid and leaves the
    # serious one alone. That is the arm ratio moving for a reason unrelated to what this
    # test is for.
    assert other.n_arms > serious.n_arms
    assert other.n_contributing_agents >= 31
    assert serious.n_contributing_agents <= 20, (
        "the serious grid has gained agents it has no serious table for"
    )
    assert serious.n_contributing_agents - 16 <= 2, (
        "the expansion is supposed to buy the serious table almost nothing; it has "
        f"{serious.n_contributing_agents} agents against the registry's 16"
    )
    # The two grids no longer span the same arms, and nothing needs them to. An earlier
    # version of this test asserted that the index arrays covered every arm under both
    # tables, on the reasoning that an arm's position should be table-independent. That
    # stopped holding once the any-grade grid began excluding columns reporting a
    # severity-restricted or non-incidence outcome -- and the property was never
    # load-bearing: each fit builds its own `ModelData`, the agent and trial effects are
    # indexed within one fit, and a saved posterior carries agent *labels* rather than
    # positions. The claim was removed rather than the filter weakened to preserve it.
    assert set(serious.arm_keys) - set(other.arm_keys), (
        "the serious grid holds no arm the any-grade grid lacks, so the two are not "
        "actually built from different column sets"
    )
