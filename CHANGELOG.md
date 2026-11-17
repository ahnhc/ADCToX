# Changelog

## 1.0.1

- Fixed repeated patient calculations when leaving an unchanged lab field.
- Kept the Patient Profile scroll position and active input steady while analysis results update.
- Marked CLcr, eGFR, and LVEF values above their displayed reference ranges as elevated.

## 1.0.0

- **3-Stage Clinical & De Novo Workspace (`EN / KO`):** Unified `Patient Profile`, `Recommend ADCs`, and `ADC Design` across desktop and mobile web (`adctox`) and terminal (`adctox-cli`).
- **On-Device Organ Vulnerability Model (`x2te`):** 110M-parameter bilingual (`EN / KO`) medical language model mapping free-text conditions, MONDO concepts, and clinical lab values to 13 physiological organ axes.
- **Safety-First Approved ADC Evaluation:** Evaluates all 15 FDA-approved ADCs against 120 DailyMed SPL dosing/contraindication rules (including Section 8.4 Pediatric Use) and 32 pivotal ClinicalTrials.gov cohorts.
- **Real-Time Multimodal `Auto Design`:** Searches 368,640 conjugate architectures (`36 Targets × 16 Linkers × 20 Payloads × 8 DARs × 4 Fc Formats`) across 5 Q3W doses via rank-24 matrix pre-screening, 5-fold `ADC-SurrogateNet-v2` pathway-decomposed organ toxicity, 252-step Q3W PK/PD ODE integration, and 64-draw QMC virtual-patient optimization with live NDJSON streaming.
- **Cross-Platform Distribution:** Synchronized one-line installers and over-the-air updaters for Linux (`x86_64` / `arm64`), macOS (`Apple Silicon`), and Windows 10/11.

## 0.9.0

- Redesigned unified research workspace UI, added real-time progressive Q3W PK/PD `Auto Design` streaming, and expanded DailyMed rules with Section 8.4 pediatric thresholds.

## 0.8.0

- Introduced 5-fold multimodal `ADC-SurrogateNet-v2` (`ESM-2`, `AlphaFold`, `ChemBERTa-2`, `GTEx`, `Tabula Sapiens`) and expanded *de novo* design space to 368,640 constructs.

## 0.7.0

- Launched interactive web workspace (`adctox`), 3D conjugate structure visualizer, bilingual `EN / KO` toggle, PWA support, and automatic release updates.

## 0.5.0 – 0.6.15

- Replaced teacher encoder pipeline with the standalone 110M `x2te` (`ScratchJudge`) organ vulnerability model and expanded DailyMed SPL / ClinicalTrials.gov evidence coverage.

## 0.1.0 – 0.4.3

- Initial terminal recommender, DailyMed label restriction engine, MONDO disease index, and cross-platform packaging.
