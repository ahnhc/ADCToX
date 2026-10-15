Model bundle 0.5: Gemma organ judge.

- **What it is:** `GemmaJudge/` is Gemma 4 E2B (Apache-2.0).
  - Only the text decoder is kept, using the first 18 layers, LoRA fine-tuned and merged, with a 13-organ probability head and int8 weights (2.38 GB in two files).
  - It reads the typed text, English or Korean, and gives the organs where the linked disease gives none.
- **Gold test, full app pipeline:** macro-F1 0.832 (models 0.4: 0.811; +0.021 [+0.005, +0.037]). Invalid inputs accepted: 0.000.
- **Needs app 0.3.8 or newer.** It is published in `releases/models/stable2.json`; older apps keep models 0.4.
- **Unchanged:** the MONDO index (with reranker and small organ head), the organ-estimate head, BioLORD-2023 and SapBERT.
