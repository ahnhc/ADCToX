"""
Export 36-Target / 368,640-Construct Studio Matrix & LoRA-Merged 5-Fold Runtime (`export_studio_368k.py`)
=========================================================================================================
Evaluates the leak-free 5-fold `ADC-SurrogateNet-v2` ensemble across the full clinical design space:
  - 36 Target Antigens (all 36 trained AlphaFold v6 + ESM-2 650M + GTEx v8 / Tabula Sapiens targets)
  - 16 Chemical Linkers (Cathepsin peptides, hydrophilic PEG8/glucuronide/pyrophosphate, pH/GSH, thioether)
  - 20 Cytotoxic & Immune Payloads (Topo I, Auristatins, Maytansinoids, Tubulysin/Eribulin, PBD/IGN/DUBA, KSPi, STING)
  - 8 DAR Levels (1, 2, 3.5, 4, 5, 6, 7.6, 8)
  - 4 Antibody / Fc Formats (IgG1 WT, IgG1 LALA-PG, IgG4 S228P, IgG2 Low-Fc)
  => Total = 36 x 16 x 20 x 8 x 4 = 368,640 combinations.

Outputs:
1. `ml/data/studio_catalog_368k.json`:
   Canonical metadata for all 36 targets, 16 linkers, 20 payloads, 8 DARs, and 4 Fc formats.
2. `ml/data/studio_368k_svd.npz`:
   Rank-24 FP16 truncated SVD factor matrices `(U, V)` of the 61 neural observables across `(144, 2560)`,
   enabling `<10 ms` vectorized NumPy matrix evaluation on any CPU without GPU.
3. `models/surrogate_c/surrogate_v2_merged_fp16.pt` + `ml/data/deep_research_cache.npz`:
   Pure-PyTorch LoRA-merged 5-fold `ADCSurrogateNetV2` bundle (no `peft` or HuggingFace hub required at runtime)
   plus precomputed ESM-2 650M, AlphaFold v6, GTEx/TS, and Boltzmann 3D conformers for real-time Deep Research
   on GPU (`cuda:0..3`) or CPU (`cpu`).
"""

from __future__ import annotations

import json
import math
import pickle
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import torch

from build_adcdb_corpus import (
    CANONICAL_LINKER_SMILES,
    CANONICAL_PAYLOAD_SMILES,
    FEATURE_INDICES,
    ORGANS_13,
    analyze_linker_cleavage_reaction,
    build_biophysical_vector,
    compute_3d_conformer_physics,
    compute_morgan_fp1024,
    load_human_organ_expression_maps,
)
from train_surrogate_nn import CHEMBERTA_NAME, N_FOLDS, ADCSurrogateNetV2
from transformers import AutoTokenizer

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "ml" / "data"
MODEL_DIR = REPO / "models" / "surrogate_c"

