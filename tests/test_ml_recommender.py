"""The ADC recommender (ml/recommend.py) and what it reads: label parsing, restriction rules, evidence, ordering.

Each test pins one defect found in the implementation audit (ml/docs/recommender_technical_report.md, section 8) or one
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
try:
    import torch  # noqa: F401
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
needs_encoder = pytest.mark.skipif(not HAS_TORCH, reason="free-text conditions need the ML env (torch); run with /data/hyeongchanahn/envs/adctox/bin/python")


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
    ("belantamab-mafodotin", {"bili": 2.0}, set(), {"hepatic"}, "insufficient_data"),       # 8.6: moderate/severe not established
    ("belantamab-mafodotin", {"bili": 1.2}, set(), {"hepatic"}, "no_adjustment"),
    ("belantamab-mafodotin", {"crcl": 20}, set(), {"renal"}, "no_adjustment"),              # 12.3: kidney failure without dialysis
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
def test_priority_order_decides_between_organs():
    """two conditions on different organs: the drug warning on the level-1 condition's organ goes last, whatever the severities."""
    import recommend as RC
    try:
        RC.PRIORITY = {}
        d = {r["adc"]: r for r in RC.recommend(["cirrhosis", "glaucoma"])[0]}            # default: cirrhosis (1.0) before glaucoma (0.5)
        assert d["mirvetuximab-soravtansine"]["Bl"] == (0, 1)                          # ocular boxed sits on level 2
        RC.PRIORITY = {"glaucoma": 1, "cirrhosis": 2}
        rows = RC.recommend(["cirrhosis", "glaucoma"])[0]; d = {r["adc"]: r for r in rows}
        assert d["mirvetuximab-soravtansine"]["Bl"] == (1, 0)
        tier = d["mirvetuximab-soravtansine"]["tier"]                                   # compared within one restriction tier
        ocular_boxed = [r["rank"] for r in rows if "ocular" in r["boxed"] and r["tier"] == tier]
        hepatic_only = [r["rank"] for r in rows if "hepatic" in r["boxed"] and "ocular" not in r["boxed"] and r["tier"] == tier]
        assert all(o > h for o in ocular_boxed for h in hepatic_only)
        RC.PRIORITY = {"glaucoma": 1, "cirrhosis": 1}                                   # equal ranks: counted together
        assert {r["adc"]: r for r in RC.recommend(["cirrhosis", "glaucoma"])[0]}["mirvetuximab-soravtansine"]["Bl"] == (1,)
    finally:
        RC.PRIORITY = {}


def test_lab_report_values_are_converted_to_what_the_labels_read():
    import labs as LB
    lab, flags, notes = LB.derive(dict(age=70, sex="F", weight=55, creatinine=1.3, bilirubin=2.4, ast=50, alt=130, hb=9.2, platelet=80, anc=1.2, hba1c=8.4))
    assert abs(lab["crcl"] - (140 - 70) * 55 / (72 * 1.3) * 0.85) < 0.1               # Cockcroft-Gault, female
    assert lab["bili"] == 2.0 and lab["ast"] == 1.25 and lab["alt"] == 3.25              # x ULN with 1.2 / 40 / 40
    assert {o for o, _ in flags} == {"haematologic", "hepatic", "metabolic_endocrine"}    # Hb, ANC; bilirubin, ALT; HbA1c
    lab, _, notes = LB.derive(dict(egfr=45))
    assert lab["crcl"] == 45 and any("approximation" in n for n in notes)               # eGFR stands in, and says so
    assert LB.derive(dict(creatinine=1.3))[0].get("crcl") is None                       # creatinine alone gives no CLcr


