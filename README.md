# ADCTOX v0.7.6

[![Linux](https://img.shields.io/badge/Linux-x86__64%20%7C%20arm64-2563EB?logo=linux&logoColor=white)](docs/INSTALL.md)
[![macOS](https://img.shields.io/badge/macOS-Apple%20silicon-0F172A?logo=apple&logoColor=white)](docs/INSTALL.md)
[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0D9488?logo=windows&logoColor=white)](docs/INSTALL.md)
[![Ubuntu terminal](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml)
[![One-line install](https://github.com/ahnhc/ADCToX/actions/workflows/install.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/install.yml)

**Patient-Specific Antibody-Drug Conjugate (ADC) Clinical Decision & 4-Part Architecture Workspace.**  
ADCTOX links a patient's cancer, comorbidities, and laboratory values to the 13 organ axes, compares all 15 FDA-approved ADCs against DailyMed label restrictions and ClinicalTrials.gov pivotal study incidence, and provides an interactive **Structure Studio** (`Target × Linker × Payload × DAR & Fc-Silencing`) for de novo conjugate evaluation.

---

## What's New in v0.7.6

1. **Patient-Tailored ADC Design (`환자 맞춤형 ADC 설계`):** Non-linear pharmacological saturation scoring model for realistic 2D candidate dispersion, expandable scoring methodology, and variable-speed left-to-right progress animation on the `ADC 자동 설계` (Auto-design ADC) button.
2. **Full-Width Comparison & 3-Part Medical Mechanisms:** Side-by-side parameter comparison cards without text truncation, plus dynamic 3-part medical mechanism explanations (`기존 약물의 문제` / `발생 기전` / `이 설계의 대응`) computed from selected DAR, Fc silencing (`LALA-PG`), linker stability, and payload.
3. **Clinical Trial Case Comparison (`임상시험 사례`):** Treatment vs. control arm percentage bars, per-event difference badges, and overall trial summary verdicts replacing raw fraction counts, alongside clear patient-centered headings (`약물 사용 제한 여부`, `취약 장기 영향 가능성`, `임상시험 사례`, `분자 구조`).
4. **Live Model Progress & Clean Patient Workspace:** Boot directly into a clean custom patient input state with a `New Patient` reset button and a live stage-by-stage progress bar (`labs`, `recommend`, `queued`, `running`, `judging`, `done`) above the condition search input.
5. **Interactive 3D Molecular Structure, Pareto Frontier & Bilingual Mobile PWA:** Bright white 3D rotational conjugate canvas with true DAR and payload classes, 1:1 multi-objective Pareto simulation, instantaneous `KO / EN` toggle, clinical biomarker flowsheet, and mobile bottom-sheet layout (`<= 480px`).

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
adctox               # Opens the v0.7.6 WebApp in your default browser (127.0.0.1)
adctox-cli           # Opens the 5-step Terminal TUI
```

### Hosting on an Ubuntu Server (`ubuntu-a1-osaka`) for Phone / PWA Access

To host ADCTOX on a remote Linux server (or behind a Cloudflare Tunnel) and access it directly from an Android or iOS phone browser, with automatic background release updates and live restart (`ADCTOX_AUTO_RESTART=1`):

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_AUTO_RESTART=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="*" adctox
```

Or behind a reverse proxy / specific domain:

```bash
ADCTOX_NO_BROWSER=1 ADCTOX_AUTO_RESTART=1 ADCTOX_HOST=0.0.0.0 ADCTOX_PORT=8765 ADCTOX_ALLOWED_HOSTS="ubuntu-a1-osaka,adc.example.com" adctox
```

### Live Over-the-Air Updates

Installed apps (v0.7.3+) automatically check for newer GitHub releases at startup and every 10 minutes while running (`ADCTOX_NO_AUTO_UPDATE=1` disables this; `ADCTOX_AUTO_RESTART=1` restarts the server automatically upon switching). You can also trigger updates manually:

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
