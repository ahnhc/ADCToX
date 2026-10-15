Model bundle 0.3.

- **MONDO index v4 adds a learned reranker.** It reorders the 10 nearest concepts and decides acceptance.
  - Gold test, full app pipeline: macro-F1 0.660 → 0.747, +0.087 [95% CI +0.037, +0.133]. Invalid inputs accepted: 0.000.
  - No external test corpus got worse.
  - Details: `ml/docs/release_0.3.1_evaluation.md` §4.
- **Organ labels re-checked by Claude Haiku 5.5 agents** (majority of 2–3 votes, 4,465 concepts), with organ votes from ICD, MeSH, DOID and HPO cross-references as low-weight features. These are machine labels; clinician labels will override them when they arrive.
- **Unchanged:** the organ-estimate head (same SHA256), BioLORD-2023 and SapBERT at the same pinned revisions.

Update with `Ctrl+U` in the app or `adctox --update-models`. Only `mondo_index.npz` is downloaded. App 0.3.2 is needed to use the reranker; app 0.3.1 reads the new index and ignores the reranker.
