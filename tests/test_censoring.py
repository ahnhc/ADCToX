"""Tests for the reporting-threshold censoring, which is the likeliest silent bug.

A missing (arm, axis) cell means different things in the two event tables, and getting
it wrong biases every axis toward zero in proportion to each trial's reporting cut. The
cut is sponsor-chosen while agents nest inside sponsors, so the bias aliases the payload
mechanism effect rather than being absorbed by a trial random effect.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import binom

from adctox.model.dataset import CENSORED, OBSERVED, ZERO, build

AXES = ["haematologic", "hepatic", "pulmonary"]


def _arms(threshold, is_mono=True, n=100):
    return pd.DataFrame(
        [
            {
                "nct_id": "NCT1", "group_id": "EG0", "arm_key": "NCT1:EG0",
                "agent": "trastuzumab_deruxtecan", "n_at_risk_other": n,
                "n_at_risk_serious": n, "frequency_threshold": threshold,
                "is_monotherapy": is_mono, "conventional_adc": True,
                "mechanism": "topo1", "payload": "DXd",
                "payload_family": "camptothecin", "linker_type": "GGFG",
                "linker_cleavable": True, "dar": 8.0, "isotype": "IgG1", "target": "ERBB2",
            }
        ]
    )


def _obs(rows):
    return pd.DataFrame(
        [
            {
                "arm_key": "NCT1:EG0", "nct_id": "NCT1",
                "agent": "trastuzumab_deruxtecan", "axis": axis, "kind": kind,
                "n_affected": k, "n_at_risk": n, "sum_affected_terms": k, "n_terms": 1,
                "frequency_threshold": None,
            }
            for axis, kind, k, n in rows
        ]
    )


def test_missing_other_event_cell_is_censored_not_zero() -> None:
    """A truncated otherEvents table suppresses rates below its cut."""
    d = build(_arms(5.0), _obs([("haematologic", "other", 30, 100)]), AXES, kind="other", min_n=1)
    status = {d.axes[a]: s for a, s in zip(d.axis_idx, d.status)}
    assert status["haematologic"] == OBSERVED
    assert status["hepatic"] == CENSORED
    assert status["pulmonary"] == CENSORED
    # ceil(100 * 5 / 100) == 5: counts strictly below 5 were suppressed.
    cens = d.censor_below[d.status == CENSORED]
    assert set(cens.tolist()) == {5}


def test_missing_serious_event_cell_is_a_true_zero() -> None:
    """seriousEvents carry no threshold: verified that in threshold=5 trials, 96.7% of
    serious terms have a max rate below 5% yet were still reported."""
    d = build(_arms(5.0), _obs([("haematologic", "serious", 3, 100)]), AXES, kind="serious", min_n=1)
    status = {d.axes[a]: s for a, s in zip(d.axis_idx, d.status)}
    assert status["hepatic"] == ZERO
    assert status["pulmonary"] == ZERO
    assert (d.status == CENSORED).sum() == 0


def test_threshold_zero_means_complete_reporting() -> None:
    """182 of 605 studies report at threshold 0; their blanks are genuine zeros."""
    d = build(_arms(0.0), _obs([("haematologic", "other", 30, 100)]), AXES, kind="other", min_n=1)
    assert (d.status == CENSORED).sum() == 0
    assert (d.status == ZERO).sum() == 2


def test_absent_threshold_is_treated_as_unknown_not_complete() -> None:
    """A missing field is unknown. Assuming complete reporting we cannot verify would
    silently convert censored cells into zeros."""
    d = build(_arms(None), _obs([("haematologic", "other", 30, 100)]), AXES, kind="other", min_n=1)
    assert (d.status == CENSORED).sum() == 2


def test_covariates_are_centered_not_zeroed() -> None:
    """Zeroing log(n) at inference would mean a one-patient arm -- the extreme edge of
    the observed range -- shifting every point estimate."""
    d = build(_arms(5.0), _obs([("haematologic", "other", 30, 100)]), AXES, kind="other", min_n=1)
    assert math.isclose(float(d.arm_log_n_c[0]), 0.0, abs_tol=1e-9)
    assert math.isclose(float(d.arm_dar_c[0]), 0.0, abs_tol=1e-9)
    assert d.log_n_mean > 0  # the reference point is retained, not discarded


def test_censored_log_probability_matches_scipy() -> None:
    """The jax incomplete-beta implementation must agree with an independent binomial CDF.

    Swept rather than spot-checked. 471 of 3,990 cells go through this term, it is the
    project's most consequential modelling choice, and the earlier version checked four
    combinations all in the same benign corner -- small cut, small p. The boundaries are
    where an incomplete-beta call goes wrong: cut at 1, cut at n, cut above n, and p near
    1 where the surviving probability underflows.
    """
    from adctox.model.forward import _log_binom_cdf_below

    floor = float(np.log(1e-30))
    checked = 0
    for n in (10, 50, 293, 1000):
        for cut in (1, 2, 5, n // 2, n, n + 5):
            for p in (0.001, 0.05, 0.5, 0.95):
                got = float(
                    _log_binom_cdf_below(
                        np.float32(cut), np.float32(n), np.float32(p)
                    )
                )
                clamped = min(max(cut, 1), n)
                want = max(float(binom.logcdf(clamped - 1, n, p)), floor)
                assert abs(got - want) < 2e-3, (n, cut, p, got, want)
                checked += 1
    assert checked == 96


def test_censored_probability_is_monotone_and_finite_in_p() -> None:
    """P(X < cut) must fall as p rises, with no NaN anywhere in between.

    A non-monotone or non-finite region would not announce itself: NUTS would simply
    wander into it and the chain would diverge or stall, and the cause would look like a
    convergence problem rather than an arithmetic one.
    """
    from adctox.model.forward import _log_binom_cdf_below

    for n, cut in ((293.0, 15.0), (50.0, 1.0), (1000.0, 999.0)):
        vals = [
            float(_log_binom_cdf_below(np.float32(cut), np.float32(n), np.float32(p)))
            for p in np.linspace(0.001, 0.999, 60)
        ]
        assert all(np.isfinite(vals)), (n, cut)
        assert all(a >= b - 1e-6 for a, b in zip(vals, vals[1:])), (
            f"n={n} cut={cut}: log P(X < cut) is not monotone decreasing in p"
        )


def test_censoring_degrades_gracefully_above_denominator() -> None:
    """A threshold implying a cut above n must give probability 1, not an invalid call."""
    from adctox.model.forward import _log_binom_cdf_below

    val = float(_log_binom_cdf_below(np.float32(500), np.float32(100), np.float32(0.05)))
    assert val == pytest.approx(0.0, abs=1e-6)


def test_non_conventional_adc_excluded_from_delivery_terms() -> None:
    """moxetumomab pasudotox is a recombinant fusion: no linker, DAR 1 by construction,
    so it cannot inform the delivery coefficients."""
    arms = _arms(5.0)
    arms.loc[0, "agent"] = "moxetumomab_pasudotox"
    arms.loc[0, "conventional_adc"] = False
    with pytest.raises(ValueError, match="no arms survive"):
        build(arms, _obs([("haematologic", "other", 30, 100)]), AXES, kind="other", min_n=1)


def test_posterior_round_trips_every_field_load_requires() -> None:
    """save() and load() must agree on the field set.

    Regression: `save` omitted `families` while `load` required it, so every artefact was
    unloadable. The format guard turned that into a clear message instead of a KeyError,
    but a round-trip test is what stops it recurring -- the two methods are edited
    separately and nothing else couples them.
    """
    import tempfile
    from pathlib import Path as _Path

    from adctox.model.predict import Posterior

    n_draws, n_axes, n_mech, n_fam = 5, 3, 2, 2
    post = Posterior(
        mu_axis=np.zeros((n_draws, n_axes)),
        mech_axis=np.zeros((n_draws, n_mech, n_axes)),
        family_axis=np.zeros((n_draws, n_fam, n_axes)),
        cleav_axis=np.zeros((n_draws, n_axes)),
        b_dar=np.zeros(n_draws), b_combo=np.zeros(n_draws),
        sigma_agent=np.zeros(n_draws),
        axes=["hepatic", "renal", "pulmonary"],
        mechanisms=["tubulin", "topo1"],
        families=["auristatin", "camptothecin"],
        dar_mean=4.0, cleavable_mean=0.875,
        # Passed explicitly, never defaulted: the band scale is a property of the event
        # table, and an implicit one is what made a 4% serious rate read "low".
        kind="other", band_edges=(0.0645, 0.2174),
        evidence_agents=np.array([[4, 4, 3], [3, 2, 3]], dtype=np.int32),
        evidence_arms=np.array([[40, 38, 31], [22, 14, 20]], dtype=np.int32),
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = _Path(tmp) / "p.npz"
        post.save(path)
        back = Posterior.load(path)
    assert back.families == post.families
    assert back.mechanisms == post.mechanisms
    assert back.axes == post.axes
    assert back.cleavable_mean == post.cleavable_mean
    assert back.dar_mean == post.dar_mean
    assert back.family_axis.shape == post.family_axis.shape
    assert (back.evidence_arms == post.evidence_arms).all()
    assert (back.evidence_agents == post.evidence_agents).all()