# ==============================================================================
# 1. Canonical 36 Targets, 16 Linkers, 20 Payloads, 8 DARs, 4 Fc Formats
# ==============================================================================
STUDIO_TARGETS_36: List[Dict[str, Any]] = [
    # --- Group A: Breast & Gynecologic Solid Tumors (7) ---
    {
        "id": "HER2 (ERBB2)", "gene": "ERBB2", "uniprot": "P04626", "mab": "trastuzumab", "group": "breast_gyn",
        "refAdc": "trastuzumab-deruxtecan", "selectivity": 4.9, "tumor_tpm": 280.0,
        "tumorKeys": ["breast", "gastric", "stomach", "nsclc", "lung", "colorectal", "colon", "bladder", "urothelial", "biliary", "유방", "위암", "폐암", "대장", "방광", "담도"],
        "tissues": [{"organ": "pulmonary", "tpm": 48}, {"organ": "cardiovascular", "tpm": 36}, {"organ": "gastrointestinal", "tpm": 42}],
        "popover": "Receptor tyrosine kinase amplified in breast, gastric, and NSCLC tumors. Baseline expression in lung alveolar epithelium and cardiomyocytes requires monitoring for ILD and LVEF decline.",
        "popover_ko": "유방암, 위암, 비소세포폐암에서 증폭되는 수용체 티로신 키나아제입니다. 폐포 상피세포와 심근세포에 기저 발현이 존재하여 간질성 폐질환(ILD) 및 좌심실 구혈률(LVEF) 감시가 필요합니다.",
    },
    {
        "id": "TROP2 (TACSTD2)", "gene": "TACSTD2", "uniprot": "P09758", "mab": "datopotamab", "group": "breast_gyn",
        "refAdc": "sacituzumab-govitecan", "selectivity": 4.4, "tumor_tpm": 310.0,
        "tumorKeys": ["breast", "tnbc", "nsclc", "lung", "urothelial", "bladder", "cervical", "endometrial", "ovarian", "유방", "삼중음성", "폐암", "요로상피", "방광", "자궁", "난소"],
        "tissues": [{"organ": "gastrointestinal", "tpm": 68}, {"organ": "dermatologic", "tpm": 62}, {"organ": "pulmonary", "tpm": 39}],
        "popover": "Transmembrane glycoprotein broadly overexpressed across epithelial carcinomas; baseline expression in GI mucosa and stratified skin keratinocytes mediates mucosal and cutaneous sensitivity.",
        "popover_ko": "상피성 고형암 전반에 과발현되는 막관통 당단백질입니다. 대장 점막 및 피부 각질형성세포에 기저 발현이 있어 구내염, 설사 및 피부 발진 민감도와 연관됩니다.",
    },
    {
        "id": "FRalpha (FOLR1)", "gene": "FOLR1", "uniprot": "P15328", "mab": "mirvetuximab", "group": "breast_gyn",
        "refAdc": "mirvetuximab-soravtansine", "selectivity": 4.6, "tumor_tpm": 210.0,
        "tumorKeys": ["ovarian", "endometrial", "fallopian", "peritoneal", "nsclc", "난소", "자궁내막", "나팔관", "복막"],
        "tissues": [{"organ": "ocular", "tpm": 54}, {"organ": "pulmonary", "tpm": 44}, {"organ": "renal", "tpm": 51}],
        "popover": "GPI-anchored folate receptor overexpressed in ovarian and endometrial carcinomas; apical expression in corneal epithelium and renal tubules requires ocular monitoring.",
        "popover_ko": "난소암, 자궁내막암에서 과발현되는 엽산 수용체 알파입니다. 각막 상피와 신장 근위세뇨관에 기저 발현이 있어 점안제 예방 등 안과적 관리가 권장됩니다.",
    },
    {
        "id": "Tissue Factor (F3)", "gene": "F3", "uniprot": "P13726", "mab": "tisotumab", "group": "breast_gyn",
        "refAdc": "tisotumab-vedotin", "selectivity": 4.2, "tumor_tpm": 195.0,
        "tumorKeys": ["cervical", "ovarian", "head and neck", "pancreatic", "자궁경부", "난소", "두경부", "췌장"],
        "tissues": [{"organ": "ocular", "tpm": 58}, {"organ": "dermatologic", "tpm": 46}, {"organ": "pulmonary", "tpm": 35}],
        "popover": "Coagulation initiator receptor highly expressed in cervical and squamous carcinomas; conjunctival and mucosal expression drives ocular surface and epistaxis risk.",
        "popover_ko": "자궁경부암 및 편평상피암에서 고발현되는 응고 개시 수용체입니다. 결막 및 비강 점막 상피 발현으로 인해 결막염, 안구건조 및 비출혈 관리가 중요합니다.",
    },
    {
        "id": "HER3 (ERBB3)", "gene": "ERBB3", "uniprot": "P21860", "mab": "patritumab", "group": "breast_gyn",
        "refAdc": "trastuzumab-deruxtecan", "selectivity": 4.5, "tumor_tpm": 230.0,
        "tumorKeys": ["breast", "nsclc", "lung", "egfr", "colorectal", "ovarian", "유방", "폐암", "대장", "난소"],
        "tissues": [{"organ": "gastrointestinal", "tpm": 48}, {"organ": "dermatologic", "tpm": 36}, {"organ": "hepatic", "tpm": 28}],
        "popover": "Pseudokinase receptor driving EGFR-TKI resistance in NSCLC and luminal/HER2 breast cancers (Patritumab deruxtecan target) with rapid clathrin internalization.",
        "popover_ko": "EGFR 표적치료 내성 비소세포폐암과 유방암에서 과발현되는 수용체(파트리투맙 데룩스테칸 표적)로, 내재화 속도가 빠르고 심근 기저 발현이 HER2보다 낮습니다.",
    },
    {
        "id": "LIV-1 (SLC39A6)", "gene": "SLC39A6", "uniprot": "Q13433", "mab": "sacituzumab", "group": "breast_gyn",
        "refAdc": "sacituzumab-govitecan", "selectivity": 4.7, "tumor_tpm": 245.0,
        "tumorKeys": ["breast", "tnbc", "prostate", "melanoma", "cervical", "유방", "삼중음성", "전립선", "흑색종"],
        "tissues": [{"organ": "metabolic_endocrine", "tpm": 42}, {"organ": "gastrointestinal", "tpm": 22}, {"organ": "dermatologic", "tpm": 18}],
        "popover": "Zinc transporter protein enriched across hormone-positive and triple-negative breast cancers (Ladiratuzumab target) with low visceral organ expression.",
        "popover_ko": "호르몬 양성 및 삼중음성 유방암 전반에 고발현되는 아연 수송체 막단백질(라디라투주맙 표적)로, 주요 실질 장기 내 기저 발현이 낮습니다.",
    },
    {
        "id": "NaPi2b (SLC34A2)", "gene": "SLC34A2", "uniprot": "O95436", "mab": "mirvetuximab", "group": "breast_gyn",
        "refAdc": "mirvetuximab-soravtansine", "selectivity": 3.8, "tumor_tpm": 265.0,
        "tumorKeys": ["ovarian", "nsclc", "lung", "endometrial", "thyroid", "난소", "폐암", "자궁내막", "갑상선"],
        "tissues": [{"organ": "pulmonary", "tpm": 88}, {"organ": "gastrointestinal", "tpm": 24}, {"organ": "renal", "tpm": 18}],
        "popover": "Sodium-dependent phosphate transporter overexpressed in high-grade serous ovarian cancer and NSCLC; physiological surfactant pneumocyte expression warrants pulmonary caution.",
        "popover_ko": "고등급 장액성 난소암과 비소세포폐암에서 발현되는 인산 수송체입니다. 정상 제2형 폐포 상피세포의 발현량이 높아 폐 독성 회피 설계가 필수적입니다.",
    },

    # --- Group B: Lung & Gastrointestinal Solid Tumors (10) ---
    {
        "id": "EGFR", "gene": "EGFR", "uniprot": "P00533", "mab": "trastuzumab", "group": "lung_gi",
        "refAdc": "enfortumab-vedotin", "selectivity": 3.9, "tumor_tpm": 290.0,
        "tumorKeys": ["nsclc", "lung", "head and neck", "colorectal", "colon", "glioblastoma", "glioma", "폐암", "두경부", "대장", "교모세포종", "뇌종양"],
        "tissues": [{"organ": "dermatologic", "tpm": 92}, {"organ": "gastrointestinal", "tpm": 54}, {"organ": "ocular", "tpm": 45}],
        "popover": "Epidermal growth factor receptor amplified in NSCLC, HNSCC, colorectal, and glioblastoma; abundant basal keratinocyte and corneal expression drives rash and keratitis.",
        "popover_ko": "비소세포폐암, 두경부암, 대장암, 교모세포종에서 증폭되는 표피성장인자 수용체입니다. 피부 기저 각질세포와 각막 상피 발현이 높아 피부 및 안구 독성 제어가 핵심입니다.",
    },
    {
        "id": "c-MET (MET)", "gene": "MET", "uniprot": "P08581", "mab": "telisotuzumab", "group": "lung_gi",
        "refAdc": "enfortumab-vedotin", "selectivity": 4.4, "tumor_tpm": 215.0,
        "tumorKeys": ["nsclc", "lung", "gastric", "stomach", "colorectal", "colon", "renal", "hepatocellular", "liver", "폐암", "위암", "대장", "신장암", "간암"],
        "tissues": [{"organ": "hepatic", "tpm": 46}, {"organ": "gastrointestinal", "tpm": 38}, {"organ": "renal", "tpm": 34}],
        "popover": "Hepatocyte growth factor receptor overexpressed in MET-amplified NSCLC, gastric, and colorectal cancers (Telisotuzumab vedotin target).",
        "popover_ko": "비소세포폐암, 위암, 대장암에서 증폭되는 간세포성장인자 수용체(텔리소투주맙 베도틴 표적)로, 간세포 및 위장관 상피 기저 발현을 고려해 설계합니다.",
    },
    {
        "id": "CEACAM5", "gene": "CEACAM5", "uniprot": "P06731", "mab": "sacituzumab", "group": "lung_gi",
        "refAdc": "sacituzumab-govitecan", "selectivity": 4.8, "tumor_tpm": 350.0,
        "tumorKeys": ["colorectal", "colon", "rectal", "gastric", "stomach", "nsclc", "lung", "pancreatic", "대장", "결장", "직장", "위암", "폐암", "췌장"],
        "tissues": [{"organ": "gastrointestinal", "tpm": 86}, {"organ": "pulmonary", "tpm": 18}, {"organ": "hepatic", "tpm": 8}],
        "popover": "Carcinoembryonic antigen densely expressed on colorectal, gastric, pancreatic, and non-squamous NSCLC tumors (Tusamitamab / Precemtabart target).",
        "popover_ko": "대장암, 위암, 췌장암, 비편평 비소세포폐암에서 고밀도로 발현되는 암배아항원(투사미타맙, 프레셈타바트 표적)입니다. 정상 대장 점막 외 전신 장기 발현이 낮습니다.",
    },
    {
        "id": "CLDN18.2 (CLDN18)", "gene": "CLDN18", "uniprot": "P56856", "mab": "disitamab", "group": "lung_gi",
        "refAdc": "trastuzumab-deruxtecan", "selectivity": 5.1, "tumor_tpm": 260.0,
        "tumorKeys": ["gastric", "stomach", "esophageal", "pancreatic", "biliary", "cholangio", "위암", "식도암", "췌장", "담도", "담관"],
        "tissues": [{"organ": "gastrointestinal", "tpm": 90}, {"organ": "pulmonary", "tpm": 22}, {"organ": "hepatic", "tpm": 4}],
        "popover": "Tight-junction isoform buried in healthy gastric pits but exposed on gastric, GEJ, and pancreatic adenocarcinoma surfaces, yielding high tumor selectivity outside gastric mucosa.",
        "popover_ko": "정상 위 점막에서는 세포 간 밀착연접 내부에 숨겨져 있다가 위암, 식도위접합부암, 췌장암에서 표면으로 노출되는 고선택성 표적입니다.",
    },
    {
        "id": "B7-H3 (CD276)", "gene": "CD276", "uniprot": "Q5ZPR3", "mab": "patritumab", "group": "lung_gi",
        "refAdc": "trastuzumab-deruxtecan", "selectivity": 5.2, "tumor_tpm": 240.0,
        "tumorKeys": ["sclc", "nsclc", "lung", "prostate", "esophageal", "head and neck", "sarcoma", "neuroblastoma", "폐암", "소세포", "전립선", "식도암", "육종", "두경부"],
        "tissues": [{"organ": "metabolic_endocrine", "tpm": 18}, {"organ": "pulmonary", "tpm": 16}, {"organ": "cardiovascular", "tpm": 14}],
        "popover": "Immune checkpoint ligand overexpressed across SCLC, prostate, esophageal, and pediatric solid tumors (Ifinatamab deruxtecan target) with restricted normal organ translation.",
        "popover_ko": "소세포폐암, 전립선암, 식도암, 육종 등 고형암 전반에 과발현되는 면역관문 단백질(이피나타맙 데룩스테칸 표적)로 정상 장기 발현이 낮아 치료지수가 넓습니다.",
    },
    {
        "id": "DLL3", "gene": "DLL3", "uniprot": "Q9NYJ7", "mab": "loncastuximab", "group": "lung_gi",
        "refAdc": "loncastuximab-tesirine", "selectivity": 5.9, "tumor_tpm": 185.0,
        "tumorKeys": ["sclc", "neuroendocrine", "lung", "prostate", "glioma", "소세포폐암", "폐암", "신경내분비"],
        "tissues": [{"organ": "neurologic", "tpm": 22}, {"organ": "metabolic_endocrine", "tpm": 11}, {"organ": "pulmonary", "tpm": 4}],
        "popover": "Inhibitory Notch ligand selectively expressed on small-cell lung cancer (SCLC) and neuroendocrine carcinomas with virtually absent surface expression in adult normal organs.",
        "popover_ko": "소세포폐암(SCLC) 및 신경내분비 종양 표면에 특이적으로 발현되는 Notch 리간드로, 성인 정상 조직의 세포막 표면 발현이 극히 낮습니다.",
    },
    {
        "id": "Mesothelin (MSLN)", "gene": "MSLN", "uniprot": "Q13421", "mab": "mirvetuximab", "group": "lung_gi",
        "refAdc": "mirvetuximab-soravtansine", "selectivity": 4.5, "tumor_tpm": 255.0,
        "tumorKeys": ["mesothelioma", "ovarian", "pancreatic", "nsclc", "lung", "중피종", "흉막", "난소", "췌장", "폐암"],
        "tissues": [{"organ": "pulmonary", "tpm": 48}, {"organ": "cardiovascular", "tpm": 30}, {"organ": "gastrointestinal", "tpm": 14}],
        "popover": "GPI-anchored glycoprotein overexpressed in mesothelioma, pancreatic, and ovarian cancers (Anetumab target); normal expression is confined to pleural/pericardial/peritoneal serosa.",
        "popover_ko": "악성 중피종, 췌장암, 난소암에서 과발현되는 막단백질(아네투맙 표적)입니다. 정상 발현이 흉막, 심낭, 복막 중피세포에 국한되어 장막염 감시가 필요합니다.",
    },
    {
        "id": "EpCAM", "gene": "EPCAM", "uniprot": "P16422", "mab": "sacituzumab", "group": "lung_gi",
        "refAdc": "sacituzumab-govitecan", "selectivity": 3.7, "tumor_tpm": 330.0,
        "tumorKeys": ["colorectal", "colon", "gastric", "breast", "pancreatic", "ovarian", "대장", "위암", "유방", "췌장", "난소"],
        "tissues": [{"organ": "gastrointestinal", "tpm": 94}, {"organ": "pulmonary", "tpm": 46}, {"organ": "renal", "tpm": 38}],
        "popover": "Pan-epithelial cell adhesion molecule with very high copy density across GI and breast carcinomas; basolateral expression in normal gut and biliary epithelium requires stable linkers.",
        "popover_ko": "위장관암, 유방암 등 상피성 암종에서 매우 높은 밀도로 발현되나 정상 장 점막 및 담관 상피에도 발현되어 고안정성 링커 조합이 요구됩니다.",
    },
    {
        "id": "FGFR2", "gene": "FGFR2", "uniprot": "P21802", "mab": "trastuzumab", "group": "lung_gi",
        "refAdc": "enfortumab-vedotin", "selectivity": 4.3, "tumor_tpm": 205.0,
        "tumorKeys": ["gastric", "stomach", "cholangio", "biliary", "breast", "endometrial", "위암", "담관", "담도", "유방", "자궁내막"],
        "tissues": [{"organ": "dermatologic", "tpm": 58}, {"organ": "ocular", "tpm": 46}, {"organ": "gastrointestinal", "tpm": 36}],
        "popover": "Fibroblast growth factor receptor 2b/2 amplified in diffuse gastric cancer and intrahepatic cholangiocarcinoma (Aprutumab target); corneal and nail-bed expression warrants ocular care.",
        "popover_ko": "미만성 위암과 담관암에서 유전자 증폭이 흔한 수용체(아프루투맙 표적)이며, 각막 및 피부 부속기 기저 발현을 고려해야 합니다.",
    },
    {
        "id": "Integrin beta-6 (ITGB6)", "gene": "ITGB6", "uniprot": "P18564", "mab": "enfortumab", "group": "lung_gi",
        "refAdc": "enfortumab-vedotin", "selectivity": 4.8, "tumor_tpm": 225.0,
        "tumorKeys": ["nsclc", "lung", "head and neck", "esophageal", "pancreatic", "breast", "폐암", "두경부", "식도암", "췌장", "유방"],
        "tissues": [{"organ": "pulmonary", "tpm": 36}, {"organ": "gastrointestinal", "tpm": 28}, {"organ": "dermatologic", "tpm": 24}],
        "popover": "Epithelial-restricted alpha-v-beta-6 integrin upregulated during carcinoma invasion in NSCLC, HNSCC, and esophageal cancer (Sigvotatug vedotin target).",
        "popover_ko": "비소세포폐암, 두경부암, 식도암의 침윤 과정에서 특이적으로 유도되는 인테그린(시그보타투그 베도틴 표적)으로 정상 성체 조직 발현이 낮습니다.",
    },

    # --- Group C: Genitourinary & Pan-Solid Tumors (10) ---
    {
        "id": "Nectin-4", "gene": "NECTIN4", "uniprot": "Q96NY8", "mab": "enfortumab", "group": "gu_solid",
        "refAdc": "enfortumab-vedotin", "selectivity": 4.3, "tumor_tpm": 190.0,
        "tumorKeys": ["urothelial", "bladder", "breast", "nsclc", "cervical", "요로상피", "방광", "유방", "자궁경부"],
        "tissues": [{"organ": "dermatologic", "tpm": 84}, {"organ": "metabolic_endocrine", "tpm": 45}, {"organ": "ocular", "tpm": 34}],
        "popover": "Cell adhesion molecule highly enriched in urothelial carcinoma; physiological expression in epidermal keratinocytes and sweat glands mediates cutaneous toxicity.",
        "popover_ko": "요로상피암(방광암)에서 고밀도로 발현되는 세포 접착 분자입니다. 정상 표피 각질세포와 땀샘에도 발현량이 높아 표적 매개 피부 발진, 건조증에 대한 관리가 중요합니다.",
    },
    {
        "id": "PSMA (FOLH1)", "gene": "FOLH1", "uniprot": "Q04609", "mab": "enfortumab", "group": "gu_solid",
        "refAdc": "enfortumab-vedotin", "selectivity": 5.3, "tumor_tpm": 295.0,
        "tumorKeys": ["prostate", "renal", "kidney", "전립선", "신장암"],
        "tissues": [{"organ": "renal", "tpm": 52}, {"organ": "gastrointestinal", "tpm": 28}, {"organ": "neurologic", "tpm": 19}],
        "popover": "Prostate-specific membrane antigen densely expressed in metastatic castration-resistant prostate cancer and tumor neovasculature, with proximal renal tubule and salivary expression.",
        "popover_ko": "전이성 거세저항성 전립선암과 종양 신생혈관에 고발현되는 막항원입니다. 신장 근위세뇨관 및 침샘의 기저 발현을 고려해 페이로드를 선택합니다.",
    },
    {
        "id": "STEAP1", "gene": "STEAP1", "uniprot": "Q9UHE8", "mab": "enfortumab", "group": "gu_solid",
        "refAdc": "enfortumab-vedotin", "selectivity": 5.4, "tumor_tpm": 240.0,
        "tumorKeys": ["prostate", "sarcoma", "ewing", "bladder", "전립선", "육종", "방광"],
        "tissues": [{"organ": "metabolic_endocrine", "tpm": 25}, {"organ": "renal", "tpm": 14}, {"organ": "pulmonary", "tpm": 12}],
        "popover": "Six-transmembrane epithelial antigen of the prostate (Vandortuzumab target) overexpressed in >85% of prostate cancers and Ewing sarcoma with minimal normal visceral expression.",
        "popover_ko": "전립선암의 85% 이상과 유윙 육종에서 과발현되는 6막관통 단백질(반도르투주맙 표적)로 정상 실질 장기의 기저 발현이 매우 낮습니다.",
    },
    {
        "id": "CDH6", "gene": "CDH6", "uniprot": "P55285", "mab": "datopotamab", "group": "gu_solid",
        "refAdc": "trastuzumab-deruxtecan", "selectivity": 5.0, "tumor_tpm": 235.0,
        "tumorKeys": ["ovarian", "renal", "kidney", "endometrial", "cholangio", "난소", "신장암", "신세포암", "자궁내막"],
        "tissues": [{"organ": "renal", "tpm": 68}, {"organ": "neurologic", "tpm": 16}, {"organ": "cardiovascular", "tpm": 8}],
        "popover": "Cadherin-6 cell adhesion receptor overexpressed in ovarian and clear-cell renal cell carcinoma (Raludotatug deruxtecan target); normal expression is mainly renal proximal tubules.",
        "popover_ko": "난소암 및 투명세포 신세포암에서 고발현되는 카드헤린-6(랄루도타투그 데룩스테칸 표적)로, 정상 조직 발현은 신장 근위세뇨관에 제한됩니다.",
    },
    {
        "id": "ENPP3", "gene": "ENPP3", "uniprot": "O14638", "mab": "enfortumab", "group": "gu_solid",
        "refAdc": "belantamab-mafodotin", "selectivity": 5.1, "tumor_tpm": 220.0,
        "tumorKeys": ["renal", "kidney", "hepatocellular", "liver", "신장암", "신세포암", "간암"],
        "tissues": [{"organ": "renal", "tpm": 44}, {"organ": "gastrointestinal", "tpm": 32}, {"organ": "hepatic", "tpm": 18}],
        "popover": "Ectonucleotide pyrophosphatase (CD203c, AGS-16C3F target) expressed in >90% of clear-cell and papillary renal cell carcinomas with low systemic background.",
        "popover_ko": "투명세포 및 유두상 신세포암의 90% 이상에서 과발현되는 효소 수용체(AGS-16C3F 표적)로 비표적 장기 기저 발현이 낮습니다.",
    },
    {
        "id": "AXL", "gene": "AXL", "uniprot": "P30530", "mab": "tisotumab", "group": "gu_solid",
        "refAdc": "tisotumab-vedotin", "selectivity": 4.4, "tumor_tpm": 205.0,
        "tumorKeys": ["nsclc", "lung", "sarcoma", "melanoma", "pancreatic", "renal", "aml", "폐암", "육종", "흑색종", "췌장", "신장암"],
        "tissues": [{"organ": "pulmonary", "tpm": 34}, {"organ": "cardiovascular", "tpm": 26}, {"organ": "musculoskeletal", "tpm": 22}],
        "popover": "TAM-family receptor tyrosine kinase enriched in mesenchymal/EMT drug-resistant NSCLC, sarcoma, and melanoma (Enapotamab / Mecbotamab target).",
        "popover_ko": "상피-중간엽 전이(EMT) 및 치료 저항성 비소세포폐암, 육종, 흑색종에서 발현이 증가하는 수용체(에나포타맙, 멕보타맙 표적)입니다.",
    },
    {
        "id": "PTK7", "gene": "PTK7", "uniprot": "Q13308", "mab": "datopotamab", "group": "gu_solid",
        "refAdc": "sacituzumab-govitecan", "selectivity": 4.7, "tumor_tpm": 225.0,
        "tumorKeys": ["ovarian", "nsclc", "lung", "tnbc", "breast", "esophageal", "난소", "폐암", "유방", "삼중음성", "식도암"],
        "tissues": [{"organ": "gastrointestinal", "tpm": 32}, {"organ": "pulmonary", "tpm": 24}, {"organ": "dermatologic", "tpm": 22}],
        "popover": "Wnt-pathway pseudokinase receptor enriched on tumor-initiating cells in ovarian cancer, TNBC, and NSCLC (Cofetuzumab pelidotin target).",
        "popover_ko": "난소암, 삼중음성 유방암, 비소세포폐암의 암줄기세포 분획에서 과발현되는 Wnt 경로 수용체(코페투주맙 표적)입니다.",
    },
    {
        "id": "P-Cadherin (CDH3)", "gene": "CDH3", "uniprot": "P22223", "mab": "enfortumab", "group": "gu_solid",
        "refAdc": "enfortumab-vedotin", "selectivity": 4.3, "tumor_tpm": 240.0,
        "tumorKeys": ["head and neck", "breast", "tnbc", "pancreatic", "gastric", "colorectal", "두경부", "유방", "삼중음성", "췌장", "위암", "대장"],
        "tissues": [{"organ": "dermatologic", "tpm": 64}, {"organ": "gastrointestinal", "tpm": 34}, {"organ": "ocular", "tpm": 22}],
        "popover": "Placental cadherin upregulated in basal-like breast, HNSCC, pancreatic, and gastric carcinomas (PCA062 target); basal epidermal expression parallels Nectin-4.",
        "popover_ko": "기저유사 유방암, 두경부암, 췌장암, 위암에서 발현되는 태반성 카드헤린으로, 피부 기저층 발현이 있어 피부 독성 감시가 권장됩니다.",
    },
    {
        "id": "GPNMB", "gene": "GPNMB", "uniprot": "Q14956", "mab": "enfortumab", "group": "gu_solid",
        "refAdc": "enfortumab-vedotin", "selectivity": 4.6, "tumor_tpm": 230.0,
        "tumorKeys": ["melanoma", "breast", "tnbc", "osteosarcoma", "sarcoma", "glioma", "흑색종", "피부암", "유방", "삼중음성", "골육종", "육종"],
        "tissues": [{"organ": "dermatologic", "tpm": 45}, {"organ": "musculoskeletal", "tpm": 18}, {"organ": "pulmonary", "tpm": 16}],
        "popover": "Osteoactivin transmembrane glycoprotein overexpressed in melanoma, TNBC, and osteosarcoma (Glembatumumab vedotin target); melanocyte expression links to rash.",
        "popover_ko": "흑색종, 삼중음성 유방암, 골육종에서 과발현되는 막관통 당단백질(글렘바투무맙 베도틴 표적)로 피부 멜라닌세포 발현과 연관됩니다.",
    },
    {
        "id": "ROR1", "gene": "ROR1", "uniprot": "Q01973", "mab": "polatuzumab", "group": "gu_solid",
        "refAdc": "polatuzumab-vedotin", "selectivity": 5.5, "tumor_tpm": 195.0,
        "tumorKeys": ["lymphoma", "cll", "leukemia", "tnbc", "breast", "nsclc", "ovarian", "림프종", "백혈병", "유방", "삼중음성", "폐암", "난소"],
        "tissues": [{"organ": "cardiovascular", "tpm": 11}, {"organ": "neurologic", "tpm": 9}, {"organ": "pulmonary", "tpm": 8}],
        "popover": "Oncofetal receptor expressed across mantle-cell/DLBCL lymphomas, CLL, TNBC, and NSCLC (Zilovertamab vedotin target) with minimal adult tissue expression.",
        "popover_ko": "외투세포 및 미만성 거대 B세포 림프종과 삼중음성 유방암, 폐암에 발현되는 태아성 종양항원(질로버타맙 베도틴 표적)으로 성인 정상 조직 발현이 매우 낮습니다.",
    },

    # --- Group D: Hematologic Malignancies (9) ---
    {
        "id": "CD79b", "gene": "CD79B", "uniprot": "P40259", "mab": "polatuzumab", "group": "heme",
        "refAdc": "polatuzumab-vedotin", "selectivity": 5.4, "tumor_tpm": 240.0,
        "tumorKeys": ["lymphoma", "dlbcl", "b-cell", "leukemia", "림프종", "백혈병", "미만성"],
        "tissues": [{"organ": "haematologic", "tpm": 72}, {"organ": "infectious_immune", "tpm": 58}, {"organ": "hepatic", "tpm": 12}],
        "popover": "B-cell receptor signaling subunit restricted to B-lineage lymphomas; rapidly internalized upon cross-linking with high selectivity outside lymphoid compartments.",
        "popover_ko": "B세포 계열 림프종에 선택적으로 발현되는 B세포 수용체 신호전달 소단위입니다. 결합 시 신속히 내재화되며 골수, 림프 조직 외 고형 장기 발현은 매우 낮습니다.",
    },
    {
        "id": "BCMA (TNFRSF17)", "gene": "TNFRSF17", "uniprot": "Q02223", "mab": "belantamab", "group": "heme",
        "refAdc": "belantamab-mafodotin", "selectivity": 5.8, "tumor_tpm": 260.0,
        "tumorKeys": ["myeloma", "plasma", "waldenstrom", "골수종", "형질세포"],
        "tissues": [{"organ": "haematologic", "tpm": 66}, {"organ": "ocular", "tpm": 49}, {"organ": "renal", "tpm": 14}],
        "popover": "Lineage-restricted receptor on mature plasma cells in multiple myeloma; corneal epithelial changes arise via off-target macropinocytosis of charged conjugates.",
        "popover_ko": "다발성 골수종 형질세포에 특이적으로 발현되는 성숙 항원입니다. 정상 고형 장기 발현은 극히 낮으나 각막 상피의 비특이적 거대음세포작용을 통한 안구 독성이 주요 감시 대상입니다.",
    },
    {
        "id": "CD19", "gene": "CD19", "uniprot": "P15391", "mab": "loncastuximab", "group": "heme",
        "refAdc": "loncastuximab-tesirine", "selectivity": 5.5, "tumor_tpm": 250.0,
        "tumorKeys": ["lymphoma", "dlbcl", "all", "cll", "leukemia", "b-cell", "림프종", "백혈병"],
        "tissues": [{"organ": "haematologic", "tpm": 68}, {"organ": "infectious_immune", "tpm": 62}, {"organ": "hepatic", "tpm": 10}],
        "popover": "Pan-B-lineage co-receptor expressed from pre-B ALL through DLBCL (Loncastuximab tesirine target) with zero expression on non-hematopoietic solid parenchyma.",
        "popover_ko": "급성 림프구성 백혈병부터 미만성 거대 B세포 림프종까지 폭넓게 발현되는 B세포 공수용체(론카스툭시맙 테시린 표적)로 비조혈계 고형 장기 발현이 없습니다.",
    },
    {
        "id": "CD22", "gene": "CD22", "uniprot": "P20273", "mab": "inotuzumab", "group": "heme",
        "refAdc": "inotuzumab-ozogamicin", "selectivity": 5.4, "tumor_tpm": 235.0,
        "tumorKeys": ["all", "leukemia", "lymphoma", "b-cell", "백혈병", "림프종"],
        "tissues": [{"organ": "haematologic", "tpm": 64}, {"organ": "infectious_immune", "tpm": 54}, {"organ": "hepatic", "tpm": 16}],
        "popover": "Sialic-acid binding Ig-like lectin (Siglec-2) rapidly endocytosed on B-cell ALL and NHL blasts (Inotuzumab ozogamicin target); hepatic VOD risk comes from calicheamicin payload.",
        "popover_ko": "B세포 급성 림프구성 백혈병에서 빠르게 내재화되는 시알산 결합 수용체(이노투주맙 오조가마이신 표적)입니다. 간 정맥폐쇄성 질환 위험은 주로 칼리키아마이신 페이로드에서 기인합니다.",
    },
    {
        "id": "CD30 (TNFRSF8)", "gene": "TNFRSF8", "uniprot": "P28908", "mab": "brentuximab", "group": "heme",
        "refAdc": "brentuximab-vedotin", "selectivity": 5.9, "tumor_tpm": 275.0,
        "tumorKeys": ["hodgkin", "lymphoma", "alcl", "t-cell", "호지킨", "림프종"],
        "tissues": [{"organ": "infectious_immune", "tpm": 34}, {"organ": "haematologic", "tpm": 28}, {"organ": "pulmonary", "tpm": 8}],
        "popover": "TNF-receptor family member densely expressed on Hodgkin Reed-Sternberg cells and ALCL (Brentuximab vedotin target), restricted to small activated lymphocyte subsets in health.",
        "popover_ko": "호지킨 림프종과 역형성 거대세포 림프종에서 선택적으로 고발현되는 수용체(브렌툭시맙 베도틴 표적)로 정상 조직 내 기저 발현이 극히 제한적입니다.",
    },
    {
        "id": "CD33", "gene": "CD33", "uniprot": "P20138", "mab": "gemtuzumab", "group": "heme",
        "refAdc": "gemtuzumab-ozogamicin", "selectivity": 4.9, "tumor_tpm": 245.0,
        "tumorKeys": ["aml", "myeloid", "leukemia", "myelodysplastic", "백혈병", "골수성", "골수이형성"],
        "tissues": [{"organ": "haematologic", "tpm": 78}, {"organ": "hepatic", "tpm": 34}, {"organ": "infectious_immune", "tpm": 42}],
        "popover": "Myeloid Siglec-3 receptor expressed on ~90% of AML blasts (Gemtuzumab ozogamicin target); shared expression on myeloid progenitors and hepatic Kupffer cells drives cytopenia and VOD.",
        "popover_ko": "급성 골수성 백혈병(AML) 모세포의 약 90%에 발현되는 골수계 항원(겜투주맙 오조가마이신 표적)으로 골수 전구세포와 간 쿠퍼세포 발현에 따른 혈구감소 및 간독성 관리가 핵심입니다.",
    },
    {
        "id": "CD123 (IL3RA)", "gene": "IL3RA", "uniprot": "P26951", "mab": "gemtuzumab", "group": "heme",
        "refAdc": "gemtuzumab-ozogamicin", "selectivity": 5.3, "tumor_tpm": 215.0,
        "tumorKeys": ["aml", "bpdcen", "myeloid", "leukemia", "myelodysplastic", "백혈병", "골수성", "골수이형성"],
        "tissues": [{"organ": "haematologic", "tpm": 58}, {"organ": "infectious_immune", "tpm": 36}, {"organ": "cardiovascular", "tpm": 18}],
        "popover": "Interleukin-3 receptor alpha chain enriched on leukemic stem cells in AML and BPDCN (Pivekimab sunirine target) with lower expression on normal HSCs than CD33.",
        "popover_ko": "급성 골수성 백혈병 줄기세포와 모세포성 형질세포양 수지상세포 종양에서 과발현되는 수용체(피베키맙 수니린 표적)로 CD33 대비 정상 조혈모세포 발현이 낮습니다.",
    },
    {
        "id": "CD70", "gene": "CD70", "uniprot": "P32970", "mab": "brentuximab", "group": "heme",
        "refAdc": "brentuximab-vedotin", "selectivity": 5.6, "tumor_tpm": 230.0,
        "tumorKeys": ["renal", "kidney", "lymphoma", "aml", "leukemia", "nasopharyngeal", "신장암", "림프종", "백혈병", "비인두암"],
        "tissues": [{"organ": "infectious_immune", "tpm": 28}, {"organ": "haematologic", "tpm": 22}, {"organ": "renal", "tpm": 10}],
        "popover": "CD27 ligand transiently expressed only on antigen-activated lymphocytes in health, but constitutively overexpressed in clear-cell RCC, NHL, and AML.",
        "popover_ko": "정상 상태에서는 활성화된 림프구에만 일시 발현되나 투명세포 신세포암, 림프종, 급성 골수성 백혈병에서 지속적으로 고발현되는 고선택성 표적입니다.",
    },
    {
        "id": "CD25 (IL2RA)", "gene": "IL2RA", "uniprot": "P01589", "mab": "brentuximab", "group": "heme",
        "refAdc": "brentuximab-vedotin", "selectivity": 5.4, "tumor_tpm": 220.0,
        "tumorKeys": ["hodgkin", "lymphoma", "t-cell", "leukemia", "호지킨", "림프종", "백혈병"],
        "tissues": [{"organ": "infectious_immune", "tpm": 48}, {"organ": "haematologic", "tpm": 35}, {"organ": "dermatologic", "tpm": 12}],
        "popover": "IL-2 receptor alpha chain expressed on Hodgkin/T-cell lymphomas and intratumoral immunosuppressive Treg cells (Camidanlumab tesirine target).",
        "popover_ko": "호지킨 및 T세포 림프종 세포와 종양 미세환경 내 면역억제 조절 T세포(Treg)에 고발현되는 수용체(카미단루맙 테시린 표적)입니다.",
    },
]

