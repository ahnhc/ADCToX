# Changelog

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
