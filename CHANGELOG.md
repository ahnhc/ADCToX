# Changelog

## 0.9.9: Guide Modal Spacing Polish

- **ADCToX Guide Modal Vertical Spacing:** Restored balanced top body padding (`20px` desktop, `16px` mobile) and symmetric header padding (`14px` top/bottom desktop, `12px` mobile) in `ml/web/app.css` for `ADCToX 사용 안내` (`ADCToX Guide`) after removing the legacy subheading margin.

## 0.9.8: Safety-First ADC Ranking, Pediatric Section 8.4 Rules, Live Auto-Design Streaming, and Sliding Segmented UI

- **Safety-First Approved ADC Recommendation Ranking & Filter Priority:** Ranked FDA-approved ADCs globally by organ safety tier, settled restrictions, boxed warnings, and Warnings & Precautions on patient vulnerable organs first, using disease match as a tie-breaker; defaulted Tab 2 (`ADC 추천` / `Recommend ADCs`) to `전체 승인 ADC 목록` (`All Approved ADC List`) first and `질병 일치` (`Disease Match`) second without an artificial disease divider row.
- **Pediatric Label Support (FDA SPL Section 8.4):** Permitted `age >= 0` (including infant month fractions) in `ml/labs.py` and wired patient `age` into `ml/restrictions.py` and `conf/label_restrictions.yaml` with 18 verbatim-verified FDA Section 8.4 rules across all 15 approved ADCs (`<18 yr` unstudied for 12 adult ADCs; `brentuximab-vedotin` `<2 yr` unstudied / `2–18 yr` monitor; `inotuzumab-ozogamicin` `<1 yr` unstudied / `1–18 yr` hepatotoxicity monitor; `gemtuzumab-ozogamicin` `<1 month` unstudied / `≥1 month` pediatric monitoring).
- **Live NDJSON Scatter Plotting & Bottom-Left Design Callouts:** Streamed evaluated candidate batches (`application/x-ndjson`) from `ml/deep_research.py` and `ml/webapp.py` during `Auto design`, plotting points progressively frame-by-frame onto the safety-efficacy chart; placed the `New Design` callout label cleanly bottom-left of its point while avoiding the 5-dose curve and approved ADC callout.
- **UI Polish & Gliding Segmented Controls:** Removed the black border around `ADC 추천 / ADC 설계` while keeping bold `환자 프로필` hierarchy; added smooth distance-proportional WAAPI gliding indicators (`360ms cubic-bezier(0.16, 1, 0.3, 1)`) across all segmented controls; simplified the `ADCToX Guide` modal and `Condition-Related Trial Cases` column; removed reference ticks below optional lab bars and trial labels inside dual-bar cells; fixed top spacing above `.compare-hero`; renamed construct undo to `초기화` (`Reset`); and added the standalone algorithm whitepaper (`docs/ADCToX_Algorithm_Specification.html` & `.pdf`).

## 0.9.7: Unified Auto Design Engine (5-Fold PK/PD ODE) and Streamlined Workspace UI

- **Real-Time Progressive Auto Design Engine:** Replaced the separate `Deep Research` toggle and static matrix path so `Auto design` (`자동 설계`) always runs 5-fold `ADCSurrogateNet v2` evaluation coupled with a vectorized 252-step 3-cycle Q3W two-compartment PK/PD solver and 5x64 QMC virtual-patient IIV simulation under a 5-second minimum compute floor (`minComputeMs: 5000`), paired with `ADC_MODEL_HOME` model checkpoint discovery.
- **Streamlined Navigation and Workspace Framing:** Removed top-bar SVG logo marks and step numbers (`1`, `2`, `3`), enlarged the `ADCToX` wordmark (`20px`), grouped `Recommend ADCs` (`ADC 추천`) and `ADC Design` (`ADC 설계`) inside a black frame matching height with `Patient Profile` (`환자 프로필`), removed per-tab large `mode-h1` page headers while retaining `New Patient`, and stretched the vertical divider symmetrically inside `.workspace-bar`.
- **Unified Terminology and Decluttered Cards:** Standardized terminology across Korean and English (`환자 질환` / `Patient Conditions`, `질환` instead of `적응증`, `ADC 추천` / `Recommend ADCs`, `#` rank column, unified `ADC 설계` / `Design ADC` run button), aligned dosing-fit pills to the right of drug names on narrow viewports, and removed inline tie/match/spacer badges, equation badge tags (`.sim-eq-sym`), and the secondary telemetry strip.

## 0.9.6: Unified Patient Summary Bar, Basic Information Naming, Cleaner Drawer, and Differentiated Deep Research

- **Uniform Workspace Bar Across Tabs 1–3:** Removed compact `.lab-summary-row` lab badges below condition chips in `2. Compare ADCs` and `3. ADC Design` and eliminated `.studio-patient-bar` CSS layout overrides so `.workspace-bar` maintains identical framing and styling across all three steps.
- **`Basic Information` Naming, Filter Labels & Unified Chevrons:** Renamed `인구학적 정보` / `Demographics` to `기본 정보` / `Basic Information`; updated Compare ADCs filter pills to `질병 일치` / `전체 승인 ADC 목록` (`Disease Match` / `All Approved ADC List`); kept `New Patient` (`새 환자 입력`) visible on the initial `1. Patient Profile` header; replaced all solid disclosure triangles and native select arrows with unified vector chevrons (`svgChevronDown`); and streamlined `Vulnerable organ precautions` in the `2. Compare ADCs` drawer to display only boxed clinical criterion cards without trailing unboxed entries.
- **Differentiated 5-Fold `Deep Research` Optimization & `12.8s` Scan:** Preserved `Auto search` speed (`3200 ms`) while setting `Deep Research` scan pacing to `12800 ms` (4x) with `(1/3)`, `(2/3)`, `(3/3)` progress states; added real Q3W `dose_mgkg` PK/PD exposure coupling, saturating Hill tumor target occupancy, 5-fold Lower Confidence Bound (LCB) utility, and 90th-percentile worst-organ tail penalty; rendered the 5-dose titration curve and 5-fold 95% confidence ellipse on the canvas, added a 5-dose therapeutic window strip (`dts-dose-grid`), and displayed `± σ` bounds directly on the `New Design` summary card.

## 0.9.5: Clean clinical workflow UI, real-time Deep Research points, and unified typography

- **Unified Header, Typography & Mobile Navigation:** Matched top navigation border and active framing across `1`, `2`, and `3`; preserved numbered step badges on narrow mobile screens (`<= 480px`) with clean two-row wrapping (`height: auto`); enforced `Manrope` / `Pretendard Variable` typography across all elements; and removed decorative middle dots and redundant status/provenance pills throughout Tabs 1–3.
- **Streamlined `1. Patient Profile`:** Automatically preloaded baseline scenario without a separate demo banner (`New Patient` remains in header); separated `Demographics` (`Age`, `Sex`, `Weight`) from unified `Optional Clinical Panels`; made full header bars clickable chevron toggles; and standardized all numeric lab inputs to uniform widths with clean threshold labels (`기준치` / `Reference`).
- **Focused `2. Compare ADCs` & Inspection Drawer:** Synchronized `Vulnerable Organs` top bar across Tabs 2–3 while keeping clicked organ selection highlighted in place; removed inline detail buttons and secondary badge clutter; folded FDA dosing rules into `Vulnerable organ precautions`; highlighted elevated treatment adverse-event bars in crimson; and added a bottom `Export summary ↗` action tab in the drawer.
- **`3. ADC Design` & Real-Time Deep Research:** Evaluated real-time multi-candidate `ADC-SurrogateNet-v2` points (`deep_points`) in `Deep Research` mode; added horizontal wheel and drag scrolling to target category tabs; introduced an HTML 4-item uniform-dot legend (`New Design`, `Existing ADC`, `Same-Target Candidates`, `Incompatible Pairs`); simplified result cards to 2 stacked panels with multi-line formatting; renamed panels to `Construct Properties`, `Organ Toxicity Prediction`, and `Advanced Settings` (`Balanced`, `Organ Protection`, `Antitumor Efficacy`); and updated `?` guide modal with direct GitHub repository links.

## 0.9.4: Decluttered ADC Design workspace, bilingual parity, and mobile part sheets

- **Decluttered `3. ADC Design` & Tabs 1–2:** Replaced duplicated condition/lab search bars on Tab 3 with a compact patient summary bar showing active disease chips, lab badges, an `Edit` action, and clickable dynamic priority-organ pills; removed redundant subtitles, rationale prose cards, preview notes, and discrete lab helper sentences across Tabs 1–3.
- **Single-Open Construct Accordions & Mobile Bottom Sheets:** Organized Target, Linker, Payload, DAR, and Antibody & Fc controls into single-open accordions on desktop (`studio-acc`) and native mobile bottom-sheet selectors (`<= 640px`) with search, category tabs, compatibility badges, focus trap, and `Confirm` actions.
- **Live Approved Reference Switcher & Collapsible Result Sections:** Added a `<select class="ref-adc-select">` dropdown in the Approved Reference card to switch across all 15 FDA-approved ADCs live (updating triad scores, open compare drawer, and `.txt` export); moved construct properties, organ toxicity, and normal-organ GTEx expression into collapsible `<details>` panels with tooltips on metric labels and 1-line weight sliders under `Advanced`.
- **Full `EN / KO` Bilingual Parity:** Preserved both Korean and English labels when adding condition chips so chips translate dynamically upon language toggle, localized search suggestions and selection summaries, dismissed floating tooltips/popovers on toggle, and re-rendered open guide or bottom-sheet dialogs in place.

## 0.9.3: Patient flow, comparison and design clarity

- Bring new-patient entry into the demo panel and give tied candidates equal emphasis.
- Keep the current construct beside the run action, allow restoring the pre-search construct, and identify previous results after input changes.
- Label organ results as model scores and distinguish trial observations from FDA label warnings.

## 0.9.2: Enclosed clinician workflow navigation, header polish, and typography verification

- **Clinician Navigation Enclosure:** Highlighted clinician workflow tabs (1. Patient Profile and 2. Compare ADCs) with a unified rectangular frame (`.crumb-clinician-group`) to visually group patient evaluation and drug comparison as a single clinician unit, separated from 3. ADC Design.
- **Header Poland & Brand Logo:** Removed the numeric version badge next to the brand logo in the top navigation header for a clean title display; version remains accessible in the guide modal and metadata.
- **Typography & Font Cascade Verification:** Verified comprehensive webfont loading for `Manrope` and `Pretendard Variable`; updated `@font-face` with robust format fallbacks and ensured all form controls (`button`, `input`, `select`, `textarea`, `optgroup`) inherit standard font properties.

## 0.9.1: Responsive layout, overlay drawers, demo flow and studio run controls

- **Mobile Layout (R01, R07, R15):** Removed horizontal overflow at 320–390px across all three modes; 16px page gutter; 44px touch targets on mobile (40 / 32 / 44 on desktop); construct groups become accordions with the run button below them, and the result summary sits above the design plot with auto-scroll after a run.
- **Drawer & Dialog Geometry (R02, R21, R27):** The detail drawer docks only when the page keeps at least 760px beside it; otherwise it opens as an overlay with a scrim, focus trap, focus return, scroll lock and `aria-modal`. On mobile it is an inset bottom sheet aligned to the page gutter. The guide has a single close button, a sticky header and a mobile sheet layout.
- **Comparison Table (R03, R16–R19):** Container-query layout (trial column hidden under 900px, card layout under 640px) with a dedicated Evidence column; tie labels for shared ranks; the default filter shows drugs approved for the entered cancer, with other-cancer drugs grouped under a divider; organ scores are labelled Association (0–100) with a definition.
- **Demo Patient & Input Flow (R04–R06, R13, R14, R22, R23, R25):** Every launch opens a labelled virtual demo patient (only the language persists); New Patient clears to an empty profile with a 7-second undo toast; stale async results are dropped; typed search text survives re-renders; lab summary reads as text with an Edit lab values button; optional labs start collapsed; lab inputs carry labels and descriptions.
- **ADC Design Run Controls (R08–R12, R20):** Segmented Manual / Auto search control with one run button; Deep Research moves to an advanced switch and the slot grid leaves the main UI; explicit Not run / Calculating / Latest / Previous · updating states; model organ risks appear only after a run; duplicate studio and compare buttons removed; compare drawer wording aligned.
- **Cleanup (R26):** Removed the fixed footer bar and unused split-button, popover and slot-grid styles.

