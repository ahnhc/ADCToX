# Curated data (machine-labelled; reviewed by Claude Opus 5.5 on 2026-10-17, see review_opus/README.md)

| folder | content | labeller |
|---|---|---|
| `disease_linking/` | pilot gold: 600 typed inputs, candidate pools, two independent annotations, adjudication, `gold_v0.jsonl` | Claude Sonnet (2 annotators + adjudicator) |
| `concept_organs/` | organ labels for 20,816 human MONDO concepts: `labels/batch_*` and `relabel_*` (Haiku 4.5), `verified_v2/v3` (Haiku 5.5), `verified_v4` (Opus 5.5 review, 678 corrections); guide, calibration manifest | Claude Haiku 4.5 / 5.5, Opus 5.5 |
| `judge2/` | Gemma judge training text: 7,890 symptom sentences, 4,849 Korean expressions, 2,344 invalid inputs (`gen/`), Korean evaluation queries (`gen/koeval_*`, evaluation only) | Claude Haiku 5.5 / Sonnet, reviewed by Opus 5.5 |
| `disease_profiles/` | 790 disease profiles (names, Korean names, abbreviations, symptoms) for the search and the judge's symptom output | Claude Sonnet, reviewed by Opus 5.5 |
| `korean/` | Korean names for 23,258 human MONDO concepts (`mondo_ko.jsonl`), translation rules, review passes | Claude Sonnet, reviewed by Opus 5.5 |
| `review_opus/` | the 2026-10-17 review: instructions, 286 verdict files, control manifests, reports, CSV copies of every dataset | Claude Opus 5.5 |
| `train_queries/` | 2,200 generated typed inputs and their reviews (with planted traps) | Claude Haiku 4.5 |
| `external/` | NCBI Disease Corpus mentions mapped to MONDO via xrefs (public NIH data, Dogan et al. 2014) | corpus annotators |

None of these labels is expert-reviewed. Gold concepts (and their parents/children) are held out of every training set.
The first Haiku round contains batches labelled by keyword scripts; ml/linking_models.py only uses batches that passed the
calibration rule, label pairs that agree, and the strict round.
