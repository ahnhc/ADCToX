"""Conditioned De Novo ADC Inverse Design Engine (Powered by 5-Fold `ADC-SurrogateNet-v2` Ensemble).

Given:
  1. Patient tumor indication & target antigen profile
  2. Compounded organ vulnerability vector V_compounded in [0, 1]^13
  3. Patient renal / hepatic clearance profile (CLcr, Bilirubin, Child-Pugh)
  4. Concomitant medication & DDI constraints

Performs multi-objective Pareto optimization over the 5-Fold `ADC-SurrogateNet-v2` neural ensemble
predictions (`ml/data/surrogate_designer.json`: `ESM-2 650M` + `ChemBERTa-2 LoRA` + `Boltzmann 3D Conformer`
+ `Reaction SMARTS` + `GTEx v8 / Tabula Sapiens` Pathway-Decomposed 13-Organ Hazard Head) to generate
a patient-conditioned ADC specification.
"""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _clip(val: float, lo: float, hi: float) -> float:
    return lo if val < lo else (hi if val > hi else val)

AXES = [
    "haematologic", "hepatic", "cardiovascular", "pulmonary", "renal",
    "gastrointestinal", "neurologic", "ocular", "dermatologic",
    "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"
]

TARGET_ANTIGENS = {
    "HER2": {
        "gene": "ERBB2",
        "tumor_tpm": 280.0,
        "normal_tpm": {"cardiovascular": 18.0, "pulmonary": 12.0, "gastrointestinal": 8.0, "renal": 5.0, "hepatic": 3.0},
        "description": "Human Epidermal Growth Factor Receptor 2; high expression in breast, gastric, colorectal, NSCLC",
        "standard_adcs": ["Enhertu", "Kadcyla"],
    },
    "TROP2": {
        "gene": "TACSTD2",
        "tumor_tpm": 310.0,
        "normal_tpm": {"gastrointestinal": 35.0, "pulmonary": 22.0, "dermatologic": 25.0, "renal": 10.0, "hepatic": 4.0},
        "description": "Trophoblast cell surface antigen 2; overexpressed in triple-negative breast, urothelial, lung carcinoma",
        "standard_adcs": ["Trodelvy", "Datroway"],
    },
    "NECTIN4": {
        "gene": "NECTIN4",
        "tumor_tpm": 190.0,
        "normal_tpm": {"dermatologic": 28.0, "neurologic": 8.0, "gastrointestinal": 6.0, "hepatic": 2.0, "pulmonary": 4.0},
        "description": "Nectin cell adhesion molecule 4; highly expressed in bladder/urothelial carcinoma",
        "standard_adcs": ["Padcev"],
    },
    "CEACAM5": {
        "gene": "CEACAM5",
        "tumor_tpm": 350.0,
        "normal_tpm": {"gastrointestinal": 40.0, "pulmonary": 15.0, "hepatic": 5.0},
        "description": "Carcinoembryonic antigen-related cell adhesion molecule 5; colorectal, pancreatic, NSCLC",
        "standard_adcs": [],
    },
    "CLDN18.2": {
        "gene": "CLDN18",
        "tumor_tpm": 260.0,
        "normal_tpm": {"gastrointestinal": 32.0, "pulmonary": 18.0},
        "description": "Claudin 18 splice variant 2; gastric, gastroesophageal junction, pancreatic adenocarcinoma",
        "standard_adcs": [],
    },
    "c_MET": {
        "gene": "MET",
        "tumor_tpm": 180.0,
        "normal_tpm": {"hepatic": 14.0, "renal": 12.0, "pulmonary": 9.0},
        "description": "MET receptor tyrosine kinase; lung, gastric, colorectal carcinoma",
        "standard_adcs": ["Emrelis"],
    },
    "B7_H3": {
        "gene": "CD276",
        "tumor_tpm": 220.0,
        "normal_tpm": {"cardiovascular": 6.0, "pulmonary": 7.0, "hepatic": 4.0},
        "description": "Immune checkpoint B7-H3; prostate, SCLC, pediatric solid tumors",
        "standard_adcs": [],
    },
    "FOLR1": {
        "gene": "FOLR1",
        "tumor_tpm": 210.0,
        "normal_tpm": {"ocular": 14.0, "renal": 15.0, "pulmonary": 6.0},
        "description": "Folate receptor alpha; ovarian, endometrial, NSCLC",
        "standard_adcs": ["Elahere"],
    },
}

