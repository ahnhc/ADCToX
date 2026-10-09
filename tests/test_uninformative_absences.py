"""An absent organ is only informative when the reporting cut was stated.

A ClinicalTrials.gov record with `frequencyThreshold = 5` means every event above 5% is
listed, so an organ that does not appear has a rate below 5% and the censored likelihood is
exactly right. A paper table captioned "most common adverse events" with no stated cut
means the author *selected* rows, and absence then says almost nothing -- the selection was
not a threshold on the rate.

The first ablation round measured the cost of conflating them. Literature arms took the
observed share from 86.2% to 60.3%, about 2,200 of their 3,360 cells are censored, 83% of
those carry a boundary derived from the arm's own minimum printed rate, and the
leave-one-agent-out delta went from -0.0422 to -0.0782. The model was told "below X" with X
too large, thousands of times.

Dropping those absences is not the same as dropping the arms. The explicit-threshold-only
corpus keeps 67 of 414 paper arms and lands at 21 agents; this keeps every arm and every
observed cell, and lands at 32 agents with the registry's own observed/censored balance.
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
    literature-augmented one falls to 58.6%, which is what made it worse than its baseline.
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
