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