@needs_labels
def test_portable_build_gives_the_server_result(tmp_path):
    """the one-file build must print the same table as the repository version for listed conditions and lab values."""
    import subprocess
    out = tmp_path / "adc_recommender.py"
    subprocess.run([sys.executable, "-I", str(ROOT / "ml/build_portable.py"), str(out)], check=True, capture_output=True)
    args = ["cirrhosis", "glaucoma", "dialysis", "--lab", "bilirubin=2.0", "--lab", "platelet=80", "--lab", "anc=1.2", "--priority", "2,1,1"]
    env = {"PATH": "/usr/bin:/bin", "NO_COLOR": "1", "HOME": str(tmp_path)}
    server = subprocess.run([sys.executable, "-I", str(ROOT / "ml/recommend.py"), *args], capture_output=True, text=True, env=env, cwd=ROOT).stdout
    portable = subprocess.run([sys.executable, "-I", str(out), *args], capture_output=True, text=True, env=env, cwd=tmp_path).stdout
    assert "라벨 제한" in server and portable == server


_HF = pathlib.Path.home() / ".cache/huggingface/hub"
_FULL_MODELS = {"BioLORD-2023": _HF / "models--FremyCompany--BioLORD-2023/snapshots/167aab527b238a50ca65224e6319215d2ff4fc9f",
                "SapBERT": _HF / "models--cambridgeltl--SapBERT-from-PubMedBERT-fulltext/snapshots/090663c3ae57bf35ffe4d0d468a2a88d03051a4d",
                "mondo_index.npz": pathlib.Path("/data/hyeongchanahn/adctox/ml_cache/mondo_index.npz"),
                "vuln_biolord.pt": pathlib.Path("/data/hyeongchanahn/adctox/ml_cache/vuln_biolord.pt")}


_MODEL_PY = "/data/hyeongchanahn/envs/adctox/bin/python"          # the environment with torch / transformers


@pytest.mark.skipif(not (all(p.exists() for p in _FULL_MODELS.values()) and pathlib.Path(_MODEL_PY).exists()), reason="models not on this machine")
def test_full_build_gives_the_server_result_for_typed_diseases(tmp_path):
    """the full one-file build (server language models, FinnGen fallback) prints what the repository version prints."""
    import subprocess
    out, m = tmp_path / "adc_recommender_full.py", tmp_path / "models"; m.mkdir()
    for k, p in _FULL_MODELS.items(): (m / k).symlink_to(p)
    subprocess.run([_MODEL_PY, "-I", str(ROOT / "ml/build_portable.py"), "--full", str(out)], check=True, capture_output=True)
    args = ["alzheimer", "adhd", "heart stop", "cirrhosis", "자폐증", "--learned-fallback", "0.25", "--lab", "bilirubin=2.0"]
    env = {"PATH": "/usr/bin:/bin", "NO_COLOR": "1", "HOME": str(tmp_path), "CUDA_VISIBLE_DEVICES": ""}
    server = subprocess.run([_MODEL_PY, "-I", str(ROOT / "ml/recommend.py"), *args], capture_output=True, text=True, env=env, cwd=ROOT).stdout
    full = subprocess.run([_MODEL_PY, "-I", str(out), *args], capture_output=True, text=True, env={**env, "ADC_MODEL_DIR": str(m)}, cwd=tmp_path).stdout
    assert "Alzheimer disease" in server and "autism" in server.lower() and full == server


def test_free_text_is_split_on_commas_whatever_the_spacing():
    import form
    assert form.split_free("copd ,   asthma,heart   stop , ,") == ["copd", "asthma", "heart stop"]


@needs_labels
def test_blood_count_and_hba1c_rules():
    import restrictions as R
    J = lambda adc, **kw: R.summary(R.judge(R.Patient(**kw), [adc])[adc])
    assert J("trastuzumab-emtansine", platelets=80).startswith("Insufficient data (blood")
    assert J("sacituzumab-govitecan", anc=1.2).startswith("Avoid (blood")
    assert J("sacituzumab-govitecan", anc=2.0) == "-"
    assert J("enfortumab-vedotin", hba1c=8.5).startswith("Insufficient data (metabolic")


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