## 0.9.0: Calm research software UI redesign and P0/P1 clinical & studio consistency fixes

- **Research Software Design System (EN / KO):** Redesigned Patient Profile, Compare ADCs, ADC Design, detail/comparison drawers, and guide modal around neutral white surfaces, 1px crisp borders, high-contrast typography, #111111 primary CTAs, restrained #0F766E selection accents, and source/provenance badges (FDA SPL, Observed Cohort %, Model 0-100).
- **Approved Reference Construct Isolation (P0):** Expanded REF_ADC_ARCH and ADC_SPECS to all 15 FDA-approved ADCs (	elisotuzumab-vedotin, pivekimab-sunirine included) and isolated each reference drug's native target antigen (Nectin-4 for PADCEV, BCMA for BLENREP) so de novo target edits never overwrite approved reference specifications or scores.
- **Persistent Comparison Context & Explicit Input States (P0):** Preserved Cancer Match filter, selected drug row, and active drawer/comparison tabs across organ priority toggles and re-evaluations; differentiated unentered, partial, evaluating, and complete profile states so empty profiles display unranked (—) candidates without premature #1 recommendations.
- **Construct Handoff, Priority-Organ Trials & Stale Evaluation Sync (P1):** Wired Load Structure in ADC Design in approved drug drawers to populate that drug's exact target, linker, payload, DAR, and Fc format into ADC Design; sorted pivotal trial adverse events and organ warnings to prioritize user-selected organs; enlarged the central design coordinate plot (470px), surfaced explicit 3-way cards (Current, Selected Optimal, Approved Reference), moved equations/weights/custom SMILES to Advanced, and synchronized screen-consistent summary exports (
eview.js).

## 0.8.9: Flowsheet default state, equalized card heights, and copy alignment

- **Default Expanded Required Flowsheet:** Set the required baseline flowsheet (`1. 환자 정보`) to be expanded by default on application launch and reset.
- **Harmonized Flowsheet Card Heights & Concise Organ Labels:** Aligned baseline section grid card heights symmetrically (`align-items: stretch` with `flex: 1` rows) to eliminate height discrepancies between left and right columns; simplified section headers to standard organ names (`신장`, `간`, `혈액 및 골수`).
- **De Novo Studio Copy Consistency:** Updated patient-tailored ADC combination chart candidate legend and progress indicators to `설계 가능 조합` (`Viable design combinations`).

## 0.8.8: Refine layout ergonomics and version indicator

- **Patient Info Flowsheet Cleanup:** Removed helper subtitle below optional laboratory inputs for a cleaner presentation.
- **Header & Status Bar Versioning:** Removed version badge from top brand header; displayed clean numeric version (`0.8.8`) in bottom right status bar.
- **De Novo Studio Empty State & Auto-Design Ergonomics:** Formatted idle canvas warning text into two balanced lines; adjusted auto-design required-patient alert and button into a compact multi-line card that stays within the chart viewport.
- **Conjugate Architecture Category Tabs:** Positioned `All 36` as the default first category tab, with a clean single-row horizontal scrolling layout.

## 0.8.7: Comparative ranking rationale in ADC Matrix detail drawer

- **Head-to-Head Ranking Rationale (`Patient & Label Fit` / `환자 적합도`):** Added a deterministic `Ranking rationale` (`순위 산정 근거`) section at the top of the Stage 2 drug detail drawer (`buildRankingRationale` in `ml/web/app.js`), summarizing the selected ADC's standing and explaining why `#1` outranks `#2`–`#3` alternatives (or why a lower-ranked candidate fell behind `#1` and its preceding rank).
- **Full Lexicographic Rule Parity (`EN / KO`):** Evaluates user-prioritized organs, FDA cancer indication match, DailyMed label dosing restriction tiers (citing exact `CLcr`, `×ULN`, or `LVEF` thresholds and patient values), confirmed vs. conditional restriction status, and vulnerable-organ warnings/cautions, while preserving tied ranks during priority-organ re-sorting.

## 0.8.6: Multiline layout for vulnerable organ warnings in drug detail drawer

- **Vulnerable Organ Warning Multiline Display:** Restructured `.wl` from a rigid 3-column grid (`64px 24px minmax(0, 1fr)`) to a clean 2-line stacked layout (`.wr`), placing the organ name and Warning/Caution status badge on the header row (`.wh`) and displaying the full description text on its own line (`.wt`) below.
- **Word Wrapping & Overlap Elimination:** Resolved text collision where English status badges ("Caution" / "Warning") overlapped with warning descriptions (`Cautilncreased...`), allowing long descriptions to wrap naturally across multiple lines with generous line-height (`1.55`).

## 0.8.5: Clean Deep Research UI and streamlined telemetry

- **Streamlined Deep Research Menu:** Renamed `Deep Research (GPU)` to `Deep Research`, removed subtitle and queue metadata lines, leaving a clean toggle switch and custom SMILES input.
- **Refined Chart and Telemetry Copy:** Removed internal device labels (`| CPU Server #0`) and verbose forward-pass counters from the chart header and telemetry strip, focusing on optimal clinical dose (`mg/kg`) and key predictive metrics.
- **Single-File Standalone Execution Parity:** Injected `__file__` metadata and in-memory data lookups into `build_portable.py`, `studio_matrix.py`, and `deep_research.py` for bulletproof standalone server execution.

## 0.8.4: Standalone portable single-file bundle __file__ execution fix

- **Injected Loader Metadata:** Added `module.__file__` injection to `_Here.exec_module` within the single-file distribution bundle (`dist/releases/app/adc_recommender_full.py`), preventing `NameError: name '__file__' is not defined`.
- **In-Memory SVD & Cache Priority:** Guarded filesystem path fallbacks in `ml/studio_matrix.py` and `ml/deep_research.py` to prioritize embedded `_portable_data()`, ensuring flawless operation on remote servers without physical source checkouts.
- **Test Suite Offset Synchronization:** Updated `tests/test_doctor_review.py` keyboard navigation offsets to account for newly added baseline clinical inputs (`CLcr`, `ESRD`).

## 0.8.3: 368,640-combination 36-target De Novo Studio, vectorized server matrix engine, split-button `Deep Research (GPU)` 4-slot queue, and collapsible 11-item required baseline labs

- **Expanded 36-Target De Novo Design Space (`368,640` Combinations):** Upgraded `3. De Novo ADC Design` (`접합체 구조 설계`) from `2,592` combinations to all `36` trained target antigens, `16` chemical linkers, `20` cytotoxic payloads, `8` DAR values (`1, 2, 3.5, 4, 5, 6, 7.6, 8`), and `4` antibody/Fc formats (`IgG1 Wild-Type`, `IgG1 LALA-PG`, `IgG4 S228P`, `IgG2 Low-Fc`), with inline target/gene search and clinical category filter tabs.
- **Mode 2 Vectorized Python Server Matrix Search (Default `Auto-design ADC`):** Added `ml/studio_matrix.py` (`POST /api/studio/evaluate`) using rank-24 FP16 SVD factors of the 5-fold `ADC-SurrogateNet-v2` ensemble (`ml/data/studio_368k_svd.npz`, mean channel MAE `0.0029`) to evaluate all `368,640` architectures in milliseconds on CPU without requiring a GPU.
- **Split Action Button & Mode 3 `Deep Research (GPU)` Live 5-Fold Inference:** Split `ADC 자동 설계` (`Auto-design ADC`) with a compact downward caret (`▾`) opening the `Deep Research (GPU)` dropdown toggle (`ml/deep_research.py`, `POST /api/studio/deep-research`, `GET /api/studio/gpu-status`). Runs live 5-fold `ADCSurrogateNetV2` forward inference (`forward_preencoded` with LoRA-merged FP16 weights and pre-encoded modality cache) with concentration-response curves (`1–1000 nM`), `±σ` ensemble uncertainty, optimal clinical dose (`mg/kg`), and optional custom payload SMILES scoring.
- **Ordered 4-GPU Slot Allocator (`0 -> 1 -> 2 -> 3`) & CPU Server Fallback:** Allocates GPUs strictly in ascending slot order `0 -> 1 -> 2 -> 3` across concurrent requests, automatically falling back to CPU server execution when no GPU is installed. When all 4 slots are concurrently busy, disables and greys out the `Deep Research` button (`HTTP 429 all_gpu_slots_busy`) and automatically restores its active state and color as soon as a slot frees up.
- **Collapsible 11-Item Required Baseline Labs & Copy Cleanup (`1. Patient Info`):** Removed redundant Cockcroft-Gault explanatory subtitles (`basicSub`, `cg-auto-note`), promoted the 11 standard pre-ADC baseline items (`Age`, `Sex`, `Weight`, `Creatinine`, `Dialysis/ESRD`, `Bilirubin`, `AST`, `ALT`, `Platelets`, `ANC`, `Hb`) into a collapsible `Required` (`필수 입력`) flowsheet toggle, and kept specialized/override items (`CLcr`, `eGFR`, `Child-Pugh`, `LVEF`, `HbA1c`, `UGT1A1*28`) in the collapsible `Optional` (`선택 입력`) flowsheet.

## 0.8.1: Collapsible Lab & Clinical Info panel, complete renal/hepatic/genotype input parity, clinician workflow grouping, and Studio equation clarity

- **Calm Patient Info & Collapsible Lab Panel (`1. Patient Info`):** Removed the redundant `AI Organ Vulnerability Linkage` panel and turned `Lab & Clinical Info` (`검진 정보`) into an optional collapsible accordion below the condition search and active vulnerable organs bar.
- **Full Missing-Input Parity (`CLcr`, `Dialysis/ESRD`, `Child-Pugh`, `Platelets`, `HbA1c`, `UGT1A1*28`):** Added direct `CLcr` (`mL/min`), `Dialysis/ESRD` (`y/n`), inline Cockcroft-Gault calculator (`Age`, `Sex`, `Weight`), `eGFR`, `Child-Pugh` (`A`/`B`/`C`), `HbA1c`, and `UGT1A1*28` controls alongside fixed `platelet` binding so every item reported under `미입력 검진 정보` in `ADC Matrix` can be entered directly in `Patient Info`.
- **Clinician vs. De Novo Navigation Grouping & Reset Flow:** Grouped `1. Patient Info` and `2. ADC Matrix` inside a clinician-workflow frame when active while keeping `3. De Novo ADC Design` distinct; aligned header `?` button dimensions, simplified footer and guide titles (`ADCTOX`, `ADCTOX 안내`), and updated `New Patient` (`새 환자 입력`) to return directly to `1. Patient Info`.
- **Evidence Drawer & De Novo Studio Refinements:** Reordered `ADC Matrix` drawer tabs to `Patient & Label Fit / Molecular Structure / Prior Trial Cases`, renamed reference study tabs cleanly, formatted the 3 neural scoring equations (`U_TI`, `X_safe`, `Y_eff`) in a single-column vertical layout with unified typography, streamlined clinical presets to 3 options (`Balanced`, `Organ Protection Priority`, `Antitumor Efficacy Priority`), and arranged auto-design rationale cards in a balanced 2x2 grid on desktop (`1fr` on mobile).

## 0.8.0: 5-Fold Multimodal Neural Surrogate (`ADC-SurrogateNet-v2`), ESM-2 & AlphaFold 3D biophysics integration, and official clinical validation

