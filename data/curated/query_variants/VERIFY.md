# Task: check typed disease queries, blind

Another annotator wrote short texts that people might type into a drug-safety search box (users: oncologists, nurses,
pharmacists, sometimes patients). You check them **without knowing which disease the annotator meant**.

You get groups. Each group has a list of candidate diseases (letters, with a short definition) and a few queries that all
mean one of those candidates, or none of them.

For every query, decide:

- `pick`: the letter of the candidate that a clinician reading only this query would take it to mean. If two or more
  candidates fit about equally, or none fits, write `"none"`. Do not guess: an ambiguous query must get `"none"`.
  **General and specific forms.** When the candidates include a general disease and narrower forms of it (for example
  "abdominal aortic aneurysm" and "familial abdominal aortic aneurysm", or "hepatitis C" and "acute hepatitis C"), a query
  that says nothing about the narrower form means the general disease: pick the general one ("AAA", "hep C"). This is not
  ambiguity. Two different diseases at the same level ("artery occlusion" and "vein occlusion", "adenoma" and
  "adenocarcinoma") still get `"none"`.
- `realistic`: `true` only if real people actually type this. For an abbreviation or shorthand, it must be a form in real
  clinical use for that disease, not an invented acronym. For a typo, it must be a plausible slip that is still recognisable.
- `category_ok`: `true` if the stated category fits:
  `lay` everyday words, `abbrev` real abbreviation or acronym, `shorthand` clipped clinical shorthand,
  `variant` spelling, word-order, eponym or British/American form, `typo` misspelling.
- `why`: at most 12 words; required when any of the three is negative.

Be strict. A query you would not trust as training data for a medical search engine should fail.

## Reply

One JSON object, nothing else, with one verdict for every query number `n`:

```json
{"verdicts": [
  {"n": 0, "pick": "C", "realistic": true, "category_ok": true, "why": ""},
  {"n": 1, "pick": "none", "realistic": true, "category_ok": true, "why": "also fits B, the parent"}
]}
```
