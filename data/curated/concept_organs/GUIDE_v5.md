# Organ labels v5: instructions for the labelling model

You label MONDO disease concepts with the organs they affect. The labels train a model that reads a patient's comorbidity and
tells an oncologist which organs are already damaged, so that a cancer drug's toxicity on those organs can be weighed. Every
label must be one a careful internist would sign.

Work concept by concept. Each input record gives the MONDO name, synonyms, definition, parents and grandparents, children,
MONDO's anatomical locations and features, causal genes, cross-references (OMIM, Orphanet, ICD, MeSH, NCIt) and, for many rare
diseases, HPO phenotype annotations with their frequency (`hpo_phenotypes`). Use all of it with your clinical knowledge:
- HPO frequencies are the best evidence for the 30% rule. "very frequent (80-99%)" and "frequent (30-79%)" phenotypes of an organ support `involved`; "occasional (5-29%)" ones do not.
- When the definition is empty, rely on the name, the parents, the genes and the phenotypes.
- Do not guess from the name alone when the definition says otherwise.
- A gene name alone is not evidence of an organ.

## The 13 organ axes

| axis | covers |
|---|---|
| `haematologic` | blood cells, bone marrow, coagulation, spleen as a blood organ |
| `hepatic` | liver, intrahepatic and extrahepatic bile ducts, gallbladder |
| `cardiovascular` | heart, pericardium, arteries, veins, capillaries; hypertension, thrombosis, vasculitis of vessels |
| `pulmonary` | lungs, airways from the nose to the alveoli (nose, sinuses, pharynx, larynx, trachea, bronchi), pleura |
| `renal` | kidneys, ureters, bladder, urethra |
| `gastrointestinal` | mouth, teeth, gums, salivary glands, oral mucosa, oesophagus, stomach, intestines, anus, pancreas (exocrine) |
| `neurologic` | brain, spinal cord, peripheral nerves, neuromuscular junction; dementia, delirium, neurodevelopmental disorders; smell and taste |
| `ocular` | eye, retina, optic nerve as part of the eye, eyelids, lacrimal system |
| `dermatologic` | skin, hair, nails, subcutis |
| `metabolic_endocrine` | endocrine glands (pituitary, thyroid, parathyroid, adrenal, endocrine pancreas, gonads as hormone organs); diabetes; lipid, electrolyte, acid-base and inborn metabolic disorders |
| `musculoskeletal` | bones, joints, skeletal muscle, tendons, ligaments, connective tissue of the locomotor system |
| `infectious_immune` | a mechanism axis: infection, immunodeficiency, autoimmune or immune-mediated disease, lymphoma |
| `otologic` | ear: external, middle, inner ear, hearing, vestibular organ |

Reproductive organs, breast and purely psychiatric conditions have no axis.

## Two tiers per concept

For each concept give two lists.

**`primary`**: the organs the disease is located in or defined by.
- The organ the disease is named after or arises in (IgA nephropathy → renal; retinitis pigmentosa → ocular).
- The organ of a tumour's origin (a hepatoblastoma → hepatic; a skin melanoma → dermatologic; a CNS tumour → neurologic).
- The organs in the disease's own definition or its major diagnostic criteria.
- Mechanism axes, added whenever they apply:
  - `infectious_immune` for an infection, an immunodeficiency, an autoimmune or immune-mediated disease, or a lymphoma.
  - `metabolic_endocrine` for a disease of an endocrine gland or a metabolic disorder.
  - `haematologic` for a disease of blood cells, marrow or coagulation.
- At least one organ unless the concept has no axis (see below). At most 3.

**`involved`**: other organs that the disease itself directly damages in a substantial share of patients.
Add an organ only when **all** of these hold:
1. **Direct damage or occupation** of that organ by the disease process: inflammation, infiltration, deposition that impairs function, tumour, infarction, fibrosis, loss of function.
2. **Common:** it happens in at least about 30% of patients over the typical course, **or** it is one of the disease's major diagnostic criteria.
3. **Part of this disease, not a separate one:** it is not usually diagnosed and coded as a separate disease that the condition raises the risk of.
   For example, the eye in diabetes is diabetic retinopathy, a separate disease, so it is not `involved` for diabetes.
4. **Not caused by treatment.**

Do **not** add an organ for:
- transient signs without lasting damage (fever, a passing rash, conjunctival injection);
- symptoms without damage (headache, fatigue);
- deposits that do not impair function (Kayser-Fleischer rings);
- complications in fewer than about 30% of patients that are not diagnostic criteria;
- a later risk;
- a disease that merely co-occurs (inflammatory bowel disease with primary sclerosing cholangitis).

**Caps:** `primary` + `involved` hold at most 4 organs in all. If more qualify, keep those damaged most often and most severely, and note the rest in `basis`.

