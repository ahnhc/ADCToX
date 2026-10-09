"""`worst_axis_risk` is not the risk on `worst_axis`, and the gap is bounded by measurement.

The axis is `argmax_a mean_draws(w_a p_a)`; the risk is `mean_draws(max_a w_a p_a)`. Both
are correct -- the risk is objective O2 as the plan defines it, and only the expectation of
the maximum penalises a candidate that is terrible on a different organ in every draw --
but the field name reads as the first and holds the second.

The objective is not changed to match the label. What is pinned is that the relationship
holds in the direction it must, that the response says which quantity it is serving, and
that the measured bound is still the measured bound.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "objective_label_gap.json"


def _doc() -> dict:
    assert ART.exists(), "run `make objective-label-gap`"
    return json.loads(ART.read_text(encoding="utf-8"))


def test_the_mean_of_the_maximum_is_never_below_the_maximum_of_the_means() -> None:
    """Jensen, in the product's output. A violation means different draws or weights.

    The tolerance is the response's own rounding to four decimals and not a fudge: at 1e-9
    this reported a violation on every run, which measured the response format rather than
    the model.
    """
    doc = _doc()
    assert doc["jensen_holds"] is True, (
        f"{doc['negative_gaps']} candidates have the risk below the named axis's weighted "
        "rate by more than the rounding; the two fields are not from one computation"
    )
    assert doc["rounding_tolerance"] < doc["display_resolution"], (
        "the rounding tolerance has grown past the display resolution, so a gap that "
        "moves a displayed digit would be dismissed as rounding"
    )


def test_the_unweighted_pair_agrees_to_the_rounding() -> None:
    """With every weight at 1 the argmax of the mean is almost always the same axis."""
    doc = _doc()
    assert doc["unweighted"]["max"] <= doc["rounding_tolerance"], (
        f"the unweighted gap reaches {doc['unweighted']['max']}, which is no longer "
        "rounding; something changed in how the unweighted objective is aggregated"
    )
    assert doc["unweighted"]["share_over_display_resolution"] == 0.0


def test_the_weighted_gap_stays_inside_its_measured_bound() -> None:
    """The bound quoted in `pipeline.py` and in the report. A regression moves it."""
    doc = _doc()
    assert doc["weighted"]["max"] <= 0.02, (
        f"the weighted gap reaches {doc['weighted']['max']}; the comment in pipeline.py "
        "and the report quote at most 0.0112, so either the sweep or the quote is stale"
    )
    assert doc["weighted"]["share_over_display_resolution"] <= 0.10, (
        "the share of candidates whose gap can move a displayed digit has grown past a "
        "tenth; at that point the label should be changed rather than documented"
    )


def test_the_sweep_covers_more_than_one_profile_and_target() -> None:
    doc = _doc()
    assert doc["queries"] >= 24 and doc["candidates"] >= 100
    assert [] in doc["profiles"], (
        "the unweighted case has to be in the sweep: it is the only one where the weighted "
        "and unweighted fields must coincide, so it is the control"
    )


def test_the_response_says_which_quantity_it_serves() -> None:
    """A field whose name reads as one quantity has to state the other in the response."""
    src = (ROOT / "src" / "adctox" / "pipeline.py").read_text(encoding="utf-8")
    assert '"worst_axis_risk_aggregation"' in src
    assert "not the rate on the named axis" in src