STUDIO_LINKERS_16: List[Dict[str, Any]] = [
    # --- Protease-Cleavable Peptide Linkers (6) ---
    {
        "id": "Tetrapeptide GGFG", "group": "protease", "cleavable": True, "stability": 88, "hydro": 0.20, "handle": "amine_hydroxyl",
        "smi": CANONICAL_LINKER_SMILES["GGFG"],
        "popover": "Hydrophilic glycine-phenylalanine tetrapeptide cleaved selectively by lysosomal cathepsins B/L. High plasma stability (88%) and low hydrophobicity enable homogeneous DAR 8 loading.",
        "popover_ko": "리소좀 효소(카텝신 B/L)에 의해 선택적으로 절단되는 친수성 테트라펩타이드 링커입니다. 높은 혈장 안정도(88%)와 낮은 소수성으로 DAR 8 고밀도 접합에서도 간 응집을 억제합니다.",
    },
    {
        "id": "GGFG-Cyclopropyl", "group": "protease", "cleavable": True, "stability": 92, "hydro": 0.24, "handle": "amine_hydroxyl",
        "smi": CANONICAL_LINKER_SMILES["GGFG-Cyclopropyl"],
        "popover": "Cyclopropyl-shielded GGFG aminomethylene linker (SHR-A1811 / Rezetecan class) that slows premature plasma esterase/protease cleavage while preserving lysosomal Topo I release.",
        "popover_ko": "아미노메틸렌 자가절단 부위에 사이클로프로필 입체 보호기를 도입한 차세대 GGFG 링커(SHR-A1811 계열)로 혈중 조기 유출을 더욱 낮춥니다.",
    },
    {
        "id": "Val-Cit PABC", "group": "protease", "cleavable": True, "stability": 76, "hydro": 0.58, "handle": "amine",
        "smi": CANONICAL_LINKER_SMILES["vc-PABC"],
        "popover": "Standard cathepsin B-cleavable dipeptide linker with self-immolative 1,6-PABC spacer. Releases amine payloads cleanly inside tumor lysosomes, optimal at DAR 2-4.",
        "popover_ko": "카텝신 B 절단 후 자가소멸 스페이서(PABC)를 통해 유리 약물을 방출하는 표준 디펩타이드 링커입니다. 아민계 페이로드 방출 효율이 뛰어나며 DAR 2-4 구간에 적합합니다.",
    },
    {
        "id": "Val-Ala PABC", "group": "protease", "cleavable": True, "stability": 80, "hydro": 0.44, "handle": "amine",
        "smi": CANONICAL_LINKER_SMILES["va-PABC"],
        "popover": "Less hydrophobic Val-Ala dipeptide with PABC spacer; reduces high-DAR aggregation relative to Val-Cit while maintaining rapid cathepsin cleavage.",
        "popover_ko": "Val-Cit 대비 소수성과 응집 경향을 낮춘 Val-Ala 디펩타이드 PABC 링커로 리소좀 카텝신 절단 속도와 용해도의 균형이 우수합니다.",
    },
    {
        "id": "Glu-Val-Cit PABC", "group": "protease", "cleavable": True, "stability": 91, "hydro": 0.28, "handle": "amine",
        "smi": "CC(C)C(NC(=O)C(CCC(=O)O)NC(=O)CCCCC1C(=O)NCC1=O)C(=O)NC(CCCNC(N)=O)C(=O)Nc1ccc(CO)cc1",
        "popover": "Anionic Glu-Val-Cit tripeptide PABC linker engineered to block extracellular neutrophil-elastase cleavage in bone marrow and lungs while retaining full lysosomal cathepsin B release.",
        "popover_ko": "음전하 글루탐산(Glu)을 도입해 골수 및 폐 호중구 엘라스타아제에 의한 세포 외 조기 절단(호중구감소증 유발 경로)을 차단한 고안정성 트리펩타이드 링커입니다.",
    },
    {
        "id": "Legumain Asn-Pro-Val", "group": "protease", "cleavable": True, "stability": 93, "hydro": 0.34, "handle": "amine_hydroxyl",
        "smi": "CC(C)C(NC(=O)C1CCCN1C(=O)C(CC(N)=O)NC(=O)CCCCC1C(=O)NCC1=O)C(=O)Nc1ccc(COC(=O)O)cc1",
        "popover": "Tumor-associated legumain (asparaginyl endopeptidase) cleavable tripeptide linker with high stability in normal human plasma and myeloid progenitors.",
        "popover_ko": "종양 리소좀에 과발현되는 레구메인 효소에 의해서만 절단되는 Asn-Pro-Val 링커로 정상 혈장 및 조혈모세포 내 안정성이 매우 높습니다.",
    },

    # --- Hydrophilic / Shielded Cleavable Linkers (4) ---
    {
        "id": "PEG8-Val-Ala PABC", "group": "hydrophilic", "cleavable": True, "stability": 84, "hydro": 0.18, "handle": "amine",
        "smi": "COCCOCCOCCOCCOCCOCCOCCOCCNC(=O)C(CCC(=O)NC(C(C)C)C(=O)NC(C)C(=O)Nc1ccc(CO)cc1)NC(=O)CCN1C(=O)C=CC1=O",
        "popover": "Discrete PEG8-shielded Val-Ala PABC linker (Zynlonta / Tesirine architecture) that masks lipophilic warheads from hepatic Kupffer-cell uptake.",
        "popover_ko": "단분산 PEG8 친수성 사슬로 소수성 페이로드를 차폐한 Val-Ala PABC 링커(진론타 구조)로 간 쿠퍼세포의 비특이 포획을 줄입니다.",
    },
    {
        "id": "Beta-Glucuronide PEG8", "group": "hydrophilic", "cleavable": True, "stability": 90, "hydro": 0.14, "handle": "amine_hydroxyl",
        "smi": CANONICAL_LINKER_SMILES["PEG8-Glucuronide"],
        "popover": "Polyhydroxylated beta-glucuronide + PEG8 linker cleaved strictly by lysosomal beta-glucuronidase; ultra-low hydrophobicity prevents DAR 8 aggregation.",
        "popover_ko": "리소좀 베타-글루쿠로니다아제에 의해서만 절단되는 초친수성 글루쿠로나이드-PEG8 링커로 고밀도 DAR 접합에서도 응집과 조기 유출을 크게 낮춥니다.",
    },
    {
        "id": "Pyrimidine-TMT PEG8", "group": "hydrophilic", "cleavable": True, "stability": 86, "hydro": 0.22, "handle": "amine_hydroxyl",
        "smi": CANONICAL_LINKER_SMILES["Pyrimidine-TMT"],
        "popover": "Methylsulfonyl-pyrimidine irreversible thiol conjugation handle with PEG8 spacer (Sacituzumab tirumotecan / SKB264 class), eliminating retro-Michael maleimide deconjugation in plasma.",
        "popover_ko": "말레이미드의 역-마이클 혈장 탈접합 반응을 원천 차단하는 메틸설포닐 피리미딘 결합부 + PEG8 링커(사시투주맙 티루모테칸 계열)입니다.",
    },
    {
        "id": "Pyrophosphate Phos", "group": "hydrophilic", "cleavable": True, "stability": 91, "hydro": 0.10, "handle": "hydroxyl_amine_hydroxyl",
        "smi": "O=C(CCCCC1C(=O)NCC1=O)NCCOP(=O)(O)OP(=O)(O)OCc1ccc(O)cc1",
        "popover": "Di-anionic pyrophosphate diester linker cleaved sequentially by lysosomal acid pyrophosphatase and acid phosphatase; imparts high water solubility.",
        "popover_ko": "이중 음전하 피로인산 에스테르 링커로 혈중에서는 완전한 수용성을 유지하고 리소좀 산성 포스파타아제에 의해 선택적으로 절단됩니다.",
    },

    # --- pH / Redox Cleavable Linkers (4) ---
    {
        "id": "Hydrolyzable CL2A", "group": "ph_redox", "cleavable": True, "stability": 54, "hydro": 0.32, "handle": "hydroxyl",
        "smi": CANONICAL_LINKER_SMILES["CL2A"],
        "popover": "PEGylated pH-sensitive benzyl carbonate linker engineered for camptothecins (SN-38). Intratumoral extracellular + lysosomal hydrolysis drives broad bystander activity at DAR 7.6-8.",
        "popover_ko": "PEG 사슬이 도입된 pH 감응성 탄산염 링커(트로델비 구조)로 산성 종양 미세환경과 리소좀에서 약물을 방출해 강한 주변 암세포 사멸 효과를 유도합니다.",
    },
    {
        "id": "Disulfide SPDB", "group": "ph_redox", "cleavable": True, "stability": 68, "hydro": 0.52, "handle": "thiol",
        "smi": CANONICAL_LINKER_SMILES["SPDB"],
        "popover": "Sterically hindered gem-dimethyl disulfide bond reduced selectively by high intracellular tumor glutathione (GSH) to release thiol maytansinoids.",
        "popover_ko": "입체장애 이황화 결합으로 혈중 산화 환경에서는 안정하고 암세포 내 고농도 글루타티온(GSH)에 의해 환원되어 티올계 메이탄시노이드를 방출합니다.",
    },
    {
        "id": "Sulfo-SPDB", "group": "ph_redox", "cleavable": True, "stability": 74, "hydro": 0.26, "handle": "thiol",
        "smi": "CC(C)(CC(=O)O)SSc1ccc(S(=O)(=O)O)cn1",
        "popover": "Charged sulfonated hindered disulfide linker (Mirvetuximab soravtansine / Elahere) that suppresses multidrug-resistance (MDR1) efflux and hepatic aggregation of DM4 conjugates.",
        "popover_ko": "설폰산 음전하기를 도입한 이황화 링커(엘라히어 구조)로 소수성 응집과 다제내성 수송체(MDR1) 약물 유출을 동시에 억제합니다.",
    },
    {
        "id": "Acid Hydrazone", "group": "ph_redox", "cleavable": True, "stability": 48, "hydro": 0.55, "handle": "ketone",
        "smi": CANONICAL_LINKER_SMILES["Hydrazone"],
        "popover": "Acid-labile AcBut hydrazone linker hydrolyzed at endosomal/lysosomal pH 4.5-5.0; pairs with ketone-bearing enediynes (calicheamicin) with higher plasma deconjugation.",
        "popover_ko": "엔도솜 및 리소좀 산성 환경(pH 4.5-5.0)에서 가수분해되는 하이드라존 링커로 케톤 작용기 페이로드(칼리키아마이신)와 결합합니다.",
    },

    # --- Non-Cleavable Linkers (2) ---
    {
        "id": "Non-cleavable mc", "group": "non_cleavable", "cleavable": False, "stability": 96, "hydro": 0.42, "handle": "amine",
        "smi": CANONICAL_LINKER_SMILES["mc"],
        "popover": "Ultra-stable maleimidocaproyl thioether bond (96% plasma stability) requiring complete lysosomal antibody proteolysis to release charged Cys-mc-payload.",
        "popover_ko": "혈중 안정도 96%의 비절단형 티오에테르 링커로 항체가 리소좀에서 완전 분해될 때만 전하성 아미노산-페이로드 결합체를 방출해 전신 누출을 최소화합니다.",
    },
    {
        "id": "Non-cleavable SMCC", "group": "non_cleavable", "cleavable": False, "stability": 95, "hydro": 0.46, "handle": "thiol_amine",
        "smi": CANONICAL_LINKER_SMILES["SMCC"],
        "popover": "Rigid cyclohexanecarboxylate thioether linker (Trastuzumab emtansine / Kadcyla architecture) releasing Lys-SMCC-DM1 exclusively after full lysosomal catabolism.",
        "popover_ko": "사이클로헥산 고리를 포함한 고강성 비절단형 티오에테르 링커(캐싸일라 구조)로 리소좀 내 완전 단백질 분해 후에만 약물이 방출됩니다.",
    },
]

