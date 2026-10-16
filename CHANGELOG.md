# Changelog

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
