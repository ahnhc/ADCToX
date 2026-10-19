# Korean evaluation questions: review instructions

ADCTOX reads what a Korean patient or clinician types as a comorbidity. These Korean questions test it. Each was translated
from an English question; you check that the Korean one is a fair test of the same thing.

## Input (`batches/kr_NN.json`)

Each item: `qid`, `group` (questions about the same disease share it), `category`, `en` (the English question), `ko` (the Korean
question), `disease` (the intended MONDO disease; empty for questions that name no disease).

Categories:
- `canonical`: the standard Korean name. `synonym`: another accepted name.
- `abbrev`: an abbreviation Korean clinicians really write (English letters such as "COPD", or Korean short forms such as "갑저").
- `typo`: a realistic misspelling a Korean typist makes (wrong vowel, wrong or missing final consonant, adjacent key, spacing).
- `lay`: plain words a patient uses.
- `ambiguous`: could mean several diseases on purpose. `non_disease`: a real medical word that is not a disease. `invalid`: names
  nothing (filler, gibberish).

## Decide for every item

`ok` when a Korean clinician or patient who typed or read it would mean the intended disease (or, for ambiguous / non_disease /
invalid, it keeps that nature), and it fits its category.

`fix` with one reason:
- `unrecognisable`: a Korean speaker would not recognise the disease (for example a word cut in the middle: "편두" for migraine).
- `other_meaning`: its usual meaning is something else ("주사" usually means an injection, not rosacea).
- `wrong_disease`: it names another disease, or a much broader or narrower one.
- `not_category`: it does not fit its category: a "typo" that is spelled correctly, an "abbrev" no one uses, "lay" that is the
  technical name.
- `unnatural`: no Korean speaker would type it this way.

For `fix`, write `proposal`: a Korean question of the same category and the same disease that fixes the problem. A typo must still
be a recognisable misspelling; an abbreviation must be one really in use (keep English letters when Korean clinicians use them).
Keep the difficulty: do not turn a typo into the correct spelling or an abbreviation into the full name.

Do not judge whether a computer would get it right. Judge only what a Korean speaker would understand.

Output `out/kr_NN_<a|b>.jsonl`, one line per item, in order:
`{"qid": "...", "verdict": "ok"}` or `{"qid": "...", "verdict": "fix", "reason": "...", "proposal": "..."}`

## Adjudication (`out/kr_NN_adj.jsonl`)

Read the batch and both reviews. For each item that both reviewers marked `fix`, write the final Korean question:
`{"qid": "...", "final": "..."}`. Pick the better proposal or write a better one under the same rules. Skip all other items.