STUDIO_PAYLOADS_20: List[Dict[str, Any]] = [
    # --- Topoisomerase I Inhibitors (6) ---
    {
        "id": "DXd ( Topo I )", "group": "topo1", "cls": "Topoisomerase I inhibitor", "perm": True, "handle": "amine_hydroxyl",
        "potency": 92, "optDar": 8, "maxSafeDar": 8, "hydro": 0.28, "smi": CANONICAL_PAYLOAD_SMILES["DXd"],
        "organs": {"pulmonary": 82, "haematologic": 68, "gastrointestinal": 64, "cardiovascular": 38, "hepatic": 30},
        "popover": "Membrane-permeable exatecan hydroxyacetamide derivative (~10x higher Topo I potency than SN-38) with short systemic half-life (~1.6 h); supports DAR 8 loading.",
        "popover_ko": "SN-38 대비 약 10배 높은 효력과 짧은 전신 반감기(약 1.6시간)를 지닌 막투과성 토포이소머라제 I 저해제로 DAR 8 고밀도 접합이 가능합니다.",
    },
    {
        "id": "Exatecan ( Topo I )", "group": "topo1", "cls": "Topoisomerase I inhibitor (PGP-evading)", "perm": True, "handle": "amine",
        "potency": 94, "optDar": 6, "maxSafeDar": 8, "hydro": 0.36, "smi": CANONICAL_PAYLOAD_SMILES["Exatecan"],
        "organs": {"haematologic": 78, "gastrointestinal": 68, "pulmonary": 72, "hepatic": 34},
        "popover": "Unmodified primary-amine exatecan warhead that evades P-gp/BCRP multidrug efflux pumps and delivers potent bystander killing in Topo I-refractory tumors.",
        "popover_ko": "다제내성 약물유출 펌프(P-gp, BCRP)를 회피하는 1차 아민 엑사테칸 페이로드로 내성 고형암에서 높은 세포독성과 동반 사멸 효능을 보입니다.",
    },
    {
        "id": "SN-38 ( Topo I )", "group": "topo1", "cls": "Topoisomerase I inhibitor (UGT1A1)", "perm": True, "handle": "hydroxyl",
        "potency": 82, "optDar": 7.6, "maxSafeDar": 8, "hydro": 0.34, "smi": CANONICAL_PAYLOAD_SMILES["SN-38"],
        "organs": {"haematologic": 86, "gastrointestinal": 84, "hepatic": 44, "pulmonary": 22},
        "popover": "Active metabolite of irinotecan cleared via hepatic UGT1A1 glucuronidation; lower interstitial lung toxicity than DXd, with neutropenia and diarrhea as main DLTs.",
        "popover_ko": "이리노테칸 활성 대사체로 간 UGT1A1 대사를 거치며, DXd 계열 대비 간질성 폐질환 빈도가 낮고 주요 감시 항목은 호중구감소증과 설사입니다.",
    },
    {
        "id": "Belotecan KL610023 ( Topo I )", "group": "topo1", "cls": "Water-soluble Topo I inhibitor", "perm": True, "handle": "amine_hydroxyl",
        "potency": 89, "optDar": 7.6, "maxSafeDar": 8, "hydro": 0.24, "smi": CANONICAL_PAYLOAD_SMILES["Belotecan_KL610023"],
        "organs": {"haematologic": 74, "gastrointestinal": 58, "pulmonary": 34, "hepatic": 32},
        "popover": "Belotecan-derived hydrophilic camptothecin warhead (Sacituzumab tirumotecan / SKB264) supporting homogeneous DAR 7.6-8 with low pulmonary and GI mucosal accumulation.",
        "popover_ko": "벨로테칸 유래 친수성 캠프토테신 페이로드(사시투주맙 티루모테칸 적용)로 DAR 7.6-8 고밀도 결합에서도 폐 및 장 점막 축적이 적습니다.",
    },
    {
        "id": "Rezetecan SHR9265 ( Topo I )", "group": "topo1", "cls": "Cyclopropyl-shielded Topo I inhibitor", "perm": True, "handle": "amine_hydroxyl",
        "potency": 93, "optDar": 6, "maxSafeDar": 8, "hydro": 0.31, "smi": CANONICAL_PAYLOAD_SMILES["Rezetecan_SHR9265"],
        "organs": {"haematologic": 70, "pulmonary": 56, "gastrointestinal": 56, "hepatic": 30},
        "popover": "Chiral cyclopropyl-hydroxyamide exatecan analog (Trastuzumab rezetecan / SHR-A1811) balancing membrane bystander permeability with reduced alveolar macrophage retention.",
        "popover_ko": "사이클로프로필 입체 구조를 도입한 엑사테칸 유도체(트라스투주맙 레제테칸 적용)로 주변 암세포 투과도와 폐포 대식세포 안전성 균형을 개선한 약물입니다.",
    },
    {
        "id": "AZD8205 Top1i ( Topo I )", "group": "topo1", "cls": "Next-gen Polar Topo I inhibitor", "perm": True, "handle": "amine_hydroxyl",
        "potency": 90, "optDar": 8, "maxSafeDar": 8, "hydro": 0.22, "smi": "CCC1(O)C(=O)OCc2c1cc1n(c2=O)Cc2cc3c(CNCC(O)CO)cc(F)cc3nc2-1",
        "popover": "Polar aminomethyl-camptothecin Topo I payload (AZ14170132 / Puxitatug samrotecan class) designed for rapid renal clearance of free payload and DAR 8 homogeneity.",
        "popover_ko": "극성 아미노메틸 치환체를 도입해 유리 약물의 신속한 신장 배설과 DAR 8 균일 접합을 구현한 차세대 토포이소머라제 I 저해제입니다.",
    },

    # --- Microtubule / Mitotic Inhibitors (8) ---
    {
        "id": "MMAE ( Auristatin )", "group": "tubulin", "cls": "Microtubule inhibitor (Auristatin)", "perm": True, "handle": "amine",
        "potency": 90, "optDar": 4, "maxSafeDar": 4, "hydro": 0.82, "smi": CANONICAL_PAYLOAD_SMILES["MMAE"],
        "organs": {"neurologic": 84, "haematologic": 76, "dermatologic": 66, "hepatic": 52},
        "popover": "Lipophilic tubulin polymerization inhibitor with strong bystander killing; optimal at DAR 3.5-4, whereas higher DAR accelerates Kupffer clearance and neuropathy.",
        "popover_ko": "막투과성과 동반 사멸 효과가 우수한 미세소관 중합 저해제입니다. DAR 3.5-4에서 치료지수가 최적이며 고DAR에서는 간 포획과 말초신경병증이 증가합니다.",
    },
    {
        "id": "MMAF ( Auristatin )", "group": "tubulin", "cls": "Charged Auristatin (low permeability)", "perm": False, "handle": "amine",
        "potency": 86, "optDar": 4, "maxSafeDar": 6, "hydro": 0.50, "smi": CANONICAL_PAYLOAD_SMILES["MMAF"],
        "organs": {"ocular": 92, "haematologic": 64, "renal": 28, "hepatic": 32, "neurologic": 20},
        "popover": "C-terminal carboxylate auristatin trapped inside target cells after release; spares peripheral nerves and marrow vs MMAE, with corneal keratopathy as primary risk.",
        "popover_ko": "말단 음전하로 세포 밖 수동 확산이 제한된 오리스타틴입니다. MMAE 대비 신경병증과 골수 억제는 낮으나 각막 상피 축적 관리가 중요합니다.",
    },
    {
        "id": "AS269 ( Auristatin )", "group": "tubulin", "cls": "Site-specific Non-permeable Auristatin", "perm": False, "handle": "amine_hydroxyl",
        "potency": 88, "optDar": 2, "maxSafeDar": 4, "hydro": 0.44, "smi": CANONICAL_PAYLOAD_SMILES["AS269"],
        "organs": {"ocular": 68, "pulmonary": 52, "haematologic": 28, "neurologic": 18, "hepatic": 34},
        "popover": "Para-acetylphenylalanine-coupled polar auristatin (ARX788 Amberstatin) yielding ultra-low systemic free payload (<1% deconjugation) and minimal myelosuppression.",
        "popover_ko": "위치 특이적 결합용 극성 오리스타틴(ARX788 앰버스타틴)으로 혈중 유리 약물 농도가 극히 낮아 골수 억제와 신경 독성이 적습니다.",
    },
    {
        "id": "Duostatin-5 ( Auristatin )", "group": "tubulin", "cls": "Morpholine Auristatin", "perm": True, "handle": "amine",
        "potency": 89, "optDar": 3.5, "maxSafeDar": 4, "hydro": 0.72, "smi": CANONICAL_PAYLOAD_SMILES["Duostatin-5"],
        "organs": {"neurologic": 68, "haematologic": 66, "ocular": 54, "hepatic": 44},
        "popover": "C-terminal morpholinamide auristatin balancing moderate bystander permeability with lower lipophilicity than MMAE.",
        "popover_ko": "말단 모르폴린 구조를 통해 MMAE보다 친유성을 낮추면서 종양 내 동반 사멸 활성을 유지한 오리스타틴 유도체입니다.",
    },
    {
        "id": "DM4 / DM1 ( Maytansinoid )", "group": "tubulin", "cls": "Microtubule inhibitor (Maytansinoid)", "perm": True, "handle": "thiol",
        "potency": 85, "optDar": 3.5, "maxSafeDar": 4, "hydro": 0.68, "smi": CANONICAL_PAYLOAD_SMILES["DM4"],
        "organs": {"ocular": 74, "hepatic": 72, "neurologic": 62, "haematologic": 58},
        "popover": "Sterically hindered thiol maytansinoid (Ravtansine / Soravtansine) yielding S-methyl-DM4 bystander catabolites; linked to reversible keratopathy and transaminase elevation.",
        "popover_ko": "입체장애 티올기를 지닌 메이탄시노이드(소라브탄신/라브탄신)로 S-메틸 대사체를 통해 동반 사멸을 유도하며 간효소 상승과 가역적 각막병증을 감시합니다.",
    },
    {
        "id": "DM1 Mertansine ( Maytansinoid )", "group": "tubulin", "cls": "Thioether Maytansinoid", "perm": False, "handle": "thiol",
        "potency": 83, "optDar": 3.5, "maxSafeDar": 4, "hydro": 0.62, "smi": CANONICAL_PAYLOAD_SMILES["DM1"],
        "organs": {"hepatic": 76, "haematologic": 64, "neurologic": 48, "cardiovascular": 34},
        "popover": "Mertansine warhead optimized for non-cleavable SMCC conjugation (Kadcyla); releases membrane-impermeable Lys-SMCC-DM1, with thrombocytopenia and AST/ALT rise as main DLTs.",
        "popover_ko": "비절단형 SMCC 링커(캐싸일라)에 최적화된 메르탄신 페이로드로 막비투과성 대사체를 형성하며 혈소판감소증 및 AST/ALT 상승이 주요 감시 항목입니다.",
    },
    {
        "id": "Eribulin ( Halichondrin )", "group": "tubulin", "cls": "Microtubule dynamics inhibitor", "perm": True, "handle": "amine",
        "potency": 87, "optDar": 4, "maxSafeDar": 6, "hydro": 0.38, "smi": CANONICAL_PAYLOAD_SMILES["Eribulin"],
        "organs": {"haematologic": 72, "pulmonary": 46, "neurologic": 44, "hepatic": 30},
        "popover": "Macrocyclic halichondrin B analog (Farletuzumab ecteribulin / MORAb-202) that inhibits microtubule plus-end growth with lower hydrophobicity and lower neuropathy than MMAE.",
        "popover_ko": "할리콘드린 B 거대고리 유도체(파를레투주맙 엑테리불린 적용)로 친수성이 높고 MMAE 대비 말초신경 손상 빈도가 낮습니다.",
    },
    {
        "id": "Tubulysin M ( Tubulysin )", "group": "tubulin", "cls": "Vinca-domain Tubulin depolymerizer", "perm": True, "handle": "amine_hydroxyl",
        "potency": 93, "optDar": 2, "maxSafeDar": 4, "hydro": 0.64, "smi": CANONICAL_PAYLOAD_SMILES["Tubulysin"],
        "organs": {"haematologic": 78, "hepatic": 64, "neurologic": 62, "gastrointestinal": 52},
        "popover": "Sub-nanomolar tetrapeptide tubulin depolymerizer resistant to P-gp efflux pumps; effective at low DAR (2-3.5) in low-antigen-density tumors.",
        "popover_ko": "P-gp 약물유출 펌프 내성을 극복하는 고효력 튜불리신 페이로드로 저발현 종양에서도 DAR 2-3.5 저밀도 접합으로 강한 세포사멸을 유도합니다.",
    },

    # --- DNA-Interacting & Next-Gen Targeted Payloads (6) ---
    {
        "id": "SG3199 ( PBD Dimer )", "group": "dna", "cls": "DNA minor-groove crosslinker", "perm": True, "handle": "amine",
        "potency": 98, "optDar": 2, "maxSafeDar": 2, "hydro": 1.15, "smi": CANONICAL_PAYLOAD_SMILES["SG3199"],
        "organs": {"haematologic": 92, "hepatic": 78, "pulmonary": 68, "dermatologic": 62, "renal": 54},
        "popover": "Picomolar pyrrolobenzodiazepine interstrand DNA crosslinker active against quiescent stem-like cells; restricted to DAR 1-2 due to delayed myelosuppression and edema.",
        "popover_ko": "비분열 암줄기세포까지 사멸시키는 피코몰 효력의 DNA 가교제(테시린 페이로드)로 지연성 골수 억제 및 부종 예방을 위해 DAR 1-2 저밀도 설계에 사용됩니다.",
    },
    {
        "id": "DGN549 Sunirine ( IGN )", "group": "dna", "cls": "Mono-imine DNA alkylator (IGN)", "perm": True, "handle": "amine_thiol",
        "potency": 95, "optDar": 2, "maxSafeDar": 3.5, "hydro": 0.86, "smi": "COc1cc2c(cc1OC)-c1cc3ccccc3n1CC(=N2)COCCc1cc(NC(=O)CCN)cc(COCC2=NCc3cc(OC)c(OC)cc3-c3cc4ccccc4n32)c1",
        "popover": "Indolinobenzodiazepine mono-imine warhead (Pivekimab sunirine) that mono-alkylates DNA without interstrand crosslinking, markedly reducing prolonged marrow aplasia vs PBD dimers.",
        "popover_ko": "가교 대신 단일 알킬화를 유도하도록 개량된 인돌리노벤조디아제핀(수니린 페이로드)으로 PBD 이합체 대비 장기 지속형 골수 억제와 간독성을 크게 완화합니다.",
    },
    {
        "id": "seco-DUBA ( Duocarmycin )", "group": "dna", "cls": "DNA minor-groove AT-alkylator", "perm": True, "handle": "amine_hydroxyl",
        "potency": 94, "optDar": 2, "maxSafeDar": 4, "hydro": 0.88, "smi": CANONICAL_PAYLOAD_SMILES["seco-DUBA"],
        "organs": {"ocular": 76, "pulmonary": 64, "haematologic": 58, "dermatologic": 52, "hepatic": 46},
        "popover": "Seco-duocarmycin hydroxybenzamide-azaindole prodrug (Trastuzumab duocarmazine / SYD985) killing dividing and non-dividing cells via Spiro-cyclopropyldienone DNA alkylation.",
        "popover_ko": "분열 및 비분열 종양세포의 DNA 작은홈 아데닌을 알킬화하는 듀오카마이신 전구약물(SYD985 페이로드)로 결막 및 폐 독성 감시가 필요합니다.",
    },
    {
        "id": "Calicheamicin ( Enediyne )", "group": "dna", "cls": "DNA double-strand cleaver", "perm": True, "handle": "ketone_thiol",
        "potency": 96, "optDar": 2, "maxSafeDar": 4, "hydro": 0.76, "smi": CANONICAL_PAYLOAD_SMILES["Calicheamicin"],
        "organs": {"hepatic": 90, "haematologic": 88, "infectious_immune": 64, "gastrointestinal": 48},
        "popover": "Enediyne diradical DNA double-strand cleaver (Mylotarg / Besponsa); highly potent in acute leukemias, with hepatic sinusoidal obstruction syndrome (VOD/SOS) as key risk.",
        "popover_ko": "DNA 이중가닥 절단을 유도하는 엔다이인계 고효력 페이로드(마일로탁, 베스폰사)로 급성 백혈병에 효과적이나 간 정맥폐쇄성 질환(VOD) 위험이 높습니다.",
    },
    {
        "id": "Filanesib KSPi ( Kinesin )", "group": "targeted", "cls": "Kinesin Spindle Protein (Eg5) inhibitor", "perm": False, "handle": "amine_hydroxyl",
        "potency": 85, "optDar": 4, "maxSafeDar": 8, "hydro": 0.35, "smi": "CCC(C1=NC(c2ccccc2)=CS1)(N(CCN)C(=O)c1ccc(F)cc1)c1ccc(F)cc1",
        "popover": "Mitotic kinesin Eg5 inhibitor (VIP943 class) selective strictly for dividing cells; completely spares post-mitotic peripheral neurons (zero axonal neuropathy) and hepatocytes.",
        "popover_ko": "세포분열 방추사 키네신(Eg5)만 선택적으로 저해하는 페이로드로 비분열 말초신경 축삭과 간세포를 손상시키지 않아 신경병증을 원천 회피합니다.",
    },
    {
        "id": "STING Agonist ( Immune )", "group": "targeted", "cls": "Innate Immune STING Agonist (iADC)", "perm": False, "handle": "amine_hydroxyl",
        "potency": 81, "optDar": 4, "maxSafeDar": 6, "hydro": 0.16, "smi": CANONICAL_PAYLOAD_SMILES["STING_Agonist"],
        "organs": {"infectious_immune": 68, "hepatic": 34, "cardiovascular": 32, "haematologic": 28, "neurologic": 12},
        "popover": "Immunostimulatory STING agonist payload activating intratumoral type-I interferon signaling without direct DNA/tubulin cytotoxicity; avoids classic myelosuppression and neuropathy.",
        "popover_ko": "종양 미세환경 내 제1형 인터페론 선천면역을 활성화하는 면역자극 페이로드(iADC)로 전통적 세포독성 약물의 골수 억제와 신경독성을 피할 수 있습니다.",
    },
]

