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
    """The jax incomplete-beta implementation must agree with an independent binomial CDF."""
    from adctox.model.forward import _log_binom_cdf_below

    for n, cut, p in [(100, 5, 0.02), (50, 3, 0.10), (200, 10, 0.03), (30, 2, 0.25)]:
        got = float(_log_binom_cdf_below(np.float32(cut), np.float32(n), np.float32(p)))
        want = float(np.log(binom.cdf(cut - 1, n, p)))
        assert abs(got - want) < 1e-3, (n, cut, p, got, want)


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
