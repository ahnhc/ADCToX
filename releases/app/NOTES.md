# ADCTOX 0.8.9 Release Notes

- **Default Expanded Required Flowsheet**:
  - Configured the required flowsheet (`1. Patient Info`) to expand by default on initial launch and patient reset.
- **Harmonized Flowsheet Card Heights & Concise Organ Labels**:
  - Balanced left and right card heights symmetrically in baseline laboratory grid (`align-items: stretch` with `flex: 1` row distribution).
  - Renamed baseline section headers to concise standard organ names (`신장`, `간`, `혈액 및 골수` / `Renal`, `Hepatic`, `Hematology`).
- **De Novo Studio Copy Consistency**:
  - Updated candidate construct legend and scan progress to `설계 가능 조합` (`Viable design combinations`).

# ADCTOX 0.8.8 Release Notes

- **Patient Info Flowsheet Cleanup**:
  - Removed helper subtitle below optional laboratory inputs for a cleaner presentation.
- **Header & Status Bar Versioning**:
  - Removed version badge from top brand header; displayed clean numeric version (`0.8.8`) in bottom right status bar.
- **De Novo Studio Empty State & Auto-Design Ergonomics**:
  - Formatted idle canvas warning text into two balanced lines.
  - Adjusted auto-design required-patient alert and button into a compact multi-line card that stays within the chart viewport.
- **Conjugate Architecture Category Tabs**:
  - Positioned `All 36` as the default first category tab, with a clean single-row horizontal scrolling layout.

# ADCTOX 0.8.5 Release Notes

- **Clean Deep Research UI & Telemetry**:
  - Simplified split-button menu and popover: renamed `Deep Research (GPU)` to `Deep Research`, removed subtitle and queue metadata lines, leaving a clean toggle switch and custom SMILES input.
  - Streamlined chart head and telemetry strip: removed internal server/device strings (`| CPU Server #0`) and status details, focusing on optimal clinical dose and key metrics.

# ADCTOX 0.8.4 Release Notes

- **Fix Standalone Bundle `__file__` Execution Context**:
  - Injected module `__file__` metadata into `_Here.exec_module` within the single-file distribution bundle (`adc_recommender_full.py`), preventing runtime `NameError: name '__file__' is not defined`.
  - Added robust in-memory data fallback in `ml/studio_matrix.py` and `ml/deep_research.py`, preventing unhandled file system lookups when running from portable archive distributions.
  - Verified end-to-end operation of `GET /api/studio/catalog` (368,640 design architectures), `GET /api/studio/gpu-status`, `POST /api/studio/evaluate`, and `POST /api/studio/deep-research`.

# ADCTOX 0.8.3 Release Notes

- **Expanded 36-Target De Novo Design Space (368,640 Combinations)**:
  - Upgraded 3. De Novo ADC Design from 2,592 combinations to all 36 trained target antigens, 16 chemical linkers, 20 cytotoxic payloads, 8 DAR values (1, 2, 3.5, 4, 5, 6, 7.6, 8), and 4 antibody/Fc formats (IgG1 Wild-Type, IgG1 LALA-PG, IgG4 S228P, IgG2 Low-Fc), with inline target/gene search and clinical category filter tabs.
- **Mode 2 Vectorized Python Server Matrix Search (Default Auto-design ADC)**:
  - Added ml/studio_matrix.py (POST /api/studio/evaluate) using rank-24 FP16 SVD factors of the 5-fold ADC-SurrogateNet-v2 ensemble (ml/data/studio_368k_svd.npz) to evaluate all 368,640 architectures in milliseconds on CPU without requiring a GPU.
- **Split Action Button & Mode 3 Deep Research (GPU) Live 5-Fold Inference**:
  - Split ADC 자동 설계 (Auto-design ADC) with a compact downward caret (▾) opening the Deep Research (GPU) dropdown toggle (ml/deep_research.py, POST /api/studio/deep-research, GET /api/studio/gpu-status).
  - Runs live 5-fold ADCSurrogateNetV2 forward inference with concentration-response curves (1–1000 nM), ensemble uncertainty, optimal clinical dose (mg/kg), and optional custom payload SMILES scoring.
