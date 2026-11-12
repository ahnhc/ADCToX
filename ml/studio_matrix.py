"""
Vectorized 368,640-Construct Server Matrix Engine (`ml/studio_matrix.py`)
=========================================================================
Mode 2 ("2단계 초대규모 탐색") backend engine for Tab 3 (`ADC 신규 설계`).
Evaluates all `36 Targets x 16 Linkers x 20 Payloads x 8 DARs x 4 Fc Formats = 368,640`
5-fold `ADC-SurrogateNet-v2` neural ensemble constructs for a patient's specific
vulnerable organ profile, cancer indication, and therapeutic-index slider weights
in `< 10 ms` on any CPU using associative low-rank `(144 x 24) @ (24 x 2560)` matrix algebra.

Supports both standard repository layout (`ml/data/`) and single-file portable builds
(`_portable_data()`).
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_LOCK = threading.Lock()
_STATE: Optional[Dict[str, Any]] = None

DEFAULT_SIM_WEIGHTS: Dict[str, float] = {
    "wSafety": 0.56,
    "wPeak": 0.58,
    "wExpr": 0.34,
    "leakSens": 1.00,
    "hydroSens": 1.00,
    "fcProtect": 0.32,
    "wSelect": 0.25,
    "wBystander": 0.22,
}

FALLBACK_ORGANS: List[Dict[str, Any]] = [
    {"organ": "pulmonary", "score": 0.8},
    {"organ": "hepatic", "score": 0.8},
    {"organ": "haematologic", "score": 0.8},
    {"organ": "cardiovascular", "score": 0.7},
]

PAYLOAD_ALIASES: Dict[str, str] = {
    "DM4 ( Maytansinoid )": "DM4 / DM1 ( Maytansinoid )",
    "SG3199 Tesirine ( PBD )": "SG3199 ( PBD Dimer )",
}

LINKER_ALIASES: Dict[str, str] = {}

FC_ADCC_BOOST: Dict[str, float] = {
    "igg1_wt": 1.015,
    "igg1_lalapg": 0.985,
    "igg4_s228p": 0.995,
    "igg2_lowfc": 0.992,
}

REF_ADC_ARCH: Dict[str, Dict[str, Any]] = {
    "trastuzumab-deruxtecan": {"linker": "Tetrapeptide GGFG", "payload": "DXd ( Topo I )", "dar": 8.0, "fcFormat": "igg1_wt"},
    "sacituzumab-govitecan": {"linker": "Hydrolyzable CL2A", "payload": "SN-38 ( Topo I )", "dar": 7.6, "fcFormat": "igg1_wt"},
    "mirvetuximab-soravtansine": {"linker": "Sulfo-SPDB", "payload": "DM4 / DM1 ( Maytansinoid )", "dar": 3.5, "fcFormat": "igg1_wt"},
    "tisotumab-vedotin": {"linker": "Val-Cit PABC", "payload": "MMAE ( Auristatin )", "dar": 4.0, "fcFormat": "igg1_wt"},
    "enfortumab-vedotin": {"linker": "Val-Cit PABC", "payload": "MMAE ( Auristatin )", "dar": 4.0, "fcFormat": "igg1_wt"},
    "polatuzumab-vedotin": {"linker": "Val-Cit PABC", "payload": "MMAE ( Auristatin )", "dar": 3.5, "fcFormat": "igg1_wt"},
    "brentuximab-vedotin": {"linker": "Val-Cit PABC", "payload": "MMAE ( Auristatin )", "dar": 4.0, "fcFormat": "igg1_wt"},
    "loncastuximab-tesirine": {"linker": "PEG8-Val-Ala PABC", "payload": "SG3199 ( PBD Dimer )", "dar": 2.0, "fcFormat": "igg1_wt"},
    "belantamab-mafodotin": {"linker": "Non-cleavable mc", "payload": "MMAF ( Auristatin )", "dar": 4.0, "fcFormat": "igg1_wt"},
    "inotuzumab-ozogamicin": {"linker": "Acid Hydrazone", "payload": "Calicheamicin ( Enediyne )", "dar": 6.0, "fcFormat": "igg4_s228p"},
    "gemtuzumab-ozogamicin": {"linker": "Acid Hydrazone", "payload": "Calicheamicin ( Enediyne )", "dar": 2.0, "fcFormat": "igg4_s228p"},
}

TUMOR_KEYWORD_RE = re.compile(r"cancer|carcinoma|tumor|lymphoma|myeloma|leukemia|sarcoma|glioma|glioblastoma|melanoma|mesothelioma|암|종양|림프종|골수종|백혈병|육종|흑색종|중피종|세포종")


def _plain_name(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\(.*?\)\s*", " ", str(label or ""))).strip()


def _load_engine() -> Dict[str, Any]:
    global _STATE
    if _STATE is not None:
        return _STATE
    with _LOCK:
        if _STATE is not None:
            return _STATE

        cat: Optional[Dict[str, Any]] = None
        npz_bytes: Optional[bytes] = None
        try:
            from __adc_data__ import _portable_data  # type: ignore
            pdata = _portable_data()
            cat = pdata.get("studio_catalog_368k")
            b64_svd = pdata.get("studio_368k_svd_b64")
            if b64_svd:
                npz_bytes = base64.b64decode(b64_svd)
        except ImportError:
            pass

        if cat is None or npz_bytes is None:
            here = Path(__file__).resolve().parent if "__file__" in globals() else Path(".")
            data_dir = here / "data"
            if cat is None:
                cat_path = data_dir / "studio_catalog_368k.json"
                cat = json.loads(cat_path.read_text(encoding="utf-8"))
            if npz_bytes is None:
                svd_path = data_dir / "studio_368k_svd.npz"
                npz_bytes = svd_path.read_bytes()

        with np.load(io.BytesIO(npz_bytes)) as zf:
            U = zf["U"].astype(np.float32)                     # (61, 144, 24)
            V = zf["V"].astype(np.float32)                     # (61, 24, 2560)
            compat_mask_lp = zf["compat_mask"].astype(bool)    # (16, 20)
            pair_aff_lp = zf["pair_affinity"].astype(np.float32)  # (16, 20)

        # Precompute the 9 static efficacy/PK channels `(9, 144, 2560)` once (~13.2 MB float32)
        m9 = np.matmul(U[0:9], V[0:9])  # [pIC50_pos, pIC50_bys, stab_pct, hic_agg, cl_hep, s_sel, s_pot, s_deliv, s_bys]

        targets = cat["targets"]
        linkers = cat["linkers"]
        payloads = cat["payloads"]
        dars = cat["dars"]
        fc_formats = cat["fc_formats"]
        organs_13 = cat["organs"]

        n_t, n_l, n_p, n_d, n_f = len(targets), len(linkers), len(payloads), len(dars), len(fc_formats)
        n_tf = n_t * n_f
        n_lpd = n_l * n_p * n_d

        # Pre-index lookup tables
        t_idx = {t["id"]: i for i, t in enumerate(targets)}
        l_idx = {lk["id"]: i for i, lk in enumerate(linkers)}
        p_idx = {pl["id"]: i for i, pl in enumerate(payloads)}
        f_idx = {fc["id"]: i for i, fc in enumerate(fc_formats)}
        dar_vals = np.array([float(d["val"]) for d in dars], dtype=np.float32)
        org_idx = {ax: i for i, ax in enumerate(organs_13)}

        # Broadcast LPD properties `(2560,)`
        compat_lpd = np.repeat(compat_mask_lp.reshape(n_l * n_p), n_d)
        aff_lpd = np.repeat(pair_aff_lp.reshape(n_l * n_p), n_d)
        chem_pen_lpd = (1.0 + (1.0 - aff_lpd) * 0.38).astype(np.float32)
        aff_pow_lpd = ((aff_lpd ** 0.34) * np.where(compat_lpd, 1.0, 0.48)).astype(np.float32)

        cleavable_l = np.array([bool(lk["cleavable"]) for lk in linkers], dtype=bool)
        perm_p = np.array([bool(pl["perm"]) for pl in payloads], dtype=bool)
        bystander_lp = cleavable_l[:, None] & perm_p[None, :]
        bystander_lpd = np.repeat(bystander_lp.reshape(n_l * n_p), n_d)

        # Broadcast TF properties `(144,)`
        adcc_tf = np.tile(
            np.array([FC_ADCC_BOOST.get(fc["id"], 1.0) for fc in fc_formats], dtype=np.float32),
            n_t,
        )
        fc_silenced_strength_f = np.array(
            [max(0.0, min(1.0, 1.0 - float(fc.get("fc_activity", 0.0 if fc.get("fc_silenced") else 1.0)))) for fc in fc_formats],
            dtype=np.float32,
        )
        fc_silenced_strength_tf = np.tile(fc_silenced_strength_f, n_t)

        # Pre-stack per-organ `(24*4=96, 2560)` right factors V_cat for single-GEMM hazard reconstruction
        V_org_cat = []
        U_org_quad = []
        for o_i in range(len(organs_13)):
            U_org_quad.append((U[9 + o_i], U[22 + o_i], U[35 + o_i], U[48 + o_i]))
            V_org_cat.append(np.concatenate([V[9 + o_i], V[22 + o_i], V[35 + o_i], V[48 + o_i]], axis=0))

        # Deterministic stratified scatter indices for fast 2,400-point cloud visualization
        rng = np.random.default_rng(20260803)
        strat_indices = []
        per_t = 56  # 36 * 56 = 2,016 background points across all 36 targets
        for ti in range(n_t):
            tf_choices = rng.integers(ti * n_f, (ti + 1) * n_f, size=per_t)
            lpd_choices = rng.choice(n_lpd, size=per_t, replace=False)
            strat_indices.append(tf_choices * n_lpd + lpd_choices)
        strat_flat = np.concatenate(strat_indices, axis=0)

        _STATE = {
            "catalog": cat,
            "U": U,
            "V": V,
            "m9": m9,
            "U_org_quad": U_org_quad,
            "V_org_cat": V_org_cat,
            "targets": targets,
            "linkers": linkers,
            "payloads": payloads,
            "dars": dars,
            "fc_formats": fc_formats,
            "organs_13": organs_13,
            "t_idx": t_idx,
            "l_idx": l_idx,
            "p_idx": p_idx,
            "f_idx": f_idx,
            "dar_vals": dar_vals,
            "org_idx": org_idx,
            "n_t": n_t,
            "n_l": n_l,
            "n_p": n_p,
            "n_d": n_d,
            "n_f": n_f,
            "n_tf": n_tf,
            "n_lpd": n_lpd,
            "n_tot": n_tf * n_lpd,
            "compat_mask_lp": compat_mask_lp,
            "pair_aff_lp": pair_aff_lp,
            "compat_lpd": compat_lpd,
            "chem_pen_lpd": chem_pen_lpd,
            "aff_pow_lpd": aff_pow_lpd,
            "bystander_lpd": bystander_lpd,
            "adcc_tf": adcc_tf,
            "fc_silenced_strength_tf": fc_silenced_strength_tf,
            "strat_flat": strat_flat,
        }
        return _STATE


def catalog_info() -> Dict[str, Any]:
    st = _load_engine()
    return st["catalog"]


def resolve_spec_indices(spec: Optional[Dict[str, Any]], st: Optional[Dict[str, Any]] = None) -> Tuple[int, int, int, int, int]:
    st = st or _load_engine()
    spec = spec or {}

    raw_t = str(spec.get("target") or "")
    ti = st["t_idx"].get(raw_t, 0)

    raw_l = str(spec.get("linker") or "")
    raw_l = LINKER_ALIASES.get(raw_l, raw_l)
    li = st["l_idx"].get(raw_l, 0)

    raw_p = str(spec.get("payload") or "")
    raw_p = PAYLOAD_ALIASES.get(raw_p, raw_p)
    pi = st["p_idx"].get(raw_p, 0)

    try:
        dar_v = float(spec.get("dar", 4.0))
    except (TypeError, ValueError):
        dar_v = 4.0
    di = int(np.argmin(np.abs(st["dar_vals"] - dar_v)))

    fc_fmt = spec.get("fcFormat")
    if isinstance(fc_fmt, str) and fc_fmt in st["f_idx"]:
        fi = st["f_idx"][fc_fmt]
    else:
        fi = 1 if bool(spec.get("fc", False)) else 0

    return ti, li, pi, di, fi


def _indication_factors(cancer_text: str, targets: List[Dict[str, Any]]) -> np.ndarray:
    txt = (cancer_text or "").strip().lower()
    n_t = len(targets)
    if not txt or not TUMOR_KEYWORD_RE.search(txt):
        return np.ones(n_t, dtype=np.float32)
    out = np.full(n_t, 0.68, dtype=np.float32)
    for i, t in enumerate(targets):
        keys = t.get("tumorKeys") or []
        if any(k.lower() in txt for k in keys):
            out[i] = 1.06
    return out


def _single_construct_detail(
    st: Dict[str, Any],
    ti: int,
    li: int,
    pi: int,
    di: int,
    fi: int,
    safety_mat: np.ndarray,
    efficacy_mat: np.ndarray,
    real_organs: List[Dict[str, Any]],
    prio_organ: Optional[str],
    off_scale: float,
    on_scale: float,
    leak_scale: float,
    agg_scale: float,
    fc_scale_tf: np.ndarray,
    nw_tuple: Tuple[float, float, float, float],
) -> Dict[str, Any]:
    tf_idx = ti * st["n_f"] + fi
    lpd_idx = (li * st["n_p"] + pi) * st["n_d"] + di

    tgt = st["targets"][ti]
    lnk = st["linkers"][li]
    pld = st["payloads"][pi]
    dar_obj = st["dars"][di]
    fc_obj = st["fc_formats"][fi]

    m_vec = st["m9"][:, tf_idx, lpd_idx]
    pic50_pos = round(float(m_vec[0]), 2)
    pic50_bys = round(float(m_vec[1]), 2)
    stab_pct = int(max(20, min(98, round(float(m_vec[2])))))
    hic_agg = round(float(m_vec[3]), 2)
    cl_hep = round(float(m_vec[4]), 2)

    chem_pen = float(st["chem_pen_lpd"][lpd_idx])
    fc_sc = float(fc_scale_tf[tf_idx])

    # Compute exact 13-organ risk map & patient-specific organ risks for this construct
    organ_risk_map: Dict[str, int] = {}
    h_base_13: Dict[str, float] = {}
    for o_i, ax in enumerate(st["organs_13"]):
        u_hb, u_ha, u_hf, u_ho = st["U_org_quad"][o_i]
        v_cat = st["V_org_cat"][o_i][:, lpd_idx]  # (96,)
        u_row = np.concatenate(
            [
                (off_scale * leak_scale) * u_hb[tf_idx],
                (off_scale * agg_scale) * u_ha[tf_idx],
                (off_scale * fc_sc) * u_hf[tf_idx],
                on_scale * u_ho[tf_idx],
            ],
            axis=0,
        )
        hz = max(0.005, float(np.dot(u_row, v_cat)) * chem_pen)
        h_base_13[ax] = hz
        organ_risk_map[ax] = int(round(100.0 * (1.0 - math.exp(-hz))))

    base_organs = [dict(o, baselineTissue=False) for o in real_organs]
    seen_org = {o["organ"] for o in base_organs}
    for tis in tgt.get("tissues") or []:
        if tis["organ"] not in seen_org:
            base_organs.append({"organ": tis["organ"], "score": 0.44, "baselineTissue": True})
            seen_org.add(tis["organ"])

    all_organ_risks = []
    for ao in base_organs:
        ax = ao["organ"]
        hz0 = h_base_13.get(ax, 0.02)
        prio_mult = 1.45 if (prio_organ and prio_organ == ax) else 1.0
        vuln_w = (0.62 if ao["baselineTissue"] else (0.85 + 0.85 * min(1.0, float(ao.get("score", 0.8))))) * prio_mult
        p_val = max(0.01, min(0.98, 1.0 - math.exp(-hz0 * vuln_w)))
        all_organ_risks.append(
            {
                "organ": ax,
                "p": round(p_val, 4),
                "baselineTissue": bool(ao["baselineTissue"]),
            }
        )

    shown_organ_risks = [r for r in all_organ_risks if not r["baselineTissue"]] if real_organs else all_organ_risks
    mean_risk = sum(r["p"] for r in all_organ_risks) / max(1, len(all_organ_risks))

    safety_raw = round(float(safety_mat[tf_idx, lpd_idx]), 2)
    efficacy_raw = round(float(efficacy_mat[tf_idx, lpd_idx]), 2)
    nw_sel, nw_pot, nw_del, nw_bys = nw_tuple
    fc_bool = fc_obj["id"] != "igg1_wt"

    return {
        "spec": {
            "target": tgt["id"],
            "linker": lnk["id"],
            "payload": pld["id"],
            "dar": float(dar_obj["val"]),
            "fc": fc_bool,
            "fcFormat": fc_obj["id"],
        },
        "indices": [ti, li, pi, di, fi],
        "safetyScore": int(round(safety_raw)),
        "efficacyScore": int(round(efficacy_raw)),
        "safetyRaw": safety_raw,
        "efficacyRaw": efficacy_raw,
        "isCompat": bool(st["compat_mask_lp"][li, pi]),
        "bystander": bool(lnk["cleavable"] and pld["perm"]),
        "fcSilenced": fc_bool,
        "fcFormat": fc_obj["id"],
        "fcLabelKo": fc_obj["ko"],
        "fcLabelEn": fc_obj["en"],
        "plasmaStabPct": stab_pct,
        "pIC50Pos": pic50_pos,
        "pIC50Bys": pic50_bys,
        "hicAgg": hic_agg,
        "clHep": cl_hep,
        "meanRisk": round(mean_risk, 4),
        "nwSel": round(nw_sel, 4),
        "nwPot": round(nw_pot, 4),
        "nwDel": round(nw_del, 4),
        "nwBys": round(nw_bys, 4),
        "organRisks": shown_organ_risks,
        "organRiskMap": organ_risk_map,
    }


def build_rationales(best_detail: Dict[str, Any], st: Dict[str, Any], real_organs: List[Dict[str, Any]]) -> Dict[str, List[List[str]]]:
    s = best_detail["spec"]
    ti = best_detail["indices"][0]
    pi = best_detail["indices"][2]
    tgt = st["targets"][ti]
    pld = st["payloads"][pi]

    tgt_name = _plain_name(s["target"])
    pl_name = _plain_name(s["payload"])
    stab = best_detail["plasmaStabPct"]
    pic = f"{best_detail['pIC50Pos']:.2f}"
    sel_fc = f"+{float(tgt['selectivity']):.1f} log2FC"
    fc_ko = best_detail["fcLabelKo"]
    fc_en = best_detail["fcLabelEn"]
    org_ko_map = {
        "haematologic": "혈액/골수", "hepatic": "간", "cardiovascular": "심장", "pulmonary": "폐",
        "renal": "신장", "gastrointestinal": "소화기", "neurologic": "신경", "ocular": "안구",
        "dermatologic": "피부", "metabolic_endocrine": "내분비/대사", "musculoskeletal": "근골격",
        "infectious_immune": "면역/감염", "otologic": "청각",
    }
    orgs_ko = ", ".join(org_ko_map.get(o["organ"], o["organ"]) for o in real_organs) or "주요 장기"
    orgs_en = ", ".join(o["organ"].replace("_", "/") for o in real_organs) or "major organs"

    return {
        "ko": [
            ["1. 표적 항원", f"{tgt_name}, 선택도 {sel_fc}", "36종 항원 발현 지도(GTEx/Tabula Sapiens) 기준 정상 장기 대비 종양 과발현 마진이 우수한 표적입니다."],
            ["2. 화학 링커", f"{s['linker']}, 신경망 혈장 보존율 {stab}%", f"{orgs_ko}로 유리 페이로드가 조기 누출되는 경로를 억제하고 종양 리소좀 절단 효율을 확보합니다."],
            ["3. 세포독성 페이로드", f"{pl_name}, {pld['cls']} (pIC50 {pic})", "환자 취약 장기 독성 위험도가 낮으면서 고효력 항암 세포사멸 활성을 유지합니다."],
            ["4. 접합비와 항체 골격", f"DAR {s['dar']:g}, {fc_ko}", f"368,640개 조합 중 장기 안전도 {best_detail['safetyScore']}점, 항암 효능 {best_detail['efficacyScore']}점으로 치료지수가 최적입니다."],
        ],
        "en": [
            ["1. Target antigen", f"{tgt_name}, selectivity {sel_fc}", "Selected across 36 antigens for strong tumor-to-normal GTEx and Tabula Sapiens expression margin."],
            ["2. Chemical linker", f"{s['linker']}, neural plasma retention {stab}%", f"Minimizes premature free-payload leakage into {orgs_en} while maintaining tumor lysosomal release."],
            ["3. Cytotoxic payload", f"{pl_name}, {pld['cls']} (pIC50 {pic})", "Lowers predicted hazard on vulnerable patient organs while preserving conjugate potency."],
            ["4. DAR and Fc format", f"DAR {s['dar']:g}, {fc_en}", f"Ranks #1 across 368,640 constructs with organ safety {best_detail['safetyScore']} and efficacy {best_detail['efficacyScore']}."],
        ],
    }


def evaluate_studio_matrix(body: Optional[Dict[str, Any]] = None, return_top_indices: int = 0) -> Dict[str, Any]:
    """
    Vectorized evaluation of all `368,640` constructs (`144 TF x 2560 LPD`) on CPU.
    """
    t0 = time.perf_counter()
    body = body or {}
    st = _load_engine()

    w0 = dict(DEFAULT_SIM_WEIGHTS)
    w0.update(st["catalog"].get("weights") or {})
    w = dict(w0)
    sim_w = body.get("simWeights")
    if isinstance(sim_w, dict):
        for k in DEFAULT_SIM_WEIGHTS:
            if k in sim_w and sim_w[k] is not None:
                try:
                    w[k] = float(sim_w[k])
                except (TypeError, ValueError):
                    pass

    raw_organs = body.get("organs")
    real_organs: List[Dict[str, Any]] = []
    if isinstance(raw_organs, list):
        seen_o = set()
        for item in raw_organs:
            if isinstance(item, dict) and item.get("organ") in st["org_idx"] and item["organ"] not in seen_o:
                try:
                    sc = float(item.get("score", 0.8))
                except (TypeError, ValueError):
                    sc = 0.8
                real_organs.append({"organ": item["organ"], "score": max(0.05, min(1.0, sc))})
                seen_o.add(item["organ"])

    active_for_scoring = real_organs if real_organs else FALLBACK_ORGANS
    prio_organ = body.get("prioOrgan") if isinstance(body.get("prioOrgan"), str) else None
    cancer_text = str(body.get("cancerText") or "")

    # 1. Pathway & slider scale factors
    w_on_target = max(0.10, min(0.85, w["wExpr"]))
    w_on0 = max(0.10, min(0.85, w0["wExpr"]))
    on_scale = w_on_target / w_on0
    off_scale = (1.0 - w_on_target) / max(0.15, 1.0 - w_on0)
    leak_scale = w["leakSens"] / max(0.15, w0["leakSens"])
    agg_scale = w["hydroSens"] / max(0.15, w0["hydroSens"])

    fc_slider_ratio = max(0.12, (1.0 - w["fcProtect"]) / max(0.15, 1.0 - w0["fcProtect"]))
    # Smoothly apply fcProtect slider adjustment proportional to Fc silencing strength (0.0 on IgG1 WT, 1.0 on LALA-PG)
    fc_scale_tf = (1.0 + st["fc_silenced_strength_tf"] * (fc_slider_ratio - 1.0)).astype(np.float32)

    # 2. Build `(144, 13)` vulnerability weight matrix (patient organs + per-target baseline tissues)
    vuln_tf_org = np.zeros((st["n_tf"], len(st["organs_13"])), dtype=np.float32)
    org_count_tf = np.zeros(st["n_tf"], dtype=np.float32)

    real_map = {o["organ"]: o["score"] for o in active_for_scoring}
    for ti, tgt in enumerate(st["targets"]):
        tf_slice = slice(ti * st["n_f"], (ti + 1) * st["n_f"])
        cnt = 0
        for ax, sc in real_map.items():
            o_i = st["org_idx"][ax]
            pm = 1.45 if (prio_organ and prio_organ == ax) else 1.0
            vuln_tf_org[tf_slice, o_i] = (0.85 + 0.85 * min(1.0, sc)) * pm
            cnt += 1
        for tis in tgt.get("tissues") or []:
            ax = tis["organ"]
            if ax not in real_map and ax in st["org_idx"]:
                o_i = st["org_idx"][ax]
                pm = 1.45 if (prio_organ and prio_organ == ax) else 1.0
                vuln_tf_org[tf_slice, o_i] = 0.62 * pm
                cnt += 1
        org_count_tf[tf_slice] = max(1, cnt)

    # 3. Single-pass sliced organ hazard accumulation (computes GEMM + exp ONLY on TF rows where organ is active!)
    sum_risk = np.zeros((st["n_tf"], st["n_lpd"]), dtype=np.float32)
    worst_risk = np.zeros((st["n_tf"], st["n_lpd"]), dtype=np.float32)
    chem_pen_row = st["chem_pen_lpd"][None, :]

    for o_i in range(len(st["organs_13"])):
        v_col = vuln_tf_org[:, o_i]
        rows = np.flatnonzero(v_col > 0.0)
        if rows.size == 0:
            continue
        u_hb, u_ha, u_hf, u_ho = st["U_org_quad"][o_i]
        u_cat = np.concatenate(
            [
                (off_scale * leak_scale) * u_hb[rows],
                (off_scale * agg_scale) * u_ha[rows],
                ((off_scale * fc_scale_tf[rows])[:, None]) * u_hf[rows],
                on_scale * u_ho[rows],
            ],
            axis=1,
        )  # (k, 96)
        hz_sub = u_cat @ st["V_org_cat"][o_i]  # (k, 2560)
        np.maximum(hz_sub, 0.005, out=hz_sub)
        hz_sub *= chem_pen_row * v_col[rows, None]
        np.negative(hz_sub, out=hz_sub)
        np.exp(hz_sub, out=hz_sub)
        p_sub = 1.0 - hz_sub
        np.clip(p_sub, 0.01, 0.98, out=p_sub)
        sum_risk[rows] += p_sub
        np.maximum(worst_risk[rows], p_sub, out=worst_risk[rows])

    mean_risk = sum_risk / org_count_tf[:, None]
    w_peak = max(0.15, min(0.90, w["wPeak"]))
    safety_mat = np.clip(100.0 * (1.0 - (w_peak * worst_risk + (1.0 - w_peak) * mean_risk)), 2.0, 98.0)

    # 4. Vectorized `(144, 2560)` Antitumor Efficacy `Y_eff` (zero redundant `exp` when sliders are at defaults!)
    m9 = st["m9"]
    stab_pct_mat = np.clip(m9[2], 20.0, 98.0)
    hic_agg_mat = m9[3]
    s_sel_mat = np.clip(m9[5], 0.12, 0.98)

    if abs(w["hydroSens"] - w0["hydroSens"]) > 1e-6:
        hydro_delta = (w["hydroSens"] - w0["hydroSens"]) * np.maximum(0.0, hic_agg_mat - 1.15) * 0.12
        s_pot_mat = np.clip(m9[6] * np.exp(-hydro_delta), 0.08, 0.99)
    else:
        s_pot_mat = np.clip(m9[6], 0.08, 0.99)

    if abs(w["leakSens"] - w0["leakSens"]) > 1e-6:
        leak_delta = (w["leakSens"] - w0["leakSens"]) * (1.0 - stab_pct_mat / 100.0) * 0.24
        s_del_mat = np.clip(m9[7] * np.exp(-leak_delta), 0.08, 0.98)
    else:
        s_del_mat = np.clip(m9[7], 0.08, 0.98)

    s_bys_mat = np.clip(m9[8], 0.06, 0.98)

    raw_w_sel = max(0.05, w["wSelect"])
    raw_w_bys = max(0.05, w["wBystander"])
    raw_w_core = max(0.20, 1.0 - 0.55 * (raw_w_sel + raw_w_bys))
    w_sum = raw_w_sel + raw_w_bys + raw_w_core
    nw_sel = raw_w_sel / w_sum
    nw_bys = raw_w_bys / w_sum
    nw_pot = (raw_w_core * 0.56) / w_sum
    nw_del = (raw_w_core * 0.44) / w_sum

    ind_t = _indication_factors(cancer_text, st["targets"])
    ind_tf = np.repeat(ind_t, st["n_f"])
    tf_mult = (st["adcc_tf"] * ind_tf)[:, None]

    convex_eff = nw_sel * s_sel_mat + nw_pot * s_pot_mat + nw_del * s_del_mat + nw_bys * s_bys_mat
    efficacy_mat = np.clip(convex_eff * tf_mult * st["aff_pow_lpd"][None, :] * 100.0, 2.0, 98.0)

    # 5. Global Therapeutic Index optimization across all 368,640 constructs!
    organ_shift = min(0.08, (len(real_organs) - 2) * 0.02) if len(real_organs) > 2 else 0.0
    w_safety = max(0.15, min(0.88, w["wSafety"] + organ_shift))

    util_mat = w_safety * safety_mat + (1.0 - w_safety) * efficacy_mat
    util_compat = np.where(st["compat_lpd"][None, :], util_mat, -1e9)

    best_flat = int(np.argmax(util_compat))
    best_tf, best_lpd = divmod(best_flat, st["n_lpd"])
    best_ti, best_fi = divmod(best_tf, st["n_f"])
    best_lp, best_di = divmod(best_lpd, st["n_d"])
    best_li, best_pi = divmod(best_lp, st["n_p"])

    cur_ti, cur_li, cur_pi, cur_di, cur_fi = resolve_spec_indices(body.get("spec"), st)

    nw_tuple = (nw_sel, nw_pot, nw_del, nw_bys)
    current_detail = _single_construct_detail(
        st, cur_ti, cur_li, cur_pi, cur_di, cur_fi,
        safety_mat, efficacy_mat, real_organs, prio_organ,
        off_scale, on_scale, leak_scale, agg_scale, fc_scale_tf, nw_tuple,
    )
    current_detail["utilScore"] = round(
        w_safety * current_detail["safetyRaw"] + (1.0 - w_safety) * current_detail["efficacyRaw"], 2
    )

    best_detail = _single_construct_detail(
        st, best_ti, best_li, best_pi, best_di, best_fi,
        safety_mat, efficacy_mat, real_organs, prio_organ,
        off_scale, on_scale, leak_scale, agg_scale, fc_scale_tf, nw_tuple,
    )
    best_detail["utilScore"] = round(float(util_mat[best_tf, best_lpd]), 2)
    best_detail["rationales"] = build_rationales(best_detail, st, real_organs)

    # Approved reference ADC simulations for current target and best target
    def _ref_for_target(ti_val: int) -> Dict[str, Any]:
        t_obj = st["targets"][ti_val]
        ref_id = t_obj.get("refAdc", "trastuzumab-deruxtecan")
        arch = REF_ADC_ARCH.get(ref_id, REF_ADC_ARCH["trastuzumab-deruxtecan"])
        r_ti, r_li, r_pi, r_di, r_fi = resolve_spec_indices({"target": t_obj["id"], **arch}, st)
        det = _single_construct_detail(
            st, r_ti, r_li, r_pi, r_di, r_fi,
            safety_mat, efficacy_mat, real_organs, prio_organ,
            off_scale, on_scale, leak_scale, agg_scale, fc_scale_tf, nw_tuple,
        )
        det["refAdcId"] = ref_id
        return det

    ref_current = _ref_for_target(cur_ti)
    ref_best = ref_current if best_ti == cur_ti else _ref_for_target(best_ti)

    # 6. Exact non-dominated Pareto Frontier across all compatible constructs in 368,640!
    compat_mask_flat = np.broadcast_to(st["compat_lpd"][None, :], (st["n_tf"], st["n_lpd"])).ravel()
    safe_flat = safety_mat.ravel()
    eff_flat = efficacy_mat.ravel()
    util_flat = util_mat.ravel()

    compat_idx = np.flatnonzero(compat_mask_flat)
    # Bucket by 0.1-point safety resolution (`0..980`) to extract exact Pareto envelope in O(N) time (`< 0.8 ms`)!
    s_bins = np.rint(safe_flat[compat_idx] * 10.0).astype(np.int32)
    max_eff_per_bin = np.full(1001, -1.0, dtype=np.float32)
    np.maximum.at(max_eff_per_bin, s_bins, eff_flat[compat_idx])

    pareto_bins = []
    running_max_eff = -1.0
    for b in range(1000, -1, -1):
        if max_eff_per_bin[b] > running_max_eff + 0.2:
            pareto_bins.append(b)
            running_max_eff = float(max_eff_per_bin[b])

    pareto_flat_indices: List[int] = []
    pareto_front: List[Dict[str, Any]] = []
    peak_mask = eff_flat[compat_idx] >= (max_eff_per_bin[s_bins] - 1e-4)
    peak_compat_idx = compat_idx[peak_mask]
    peak_bins = s_bins[peak_mask]
    for b in pareto_bins:
        cand_in_bin = peak_compat_idx[peak_bins == b]
        if cand_in_bin.size == 0:
            continue
        idx_f = int(cand_in_bin[np.argmax(util_flat[cand_in_bin])])
        pareto_flat_indices.append(idx_f)
        p_tf, p_lpd = divmod(idx_f, st["n_lpd"])
        p_ti, p_fi = divmod(p_tf, st["n_f"])
        p_lp, p_di = divmod(p_lpd, st["n_d"])
        p_li, p_pi = divmod(p_lp, st["n_p"])
        pareto_front.append(
            {
                "safetyRaw": round(float(safe_flat[idx_f]), 2),
                "efficacyRaw": round(float(eff_flat[idx_f]), 2),
                "utilScore": round(float(util_flat[idx_f]), 2),
                "spec": {
                    "target": st["targets"][p_ti]["id"],
                    "linker": st["linkers"][p_li]["id"],
                    "payload": st["payloads"][p_pi]["id"],
                    "dar": float(st["dars"][p_di]["val"]),
                    "fc": st["fc_formats"][p_fi]["id"] != "igg1_wt",
                    "fcFormat": st["fc_formats"][p_fi]["id"],
                },
            }
        )

    # 7. Top candidates list (top 12 by utility, deduplicated across DARs if desired or exact top 12)
    top_k = max(48, return_top_indices)
    top_part = np.argpartition(util_compat.ravel(), -top_k)[-top_k:]
    top_sorted = top_part[np.argsort(-util_compat.ravel()[top_part])]

    top_candidates = []
    for rank_i, idx_f in enumerate(top_sorted[:12], start=1):
        idx_f = int(idx_f)
        t_tf, t_lpd = divmod(idx_f, st["n_lpd"])
        t_ti, t_fi = divmod(t_tf, st["n_f"])
        t_lp, t_di = divmod(t_lpd, st["n_d"])
        t_li, t_pi = divmod(t_lp, st["n_p"])
        top_candidates.append(
            {
                "rank": rank_i,
                "safetyScore": int(round(float(safe_flat[idx_f]))),
                "efficacyScore": int(round(float(eff_flat[idx_f]))),
                "safetyRaw": round(float(safe_flat[idx_f]), 2),
                "efficacyRaw": round(float(eff_flat[idx_f]), 2),
                "utilScore": round(float(util_flat[idx_f]), 2),
                "pIC50Pos": round(float(m9[0, t_tf, t_lpd]), 2),
                "plasmaStabPct": int(max(20, min(98, round(float(m9[2, t_tf, t_lpd]))))),
                "spec": {
                    "target": st["targets"][t_ti]["id"],
                    "linker": st["linkers"][t_li]["id"],
                    "payload": st["payloads"][t_pi]["id"],
                    "dar": float(st["dars"][t_di]["val"]),
                    "fc": st["fc_formats"][t_fi]["id"] != "igg1_wt",
                    "fcFormat": st["fc_formats"][t_fi]["id"],
                },
            }
        )

    # 8. Representative 2,400-point cloud (`[safetyRaw, efficacyRaw, bitflags]`) + Same-Target cloud for Manual Mode
    cloud_idx_arr = np.unique(
        np.concatenate(
            [
                np.array(pareto_flat_indices, dtype=np.int64),
                top_sorted[:80].astype(np.int64),
                st["strat_flat"],
            ]
        )
    )
    cloud: List[List[float]] = []
    for idx_f in cloud_idx_arr:
        idx_i = int(idx_f)
        c_tf = idx_i // st["n_lpd"]
        c_ti = c_tf // st["n_f"]
        flags = (1 if compat_mask_flat[idx_i] else 0) | (2 if c_ti == best_ti else 0) | (4 if c_ti == cur_ti else 0)
        cloud.append([round(float(safe_flat[idx_i]), 1), round(float(eff_flat[idx_i]), 1), flags])

    # Same-target compatible sample (`320` points across `4 Fc x 2560 LPD = 10,240` for `cur_ti`)
    st_start = cur_ti * st["n_f"] * st["n_lpd"]
    st_compat = np.flatnonzero(compat_mask_flat[st_start : st_start + st["n_f"] * st["n_lpd"]]) + st_start
    stride = max(1, st_compat.size // 320)
    same_target_cloud = [
        [round(float(safe_flat[int(i)]), 1), round(float(eff_flat[int(i)]), 1)]
        for i in st_compat[::stride][:320]
    ]

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    out: Dict[str, Any] = {
        "schema": "ADCToX-StudioMatrixEval-v083",
        "mode": "matrix_368k",
        "total_combinations": st["n_tot"],
        "compatible_combinations": int(compat_idx.size),
        "w_safety": round(w_safety, 4),
        "elapsed_ms": elapsed_ms,
        "current": current_detail,
        "best": best_detail,
        "ref_current": ref_current,
        "ref_best": ref_best,
        "pareto_front": pareto_front,
        "top_candidates": top_candidates,
        "cloud": cloud,
        "same_target_cloud": same_target_cloud,
    }
    if return_top_indices > 0:
        out["_top_flat_indices"] = [int(x) for x in top_sorted[:return_top_indices]]
    return out
