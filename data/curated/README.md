# Curated data (machine-labelled; see ml/docs/archive/model_review_2026-10-12.md)

| folder | content | labeller |
|---|---|---|
| `disease_linking/` | pilot gold: 600 typed inputs, candidate pools, two independent annotations, adjudication, `gold_v0.jsonl` | Claude Sonnet (2 annotators + adjudicator) |
| `concept_organs/` | organ labels for 4,000 + 602 human MONDO concepts (`labels/batch_*` first round, `labels/relabel_*` strict round), guide, calibration manifest | Claude Haiku 4.5 |
| `train_queries/` | 2,200 generated typed inputs and their reviews (with planted traps) | Claude Haiku 4.5 |
| `external/` | NCBI Disease Corpus mentions mapped to MONDO via xrefs (public NIH data, Dogan et al. 2014) | corpus annotators |

None of these labels is expert-reviewed. Gold concepts (and their parents/children) are held out of every training set.
The first Haiku round contains batches labelled by keyword scripts; ml/linking_models.py only uses batches that passed the
calibration rule, label pairs that agree, and the strict round.