@needs_labels
def test_review_cases_restrictions_are_not_weakened_by_entering_labs():
    import restrictions as R
    J = lambda adc, **kw: R.judge(R.Patient(**kw), [adc])[adc]
    # 1 T-DM1: not studied at bilirubin > 1.5 x ULN (5.1), even with Child-Pugh A
    v = J("trastuzumab-emtansine", child_pugh="A", bili=2.0, ast=1.0, lvef=60)
    assert R.summary(v).startswith("Insufficient data (hepatic 5.1)") and v.missing == []
    # 2 inotuzumab: ALT is part of the label condition; unknown ALT stays open, raised ALT restricts
    assert "Insufficient data?" in R.summary(J("inotuzumab-ozogamicin", bili=1.0, ast=1.0))
    assert R.summary(J("inotuzumab-ozogamicin", bili=1.0, ast=1.0, alt=3.0)).startswith("Insufficient data (hepatic")
    assert R.summary(J("inotuzumab-ozogamicin", bili=1.0, ast=1.0, alt=1.0)).startswith("No adjustment")
    # 3 brentuximab Child-Pugh A: the label requires a dose reduction, not monitoring
    assert R.summary(J("brentuximab-vedotin", child_pugh="A")).startswith("Dose reduction required")
    # 4 CLcr < 15 with dialysis status unknown: the ESRD rule stays possible and the test is asked for
    v = J("inotuzumab-ozogamicin", crcl=10)
    assert "Insufficient data?" in R.summary(v) and any("ESRD" in m for m in v.missing)
    assert J("inotuzumab-ozogamicin", crcl=10, conditions={"dialysis"}).worst_known == R.TIER["insufficient_data"]
    # 5 every domain at the top tier is named, not one picked arbitrarily
    s = R.summary(J("trastuzumab-emtansine", conditions={"heart_failure", "chronic_liver_disease"}, organs={"cardiovascular", "hepatic"}))
    assert "cardiac" in s.split(";")[0] and "hepatic" in s.split(";")[0]


@needs_cache
def test_learned_model_is_off_by_default():
    import recommend as RC
    assert RC.LEARNED_FRACTION == 0.0
    s = RC.resolve(["interstitial_lung_disease"])[0]
    assert (s > 0).sum() == 1                                # only the condition's own organ


@needs_cache
@needs_encoder
def test_learned_fallback_touches_only_conditions_with_no_organ():
    import numpy as np
    import recommend as RC
    conds = ["obesity", "alzheimer", "ckd_stage_3"]
    assert RC.unresolved(conds) == ["obesity"]                 # alzheimer has a MONDO organ, ckd is in the registry
    base = RC.resolve(["alzheimer", "ckd_stage_3"])[0]
    try:
        RC.FALLBACK = {"obesity": 0.5}
        s, _, _, notes, _ = RC.resolve(conds)
        assert "not validated" in dict(notes)["obesity"] and "not validated" not in dict(notes)["alzheimer"]
        assert (s >= base).all() and (s > 0).sum() > (base > 0).sum()
        RC.FALLBACK = {"obesity": 0.5}
        assert np.array_equal(RC.resolve(["alzheimer", "ckd_stage_3"])[0], base)   # understood conditions never change
        assert RC.unresolved(conds) == ["obesity"] and RC.FALLBACK == {"obesity": 0.5}
    finally:
        RC.FALLBACK = {}


# ------------------------------------------------------------------ learned model inference matches training
def test_vulnerability_inference_does_not_set_context_bits_training_never_saw():
    src = (ROOT / "ml" / "vulnerability_model.py").read_text()
    pred = src[src.index("def predict"):]
    assert "meta[\"nl\"] + k] = 1" not in pred


# ------------------------------------------------------------------ stage-5 patient-level harness (ml/validate_outcomes.py)
def _synthetic_cohort(signal: bool, n=480, seed=1):
    """Each patient has one condition and gets a random ADC. With signal=True the event rate is high exactly when that ADC's
    label warns on the patient's organ (a patient x drug interaction), so a tool that uses patient information must win."""
    import numpy as np
    import drug_evidence as DE
    E = DE.evidence(); rng = np.random.default_rng(seed)
    conds = {"interstitial_lung_disease": "pulmonary", "keratopathy_history": "ocular", "cirrhosis": "hepatic", "peripheral_neuropathy": "neurologic"}
    adcs = [a for a in sorted(E) if a != "pivekimab-sunirine"]; rows = []
    for i in range(n):
        c = list(conds)[i % len(conds)]; a = adcs[rng.integers(len(adcs))]
        hit = E[a]["organs"][conds[c]]["level"] != "none"
        p = (0.55 if hit else 0.08) if signal else 0.25
        rows.append(dict(patient_id=str(i), adc=a, conditions=c, crcl="", bili="1.0", ast="1.0", child_pugh="A", lvef="", outcome=str(int(rng.random() < p)), site=""))
    return rows