- **Ordered 4-GPU Slot Allocator (0 -> 1 -> 2 -> 3) & CPU Server Fallback**:
  - Allocates GPUs strictly in ascending slot order across concurrent requests, automatically falling back to CPU server execution when no GPU is installed, with 429 queue busy handling and auto-recovery.
- **Collapsible 11-Item Required Baseline Labs (1. Patient Info)**:
  - Promoted the 11 standard pre-ADC baseline items (Age, Sex, Weight, Creatinine, Dialysis/ESRD, Bilirubin, AST, ALT, Platelets, ANC, Hb) into a collapsible Required flowsheet toggle, keeping specialized/override items in the collapsible Optional flowsheet.

# ADCTOX 0.8.1 Release Notes

- **Streamlined Patient Info & Complete Lab/Clinical Input Coverage (`1. Patient Info`)**:
  - Replaced the always-open lab flowsheet and removed the duplicate `AI Organ Vulnerability Linkage` card in favor of a calm, collapsible `Lab & Clinical Info` (`검진 정보`) panel.
  - Added full input support for `CLcr`, `Dialysis/ESRD`, `eGFR`, Cockcroft-Gault (`Creatinine + Age, Sex, Weight`), `Child-Pugh`, `Platelets`, `ANC`, `LVEF`, `HbA1c`, and `UGT1A1*28`, matching every item surfaced under `Missing Lab & Clinical Info` (`미입력 검진 정보`) in `ADC Matrix`.
- **Navigation Grouping, Drawer Ordering & Header/Footer Polish**:
  - Highlighted the clinician workflow (`1. Patient Info` + `2. ADC Matrix`) with a unified enclosing frame when active while keeping `3. De Novo ADC Design` separate, and routed `New Patient` (`새 환자 입력`) back to `1. Patient Info`.
  - Reordered `ADC Matrix` drawer tabs (`Patient & Label Fit` -> `Molecular Structure` -> `Prior Trial Cases`), updated reference trial labels, matched header `?` button sizing, and simplified footer and guide headers (`ADCTOX`, `ADCTOX Guide`).
- **De Novo ADC Design Formula & Layout Clarity (`3. De Novo ADC Design`)**:
  - Stacked the 3 neural scoring equations (`U_TI`, `X_safe`, `Y_eff`) vertically with clean mathematical typography and unified Korean/English font rendering.
  - Consolidated clinical scenario presets into 3 intuitive modes (`Balanced`, `Organ Protection Priority`, `Antitumor Efficacy Priority`) and formatted auto-design rationale steps in a 2x2 desktop / 1-column mobile grid.

# ADCTOX 0.8.0 Release Notes

- **5-Fold Multimodal Neural Surrogate (`ADC-SurrogateNet-v2`)**:
  - Replaced rule-based scoring in Stage 3 (`De Novo ADC Design`) with a deep multimodal ensemble neural surrogate model.
  - Coupled ESM-2 650M antibody embeddings, AlphaFold 3D structure solvent accessibility & pLDDT, ChemBERTa-2 LoRA molecular embeddings, and GTEx v8 / Tabula Sapiens normal tissue expression.
  - Pathway-decomposed 13-organ hazard modeling ($H_{\text{leak}} + H_{\text{agg}} + H_{\text{Fc}} + H_{\text{on}}$) with verified biophysical monotonicity.
- **Official Clinical Benchmark Validation**:
  - Case 1 (Ovarian Cancer + Corneal Disorder + CKD): Recommends novel conjugate `FRα + GGFG + DXd + DAR 2 + LALA-PG` with Boltz-2 whole-atom 3D validation.
  - Case 2 (Urothelial Carcinoma + Pulmonary Fibrosis + Hepatic Impairment): Recommends `Nectin-4 + Hydrophilic Cleavable Linker + Topo I Inhibitor + DAR 2/4 + LALA-PG`.
- **Integrated Competition Documentation & High-Resolution Figures**:
  - Added final competition reports and high-resolution workflow, 3D co-folding, and chemical structure figures in `docs/`.
  - Streamlined `pyproject.toml`, test suites, and documentation without defensive disclaimers.

