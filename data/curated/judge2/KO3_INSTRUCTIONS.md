# Korean expressions (ko3): instructions for the agents

ADCTOX reads what a Korean patient or clinician types as a comorbidity and decides which organs it affects. You write the
short, abbreviated and mixed Korean-English ways people really type a disease. Write only what a Korean speaker really types.

## Generation (`batches/ko3_NNN.json` → `out_ko3/ko3_NNN.jsonl`)

Each item: `{"id", "concept": "- MONDO:id | English name | syn | ancestors | def", "ko", "alt", "organs", "new"}`.
For every concept write these lines (one JSON object per line):

| kind | how many | what |
|---|---|---|
| `short` | 0 or 1 | the short everyday word Koreans type for exactly this disease, 2–4 syllables, different from `ko` ("뾰루지", "무좀", "축농증", "통풍"). Skip it when there is none |
| `abbrev` | 0 or 1 | an abbreviation Korean clinicians really write for exactly this concept: Korean short forms ("갑저", "고지혈", "심근경") or English letters ("CKD", "AMD"). Skip it when there is none or when it more often means something else |
| `mixed` | 1 | how a Korean chart or history line mixes Korean and English for it ("DM 2형", "HTN 진단", "CKD 3기", "r/o 결핵", "s/p 위절제술", "AF 있음", "B형 간염 carrier") |
| `everyday` | 2, only when `new` is true | what ordinary people call it or how they describe having it in plain words |
| `spoken` | 1, only when `new` is true | a short sentence a patient says or a nurse writes when telling the history ("작년에 녹내장 진단받았어요") |

Rules:
- The text must mean exactly this concept: not its parent, not a child, not a neighbour.
- At most 40 characters. Do not copy `ko` or an `alt` name unchanged.
- Do not invent abbreviations. If you are not sure Korean clinicians use it, skip it.

Line format: `{"id": "MONDO:...", "kind": "mixed", "text": "..."}`. Write all lines of the batch to the output file, then return
`written N`.

## Verification (`batches/ko3v_NN.json` → `out_ko3/ko3v_NN.jsonl`)

Each item: `{"i", "id", "concept", "ko", "text", "kind"}`. Decide whether `text` is a way a Korean speaker would type this concept.

- `keep`: it means this concept (for `abbrev`, an abbreviation really used for it; for `short`, a short word that means it).
- `drop`: it means another disease, a much broader or narrower one, is not recognisable, is not really used, or (abbrev) usually
  means something else.

Write `{"i": <i exactly as given, including negative values>, "verdict": "keep" | "drop"}` for every item, in order, then return
`written N, dropped M`.
