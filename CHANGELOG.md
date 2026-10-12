# Changelog

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
