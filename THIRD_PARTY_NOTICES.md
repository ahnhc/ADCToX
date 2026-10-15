# Third-party models and evidence

The application, the trained vulnerability head, and upstream encoders are separate artifacts.
Raw collaborator workbooks and FinnGen row-level caches are not included in downloads.

| Component | Source and terms |
|---|---|
| BioLORD-2023 | [Model card](https://huggingface.co/FremyCompany/BioLORD-2023). The author licenses their own contributions under MIT and describes additional UMLS and SNOMED CT licensing requirements. Follow the upstream terms. |
| SapBERT | [Model card](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext), Apache 2.0. |
| MONDO names and hierarchy | [MONDO](https://mondo.monarchinitiative.org/), CC BY 4.0. Index derived from the 2026-10-07 local snapshot. |
| Human Phenotype Ontology (model 0.2 index) | This product uses the Human Phenotype Ontology (version hp/releases/2026-09-01). Find out more at [hpo.jax.org](https://hpo.jax.org/). CC BY 4.0. Term names, exact synonyms and their embeddings are in the index. |
| SPECIALIST Lexicon abbreviations (model 0.2 index) | [NLM SPECIALIST Lexicon](https://lhncbc.nlm.nih.gov/LSG/Projects/lexicon/) LRABR, 2026 release, open source under the NLM terms and conditions. The index stores abbreviations with the MONDO ids their expansions name. |
| Korean disease names (model 0.2 index) | 건강보험심사평가원 상병마스터 2025.9 (KCD-8 기반), [공공데이터포털](https://www.data.go.kr/data/15067467/fileData.do), 공공누리 제1유형(출처표시). The index stores Korean names with their English names. A short list of everyday Korean words (`data/curated/korean/lay_aliases.tsv`) is this project's own. |
| Gemma 4 E2B (model 0.5 organ judge) | [google/gemma-4-E2B](https://huggingface.co/google/gemma-4-E2B), revision d29ff6b, Apache License 2.0. Modified: text decoder only, first 18 of 35 layers, LoRA fine-tuned on this project's organ labels, merged and quantized to int8; a 13-output classification head added. Redistributed as `GemmaJudge/` in the model release under the same licence. |
| Label evidence | US drug labels obtained through [DailyMed](https://dailymed.nlm.nih.gov/). Factual warning and restriction evidence; source versions remain in the data. |
| Danish disease trajectories (model 0.2 axis heads) | Siggaard T. et al., Disease trajectory browser for exploring temporal, population-wide disease progression in Denmark, Nat Commun 11, 4952 (2020), Supplementary Data 1, CC BY 4.0. The axis heads are trained on derived per-disease, per-organ summaries; no rows are redistributed. |
| FinnGen-trained head (TwoTower ensemble, kept for comparison) | Trained locally on collaborator-provided endpoint association summaries. See [research status](ml/docs/research_status_2026-10-12.md) for the task and limitations. |

The installer downloads the two encoder snapshots directly from Hugging Face at pinned revisions.
They are not rehosted in the Git repository. The model manifest records the source and checksum of every file.
