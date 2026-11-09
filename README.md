# ADCTOX v0.7.1

[![Linux](https://img.shields.io/badge/Linux-x86__64%20%7C%20arm64-2563EB?logo=linux&logoColor=white)](docs/INSTALL.md)
[![macOS](https://img.shields.io/badge/macOS-Apple%20silicon-0F172A?logo=apple&logoColor=white)](docs/INSTALL.md)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0D9488?logo=windows&logoColor=white)](docs/INSTALL.md)
[![Ubuntu terminal](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml)
[![One-line install](https://github.com/ahnhc/ADCToX/actions/workflows/install.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/install.yml)

**Patient-Specific Antibody-Drug Conjugate (ADC) Clinical Decision & 4-Part Architecture Workspace.**  
ADCTOX links a patient's cancer, comorbidities, and laboratory values to the 13 organ axes, compares all 15 FDA-approved ADCs against DailyMed label restrictions and ClinicalTrials.gov pivotal study incidence, and provides an interactive **Structure Studio** (`Target × Linker × Payload × DAR & Fc-Silencing`) for de novo conjugate evaluation.

---

## What's New in v0.7.1

1. **Interactive 3D ADC Molecular Structure Visualizer:** 3D rotational canvas rendering distinct architectures for all approved ADCs with accurate DAR counts, payload classes (DXd cyan, SN-38 emerald, SG3199 rose, DM1 gold, MMAE violet, MMAF indigo, Calicheamicin crimson), cleavable/non-cleavable linkers, paratope bindings, and 360-degree interactive rotation.
2. **Dynamic Multi-Objective Pareto Frontier Optimization:** Multi-objective simulation plot comparing Patient Organ Safety Score vs. Antitumor Efficacy & Selectivity across all candidate architectures with progressive scan wavefront, 1:1 square aspect ratio without distortion, clean high-contrast daylight background, and AI de novo optimal architecture rationales.
3. **Bilingual Support (English / Korean Toggle):** Instantaneous `KO / EN` toggle switching all modes, tables, filter tabs, condition inputs, organ vulnerability meters, biomarker flowsheets, and evidence drawer descriptions between English and clinical Korean oncology terminology.
4. **Mobile Responsive Layout:** 2-tier sticky header, responsive single-column grid adaptation, mobile bottom-sheet drawer (`84vh`), and touch-optimized controls on narrow phone screens (<= 480px).
5. **Clinical Biomarker Flowsheet:** Institutional laboratory reference intervals mapping with dynamic spectrum indicators and AI organ vulnerability linkages.

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

## Quick Start & Remote Server Hosting (Mobile / Android Access)

### Local Desktop Browser

```bash
adctox               # Opens the v0.7.1 WebApp in your default browser (127.0.0.1)
adctox-cli           # Opens the 5-step Terminal TUI
```

### Hosting on an Ubuntu Server (`ubuntu-a1-osaka`) for Phone / PWA Access

To host ADCTOX on a remote Linux server and access it directly from an Android or iOS phone browser (or install it to the home screen as a PWA):

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="*" adctox
```

Or behind a reverse proxy / specific domain:

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="ubuntu-a1-osaka,adc.example.com" adctox
```

### Live Over-the-Air Updates

```bash
adctox --update-app      # Update the application to the latest release
adctox --update-models   # Update the organ judge model bundle
```

---

## Core Architecture & From-Scratch Medical Language Model (`x2te`)

```
Patient Input ──▶ MONDO Concept Link ──▶ 13-Organ Judge (x2te) ──▶ 15 FDA ADC Labels & 32 Pivotal Trials
(EN / KO /        (Vector & Alias        (110M BERT trained        (Boxed / Section 5 warnings, ULN & CLcr
 Symptoms)         Index)                 from random weights)      thresholds, Section 12.1 architecture)
```

- **Trained From Random Weights (`ScratchJudge/`):** A 110M-parameter BERT encoder pretrained from scratch on PubMed abstracts (86%), UMLS level-0 terms and definitions (12%), MONDO/HPO ontologies (1%), and drug labels/clinical trials (0.5%), distilled against 22,638 triple-annotated MONDO disease-organ profiles.
- **Ontology Evidence Reading:** For unseen diseases, the model reads MONDO definitions, parent hierarchies, and HPO phenotypes, raising unseen-disease macro-F1 from `0.694` to `0.778` (overall test macro-F1 `0.723` across 3 seeds vs `0.711` for fine-tuned Gemma 4 E2B).
- **Exact FDA Label & Trial Arithmetic:** Unrounded Cockcroft–Gault `CLcr` and laboratory `×ULN` ratios (`Bilirubin`, `AST`, `ALT`) are matched directly against DailyMed label rules alongside adverse event counts from 28 ClinicalTrials.gov pivotal studies.

| Test Macro-F1 (3-seed mean) | Unseen Diseases (296) | Known Diseases, New Phrasing (168) | Mean |
|---|---|---|---|
| Gemma 4 E2B (untuned) | 0.739 | 0.432 | 0.586 |
| Gemma 4 E2B (fine-tuned on same labels) | 0.834 | 0.588 | 0.711 |
| **ADCTOX `x2te` (shipped in app, 110M params)** | **0.778** | **0.667** | **0.723** |

---

## Known Limitations

- **Research Prototype:** Rankings and simulated conjugate metrics have not been prospectively validated against patient clinical outcomes.
- **Drug-Level Post-Marketing Calibration:** FAERS AUROC `0.778 [0.727, 0.837]` reflects drug-level label-warning alignment rather than patient-level risk prediction ([validation plan](ml/docs/validation_plan.md)).
- **Missed Organ Links:** On unseen diseases (`dev`), 19.9% of Boxed Warning links and 23.7% of Section 5 Warning links are missed at the organ-judging stage (`ml/bench_judge.py --table`).

---

## Documentation & Licenses

- [Installation & Platform Guide](docs/INSTALL.md)
- [From-Scratch Organ Judge (`x2te`) Architecture](ml/docs/scratch_model.md)
- [Reproducing the Gemma Benchmark](ml/docs/reproduce.md)
- [Module Reference](ml/README.md)
- [Third-Party Notices & Font Licenses (`Manrope`, `Pretendard`)](THIRD_PARTY_NOTICES.md)

Code and project-curated datasets are licensed under the [Apache License 2.0](LICENSE).