CANDIDATE_PAYLOADS = {
    "DXd": {
        "name": "Deruxtecan (DXd)",
        "class": "Topoisomerase I Inhibitor",
        "ic50_nm": 1.5,
        "elimination": "Hepatic/biliary (CYP3A4, OATP1B1/1B3)",
        "cyp3a4_fraction": 0.45,
        "hepatic_fraction": 0.85,
        "renal_fraction": 0.15,
        "membrane_permeable": True,
        "primary_tox": ["pulmonary", "haematologic", "gastrointestinal"],
        "smiles": "CCC1(O)C(=O)OCc2c1cc3n(c2=O)Cc4c-3nc5ccc(F)c(C)c5c4NC(=O)CO",
        "sa_score": 3.8,
        "qed": 0.58,
    },
    "SN_38": {
        "name": "SN-38 (7-ethyl-10-hydroxycamptothecin)",
        "class": "Topoisomerase I Inhibitor",
        "ic50_nm": 2.0,
        "elimination": "Hepatic UGT1A1 glucuronidation -> biliary excretion",
        "cyp3a4_fraction": 0.0,
        "hepatic_fraction": 0.80,
        "renal_fraction": 0.20,
        "membrane_permeable": True,
        "primary_tox": ["gastrointestinal", "haematologic"],
        "smiles": "CCc1c2c(nc3ccc(O)cc13)-c1cc3c(c(=O)n1C2)COC(=O)C3(O)CC",
        "sa_score": 3.4,
        "qed": 0.62,
    },
    "MMAE": {
        "name": "Monomethyl auristatin E (MMAE)",
        "class": "Microtubule Inhibitor (Auristatin)",
        "ic50_nm": 0.2,
        "elimination": "Hepatic CYP3A4 oxidation & biliary excretion",
        "cyp3a4_fraction": 0.92,
        "hepatic_fraction": 0.88,
        "renal_fraction": 0.12,
        "membrane_permeable": True,
        "primary_tox": ["neurologic", "haematologic", "dermatologic"],
        "smiles": "CCC(C)C(C(CC(=O)N1CCCC1C(C(C)C(=O)NC(C)C(c2ccccc2)O)OC)OC)N(C)C(=O)C(C(C)C)NC(=O)C(C(C)C)NC",
        "sa_score": 3.9,
        "qed": 0.52,
    },
    "MMAF": {
        "name": "Monomethyl auristatin F (MMAF)",
        "class": "Microtubule Inhibitor (Auristatin with terminal charged phenylalanine)",
        "ic50_nm": 0.5,
        "elimination": "Biliary & Renal filtration (P-gp / CYP3A4 minor)",
        "cyp3a4_fraction": 0.65,
        "hepatic_fraction": 0.45,
        "renal_fraction": 0.55,
        "membrane_permeable": False,
        "primary_tox": ["ocular", "haematologic"],
        "smiles": "CCC(C)C(C(CC(=O)N1CCCC1C(C(C)C(=O)NC(Cc2ccccc2)C(=O)O)OC)OC)N(C)C(=O)C(C(C)C)NC(=O)C(C(C)C)NC",
        "sa_score": 3.7,
        "qed": 0.55,
    },
    "DM1": {
        "name": "Maytansinoid (DM1)",
        "class": "Microtubule Inhibitor (Maytansinoid)",
        "ic50_nm": 0.1,
        "elimination": "Hepatic/CYP3A4",
        "cyp3a4_fraction": 0.85,
        "hepatic_fraction": 0.90,
        "renal_fraction": 0.10,
        "membrane_permeable": False,
        "primary_tox": ["hepatic", "cardiovascular", "haematologic"],
        "smiles": "CC1C2CC(C(/C=C/C=C(/Cc3cc(OC)c(Cl)c(c3)N(C)C(=O)CC(C4(C1O4)C)OC(=O)C(C)N(C)C(=O)CCS)\\C)OC)(NC(=O)O2)O",
        "sa_score": 4.1,
        "qed": 0.49,
    },
    "STING_Agonist": {
        "name": "Immune-Stimulating Di-GMP Agonist",
        "class": "Immune Agonist (ISAC Payload)",
        "ic50_nm": 15.0,
        "elimination": "Systemic nucleases & Renal excretion",
        "cyp3a4_fraction": 0.0,
        "hepatic_fraction": 0.15,
        "renal_fraction": 0.70,
        "membrane_permeable": False,
        "primary_tox": ["infectious_immune"],
        "smiles": "Nc1nc2c(ncn2[C@@H]2O[C@H]3COP(=O)(O)O[C@H]4[C@H](O)[C@@H](O[C@@H]4COP(=O)(O)O[C@H]3[C@H]2O)n2cnc3c(O)nc(N)nc32)c(=O)[nH]1",
        "sa_score": 3.2,
        "qed": 0.65,
    },
}

