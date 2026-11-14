# ADCTOX v0.9.4

[![Linux](https://img.shields.io/badge/Linux-x86__64%20%7C%20arm64-2563EB?logo=linux&logoColor=white)](#one-line-installation-ubuntu-macos-windows)
[![macOS](https://img.shields.io/badge/macOS-Apple%20silicon-0F172A?logo=apple&logoColor=white)](#one-line-installation-ubuntu-macos-windows)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0D9488?logo=windows&logoColor=white)](#one-line-installation-ubuntu-macos-windows)
[![App Version](https://img.shields.io/badge/version-v0.9.4-10B981)](#)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live%20Platform-adctox.hyeongchan.dpdns.org-6366F1)](https://adctox.hyeongchan.dpdns.org)

**Patient-Specific Antibody-Drug Conjugate (ADC) Safety Evaluation & Multimodal Neural Surrogate De Novo Design Workspace.**  
ADCTOX links a patient's malignancies, comorbidities, and quantitative laboratory biomarkers to 13 physiological organ axes using an on-device 110M-parameter medical language model (`x2te`), evaluates all 15 FDA-approved ADCs against DailyMed label restrictions and ClinicalTrials.gov pivotal trial outcomes, and designs bespoke conjugates across **`368,640` architectures** (`36 Targets × 16 Linkers × 20 Payloads × 8 DARs × 4 Fc Formats`) using a vectorized server matrix engine (`Mode 2`) and real-time 5-fold `ADC-SurrogateNet-v2` inference (`Mode 3 Deep Research`).

---

![ADCTOX 3-Stage Workflow](docs/figures/fig1_adctox_workflow_3steps.png)

![ADCTOX De Novo Studio & Deep Research Telemetry](docs/figures/fig2_de_novo_studio_deep_research.png)

---

## Key Capabilities in v0.9.4

1. **Streamlined 3-Stage Clinical Workflow (`1. Patient Profile` -> `2. Compare ADCs` -> `3. ADC Design`):**
   - **Stage 1 (`Patient Profile`):** Bilingual (`EN / KO`) free-text condition and malignancy entry with real-time AI organ vulnerability mapping, active organ burden indicators, a collapsible 11-item required baseline flowsheet (`Age`, `Sex`, `Weight`, `Creatinine`, `Dialysis/ESRD`, `Bilirubin`, `AST`, `ALT`, `Platelets`, `ANC`, `Hb`), and a collapsible optional biomarker panel (`CLcr`, `eGFR`, `Child-Pugh`, `LVEF`, `HbA1c`, `UGT1A1*28`).
   - **Stage 2 (`Compare ADCs`):** Evaluates all 15 FDA-approved ADCs against patient-specific organ vulnerabilities, DailyMed SPL Boxed Warnings, Section 5 Warnings, Cockcroft–Gault `CLcr` / `×ULN` hepatic thresholds, and 32 ClinicalTrials.gov pivotal trial comparator arms, with head-to-head ranking rationale in the `Patient & Label Fit` drawer.
   - **Stage 3 (`ADC Design`):** Compact patient summary bar with clickable priority-organ pills and an `Edit` shortcut; single-open construct accordions on desktop and mobile (`<= 640px`) bottom-sheet selectors across `368,640` candidate architectures; live 15-drug approved reference selector (`ref-adc-select`) inside the comparison triad; collapsible construct property, organ toxicity, GTEx expression, and `Advanced` equation/weight panels with 1-line parameter sliders; and vectorized `Auto search` (`Mode 2`) or live 5-fold `ADC-SurrogateNet-v2` inference (`Deep Research`).

2. **Multimodal Neural Surrogate Engine (`ADC-SurrogateNet-v2`):**
   - **Ensemble Architecture:** 5-fold leak-free ensemble combining ESM-2 650M protein language models, AlphaFold pLDDT/solvent accessibility, ChemBERTa-2 LoRA molecular representations, Boltzmann 3D conformer ensembles, and enzymatic cleavage reaction SMARTS.
   - **Pathway-Decomposed 13-Organ Risk Heads:** Separates Off-Target systemic leak ($H_{\text{leak}}$), hydrophobic DAR aggregation ($H_{\text{agg}}$), and FcγR macrophage clearance ($H_{\text{Fc}}$) from On-Target normal tissue toxicity ($H_{\text{on}}$) derived from GTEx v8 and Tabula Sapiens single-cell atlases.
   - **Physiological Monotonicity:** Enforces strict biophysical constraints: LALA-PG Fc silencing reduces FcγR hazard by >50%, high DAR scales aggregation risk, and target-specific organ lookups drive on-target toxicity.

3. **Official Clinical Case Validation & Mechanism Convergence:**
   - **Case 1 (Ovarian Cancer + Corneal Disorder + CKD):** Proposes novel conjugate `FRα + GGFG + DXd + DAR 2 + LALA-PG`, converging on late-stage clinical mechanisms (Sofetabart mipitecan, Rina-S, ZW191) to circumvent mirvetuximab soravtansine ocular toxicity and renal burden. Validated via Boltz-2 whole-atom 3D co-folding.
   - **Case 2 (Urothelial Carcinoma + Pulmonary Fibrosis + Hepatic Impairment):** Proposes `Nectin-4 + Hydrophilic Cleavable Linker + Topo I Inhibitor + DAR 2/4 + LALA-PG`, converging on next-generation clinical candidates (ETx-22 / LY4101174, SHR-A2102) to mitigate enfortumab vedotin skin and peripheral neuropathy risks.

4. **Interactive 3D Molecular Canvas & Bilingual Workspace (`EN / KO`):**
   - Real-time 3D conjugate structure renderer reflecting exact DAR stoichiometry and payload classes, viewport-clamped bilingual hover descriptions, and responsive desktop/mobile PWA interface.

---

## System Architecture

```
[ Stage 1: Patient Clinical Input ]
  ├─ Malignancy & Comorbidities (EN / KO) ──▶ MONDO Concept Linking
  ├─ 8 Laboratory Biomarkers (CLcr, ULN)   ──▶ 110M Medical LM (x2te / ScratchJudge)
  └─ Output: 13-Organ Vulnerability Vector (V_o)
               │
               ▼
[ Stage 2: Approved ADC Safety Evaluation ]
  ├─ 15 FDA-Approved ADC Labels (DailyMed SPL)
  ├─ 32 Pivotal Clinical Trials (Treatment vs Control AE Delta)
  └─ Deterministic Contraindication & Safety Ranking
               │
               ▼
[ Stage 3: De Novo Multimodal Conjugate Design ]
  ├─ Search Space: 368,640 Architectures (36 Targets × 16 Linkers × 20 Payloads × 8 DARs × 4 Fc)
  ├─ Antibody / Target: ESM-2 650M + AlphaFold 3D Solvent Accessibility & pLDDT
  ├─ Linker / Payload: ChemBERTa-2 LoRA + 3D Conformer Ensembles + Reaction SMARTS
  ├─ Mode 2 Default: Vectorized Python 368,640 Matrix Engine (CPU, no GPU required)
  └─ Mode 3 Deep Research: Live 5-Fold ADC-SurrogateNet-v2 (4-GPU Queue 0->3 or CPU Fallback)
```

---

## Model Performance & Cross-Validation

### 110M Medical Language Model (`x2te`) vs. Gemma 4 E2B

| Test Macro-F1 (3-seed mean) | Unseen Diseases (296) | Known Diseases, New Phrasing (168) | Overall Mean |
|---|---|---|---|
| Gemma 4 E2B (untuned) | 0.739 | 0.432 | 0.586 |
| Gemma 4 E2B (fine-tuned on same labels) | 0.834 | 0.588 | 0.711 |
| **ADCTOX `x2te` (shipped in app, 110M params)** | **0.778** | **0.667** | **0.723** |

### 5-Fold `ADC-SurrogateNet-v2` Cross-Validation

| Target & Modality Heads | Test MSE | Spearman ρ | R² Score | Key Biophysical Validation |
|---|---|---|---|---|
| Off-Target Leak ($H_{\text{leak}}$) | 0.0142 | 0.884 | 0.841 | Cathepsin B cleavability separation |
| DAR Aggregation ($H_{\text{agg}}$) | 0.0118 | 0.912 | 0.876 | Monotonic scaling from DAR 2 to 8 |
| FcγR Clearance ($H_{\text{Fc}}$) | 0.0089 | 0.935 | 0.902 | LALA-PG >50% hazard reduction |
| On-Target Expression ($H_{\text{on}}$) | 0.0165 | 0.867 | 0.819 | GTEx v8 / Tabula Sapiens specificity |
| Composite Antitumor Efficacy | 0.0131 | 0.893 | 0.854 | Target selectivity & bystander effect |

---

## One-Line Installation (Ubuntu, macOS, Windows)

### Ubuntu / Linux (`x86_64` & `arm64`) and macOS (`Apple Silicon`)

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash
```

### Windows 10 / 11 (PowerShell)

```powershell
irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex
```

The installer configures an isolated Python environment, downloads the `0.8` from-scratch organ judge model bundle (~305 MB), and registers `adctox` (WebApp, default) and `adctox-cli` (Terminal TUI).

---

## Quick Start & Server Hosting

### Local Desktop Browser

```bash
adctox               # Opens the v0.9.4 WebApp in your default browser (127.0.0.1)
adctox-cli           # Opens the Terminal TUI
```

### Hosting on a Linux Server or Cloudflare Tunnel

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_AUTO_RESTART=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="*" adctox
```

### Live Over-the-Air Updates

Installed applications check for newer GitHub releases at startup and every 10 minutes while running:

```bash
adctox --update-app      # Update the application to the latest release
adctox --update-models   # Update the organ judge model bundle
```

---

## Documentation & Competition Reports

- [Final Competition Report (최종 결과 보고서)](docs/ADCToX_바이오헬스_AI융합_경진대회_최종보고서.md)
- [ADC Design Model Scientific Evidence & References](docs/ADC_Design_Model_Scientific_Evidence_and_References.md)
- [Preclinical Multimodal Surrogate NN Training Plan](docs/GPU_Preclinical_Surrogate_NN_Training_Plan.md)
- [From-Scratch Organ Judge (`x2te`) Architecture](ml/docs/scratch_model.md)
- [Reproducing the Gemma Benchmark](ml/docs/reproduce.md)
- [Module Reference](ml/README.md)
- [Third-Party Notices & Font Licenses](THIRD_PARTY_NOTICES.md)

Code and project-curated datasets are licensed under the [Apache License 2.0](LICENSE).
