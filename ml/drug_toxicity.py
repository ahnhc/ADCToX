"""Drug-Induced Toxicity and Drug-Drug Interaction (DDI) Compounded Vulnerability Engine.

Evaluates:
  1. Prior chemotherapy cumulative organ toxicities (e.g. anthracyclines, bleomycin, platinums, taxanes, checkpoint inhibitors).
  2. Concomitant medications and CYP/P-gp/UGT metabolic drug-drug interactions (DailyMed Section 7 & FAERS signals).
  3. Computes the compounded patient organ vulnerability vector V_compounded in [0, 1]^13.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

AXES = [
    "haematologic", "hepatic", "cardiovascular", "pulmonary", "renal",
    "gastrointestinal", "neurologic", "ocular", "dermatologic",
    "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"
]

# 1. Prior Chemotherapy Cumulative Toxicity Definitions
PRIOR_CHEMO_BURDEN = {
    "prior_anthracycline": {
        "label": "Prior Anthracyclines (Doxorubicin, Epirubicin)",
        "organs": {"cardiovascular": 0.45},
        "description": "Subclinical myocardial injury & free-radical damage; lowers threshold for HER2-directed LVEF dysfunction",
        "dynamic_rules": {"min_lvef": 55.0}  # standard threshold is 50%; prior anthracycline raises safety floor to 55%
    },
    "prior_bleomycin": {
        "label": "Prior Bleomycin",
        "organs": {"pulmonary": 0.55},
        "description": "Alveolar epithelial injury & occult interstitial fibrogenesis; extreme susceptibility to DXd/ILD",
        "dynamic_rules": {"forbid_bystander_cleavable": True}
    },
    "prior_checkpoint_inhibitor": {
        "label": "Prior Immune Checkpoint Inhibitors (PD-1 / PD-L1 / CTLA-4)",
        "organs": {"pulmonary": 0.35, "hepatic": 0.30, "metabolic_endocrine": 0.25},
        "description": "Subclinical autoimmune pneumonitis / hepatitis; hyper-reactivity upon ADC cytotoxic release"
    },
    "prior_platinum": {
        "label": "Prior Platinum (Cisplatin, Carboplatin, Oxaliplatin)",
        "organs": {"renal": 0.40, "neurologic": 0.35, "otologic": 0.30},
        "description": "Cumulative proximal tubule necrosis and sensory axonal loss; increases nephrotoxic & neuropathic vulnerability"
    },
    "prior_taxane_vinca": {
        "label": "Prior Taxanes (Paclitaxel, Docetaxel) / Vinca Alkaloids",
        "organs": {"neurologic": 0.45},
        "description": "Microtubule stabilization/depolymerization sensory neuropathy; synergistic toxicity with MMAE/DM1"
    }
}

# 2. Concomitant Medications & DDI Rules (DailyMed Section 7.1, 12.3)
CONCOMITANT_DDI_RULES = {
    "strong_cyp3a4_inhibitor": {
        "label": "Strong CYP3A4 Inhibitor (Ketoconazole, Itraconazole, Clarithromycin, Ritonavir)",
        "aliases": ["ketoconazole", "itraconazole", "clarithromycin", "ritonavir", "cyp3a4_inhibitor"],
        "effect": "Blocks hepatic oxidation of MMAE/MMAF; increases free payload AUC by 2.2x",
        "impacted_payloads": ["MMAE", "MMAF"],
        "action": "Avoid or require 50% dose reduction; shift to non-CYP cleared payloads",
        "organ_multiplier": {"hepatic": 1.4, "haematologic": 1.5, "neurologic": 1.6}
    },
    "strong_cyp3a4_inducer": {
        "label": "Strong CYP3A4 Inducer (Rifampin, Carbamazepine, St. John's Wort, Phenytoin)",
        "aliases": ["rifampin", "carbamazepine", "phenytoin", "st_johns_wort"],
        "effect": "Accelerates clearance of MMAE, reducing antitumor efficacy by >50%",
        "impacted_payloads": ["MMAE"],
        "action": "Avoid co-administration"
    },
    "dual_pgp_cyp3a4_inhibitor": {
        "label": "Dual P-gp and Strong CYP3A4 Inhibitor",
        "aliases": ["dual_pgp_cyp3a4", "verapamil_ketoconazole"],
        "effect": "Maximizes both systemic bioavailability and intracellular accumulation of tubulin inhibitors",
        "impacted_payloads": ["MMAE", "DM1"],
        "action": "Severe toxicity warning (Padcev Section 7.1)",
        "organ_multiplier": {"hepatic": 1.6, "haematologic": 1.8, "neurologic": 1.8}
    },
    "ugt1a1_inhibitor": {
        "label": "UGT1A1 Inhibitor (Propofol, Ketoconazole, Atazanavir)",
        "aliases": ["propofol", "atazanavir", "ugt1a1_inhibitor"],
        "effect": "Blocks SN-38 glucuronidation (Trodelvy Section 7.1); severe neutropenia & diarrhea risk doubled",
        "impacted_payloads": ["SN-38"],
        "action": "Avoid or strictly monitor; reduce starting dose",
        "organ_multiplier": {"haematologic": 1.7, "gastrointestinal": 1.6}
    },
    "qt_prolonging_agents": {
        "label": "QT-Prolonging Medication (Amiodarone, Sotalol, Haloperidol, Moxifloxacin)",
        "aliases": ["amiodarone", "sotalol", "haloperidol", "moxifloxacin", "qt_drug"],
        "effect": "Synergistic cardiotoxicity / fatal ventricular arrhythmia (Mylotarg/Besponsa Section 5.4)",
        "impacted_payloads": ["Calicheamicin"],
        "action": "ECG monitoring mandatory; avoid calicheamicin ADCs",
        "organ_multiplier": {"cardiovascular": 1.5}
    }
}


@dataclass
class DrugToxicityProfile:
    prior_chemo: List[str] = field(default_factory=list)
    concomitant_drugs: List[str] = field(default_factory=list)
    custom_ddi_notes: List[str] = field(default_factory=list)


def compute_compounded_vulnerability(
    baseline_organs: Dict[str, float],
    prior_chemo: Optional[List[str]] = None,
    concomitant_drugs: Optional[List[str]] = None
) -> Tuple[Dict[str, float], List[str], Dict[str, any]]:
    """Combines patient comorbidity vulnerability with drug-induced toxicities and DDI multipliers.

    Returns:
        compounded_vector: {axis: vulnerability in [0.0, 1.0]}
        clinical_alerts: list of human-readable warnings
        dynamic_constraints: dict of adjusted safety thresholds (min_lvef, forbidden payloads, etc.)
    """
    compounded = {a: float(baseline_organs.get(a, 0.0)) for a in AXES}
    alerts = []
    dynamic_constraints = {
        "min_lvef": 50.0,
        "forbid_payloads": set(),
        "forbid_bystander_cleavable": False,
        "payload_multipliers": {}
    }

    # 1. Process Prior Chemotherapy Cumulative Toxicities
    prior_chemo = prior_chemo or []
    for item in prior_chemo:
        key = item.strip().lower()
        matched = None
        for k, v in PRIOR_CHEMO_BURDEN.items():
            if key == k or key in k:
                matched = v
                break
        if matched:
            alerts.append(f"[기투여 누적독성] {matched['label']}: {matched['description']}")
            for organ, delta in matched["organs"].items():
                compounded[organ] = min(1.0, compounded[organ] + delta)
            if "dynamic_rules" in matched:
                for rk, rv in matched["dynamic_rules"].items():
                    if rk == "min_lvef":
                        dynamic_constraints["min_lvef"] = max(dynamic_constraints["min_lvef"], rv)
                    elif rk == "forbid_bystander_cleavable" and rv:
                        dynamic_constraints["forbid_bystander_cleavable"] = True

    # 2. Process Concomitant Drug Interactions (DDI)
    concomitant_drugs = concomitant_drugs or []
    for drug in concomitant_drugs:
        d_lower = drug.strip().lower()
        for ddi_key, ddi_info in CONCOMITANT_DDI_RULES.items():
            if any(alias in d_lower for alias in ddi_info["aliases"]):
                alerts.append(f"[병용약물 DDI 경고] {ddi_info['label']}: {ddi_info['effect']} -> 조치: {ddi_info['action']}")
                for payload in ddi_info["impacted_payloads"]:
                    dynamic_constraints["forbid_payloads"].add(payload)
                for organ, mult in ddi_info["organ_multiplier"].items():
                    # Multiplicative amplification of organ vulnerability
                    compounded[organ] = min(1.0, max(compounded[organ] * mult, 0.35 * (mult - 1.0) + compounded[organ]))

    # Clamp all axes to [0.0, 1.0]
    for a in AXES:
        compounded[a] = round(float(np.clip(compounded[a], 0.0, 1.0)), 3)

    return compounded, alerts, dynamic_constraints
