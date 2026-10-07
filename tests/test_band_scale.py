"""Bands must be computed on the scale of the outcome they band.

This file exists because the band thresholds were the asserted constants 0.05 and 0.20,
chosen against the otherEvents table, and were then applied to serious-event rates that
are an order of magnitude smaller. The consequence was measured, not hypothesised: 91% of
serious cells fell in "low", and a 3.1% serious pulmonary rate for a deruxtecan design --
the organ named in ENHERTU's boxed warning, in a patient with pre-existing ILD -- rendered
as "low". The error ran in the most dangerous available direction.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from adctox.model.predict import MIN_ARMS_FOR_A_BAND, Posterior, risk_band

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"

# Measured from the corpus: 15th and 60th percentiles of non-zero observed rates.
OTHER_EDGES = (0.0645, 0.2174)
SERIOUS_EDGES = (0.0075, 0.0250)
N = MIN_ARMS_FOR_A_BAND + 10


def test_edges_are_required_not_defaulted():
    """A default would silently band serious rates on the common table's scale."""
    with pytest.raises(TypeError):
        risk_band(0.03, N)  # type: ignore[call-arg]


def test_degenerate_edges_are_rejected():
    for bad in ((0.0, 0.2), (0.2, 0.1), (-0.1, 0.2), (0.1, 0.1)):
        with pytest.raises(ValueError):
            risk_band(0.05, N, bad)


def test_the_regression_a_serious_rate_is_not_low():
    """The exact figure that motivated this: 3.1% serious pulmonary for a DXd design."""
    rate = 0.0313
    assert risk_band(rate, N, SERIOUS_EDGES) == "high"
    assert risk_band(rate, N, (0.05, 0.20)) == "low", (
        "this asserts the OLD behaviour to document it; if this line ever fails the "
        "constants have changed and the comment above needs rewriting"
    )


def test_same_rate_bands_differently_on_the_two_scales():
    """Not a quirk -- the point. The tables differ by an order of magnitude."""
    rate = 0.03
    assert risk_band(rate, N, SERIOUS_EDGES) == "high"
    assert risk_band(rate, N, OTHER_EDGES) == "low"


def test_no_evidence_still_outranks_any_scale():
    """Evidence absence is checked before the rate, on either scale."""
    for edges in (OTHER_EDGES, SERIOUS_EDGES):
        assert risk_band(0.9, MIN_ARMS_FOR_A_BAND - 1, edges) == "no_evidence"


def test_a_genuine_zero_bands_low_on_the_serious_scale():
    """39% of serious cells are exact zeros and the table is completely reported, so a
    zero is a real zero. The edges come from the non-zero distribution precisely so that
    zeros still land in "low" rather than dragging the lower edge onto 0.0."""
    assert risk_band(0.0, N, SERIOUS_EDGES) == "low"


@pytest.mark.skipif(
    not (ARTIFACTS / "posterior_serious.npz").exists(),
    reason="serious posterior not built",
)
def test_each_posterior_carries_its_own_measured_scale():
    po = Posterior.load(ARTIFACTS / "posterior_other.npz")
    ps = Posterior.load(ARTIFACTS / "posterior_serious.npz")
    assert po.kind == "other" and ps.kind == "serious"
    # An order of magnitude apart, which is the whole reason the scale cannot be shared.
    assert ps.band_edges[1] < po.band_edges[0], (
        f"serious upper edge {ps.band_edges[1]} should sit below the common lower edge "
        f"{po.band_edges[0]}; if not, the two tables are closer than measured and the "
        "dual-scale design needs rechecking"
    )
    for p in (po, ps):
        assert 0 < p.band_edges[0] < p.band_edges[1]


@pytest.mark.skipif(
    not (ARTIFACTS / "posterior_serious.npz").exists(),
    reason="serious posterior not built",
)
def test_at_risk_axis_is_banded_on_the_serious_table():
    """The one decision the dual-table design turns on."""
    from adctox.pipeline import propose

    po = Posterior.load(ARTIFACTS / "posterior_other.npz")
    ps = Posterior.load(ARTIFACTS / "posterior_serious.npz")
    r = propose("ERBB2", ["interstitial_lung_disease"], po, top_k=1,
                hard_flags=False, serious_posterior=ps)
    risks = {o["organ_axis"]: o for o in r["candidates"][0]["organ_risks"]}
    assert risks["pulmonary"]["band_basis"] == "serious", (
        "pulmonary is the axis this patient is vulnerable on, so it is a serious-harm "
        "question and must be banded on the serious table"
    )
    assert risks["gastrointestinal"]["band_basis"] == "common", (
        "an axis with no stated vulnerability is a tolerability question"
    )
    assert r["candidates"][0]["weighted_risk_basis"] == "serious"