@needs_cache
def test_outcome_harness_detects_a_real_patient_drug_association():
    import validate_outcomes as VO
    rows = _synthetic_cohort(signal=True); res = VO.analyse(rows, VO.features(rows), n_boot=400)
    assert res["auroc"]["tool"]["ci"][0] > 0.5
    assert res["paired"]["tool_minus_label_only"]["adds_patient_information"]
    c = res["calibration"]
    assert c["brier"] < c["brier_base_rate"] and 0.5 < c["calibration_slope"] < 1.5      # out-of-fold probabilities are informative and not wildly off


@needs_cache
def test_outcome_harness_does_not_invent_an_association():
    """no patient x drug signal: a 95% interval excludes 0 by chance about once in 40 cohorts, so judge 8 cohorts, not one draw."""
    import validate_outcomes as VO
    found = []
    for seed in range(1, 9):
        rows = _synthetic_cohort(signal=False, seed=seed); res = VO.analyse(rows, VO.features(rows), n_boot=400)
        found.append(res["paired"]["tool_minus_label_only"]["adds_patient_information"])
        if seed == 2:
            lo, hi = res["auroc"]["tool"]["ci"]; assert lo < 0.5 < hi
    assert sum(found) <= 1, found


# ------------------------------------------------------------------ JADER (ml/validate_jader.py): Japanese term -> organ rules
@pytest.mark.parametrize("term,organ", [
    ("間質性肺疾患", "pulmonary"), ("好中球減少症", "haematologic"), ("発熱性好中球減少症", "haematologic"), ("下痢", "gastrointestinal"),
    ("悪心", "gastrointestinal"), ("角膜症", "ocular"), ("末梢性ニューロパチー", "neurologic"), ("駆出率減少", "cardiovascular"),
    ("心不全", "cardiovascular"), ("急性腎障害", "renal"), ("慢性腎臓病", "renal"), ("肝毒性", "hepatic"), ("静脈閉塞性肝疾患", "hepatic"),
    ("肺炎", "infectious_immune"), ("スティーブンス・ジョンソン症候群", "dermatologic"), ("高血糖", "metabolic_endocrine"), ("ＱＴ延長", "cardiovascular"),
    ("ドライアイ", "ocular"), ("緑内障", "ocular"), ("Ｂ型肝炎", "hepatic"),
    ("糖尿病", "metabolic_endocrine"), ("２型糖尿病", "metabolic_endocrine"), ("高尿酸血症", "metabolic_endocrine"), ("脂質異常症", "metabolic_endocrine"),
    ("腎機能障害", "renal"), ("スティーヴンス・ジョンソン症候群", "dermatologic"), ("腹水", "gastrointestinal"), ("ホジキン病", None), ("乳癌", None), ("肝転移", None), ("急性骨髄性白血病", None), ("死亡", None), ("発熱", None),
])
def test_jader_organ_rules(term, organ):
    import validate_jader as VJ
    assert VJ.OrganMapper(use_embedding=False).map([term])[term] == organ


@pytest.mark.parametrize("arg", ["--help", "-h", "help"])
def test_help_explains_the_program_and_lists_every_command(arg, monkeypatch, capsys):
    import recommend as RC
    monkeypatch.setattr(sys, "argv", ["adctox", arg])
    RC.main(); out = capsys.readouterr().out
    assert "ADC" in out and "연구용" in out and "TAB" in out and "Ctrl+U" in out
    for c in ("--update-app", "--check-app", "--update-models", "--check-models", "--model-version", "--rollback-models", "--verify-models", "--version", "--list", "--lab"):
        assert c in out
