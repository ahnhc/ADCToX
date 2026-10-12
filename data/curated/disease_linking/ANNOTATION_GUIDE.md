# Disease-linking gold: annotation guide (pilot v0)

This gold set measures Task A of `ml/docs/model_accuracy_plan_2026-10-12.md`: free-text comorbidity -> disease concept -> organs.
The pilot was labelled by two independent LLM annotators (Claude Sonnet 5.5 subagents) and then adjudicated.
**It is an LLM-annotated silver set, not expert gold.** Clinician review is still required before any number from it is quoted as accuracy.

## What a record is

One typed input, as a user would type it into the terminal's condition box. The input is English and lower or mixed case.
It describes an adult cancer patient's comorbidity or history.

## Fields each annotator fills

| field | values | meaning |
|---|---|---|
| `validity` | `valid`, `ambiguous`, `non_disease`, `invalid` | see below |
| `concepts` | list of candidate MONDO IDs from the pool, may be empty | every candidate that is an acceptable reading of the input |
| `best` | one MONDO ID or null | the single best candidate. Null when none in the pool is acceptable or the input is not `valid` |
| `pool_miss` | true/false | true when the input is a valid disease but no pool candidate is an acceptable reading |
| `organs` | subset of the 13 axes | the organs the condition itself affects (see below). Fill for `valid` and, where one reading is clear enough, `non_disease` |
| `confidence` | `high`, `medium`, `low` | |
| `note` | short text | reason for any non-obvious choice |

### validity

- `valid`: names one disease or a closely related family of readings that share organs. Typos, abbreviations with one dominant clinical meaning, and lay terms with one clear meaning count.
- `ambiguous`: a medical-sounding input with two or more plausible diagnoses on different organs, or so vague that no diagnosis can be chosen (`lung hole`, `ms` without context, `bad heart`).
- `non_disease`: a procedure, exposure, symptom, lab finding or history item rather than a disease (`prior chest radiation`, `on dialysis`, `high creatinine`). The system may still use it. Mark `organs` if they are clear.
- `invalid`: not medical at all, gibberish, or a non-condition (`banana`, `xqzv`, `none`, `n/a`).

### concepts and best

Accept a candidate when a clinician reading the input would code it as that concept.
- An **exact** synonym is acceptable.
- A slightly **broader** parent is acceptable only when the input itself is that broad, for example `kidney disease` -> chronic kidney disease is NOT acceptable but kidney disorder is.
- A **narrower** child is not acceptable unless the input names it. Stage or subtype in the input must be respected: `ckd 3` -> chronic kidney disease stage 3, not stage 5.

Never invent IDs. Choose only from the pool shown.

### organs (13 axes)

`haematologic, hepatic, cardiovascular, pulmonary, renal, gastrointestinal, neurologic, ocular, dermatologic, metabolic_endocrine, musculoskeletal, infectious_immune, otologic`

Mark the organs whose reserve the condition **itself directly damages or occupies**, the ones where a drug toxicity would land on an already affected organ. Judge from clinical knowledge, **not** from the candidate names.
- Include every directly involved organ: diabetic nephropathy -> renal + metabolic_endocrine; chronic hepatitis B -> hepatic + infectious_immune.
- `infectious_immune` covers chronic infection, immunodeficiency and autoimmune or immune-mediated disease (ITP, lupus, rheumatoid arthritis, HIV).
- `cardiovascular` covers heart and vessels, including hypertension, thrombosis and stroke as a vascular event (stroke is also neurologic).
- Do not add organs reached only through a rare complication or a later risk (type 2 diabetes alone -> metabolic_endocrine, not renal or cardiovascular).
- Cancer itself is out of scope. If the input is a cancer, mark the organ of the cancer.

## Process

1. Two annotators label every record independently, without seeing each other's output, the intended concept or any system output other than the shuffled candidate pool.
2. Disagreements on `validity`, `best` or `organs` go to an adjudicator, who sees both labels and writes the final record and the reason.
3. Records keep both raw labels, the final label and an adjudication note.
