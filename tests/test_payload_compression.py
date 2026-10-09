"""What a mechanism-level model can say about payloads inside one mechanism: nothing.

Result 6 ruled out a payload-by-axis interaction on identification grounds, and that ruling
is correct. Result 41 is its price at the output, measured rather than assumed: within the
tubulin mechanism the model's ordering of the four payloads on an organ axis is uncorrelated
with the observed ordering, and on ocular -- where MMAF corneal toxicity makes the effect
the best-established in the field -- a 7.5-fold observed spread is predicted as 1.3-fold.

These tests hold the measurement to its own claims rather than to its current numbers. The
exception is the structural fact that makes the finding sharp and will not move with a
refit: the two high-ocular payloads disagree about cleavability, so the one lever the model
has inside a mechanism is orthogonal to the axis it is supposed to explain.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTEFACT = ROOT / "artifacts" / "payload_axis_compression.json"


def _doc() -> dict | None:
    if not ARTEFACT.exists():
        return None
    return json.loads(ARTEFACT.read_text(encoding="utf-8"))


# Below this the observed payloads barely differ on the axis, and the comparison has nothing
# to compress. The first version of the test below asserted the model spread never exceeds
# the observed one; neurologic within topo1 refuted it, with DXd at 0.1467 against SN-38 at
# 0.1472 -- an observed fold of 1.00 -- and a model fold of 1.02 manufactured out of
# cleavability. So the model can be the *wider* of the two where there is nothing to be wide
# about, and the invariant only holds where the observed spread is material.
MATERIAL_FOLD = 1.5


def test_the_model_does_not_exceed_a_material_observed_spread() -> None:
    """Not a tautology: a model that invented payload-level structure would break it.

    The model has no payload term, so inside a mechanism its spread comes from cleavability
    and DAR alone, and wherever the payloads genuinely differ it must be the narrower of the
    two. Where they do not differ it can be the wider, which is what `MATERIAL_FOLD` is for
    and is worth knowing in its own right: the spread the model shows between two payloads
    is not evidence that they differ.
    """
    doc = _doc()
    if not doc:
        return
    checked = 0
    for r in doc["rows"]:
        if (r.get("observed_fold") or 0) >= MATERIAL_FOLD and r.get("model_fold"):
            assert r["model_fold"] <= r["observed_fold"] + 1e-9, r
            checked += 1
    assert checked >= 5, f"only {checked} rows had a material observed spread"


def test_the_compression_is_a_ratio_of_the_two_folds() -> None:
    doc = _doc()
    if not doc:
        return
    for r in doc["rows"]:
        if "compression" in r:
            assert abs(r["compression"] - r["observed_fold"] / r["model_fold"]) < 0.02, r


def test_the_rank_agreement_is_reported_over_several_axes_not_one() -> None:
    """With four payloads a single rho takes one of ten values, so one axis proves nothing.

    The claim is the average, and the per-axis values are kept so a reader can see the
    spread rather than take the mean on trust.
    """
    doc = _doc()
    if not doc:
        return
    per_axis = doc["summary"].get("within_mechanism_spearman") or {}
    if not per_axis:
        return
    assert len(per_axis) >= 6, per_axis
    mean = doc["summary"]["mean_within_mechanism_spearman"]
    # The stored mean is rounded to four decimals, so the tolerance is that rounding.
    assert abs(mean - sum(per_axis.values()) / len(per_axis)) < 1e-3
    # And the spread is what makes the mean worth stating rather than a point.
    assert max(per_axis.values()) - min(per_axis.values()) > 0.5, per_axis


def test_cleavability_is_orthogonal_to_the_ocular_pair() -> None:
    """The structural fact behind the finding, read from the corpus and not the artefact.

    Among the tubulin payloads, the two with high observed ocular rates are MMAF, which is
    non-cleavable, and DM4, which is cleavable. So the one payload-adjacent lever the model
    has cannot order them, whatever the fit does -- which is why the rank agreement on
    ocular is about zero rather than merely weak, and why it will not improve with more
    arms of the same four payloads.
    """
    arms_path = ROOT / "data" / "processed" / "arms.parquet"
    doc = _doc()
    if not doc or not arms_path.exists():
        return
    ocular = next(
        (r for r in doc["rows"] if r["axis"] == "ocular" and r["mechanism"] == "tubulin"),
        None,
    )
    if not ocular or len(ocular["payloads"]) < 4:
        return
    arms = pd.read_parquet(arms_path)
    cleav = (
        arms.dropna(subset=["payload", "linker_cleavable"])
        .drop_duplicates("payload").set_index("payload")["linker_cleavable"].to_dict()
    )
    ranked = sorted(ocular["payloads"], key=lambda k: -ocular["payloads"][k])
    top_two = {bool(cleav[p]) for p in ranked[:2] if p in cleav}
    assert top_two == {True, False}, (
        f"the two highest-ocular payloads {ranked[:2]} no longer disagree about "
        f"cleavability ({top_two}); the finding's mechanism has changed and the prose in "
        "negative result 41 must be re-derived rather than kept"
    )


def test_family_is_a_proxy_on_some_axes_and_not_on_ocular() -> None:
    """The claim is axis-specific, so a test that only checked ocular would miss its point.

    Family recovers most of the payload spread on several organ axes -- which is why trying
    it was reasonable -- and almost none of it on ocular. Both halves are the finding.
    """
    doc = _doc()
    if not doc:
        return
    gran = {r["axis"]: r for r in doc.get("granularity") or []
            if r.get("payload_fold") and r.get("family_fold")}
    if "ocular" not in gran or len(gran) < 4:
        return
    oc = gran["ocular"]
    oc_share = oc["family_fold"] / oc["payload_fold"]
    others = [
        r["family_fold"] / r["payload_fold"]
        for a, r in gran.items() if a != "ocular"
    ]
    assert oc_share < 0.5, oc
    assert max(others) > oc_share, (oc_share, max(others))