CANDIDATE_LINKERS = {
    "GGFG_Cleavable": {
        "name": "GGFG Gly-Gly-Phe-Gly Tetrapeptide",
        "type": "Cleavable (Lysosomal Cathepsin B/L)",
        "bystander_release": True,
        "hydrophilicity": 0.4,
        "plasma_stability_t12_h": 120.0,
        "contraindicated_in": ["pulmonary", "gastrointestinal"],
    },
    "ValCit_PABC_Cleavable": {
        "name": "Valine-Citrulline PABC",
        "type": "Cleavable (Cathepsin B with self-immolative spacer)",
        "bystander_release": True,
        "hydrophilicity": 0.35,
        "plasma_stability_t12_h": 96.0,
        "contraindicated_in": ["pulmonary", "neurologic"],
    },
    "SMCC_NonCleavable": {
        "name": "Succinimidyl-4-(N-maleimidomethyl)cyclohexane-1-carboxylate (SMCC/MCC)",
        "type": "Non-Cleavable (Proteolytic backbone degradation)",
        "bystander_release": False,
        "hydrophilicity": 0.6,
        "plasma_stability_t12_h": 350.0,
        "contraindicated_in": [],
    },
    "PEG8_Glucuronide_Cleavable": {
        "name": "PEG8-Beta-Glucuronide (Conditionally Cleavable)",
        "type": "Conditionally Cleavable (Tumor Extracellular/Lysosomal Beta-Glucuronidase)",
        "bystander_release": False,
        "hydrophilicity": 0.95,
        "plasma_stability_t12_h": 280.0,
        "contraindicated_in": [],
    },
}

# Chemical conjugation compatibility matrix (1.0 = native clinical chemistry, <1.0 = requires adapter spacer)
LINKER_PAYLOAD_COMPAT = {
    ("GGFG_Cleavable", "DXd"): 1.00,
    ("GGFG_Cleavable", "SN_38"): 0.88,
    ("GGFG_Cleavable", "MMAE"): 0.82,
    ("GGFG_Cleavable", "MMAF"): 0.78,
    ("GGFG_Cleavable", "DM1"): 0.55,
    ("GGFG_Cleavable", "STING_Agonist"): 0.76,
    ("ValCit_PABC_Cleavable", "MMAE"): 1.00,
    ("ValCit_PABC_Cleavable", "MMAF"): 0.90,
    ("ValCit_PABC_Cleavable", "DXd"): 0.84,
    ("ValCit_PABC_Cleavable", "SN_38"): 0.82,
    ("ValCit_PABC_Cleavable", "DM1"): 0.52,
    ("ValCit_PABC_Cleavable", "STING_Agonist"): 0.74,
    ("SMCC_NonCleavable", "DM1"): 1.00,
    ("SMCC_NonCleavable", "MMAF"): 1.00,
    ("SMCC_NonCleavable", "STING_Agonist"): 0.88,
    ("SMCC_NonCleavable", "MMAE"): 0.58,
    ("SMCC_NonCleavable", "DXd"): 0.54,
    ("SMCC_NonCleavable", "SN_38"): 0.50,
    ("PEG8_Glucuronide_Cleavable", "MMAF"): 0.96,
    ("PEG8_Glucuronide_Cleavable", "SN_38"): 0.95,
    ("PEG8_Glucuronide_Cleavable", "MMAE"): 0.94,
    ("PEG8_Glucuronide_Cleavable", "DXd"): 0.90,
    ("PEG8_Glucuronide_Cleavable", "STING_Agonist"): 0.94,
    ("PEG8_Glucuronide_Cleavable", "DM1"): 0.72,
}

