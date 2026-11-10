# ADCTOX v0.7.7

[![Linux](https://img.shields.io/badge/Linux-x86__64%20%7C%20arm64-2563EB?logo=linux&logoColor=white)](docs/INSTALL.md)
[![macOS](https://img.shields.io/badge/macOS-Apple%20silicon-0F172A?logo=apple&logoColor=white)](docs/INSTALL.md)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0D9488?logo=windows&logoColor=white)](docs/INSTALL.md)
[![Ubuntu terminal](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml)
[![One-line install](https://github.com/ahnhc/ADCToX/actions/workflows/install.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/install.yml)

**Patient-Specific Antibody-Drug Conjugate (ADC) Clinical Decision & 5-Axis De Novo Design Workspace.**  
ADCTOX links a patient's malignancies, comorbidities, and quantitative laboratory biomarkers to 13 physiological organ axes using a 110M-parameter medical language model (`x2te`), evaluates all 15 FDA-approved ADCs against DailyMed label restrictions and ClinicalTrials.gov pivotal trial outcomes, and couples patient organ vulnerability profiles with a 5-axis mechanistic PK/PD conjugate design engine (`Target × Linker × Payload × DAR × Fc`).

---

## Key Capabilities in v0.7.7

1. **Coupled Patient-to-Conjugate Design Engine (`Structure Studio`):**
   - Evaluates `2,592` candidate architectures (`8 Targets × 6 Linkers × 6 Payloads × 3 DARs × 3 Fc Variants`) conditioned directly on the patient's active organ vulnerability vector (`S.result`) and priority organ weighting (`S.prioOrgan`).
   - Supports both **`ADC 자동 설계` (`Auto-design ADC`)** (full-space multi-objective Pareto frontier search with collision-free callout geometry) and **`ADC 수동 설계` (`Manual ADC Design`)** (target-conditioned candidate distribution, FDA reference drug comparison vector, and interactive parameter trajectory tracking).
   - Models linker-payload chemical pairing affinity, payload-specific DAR hydrophobic clearance thresholds (`optDar`, `maxSafeDar`), FcγRIIa/FcRn engineering (`LALA-PG`, `YTE`), and tumor-indication target expression matching.
2. **Malignancy & Multi-Comorbidity Organ Vulnerability Inference:**
   - Combines `x2te` 13-organ neural predictions with hematologic/solid-tumor pathophysiological organ reserve rules and probabilistic score compounding (`1 - Π(1 - s_i)`), sorted in descending severity order with one-click priority organ targeting.
3. **Full-Width Clinical Comparison & 3-Part Mechanism Synthesis:**
   - Side-by-side parameter comparison against the closest FDA-approved reference ADC (`ENHERTU`, `TRODELVY`, `PADCEV`, `POLIVY`, `BLENREP`, `ELAHERE`), synthesizing dynamic 3-part clinical mechanisms (`기존 약물의 문제` / `발생 기전` / `이 설계의 대응`).
4. **Pivotal Clinical Trial Case Comparison (`임상시험 사례`):**
   - Treatment vs. control arm incidence bars across 32 ClinicalTrials.gov pivotal studies, per-event risk difference badges, and automated trial safety verdicts alongside DailyMed Boxed Warnings, Section 5 Warnings, and Cockcroft–Gault `CLcr` / `×ULN` hepatic thresholds.
5. **Interactive 3D Molecular Canvas & Bilingual Workspace (`KO / EN`):**
   - Real-time 3D conjugate structure renderer reflecting exact DAR stoichiometry and payload classes, viewport-clamped bilingual hover descriptions, streamlined top navigation, and responsive desktop/mobile layout.

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

The installer sets up an isolated Python runtime, downloads the `0.8` from-scratch organ judge model bundle (~305 MB), and registers `adctox` (WebApp, default) and `adctox-cli` (Terminal TUI).

---

## Quick Start & Server Hosting

### Local Desktop Browser

```bash
adctox               # Opens the v0.7.7 WebApp in your default browser (127.0.0.1)
adctox-cli           # Opens the 5-step Terminal TUI
```

### Hosting on a Linux Server or Cloudflare Tunnel

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_AUTO_RESTART=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="*" adctox
```

Or restricted to specific hostnames:

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_AUTO_RESTART=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="ubuntu-a1-osaka,adctox.hyeongchan.dpdns.org" adctox
```

### Live Over-the-Air Updates

Installed apps check for newer GitHub releases at startup and every 10 minutes while running (`ADCTOX_NO_AUTO_UPDATE=1` disables checks; `ADCTOX_AUTO_RESTART=1` restarts automatically upon switching):

```bash
adctox --update-app      # Update the application to the latest release
adctox --update-models   # Update the organ judge model bundle
```

---

## Core Architecture: From-Scratch Organ Judge (`x2te`) + Mechanistic PK/PD Studio

```
Patient Input ──▶ MONDO Concept Link ──▶ 13-Organ Judge (x2te) ──▶ 15 FDA ADC Labels & 32 Pivotal Trials
(EN / KO /        (Vector & Alias        (110M BERT trained        (Boxed / Section 5 warnings, ULN & CLcr
 Symptoms)         Index)                 from random weights)      thresholds, 5-axis PK/PD design studio)
```

- **Trained From Random Weights (`ScratchJudge/`):** A 110M-parameter BERT encoder pretrained from scratch on PubMed abstracts (86%), UMLS level-0 terms and definitions (12%), MONDO/HPO ontologies (1%), and drug labels/clinical trials (0.5%), distilled against 22,638 triple-annotated MONDO disease-organ profiles.
- **Ontology Evidence Reading:** For unseen diseases, the model reads MONDO definitions, parent hierarchies, and HPO phenotypes, raising unseen-disease macro-F1 from `0.694` to `0.778` (overall test macro-F1 `0.723` across 3 seeds vs `0.711` for fine-tuned Gemma 4 E2B).
- **Exact FDA Label & Trial Arithmetic:** Unrounded Cockcroft–Gault `CLcr` and laboratory `×ULN` ratios (`Bilirubin`, `AST`, `ALT`) are matched directly against DailyMed label rules alongside adverse event counts from 32 ClinicalTrials.gov pivotal studies.
- **Patient-Conditioned 5-Axis Conjugate Scoring:** Combines Hill-type DAR receptor saturation, linker-modulated bystander killing, tumor-indication target expression matching, non-linear multi-organ toxicity amplification, and payload-specific DAR hydrophobic clearance penalties.

| Test Macro-F1 (3-seed mean) | Unseen Diseases (296) | Known Diseases, New Phrasing (168) | Mean |
|---|---|---|---|
| Gemma 4 E2B (untuned) | 0.739 | 0.432 | 0.586 |
| Gemma 4 E2B (fine-tuned on same labels) | 0.834 | 0.588 | 0.711 |
| **ADCTOX `x2te` (shipped in app, 110M params)** | **0.778** | **0.667** | **0.723** |

---

## Documentation & Licenses

- [Installation & Platform Guide](docs/INSTALL.md)
- [From-Scratch Organ Judge (`x2te`) Architecture](ml/docs/scratch_model.md)
- [Reproducing the Gemma Benchmark](ml/docs/reproduce.md)
- [Module Reference](ml/README.md)
- [Third-Party Notices & Font Licenses (`Manrope`, `Pretendard`)](THIRD_PARTY_NOTICES.md)

Code and project-curated datasets are licensed under the [Apache License 2.0](LICENSE).