def test_omitting_the_serious_posterior_degrades_rather_than_fails():
    """A deployment without the serious fit must still answer, saying which table it used."""
    from adctox.pipeline import propose

    if not (ARTIFACTS / "posterior_other.npz").exists():
        pytest.skip("no posterior built")
    po = Posterior.load(ARTIFACTS / "posterior_other.npz")
    r = propose("ERBB2", ["interstitial_lung_disease"], po, top_k=1, hard_flags=False)
    top = r["candidates"][0]
    assert top["weighted_risk_basis"] == "common"
    assert all(o["band_basis"] == "common" for o in top["organ_risks"])
    assert all(o["serious_estimate"] is None for o in top["organ_risks"])


@pytest.mark.skipif(
    not (ARTIFACTS / "posterior_serious.npz").exists(),
    reason="serious posterior not built",
)
def test_reported_evidence_follows_the_band_basis():
    """The count shown must be the count that produced the figure shown.

    These disagreed: an axis banded from the serious table reported the common table's
    arm count -- 162 arms quoted behind a number that 157 arms produced -- while C6
    gated on the serious count. The gate and the display were describing different
    evidence.
    """
    from adctox.pipeline import propose

    po = Posterior.load(ARTIFACTS / "posterior_other.npz")
    ps = Posterior.load(ARTIFACTS / "posterior_serious.npz")
    r = propose("ERBB2", ["interstitial_lung_disease"], po, top_k=1,
                hard_flags=False, serious_posterior=ps)
    axes = {o["organ_axis"]: o for o in r["candidates"][0]["organ_risks"]}
    mech = r["candidates"][0]["mechanism"]

    def arms(post, axis):
        if mech not in post.mechanisms or axis not in post.axes:
            return 0
        return int(post.evidence_arms[post.mechanisms.index(mech), post.axes.index(axis)])

    serious_rows = [a for a, o in axes.items() if o["band_basis"] == "serious"]
    assert serious_rows, "no axis was banded on the serious table"
    for axis in serious_rows:
        assert axes[axis]["n_supporting_arms"] == arms(ps, axis), (
            f"{axis} is banded on the serious table but reports the common table's count"
        )
    for axis, o in axes.items():
        if o["band_basis"] == "common":
            assert o["n_supporting_arms"] == arms(po, axis)


@pytest.mark.skipif(
    not (ARTIFACTS / "posterior_serious.npz").exists(),
    reason="serious posterior not built",
)
def test_both_estimates_are_reported_so_neither_is_hidden():
    """A row carries both tables' rates where evidence allows, not only the banded one.

    Suppressing the other would make the two bases incomparable *and* invisible.
    """
    from adctox.pipeline import propose

    po = Posterior.load(ARTIFACTS / "posterior_other.npz")
    ps = Posterior.load(ARTIFACTS / "posterior_serious.npz")
    r = propose("ERBB2", ["interstitial_lung_disease"], po, top_k=1,
                hard_flags=False, serious_posterior=ps)
    rows = r["candidates"][0]["organ_risks"]
    both = [o for o in rows
            if o["point_estimate"] is not None and o["serious_estimate"] is not None]
    assert len(both) >= 8, f"only {len(both)} of {len(rows)} axes carry both rates"
    # Serious rates must be the smaller of the two essentially everywhere; a serious event
    # is a subset of any-grade events, so the reverse would indicate a table mix-up.
    smaller = sum(1 for o in both if o["serious_estimate"] < o["point_estimate"])
    assert smaller / len(both) > 0.8, (
        f"serious rate exceeds the any-grade rate on {len(both) - smaller} of "
        f"{len(both)} axes; a serious event is a subset of an any-grade event, so the "
        "two tables may have been swapped"
    )


@pytest.mark.skipif(
    not (ARTIFACTS / "posterior_serious.npz").exists(),
    reason="serious posterior not built",
)
def test_every_reported_rate_carries_its_own_interval():
    """The project's own uncertainty rules require an interval beside every number.

    The serious rate was shipped as a bare point for a while: the row led with it, banded
    on it, and showed the any-grade table's interval beside it or none at all. That is the
    row a patient with a declared vulnerability reads first, so it is the worst place to
    drop the uncertainty.
    """
    from adctox.pipeline import propose

    po = Posterior.load(ARTIFACTS / "posterior_other.npz")
    ps = Posterior.load(ARTIFACTS / "posterior_serious.npz")
    r = propose("ERBB2", ["interstitial_lung_disease"], po, top_k=1,
                hard_flags=False, serious_posterior=ps)
    for o in r["candidates"][0]["organ_risks"]:
        if o["serious_estimate"] is not None:
            iv = o["serious_interval"]
            assert iv is not None, f"{o['organ_axis']} reports a serious rate with no interval"
            assert iv["lo"] <= o["serious_estimate"] <= iv["hi"], (
                f"{o['organ_axis']}: serious estimate {o['serious_estimate']} outside its "
                f"own interval [{iv['lo']}, {iv['hi']}]"
            )
            # The two intervals must be distinct objects, not the same one reused.
            assert iv != o["interval"], (
                f"{o['organ_axis']} reports the same interval for both tables; the "
                "serious interval is probably the any-grade one"
            )
        if o["point_estimate"] is not None:
            assert o["interval"]["lo"] <= o["point_estimate"] <= o["interval"]["hi"]
