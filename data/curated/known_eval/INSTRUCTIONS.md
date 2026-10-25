# Korean questions for the known-disease benchmark: instructions for the agents

ADCTOX reads what a Korean patient or clinician types as a comorbidity. These questions test whether it recognises a disease
typed in a new way. They are used only to evaluate, never to train. Write only what a Korean speaker would really type.

## Generation (`batches/ke_NN.json` → `out/ke_NN.jsonl`)

Each item: `{"id", "concept": "- MONDO:id | English name | syn | ancestors | def", "ko": standard Korean name}`.
For every concept write exactly one line of each kind:

| kind | what |
|---|---|
| `everyday` | what ordinary people call it, or how they describe having it in plain words |
| `typo` | a realistic misspelling of the Korean name (wrong vowel, wrong or missing final consonant, adjacent key, spacing) |
| `mixed` | how a Korean chart or history line writes it mixing Korean and English, or an abbreviation Korean clinicians really use |
| `spoken` | a short sentence a patient says or a nurse writes when telling the history |

Rules:
- The text must mean exactly this concept: not its parent, not a child, not a neighbour.
- Do not copy `ko` unchanged. At most 40 characters.
- Write it fresh, the way a person would type it today; do not repeat a textbook name.

Line format: `{"id": "MONDO:...", "kind": "typo", "text": "..."}`. Write all lines of the batch to the output file, then return
`written N`.

## Verification (`batches/kev_NN.json` → `out/kev_NN.jsonl`)

Each item: `{"i", "id", "concept", "ko", "text", "kind"}`. `keep` when a Korean speaker typing `text` would mean this concept
(for `typo`, a recognisable misspelling; for `mixed`, a mix or abbreviation really used for it); `drop` when it means another
disease, a much broader or narrower one, or is not recognisable.

Write `{"i": <i exactly as given, including negative values>, "verdict": "keep" | "drop"}` for every item, in order, then return
`written N, dropped M`.