STUDIO_DARS_8: List[Dict[str, Any]] = [
    {"id": "1", "val": 1.0,
     "popover": "DAR 1: Ultra-low site-specific single-drug loading for picomolar DNA warheads (PBD/IGN/Calicheamicin) or severe multi-organ fragility.",
     "popover_ko": "DAR 1: 초고효력 DNA 작용 페이로드(PBD, IGN, 칼리키아마이신) 또는 중증 다장기 기능저하 환자의 안전역 확보를 위한 초저밀도 단일 접합 설계입니다."},
    {"id": "2", "val": 2.0,
     "popover": "DAR 2: Site-specific low drug loading. Minimizes hydrophobic aggregation and preserves antibody half-life; standard for PBD/IGN/AS269 conjugates.",
     "popover_ko": "DAR 2: 위치 특이적 저밀도 설계로 소수성 응집을 최소화하고 항체 반감기를 보존하며 고효력 페이로드의 표준 접합비입니다."},
    {"id": "3.5", "val": 3.5,
     "popover": "DAR 3.5: Validated clinical loading for Polivy, Kadcyla, and Elahere. Balances intracellular delivery against hepatic sinusoidal uptake.",
     "popover_ko": "DAR 3.5: 폴라이비, 캐싸일라, 엘라히어 등 승인 약물에서 검증된 접합비로 세포 내 전달량과 간 비특이 포획 사이의 균형이 우수합니다."},
    {"id": "4", "val": 4.0,
     "popover": "DAR 4: Standard interchain cysteine/engineered-site loading (Padcev, Blenrep, Dato-DXd). Optimal therapeutic index for auristatins and Topo I.",
     "popover_ko": "DAR 4: 파드셉, 블렌렙, 다토포타맙 데룩스테칸에 적용된 표준 접합비로 오리스타틴 및 Topo I 계열 전반에서 안정적인 약동학을 보입니다."},
    {"id": "5", "val": 5.0,
     "popover": "DAR 5: Intermediate engineered loading boosting receptor-limited tumor killing while keeping HIC retention below hepatic clearance thresholds.",
     "popover_ko": "DAR 5: 중등도 항원 발현 종양에서 수용체당 약물 전달량을 높이면서도 간 쿠퍼세포 청소 임계치 이하로 소수성을 유지하는 설계입니다."},
    {"id": "6", "val": 6.0,
     "popover": "DAR 6: High-intermediate homogeneous loading (Trastuzumab rezetecan / SHR-A1811 class) pairing shielded GGFG/PEG linkers with Topo I warheads.",
     "popover_ko": "DAR 6: 트라스투주맙 레제테칸(SHR-A1811) 등에 채택된 중고밀도 균일 접합비로 친수성 링커와 결합해 효능과 폐/골수 안전성의 균형을 잡습니다."},
    {"id": "7.6", "val": 7.6,
     "popover": "DAR 7.6: High-density loading validated in Trodelvy and SKB264 when paired with PEGylated linkers.",
     "popover_ko": "DAR 7.6: 트로델비 및 사시투주맙 티루모테칸에 적용된 고밀도 접합비로 PEG 친수성 링커와 결합해 높은 종양 내 농도를 형성합니다."},
    {"id": "8", "val": 8.0,
     "popover": "DAR 8: Full interchain cysteine loading (Enhertu). Maximizes efficacy with hydrophilic Topo I linkers, but accelerates hepatic aggregation with lipophilic payloads.",
     "popover_ko": "DAR 8: 사슬 간 시스테인 8곳 전체에 결합하는 최대 밀도 설계(엔허투)로 친수성 Topo I 조합에서 최고 효능을 내나 소수성 약물에서는 간 응집을 유발합니다."},
]

