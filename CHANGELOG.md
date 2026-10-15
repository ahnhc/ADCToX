# Changelog

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