**Umbrella concepts** (a group with subtypes, e.g. "Ehlers-Danlos syndrome"): label what applies to most patients across the group, not the rarest subtype.

**No axis:** a real human disease whose organs are all outside the 13 axes (purely reproductive, obstetric, breast, or psychiatric: mood, anxiety, personality, psychotic, eating and substance-use disorders) gets `primary: []`, `involved: []`, `no_axis: true`. A psychiatric disease that damages one of the axes (alcoholic liver disease) is labelled by that organ.

## Worked examples

These are illustrations of the rules; follow the rules, not the examples, when a case differs.

| concept | primary | involved | why |
|---|---|---|---|
| MONDO:0005342 IgA nephropathy | renal, infectious_immune | – | named organ; immune-mediated |
| MONDO:0019200 retinitis pigmentosa | ocular | – | |
| MONDO:0043373 sudden sensorineural hearing loss | otologic | – | |
| MONDO:0000984 thalassemia | haematologic | – | bone changes and iron overload belong to severe forms and to treatment; not most patients across the group |
| MONDO:0005354 chronic hepatitis C virus infection | hepatic, infectious_immune | – | cirrhosis and cryoglobulinaemia are separate diseases or under 30% |
| MONDO:0005136 malaria | infectious_immune, haematologic | – | the parasite infects red cells; cerebral malaria is a minority |
| MONDO:0000565 infective endocarditis | cardiovascular, infectious_immune | – | emboli are complications in a minority |
| MONDO:0012727 Kawasaki disease | cardiovascular, infectious_immune | – | a vasculitis; rash and conjunctival injection are transient signs |
| MONDO:0008538 giant cell arteritis | cardiovascular, infectious_immune | – | permanent visual loss is under 30%; headache is a symptom |
| MONDO:0010200 Wilson disease | hepatic, metabolic_endocrine | neurologic | neurologic damage in about half; Kayser-Fleischer rings do not impair the eye |
| MONDO:0013433 primary sclerosing cholangitis | hepatic, infectious_immune | – | bile ducts are hepatic; the inflammatory bowel disease it often comes with is a separate disease |
| MONDO:0010837 primary hyperparathyroidism | metabolic_endocrine | musculoskeletal | bone loss is common; kidney stones are under 30% and a separate disease |
| MONDO:0008219 pemphigus vulgaris | dermatologic, infectious_immune | gastrointestinal | oral mucosa is involved in nearly all; mouth is gastrointestinal |
| MONDO:0007947 Marfan syndrome | cardiovascular, musculoskeletal | ocular | aortic root dilatation and skeletal features define it; lens dislocation is a major criterion |
| MONDO:0001734 tuberous sclerosis | neurologic, dermatologic | renal | brain and skin lesions are major criteria; renal angiomyolipomas in most |
| MONDO:0018975 neurofibromatosis type 1 | neurologic, dermatologic | – | Lisch nodules do not impair the eye; optic glioma and scoliosis are under 30% |
| MONDO:0016367 dermatomyositis | musculoskeletal, dermatologic, infectious_immune | pulmonary | interstitial lung disease in about a third or more |
| MONDO:0007191 Behcet disease | infectious_immune, gastrointestinal | dermatologic, ocular | oral ulcers are required for diagnosis (mouth is gastrointestinal); skin lesions and uveitis in about half or more |
| MONDO:0010526 Fabry disease | metabolic_endocrine | renal, cardiovascular, neurologic | lysosomal storage; kidney, heart and small-fibre nerve damage in most; angiokeratoma noted in basis because of the cap of 4 |
| MONDO:0009693 multiple myeloma | haematologic | musculoskeletal, renal | plasma cell neoplasm; bone lesions in most, kidney impairment in about a third or more |

## Output

One JSON object per line, one line per input concept, in input order:

```json
{"id": "MONDO:0010200", "primary": ["hepatic", "metabolic_endocrine"], "involved": ["neurologic"], "no_axis": false, "confidence": "high", "basis": "copper accumulates in liver and brain; neuro in ~50%; KF rings non-damaging"}
```

- `primary`, `involved`: axis names from the table only, no organ in both lists.
- `no_axis`: true only with both lists empty.
- `confidence`:
  - `high`: you know this disease well.
  - `medium`: the rules leave a close call (an organ near 30%).
  - `low`: you are unsure what the disease is. Use the definition and ancestors before choosing `low`.
- `basis`: at most 200 characters. Give the reason for each `involved` organ with a rough frequency, and any organ you left out at a close call or because of the cap.

## Before you finish a batch

1. One line per input concept, same ids, same order, valid JSON.
2. Only the 13 axis names; no organ in both lists; at most 3 in `primary` and 4 in all.
3. Every `involved` organ meets all four conditions above. Remove any that is only a risk, a separate disease, a treatment effect, a transient sign or a minority complication.
4. Re-read the `medium` and `low` lines once.