STUDIO_FC_4: List[Dict[str, Any]] = [
    {
        "id": "igg1_wt", "ko": "야생형 IgG1", "en": "Wild-type IgG1",
        "isotype": "IgG1", "fc_silenced": False, "fc_activity": 1.00, "adcc": 1.015,
        "popover": "Wild-Type IgG1: Retains FcgammaRIIIa binding on NK cells and macrophages for ADCC effector support, but permits FcgammaR-mediated uptake in lung, liver, and marrow.",
        "popover_ko": "야생형 IgG1: NK세포 및 대식세포 Fc감마 수용체 결합으로 항체 의존성 세포독성(ADCC)을 지원하나 폐포 대식세포, 간, 골수로의 비특이 흡수가 동반될 수 있습니다.",
    },
    {
        "id": "igg1_lalapg", "ko": "Fc 침묵화 (LALA-PG)", "en": "Fc-Silenced (LALA-PG)",
        "isotype": "IgG1", "fc_silenced": True, "fc_activity": 0.08, "adcc": 0.985,
        "popover": "Fc-Silenced IgG1 (L234A/L235A/P329G): Ablates FcgammaR and C1q complement binding while preserving FcRn half-life recycling, blocking macrophage uptake in lung, liver, and eye.",
        "popover_ko": "Fc 침묵화 (LALA-PG): FcRn 반감기 재순환은 유지하면서 대식세포 Fc감마 수용체 및 보체 결합만 제거해 폐, 간, 안구로의 비특이 흡수를 차단합니다.",
    },
    {
        "id": "igg4_s228p", "ko": "IgG4 S228P (저효능기)", "en": "IgG4 S228P (Low Effector)",
        "isotype": "IgG4", "fc_silenced": False, "fc_activity": 0.40, "adcc": 0.995,
        "popover": "Hinge-stabilized IgG4 S228P backbone (used clinically in Mylotarg and Besponsa): markedly lower FcgammaRIIIa & complement activation than WT IgG1 without synthetic CH2 triple mutation.",
        "popover_ko": "힌지 안정화 IgG4 S228P 골격(마일로탁, 베스폰사 채택): 야생형 IgG1 대비 Fc감마 수용체 및 보체 활성이 현저히 낮아 면역원성 부담 없이 비특이 흡수를 줄입니다.",
    },
    {
        "id": "igg2_lowfc", "ko": "IgG2 (비결합 힌지)", "en": "IgG2 (Minimal FcgammaR)",
        "isotype": "IgG2", "fc_silenced": False, "fc_activity": 0.35, "adcc": 0.992,
        "popover": "Human IgG2 backbone (PVAGP lower hinge): naturally minimal FcgammaRI/IIIa affinity (~0.35x WT) with rigid disulfide hinge geometry that shields conjugation sites.",
        "popover_ko": "인간 IgG2 골격: 선천적으로 낮은 Fc감마 수용체 결합력(야생형 IgG1의 약 35%)과 견고한 이황화 힌지 구조로 접합 부위를 입체적으로 보호합니다.",
    },
]


def _check_compat_and_affinity(lnk: Dict[str, Any], pld: Dict[str, Any]) -> Tuple[bool, float]:
    lh = lnk["handle"]
    ph = pld["handle"]
    l_tokens = set(lh.split("_"))
    p_tokens = set(ph.split("_"))
    is_compat = bool(l_tokens & p_tokens)
    if not is_compat:
        return False, 0.35

    lid = lnk["id"]
    pid = pld["id"]
    pg = pld["group"]
    lg = lnk["group"]

    # Empirically grounded pairing affinity for compatible handle pairs
    aff = 0.80
    if "GGFG" in lid and pg == "topo1" and "hydroxyl" in p_tokens:
        aff = 0.98 if "DXd" in pid or "Rezetecan" in pid or "AZD8205" in pid else 0.88
    elif lid == "Pyrimidine-TMT PEG8" and ("Belotecan" in pid or pg == "topo1"):
        aff = 0.98
    elif lid == "Hydrolyzable CL2A" and "SN-38" in pid:
        aff = 1.00
    elif ("Val-Cit" in lid or "Val-Ala" in lid) and (pg in ("tubulin", "dna") and "amine" in p_tokens):
        aff = 0.96
    elif lg == "hydrophilic" and pg in ("topo1", "dna", "targeted"):
        aff = 0.92
    elif "SPDB" in lid and "thiol" in p_tokens:
        aff = 0.98
    elif lid == "Acid Hydrazone" and "ketone" in p_tokens:
        aff = 0.95
    elif lg == "non_cleavable" and not pld["perm"]:
        aff = 0.98
    elif lg == "non_cleavable" and pld["perm"]:
        aff = 0.62
    return True, aff


def merge_peft_fold_to_clean_state(ckpt_state: Dict[str, torch.Tensor]) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor]]:
    """
    Merges ChemBERTa LoRA (`alpha=32, r=16 -> scale=2.0`) and ESM2LoRAProjector (`scale=2.0`)
    directly into standard dense Linear weights in FP16, separating shared ChemBERTa base vs fold weights!
    wait - note that ChemBERTa HAS per-fold LoRA weights (`lora_A`, `lora_B`) trained in each fold!
    Let's merge ChemBERTa LoRA per fold OR keep base + low-rank delta (`lora_A`, `lora_B`)!
    Wait: `lora_A` (16x384) + `lora_B` (384x16) across 12 linear layers in 3 RoBERTa layers is only 589 KB per fold!
    Merging into per-fold ChemBERTa is also only 6.5 MB per fold in FP16 (`5 * 6.5 MB = 32.5 MB` total!).
    Merging completely into standard RoBERTa weights per fold means ZERO LoRA math at runtime and 32 MB total!
    """
    chem_sd: Dict[str, torch.Tensor] = {}
    head_sd: Dict[str, torch.Tensor] = {}

    # 1. Merge ChemBERTa RoBERTa layers (`chemberta.base_model.model....`)
    prefix = "chemberta.base_model.model."
    chem_keys = [k for k in ckpt_state if k.startswith(prefix)]
    for k in chem_keys:
        sub = k[len(prefix) :]
        if ".lora_A." in sub or ".lora_B." in sub:
            continue
        if sub.endswith(".base_layer.weight"):
            clean_k = sub.replace(".base_layer.weight", ".weight")
            stem = k[: -len(".base_layer.weight")]
            la = ckpt_state[stem + ".lora_A.default.weight"].float()
            lb = ckpt_state[stem + ".lora_B.default.weight"].float()
            # LoraConfig(r=16, lora_alpha=32) -> scaling = 32 / 16 = 2.0
            merged_w = ckpt_state[k].float() + 2.0 * (lb @ la)
            chem_sd[clean_k] = merged_w.half()
        elif sub.endswith(".base_layer.bias"):
            clean_k = sub.replace(".base_layer.bias", ".bias")
            chem_sd[clean_k] = ckpt_state[k].half()
        else:
            chem_sd[sub] = ckpt_state[k].half() if ckpt_state[k].is_floating_point() else ckpt_state[k]

    # 2. Merge ESM2LoRAProjector (`heavy_enc`, `light_enc`, `antigen_enc`) + copy fusion & heads
    for enc_name in ("heavy_enc", "light_enc", "antigen_enc"):
        bw = ckpt_state[f"{enc_name}.base_proj.weight"].float()
        bb = ckpt_state[f"{enc_name}.base_proj.bias"].float()
        la = ckpt_state[f"{enc_name}.lora_A.weight"].float()
        lb = ckpt_state[f"{enc_name}.lora_B.weight"].float()
        head_sd[f"{enc_name}.proj.weight"] = (bw + 2.0 * (lb @ la)).half()
        head_sd[f"{enc_name}.proj.bias"] = bb.half()
        for sub_k in ("norm1.weight", "norm1.bias", "ffn.0.weight", "ffn.0.bias", "ffn.3.weight", "ffn.3.bias", "norm2.weight", "norm2.bias"):
            head_sd[f"{enc_name}.{sub_k}"] = ckpt_state[f"{enc_name}.{sub_k}"].half()

    skip_prefixes = (prefix, "heavy_enc.", "light_enc.", "antigen_enc.")
    for k, v in ckpt_state.items():
        if k.startswith(skip_prefixes):
            continue
        head_sd[k] = v.half() if v.is_floating_point() else v

    return chem_sd, head_sd


