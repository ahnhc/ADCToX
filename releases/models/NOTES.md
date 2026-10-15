Model bundle 0.4.

- **Organ labels for every human MONDO concept of the index:** about 21,000 concepts, Claude Haiku 5.5, gold calibration 0.89.
  - New rules: dementia, autism and ADHD → neurologic; mouth/teeth → gastrointestinal; skin cancers → skin.
  - These are machine labels; clinician labels override them when they arrive.
- **Fast organ judgment (index keys `oh_*`):** a small network on the SapBERT vector of the typed text. App 0.3.7 uses it when the linked disease gives no organ.
- **Reranker:** retrained on the new index.
- **Gold test, full app pipeline:** macro-F1 0.811 (models 0.3: 0.747; +0.064 [+0.023, +0.117]). Invalid inputs accepted: 0.000. Details: `ml/docs/release_0.3.1_evaluation.md` §5.
- **Unchanged:** the organ-estimate head (same SHA256), BioLORD-2023 and SapBERT.

Update with `Ctrl+U` or `adctox --update-models`; only `mondo_index.npz` is downloaded. App 0.3.6 and older read the index but not the fast judgment.