- **5-Fold Multimodal Neural Surrogate Engine (`ADC-SurrogateNet-v2`):** Replaced rule-based scoring with a deep multimodal ensemble neural network (`ml/preclinical/train_surrogate_nn.py`, `ml/data/surrogate_designer.json`, `ml/web/surrogate_2592.js`). Integrated ESM-2 650M antibody embeddings, AlphaFold 3D structure solvent accessibility & pLDDT, ChemBERTa-2 LoRA molecular embeddings, Boltzmann 3D conformer ensembles, reaction SMARTS, and GTEx v8 / Tabula Sapiens normal tissue expression.
- **Pathway-Decomposed 13-Organ Risk Modeling:** Decomposed organ risk into Off-Target systemic leak ($H_{\text{leak}}$), hydrophobic DAR aggregation ($H_{\text{agg}}$), and FcγR macrophage clearance ($H_{\text{Fc}}$) vs On-Target normal tissue toxicity ($H_{\text{on}}$). Validated monotonicity: LALA-PG Fc-silencing reduces FcγR hazard by >50%, high DAR (8) scales aggregation hazard, and target-specific organ lookups drive on-target toxicity.
- **Official Clinical Benchmark & Case Demonstrations:**
  - *Case 1 (Ovarian Cancer + Corneal Disorder + CKD):* Proposes novel conjugate `FRα + GGFG + DXd + DAR 2 + LALA-PG`, converging with late-stage clinical pipeline strategies (Sofetabart mipitecan, Rina-S, ZW191) to circumvent mirvetuximab soravtansine ocular toxicity and renal burden. Validated via Boltz-2 whole-atom 3D co-folding.
  - *Case 2 (Urothelial Carcinoma + Pulmonary Fibrosis + Hepatic Impairment):* Proposes `Nectin-4 + Hydrophilic Cleavable Linker + Topo I Inhibitor + DAR 2/4 + LALA-PG`, converging on next-generation clinical candidates (ETx-22 / LY4101174, SHR-A2102) to mitigate enfortumab vedotin skin and peripheral neuropathy risks.
- **Streamlined 3-Stage Clinical Web Interface:** Updated top workspace flow to `1. Patient Info` -> `2. ADC Matrix` -> `3. De Novo ADC Design`, embedding real-time client-side neural surrogate inference without backend dependencies.
- **Hygiene & Copywriting Rules:** Removed defensive disclaimers and decorative emoji slop across all UI components and documentation; updated `pyproject.toml` and release manifests to v0.8.0.

## 0.7.9: Two-pathway mechanistic PK/PD Formula Studio, 4 clinical presets, fixed 0-100 coordinate cluster dynamics, and repository cleanup

- **Two-Pathway Mechanistic PK/PD Scoring:** Separated organ hazard into Off-Target Systemic & FcγR clearance (plasma linker deconjugation $\beta_{\text{leak}}$, hydrophobic DAR Kupffer aggregation $\gamma_{\text{agg}}$, and LALA-PG Fc$\gamma$R silencing $\phi_{\text{Fc}}$) vs. On-Target / Off-Tumor tissue expression (GTEx $\alpha_{\text{on}}$), coupled with convex multi-mechanism antitumor efficacy.
- **Clinical Scenario Presets:** Added 4 one-click clinical scenario presets (`Balanced TI`, `Organ-Sparing Safety`, `Heterogeneous Solid Tumor`, `High-Selectivity / Hepatic-Sparing`) with 8 interactive parameter sliders in `점수 계산식` (`Scoring Formula`).
- **Fixed-Frame Cluster Dynamics:** Mapped all 2,592 construct candidates onto a fixed `0–100` clinical coordinate space with real-time cluster geometry shifts and Pareto frontier updates.
- **Repository & Release Cleanup:** Streamlined the repository for v0.7.9 by removing legacy report drafts, obsolete UI prototypes, and superseded test artifacts.

## 0.7.8: Workflow-ordered tabs (Patient Info -> ADC Matrix -> De Novo ADC Design), interactive formula tuner, and aligned biomarker reference bars

- **Reordered workspace tabs & default English UI:** ordered top navigation as `1. Patient Info` (`환자 정보`), `2. ADC Matrix` (`ADC 매트릭스`), and `3. De Novo ADC Design` (`ADC 신규 설계`), and set the default startup language to English (`en`).
- **Patient-profile simulation guard:** prevented `Auto-design ADC` and `Manual ADC Design` from running on fallback organs when no patient conditions or lab values are entered, displaying an inline prompt with a direct link to `1. Patient Info`.
- **Interactive Scoring Formula (`점수 계산식`) parameter tuner:** added live slider and numeric controls for all 12 PK/PD safety and efficacy coefficients with real-time formula and chart updates and a `Reset Defaults` (`기본값 복원`) action.
- **Unified biomarker reference range bars:** mapped each lab field's gray reference zone, boundary ticks, and live value marker onto a shared physiological scale with immediate `oninput` updates.
- **Guide modal & spotlight card polish:** equalized all 4 visual indicator badge boxes in the `?` guide modal and removed the redundant spotlight card click hint.

## 0.7.7: Dynamic Pareto/manual design visualization, malignancy organ mapping, and UI layout polish

- **Collision-free Patient-Tailored ADC Design chart:** fixed top plot-area padding (`padT = 42 * dpr`), unified overlapping `Best` and `Selected` callout labels into a single pill, and added bounding-box collision resolution when distinct.
- **Continuous coordinate dispersion & reference vectors:** plotted unrounded `(safetyRaw, efficacyRaw)` coordinates, incorporated target normal-tissue baseline risk (`tgt.tissues`), added Pareto frontier curve rendering in `Auto-design ADC`, and added target-conditioned sub-cloud + FDA reference drug comparison vector + manual parameter trajectory in `Manual ADC Design`.
- **Malignancy organ vulnerability inference & clean priority state:** mapped hematologic and solid tumor indications (`breast cancer`, `lung cancer`, `Lymphoid leukemia`, `Myeloid leukemia`, etc.) to physiological organ reserve axes with probabilistic score compounding, and styled priority organ selection with clean structural highlighting.
- **Navigation, guide modal & scoring formula layout:** removed duplicate numbering in top navigation tabs and the `How it works` modal, structured guide steps/shortcuts into aligned cards, and added proper container spacing and concise monospace equations to `점수 계산식` (`Scoring Formula`).

## 0.7.6: Pictorial brand emblem, manual/auto ADC design workflow, and mechanistic PK/PD scoring

- **Pictorial Brand Logo (`ADC` + `ToX`):** inline SVG vector rendition of the ADCToX emblem (Erlenmeyer flask `A` + `D` + `C` in cyan, paired with syringe `T` + droplet `o` + crossed bones `X` in crimson).
- **Manual & Auto ADC Design (`Mode 1`):** added `ADC 수동 설계` (`Manual ADC Design`) alongside `ADC 자동 설계` (`Auto-design ADC`), initialized the coordinate plane in a ready state prior to execution, and upgraded the scoring model with linker–payload chemical pairing affinity, payload-specific DAR hydrophobic aggregation ceilings, and tumor-indication target matching.
- **Viewport-clamped bilingual popovers & workspace polish:** mounted `.micro-popover` tooltips to `document.body` with full Korean/English descriptions across all 5 design groups, sorted active vulnerable organs by descending `%`, added condition autocomplete hover transitions, and simplified workspace section headers.

## 0.7.5: Bilingual layout refinement, horizontal bar alignment, and responsive design chart

- **Bilingual (KO/EN) & docked drawer layout:** widened organ/biomarker label columns, enforced single-line pills and badges, and added responsive grid breakpoints when the side drawer opens so text never overlaps or clips.
- **Horizontal bar alignment & cleaner 3D viewer:** aligned horizontal bars across spotlight cards, cohort matrix rows, and studio panels onto shared baselines, and removed the 3D rotation overlay hint.
- **Responsive Patient-Tailored ADC Design chart:** attached a `ResizeObserver` and dynamic frame sizing to `.sim-canvas` and `.adc-3d-canvas` so opening/closing the side drawer or switching tabs redraws at native resolution without distortion.
- **Concise scoring explanation:** focused the scoring explanation strictly on the mathematical formulation for safety and efficacy.

## 0.7.4: Patient-tailored ADC design, clinical trial comparison, and UI refinement

- **Removed demo presets:** boots into a clean custom patient input state with a `New Patient` reset button.
- **Live model progress bar:** thin progress bar above the condition input tracks actual backend stages (`labs`, `recommend`, `queued`, `running`, `judging`, `done`).
- **Clear clinical language:** replaced raw regulatory jargon with clear patient-centered headings and explanations (`약물 사용 제한 여부`, `취약 장기 영향 가능성`, `임상시험 사례`, `분자 구조`).
- **Clinical trial comparison (`임상시험 사례`):** replaced raw `ADC`/`CMP` fraction counts with treatment vs. control percentage bars, per-event difference badges, and an overall trial summary verdict.
- **Bright 3D molecular canvas:** updated the 3D conjugate structure viewer to a bright white background in both the ADC Matrix drawer and the Structure Studio comparison drawer, and removed the redundant indications list from the Structure tab.
- **Patient-Tailored ADC Design (`환자 맞춤형 ADC 설계`):** replaced linear clamped scoring with a non-linear pharmacological saturation model for realistic 2D candidate dispersion, added an expandable scoring explanation, and updated the `ADC 자동 설계` button with variable-speed left-to-right progress fill.
- **Full-width comparison & medical mechanisms:** redesigned the comparison drawer with full-width side-by-side parameter cards so clinical advantages never truncate, and added 3-part medical mechanism explanations (`기존 약물의 문제`, `발생 기전`, `이 설계의 대응`) dynamically computed from the selected DAR, Fc silencing, linker stability, and payload.

## 0.7.3: Automatic app updates

- An installed app checks the published release at every start (5 minute cache) and every 10 minutes while running, downloads and verifies the newer release and switches to it. `ADCTOX_NO_AUTO_UPDATE=1` turns it off; `ADCTOX_AUTO_RESTART=1` restarts a running server at once.
- Includes the 0.7.2 interface changes (wider comparison drawer).

## 0.7.2: Structure Studio comparison drawer and UI polish

- **De novo vs approved ADC comparison drawer:** opens automatically after Auto Optimize or when an architecture is picked, with spec comparison, clinical de-risking notes, 3D structure toggle and the approved drug's pivotal trial.
- **Wider side drawer:** 520-780px (was 460px) so the comparison table is readable.
- **Auto Optimize** button moved under Fc engineering; slower 3.5s progressive animation.
- 3D structure legend moved out of the canvas (no overlapping text); removed the "Label restrictions" filter; clearer bystander and normal-tissue wording with a traffic-light baseline.

## 0.7.1: Interactive 3D ADC Molecular Structure, Multi-Objective Pareto Optimization, Bilingual Toggle (KO/EN), and Mobile Optimization

- **Interactive 3D ADC Molecular Visualizer:** 3D rotational canvas rendering distinct architectures for all approved ADCs with accurate DAR counts, payload classes (DXd cyan, SN-38 emerald, SG3199 rose, DM1 gold, MMAE violet, MMAF indigo, Calicheamicin crimson), cleavable/non-cleavable linkers, paratope bindings, and continuous 360-degree interactive rotation.
- **Dynamic Multi-Objective Pareto Frontier:** multi-objective simulation plot comparing Patient Organ Safety Score vs. Antitumor Efficacy & Selectivity across all candidate architectures. Features an animated progressive scan wavefront, 1:1 square aspect ratio without distortion, clean high-contrast daylight background, and AI de novo optimal architecture rationales.
- **Bilingual Support (English / Korean Toggle):** instantaneous `KO / EN` toggle switching all modes, tables, filter tabs, condition inputs, organ vulnerability meters, biomarker flowsheets, and evidence drawer descriptions between English and clinical Korean oncology terminology.
- **Mobile Responsive Layout:** 2-tier sticky header, responsive single-column grid adaptation, mobile bottom-sheet drawer (`84vh`), and touch-optimized controls on narrow phone screens (<= 480px).
- **Clinical Biomarker Flowsheet:** institutional laboratory reference intervals mapping with dynamic spectrum indicators and AI organ vulnerability linkages.
- Models remain at 0.8 (`releases/models/stable4.json`).

## 0.7.0: Architectural Daylight WebApp, Active-Organ Matrix, Structure Studio, and Mobile PWA (Ubuntu, macOS and Windows)

