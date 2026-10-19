# Korean expressions (ko2): instructions for the agents

ADCTOX reads what a Korean patient or clinician types as a comorbidity and decides which organs it affects. You write the
Korean ways people actually type a disease, so the model learns them. Write only what a Korean speaker would really type.

## Generation (`batches/ko2_NNN.json` → `out_ko2/ko2_NNN.jsonl`)

Each item: `{"id", "concept": "- MONDO:id | English name | syn | ancestors | def", "ko": standard Korean name, "alt", "organs"}`.
For every concept write these lines (one JSON object per line):

| kind | how many | what |
|---|---|---|
| `everyday` | 2 | what ordinary people call it, or how they describe having it in plain words ("눈 압력이 높은 병", "피부가 하얗게 빠지는 병") |
| `spoken` | 1 | a short sentence a patient says or a nurse writes when telling their history ("작년에 녹내장 진단받았어요", "갑상선 기능 저하로 약 먹는 중") |
| `abbrev` | 0 or 1 | an abbreviation Korean clinicians really use for exactly this concept (English letters such as "AMD", or a Korean short form such as "갑저"). Skip it when there is none or when it more often means something else |
| `typo` | 2 | realistic misspellings of the Korean name: a wrong vowel (ㅔ/ㅐ, ㅗ/ㅓ), a missing or wrong final consonant, a swapped syllable, wrong spacing. Still recognisable |

Rules:
- The text must mean exactly this concept: not its parent, not a child, not a neighbour. For a rare subtype, everyday words may name the subtype plainly ("어릴 때부터 있는 ~").
- Korean only, except `abbrev`. At most 40 characters. Do not copy the `ko` name unchanged.
- Do not invent symptoms that belong to another disease.

Line format: `{"id": "MONDO:...", "kind": "everyday", "text": "..."}`. Write all lines of the batch to the output file, then
return `written N`.

## Verification (`batches/ko2v_NN.json` → `out_ko2/ko2v_NN.jsonl`)

Each item: `{"i", "id", "concept", "ko", "text", "kind"}`. Decide whether `text` is a way a Korean speaker would type this
concept.

- `keep`: it means this concept (for `typo`, a recognisable misspelling of it; for `abbrev`, an abbreviation used for it).
- `drop`: it means another disease, a much broader or narrower one, is not recognisable, or (abbrev) usually means something else.

Write `{"i": <i exactly as given, including negative values>, "verdict": "keep" | "drop"}` for every item, in order, then
return `written N, dropped M`.
