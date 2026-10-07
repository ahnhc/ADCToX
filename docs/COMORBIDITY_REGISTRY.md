# Comorbidity registry

`conf/comorbidity_registry.csv` is the closed list of conditions the system accepts.
Nothing outside it can be entered; the API rejects unknown ids with HTTP 422.

## Why the ontology ids are pinned by hand, not resolved at runtime

Resolving a condition label against a disease ontology at runtime looks convenient and
is unsafe. Measured on 36 trial lookups against the Open Targets disease index,
**3 resolved silently to the wrong disease**:

| label | naive resolution | why it is wrong |
|---|---|---|
| ocular surface disease | brain small vessel disease 1 | unrelated |
| left ventricular dysfunction | left ventricular noncompaction | a congenital cardiomyopathy, not acquired dysfunction |
| QT prolongation | familial long QT syndrome | a germline channelopathy, not drug-induced prolongation |

A silent mis-resolution does not raise; it produces a plausible-looking organ mapping
derived from the wrong disease. So every id in the CSV is hand-checked and frozen, and
the resolver is never called on user input.

Two further traps the pinned ids record:

* **Not everything is a MONDO node.** Open Targets' disease index mixes in HPO terms:
  `thrombocytopenia` resolves to `HP:0001873`, not a `MONDO:` id. Code must not assume
  the prefix.
* **ICD-10 is not a usable join key.** Only ~3.5% of MONDO terms carry an ICD10CM
  cross-reference, and only about half of the conditions here do. The `icd10_prefix`
  column is for human reference and for the Elixhauser grouping, not for lookup.

Rows whose `mondo_id` is `MONDO:0000001` (the ontology root) or carries a
"Hand-pinned; verify before use" note are exposure or procedure histories rather than
diseases, and have no meaningful ontology node. They are kept because protocols exclude
on them, and they are flagged so no analysis treats them as diseases.

## Severity is an elicited prior, not a fitted quantity

`severity` scales the objective weight (`w_o = 1 + lambda * severity`). It is **not**
learned, because no public dataset of (ADC, comorbidity, outcome) exists -- zero trials
report comorbidity-stratified organ adverse-event rates. The magnitudes are read off the
quantitative thresholds inside trial exclusion criteria ("LVEF < 50%",
"creatinine clearance < 30"), which is why `severity_basis` is a required column: a row
without a cited basis is a bug.

Anything derived from this column must be displayed with `source: elicited_prior`, never
pooled with model output.
