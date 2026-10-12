# Concept organ labels: guide (v1, Haiku labelling round)

Purpose: training labels for a learned MONDO concept -> organ model that replaces or corrects the ancestor-name crosswalk.
Labels come from Claude Haiku 4.5 agents. **They are machine labels, not expert labels.** 20% of concepts are labelled twice
for agreement, and every batch has hidden calibration concepts scored against the Sonnet pilot gold.

## Input line

`- MONDO:id | name | syn: ... | ancestors: nearest is_a ancestors | def: ...`

## Output (one JSON object per line, one line per input concept)

```json
{"id": "MONDO:0005148", "organs": ["metabolic_endocrine"], "scope": "axis", "confidence": "high"}
```

- `organs`: subset of the 13 axes below. It may be empty.
- `scope`:
  - `axis`: at least one organ applies.
  - `no_axis`: a real human disease whose organs are all outside the 13 axes (for example reproductive-only or purely psychiatric).
  - `unclear`: the name and definition are not enough to judge.
- `confidence`: `high`, `medium` or `low`.

## The 13 axes

`haematologic, hepatic, cardiovascular, pulmonary, renal, gastrointestinal, neurologic, ocular, dermatologic,
metabolic_endocrine, musculoskeletal, infectious_immune, otologic`

Mark the organs that the disease **itself directly damages or occupies**: the organs where an extra drug toxicity would land on an
already affected organ.

- Include every directly involved organ, at most 4. For a multi-system syndrome, pick its main affected organs.
- `infectious_immune`: infections, immunodeficiency, autoimmune or immune-mediated disease. Add it next to the organ affected.
- `cardiovascular`: heart and blood vessels, including thrombosis, hypertension, vasculitis of vessels, and vascular stroke (stroke is also neurologic).
- `metabolic_endocrine`: endocrine glands, diabetes, lipid, electrolyte and metabolic disorders.
- `haematologic`: blood cells, marrow, coagulation. Leukaemia and lymphoma are haematologic (+ infectious_immune for lymphoma).
- Tumours: the organ of the tumour (a CNS tumour -> neurologic; a skin melanoma -> dermatologic; a bone sarcoma -> musculoskeletal).
- Do not add organs reached only by a rare complication or a later risk (type 2 diabetes alone -> metabolic_endocrine, not renal).
- Gallstones and varices -> gastrointestinal (gallstones also hepatic). Biliary disease -> hepatic.
- Purely reproductive, obstetric or psychiatric conditions without one of the 13 axes -> `organs: []`, `scope: no_axis`.

Reference examples (from the pilot gold conventions):

| concept | organs |
|---|---|
| immune thrombocytopenia | haematologic, infectious_immune |
| primary biliary cholangitis | hepatic, infectious_immune |
| cholelithiasis | gastrointestinal, hepatic |
| pulmonary embolism | cardiovascular, pulmonary |
| obstructive sleep apnea | pulmonary |
| crohn disease | gastrointestinal, infectious_immune |
| ischemic stroke | cardiovascular, neurologic |
| myasthenia gravis | infectious_immune, neurologic |
| type 1 diabetes mellitus | infectious_immune, metabolic_endocrine |
| gout | metabolic_endocrine, musculoskeletal |
| herpes zoster | dermatologic, infectious_immune, neurologic |
| urinary tract infection | infectious_immune, renal |
| diabetic nephropathy | metabolic_endocrine, renal |
| systemic sclerosis | dermatologic, gastrointestinal, infectious_immune, pulmonary |
| neurofibromatosis type 2 | neurologic, otologic |
| hyperlipidemia | metabolic_endocrine |
| fibromyalgia | musculoskeletal |

## Self-check before finishing

1. One line per input concept, same IDs, valid JSON.
2. Only the 13 axis names in `organs`.
3. Re-read the low-confidence lines once.
