# Dataset review: instructions for the review agent

You review one batch file of one training dataset of ADCTOX, a terminal app that reads a patient's comorbidities and compares
approved antibody-drug conjugates against the label warnings for the organs those comorbidities affect. The datasets train a
Gemma judge (organ labels, symptom sentences, Korean expressions, invalid inputs) and drive the disease search (profiles,
Korean MONDO names). Your job is to find and fix errors, not to rewrite what is right. When in doubt, keep.

Read your batch file, judge every item, write one JSON object per item to the output file, in the input order, then return the
counts. Do not edit any other file. Do not run the app or the tests. Write in the language of the data: Korean names and
sentences stay Korean; reasons may be in English or Korean, one short clause.

## Output file

`data/curated/review_opus/out/<batch name>.jsonl`, UTF-8, one line per input item (for `sym`, one line per sentence).
Valid JSON on every line. Use the item's `id` or `i` exactly as given, including negative `i` values.

## Sets

### organ — concept organ labels (`organ_NNN.json`)

Items: `{"id", "concept": "- MONDO:id | name | syn: ... | ancestors: ... | def: ...", "current": [organs]}`.
Judge the current label against `data/curated/concept_organs/GUIDE.md` (read it first; the v3 additions at the end override
the earlier rules). The 13 axes are haematologic, hepatic, cardiovascular, pulmonary, renal, gastrointestinal, neurologic,
ocular, dermatologic, metabolic_endocrine, musculoskeletal, infectious_immune, otologic.

Write `{"id", "verdict": "keep" | "change" | "unclear", "organs": [...], "confidence": "high" | "medium" | "low", "reason": "..."}`.
- `keep`: the current organs are right (an empty list is right for purely reproductive, obstetric or psychiatric disease).
- `change`: give the full corrected list in `organs` (at most 4), and the reason. Change only when the current label is wrong by
  the guide: a missing directly damaged organ, an organ that is only a rare complication, the wrong organ for a tumour, etc.
  Do not change for taste; two readings that both follow the guide are `keep`.
- `unclear`: the concept cannot be judged from name, synonyms, ancestors and definition. `organs` = the current list.
- `reason` only for `change` and `unclear`.

### sym — symptom sentences (`sym_NN.json`)