- **Visual ADC Matrix (Option A, Active-Organ-Only):** replaces the 5-step wizard wall and 13-cell organ clutter with a unified workspace that boots directly into the visual ADC Matrix. Only the patient's active vulnerable organs (1 to 4 axes) are graphed.
- **Spotlight Hero Cards & Monochrome Hierarchy:** top recommended ADCs render in full-chroma Cobalt (`#2563EB`) and Emerald (`#0D9488`) Spotlight Hero Cards with larger typography, 4-part conjugate tags, active-organ safety bars, and pivotal trial dual-bars (`ADC` vs `CMP` incidence). Lower-ranked or restricted ADCs recede into compact monochrome slate rows until hovered or selected.
- **Structure & Combination Studio:** interactive 4-part ADC design studio (`Target Antigen × Linker × Payload × DAR & Fc-Silencing LALA-PG`) with visual meters for chemical conjugation handle compatibility, GTEx tumor/normal tissue selectivity (`log2FC`), bystander killing capacity, plasma linker stability, and patient active-organ toxicity index.
- **Typography & Anti-Slop Polish:** Google Fonts **Manrope** (`ManropeVariable.woff2`, SIL OFL 1.1) with `tabular-nums` replaces Intel One Mono. All indicator dots, warning beads, middle dots, and stock-ticker delta triangles are removed. Detailed FDA label text, boxed warnings, trial populations, and Section 12.1 mechanisms open in the smooth secondary slide-over drawer (desktop) or bottom-sheet drawer (mobile).
- **Android / Mobile PWA & Remote Server Hosting:** adds `manifest.webmanifest`, `sw.js`, `icon.svg`, and `ADCTOX_HOST` / `ADCTOX_ALLOWED_HOSTS` support in `ml/webapp.py` so the web app can be hosted on a remote Ubuntu server (e.g. `ubuntu-a1-osaka`) and installed on Android/iOS phones while preserving loopback security by default.
- Models remain at 0.8 (`releases/models/stable4.json`).

## 0.6.15: clearer evidence review and local review export

- Explicit missing, entered and no-flag lab states; model associations and review order explained beside the results.
- Cancer-match status on each ADC; direct links back to conditions and labs.
- Trial population, arms, sample sizes and source study visible in the evidence detail.
- Save a local text review with inputs, missing values, restrictions, warnings and trial context.
- Shared presentation functions with regression coverage; Pretendard replaces the unlicensed display face in distributed web assets.
- Models remain at 0.8. Existing 0.6.14 fixes are included. No clinical time saving or toxicity-prediction improvement is claimed.


## 0.6.14: reading typed text, numbered disease names, the screens, and the page on a filtered PC (Ubuntu, macOS and Windows)