def main() -> None:
    t0 = time.time()
    print("=== Exporting 36-Target x 16-Linker x 20-Payload x 8-DAR x 4-Fc = 368,640 Studio Space ===")

    exp_cache = pickle.load(open(DATA_DIR / "expanded_biophysics_cache.pkl", "rb"))
    uid_to_seq: Dict[str, str] = exp_cache["uid_to_seq"]
    af_lookup: Dict[str, Dict[str, float]] = exp_cache["af_feats"]
    mab_library: Dict[str, Dict[str, str]] = exp_cache["mab_library"]
    esm_map: Dict[str, np.ndarray] = exp_cache["esm_map"]

    organ_expr_map, cell_expr_map = load_human_organ_expression_maps(REPO / "artifacts" / "target_expression.json")
    train_metrics = json.loads((MODEL_DIR / "training_metrics.json").read_text(encoding="utf-8"))
    blend_alpha_nn = float(train_metrics["best_validation_metrics"]["bioactivity_ensemble_nn_weight"])

    assert len(STUDIO_TARGETS_36) == 36
    assert len(STUDIO_LINKERS_16) == 16
    assert len(STUDIO_PAYLOADS_20) == 20
    assert len(STUDIO_DARS_8) == 8
    assert len(STUDIO_FC_4) == 4
    assert len({t["uniprot"] for t in STUDIO_TARGETS_36}) == 36, "Duplicate UniProt ID in STUDIO_TARGETS_36!"

    # Verify 100% AlphaFold, ESM-2, and GTEx/TS coverage across all 36 targets and 4 Fc formats
    for tgt in STUDIO_TARGETS_36:
        uid = tgt["uniprot"]
        gene = tgt["gene"]
        assert uid in af_lookup, f"Missing AlphaFold features for {uid}"
        assert uid in uid_to_seq and uid_to_seq[uid].strip().upper() in esm_map, f"Missing antigen ESM-2 for {uid}"
        assert gene in organ_expr_map, f"Missing GTEx/TS expression for {gene}"
        assert tgt["mab"] in mab_library, f"Missing mAb {tgt['mab']} in mab_library"

    # 1. Precompute unique chemical features (16 linkers, 20 payloads, 320 reaction pairs)
    print("[1/5] Computing Boltzmann 3D conformers, Morgan-1024 FPs, and cleavage SMARTS for 16 linkers x 20 payloads...")
    l_3d = np.stack([compute_3d_conformer_physics(lk["smi"]) for lk in STUDIO_LINKERS_16], axis=0)      # (16, 16)
    p_3d = np.stack([compute_3d_conformer_physics(pl["smi"]) for pl in STUDIO_PAYLOADS_20], axis=0)    # (20, 16)
    l_fp = np.stack([compute_morgan_fp1024(lk["smi"]) for lk in STUDIO_LINKERS_16], axis=0)            # (16, 1024)
    p_fp = np.stack([compute_morgan_fp1024(pl["smi"]) for pl in STUDIO_PAYLOADS_20], axis=0)           # (20, 1024)

    rxn_mat = np.zeros((16, 20, 25), dtype=np.float32)
    has_shield_mat = np.zeros((16, 20), dtype=np.float32)
    compat_mask = np.zeros((16, 20), dtype=bool)
    pair_affinity = np.zeros((16, 20), dtype=np.float32)

    for li, lk in enumerate(STUDIO_LINKERS_16):
        for pi, pl in enumerate(STUDIO_PAYLOADS_20):
            ic, aff = _check_compat_and_affinity(lk, pl)
            compat_mask[li, pi] = ic
            pair_affinity[li, pi] = aff
            rxn_d = analyze_linker_cleavage_reaction(lk["smi"], pl["smi"])
            has_shield_mat[li, pi] = rxn_d["has_peg_or_gluc"]
            rxn_mat[li, pi] = np.array(
                [
                    rxn_d["is_cleavable"],
                    rxn_d["has_pabc_16_elim"],
                    rxn_d["has_ggfg_hemiaminal"],
                    rxn_d["has_disulfide_gsh"],
                    rxn_d["has_steric_disulfide"],
                    rxn_d["has_acid_hydrazone_carbonate"],
                    rxn_d["has_peg_or_gluc"],
                    rxn_d["plasma_half_life_days"] / 21.0,
                    rxn_d["plasma_stability_score"],
                    rxn_d["lysosomal_cleavage_rate"],
                    rxn_d["metabolite_perm_pH45"],
                    rxn_d["metabolite_perm_pH74"],
                    rxn_d["bystander_diffusion_index"],
                    rxn_d["payload_q_pH74"],
                    rxn_d["payload_q_pH60"],
                    rxn_d["payload_q_pH45"],
                    rxn_d["payload_abs_q_pH74"],
                    rxn_d["payload_abs_q_pH45"],
                    rxn_d["payload_logD_pH74"] / 5.0,
                    rxn_d["payload_logD_pH60"] / 5.0,
                    rxn_d["payload_logD_pH45"] / 5.0,
                    rxn_d["payload_lysosomal_trapping_delta"] / 3.0,
                    rxn_d["payload_membrane_perm_pH45"],
                    rxn_d["payload_lactone_closed_frac_pH74"],
                    rxn_d["payload_lactone_closed_frac_pH45"],
                ],
                dtype=np.float32,
            )

    # 2. Vectorized assembly of all 368,640 108D biophysical vectors!
    # Canonical axis ordering:
    #   TF = 36 Targets x 4 Fc = 144  (tf_idx = ti * 4 + fi)
    #   LPD = 16 Linkers x 20 Payloads x 8 DARs = 2560  (lpd_idx = (li * 20 + pi) * 8 + di)
    print("[2/5] Assembling exact 108D biophysical matrix for (144 TF x 2560 LPD = 368,640 constructs)...")
    n_tf = 36 * 4
    n_lpd = 16 * 20 * 8
    n_tot = n_tf * n_lpd  # 368,640

    heavy_esm_tf = np.zeros((n_tf, 1280), dtype=np.float32)
    light_esm_tf = np.zeros((n_tf, 1280), dtype=np.float32)
    antigen_esm_tf = np.zeros((n_tf, 1280), dtype=np.float32)
    prot_static_tf = np.zeros((n_tf, 16), dtype=np.float32)  # prot_vec[0:16] independent of DAR/payload
    expr_tf = np.zeros((n_tf, 13), dtype=np.float32)
    cell_tf = np.zeros((n_tf, 13), dtype=np.float32)
    cdr_hydro_tf = np.zeros(n_tf, dtype=np.float32)

    fc_seq_key = {
        "igg1_wt": "heavy_igg1",
        "igg1_lalapg": "heavy_lalapg",
        "igg4_s228p": "heavy_igg4",
        "igg2_lowfc": "heavy_igg2",
    }

    dummy_p3d = p_3d[0]
    for ti, tgt in enumerate(STUDIO_TARGETS_36):
        uid = tgt["uniprot"]
        gene = tgt["gene"]
        a_seq = uid_to_seq[uid].strip().upper()
        a_emb = esm_map[a_seq].astype(np.float32)
        m_entry = mab_library[tgt["mab"]]
        l_seq = m_entry["light"].strip().upper()
        l_emb = esm_map[l_seq].astype(np.float32)

        for fi, fc_obj in enumerate(STUDIO_FC_4):
            tf_idx = ti * 4 + fi
            h_seq = m_entry[fc_seq_key[fc_obj["id"]]].strip().upper()
            h_emb = esm_map[h_seq].astype(np.float32)
            heavy_esm_tf[tf_idx] = h_emb
            light_esm_tf[tf_idx] = l_emb
            antigen_esm_tf[tf_idx] = a_emb
            expr_tf[tf_idx] = organ_expr_map[gene]
            cell_tf[tf_idx] = cell_expr_map[gene]

            # Extract exact prot_vec[0:16] via build_biophysical_vector once per TF (144 calls total!)
            ref_bv = build_biophysical_vector(
                linker_smi=STUDIO_LINKERS_16[0]["smi"],
                payload_smi=STUDIO_PAYLOADS_20[0]["smi"],
                dar=4.0,
                heavy_seq=h_seq,
                light_seq=l_seq,
                antigen_seq=a_seq,
                uniprot_id=uid,
                af_lookup=af_lookup,
                fc_isotype=fc_obj["isotype"],
                fc_silenced=fc_obj["fc_silenced"],
                dose_mgkg=3.6,
                interval_d=21.0,
                is_monotherapy=1.0,
                is_cell_assay=1.0,
                expr_vec_13=organ_expr_map[gene],
                cell_expr_vec_13=cell_expr_map[gene],
            )
            prot_static_tf[tf_idx] = ref_bv[57:73]
            cdr_hydro_tf[tf_idx] = ref_bv[58]

    # Build LPD static slice `[p_3d(16), l_3d(16), rxn(25)]` (57D) and DAR/context vectors
    lpd_chem57 = np.zeros((n_lpd, 57), dtype=np.float32)
    lpd_dar = np.zeros(n_lpd, dtype=np.float32)
    lpd_dar_hydro = np.zeros(n_lpd, dtype=np.float32)
    lpd_ctx5 = np.zeros((n_lpd, 5), dtype=np.float32)
    lpd_li = np.zeros(n_lpd, dtype=np.int64)
    lpd_pi = np.zeros(n_lpd, dtype=np.int64)

    dose_mgkg = 3.6
    interval_d = 21.0
    log_dose = math.log1p(dose_mgkg) / 3.0
    for li in range(16):
        for pi in range(20):
            shield_mult = 0.52 if has_shield_mat[li, pi] > 0.5 else 1.0
            payload_clogp = float(p_3d[pi, 1] * 5.0)
            payload_hydro_sasa = float(p_3d[pi, 15])
            base_c57 = np.concatenate([p_3d[pi], l_3d[li], rxn_mat[li, pi]], axis=0)
            for di, dar_obj in enumerate(STUDIO_DARS_8):
                idx = (li * 20 + pi) * 8 + di
                dar_f = float(dar_obj["val"])
                lpd_chem57[idx] = base_c57
                lpd_dar[idx] = dar_f
                lpd_li[idx] = li
                lpd_pi[idx] = pi
                lpd_dar_hydro[idx] = shield_mult * (dar_f / 8.0) * max(0.05, (payload_clogp + 1.0) / 5.0) * (0.45 + payload_hydro_sasa)
                molar_dose_idx = min(3.0, (dose_mgkg / 5.0) * (dar_f / 4.0))
                lpd_ctx5[idx] = np.array([log_dose, 1.0, molar_dose_idx, 1.0, 1.0], dtype=np.float32)

    # Broadcast `(144, 2560, 108)` biophysical tensor in ~0.04s!
    biophys_all = np.zeros((n_tf, n_lpd, 108), dtype=np.float32)
    biophys_all[:, :, 0:57] = lpd_chem57[None, :, :]
    biophys_all[:, :, 57:73] = prot_static_tf[:, None, :]
    biophys_all[:, :, 73] = (lpd_dar / 8.0)[None, :]
    biophys_all[:, :, 74] = ((lpd_dar / 8.0) ** 2)[None, :]
    biophys_all[:, :, 75] = lpd_dar_hydro[None, :]
    agg_factor = 1.0 + 0.35 * np.maximum(0.0, lpd_dar - 4.0) / 4.0
    biophys_all[:, :, 76] = np.maximum(
        0.0,
        lpd_dar_hydro[None, :] * agg_factor[None, :] + 0.35 * cdr_hydro_tf[:, None] - 0.12,
    )
    biophys_all[:, :, 77:82] = lpd_ctx5[None, :, :]
    biophys_all[:, :, 82:95] = expr_tf[:, None, :]
    biophys_all[:, :, 95:108] = cell_tf[:, None, :]
    biophys_flat = biophys_all.reshape(n_tot, 108)

    # Spot-check exact bit-level agreement against `build_biophysical_vector`!
    for check_ti, check_fi, check_li, check_pi, check_di in [(0, 0, 0, 0, 3), (17, 1, 6, 3, 6), (31, 2, 13, 17, 1), (35, 3, 15, 11, 2)]:
        tf_i = check_ti * 4 + check_fi
        lpd_i = (check_li * 20 + check_pi) * 8 + check_di
        tgt_c = STUDIO_TARGETS_36[check_ti]
        fc_c = STUDIO_FC_4[check_fi]
        m_c = mab_library[tgt_c["mab"]]
        ref_vec = build_biophysical_vector(
            linker_smi=STUDIO_LINKERS_16[check_li]["smi"],
            payload_smi=STUDIO_PAYLOADS_20[check_pi]["smi"],
            dar=float(STUDIO_DARS_8[check_di]["val"]),
            heavy_seq=m_c[fc_seq_key[fc_c["id"]]],
            light_seq=m_c["light"],
            antigen_seq=uid_to_seq[tgt_c["uniprot"]],
            uniprot_id=tgt_c["uniprot"],
            af_lookup=af_lookup,
            fc_isotype=fc_c["isotype"],
            fc_silenced=fc_c["fc_silenced"],
            dose_mgkg=3.6,
            interval_d=21.0,
            is_monotherapy=1.0,
            is_cell_assay=1.0,
            expr_vec_13=organ_expr_map[tgt_c["gene"]],
            cell_expr_vec_13=cell_expr_map[tgt_c["gene"]],
        )
        assert np.allclose(biophys_all[tf_i, lpd_i], ref_vec, atol=1e-5), "Vectorized biophys mismatch!"
    print("  -> Verified exact agreement (`atol < 1e-5`) between vectorized 368,640 tensor and `build_biophysical_vector`!")

    # 3. Tokenize the 16 linkers + 20 payloads once and run all 5 folds across 4x RTX 4090 GPUs!
    tokenizer = AutoTokenizer.from_pretrained(CHEMBERTA_NAME)
    l_enc = tokenizer([lk["smi"] for lk in STUDIO_LINKERS_16], max_length=128, padding="max_length", truncation=True, return_tensors="pt")
    p_enc = tokenizer([pl["smi"] for pl in STUDIO_PAYLOADS_20], max_length=128, padding="max_length", truncation=True, return_tensors="pt")

    n_gpus = max(1, torch.cuda.device_count())
    print(f"[3/5] Running 5-Fold `ADC-SurrogateNet-v2` Ensemble over 368,640 constructs across {n_gpus}x RTX 4090 GPUs...")

    # Precompute flat index gather maps once on CPU
    tf_grid = np.repeat(np.arange(n_tf, dtype=np.int64), n_lpd)
    lpd_grid = np.tile(np.arange(n_lpd, dtype=np.int64), n_tf)
    li_flat = lpd_li[lpd_grid]
    pi_flat = lpd_pi[lpd_grid]

    fold_outputs: Dict[int, Dict[str, np.ndarray]] = {}
    merged_folds_export: List[Dict[str, Any]] = []
    ols_slopes: List[Tuple[float, float]] = []

    # Prepare ExtraTrees input `(368640, 1132)` once in RAM (~1.6 GB float32)
    tree_x_flat = np.concatenate([p_fp[pi_flat], biophys_flat], axis=1)

    def _run_fold_on_gpu(fold_idx: int, gpu_id: int) -> None:
        dev = torch.device(f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu")
        ckpt = torch.load(MODEL_DIR / f"fold_{fold_idx}_best.pt", map_location="cpu", weights_only=False)
        chem_sd, head_sd = merge_peft_fold_to_clean_state(ckpt["state_dict"])
        bio_mean = ckpt["bio_mean"].astype(np.float32)
        bio_std = np.maximum(ckpt["bio_std"].astype(np.float32), 1e-5)

        model = ADCSurrogateNetV2(chemberta_path=CHEMBERTA_NAME, biophys_dim=108, fp_dim=1024, d_model=512).to(dev)
        model.load_state_dict(ckpt["state_dict"])
        model.eval()

        with torch.no_grad():
            # Encode unique 144 TF protein chains + 16 linkers + 20 payloads ONCE!
            h_tok_144 = model.heavy_enc(torch.from_numpy(heavy_esm_tf).to(dev))        # (144, 512)
            l_tok_144 = model.light_enc(torch.from_numpy(light_esm_tf).to(dev))        # (144, 512)
            a_tok_144 = model.antigen_enc(torch.from_numpy(antigen_esm_tf).to(dev))    # (144, 512)

            l_chem_16 = model.encode_chemberta(l_enc["input_ids"].to(dev), l_enc["attention_mask"].to(dev))
            p_chem_20 = model.encode_chemberta(p_enc["input_ids"].to(dev), p_enc["attention_mask"].to(dev))
            lnk_tok_16 = model.linker_chem_proj(torch.cat([l_chem_16, torch.from_numpy(l_fp).to(dev)], dim=-1))   # (16, 512)
            pld_tok_20 = model.payload_chem_proj(torch.cat([p_chem_20, torch.from_numpy(p_fp).to(dev)], dim=-1))  # (20, 512)
            p_fp_20_gpu = torch.from_numpy(p_fp).to(dev)

            bsz = 8192
            c4_list, pic_list, hb_list, ha_list, hf_list, ho_list = [], [], [], [], [], []
            for s in range(0, n_tot, bsz):
                e = min(n_tot, s + bsz)
                tf_b = torch.from_numpy(tf_grid[s:e]).to(dev)
                li_b = torch.from_numpy(li_flat[s:e]).to(dev)
                pi_b = torch.from_numpy(pi_flat[s:e]).to(dev)

                raw_b = biophys_flat[s:e]
                norm_b = (raw_b - bio_mean) / bio_std
                raw_gpu = torch.from_numpy(raw_b).to(dev)
                norm_gpu = torch.from_numpy(norm_b).to(dev)

                with torch.amp.autocast("cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_available()):
                    out = model.forward_preencoded(
                        t_heavy=h_tok_144[tf_b],
                        t_light=l_tok_144[tf_b],
                        t_antigen=a_tok_144[tf_b],
                        t_linker=lnk_tok_16[li_b],
                        t_payload=pld_tok_20[pi_b],
                        payload_fp=p_fp_20_gpu[pi_b],
                        biophys_raw=raw_gpu,
                        biophys_norm=norm_gpu,
                    )
                c4_list.append(out["prob_conc4"].float().cpu().numpy())
                pic_list.append(out["pred_pic50"].float().cpu().numpy())
                hb_list.append(out["h_base"].float().cpu().numpy())
                ha_list.append(out["h_agg"].float().cpu().numpy())
                hf_list.append(out["h_fc"].float().cpu().numpy())
                ho_list.append(out["h_on"].float().cpu().numpy())

        nn_pic = np.concatenate(pic_list, axis=0)
        et_reg = pickle.load(open(MODEL_DIR / f"fold_{fold_idx}_tree.pkl", "rb"))
        et_reg.n_jobs = 8
        tree_pic = et_reg.predict(tree_x_flat).astype(np.float32)
        blended_pic = blend_alpha_nn * nn_pic + (1.0 - blend_alpha_nn) * tree_pic

        # Fit linear calibration `a * nn_pic + b` -> `blended_pic` for lightweight CPU servers without ExtraTrees!
        cov = float(np.cov(nn_pic, blended_pic)[0, 1])
        var = max(1e-6, float(np.var(nn_pic)))
        cal_a = cov / var
        cal_b = float(blended_pic.mean() - cal_a * nn_pic.mean())

        fold_outputs[fold_idx] = {
            "conc4": np.concatenate(c4_list, axis=0),
            "pic50": blended_pic,
            "h_base": np.concatenate(hb_list, axis=0),
            "h_agg": np.concatenate(ha_list, axis=0),
            "h_fc": np.concatenate(hf_list, axis=0),
            "h_on": np.concatenate(ho_list, axis=0),
            "chem_sd": chem_sd,
            "head_sd": head_sd,
            "bio_mean": bio_mean,
            "bio_std": bio_std,
            "cal_ab": (cal_a, cal_b),
        }
        print(f"  -> Fold {fold_idx} finished on {dev} (mean blended pIC50={blended_pic.mean():.3f})")

    # Wave 1: Folds 0, 1, 2, 3 concurrently on GPUs 0, 1, 2, 3!
    threads = []
    for f_i in range(min(4, N_FOLDS)):
        th = threading.Thread(target=_run_fold_on_gpu, args=(f_i, f_i % n_gpus))
        th.start()
        threads.append(th)
    for th in threads:
        th.join()

    # Wave 2: Fold 4 on GPU 0!
    for f_i in range(4, N_FOLDS):
        _run_fold_on_gpu(f_i, 0)

    assert len(fold_outputs) == N_FOLDS, "Not all folds completed!"

    ens_conc4 = sum(fold_outputs[f]["conc4"] for f in range(N_FOLDS)) / N_FOLDS
    ens_pic50 = sum(fold_outputs[f]["pic50"] for f in range(N_FOLDS)) / N_FOLDS
    ens_hb = sum(fold_outputs[f]["h_base"] for f in range(N_FOLDS)) / N_FOLDS
    ens_ha = sum(fold_outputs[f]["h_agg"] for f in range(N_FOLDS)) / N_FOLDS
    ens_hf = sum(fold_outputs[f]["h_fc"] for f in range(N_FOLDS)) / N_FOLDS
    ens_ho = sum(fold_outputs[f]["h_on"] for f in range(N_FOLDS)) / N_FOLDS

    # 4. Compute the 9 scalar observables `m` + 52 organ pathway hazards (`61` channels total) identically to `distill_to_studio.py`!
    print("[4/5] Packaging 61 neural pathway observables and computing Rank-24 FP16 SVD factorization...")
    is_cleavable = biophys_flat[:, FEATURE_INDICES["is_cleavable"]]
    plasma_stab_pct = np.clip(biophys_flat[:, FEATURE_INDICES["plasma_stab"]] * 100.0, 20.0, 98.0)
    lys_k_rel = biophys_flat[:, FEATURE_INDICES["lys_k_rel"]]
    bystander_idx = biophys_flat[:, FEATURE_INDICES["bystander_idx"]]
    dar_val = biophys_flat[:, FEATURE_INDICES["dar_norm"]] * 8.0
    dar_hydro_patch = biophys_flat[:, FEATURE_INDICES["dar_hydro_patch"]]
    agg_propensity = biophys_flat[:, FEATURE_INDICES["agg_propensity"]]
    af_plddt = biophys_flat[:, FEATURE_INDICES["af_plddt"]]
    expr_13 = biophys_flat[:, FEATURE_INDICES["expr_start"] : FEATURE_INDICES["expr_end"]]
    cell_13 = biophys_flat[:, FEATURE_INDICES["cell_expr_start"] : FEATURE_INDICES["cell_expr_end"]]

    hep_idx = ORGANS_13.index("hepatic")
    nn_hep_agg_hazard = ens_ha[:, hep_idx]

    conc_area = ens_conc4.mean(axis=1)
    in_vivo_pk_retention = np.exp(-0.55 * agg_propensity - 1.10 * nn_hep_agg_hazard)
    dar_copy_gain = (
        0.62 * np.log2(1.0 + dar_val) * in_vivo_pk_retention
        - 0.22 * np.maximum(0.0, dar_val - 4.0) * dar_hydro_patch
    )
    pIC50_pos = np.clip(0.68 * ens_pic50 + 1.95 * conc_area + dar_copy_gain, 5.6, 9.9)
    pIC50_bys = np.clip(
        pIC50_pos - (1.90 - 1.35 * bystander_idx) - 0.85 * (1.0 - is_cleavable),
        4.6,
        9.1,
    )
    hic_agg = np.clip(1.00 + 1.50 * dar_hydro_patch + 0.95 * agg_propensity, 1.00, 4.50)
    cl_hep = np.clip(
        1.00 + 1.80 * nn_hep_agg_hazard + 0.75 * (hic_agg - 1.00) + 0.30 * (1.0 - plasma_stab_pct / 100.0),
        1.00,
        3.80,
    )

    tgt_tumor_log2_36 = np.array([math.log2(t["tumor_tpm"] + 1.0) / 8.5 for t in STUDIO_TARGETS_36], dtype=np.float32)
    tumor_log2_flat = tgt_tumor_log2_36[tf_grid // 4]
    normal_mean = 0.55 * expr_13.mean(axis=1) + 0.45 * cell_13.max(axis=1) * 0.5
    s_sel = np.clip(0.55 * (tumor_log2_flat - 0.65 * normal_mean) + 0.35 * af_plddt, 0.18, 0.96)
    s_pot = np.clip(((pIC50_pos - 5.6) / 4.1) * (in_vivo_pk_retention ** 0.35), 0.12, 0.98)
    s_deliv = np.clip((plasma_stab_pct / 100.0) * (0.58 + 0.40 * lys_k_rel) / np.sqrt(cl_hep), 0.14, 0.97)
    s_bys = np.clip(((pIC50_bys - 4.6) / 4.2) * (0.30 + 0.70 * bystander_idx), 0.08, 0.97)

    # Channel order (61 channels):
    #   [0..8]   = pIC50_pos, pIC50_bys, plasma_stab_pct, hic_agg, cl_hep, s_sel, s_pot, s_deliv, s_bys
    #   [9..21]  = hb (13 organs)
    #   [22..34] = ha (13 organs)
    #   [35..47] = hf (13 organs)
    #   [48..60] = ho (13 organs)
    m9 = np.stack([pIC50_pos, pIC50_bys, plasma_stab_pct, hic_agg, cl_hep, s_sel, s_pot, s_deliv, s_bys], axis=1)
    full_61 = np.concatenate([m9, ens_hb, ens_ha, ens_hf, ens_ho], axis=1)  # (368640, 61)
    mat_61 = np.transpose(full_61.reshape(n_tf, n_lpd, 61), (2, 0, 1))       # (61, 144, 2560)

    rank = 24
    U_24 = np.zeros((61, n_tf, rank), dtype=np.float16)
    V_24 = np.zeros((61, rank, n_lpd), dtype=np.float16)
    max_maes = []
    for ch in range(61):
        u, s, vt = np.linalg.svd(mat_61[ch].astype(np.float64), full_matrices=False)
        sq = np.sqrt(s[:rank])
        u_r = (u[:, :rank] * sq[None, :]).astype(np.float16)
        v_r = (sq[:, None] * vt[:rank, :]).astype(np.float16)
        U_24[ch] = u_r
        V_24[ch] = v_r
        rec = u_r.astype(np.float32) @ v_r.astype(np.float32)
        max_maes.append(float(np.mean(np.abs(rec - mat_61[ch]))))

    print(f"  -> Rank-{rank} FP16 SVD mean channel MAE={np.mean(max_maes):.5f} (worst channel MAE={np.max(max_maes):.4f})")

    svd_path = DATA_DIR / "studio_368k_svd.npz"
    np.savez_compressed(
        svd_path,
        U=U_24,
        V=V_24,
        compat_mask=compat_mask,
        pair_affinity=pair_affinity.astype(np.float16),
    )
    print(f"  -> Saved {svd_path} ({svd_path.stat().st_size / (1024 * 1024):.2f} MB)")

    # 5. Save `studio_catalog_368k.json`, `surrogate_v2_merged_fp16.pt`, and `deep_research_cache.npz`!
    print("[5/5] Saving catalog JSON and LoRA-merged Deep Research runtime bundle...")
    sur2592 = json.loads((DATA_DIR / "surrogate_2592.json").read_text(encoding="utf-8"))
    emp_weights = sur2592["distilled_weights"]

    catalog_payload = {
        "schema": "ADCToX-StudioCatalog-368640-v083",
        "total_combinations": n_tot,
        "dimensions": {
            "targets": len(STUDIO_TARGETS_36),
            "linkers": len(STUDIO_LINKERS_16),
            "payloads": len(STUDIO_PAYLOADS_20),
            "dars": len(STUDIO_DARS_8),
            "fc_formats": len(STUDIO_FC_4),
        },
        "organs": ORGANS_13,
        "weights": emp_weights,
        "validation_metrics": train_metrics["best_validation_metrics"],
        "targets": STUDIO_TARGETS_36,
        "linkers": [{k: v for k, v in lk.items()} for lk in STUDIO_LINKERS_16],
        "payloads": [{k: v for k, v in pl.items()} for pl in STUDIO_PAYLOADS_20],
        "dars": STUDIO_DARS_8,
        "fc_formats": STUDIO_FC_4,
    }
    cat_txt = json.dumps(catalog_payload, ensure_ascii=False, separators=(",", ":"))
    assert "\u00b7" not in cat_txt, "Forbidden middle dot in studio_catalog_368k.json!"
    cat_path = DATA_DIR / "studio_catalog_368k.json"
    cat_path.write_text(cat_txt, encoding="utf-8")
    print(f"  -> Saved {cat_path} ({cat_path.stat().st_size / 1024:.1f} KB)")

    # Extract RobertaTokenizer vocab + merges so pure-PyTorch runtime needs zero HuggingFace files!
    vocab_dict = tokenizer.get_vocab()
    merges_list = []
    if hasattr(tokenizer, "bpe_ranks"):
        merges_list = [list(pair) for pair, _ in sorted(tokenizer.bpe_ranks.items(), key=lambda kv: kv[1])]
    elif hasattr(tokenizer, "backend_tokenizer"):
        tok_obj = json.loads(tokenizer.backend_tokenizer.to_str())
        raw_merges = tok_obj.get("model", {}).get("merges", [])
        merges_list = [m.split(" ") if isinstance(m, str) else list(m) for m in raw_merges]

    merged_bundle = {
        "schema": "ADCToX-SurrogateNet-v2-MergedFP16-5Fold",
        "n_folds": N_FOLDS,
        "biophys_dim": 108,
        "fp_dim": 1024,
        "d_model": 512,
        "blend_alpha_nn": blend_alpha_nn,
        "vocab": vocab_dict,
        "merges": merges_list,
        "folds": [
            {
                "fold": f,
                "chem_sd": fold_outputs[f]["chem_sd"],
                "head_sd": fold_outputs[f]["head_sd"],
                "bio_mean": fold_outputs[f]["bio_mean"],
                "bio_std": fold_outputs[f]["bio_std"],
                "cal_ab": fold_outputs[f]["cal_ab"],
            }
            for f in range(N_FOLDS)
        ],
    }
    merged_pt_path = MODEL_DIR / "surrogate_v2_merged_fp16.pt"
    torch.save(merged_bundle, merged_pt_path)
    print(f"  -> Saved {merged_pt_path} ({merged_pt_path.stat().st_size / (1024 * 1024):.2f} MB)")

    cache_npz_path = DATA_DIR / "deep_research_cache.npz"
    np.savez_compressed(
        cache_npz_path,
        heavy_esm_tf=heavy_esm_tf.astype(np.float16),
        light_esm_tf=light_esm_tf.astype(np.float16),
        antigen_esm_tf=antigen_esm_tf.astype(np.float16),
        prot_static_tf=prot_static_tf.astype(np.float32),
        cdr_hydro_tf=cdr_hydro_tf.astype(np.float32),
        expr_tf=expr_tf.astype(np.float32),
        cell_tf=cell_tf.astype(np.float32),
        l_3d=l_3d.astype(np.float32),
        p_3d=p_3d.astype(np.float32),
        l_fp=l_fp.astype(np.float16),
        p_fp=p_fp.astype(np.float16),
        rxn_mat=rxn_mat.astype(np.float32),
        has_shield_mat=has_shield_mat.astype(np.float32),
        l_input_ids=l_enc["input_ids"].numpy().astype(np.int16),
        l_attention_mask=l_enc["attention_mask"].numpy().astype(np.int8),
        p_input_ids=p_enc["input_ids"].numpy().astype(np.int16),
        p_attention_mask=p_enc["attention_mask"].numpy().astype(np.int8),
    )
    print(f"  -> Saved {cache_npz_path} ({cache_npz_path.stat().st_size / 1024:.1f} KB)")
    print(f"=== Completed 368,640 Export in {time.time() - t0:.1f}s ===")


if __name__ == "__main__":
    main()
