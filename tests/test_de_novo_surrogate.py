"""End-to-end verification tests for the 5-Fold `ADC-SurrogateNet-v2` ensemble replacement.

Verifies:
1. Integrity and biophysical consistency of `surrogate_2592.json`, `surrogate_2592.js`, and `surrogate_designer.json`.
2. Elimination of v1 bugs (distinct GTEx/Tabula Sapiens organ hazards across targets, LALA-PG Fc-silencing reduction on `hf`, DAR aggregation scaling on `ha`, 5-fold leak-free CV metadata).
3. Replacement of rule-based scoring in `ml/adc_designer.py` (`design_novel_adc`) across all 8 targets and clinical comorbidity/DDI scenarios.
4. Integration of `surrogate_2592.js` in `ml/web/index.html`, `ml/web/sw.js`, and `ml/web/app.js`.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
ML_DIR = REPO_ROOT / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import adc_designer as AD  # noqa: E402


def test_surrogate_2592_and_js_bundle_integrity():
    s_json_path = ML_DIR / "data" / "surrogate_2592.json"
    s_js_path = ML_DIR / "web" / "surrogate_2592.js"
    assert s_json_path.exists(), "Missing ml/data/surrogate_2592.json"
    assert s_js_path.exists(), "Missing ml/web/surrogate_2592.js"

    payload = json.loads(s_json_path.read_text(encoding="utf-8"))
    assert payload["zero_synthetic_formula_labels"] is True
    assert payload["organs"] == AD.AXES
    assert len(payload["grid"]) == 2592
    assert len(payload["table"]) == 2592

    js_txt = s_js_path.read_text(encoding="utf-8")
    assert "\u00b7" not in js_txt
    assert js_txt.find("window.ADCTOX_SURROGATE=") != -1
    json_part = js_txt.split("window.ADCTOX_SURROGATE=", 1)[1].strip().rstrip(";")
    js_obj = json.loads(json_part)
    assert len(js_obj["grid"]) == 2592
    assert js_obj["organs"] == AD.AXES


def test_biophysical_pathway_monotonicity_and_target_specificity():
    payload = json.loads((ML_DIR / "data" / "surrogate_2592.json").read_text(encoding="utf-8"))
    grid = payload["grid"]
    organs = payload["organs"]
    fc_idx = [organs.index(ax) for ax in ("pulmonary", "haematologic", "ocular", "hepatic")]

    # 1. LALA-PG Fc silencing (`fc=1`) must strictly reduce neural Fc pathway hazard (`hf`) vs wild-type IgG1 (`fc=0`)
    wt_hf, sil_hf = [], []
    for key, node in grid.items():
        if key.endswith("|0"):
            sil_key = key[:-2] + "|1"
            wt_hf.append(sum(node["hf"][i] for i in fc_idx) / len(fc_idx))
            sil_hf.append(sum(grid[sil_key]["hf"][i] for i in fc_idx) / len(fc_idx))
    assert (sum(sil_hf) / len(sil_hf)) < (sum(wt_hf) / len(wt_hf)) * 0.5, "LALA-PG must attenuate neural FcgammaR hazard `hf`"

    # 2. High DAR (8) must exhibit higher aggregation pathway hazard (`ha`) than low DAR (2)
    dar2_ha = [sum(v["ha"]) / len(v["ha"]) for k, v in grid.items() if "|2|" in k]
    dar8_ha = [sum(v["ha"]) / len(v["ha"]) for k, v in grid.items() if "|8|" in k]
    assert (sum(dar8_ha) / len(dar8_ha)) > (sum(dar2_ha) / len(dar2_ha)), "DAR 8 must increase aggregation hazard `ha` relative to DAR 2"

    # 3. Distinct targets must produce distinct on-target organ hazard vectors (`ho`), proving GTEx/TS lookup works
    ho_her2 = grid["HER2 (ERBB2)|Tetrapeptide GGFG|DXd ( Topo I )|4|0"]["ho"]
    ho_trop2 = grid["TROP2 (TACSTD2)|Tetrapeptide GGFG|DXd ( Topo I )|4|0"]["ho"]
    ho_folr1 = grid["FRalpha (FOLR1)|Tetrapeptide GGFG|DXd ( Topo I )|4|0"]["ho"]
    assert ho_her2 != ho_trop2, "HER2 and TROP2 on-target hazards must differ"
    assert ho_her2 != ho_folr1, "HER2 and FOLR1 on-target hazards must differ"


def test_python_adc_designer_neural_surrogate_all_targets():
    d_json_path = ML_DIR / "data" / "surrogate_designer.json"
    assert d_json_path.exists(), "Missing ml/data/surrogate_designer.json"
    d_payload = json.loads(d_json_path.read_text(encoding="utf-8"))
    assert len(d_payload["grid"]) == 768

    zero_v = {ax: 0.0 for ax in AD.AXES}
    for tgt_key in AD.TARGET_ANTIGENS:
        spec = AD.design_novel_adc(tgt_key, zero_v)
        assert spec.target_antigen == tgt_key.upper()
        assert spec.dar in (2, 4)
        assert 1.0 <= spec.predicted_safety_score <= 9.9
        assert 1.0 <= spec.predicted_efficacy_score <= 9.9
        assert len(spec.rationales) >= 3

    # Severe pulmonary comorbidity + bystander forbidden -> rejects DXd and permeable bystander linkers, enables LALA-PG
    ild_v = {ax: 0.05 for ax in AD.AXES}
    ild_v["pulmonary"] = 0.90
    spec_ild = AD.design_novel_adc("HER2", ild_v, bystander_forbidden=True)
    assert "LALA-PG" in spec_ild.fc_engineering
    assert "Deruxtecan" not in spec_ild.payload_choice
    assert any(tok in spec_ild.linker_choice for tok in ("SMCC", "MCC", "Glucuronide"))

    # Strong CYP3A4 inhibitor co-medication -> avoids CYP3A4-dependent MMAE/MMAF/DM1
    ddi_v = {ax: 0.10 for ax in AD.AXES}
    spec_ddi = AD.design_novel_adc("TROP2", ddi_v, concomitant_drugs=["itraconazole"])
    assert "MMAE" not in spec_ddi.payload_choice
    assert "MMAF" not in spec_ddi.payload_choice
    assert "Maytansinoid" not in spec_ddi.payload_choice


def test_web_studio_wiring_has_neural_surrogate():
    idx_txt = (ML_DIR / "web" / "index.html").read_text(encoding="utf-8")
    sw_txt = (ML_DIR / "web" / "sw.js").read_text(encoding="utf-8")
    app_txt = (ML_DIR / "web" / "app.js").read_text(encoding="utf-8")

    assert "surrogate_2592.js" in idx_txt
    assert idx_txt.index("surrogate_2592.js") < idx_txt.index("app.js")
    assert "/static/surrogate_2592.js" in sw_txt
    assert "ADCTOX_SURROGATE" in app_txt


def test_studio_368k_catalog_and_svd_matrix_engine():
    import studio_matrix as SM

    cat = SM.catalog_info()
    assert len(cat["targets"]) == 36
    assert len(cat["linkers"]) == 16
    assert len(cat["payloads"]) == 20
    assert len(cat["dars"]) == 8
    assert len(cat["fc_formats"]) == 4
    assert cat["total_combinations"] == 368640
    assert all(isinstance(p.get("organs"), dict) and len(p["organs"]) >= 3 for p in cat["payloads"])

    res = SM.evaluate_studio_matrix(
        {
            "spec": {
                "target": "CLDN18.2 (CLDN18)",
                "linker": "Tetrapeptide GGFG",
                "payload": "DXd ( Topo I )",
                "dar": 6,
                "fc": True,
                "fcFormat": "igg1_lalapg",
            },
            "organs": [{"organ": "pulmonary", "score": 0.92}, {"organ": "hepatic", "score": 0.75}],
            "prioOrgan": "pulmonary",
            "cancerText": "gastric adenocarcinoma",
        }
    )
    assert res["mode"] == "matrix_368k"
    assert res["total_combinations"] == 368640
    assert res["compatible_combinations"] > 100000
    assert 2 <= res["current"]["safetyScore"] <= 98
    assert 2 <= res["best"]["efficacyScore"] <= 98
    assert len(res["pareto_front"]) >= 2
    assert len(res["cloud"]) > 500
    assert len(res["same_target_cloud"]) > 50


def test_v083_ui_copy_and_collapsible_required_labs_invariants():
    app_txt = (ML_DIR / "web" / "app.js").read_text(encoding="utf-8")
    assert "나이, 성별, 체중을 입력해 두면" not in app_txt
    assert "CLcr 수치가 없을 때" not in app_txt
    assert "Will Cockcroft-Gault auto-derive" not in app_txt
    assert "studioDeepResearch" in app_txt
    assert "Deep Research" not in app_txt
    assert "studio-exec-box" in app_txt
    assert "basicLabsOpen" in app_txt
    assert "buildRequiredLabsPanel" in app_txt
    assert "CLDN18.2 (CLDN18)" in app_txt
    assert "DLL3" in app_txt
    assert "BCMA (TNFRSF17)" in app_txt
    assert "ROR1" in app_txt
    assert "studio-patient-bar" in app_txt
    assert "ref-adc-select" in app_txt
    assert "studio-fold" in app_txt
    assert "openStudioPartSheet" in app_txt
    assert "sim-param-row" in app_txt


def test_v090_approved_ref_adc_native_target_isolation():
    import studio_matrix as SM

    assert len(SM.REF_ADC_ARCH) == 15

    # P0-1 regression: Integrin beta-6 de novo construct compares against PADCEV (enfortumab-vedotin),
    # whose true approved target MUST remain Nectin-4 (never overwritten with Integrin beta-6).
    res_itgb6 = SM.evaluate_studio_matrix(
        {
            "spec": {
                "target": "Integrin beta-6 (ITGB6)",
                "linker": "Val-Cit PABC",
                "payload": "MMAE ( Auristatin )",
                "dar": 4,
                "fcFormat": "igg1_wt",
            },
            "organs": [{"organ": "dermatologic", "score": 0.70}, {"organ": "pulmonary", "score": 0.90}],
            "prioOrgan": "pulmonary",
        }
    )
    assert res_itgb6["current"]["spec"]["target"] == "Integrin beta-6 (ITGB6)"
    assert res_itgb6["ref_current"]["spec"]["target"] == "Nectin-4"
    assert res_itgb6["current"]["organRisks"][0]["organ"] == "pulmonary"

    # P0-1 regression: ENPP3 de novo construct compares against BLENREP (belantamab-mafodotin),
    # whose true approved target MUST remain BCMA (TNFRSF17) (never overwritten with ENPP3).
    res_enpp3 = SM.evaluate_studio_matrix(
        {
            "spec": {
                "target": "ENPP3",
                "linker": "Non-cleavable mc",
                "payload": "MMAF ( Auristatin )",
                "dar": 4,
                "fcFormat": "igg1_wt",
            }
        }
    )
    assert res_enpp3["current"]["spec"]["target"] == "ENPP3"
    assert res_enpp3["ref_current"]["spec"]["target"] == "BCMA (TNFRSF17)"

    # Expanded 15-ADC reference coverage: c-MET -> telisotuzumab-vedotin, CD123 -> pivekimab-sunirine
    res_cmet = SM.evaluate_studio_matrix(
        {
            "spec": {
                "target": "c-MET (MET)",
                "linker": "Val-Cit PABC",
                "payload": "MMAE ( Auristatin )",
                "dar": 3.5,
                "fcFormat": "igg1_wt",
            }
        }
    )
    assert res_cmet["ref_current"]["spec"]["target"] == "c-MET (MET)"
    assert res_cmet["ref_current"]["spec"]["dar"] == 3.5

    res_cd123 = SM.evaluate_studio_matrix(
        {
            "spec": {
                "target": "CD123 (IL3RA)",
                "linker": "Val-Ala PABC",
                "payload": "DGN549 Sunirine ( IGN )",
                "dar": 2,
                "fcFormat": "igg1_wt",
            }
        }
    )
    assert res_cd123["ref_current"]["spec"]["target"] == "CD123 (IL3RA)"
    assert res_cd123["ref_current"]["spec"]["payload"] == "DGN549 Sunirine ( IGN )"

    # Explicit refAdcId override (e.g., loading KADCYLA / trastuzumab-emtansine into Studio)
    res_kadcyla = SM.evaluate_studio_matrix(
        {
            "spec": {
                "target": "HER2 (ERBB2)",
                "linker": "Non-cleavable SMCC",
                "payload": "DM1 Mertansine ( Maytansinoid )",
                "dar": 3.5,
                "fcFormat": "igg1_wt",
            },
            "refAdcId": "trastuzumab-emtansine",
        }
    )
    assert res_kadcyla["ref_current"]["spec"]["linker"] == "Non-cleavable SMCC"
    assert res_kadcyla["ref_current"]["spec"]["dar"] == 3.5


def test_v095_clean_ui_fonts_and_terminology_invariants():
    import re
    from pathlib import Path
    from ml.adc_version import APP_VERSION

    assert APP_VERSION == "0.9.9"
    root = Path(__file__).resolve().parent.parent
    sw_text = (root / "ml" / "web" / "sw.js").read_text(encoding="utf-8")
    assert "adctox-pwa-v0.9.9" in sw_text

    app_js = (root / "ml" / "web" / "app.js").read_text(encoding="utf-8")
    review_js = (root / "ml" / "web" / "review.js").read_text(encoding="utf-8")
    app_css = (root / "ml" / "web" / "app.css").read_text(encoding="utf-8")
    index_html = (root / "ml" / "web" / "index.html").read_text(encoding="utf-8")
    icon_svg = (root / "ml" / "web" / "icon.svg").read_text(encoding="utf-8")

    for fname, content in [
        ("app.js", app_js),
        ("review.js", review_js),
        ("app.css", app_css),
        ("index.html", index_html),
    ]:
        assert "\u00b7" not in content and "&middot;" not in content, f"middle dot found in {fname}"

    for fname, content in [
        ("app.css", app_css),
        ("app.js", app_js),
        ("icon.svg", icon_svg),
    ]:
        for bad_font in ("Georgia", "ui-monospace"):
            assert bad_font not in content, f"prohibited font {bad_font} in {fname}"
        assert not re.search(r"\bInter\b", content), f"prohibited font Inter in {fname}"

    prohibited_tokens = (
        "참고치",
        "Required Labs",
        "Optional Labs",
        "인구학적 정보",
        "암종",
        "적응증",
        "ADC 비교",
        "자동 탐색",
        "현재 구성 평가",
        "진단 질환 및 기저질환",
        "전체 순위",
        "Deep Research",
        "탄두",
        "설계 축",
        "gtexFold",
        "탐색 최적 설계",
        "고유 승인 구성",
        "모델 점수 0-100",
        "368,640",
        "ADCSurrogateNet v2",
        "데이터 출처 및 지표 기준",
        "Data Sources and Metrics",
        "이전 구성으로 되돌리기",
        "Restore previous construct",
    )
    for fname, content in [("app.js", app_js), ("review.js", review_js)]:
        for tok in prohibited_tokens:
            assert tok not in content, f"prohibited token {tok!r} in {fname}"

    assert app_js.count("임상시험 사례") == app_js.count("환자 질환 관련 임상시험 사례")

    for required in (
        "drawer-export-tab",
        "sim-chart-legend",
        "deep_points",
        "github.com/ahnhc/ADCToX",
        "기본 정보",
        "Basic Information",
        "선택 검진 수치",
        "취약 장기군",
        "장기별 독성 예측",
        "고급 설정",
        "ADC 추천",
        "환자 질환",
        "자동 설계",
        "장기 안전도 예측",
        "항암 효능 예측",
        "신규 페이로드 SMILES",
        "crumb-action-group",
        "minComputeMs: 5000",
        "lastScanAnimMs",
        "전체 승인 ADC 목록",
        "질병 일치",
        "fold-chevron",
        "환자 질환 관련 임상시험 사례",
        "Condition-Related Trial Cases",
        "초기화",
        "seg-glide-pill",
        "studioDeepResearchStream",
    ):
        assert required in app_js, f"missing expected v0.9.8 feature/label {required!r} in app.js"

    # Unboxed warnings in Compare ADCs drawer must stay removed while keeping boxed rule cards
    assert "warnsListEl" not in app_js
    assert "rulesListEl" in app_js
    # Compare ADCs and ADC Design header bar should not inject .lab-summary-row or override .studio-patient-bar layout
    assert "lab-summary-row" not in app_js
    assert not re.search(r"^\.studio-patient-bar\s*\{", app_css, flags=re.M)
    # No solid triangle disclosure markers and keep New Patient button visible on Patient Profile
    assert "\u25b8" not in app_css and "\u25b8" not in app_js
    assert ".profile-demo .scenario-dropdown" not in app_css


def test_deep_research_dose_curve_and_lcb_differentiation():
    from ml import deep_research as DR
    from ml import studio_matrix as SM

    body = {
        "cancerText": "HER2-positive breast cancer",
        "organs": [
            {"organ": "pulmonary", "score": 0.92},
            {"organ": "cardiac", "score": 0.85},
            {"organ": "hepatic", "score": 0.60},
        ],
        "prioOrgan": "pulmonary",
        "simWeights": {
            "wSafety": 0.50,
            "wPeak": 0.50,
            "wExpr": 0.40,
            "leakSens": 0.50,
            "hydroSens": 0.50,
            "fcProtect": 0.65,
            "wSelect": 0.45,
            "wBystander": 0.35,
        },
        "spec": {
            "target": "HER2 (ERBB2)",
            "linker": "GGFG Peptide (Enhertu-like)",
            "payload": "DXd (Exatecan deriv, Topo I)",
            "dar": 8,
            "fcFormat": "igg1_wt",
        },
    }

    res_auto = SM.evaluate_studio_matrix(body)
    res_dr = DR.run_deep_research(body)

    assert res_dr["mode"] == "deep_research_v2"
    best = res_dr["best"]
    dc = best["doseCurve"]
    assert [d["doseMgKg"] for d in dc] == [1.8, 2.4, 3.6, 5.4, 6.0]
    assert sum(1 for d in dc if d["isOptimalDose"]) == 1
    assert dc[0]["safetyRaw"] - dc[-1]["safetyRaw"] >= 8.0
    assert dc[-1]["efficacyRaw"] > dc[0]["efficacyRaw"] + 4.0
    assert best["safetyStd"] >= 0.55
    assert best["efficacyStd"] >= 0.50
    # Deep Research evaluates 5 clinical Q3W doses + 5-fold LCB objective rather than repeating Auto Search unchanged
    differs = (
        best["spec"] != res_auto["best"]["spec"]
        or res_dr["deep_research"]["optimal_dose_mgkg"] != 3.6
        or abs(best["safetyScore"] - res_auto["best"]["safetyScore"]) >= 1
    )
    assert differs


def test_v097_progressive_ode_compute_floor():
    import time
    from ml import deep_research as DR

    t0 = time.perf_counter()
    res = DR.run_deep_research(
        {
            "cancerText": "HER2-positive breast cancer",
            "organs": [{"organ": "pulmonary", "score": 0.90}, {"organ": "cardiac", "score": 0.70}],
            "prioOrgan": "pulmonary",
            "minComputeMs": 1200,
        }
    )
    wall_ms = (time.perf_counter() - t0) * 1000.0
    assert wall_ms >= 1150.0, f"expected >= 1.15s real progressive compute, got {wall_ms:.1f}ms"
    dr_meta = res["deep_research"]
    assert dr_meta["evaluated_constructs"] >= 90
    assert dr_meta["ode_q3w_steps"] == 252
    assert dr_meta["mc_patient_draws"] == 64
    assert dr_meta["elapsed_ms"] >= 1150.0
    assert len(res["deep_points"]) >= 120


def test_v098_deep_research_ndjson_streaming(monkeypatch):
    import http.client
    import json
    import threading
    from ml import recommend as RC
    from ml import suggest as SG
    from ml import webapp

    monkeypatch.setenv("ADCTOX_NO_BROWSER", "1")
    monkeypatch.setattr(SG.Index, "load_mondo", lambda self: None)
    box, up = [], threading.Event()
    t = threading.Thread(
        target=webapp.serve,
        args=(RC,),
        kwargs={"ready": lambda s: (box.append(s), up.set())},
        daemon=True,
    )
    t.start()
    try:
        assert up.wait(10)
        srv = box[0]
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=60)
        payload = json.dumps(
            {
                "stream": True,
                "cancerText": "HER2-positive breast cancer",
                "organs": [{"organ": "pulmonary", "score": 0.90}, {"organ": "cardiac", "score": 0.70}],
                "prioOrgan": "pulmonary",
                "minComputeMs": 5500,
            }
        )
        conn.request("POST", "/api/studio/deep-research", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        assert (resp.getheader("Content-Type") or "").startswith("application/x-ndjson")
        events = []
        for raw_line in resp.read().decode("utf-8").splitlines():
            if raw_line.strip():
                events.append(json.loads(raw_line))
        conn.close()
        chunks = [e for e in events if e.get("type") == "chunk"]
        dones = [e for e in events if e.get("type") == "done"]
        assert len(chunks) >= 2
        assert all(isinstance(c.get("points"), list) and len(c["points"]) > 0 for c in chunks)
        assert len(dones) == 1
        assert dones[0]["result"]["deep_research"]["evaluated_constructs"] >= 90
    finally:
        if box:
            box[0].shutdown()
        t.join(10)