- **Fixed, disease names with a number after them:** a numbered gene-locus subtype nobody typed reads and lists as its general concept (`CHF NYHA III` no longer reads `hypertrophic cardiomyopathy 3`, `primary biliary cholangitis 3` is `primary biliary cholangitis`). A typed number keeps its subtype (`MODY 3`). 4,495 of 4,655 subtypes have a general concept; the other 160 stay numbered and list last.
- **Changed, reading typed text:** the choice screen opens again for short inputs and low reads whose candidates disagree on organs (`SCD`, `TB`, `MS`, `CAD`). A cancer becomes the patient's only when typed by name or picked; a read that only resembles one is offered, with the non-cancer reading selected. Inputs the judge used to reject between validity 0.9 and its threshold (`TB`, `shingles`, `migrane`) now read with a `Low confidence, check this` mark, and a weak match shows `Confirm this read`.
- **New:** `conf/registry_aliases.yaml`, typed forms that reach a registry condition before the judge reads them (`ild`, `cirrhosis child pugh B`, `CHF NYHA III`). LLM-written and marked as needing clinician review. Short forms with several meanings stay out.
- **New, needs a model bundle:** `ScratchJudge/index_ko.npz`, Korean MONDO names searched for Hangul input. Without the file the app behaves as before; the 0.8 bundle does not have it.
- **Fixed, the page on a PC with a loopback filter (seen with AdGuard):** one response over about 64 KB stalled and the page stayed blank. Responses over 32 KB are compressed for browsers, page files reload up to three times, and API calls try three times (starting an analysis does not).
- **Fixed, conditions:** retyping a condition already added says so instead of adding the next name. `MODY 3` and Enter no longer adds an unrelated disease. Next no longer drops text still in the field. A comma list where every item finds a name is offered item by item, `Cirrhosis, familial` is searched whole, a very long paste answers in about 3 s instead of minutes, and Korean initials that spell a whole name come first (`ㄱㅎㅇ` is hypertension).
- **Fixed, screens:** Read as follows a picked reading, removing a condition drops its reading and priority, the selected ADC stays selected when the ranking changes, Key values read `Sex F` and no longer shift rows, long names and gauges fit at phone width, the labs bar shows CLcr first, and a failed search says why.
- **Fixed, research scripts:** eleven scripts put another checkout's path first on `sys.path`, so later imports could read old code. A model manifest missing a file the judge needs is now refused.
- **Tools:** `ml/missed_warnings.py` (Boxed and W&P miss rates in `bench_judge`), `ml/eval_query_variants.py`, `ml/eval_registry_linking.py`, `ml/risk_sheet.py` with a clinician review sheet (answers blank), `ml/score_refit.py` and `ADCTOX_RELEASE_DEV_GOLD=1` for a refit that releases dev gold concepts into training.
- **Docs:** gold_v0 is described as an LLM silver set, Gemma's role as a training teacher is stated, and the README has a known limits section.
- **Fixed, label reading:** a condition picked from several readings counts like the same concept typed (T-DXd's cardiac rule and the QT and VOD monitor rules fired only when typed). Typed bleomycin reaches brentuximab's contraindication. Typed ESRD or dialysis counts as ESRD, and the condition reads "End-stage renal disease or dialysis". Unentered platelets no longer hide belantamab's Avoid: the states tried for a missing value now come from each ADC's own rule thresholds. Enfortumab's and belantamab's renal detail says what their summary says.
- **New:** the lab's own ULN for bilirubin, AST and ALT, in the browser and the terminal; the value it was read against shows beside ×ULN. Bilirubin 1.7 with ULN 1.0 is 1.7×ULN, not the 1.42×ULN the default gives.
- **Fixed, input:** a decimal comma is an error instead of ten times the value (`0,8` read as 8). A picked MONDO name with a comma stays one condition in the terminal. A cancer with two lab flags no longer crashes the terminal's priority step. A decomposed Hangul paste (macOS) reads like the typed name.
- **Fixed, updates and install:** a blob that failed `--verify-models` is downloaded again instead of re-adopted by its size. `previous.json` is written only after the switch, so a cancelled update keeps the rollback. An asset 404, a dropped connection or a malformed manifest is one line, not a traceback. `install.ps1` stops cleanly while ADCTOX is running and restores the old folder on failure; its launchers survive a non-ASCII account name. `install.sh` runs Python isolated, and an interrupted copy can't pass as a finished release. On Windows a second process no longer binds a port in use.
- **Page:** the guide keeps Tab inside it, ignores PageUp and PageDown and returns focus to `?`. The `/api/v1` page gets its light-theme source colours back, says when loading fails, and has AA contrast and a phone layout.
- **Tests and CI:** a clean clone runs green and leaves its files alone; CI runs all of `tests/`, fails on a text `open()` without an encoding, and pins actions by commit.

## 0.6.13: typed conditions analyse again, and a message when adctox has stopped (Ubuntu, macOS and Windows)

- **Fixed (0.6.11 and 0.6.12): a typed condition failed the organ analysis** with "ValueError: not enough values to unpack" in the browser and the terminal; `ambiguous_conditions` still read the organ judge's links in their pre-0.6.11 form. Registry conditions alone were not affected. A test now runs typed and ambiguous conditions through the analysis job.
- When the page gets no answer at all (the adctox process ended), it says so and how to start it again, instead of the browser's "Failed to fetch".
- Models stay at 0.8.

## 0.6.12: the browser is the default, `adctox-cli` for the terminal (Ubuntu, macOS and Windows)

- **`adctox` with no argument opens the browser screens** (as `adctox --web` and `adctox-web` did); the Windows `ADCTOX.bat` and its shortcuts do too. **`adctox-cli` (`adctox --cli`) opens the terminal screens**, and on Windows `ADCTOX-cli.bat` and `adctox-cli.cmd`; Windows Terminal is used for `--cli` only. `adctox --plain` stays in the terminal. `adctox-web` and `adctox --web` still work.
- install.sh and install.ps1 write `adctox-cli`; an installed app updated with `--update-app` writes it beside `adctox` at its first start.
- Models stay at 0.8.

## 0.6.11: the organ judge alone reads typed text, and a 305 MB model bundle (models 0.8)

- **A typed disease names a registry condition through the organ judge's MONDO or HPO concept**, not by BioLORD name similarity. The organs are always the judge's; the registry condition adds its severity and its label restriction rules. `conf/registry_concepts.json` (built by `ml/registry_concepts.py` from the MONDO and HPO `is_a` hierarchy) lists 1,533 concepts for 34 registry conditions; prior exposures, procedures and measurements are picked from the list.
- Gold dev (304 queries per language): organ F1 unchanged (English 0.7595, Korean 0.6748). Registry conditions are now found for chronic hepatitis B, Child-Pugh B cirrhosis, congestive heart failure, cardiorenal syndrome, Crohn disease and Korean COPD names that the name match missed; the ADC order changes for 4 English and 6 Korean queries, all cirrhosis or heart failure.
- The registry's `mondo_id` for diabetic neuropathy names type 1 diabetes, and two conditions share one id; that column is left for the older audit scripts and is not used for the match.
- **The app no longer loads BioLORD or SapBERT.** When the organ judge is missing or fails, typed conditions are shown as not understood with the reason, instead of going to the older SapBERT linker. A typed condition with no organ no longer gets the unvalidated BioLORD estimate (x0.25); the Unmapped line lists it. The AI suggestions under the search box are the judge's nearest concept names. Symptom and sentence search keeps its n-gram and word scores without the BioLORD term (dev, 88 synthetic queries: top 5 unchanged, top 1 one English query fewer). The Gemma panel and the learned-estimate wizard step are gone.
- **Models 0.8 (`releases/models/stable4.json`, app 0.6.11+): ScratchJudge/ and a 3.2 MB name index, 305 MB in all** (models 0.7: 1.4 GB). `scripts/build_ubuntu_release.py --base-manifest releases/models/stable3.json --drop BioLORD-2023 --drop SapBERT --drop vuln_biolord.pt --names-from <mondo_index.npz>` builds it; the app still runs on a models 0.7 bundle, and the updater accepts either for rollback. Gold dev on a models 0.8 bundle installed through the updater: the same organs, registry conditions, priority levels, order and reading notes as before for all 304 queries per language and 121 two-condition patients.

## 0.6.10: Anthropic Sans Text as the page face, and a fixed web port (Ubuntu, macOS and Windows)

- **The page face is Anthropic Sans Text Light** (59 KB, one weight) in place of Cafe24 Decobox, whose single heavy weight crowded small text. Hangul and ✓ still come from Pretendard. The file carries no public licence and is used here for this personal, non-commercial project only (THIRD_PARTY_NOTICES.md).
- **`ADCTOX_PORT` fixes the web port**, so an SSH tunnel command can stay the same; a bad value or a port in use stops with one line.

## 0.6.9: Label restriction as what the patient has and the rule it meets (Ubuntu, macOS and Windows)

- **Label restriction in the ADC detail shows both sides**: under each organ and status, `Patient` (the entered condition or value that meets the rule, such as Heart failure or Bilirubin 1.67×ULN, or "LVEF not entered") and `Label` (the rule, as "Monitor with bilirubin >1.5 to 3×ULN" or "Not studied if LVEF < 50%"). The server sends the patient side with each row.
- **Indication says it in words**: "Approved for" or "Not approved for" the entered cancer, then "All approved uses" as a list.
- **Hover notes are a summary line and rows** (mark, meaning) instead of running text, for every dotted title.
- **The Windows install check opens the browser page**: the page, both fonts and a search, then Edge draws it and keeps a screenshot.

## 0.6.8: Trial rates as dots under each warning, and the page behind an SSH tunnel (Ubuntu, macOS and Windows)

- **Trial results sit under the label warning they measure**: 20 dots, one per 5 patients in 100, pink for the serious ones, and a line such as "6 in 100 had pneumonitis, 2 serious". An event about as common on the other treatment is grey and says "as on other treatment". The trial, both arms and their rates are on hover. The separate Trial results section, its bars and its scale are gone.
- **The page opens behind an SSH tunnel** (`ssh -L 8080:127.0.0.1:<port>`): the server answers 127.0.0.1, localhost and [::1] on any port. Other host names are still refused, and an API call must come from the page's own address.
- **ADC detail reads as lists**: approved uses one per line, Payload and linker as Payload, Action, Linker, Bystander effect and Target rows, warning names joined with commas.
- **Tips and notes have one sentence per line**, with no semicolons, and the colours they name are the page's (teal, pink). New notes on Payload and linker, Pre-treatment checks, Missing inputs and Warnings on other organs.

## 0.6.7: The browser screens in English, with help (Ubuntu, macOS and Windows)

- **The browser page is in English**: steps Conditions, Labs, Organs, Priority, Results; keys, buttons, errors and progress lines too. Korean input is still read, and comes back under its English name (suggestions, chips, Read as). The terminal screens are unchanged.
- **Help for a first-time user**: a short card on each step the first time it opens (Got it, or Hide all tips; remembered in the browser), a note on every dotted title on hover or focus (Key values, Review order, Label restriction, Patient organs, Other, Organs, Read as and the evidence sections), and a `?` guide in the header with the steps, how to read the results and the keys.
- **Label restriction shows its level**: three rising bars (1 Monitor, 2 Not studied, 3 Avoid), solid up to what the entered values set and dashed up to what a value not entered could set (replacing `?`), then the organ behind it. The bar at the bottom carries the legend.
- **Trial results are bars**: each event is an ADC bar (its serious part pink) over a comparator bar, on one scale per trial (web and terminal detail); the counts stay in the report and the tooltip.
- **Key values are gauges**: ×ULN on 0 to 3 (ticks at 1× and 1.5×), CLcr on 0 to 120 mL/min (ticks at 30, 60, 90), teal or pink past a limit (web; amber or red in the terminal).
- **Result table**: ties repeat their rank faint, `+N` with the other organs on hover, no `-` cells, only a sure Avoid in bold. Organs screen: bars only, no process line. No wordmark in the header. The start screen is the search alone; the body map appears from Labs on.
- Step 4 asks "Which condition should be reviewed first?".
- **The page face is Cafe24 Decobox** (SIL Open Font License 1.1, licence text beside it, 92 KB): Latin letters, digits and ASCII punctuation; symbols such as ×, →, ✓ and Hangul come from Pretendard.
- **One light theme in four colours**: navy #364F6B (text), teal #3FC1C9 (accent, Monitor, within limits), light grey #F5F5F5 (page) and pink #FC5185 (Avoid, boxed warnings, flagged labs); Not studied is plain navy. Text uses darker steps of teal and pink (about 4.7:1 on white). The dark theme is gone; the page stays light under a dark system setting.

## 0.6.6: Marks and bars instead of explanations (Ubuntu, macOS and Windows)

- **No explanatory sentences on the screens** (web and terminal): the start screen's description, the 검사 수치 and 우선순위 hints, the "pick the meaning" line, the model-loading note, the % note under Organs and the "not a risk ranking" note under Review order are gone. 자동 (질환 중증도 순) reads `Auto`.
- **AI 장기 분석 shows bars, not percentages**: each of the three likeliest organs has a bar of its probability (web: the % in the bar's tooltip; terminal: five cells). Organ names take a fixed width, so the bars start and end at the same place on every row.
- **Review order is drawn as tiers**: the first organs as filled chips, then `→` and the next ones plain (terminal: `Cardio Lung → Liver Kidney`), no numbers. The body map drops its numbered legend.
- **Indication is a mark**: a green ✓ or an amber ✕ before the entered cancer (terminal detail too); nothing when no cancer is entered.
- **검사 수치 shows state by the box**: an empty field is a faint dashed box, a value below its organ flag a green box and ✓ (the flag in its tooltip), a value over it an amber box and `→ organ`. The terminal puts ✓ or `→ organ` after the value.
- The result legend keeps `!! Boxed warning` and `! Warning` only.

## 0.6.5: Screens say what their numbers mean (Ubuntu, macOS and Windows)

- **AI 장기 분석**: the Organs column says the % is the AI's confidence that the disease involves the organ, not a side-effect probability (web: under the column title and in each value's tooltip; terminal: beside the title and a line under the table).
- **Review order** replaces Organ priority on the result screen and the body-map legend, marked as the order to review organs in, not a risk ranking (web and terminal).
- **The ADC detail has four parts**: Indication (`Indicated for` / `Not indicated for` the entered cancer, or `No cancer entered`, then the label's indications), Label restriction, Warnings on the patient's organs, and the new Warnings on other organs (the table's Other column with the warning names). The key hint reads `Enter 상세 근거 보기`.
- **검사 수치** tells an empty field from a checked one: empty fields read 미입력; a value checked against an organ flag and below it reads 기준 이내 (the flag, as `AST > 3 x ULN (CTCAE G2)`, in its tooltip); above it, the organ as before.

## 0.6.4: The browser screens, finished (Ubuntu, macOS and Windows)

- **The ADC detail docks as a third column from 1280 px**: the body map gives way first and the table stays whole (#, ADC, Label restriction, Patient organs, Other, Key values, Organ priority all readable with the detail open); narrower screens keep the overlay.
- **The body map is on every step**: empty on 질환, lit by the lab flags on 검사 수치 (Hb 9.1 g/dL lights Blood, bilirubin 2.0 mg/dL lights Liver), as before from AI 장기 분석 on.
- **The result screen prints** (Ctrl-P): Key values, Organ priority, the table, the legend and the open ADC's detail on A4, no page break inside a row or a section.
- **Pretendard Variable is embedded** (SIL Open Font License 1.1, licence text beside it), so the page has the same face on every PC, Korean and Latin alike; the app grows by 2 MB.
- An app updated in place writes `adctox-web` beside `adctox` at its first start of any kind, `--version` and `--help` included.

## 0.6.3: The five screens in the browser (Ubuntu, macOS and Windows)

- **`adctox --web`: the same five steps in the default browser**, served on this computer only (127.0.0.1, a free port; nothing is stored on the server, the page keeps its entries in the tab). A body map beside the screens lights the patient's organs from AI 장기 분석 on (level 1 bright, level 2 dim) and rings the selected ADC's boxed warnings red and its warnings amber; the ADC detail opens as a drawer with the same sections as the terminal panel; keys as in the terminal (PgUp / PgDn, ↑↓, Enter, Esc), clicking works everywhere. The terminal screens stay the default.
- The one-file build carries the page (ml/web/, served from memory); `ADCTOX.bat --web` on Windows.
- **`adctox-web`** does the same: install.sh and install.ps1 write it beside `adctox`, the Windows zip has `ADCTOX-web.bat`, and an app updated with `--update-app` writes it on its next start.

## 0.6.2: Trial results on the patient's organs (Ubuntu, macOS and Windows)

- **The ADC detail panel shows the ADC's main ClinicalTrials.gov trial on the patient's organs**: per organ, the events the label warning on that organ is about, as `pneumonitis 18/257 (7.0%, vs 0.4%), serious 1/257` (count and rate in the ADC arm, the comparator arm's rate, the serious count); an organ the label does not warn about shows its most frequent event and its most frequent serious event. The trial of the patient's cancer when one is typed (HER2+ breast cancer: DESTINY-Breast03), else the largest trial of a labelled regimen. 32 trials from the team's list of 2026-10-29 (data/curated/competition/adc_trials.csv, with the arm and comparator of each), 28 with posted results in the project's ClinicalTrials.gov snapshot; ALFA-0701, POLARIX and LUMINOSITY read `no results posted`. Built by ml/build_trial_ae.py into trial_ae.json; organs by the research corpus's MedDRA mapping (conf/ontology). The order of the ADCs does not change.
- 검사 수치: no `Other` group. Child-Pugh sits under Liver, LVEF under Cardio, UGT1A1 under Genotype.

## 0.6.1: No section numbers (Ubuntu, macOS and Windows)

- The ADC detail panel names the label's warnings without section numbers (`Lung  !!  Interstitial Lung Disease/Pneumonitis`, was `Boxed INTERSTITIAL LUNG DISEASE; 5.1 Interstitial Lung Disease/Pneumonitis`); a boxed warning named inside its section 5 heading is shown once. The payload text no longer ends in its section reference. `--plain` follows.

## 0.6.0: Final design pass (Ubuntu and macOS; Windows stays on 0.5.5)

- **A cancer name the search reads badly comes first in the suggestions**: `HER2 양성 유방암` suggested benign tumours (양성 also means benign); now HER2 positive breast carcinoma is the first row. Six more Korean receptor-status names in cancer_aliases.csv (HER2 음성, 호르몬수용체 양성, ER 양성 유방암; HER2 양성 위암).
- The start screen says the cancer goes in the box too (`기저질환, 암종, 검사 수치로 ...`; the box `질환명, 증상, 암종을 입력하세요`), and the summary line above each step reads `질환`.
- Wrapped lines keep their column: the ADC detail panel (indications, restriction reasons) and Read as on AI 장기 분석 at 80 columns no longer fall back to the left edge.

## 0.5.9: The cancer is typed with the diseases (Ubuntu and macOS; Windows stays on 0.5.5)

- **No separate cancer step.** A cancer typed or picked on the 질환 screen (any MONDO cancer, lymphoma or leukemia; 2,597 terms in data/curated/competition/cancer_mondo.json, built by ml/build_cancer_mondo.py from cancer_roots.csv) is taken as the patient's cancer, and the patient as having that cancer only: the ADCs approved for it come first, the others follow under the `Other cancers` rule. Several cancers take the ADCs of all of them. A cancer counts for no organ, and AI 장기 분석 shows it as `Cancer`.
- A cancer maps to the label cancers under its most specific MONDO root: HER2 positive breast carcinoma to HER2+ breast cancer, breast cancer to all four breast indications, lung cancer to the three NSCLC ones. A solid cancer also takes the tumour-agnostic HER2+ (IHC 3+) solid tumor approval. A cancer no ADC is approved for puts the rule above every ADC.
- cancer_aliases.csv reads the cancer names the linker misreads (폐암 as pneumoconiosis; multiple myeloma as the non-human animal term). BPDCN has no MONDO term and cannot be typed yet.

## 0.5.8: Cancer type first, models load while typing (Ubuntu and macOS; Windows stays on 0.5.5)

- **A cancer step comes first** (암종, before 질환): pick the patient's cancer, or 모름. The ADCs approved for it (FDA label section 1, data/curated/competition/adc_cancers.csv, 19 cancer types covering all 15 ADCs) come first; the others follow under a `Other cancers` rule, in the same order as before. 모름 keeps the order unchanged. `--plain` asks it too, and the saved input keeps it.
- **The encoder and the organ judge load in the background from the start**, while the doctor picks the cancer and types the diseases. On this server the first analysis after typing took 3 s, against about 80 s before.

## 0.5.7: CPU threads (Ubuntu and macOS; Windows stays on 0.5.5)

- **The AI analysis runs torch on at most 4 CPU threads** (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`; `ADCTOX_THREADS` or the user's own `OMP_NUM_THREADS` win). Torch's default, one thread per core, left most threads waiting on a few diseases at a time: on a shared 24-core Xeon, 4 diseases took 14 to 19 s on 24 threads and 1.1 to 1.4 s on 4, and the first analysis with model loading 110 to 134 s against 79 to 84 s.
- The AI 장기 분석 screen no longer explains its colours in a legend line.

## 0.5.6: Organs first shown by the analysis (Ubuntu and macOS; Windows stays on 0.5.5)

- **The first screen no longer shows organs.** The suggestions and the picked chips carry names only; the organs appear on the AI 장기 분석 screen, which every disease now goes through, a disease picked from the registry list too (it used to skip the screen and show its organs first on the result).
- **The analysis shows the organ judge's three most probable organs with their probability** (`Liver 90%  Cardio 16%  Blood 9%`), the calibrated organ output on the text. The organs the ranking uses are green, the others grey; a used organ outside the three follows them. Without the judge (models before 0.7, or the judge failed) the used organs are shown as before.
- No middle dot in the app's text: Read as reads `MONDO (record)`, the step bar is spaced, the payload line uses semicolons.

## 0.5.5 — Read as a doctor would

From going through every screen as a doctor using the app for the first time.
- **Priority step: one pick, no numbers.** "가장 걱정되는 질환" lists the diseases with their organs and "자동 (질환 중증도 순)". The numbered levels, − / + buttons and "1 = 먼저 피함" are gone (terminal screens and `--plain`). Lab findings are not offered as a pick; they keep the automatic order.
- **A picked disease now moves its organs' warnings down.** Among ADCs that are not Avoid / Contraindicated, those with a boxed warning on the picked disease's organs go last, then those with a warning there. Before, the label restriction tier came first, so picking interstitial lung disease still left Datopotamab deruxtecan (lung warning) at #1. Without a pick the order is unchanged; Avoid stays at the bottom either way.
- **Result words:** "Unclear" is gone. The label's "not studied / data limited" reads `Not studied`, a label silent on the patient's state reads `No data`, and a restriction that depends on a value not entered ends in `?` (`Avoid?`), explained in the legend.
- **Missing inputs** lists only the values not entered that could change the restriction (`ANC`, `Child-Pugh`), not the whole domain ("Bilirubin / AST / ALT / Child-Pugh" after bilirubin and AST were entered).
- **The selected ADC's panel** starts with its FDA indications (label section 1, data/curated/competition/adc_indications.csv), lists the label warnings on the patient's organs with their sections (`Lung  !!  Boxed INTERSTITIAL LUNG DISEASE; 5.1 ...`), writes bands as the label does (`bilirubin >1.5 to 3×ULN`, `CLcr 30 to <60`) and the payload without table codes (`topoisomerase I inhibitor`, `Val-Cit PABC`, target).
- **Input screens:** the start screen says in one line what the app does; the lab screen shows the ULN each x ULN uses and the value being entered as x ULN; a value out of range names the field and its unit and moves the cursor there ("Hb: 1–25 g/dL 사이로 입력하세요", was "hb: 1–25"); Backspace on an empty box takes a disease off on the second press, not the first. The result screen's PgDn says `종료`.

## 0.5.4 — Lab boundaries, analysis screen

- **Bilirubin, AST, ALT (x ULN) and Cockcroft-Gault CLcr reach the label thresholds unrounded**, in exact decimal arithmetic. Before, the ratio was rounded to 0.01 first: bilirubin 3.601 mg/dL with ULN 1.2 became 3.00 x ULN and Datopotamab deruxtecan got the "up to 3 x ULN" rule instead of "> 3 x ULN". The CTCAE organ flags compare exactly too (bilirubin 1.8 is not above 1.5 x 1.2). Only the screen rounds, with more digits when a value would otherwise show as a threshold (3.001 x ULN, not 3).
- **AI 장기 분석:** the model names (`BioLORD ── Organ judge ── MLP`) are gone. One line says what the model reports it is doing: "질환 확인 중..." or "장기 분석 중...". A cached analysis shows the table at once.
- **A failed organ judge is no longer silent.** The bundle's older MONDO linker reads the text instead (as before), and the table says so: "Organ judge 오류, MONDO linker로 대체", Read as ends in `linker`. An analysis that cannot finish shows one error line.
- The analysis table, the priority list and the result list scroll with the highlighted row at 80x24; headers stay, and no row runs into the key hint.

## 0.5.3 — Input on the screens only

- **The command line no longer takes conditions or lab values.** `adctox cirrhosis --lab hb=8`, `--crcl`, `--child-pugh`, `--priority`, `--detail` and `--list` are gone; any such argument is refused with exit code 2 and a pointer to the input screens. This also removes three ways to get a result from input nobody checked: without a terminal the app used to analyse a made-up patient (interstitial lung disease), a misspelt `--lab` key was ignored, and `--crcl -10 --child-pugh Z` went into the table as given.
- `adctox --self-test` prints the table for one fixed example patient (alzheimer, cirrhosis, 치매); the install workflow uses it.
- `--plain` keeps the question-and-answer input; an empty condition line ends it instead of filling in an example patient.
- **Key values on the result screen list every entered lab value**, with the organ it marked: `Hb 8 g/dL → Blood`. Before, a value that only marked an organ (Hb, TSH, albumin, ...) was used but the block said "Not entered".
- **A saved run in progress is no longer loaded silently.** At start the app names what is saved (conditions, number of lab values, the file) and offers "이어서 하기" or "새 환자로 시작", which deletes the file.
- pyproject.toml carries the app version (it said 0.4.3); a test keeps the two equal.
- README: the AI judgment was evaluated on English input only; where the input is saved and when it is deleted.

## 0.5.2 — Result screen fix

- **The result screen opens again.** In 0.5.0 and 0.5.1 the installed app stopped with `NameError: __file__` on the result screen: the payload and linker table (data/curated/competition/adc_mechanism_draft.csv) was read from the repository path, which the one-file app does not have. The build now carries the table (ml/build_portable.py), and a test opens every ADC's result panel from the one-file build.
- **A wrong option value is reported, not a traceback:** `--lab hb=abc`, `--lab hb`, `--crcl` without a value, `--priority a` print what could not be read and exit with code 2. The lab step says "숫자를 입력하세요" for a value that is not a number.
- **A disease picked from the list that has neither a label nor a MONDO record** gets the judge's organs for its name, as when the name is typed (`Chosen, name`).

## 0.5.1 — The app reads a disease the way the judge does

With model bundles 0.7+, every way into the analysis now gives the organs the from-scratch judge gives (gold dev: the app and the judge differ on 1 of 304 queries, down from 6; the one left is a registry context condition, 'anthracycline exposure').
- **A disease picked from the search list** gets the judge's organs for that concept (the v5.1 organ table, or what the evidence reader got from its MONDO entry), not the older MONDO crosswalk the list used to show. The two disagreed on 8,121 of the 21,238 concepts the judge has organs for. "Read as" for a picked disease ends in `label` or `record` too. The crosswalk stays for concepts the judge has no organs for.
- **A registry condition no longer overrides the judge's MONDO link by name similarity alone.** 'Type 1 diabetes mellitus' was read as the registry's 'Type 2 diabetes' (BioLORD 0.84) and lost its immune axis. A registry condition still matches by name when the judge links the same concept or does not place the text in MONDO (prior exposures, procedures).
- **A MONDO link of the judge counts at the judge's own threshold (0.65)**, not the older linker's 0.75, and the judge's "no organs" is no longer replaced by organs borrowed from a loosely similar registry condition.
- docs/INSTALL.md: the model download is about 1.4 GiB (was 3.3 GiB with the Gemma judge).

## 0.5.0 — The from-scratch organ judge

- **The disease judge is the model trained from scratch here (x2te), not Gemma**, in model bundles 0.7+ (`ScratchJudge/`, ml/scratch_runtime.py).
  - It is a BERT-base encoder pretrained from random weights on PubMed abstracts, UMLS, MONDO and HPO text (ml/scratch_pretrain.py), and trained to link a typed condition to a MONDO name and to judge its 13 organs (ml/scratch_judge.py, with English misspellings and abbreviations).
  - A linked MONDO concept takes its organs from the v5.1 organ table. A concept without a label takes the organs that the evidence reader got from its MONDO entry (definition, parents, phenotypes, ml/evidence_judge.py). These are precomputed into `concepts.json`; the reader is not shipped.
  - Test, English organ macro-F1, mean of unseen diseases (gold_v0) and known diseases: 0.723, against 0.711 for the tuned Gemma judge and 0.586 for untuned Gemma (ml/docs/overview.md §5). The difference to the tuned Gemma is within the 95% interval.
  - The exported folder gives the same concept and organs as the research code on all 304 gold dev queries (ml/scratch_export.py). CPU: about 0.4 s per typed condition after a 7 s load.
- **AI 장기 분석 screen:** the stage line is `BioLORD ── Organ judge ── MLP`. "Read as" ends in what set the organs: `label` (the organ table), `record` (read from the MONDO entry) or `name` (judged from the typed text alone). The Gemma panel appears only with a Gemma bundle.
- **Not carried over from the Gemma judge:** Korean text outside the Korean MONDO names is not linked (Korean is not evaluated since 2026-10-25), there is no symptom-to-disease output, and an input is no longer offered as "N meanings" to pick from.
- **Updates:** app 0.5 reads `releases/models/stable3.json`. Apps 0.3.8–0.4.x keep reading `stable2.json` (Gemma bundles), because their updater rejects the `ScratchJudge/` folder. `ADC_SCRATCH_JUDGE=0` uses the older linker and judge of the same bundle when it has them.

## 0.4.0 – 0.4.3 — One session, five steps

- **One terminal session from the search page to the result screen.** The result screen used to open in a second curses session after the input steps, with a flash of the shell in between; PgUp on it then restarted the wizard. Now `form.run` owns the whole flow and returns the results; PgUp on the result screen goes back to the priority or lab-value step in place.
- **Five steps, shown as a breadcrumb at the top** (질환, 검사 수치, AI 장기 분석, 우선순위, 결과), the current one lit.
  - The analysis progress and the review are one screen. While it runs, the four stage names stand over one thin bar that fills a quarter per finished stage and eases towards the next quarter meanwhile (0.4.3; the stage spinner of 0.4.0, the braille stream of 0.4.1 and the wave of 0.4.2 were replaced). When it ends, the table builds up under `BioLORD ── SapBERT, MONDO ── Gemma ── MLP   ✓ 3.5 s`.
  - Priority is one screen: the default order is shown at once and can be changed with ←→ or the − / + buttons; PgDn keeps it. The separate "자동 / 직접 정하기" question is gone.
  - After the result screen, the table is printed and the app exits. The `Run again? (y/Enter)` prompt is gone (the `--plain` path keeps it).
- **The clickable `[ ◀ 이전 ] [ 다음 ▶ ]` buttons are gone** (0.4.1). PgUp / PgDn move between screens; the hint at the bottom right stays.
- **Motion** (`ml/motion.py`): a window wrapper records each frame and can play a short transition before showing it. In use: the logo is drawn in from the left on the first screen (420 ms); the analysis table, the Gemma judge panel and the reasons for a newly selected ADC build up row by row (220 ms); the search caret blinks; a newly added disease chip is lit for 0.4 s. The slide between steps (0.4.0) was removed in 0.4.1. `ADC_MOTION=0` turns all of it off; it is off when stdout is not a terminal.
- The portable build embeds `motion` and checks that the screen modules import only embedded modules.

## 0.3.23 — Validity threshold 0.95; each disease listed once

- **The app accepts an input as real when the Gemma judge's validity score is 0.95 or more** (`gemma_runtime.VALID_THR`). The model's own threshold, 0.995, rejected common complaints such as "간이 안좋아요" (0.992). `ADC_VALID_THR=model` restores it.
  - Dev, full pipeline: Korean macro-F1 0.705 → 0.743 (+0.038 [−0.029, +0.058]); English 0.886 → 0.890. Korean coverage went from 0.864 to 0.947. Invalid inputs accepted: 0 in both languages, as before.
  - Cost: 6 of the 2,498 generated invalid inputs now pass (0 before). Some get organs, e.g. 심통 → Cardio and 뇌절 → Neuro.
- **The search list shows each disease once.** A registry disease and its MONDO concept (Heart failure / `heart_failure` and `MONDO:0005252`) are the same row. A disease already listed above is left out of the symptom section, and a disease already added as a chip is left out of the list. Rows match on id, MONDO id, English name or Korean name.

## 0.3.22 — Simpler Gemma panel; repository tidied

- **The Gemma judge panel is a plain tree.** It has no bars, dots, role column or threshold text. These glyphs have different widths in some terminal fonts, so the tree and the right border no longer break or shift. The output that set the organs is green; the others are grey. The last line gives the organs and the step that set them (Gemma align, Gemma organ, Chosen, MONDO, Registry, HPO).
- **Repository:**
  - README rewritten for the current app: search page, PgUp/PgDn, the Gemma judge, the model size (about 3.3 GiB), and screenshots of the current screens (`docs/images/*.svg`, made with `scripts/capture_svg.py`).
  - `docs/INSTALL.md` repaired; its first section was garbled. The in-app model update text that no longer applies is removed. `docs/DISTRIBUTION.md` describes `stable2.json` and the current release commands.
  - Superseded and team documents moved to `docs/archive/`. Private server paths removed from documents. `ml/README.md` is now a short guide to the modules.
  - Old capture images and logs removed. `.gitignore` covers `.pytest_cache/`, `*.log` and `*.pre-centering-bug`.
  - `THIRD_PARTY_NOTICES.md` updated. The Gemma judge's Apache-2.0 text and list of changes (`GemmaJudge-LICENSE.txt`) are attached to the models-0.6 release.

## 0.3.21 — Korean names on abbreviation hits; one translation batch repaired

- **An abbreviation hit shows the disease's Korean name** in the grey column, as every other result does. It showed `약어 ASD`.
- **Translation batch 48 repaired.** Its agent wrote the batch four times. The later passes put other diseases' names on items 100–199, and the merge kept the last pass. An example is `중증 조기 발병 COPD` on an Alzheimer disease concept. The first pass, which matches the batch, is kept.
  - The merge now keeps the first line per disease within a file.
  - An audit of every name for gene symbols or abbreviations absent from the English name finds no other shifted rows.

## 0.3.20 — Gemma judge panel on the AI organ screen

- **The AI organ analysis screen shows what the Gemma judge's four outputs said** for the highlighted input (↑↓ picks the input), as a boxed flow picture:
  - `valid` with its score and the threshold, `organ` with the top three organ probabilities, `align` with the nearest MONDO disease and its cosine, `sym` with the top disease profile.
  - A green ● marks the output that decided something for this input, a grey ○ one that was only computed.
  - The last line shows the final organs and the step that set them: Gemma align, Gemma organ, a chosen disease, the MONDO link, the registry or HPO.
- Hints and labels without parentheses: result-screen keys, the lab-value title, the priority option and the symptom-search status line.

## 0.3.19 — AI organ screen without the explanation line

- The AI organ analysis screen no longer shows the explanation line under its title or the "cached" label. The run time is still shown when the analysis actually ran.

## 0.3.18 — Korean names for every human MONDO disease

- **Korean names for 23,258 of the 23,264 human MONDO concepts in the index** (`data/curated/korean/mondo_ko.jsonl`):
  - Written by 117 Claude Sonnet agents under `data/curated/korean/TRANSLATE.md`, which follows 대한의학회 / KCD style; eponyms are transliterated and gene symbols kept.
  - The 1,514 low-confidence or missing names had a second Sonnet pass; 648 of them were changed. 524 remain low confidence.
  - Where the app already had a name (KCD names whose English is the MONDO name, curated profile names), that name is kept. On those 1,842 concepts the new names are the same in 57% of cases and mostly equivalent spellings otherwise (가성/거짓, 지주막/거미막).
- **English search now shows the Korean name next to every result.**
  - When it does not fit, the highlighted row's two full names are shown under the list.
- **Korean search finds any disease by its Korean name**, e.g. 안검하수, 인슐린 저항.
- **Labels use the preferred MONDO name.** The index's first row was sometimes a synonym.
- **A KCD name now names a concept only when its English is that concept's preferred name.** A KCD name that matches only a synonym still finds the concept, but does not rename it.
- The app file grows from 242 KiB to 896 KiB.

## 0.3.17 — Finer logo, page keys only, scrolling names

- **Logo in braille cells:** 2 × 4 dots per cell, so pixels are square and twice as fine as the half blocks.
  - The flask has bubbles in its drug and the syringe has marks.
  - The art is drawn from shapes by `scripts/logo_art.py` and stored as text in `ml/tui.py`.
- **Only PgUp and PgDn move between screens** (or the ◀ 이전 / 다음 ▶ buttons):
  - Enter, Space and clicks now only pick within a screen: a choice, a meaning, a priority or a lab field.
  - Esc clears a lab field or the search text. On an empty search line it still quits.
  - The result viewer no longer closes on q or Esc.
  - The lab screen's `[ 완료 ]` row is gone.
  - Every step shows `PgUp ◀ 이전   PgDn 다음 ▶` at the bottom right.
- **A long name under the cursor scrolls by itself:** after 1 s it moves 5 characters a second, holds at the end, then starts again.

## 0.3.16 — A drawn logo and a bare search line

- **Logo drawn as objects in 10-pixel letters:**
  - A is a flask holding a yellow drug, T a syringe, o a red toxic drop and X crossed bones. D and C are plain.
  - ADC is cyan, ToX red, 65 columns, 5 lines.
  - Half blocks give square pixels. The letters are drawn so a cell never needs two colours; a test checks this.
- **First screen:**
  - The tagline and the example line are gone.
  - The search box is one line with an underline, with no frame.

## 0.3.15 — Logo and a calmer first screen

- **Block-letter `ADCToX` logo:** ADC in cyan, ToX in red, grey box-line shadow, 50 columns. Below 54 columns or 24 rows it falls back to one coloured word.
- **Calmer first screen:**
  - The empty page is centred vertically, with one example line under the box.
  - The box is at most 66 columns.
  - `다음 ▶` appears only once a disease is picked.
  - The footer has three hints.
  - A second name that does not fit is left out instead of cut mid-word.

## 0.3.14 — A search page first; no model updates inside the app

- **The first screen is a search page:**
  - A centred title and a framed search box.
  - Suggestions open right under the box. Diseases found from symptoms appear under their own heading.
  - Picked diseases sit above the box as chips with their organs (`[ 심부전  Cardio × ]`).
  - Clicking × or pressing Backspace in the empty box takes a disease off.
- **The model update screen (Ctrl+U) is removed from the app.** Models are updated with `adctox --update-models`; `--check-models`, `--rollback-models` and `--verify-models` stay.
- `adctox --help` lists the new keys.

## 0.3.13 — Clinical terms back in English; clearer screens

- **English again for terms that read fine in English:**
  - Result table: Label restriction / Patient organs / Other; None, Monitor, Unclear, Avoid.
  - Organ names everywhere: Liver, Kidney, Cardio ...
  - Panels: Key values, Organ priority, Missing inputs, Pre-treatment checks.
  - Printed headings and `!! Boxed warning   ! Warning   + more organs`.
  - Korean stays only in the guidance lines.
- **First screen:**
  - Disease names follow the typed language: Korean main name for Korean input, English for English.
  - The other language is shown in grey.
  - Diseases found from symptoms come before "입력한 그대로 추가", so Enter takes the best suggestion.
  - Selected rows are no longer cut short.
- **AI organ analysis:** columns Input / Organs / Read as, with the source in grey (MONDO, AI judgment (Gemma), Chosen, Not understood).
- **Priority screen:** one line says why it is asked; the option reads "자동 (질환 심각도 순, 위 순서)".
- **Result screen:**
  - The three-column table is used from 90 columns; narrower terminals show one `Patient: … Other: …` line.
  - The key hints say what each key does.

## 0.3.12 — The four-output judge actually runs in the installed app

- **Fix:** in 0.3.11 the installed (full portable) app left `mondo_index.nearest` out. The Gemma judge then failed quietly and every free text went back to the old path, so Korean sentences stayed unmapped.
  - The full build now includes `nearest`.
  - The build stops when the app calls a `mondo_index` function the build leaves out.
- **Printed AI section in Korean, one line per input:** e.g. `콩팥이 안좋아요 → 신장 (MONDO: kidney failure)`.
  - The "Learned signal" numbers are no longer printed.
  - "Missing inputs" → 입력하면 더 정확해지는 값.

## 0.3.11 and models 0.6 — Four-output Gemma judge

- **One Gemma 4 E2B judge (int8, `GemmaJudge/`) with four outputs:**
  - **organs:** 13 organs, as before.
  - **validity:** a real input or filler.
    - Trained against 2,500 Haiku-written non-inputs, 1,500 of them Korean.
    - Threshold 0.995: the lowest that rejects every held-out non-input.
  - **align:** a SapBERT-space vector. It links Korean text the KCD names miss through the existing MONDO index, at cosine ≥ 0.6.
  - **sym:** symptom description → one of 790 disease profiles. Added to the symptom search with weight 4, chosen on the dev half.
  - Trained on 95k texts. The new ones, all written by Haiku 5.5, are 7,900 symptom sentences, 4,983 Korean disease expressions and the 2,500 non-inputs. 16k HIRA KCD names were also added.
  - Gold concepts and their relatives are excluded.
- **Validity decision:** with models 0.6 the judge's validity output replaces the SapBERT gate (`ADC_JUDGE_GATE`). Korean text is no longer rejected because SapBERT cannot read it.
- **Test results, full app pipeline:**
  - Korean gold: 0.429 → **0.733** (+0.304 [+0.229, +0.384]). The Korean queries were written by Sonnet from the gold set and are used for evaluation only.
  - English gold: 0.832 → 0.841 (+0.009 [−0.002, +0.022]).
  - Invalid inputs accepted: 0 in both languages.
  - Symptom search: top-3 0.763 → 0.839, top-1 0.415 → 0.661.
- **Size and agreement:** 2.39 GB; the int8 judge gives the same organ set as the float one on 97.2% of gold queries.
  - Only the `GemmaJudge/` files change.
  - Apps 0.3.8–0.3.10 read models 0.6 too, but use only its organ output.
- **What was trained:** `ml/docs/gemma_judge.md`.

## 0.3.10 — One search box, a plain analysis screen, a Korean result table

- **One search box on the first screen.** The name / symptom tabs are gone.
  - Names are suggested while typing.
  - Two or more words (a sentence or symptoms) also list diseases found from the symptoms, under their own heading, after a short pause.
- **Suggestion rows:** Korean name, organs, then the English name in grey.
  - Picked diseases keep their Korean name in the list, the step summary and the priority screen.
- **AI organ analysis screen:** one line per typed condition with input, organs and what it was read as (MONDO, AI 판정, 직접 고름, 판정 못 함).
  - The yellow learned-model guesses are no longer shown there.
  - The question "학습 모델 추정을 쓸까요?" is gone: unmapped inputs use the automatic rule (only text read as a disease).
- **Result table and printed output in Korean:**
  - Column headings: 라벨 제한, 이 환자 장기 경고, 다른 장기 경고.
  - Restriction states: 없음, 모니터링, 자료 부족, 피하기. An ADC with no label statement shows 없음 instead of `-`.
  - Organ names: 간, 폐, 신장 ...
  - Panels: 검사 수치, 장기 우선순위, 치료 전 확인, 라벨 조치, AI 장기 분석.
  - An empty second organ cell is left blank.
- "검증 안 된 추정" is shown only when a learned estimate was actually applied.

## 0.3.9 — Natural disease names and organ words

- **Suggestions show the Korean name first:**
  - The English MONDO name follows in grey, e.g. `당뇨 | Diabetes mellitus | 대사`.
  - A HIRA KCD Korean name whose English name is a MONDO name or synonym now suggests that concept, with its organs.
  - The same Korean name is shown once.
  - KCD rows with code notes are dropped, e.g. `천식f54와j45이분류항목이쓰인예`. So are unlinked KCD names longer than 10 characters.
- **Organs as short Korean words instead of the 13-initial strip:**
  - e.g. `신장`, `대사`, `폐 면역`: green when linked, yellow with `?` when estimated.
  - A row without organs says `13개 장기 밖` (a disease outside the 13 axes) or `분석 때 판정` (decided at analysis).
- **Ranking:** a disease with a KCD Korean name ranks like a curated everyday disease, so `diabetes` lists diabetes mellitus before diabetes insipidus.
- **Prepared for a later model bundle** (not released yet):
  - The app can read a Gemma judge with four outputs (organs, validity, a SapBERT-space vector for Korean, symptom → disease).
  - With models 0.5 nothing changes.

## 0.3.8 and models 0.5 — Gemma organ judge

- **Gemma organ judge (`GemmaJudge/`):** a Jev-style decision model on Gemma 4 E2B (Apache-2.0).
  - Built from the first 18 of 35 layers with LoRA and a 13-organ probability head. It is distilled from the Haiku labels on 69k texts, including Korean names, everyday words and symptoms.
  - It returns calibrated probabilities with a temperature and threshold per organ; it generates no text.
  - It reads the typed text itself, Korean too, and decides the organs when the linked disease gives none.
- **Quantization:** int8 weights with bf16 activations through PyTorch's weight-only int8 kernel.
  - 2.38 GB in two files, about 3 GB RAM, about 0.1 s per input on 8 CPU threads.
  - Same organ set as the trained model on 97% of gold queries.
  - Dynamic int8, which also quantizes the activations, and 4-bit tables lost too much and are not used.
- **Gold test, full app pipeline:** macro-F1 0.811 (models 0.4) → **0.832**, +0.021 [+0.005, +0.037]; against the start, +0.172 [+0.107, +0.236]. Invalid inputs accepted: 0.000.
  - Everyday words 0.745 → 0.808; abbreviations 0.714 → 0.759.
- **New model manifest (`releases/models/stable2.json`), read from app 0.3.8.** Apps up to 0.3.7 cannot accept a `GemmaJudge/` folder; they keep reading `stable.json`, which stays at models 0.4.
- **Update:** run `adctox --update-app`, then `adctox --update-models`. Only `mondo_index.npz` is unchanged; the judge adds 2.4 GB.

## 0.3.7 and models 0.4 — Clicks, organ strips, every concept labelled, fast organ judgment

- **Mouse:** every screen can be used with the mouse.
  - Suggestion and selected rows, the mode tabs, lab fields, choices, meanings, and the priority `−` / `+`.
  - `◀ 이전` / `다음 ▶` buttons sit at the top right, and the wheel scrolls.
  - Works in curses (Linux, macOS) and in the Windows terminal stand-in, which now turns on virtual-terminal input and reads SGR mouse reports.
- **Organ strip:** long organ text is replaced by the 13 organ initials `혈간심폐콩위뇌눈피대뼈면귀`. Green marks linked organs and yellow marks organs the learned models estimate.
  - Shown in the suggestion list, the analysis result, the meaning choice, the priority screens and the result header.
  - Printed output keeps the words.
- **Typing:** suggestions update when typing pauses (or every 0.15 s), so fast typing no longer lags. Text the disease gate rejects is not offered as a meaning to pick.
- **Organ labels:** 100 Claude Haiku 5.5 agents labelled every remaining human MONDO concept of the index. That adds 16,831 labels (gold calibration 0.89), about 21,000 in total, under new guide rules (`GUIDE.md` v3 additions):
  - dementia and neurodevelopmental disorders → neurologic;
  - mouth and teeth → gastrointestinal;
  - smell and taste → neurologic;
  - endocrine syndromes → metabolic/endocrine;
  - skin cancers → skin.
- **Fast organ judgment:** a 768→512→13 network reads organs straight from the SapBERT vector the linker already computes. It is a student of the Haiku labels, trained on 65k texts, and adds no download or noticeable time. It is used when the linked disease gives no organ (`AI 판정`).
- **Gold test, full app pipeline:** macro-F1 0.747 (models 0.3) → **0.811**, +0.064 [+0.023, +0.117]. Against 0.660 before any of this work: +0.151 [+0.090, +0.215]. Invalid inputs accepted: 0.000.
  - Everyday words 0.543 → 0.745; synonyms 0.769 → 0.842; typos 0.715 → 0.770.
  - External corpora unchanged or better; CPU time unchanged.

## 0.3.6 — Cleaner name suggestions

- Gene-numbered subtypes (`Alzheimer disease 2` … `8`, `Parkinson disease 12`) no longer fill the suggestion list.
  - They rank low, and are hidden when the general disease is already listed.
  - They come back when a number is typed (`alzheimer disease 2`).
- Veterinary diseases are excluded from suggestions (`Alzheimer disease, domestic cat`, `Diabetes mellitus, koala`).
  - These are the 8,319 MONDO concepts under `non-human animal disease`, still present in the index.
  - The list ships inside the app file.

## 0.3.5 — Abbreviations and several names on one line

- Typing several names on one line separated by spaces (`asd adhd`, `copd htn`) offers `각각 따로 추가`. Each one is then read on its own; before, the whole line was linked as one disease.
- Name suggestions include every disease an abbreviation may mean (NLM LRABR):
  - `adhd` now has a suggestion;
  - `asd` lists atrial septal defect, autism spectrum disorder and the others, marked `약어 ASD`.
- A recognised disease outside the 13 organs (psychiatric, developmental, reproductive) is shown as `None of the 13 organs (...)` instead of `Unmapped`.

## 0.3.4 — Help

- `adctox --help` (also `-h`, `help`) explains in Korean what the program does and how it orders the ADCs, then lists:
  - direct-run usage with an example;
  - result-table options (`--lab`, `--crcl`, `--child-pugh`, `--priority`, `--detail`);
  - the input-screen keys;
  - every update and maintenance command.

## 0.3.3 — Belantamab mafodotin (BLENREP)

- The 15th ADC: belantamab mafodotin (BLENREP; BCMA, MMAF). Its current US label (version 2, 2026-10-06) is fetched into a separate DailyMed snapshot dated 2026-10-15; the other 14 labels stay on the 2026-10-07 snapshot, and their evidence is unchanged.
- Label evidence:
  - Boxed warning: ocular toxicity.
  - Section 5 warning: thrombocytopenia.
  - Grade 3+ laboratory rates come from the combination-therapy tables (marked combo).
- Five label rules, each with a verbatim quote:
  - Hepatic: mild impairment no adjustment; moderate or severe not established.
  - Renal: no adjustment outside dialysis (section 12.3).
  - Ocular: eye exam before every dose.
  - Blood: withhold below 25,000/mcL platelets.
- Two existing tests were tightened. They were exposed by the new drug, and the app logic is unchanged.
  - The priority test now compares ranks within one restriction tier on both sides.
  - The null outcome test now judges the false-positive rate over 8 simulated cohorts instead of one draw.
- Other ADCs approved outside the US or still in trials are listed in `docs/research/adc_candidates_2026-10.md`; they have no US label to read.

## 0.3.2 and models 0.3 — Learned reranker

- Model bundle 0.3 adds a learned reranker to the MONDO index and organ labels re-checked by Haiku 5.5 agents. Only the index changes (about 180 MB); the encoders and the organ-estimate head are reused.
  - The reranker reorders the 10 nearest concepts with 17 features (similarity, gap, rank, spelling overlap, literature frequency, abbreviation table, input shape), and its score decides acceptance.
  - Trained on about 12k inputs: external corpora, two rounds of reviewed Claude-written queries, synthetic typos and abbreviations. Gold concepts and their relatives are never used.
- Gold test, full app pipeline: macro-F1 0.660 → 0.747, +0.087 [+0.037, +0.133]; invalid inputs accepted 0.000 (unchanged).
  - Abbreviations 0.514 → 0.671; typos 0.525 → 0.715.
  - External test corpora all improve (MedMentions +0.024, NCBI +0.013, BC5CDR +0.015, COMETA +0.039).
  - CPU time per query is unchanged within noise.
- App 0.3.2 runs the reranker when the index has one. App 0.3.1 also works with models 0.3, using the new organ labels without the reranker.

## 0.3.1 — Search as you type, symptoms, macOS and one-line installers

- The first screen no longer lists conditions. Typing a disease name shows suggestions below the input and updates them on every key press.
  - Searches registry conditions, 790 disease profiles (Korean names, everyday words, abbreviations), MONDO names and the HIRA KCD Korean names.
  - Also matches Korean initial consonants (`ㄷㄴ`) and corrects misspelt English (`diabetis`).
  - After a short pause, SapBERT suggestions are added and marked `AI`.
- **TAB** switches to a second menu that finds diseases from symptoms, treatments or a whole sentence, in Korean or English (`투석 중이고 숨이 차요`, `short of breath and swollen legs on diuretics`).
  - Ranking uses character n-grams and content words matched against the profiles' names, symptoms and treatments, plus BioLORD for English text.
  - Synthetic test set: top-3 0.76 (Korean 0.74, English 0.80); see `ml/docs/release_0.3.1_evaluation.md`.
- A suggestion picked from the list is taken as that exact concept; the screen that asks which of several meanings was meant appears only for typed text.
- Model updates moved from `U` to **Ctrl+U**, since letters now type into the search.
- macOS (Apple silicon) support: the installer works with the macOS bash 3.2 and installs the PyPI PyTorch build. The memory readout falls back to the peak resident size where `/proc` is missing.
- One-line installers:
  - `install.sh` (Linux and macOS) fetches Python 3.12 with a pinned, checksum-verified uv when no Python 3.12+ is installed.
  - `install.ps1` (Windows) installs the Windows package with Start menu and desktop shortcuts and an `adctox` command.
  - The `One-line install` workflow runs all installers on Ubuntu 22.04/24.04, macOS 14/15 and Windows after each release.
- Concept-organ labels re-checked by 50 Claude Haiku 5.5 agents (`labels/verified_v2.jsonl`, majority of 2–3 votes; 4,465 concepts).
  - The research organ model improves over the crosswalk with a CI above 0 (+0.042 [+0.013, +0.077]).
  - The full pipeline gain did not pass the release rule (+0.030 [−0.014, +0.081]), so the model bundle stays at 0.2.

## 0.3 — App updates and Windows

- The app checks the published app version once a day; when a newer one exists the condition picker says so, and `adctox --update-app` downloads, verifies and switches to it (`--check-app` only checks). A release that needs other Python packages is refused with a pointer to the installer.
- Windows package: unzip `ADCTOX-windows.zip` and double-click `ADCTOX.bat`. It carries its own Python 3.12 and packages, downloads the models on the first start into `%LOCALAPPDATA%\adctox\models`, and updates app and models the same way as Ubuntu.
- The model updater works on Windows: the active bundle is recorded in `current.txt` instead of a directory symlink, the update lock uses `msvcrt`, and blobs are copied where hard links are unavailable.
- Concept organ labels reviewed by clinicians (`data/curated/concept_organs/labels/expert_*.jsonl`) override machine labels; gold concepts and their parents and children never train.

## 0.2.1 — Screen flicker

- Redraws update only the changed cells instead of clearing the whole terminal: the model update and analysis screens redrew about 20 times per second with a full clear and flickered.

## 0.2 — Disease input and model 0.2

- Typed text that reads as several diseases (abbreviations such as `asd`, near-tie names) is confirmed on one screen with every candidate, its organs, `모름`, and PgUp to edit the input.
- Symptoms and findings (`amnesia`, `sleep`) link to the Human Phenotype Ontology when no disease matches; diseases outside the 13 organs show as `MONDO (no organ axis)` instead of `Unmapped`.
- Korean disease names are read through the HIRA KCD master (exact names, then the most general name ending with the typed words) plus a short list of everyday words (`당뇨`, `중풍`, `고지혈증`).
- Learned organ estimates now come from axis heads trained on the FinnGen summaries together with the published Danish disease trajectories (Siggaard et al. 2020): across FinnGen, Danish and US (HuDiNe) held-out data the within-disease ranking has the best mean and worst case (US 0.21 to 0.36). Metabolic/endocrine failed the per-axis check and is left blank, never applied automatically.
- The review shows the learned estimate of three models side by side (Both, Den, Fin: trained on both sources, Danish DTB, FinnGen) with how many agree on each organ; automatic use keeps only organs at least two models agree on (precision 0.63 to 0.77 vs 0.44 for single-model organs on the US HuDiNe cohort).
- Model updates compare the manifest with the installed hashes and download only changed files; `adctox --verify-models` re-hashes everything on request.
- Linking and inference load each model once per process (warm query 2.0 s → 0.02 s on GPU, 1.6 s → 0.1 s on CPU).

## 0.1 — Ubuntu distribution

- Connected development to `ahnhc/ADCToX` with Ubuntu checks on GitHub Actions.
- Added `curl` installation and the `adctox` launcher, with separate app and model versions.
- Added model updates to the condition picker with `U`, plus update/check/version/rollback commands.
- Reuse unchanged encoder, index, and head files; verify SHA256 and compatibility before activation.
- Keep the previous model bundle for rollback and clear linking/inference caches after updates.
- Export released heads as restricted-load tensor checkpoints and indexes without object pickle arrays.
- Keep the current terminal layout and all label evidence behavior.

## 0.0 — Terminal research prototype

- Patient condition and laboratory input, actual model analysis, and grouped organ priorities.
- Existing ADC comparison by label restrictions and patient-priority warnings.
- Full restriction details, separate missing inputs, and scrollable pre-treatment checks.
- BioLORD/SapBERT linking and the FinnGen-trained five-head MLP ensemble.
- Saved baseline, LoRA, structure, and external-validation experiments with their limitations.