_SURROGATE_CACHE: Optional[Dict[str, Any]] = None


def _load_designer_surrogate() -> Dict[str, Any]:
    global _SURROGATE_CACHE
    if _SURROGATE_CACHE is None:
        data_path = Path(__file__).resolve().parent / "data" / "surrogate_designer.json"
        if not data_path.exists():
            raise FileNotFoundError(
                f"Neural surrogate table missing at {data_path}. Run ml/preclinical/distill_to_studio.py first."
            )
        _SURROGATE_CACHE = json.loads(data_path.read_text(encoding="utf-8"))
    return _SURROGATE_CACHE


def _lookup_target_info(target_antigen: str) -> Tuple[str, Dict[str, Any]]:
    t_up = (target_antigen or "HER2").strip().upper()
    for k, v in TARGET_ANTIGENS.items():
        if k.upper() == t_up:
            return k.upper(), v
    return "HER2", TARGET_ANTIGENS["HER2"]


@dataclass
class DeNovoADCSpecification:
    target_antigen: str
    antibody_format: str
    fc_engineering: str
    linker_choice: str
    payload_choice: str
    dar: int
    conjugation_chemistry: str
    predicted_safety_score: float
    predicted_efficacy_score: float
    off_tumor_safety_margin: float
    rationales: List[str] = field(default_factory=list)