Items: one per disease profile: `{"id", "name", "en", "ko", "symptoms_en", "symptoms_ko", "sentences": [{"i", "text", "lang", "style"}]}`.
A sentence is a patient's or clinician's description of that disease's presentation; `lay` = everyday words, `clinical` = chart
style. Judge each sentence: does it fit this disease (a typical presentation, history or finding of it), is it natural in its
language and style, and is it free of errors (wrong organ, impossible finding, a different disease's hallmark)?

Write `{"i", "verdict": "keep" | "fix" | "drop", "text": "...", "reason": "..."}` for every sentence.
- `fix`: a small correction keeps the sentence usable (a wrong word, an unnatural phrase). Put the whole corrected sentence in
  `text`, same language and style.
- `drop`: the sentence describes another disease, contradicts this one, or is not a symptom/history description at all.
- A sentence may name the disease; that is allowed.

### ko — Korean expressions (`ko_NN.json`)

Items: `{"i", "id", "concept": "- MONDO:id | name | ...", "text", "kind"}`; `kind` is formal / everyday / spoken / short (an
abbreviation). The text should denote exactly this concept (not a parent, a child or a neighbour), with standard spelling
(대한의학회 의학용어집, KCD style) for `formal`, and natural Korean for the rest.

Write `{"i", "verdict": "keep" | "fix" | "drop", "text": "...", "reason": "..."}`.
- `fix`: right concept, wrong spelling or unnatural wording; corrected text in `text`.
- `drop`: the text denotes another concept, a much broader or narrower one, or is not a disease expression.

### junk — invalid inputs (`junk_NN.json`)

Items: `{"i", "text", "kind"}`. These are meant to be inputs that name no disease, symptom, finding or medical history: keyboard
mashing, chit-chat, objects, food, places, questions to a chatbot, refusals, random sentences. The judge learns to reject them.

Write `{"i", "verdict": "junk" | "real", "reason": "..."}`.
- `real`: a clinician could read it as a symptom, complaint, finding, diagnosis, medication or medical history ("졸려요",
  "말하기 곤란합니다", "숨이 차요" are real). Such items must leave the dataset.
- `junk`: everything else. `reason` only for `real`.

### profiles — disease profiles (`profiles_NN.json`)

Items: the profile itself: `{"id", "name", "everyday", "en": [...], "abbr": [...], "ko": [...], "ko_lay": [...], "symptoms_en": [...],
"symptoms_ko": [...], "concept": "- MONDO:id | ..."}`. `ko[0]` is the Korean name the app shows; `ko_lay` are everyday Korean
words for it; `abbr` are abbreviations clinicians use; the symptom lists are short presenting complaints.

Write `{"id", "verdict": "keep" | "fix", "fields": {only the fields you change, each with its full corrected list}, "reason": "..."}`.
- Fix a Korean name that is not this disease or is misspelt, an abbreviation that means something else, a symptom that belongs
  to another disease. Keep lists short (as they are). Do not add new content unless a list is wrong.

### mondo_ko — Korean MONDO names (`mondo_ko_NN.json`)

Items: `{"id", "concept": "- MONDO:id | name | ...", "ko", "alt": [...], "conf"}`. `ko` is the Korean name shown for this concept.
Rules: `data/curated/korean/TRANSLATE.md` (read it first).

Write `{"id", "verdict": "keep" | "fix" | "unsure", "ko": "...", "reason": "..."}`.
- `fix`: `ko` names another disease, mistranslates a part, or breaks the rules; put the corrected name in `ko`.
- `unsure`: you cannot tell; `ko` = the current name.
- `keep`: the name is right, including an equivalent spelling of a standard term.

## Finish

Count your lines: they must equal the number of items (sentences for `sym`). Then return `written`, `changed` (change / fix),
`dropped` (drop / real), `unclear` (unclear / unsure) and at most three short notes on patterns you saw.

## Round 2 sets

### verify — A/B check of a proposed change (`verify_NN.json`)

Items: `{"set", "key", "context", "A", "B"}`. `A` and `B` are two versions of the same thing for the concept or sentence in
`context`: an organ list (set organ), a Korean expression (ko; one side may be the note "(drop: ...)", which means the
expression should be removed), a symptom sentence (sym; one side may be "(drop: ...)"), profile fields (profiles) or a Korean
MONDO name (mondo_ko). Judge from the data and the guides (GUIDE.md for organ, TRANSLATE.md for names) which version is right.
You do not know which one is the current value; judge on the merits.

Write `{"key", "better": "A" | "B" | "same", "reason": "..."}` for every item. `same` only when both are acceptable.

### mondo_ko2 — Korean MONDO names, second part (`mondo_ko2_NN.json`)

Exactly as `mondo_ko` above. Output file `out/mondo_ko2_NN.jsonl`.

### blind — organ labels without the current label (`blind_NN.json`)

Items: `{"id", "concept"}`. Label each concept from scratch by `data/curated/concept_organs/GUIDE.md` (v3 additions override).
Write `{"id", "organs": [...], "scope": "axis" | "no_axis" | "unclear", "confidence": "high" | "medium" | "low"}`; at most 4
organs; `organs` empty for `no_axis` and `unclear`.

### adjudicate — current label vs blind relabel (`adjudicate_NN.json`)

Exactly as `verify`: `{"set": "organ", "key", "context", "A", "B"}`, two organ lists for the concept. Choose the one that follows
GUIDE.md; `same` when both do. Output `{"key", "better": "A" | "B" | "same", "reason"}` to `out/adjudicate_NN.jsonl`.
