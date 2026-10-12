# Third-party models and evidence

The application, the trained vulnerability head, and upstream encoders are separate artifacts.
Raw collaborator workbooks and FinnGen row-level caches are not included in downloads.

| Component | Source and terms |
|---|---|
| BioLORD-2023 | [Model card](https://huggingface.co/FremyCompany/BioLORD-2023). The author licenses their own contributions under MIT and describes additional UMLS and SNOMED CT licensing requirements. Follow the upstream terms. |
| SapBERT | [Model card](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext), Apache 2.0. |
| MONDO names and hierarchy | [MONDO](https://mondo.monarchinitiative.org/), CC BY 4.0. Index derived from the 2026-10-07 local snapshot. |
| Label evidence | US drug labels obtained through [DailyMed](https://dailymed.nlm.nih.gov/). Factual warning and restriction evidence; source versions remain in the data. |
| FinnGen-trained head | Trained locally on collaborator-provided endpoint association summaries. See [research status](ml/docs/research_status_2026-10-12.md) for the task and limitations. |

The installer downloads the two encoder snapshots directly from Hugging Face at pinned revisions.
They are not rehosted in the Git repository. The model manifest records the source and checksum of every file.