# ADCTOX 0.7.9 Release Notes

- **Two-Pathway Mechanistic PK/PD Formula Studio & Clinical Presets (`점수 계산식` / `Scoring Formula`)**:
  - Separated organ toxicity modeling into two competing physiological pathways: **Off-Target Systemic & FcγR Clearance** (plasma linker deconjugation $\beta_{\text{leak}}$, hydrophobic DAR Kupffer-cell aggregation $\gamma_{\text{agg}}$, and LALA-PG Fc$\gamma$R silencing $\phi_{\text{Fc}}$) vs. **On-Target / Off-Tumor Normal Tissue Expression** (GTEx $\alpha_{\text{on}}$).
  - Modeled antitumor efficacy as a normalized convex combination of target selectivity ($w_{\text{sel}}$), payload-DAR stoichiometry ($S_{\text{pot}}$), intact plasma delivery ($S_{\text{deliv}}$), and membrane-permeable bystander diffusion ($w_{\text{bys}}$).
  - Added 4 one-click **Clinical Scenario Presets** (`Balanced TI`, `Organ-Sparing Safety`, `Heterogeneous Solid Tumor`, `High-Selectivity / Hepatic-Sparing`) and 8 interactive coefficient controls.
- **Fixed-Frame Cluster Dynamics (0–100 Coordinate Space)**:
  - Fixed candidate dispersion coordinates on an absolute `0–100` clinical coordinate frame with real-time cluster geometry shifts and dynamic Pareto frontier recalculation.
- **Full-Width Reference Drug Comparison & 3-Part Mechanism Synthesis**:
  - Dynamically synthesizes 3-part medical mechanisms (`Approved Drug Issue`, `Mechanism`, `How This Design Responds`) contrasting candidates against approved reference ADCs.
- **Repository Cleanup & v0.7.9 Distribution**:
  - Cleaned up obsolete preliminary reports, legacy prototypes, and superseded test artifacts; synchronized release manifests and standalone application packages.

# ADCTOX 0.7.8 Release Notes

- **Workflow-Ordered Navigation (`1. Patient Info` → `2. ADC Matrix` → `3. De Novo ADC Design`) & Default English UI**:
  - Reordered top workspace tabs so users start directly on **`1. Patient Info` (`환자 정보`)**, proceed to **`2. ADC Matrix` (`ADC 매트릭스`)**, and then open **`3. De Novo ADC Design` (`ADC 신규 설계`)**.
  - Set default launch language to English (`EN / KO` toggle in header) and renamed `Structure Studio` (`구조 스튜디오`) to **`De Novo ADC Design` (`ADC 신규 설계`)** across navigation, drawers, and the workspace guide.
- **Patient-Input Guard & Interactive Scoring Formula Tuner (`Mode 2: De Novo ADC Design`)**:
  - Added `hasPatientProfile()` validation so clicking `Manual ADC Design` or `Auto-design ADC` without entered conditions or lab values prompts the user to enter patient information first rather than simulating on fallback organs.
  - Upgraded **`Scoring Formula` (`점수 계산식`)** into an interactive live parameter tuning panel with synchronized sliders and numeric inputs for all 12 PK/PD model coefficients (`w_peak`, `k_risk`, normal expression weight, DAR load exponent, Fc-silenced factor, priority organ multiplier, and efficacy exponents) plus a 1-click **`Reset Defaults` (`기본값 복원`)** button.
- **Physiologically Scaled Lab Reference Bars & Guide Indicator Alignment**:
  - Aligned each biomarker's gray reference zone (`.bio-spectrum-normal`), boundary ticks (`refLow` / `refHigh`), and live value needle (`.bio-spectrum-needle`) onto a unified physiological scale with instant `oninput` feedback and distinct `Low` (`수치 저하`) vs. `Elevated` (`수치 상승`) badges.
  - Standardized visual indicator badges in the `?` Workspace Guide modal so `Treatment vs Control` (`치료군 vs 대조군`) matches the exact dimensions of the dosing status badges, and removed the redundant spotlight subtitle hint.
