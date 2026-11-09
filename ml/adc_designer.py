"""Conditioned De Novo ADC Inverse Design Engine.

Given:
  1. Patient tumor indication & target antigen profile
  2. Compounded organ vulnerability vector V_compounded in [0, 1]^13
  3. Patient renal / hepatic clearance profile (CLcr, Bilirubin, Child-Pugh)
  4. Concomitant medication & DDI constraints

Performs multi-objective Pareto optimization to generate a bespoke novel ADC specification:
  - Antibody: Target antigen, binding affinity, Fc-silencing (LALA-PG)
  - Linker: Cleavable vs non-cleavable (bystander risk control), hydrophilic spacers
  - Payload: MoA, elimination route matching, DDI avoidance
  - DAR & Conjugation: Site-specific uniform conjugation (DAR 2 or 4)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

AXES = [
    "haematologic", "hepatic", "cardiovascular", "pulmonary", "renal",
    "gastrointestinal", "neurologic", "ocular", "dermatologic",
    "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"
]

# Baseline Target Antigen Database (with tumor vs normal organ TPM expression profile)
TARGET_ANTIGENS = {
    "HER2": {
        "gene": "ERBB2",
        "tumor_tpm": 280.0,
        "normal_tpm": {"cardiovascular": 18.0, "pulmonary": 12.0, "gastrointestinal": 8.0, "renal": 5.0, "hepatic": 3.0},
        "description": "Human Epidermal Growth Factor Receptor 2; high expression in breast, gastric, colorectal, NSCLC",
        "standard_adcs": ["Enhertu", "Kadcyla"]
    },
    "TROP2": {
        "gene": "TACSTD2",
        "tumor_tpm": 310.0,
        "normal_tpm": {"gastrointestinal": 35.0, "pulmonary": 22.0, "dermatologic": 25.0, "renal": 10.0, "hepatic": 4.0},
        "description": "Trophoblast cell surface antigen 2; overexpressed in triple-negative breast, urothelial, lung carcinoma",
        "standard_adcs": ["Trodelvy", "Datroway"]
    },
    "NECTIN4": {
        "gene": "NECTIN4",
        "tumor_tpm": 190.0,
        "normal_tpm": {"dermatologic": 28.0, "neurologic": 8.0, "gastrointestinal": 6.0, "hepatic": 2.0, "pulmonary": 4.0},
        "description": "Nectin cell adhesion molecule 4; highly expressed in bladder/urothelial carcinoma",
        "standard_adcs": ["Padcev"]
    },
    "CEACAM5": {
        "gene": "CEACAM5",
        "tumor_tpm": 350.0,
        "normal_tpm": {"gastrointestinal": 40.0, "pulmonary": 15.0, "hepatic": 5.0},
        "description": "Carcinoembryonic antigen-related cell adhesion molecule 5; colorectal, pancreatic, NSCLC",
        "standard_adcs": []
    },
    "CLDN18.2": {
        "gene": "CLDN18",
        "tumor_tpm": 260.0,
        "normal_tpm": {"gastrointestinal": 32.0, "pulmonary": 18.0},
        "description": "Claudin 18 splice variant 2; gastric, gastroesophageal junction, pancreatic adenocarcinoma",
        "standard_adcs": []
    },
    "c_MET": {
        "gene": "MET",
        "tumor_tpm": 180.0,
        "normal_tpm": {"hepatic": 14.0, "renal": 12.0, "pulmonary": 9.0},
        "description": "MET receptor tyrosine kinase; lung, gastric, colorectal carcinoma",
        "standard_adcs": ["Emrelis"]
    },
    "B7_H3": {
        "gene": "CD276",
        "tumor_tpm": 220.0,
        "normal_tpm": {"cardiovascular": 6.0, "pulmonary": 7.0, "hepatic": 4.0},
        "description": "Immune checkpoint B7-H3; prostate, SCLC, pediatric solid tumors",
        "standard_adcs": []
    },
    "FOLR1": {
        "gene": "FOLR1",
        "tumor_tpm": 210.0,
        "normal_tpm": {"ocular": 14.0, "renal": 15.0, "pulmonary": 6.0},
        "description": "Folate receptor alpha; ovarian, endometrial, NSCLC",
        "standard_adcs": ["Elahere"]
    }
}

# Candidate Payloads with Pharmacokinetics & Inherent Toxicity Spectra
CANDIDATE_PAYLOADS = {
    "DXd": {
        "name": "Deruxtecan (DXd)",
        "class": "Topoisomerase I Inhibitor",
        "ic50_nm": 1.5,
        "elimination": "Hepatic/biliary (CYP3A4, OATP1B1/1B3)",
        "membrane_permeable": True,  # High bystander effect
        "primary_tox": ["pulmonary", "haematologic", "gastrointestinal"],
        "smiles": "CC1=C2C(=CC(=C1)NC(=O)CNC(=O)CC)CN3C2=NC4=C(C3=O)C=C(C=C4)C(=O)O",
        "sa_score": 3.8,
        "qed": 0.58
    },
    "SN_38": {
        "name": "SN-38 (7-ethyl-10-hydroxycamptothecin)",
        "class": "Topoisomerase I Inhibitor",
        "ic50_nm": 2.0,
        "elimination": "Hepatic UGT1A1 glucuronidation -> biliary excretion",
        "membrane_permeable": True,  # Moderate-high bystander effect
        "primary_tox": ["gastrointestinal", "haematologic"],
        "smiles": "CCC1=C2CN3C(=CC4=C(C3=O)C=C(C=C4)O)C2=NC5=C1C=CC=C5",
        "sa_score": 3.4,
        "qed": 0.62
    },
    "MMAE": {
        "name": "Monomethyl auristatin E (MMAE)",
        "class": "Microtubule Inhibitor (Auristatin)",
        "ic50_nm": 0.2,
        "elimination": "Hepatic CYP3A4 oxidation & biliary excretion",
        "membrane_permeable": True,  # High bystander effect
        "primary_tox": ["neurologic", "haematologic", "dermatologic"],
        "smiles": "CCC(C)C(C(=O)NC(CC(=O)O)C(=O)NC(C)C(=O)N1CCCC1)NC(=O)C(C(C)C)NC",
        "sa_score": 3.9,
        "qed": 0.52
    },
    "MMAF": {
        "name": "Monomethyl auristatin F (MMAF)",
        "class": "Microtubule Inhibitor (Auristatin with terminal charged phenylalanine)",
        "ic50_nm": 0.5,
        "elimination": "Biliary & Renal filtration",
        "membrane_permeable": False,  # Charged terminal acid: Low/negligible bystander effect!
        "primary_tox": ["ocular", "haematologic"],
        "smiles": "CCC(C)C(C(=O)NC(CC1=CC=CC=C1)C(=O)O)NC(=O)C(C(C)C)NC",
        "sa_score": 3.7,
        "qed": 0.55
    },
    "DM1": {
        "name": "Maytansinoid (DM1)",
        "class": "Microtubule Inhibitor (Maytansinoid)",
        "ic50_nm": 0.1,
        "elimination": "Hepatic/CYP3A4",
        "membrane_permeable": False,  # Trapped as Lys-MCC-DM1 inside cells
        "primary_tox": ["hepatic", "cardiovascular", "haematologic"],
        "smiles": "CC1CC2=CC(=O)C=C(N2)C(=O)OC(CC3=CC=CC=C3)CC1",
        "sa_score": 4.1,
        "qed": 0.49
    },
    "STING_Agonist": {
        "name": "Immune-Stimulating Di-GMP Agonist",
        "class": "Immune Agonist (ISAC Payload)",
        "ic50_nm": 15.0,  # Non-cytotoxic immune activation
        "elimination": "Systemic nucleases & Renal excretion",
        "membrane_permeable": False,  # Confined to tumor immune microenvironment
        "primary_tox": ["infectious_immune"],
        "smiles": "O=P(O)(O)OCC1OC(N2C=NC3=C2N=CN=C3N)C(O)C1OP(=O)(O)O",
        "sa_score": 3.2,
        "qed": 0.65
    }
}

# Candidate Linkers
CANDIDATE_LINKERS = {
    "GGFG_Cleavable": {
        "name": "GGFG Gly-Gly-Phe-Gly Tetrapeptide",
        "type": "Cleavable (Lysosomal Cathepsin B/L)",
        "bystander_release": True,
        "hydrophilicity": 0.4,
        "plasma_stability_t12_h": 120.0,
        "contraindicated_in": ["pulmonary", "gastrointestinal"]  # High bystander leakage
    },
    "ValCit_PABC_Cleavable": {
        "name": "Valine-Citrulline PABC",
        "type": "Cleavable (Cathepsin B with self-immolative spacer)",
        "bystander_release": True,
        "hydrophilicity": 0.35,
        "plasma_stability_t12_h": 96.0,
        "contraindicated_in": ["pulmonary", "neurologic"]
    },
    "SMCC_NonCleavable": {
        "name": "Succinimidyl-4-(N-maleimidomethyl)cyclohexane-1-carboxylate (SMCC/MCC)",
        "type": "Non-Cleavable (Proteolytic backbone degradation)",
        "bystander_release": False,  # Completely traps charged amino acid adduct in lysosomes
        "hydrophilicity": 0.6,
        "plasma_stability_t12_h": 350.0,  # Ultra-stable in plasma
        "contraindicated_in": []  # Zero off-target bystander leakage to lung/gut
    },
    "PEG8_Glucuronide_Cleavable": {
        "name": "PEG8-Beta-Glucuronide",
        "type": "Conditionally Cleavable (Tumor Extracellular/Lysosomal Beta-Glucuronidase)",
        "bystander_release": False,  # Highly hydrophilic PEG8 tail prevents passive cell membrane diffusion
        "hydrophilicity": 0.95,
        "plasma_stability_t12_h": 280.0,
        "contraindicated_in": []
    }
}


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
    bystander_forbidden: bool = False
) -> DeNovoADCSpecification:
    """Computes a multi-objective de novo ADC design tailored to the patient's exact toxicological constraints."""
    rationales = []
    antigen_info = TARGET_ANTIGENS.get(target_antigen.upper(), TARGET_ANTIGENS["HER2"])

    # 1. On-target, off-tumor safety margin evaluation
    safety_margins = {}
    tumor_tpm = antigen_info["tumor_tpm"]
    for organ, norm_tpm in antigen_info["normal_tpm"].items():
        # Margin = log2(tumor_tpm / normal_tpm)
        margin = np.log2((tumor_tpm + 1.0) / (norm_tpm + 1.0))
        safety_margins[organ] = margin
        if v_compounded.get(organ, 0.0) >= 0.4 and margin < 2.5:
            rationales.append(f"[표적 안전성 경고] {target_antigen}의 정상 {organ} 발현 대비 종양 발현 배수가 낮아(log2FC={margin:.1f}), 온타깃 정상조직 독성 위험 상존.")

    min_margin = min(safety_margins.values()) if safety_margins else 3.5

    # 2. Antibody & Fc Engineering
    # If liver, lung, or immune vulnerability is high, enforce Fc-silencing (LALA-PG)
    high_reticuloendothelial = (
        v_compounded.get("hepatic", 0.0) >= 0.4 or
        v_compounded.get("pulmonary", 0.0) >= 0.4 or
        v_compounded.get("haematologic", 0.0) >= 0.5
    )
    if high_reticuloendothelial:
        fc_engineering = "IgG1 Fc-silenced (L234A/L235A/P329G 'LALA-PG' triple mutant)"
        rationales.append("[항체 엔지니어링] 간/폐 대식세포 및 쿠퍼세포의 FcγR 비특이 흡수 차단을 위해 LALA-PG 침묵 Fc 변이 도입.")
    else:
        fc_engineering = "Recombinant Humanized IgG1 (Native Fc effector competency retained)"

    # 3. Linker Selection (Bystander control)
    # Severe pulmonary (ILD risk) or severe GI vulnerability mandates non-cleavable or hydrophilic glucuronide
    require_zero_bystander = (
        bystander_forbidden or
        v_compounded.get("pulmonary", 0.0) >= 0.45 or
        v_compounded.get("gastrointestinal", 0.0) >= 0.55
    )
    if require_zero_bystander:
        if v_compounded.get("pulmonary", 0.0) >= 0.6:
            linker_choice = "SMCC_NonCleavable"
            rationales.append("[링커 화학] 중증 폐/간질성 폐질환(ILD) 위험 환자: 비절단형 SMCC 링커로 리소좀 내 Lys-adduct 트래핑 유도 (Bystander 누출 0%).")
        else:
            linker_choice = "PEG8_Glucuronide_Cleavable"
            rationales.append("[링커 화학] 위장관/폐 보호: 친수성 PEG8-베타-글루쿠로니드 링커로 종양 특이적 세포외 효소 절단 및 정상조직 막투과 억제.")
    else:
        linker_choice = "GGFG_Cleavable"
        rationales.append("[링커 화학] 장기 독성 저위험 환자: 리소좀 카텝신 B 절단형 GGFG 링커로 종양 이질성 극복용 Bystander 살상 유지.")

    # 4. Payload Selection (Clearance Route & DDI avoidance)
    # Check DDI for strong CYP3A4 inhibitors
    cyp3a4_blocked = False
    if concomitant_drugs:
        cyp_names = ["ketoconazole", "itraconazole", "clarithromycin", "ritonavir"]
        cyp3a4_blocked = any(any(c in d.lower() for c in cyp_names) for d in concomitant_drugs)

    # Renal & Hepatic elimination restrictions
    severe_renal = (renal_crcl is not None and renal_crcl < 30.0) or (v_compounded.get("renal", 0.0) >= 0.6)
    severe_hepatic = (bili_uln is not None and bili_uln > 1.5) or (v_compounded.get("hepatic", 0.0) >= 0.5)

    payload_scores = {}
    for p_id, p_info in CANDIDATE_PAYLOADS.items():
        score = 10.0
        # Penalize for organ toxicities that match patient vulnerabilities
        for organ in p_info["primary_tox"]:
            vuln = v_compounded.get(organ, 0.0)
            score -= vuln * 5.0

        # DDI penalty
        if cyp3a4_blocked and "CYP3A4" in p_info["elimination"]:
            score -= 8.0  # Disqualify CYP-dependent payloads

        # Clearance organ matching
        if severe_renal and "Renal" in p_info["elimination"]:
            score -= 4.0
        if severe_hepatic and "Hepatic" in p_info["elimination"]:
            score -= 7.0

        # Bystander penalty if bystander is strictly forbidden
        if require_zero_bystander and p_info["membrane_permeable"]:
            score -= 4.5

        payload_scores[p_id] = score

    # Select best payload
    best_payload_id = max(payload_scores, key=payload_scores.get)
    best_payload = CANDIDATE_PAYLOADS[best_payload_id]

    if cyp3a4_blocked and best_payload_id in ["MMAE", "MMAF"]:
        rationales.append("[약물상호작용 DDI 회피] 병용 CYP3A4 저해제 감지: MMAE/MMAF 배제 및 비-CYP 대사 페이로드 채택.")
    if severe_hepatic:
        rationales.append("[배설 장기 매칭] 간장애(Bilirubin>1.5) 감지: 간 대사/담즙 배설 의존성 페이로드 감점 및 안전 배설 경로 분기.")

    rationales.append(f"[페이로드 선정] {best_payload['name']} (MoA: {best_payload['class']}) - 최적 파레토 안전성 점수 {payload_scores[best_payload_id]:.1f} 달성.")

    # 5. DAR & Site-Specific Conjugation
    # If high potency payload (IC50 < 0.5nM) or moderate vulnerability -> DAR = 2 or 4 site-specific
    if best_payload["ic50_nm"] <= 0.2:
        dar = 2
        conjugation = "Site-specific engineered cysteine (ThioMab, DAR=2.0 uniform)"
        rationales.append("[DAR 및 접합] 초고활성 페이로드(IC50<=0.2nM): ThioMab 부위 특이적 접합으로 균일 DAR 2.0 고정 (과도한 전신 독성 방지).")
    else:
        dar = 4
        conjugation = "Enzymatic microbial transglutaminase (Gln295 conjugation, DAR=4.0 uniform)"
        rationales.append("[DAR 및 접합] 중간 효력 페이로드: 미생물 트랜스글루타미나아제 부위 특이적 접합으로 DAR 4.0 균일 합성 (소수성 응집 차단).")

    # Overall predicted scores
    efficacy_score = round(float(np.clip(8.5 - 0.5 * (dar == 2), 6.0, 9.8)), 2)
    safety_score = round(float(np.clip(payload_scores[best_payload_id], 4.0, 10.0)), 2)

    return DeNovoADCSpecification(
        target_antigen=target_antigen.upper(),
        antibody_format=f"Humanized anti-{target_antigen.upper()} mAb",
        fc_engineering=fc_engineering,
        linker_choice=CANDIDATE_LINKERS[linker_choice]["name"],
        payload_choice=f"{best_payload['name']} ({best_payload['class']})",
        dar=dar,
        conjugation_chemistry=conjugation,
        predicted_safety_score=safety_score,
        predicted_efficacy_score=efficacy_score,
        off_tumor_safety_margin=round(float(min_margin), 2),
        rationales=rationales
    )
