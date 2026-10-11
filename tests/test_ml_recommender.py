"""The ADC recommender (ml/recommend.py) and what it reads: label parsing, restriction rules, evidence, ordering.

Each test pins one defect found in the implementation audit (docs/recommender_technical_report.md, section 8) or one
property the redesign promises. Tests that need the local label snapshot or the collaborator workbook cache skip
when those are absent (they are not redistributed).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ml"), str(ROOT / "src")]
DM = pathlib.Path("/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07")
CACHE = pathlib.Path("/data/hyeongchanahn/adctox/ml_cache/tox.pkl")
needs_labels = pytest.mark.skipif(not DM.exists(), reason="DailyMed snapshot not present")
needs_cache = pytest.mark.skipif(not (DM.exists() and CACHE.exists()), reason="label snapshot or workbook cache not present")


# ------------------------------------------------------------------ label parsing (src/adctox/validation/label_change.py)
def test_boxed_headline_splits_upper_case_and():
    from adctox.validation import label_change as LC
    html = "<html><body><h1>WARNING: NEUTROPENIA AND DIARRHEA</h1><h2>5.1 Neutropenia</h2></body></html>"
    p = pathlib.Path(__import__("tempfile").mkdtemp()) / "v1.html"; p.write_text(html)
    assert LC.parse_version(p, "x", 1, None).boxed_axes == ["haematologic", "gastrointestinal"]


def test_section5_title_is_not_a_boxed_warning():
    from adctox.validation import label_change as LC
    html = "<html><body><h1>WARNINGS AND PRECAUTIONS</h1><h2>5.1 Interstitial Lung Disease</h2></body></html>"
    p = pathlib.Path(__import__("tempfile").mkdtemp()) / "v1.html"; p.write_text(html)
    lv = LC.parse_version(p, "x", 1, None)
    assert lv.boxed_headline is None and lv.boxed_axes == []


def test_axes_for_heading_returns_every_organ_and_axis_for_heading_keeps_the_first():
    from adctox.validation.label_change import axes_for_heading, axis_for_heading
    h = "Hemorrhage and Hepatotoxicity"
    assert axis_for_heading(h) == "hepatic"
    assert set(axes_for_heading(h)) == {"hepatic", "cardiovascular"}
    assert axes_for_heading("Embryo-Fetal Toxicity") == []


@needs_labels
def test_sacituzumab_diarrhea_is_boxed_in_the_evidence():
    import drug_evidence as DE
    ax = DE.warnings()["sacituzumab-govitecan"]["axes"]
    assert ax["gastrointestinal"]["level"] == "boxed" and ax["haematologic"]["level"] == "boxed"


# ------------------------------------------------------------------ restriction rules
@needs_labels
def test_every_restriction_quote_is_verbatim_in_its_label():
    import restrictions as RS
    assert RS.verify_quotes() == []


@needs_labels
@pytest.mark.parametrize("adc,labs,conds,organs,expect", [
    ("pivekimab-sunirine", {"crcl": 45}, set(), {"renal"}, "avoid"),                  # 8.6: CLcr < 60
    ("pivekimab-sunirine", {"crcl": 75}, set(), {"renal"}, "no_adjustment"),
    ("pivekimab-sunirine", {"bili": 2.0}, set(), {"hepatic"}, "avoid"),               # 8.7: bilirubin > 1.5 x ULN
    ("mirvetuximab-soravtansine", {"bili": 1.6}, set(), {"hepatic"}, "avoid"),        # 8.7
    ("mirvetuximab-soravtansine", {}, {"dialysis"}, {"renal"}, "insufficient_data"),  # 8.6: ESRD unknown
    ("datopotamab-deruxtecan", {"crcl": 50}, set(), {"renal"}, "monitor"),            # 8.6: ILD more frequent at CLcr 30-<90
    ("brentuximab-vedotin", {"crcl": 25}, set(), {"renal"}, "avoid"),
    ("brentuximab-vedotin", {"child_pugh": "B"}, set(), {"hepatic"}, "avoid"),
    ("trastuzumab-deruxtecan", {"lvef": 45}, set(), {"cardiovascular"}, "insufficient_data"),
])
def test_known_label_restrictions(adc, labs, conds, organs, expect):
    import restrictions as RS
    v = RS.judge(RS.Patient(conditions=conds, organs=organs, **labs), [adc])[adc]
    assert max((RS.TIER[c] for c, _ in v.known), default=-1) == RS.TIER[expect]


@needs_labels
def test_missing_lab_is_not_guessed_from_the_diagnosis():
    """CKD 3 without CLcr: pivekimab is a possible 'avoid', not a settled one, and CLcr is asked for."""
    import restrictions as RS
    v = RS.judge(RS.Patient(conditions={"ckd_stage_3"}, organs={"renal"}), ["pivekimab-sunirine"])["pivekimab-sunirine"]
    assert v.worst_known < RS.TIER["avoid"] <= v.worst_possible
    assert any("CLcr" in m for m in v.missing)


@needs_labels
def test_label_silence_is_reported_not_read_as_safe():
    """Enfortumab's label does not address dialysis: 'no label statement', which ranks with insufficient data."""
    import restrictions as RS
    v = RS.judge(RS.Patient(conditions={"dialysis"}, organs={"renal"}), ["enfortumab-vedotin"])["enfortumab-vedotin"]
    assert v.worst_known == RS.TIER["no_statement"] == RS.TIER["insufficient_data"]