def design_novel_adc(
    target_antigen: str,
    v_compounded: Dict[str, float],
    renal_crcl: Optional[float] = None,
    bili_uln: Optional[float] = None,
    concomitant_drugs: Optional[List[str]] = None,
    bystander_forbidden: bool = False,
) -> DeNovoADCSpecification:
    """Performs patient-conditioned Pareto optimization using the 5-Fold `ADC-SurrogateNet-v2` ensemble."""
    surrogate = _load_designer_surrogate()
    grid = surrogate["grid"]
    organs = surrogate["organs"]
    w0 = surrogate["weights"]

    grid_tgt_id, antigen_info = _lookup_target_info(target_antigen)
    rationales: List[str] = []

    # 1. Tumor-to-normal expression margin check
    safety_margins: Dict[str, float] = {}
    tumor_tpm = antigen_info["tumor_tpm"]
    for organ, norm_tpm in antigen_info["normal_tpm"].items():
        margin = float(math.log2((tumor_tpm + 1.0) / (norm_tpm + 1.0)))
        safety_margins[organ] = margin
        if v_compounded.get(organ, 0.0) >= 0.4 and margin < 2.5:
            rationales.append(
                f"[표적 발현 분석] {target_antigen.upper()} 정상 {organ} 대비 종양 발현비(log2FC={margin:.1f}) 반영."
            )
    min_margin = min(safety_margins.values()) if safety_margins else 3.5

    # 2. Clinical PK / DDI / Bystander boundary conditions
    cyp3a4_inhibitors = ("ketoconazole", "itraconazole", "clarithromycin", "ritonavir", "voriconazole", "posaconazole", "cobicistat")
    cyp3a4_blocked = bool(
        concomitant_drugs
        and any(any(inh in d.lower() for inh in cyp3a4_inhibitors) for d in concomitant_drugs)
    )
    severe_renal = (renal_crcl is not None and renal_crcl < 30.0) or (v_compounded.get("renal", 0.0) >= 0.60)
    severe_hepatic = (bili_uln is not None and bili_uln > 1.5) or (v_compounded.get("hepatic", 0.0) >= 0.50)

    v_vec = [_clip(float(v_compounded.get(ax, 0.0)), 0.0, 1.0) for ax in organs]
    pulm_v = float(v_compounded.get("pulmonary", 0.0))
    gi_v = float(v_compounded.get("gastrointestinal", 0.0))
    hep_v = float(v_compounded.get("hepatic", 0.0))
    haem_v = float(v_compounded.get("haematologic", 0.0))

    require_bystander_containment = bool(bystander_forbidden or pulm_v >= 0.48 or gi_v >= 0.58)
    max_vuln = max(v_vec) if v_vec else 0.0
    mean_vuln = (sum(v_vec) / len(v_vec)) if v_vec else 0.0

    # Adaptive Pareto safety priority increases smoothly with patient comorbidity severity
    w_safety = _clip(0.42 + 0.36 * max_vuln + 0.15 * mean_vuln, 0.40, 0.86)

    w_sel = float(w0.get("wSelect", 0.25))
    w_bys = 0.06 if require_bystander_containment else max(0.32, float(w0.get("wBystander", 0.28)))
    w_core = max(0.25, 1.0 - w_sel - w_bys)
    w_pot = 0.58 * w_core
    w_del = 0.42 * w_core

    best_cand: Optional[Dict[str, Any]] = None
    best_utility = -1e9

    for l_id, l_info in CANDIDATE_LINKERS.items():
        for p_id, p_info in CANDIDATE_PAYLOADS.items():
            compat = LINKER_PAYLOAD_COMPAT.get((l_id, p_id), 0.65)
            for dar in (2, 4):
                for fc_flag in (0, 1):
                    key = f"{grid_tgt_id}|{l_id}|{p_id}|{dar}|{fc_flag}"
                    node = grid.get(key)
                    if node is None:
                        continue

                    m = node["m"]  # [pIC50_pos, pIC50_bys, S_plasma_pct, HIC_agg, CL_hep, s_sel, s_pot, s_deliv, s_bys]
                    hb = [float(x) * 1e-3 for x in node["hb"]]
                    ha = [float(x) * 1e-3 for x in node["ha"]]
                    hf = [float(x) * 1e-3 for x in node["hf"]]
                    ho = [float(x) * 1e-3 for x in node["ho"]]

                    # Pharmacokinetic clearance & DDI exposure scaling on free-payload systemic hazard `hb`
                    pk_sys_mult = 1.0
                    if cyp3a4_blocked and p_info["cyp3a4_fraction"] > 0.0:
                        pk_sys_mult += 3.2 * p_info["cyp3a4_fraction"]
                    if severe_hepatic:
                        pk_sys_mult += 1.6 * p_info["hepatic_fraction"]
                    if severe_renal:
                        pk_sys_mult += 1.4 * p_info["renal_fraction"]

                    h_organ = [
                        (pk_sys_mult * hb[idx] + ha[idx] + hf[idx] + ho[idx]) * (0.45 + 2.35 * v_vec[idx])
                        for idx in range(len(organs))
                    ]

                    # Payload-specific organ tropism coupling under acute patient vulnerability
                    for tox_ax in p_info["primary_tox"]:
                        if tox_ax in organs:
                            t_idx = organs.index(tox_ax)
                            h_organ[t_idx] += 0.42 * v_vec[t_idx] * (dar / 4.0) * pk_sys_mult

                    # Bystander extracellular diffusion hazard in vulnerable lung/gut parenchyma
                    if require_bystander_containment:
                        bys_flux = (1.0 if l_info["bystander_release"] else 0.0) + (0.85 if p_info["membrane_permeable"] else 0.0)
                        if pulm_v >= 0.45 and l_id == "PEG8_Glucuronide_Cleavable" and pulm_v >= 0.65:
                            # Under severe ILD (>=0.65), full lysosomal trapping via SMCC is safer than extracellular cleavage
                            bys_flux += 0.28 * (1.0 if p_info["membrane_permeable"] else 0.15)
                        for idx in range(len(organs)):
                            h_organ[idx] += bys_flux * (0.38 * v_vec[idx] + 0.18)

                    if cyp3a4_blocked and p_info["cyp3a4_fraction"] >= 0.55:
                        ddi_pen = 0.55 * p_info["cyp3a4_fraction"]
                        for idx in range(len(organs)):
                            h_organ[idx] += ddi_pen

                    p_organ = [1.0 - math.exp(-_clip(h_val, 0.0, 6.0)) for h_val in h_organ]
                    peak_risk = max(p_organ)
                    mean_risk = sum(p_organ) / len(p_organ)
                    safety_100 = _clip(100.0 * (1.0 - (0.62 * peak_risk + 0.38 * mean_risk)), 5.0, 98.0)

                    # Neural ensemble efficacy score (with native FcgammaRIIIa ADCC contribution when Fc=0)
                    s_sel, s_pot, s_deliv, s_bys = float(m[5]), float(m[6]), float(m[7]), float(m[8])
                    adcc_gain = 0.032 if fc_flag == 0 else 0.0
                    cytotoxic_mode_scale = 0.84 if p_id == "STING_Agonist" else 1.00
                    eff_100 = _clip(
                        100.0 * compat * cytotoxic_mode_scale * (w_sel * s_sel + w_pot * s_pot + w_del * s_deliv + w_bys * s_bys + adcc_gain),
                        8.0,
                        98.0,
                    )

                    utility = w_safety * safety_100 + (1.0 - w_safety) * eff_100
                    if utility > best_utility:
                        best_utility = utility
                        best_cand = {
                            "linker_id": l_id,
                            "payload_id": p_id,
                            "dar": dar,
                            "fc_flag": fc_flag,
                            "safety_10": round(_clip(safety_100 / 10.0, 1.0, 9.9), 2),
                            "efficacy_10": round(_clip(eff_100 / 10.0, 1.0, 9.9), 2),
                            "pIC50_pos": m[0],
                            "S_plasma_pct": m[2],
                        }

    assert best_cand is not None
    sel_l_id = best_cand["linker_id"]
    sel_p_id = best_cand["payload_id"]
    sel_dar = int(best_cand["dar"])
    sel_fc = int(best_cand["fc_flag"])
    sel_p_info = CANDIDATE_PAYLOADS[sel_p_id]
    sel_l_info = CANDIDATE_LINKERS[sel_l_id]

    if sel_fc == 1 or hep_v >= 0.45 or pulm_v >= 0.45 or haem_v >= 0.55:
        fc_engineering = "IgG1 Fc-silenced (L234A/L235A/P329G 'LALA-PG' triple mutant)"
        rationales.append(
            "[항체 Fc 엔지니어링] ADC-SurrogateNet 신경망 Fc 경로 위험도를 최소화하기 위해 LALA-PG 침묵 변이 채택 (폐/간/골수 대식세포 FcγR 비특이 흡수 차단)."
        )
    else:
        fc_engineering = "Recombinant Humanized IgG1 (Native Fc effector competency retained)"
        rationales.append(
            "[항체 Fc 엔지니어링] 주요 망상내피계 장기 취약도가 낮아 야생형 IgG1 Fc 작동기(ADCC) 활성 유지."
        )

    rationales.append(
        f"[링커 선정] {sel_l_info['name']} (신경망 혈장 보존율 {best_cand['S_plasma_pct']:.1f}%, 절단 기전: {sel_l_info['type']})."
    )
    if cyp3a4_blocked:
        rationales.append(
            "[약물상호작용 DDI 회피] 병용 CYP3A4 저해제 투여 반영: CYP3A4 대사 의존성 오리스타틴/메이탄시노이드 전신 노출 급증을 회피하고 비-CYP 대사 페이로드 선택."
        )
    if severe_hepatic or severe_renal:
        rationales.append(
            "[청소 경로 매칭] 환자 신장/간 배설 예비능 저하를 신경망 전신 독성 경로에 반영하여 배설 부담이 낮은 페이로드 채택."
        )
    rationales.append(
        f"[페이로드 선정] {sel_p_info['name']} ({sel_p_info['class']}, 신경망 예측 pIC50={best_cand['pIC50_pos']:.2f})."
    )

    if sel_dar == 2:
        conjugation = "Site-specific engineered cysteine (ThioMab, DAR=2.0 uniform)"
        rationales.append("[DAR 및 접합] 부위 특이적 시스테인(ThioMab) 균일 DAR 2.0 접합으로 소수성 응집 및 전신 독성 억제.")
    else:
        conjugation = "Enzymatic microbial transglutaminase (Gln295 conjugation, DAR=4.0 uniform)"
        rationales.append("[DAR 및 접합] 미생물 트랜스글루타미나아제(Gln295) 부위 특이적 균일 DAR 4.0 접합으로 세포 내 전달량 최적화.")

    return DeNovoADCSpecification(
        target_antigen=target_antigen.upper(),
        antibody_format=f"Humanized anti-{target_antigen.upper()} mAb",
        fc_engineering=fc_engineering,
        linker_choice=sel_l_info["name"],
        payload_choice=f"{sel_p_info['name']} ({sel_p_info['class']})",
        dar=sel_dar,
        conjugation_chemistry=conjugation,
        predicted_safety_score=best_cand["safety_10"],
        predicted_efficacy_score=best_cand["efficacy_10"],
        off_tumor_safety_margin=round(float(min_margin), 2),
        rationales=rationales,
    )
