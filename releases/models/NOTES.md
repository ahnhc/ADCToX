Initial independent model bundle, version 0.0.

- Frozen BioLORD-2023 and SapBERT at pinned Hugging Face revisions.
- FinnGen-trained five-head TwoTower MLP ensemble.
- SapBERT MONDO index with the current 13-axis crosswalk.
- No additional training in this release. Tensor and index serialization were converted for restricted loading, preserving predictions.

Install or update through the app using `adctox --update-models`. The installer uses `releases/models/stable.json`; unchanged files are reused by SHA256. The two encoder snapshots come directly from Hugging Face. This release contains the trained head, MONDO index, and manifest, with no raw collaborator workbooks or FinnGen rows.
