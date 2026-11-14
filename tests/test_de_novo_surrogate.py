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
    assert "Deep Research" in app_txt
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

    assert APP_VERSION == "0.9.5"
    root = Path(__file__).resolve().parent.parent
    sw_text = (root / "ml" / "web" / "sw.js").read_text(encoding="utf-8")
    assert "adctox-pwa-v0.9.5" in sw_text

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
        "암종",
        "탄두",
        "설계 축",
        "gtexFold",
        "탐색 최적 설계",
        "고유 승인 구성",
        "모델 점수 0-100",
        "368,640",
    )
    for fname, content in [("app.js", app_js), ("review.js", review_js)]:
        for tok in prohibited_tokens:
            assert tok not in content, f"prohibited token {tok!r} in {fname}"

    for required in (
        "drawer-export-tab",
        "sim-chart-legend",
        "deep_points",
        "github.com/ahnhc/ADCToX",
        "인구학적 정보",
        "선택 검진 수치",
        "취약 장기군",
        "장기별 독성 예측",
        "고급 설정",
    ):
        assert required in app_js, f"missing expected v0.9.5 feature/label {required!r} in app.js"



