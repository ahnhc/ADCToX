# Task: what people actually type for a disease

You get a batch of diseases from the MONDO ontology. For each disease, write the short texts that a real person would type into
a drug-safety search box when they mean **exactly this disease**, but that are not its official name or listed synonyms.
The searchers are oncologists, nurses, pharmacists, and sometimes patients or family members, typing in English.

Each disease comes with: `id`, `name`, `synonyms` (already known; do not repeat them), `related_synonyms`, `definition`,
`parents` (broader diseases) and `siblings` (other diseases under the same parents).

## Categories

| category | what it is | how many per disease | good | bad |
|---|---|---|---|---|
| `lay` | everyday words a patient or family member would use | 0 to 3 | "bleeder disease" (haemophilia), "sugar diabetes" | "ear tumor" for benign middle ear neoplasm (fits many diseases) |
| `abbrev` | an abbreviation or acronym that clinicians really use for this disease | 0 to 3 | "CKD", "DLBCL", "HCM" | an invented acronym ("BNEM"); a full name labelled as abbreviation |
| `shorthand` | clipped clinical shorthand from notes and handovers | 0 to 3 | "pl eff" (pleural effusion), "hep B", "afib" | anything you have not seen used |
| `variant` | spelling, word-order, eponym or British/American forms not in the synonyms | 0 to 2 | "oesophagitis", "Hodgkin's disease", "anaemia, iron deficiency" | a synonym already listed (case-insensitive) |
| `typo` | a misspelling a hurried typist really makes, still recognisable | 0 to 1 | "haemophelia A", "pnuemonia" | random letter noise; more than one error; a typo for a disease that already has other items |

**Where the effort goes.** `lay`, `abbrev` and `shorthand` are the point of this task: the search engine already copes with
most misspellings, but not with everyday words or with the abbreviations and shorthand clinicians type. Consider those three
for every disease first. Write a `typo` only when the disease has no `lay`, `abbrev`, `shorthand` or `variant` item,
and only for a word people really misspell.

## Rules

1. **Exactly this disease.** A clinician who reads your text with no other context must think of this disease (or accept it
   as the obvious reading). If the text would equally mean a parent, a sibling or another disease, leave it out. Check the
   `siblings` and `parents` lists for this.
2. **Real usage only.** For `abbrev` and `shorthand`, write only forms you are confident are in real clinical use for this
   disease. When unsure, write nothing. Zero items in a category is normal and expected for rare diseases.
3. **Rare and genetic diseases.** Most will only have a `variant` or a single `typo`, and some will have nothing. Do not
   invent everyday words for diseases that patients would not name in everyday words.
4. **No repeats.** Do not repeat the name, a synonym, or another item of the same disease (ignore case, spaces, punctuation).
5. **English only.** Up to 120 characters; usually 2 to 40.
6. Do not explain. Do not add organ, drug or treatment information.

## Reply

One JSON object, nothing else:

```json
{"items": [
  {"id": "MONDO:0005300", "query": "CKD", "category": "abbrev"},
  {"id": "MONDO:0005300", "query": "kidney failure that keeps getting worse", "category": "lay"},
  {"id": "MONDO:0005300", "query": "chronic kidney dz", "category": "shorthand"}
]}
```

A disease with no item you are confident about gets no items.