# ------------------------------------------------------------------ evidence (no imputation)
@needs_cache
def test_grade_3_and_4_are_not_added_across_trials():
    """T-DM1 platelets: 14 + 3 (EMILIA) and 4 + 2 (KATHERINE); the first version reported 23."""
    import drug_evidence as DE
    assert DE.incidence()["trastuzumab-emtansine"]["haematologic"]["pct"] <= 17.0


@needs_cache
def test_missing_incidence_is_flagged_not_zero():
    import drug_evidence as DE
    E = DE.evidence()
    gem = E["gemtuzumab-ozogamicin"]["organs"]
    assert all(o["inc_status"] == "no data" and o["inc"] is None for o in gem.values())
    assert E["sacituzumab-govitecan"]["organs"]["gastrointestinal"]["inc_status"] == "not reported"


# ------------------------------------------------------------------ ordering
@needs_cache
def test_more_vulnerability_never_lowers_concern_for_a_drug_that_warns_on_that_organ():
    """The old weighted mean fell when an organ's vulnerability rose (d raw / d s_k < 0 when 100 T_k < raw)."""
    import numpy as np
    import recommend as RC
    rows_lo, *_ = RC.recommend(["ckd_stage_3"])
    rows_hi, *_ = RC.recommend(["ckd_stage_4_5"])          # same organ, higher curated severity
    lo = {r["adc"]: (r["B"], r["Wn"]) for r in rows_lo}; hi = {r["adc"]: (r["B"], r["Wn"]) for r in rows_hi}
    assert all(hi[a][0] >= lo[a][0] and hi[a][1] >= lo[a][1] for a in lo)
    assert any(hi[a] != lo[a] for a in lo)


@needs_cache
def test_no_min_max_rescaling_and_no_percentage():
    import recommend as RC
    rows, *_ = RC.recommend(["interstitial_lung_disease"])
    assert not any(k in rows[0] for k in ("risk_pct", "raw_pct"))


@needs_cache
def test_identical_evidence_is_shown_as_a_tie_not_an_order():
    import recommend as RC
    rows, *_ = RC.recommend(["interstitial_lung_disease"])
    r = {x["adc"]: x for x in rows}
    g, p = r["gemtuzumab-ozogamicin"], r["pivekimab-sunirine"]
    if g["key"] == p["key"]:
        assert g["tie"] and p["tie"] and g["rank"] == p["rank"]


@needs_cache
def test_restriction_outranks_any_organ_burden():
    """A settled 'avoid' (pivekimab, CLcr 45) must sort after every drug without one, whatever their warnings."""
    import recommend as RC
    rows, *_ = RC.recommend(["ckd_stage_3"], {"crcl": 45})
    order = [r["adc"] for r in rows]
    assert order[-1] == "pivekimab-sunirine"


@needs_cache
def test_boxed_warning_on_the_patients_organ_is_visible():
    """The case that motivated the review: an ocular patient must see mirvetuximab's boxed ocular warning, and it must not rank first."""
    import recommend as RC
    rows, *_ = RC.recommend(["keratopathy_history", "dry_eye"])
    r = {x["adc"]: x for x in rows}
    assert "ocular" in r["mirvetuximab-soravtansine"]["boxed"]
    assert rows[0]["adc"] != "mirvetuximab-soravtansine"


@needs_cache
def test_organs_shown_carry_label_evidence():
    """The old table could name an organ with no warning and no incidence; every organ shown now has a warning behind it."""
    import recommend as RC
    rows, *_ = RC.recommend(["nafld", "dialysis", "heart_failure"])
    for r in rows:
        for a in r["boxed"]: assert r["organs"][a]["level"] == "boxed"
        for a in r["warn"]: assert r["organs"][a]["level"] == "W&P"


@needs_cache
def test_learned_model_is_off_by_default():
    import recommend as RC
    assert RC.LEARNED_FRACTION == 0.0
    s = RC.resolve(["interstitial_lung_disease"])[0]
    assert (s > 0).sum() == 1                                # only the condition's own organ


# ------------------------------------------------------------------ learned model inference matches training
def test_vulnerability_inference_does_not_set_context_bits_training_never_saw():
    src = (ROOT / "ml" / "vulnerability_model.py").read_text()
    pred = src[src.index("def predict"):]
    assert "meta[\"nl\"] + k] = 1" not in pred
