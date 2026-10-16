# Korean names for MONDO diseases: translation rules

Write the name a Korean clinician would read in a chart or a textbook. Do not write a word-for-word gloss.

1. **Standard terms first.** Use 대한의학회 의학용어집 (6th edition) and HIRA KCD-8 style.
   - `chronic kidney disease` → 만성 콩팥병; `heart failure` → 심부전; `asthma` → 천식
   - When two forms are both used (콩팥 / 신장, 뇌전증 / 간질), use the current preferred one in `ko`. Put the other in `alt`.
2. **Eponyms:** transliterate the person's name and keep the head noun in Korean.
   - `Gilbert syndrome` → 길버트 증후군; `Fabry disease` → 파브리병; `Kawasaki disease` → 가와사키병
3. **Gene names, symbols and abbreviations stay in Latin letters.**
   - `BRCA1-related breast cancer` → BRCA1 관련 유방암; `COL4A1-related disorder` → COL4A1 관련 질환
   - Numbered subtypes keep the number: `Charcot-Marie-Tooth disease type 2A` → 샤르코-마리-투스병 2A형; `spinocerebellar ataxia type 3` → 척수소뇌실조 3형; `Bardet-Biedl syndrome 12` → 바르데-비들 증후군 12
4. **Head nouns:**
   - disease → 병 / 질환; disorder → 장애 (psychiatric) or 질환; syndrome → 증후군
   - cancer → 암; carcinoma → 암종; neoplasm → 신생물; tumor → 종양
   - deficiency → 결핍증; infection → 감염(증); inflammation of X → X염 (hepatitis 간염, nephritis 신장염)
5. **Qualifiers keep their order in the Korean way:**
   - `autosomal dominant` → 상염색체 우성; `X-linked` → X연관; `familial` → 가족성; `congenital` → 선천성
   - `juvenile` → 소아 / 청소년; `early-onset` → 조기 발병; `childhood` → 소아
6. **Never invent meaning.** If a part of the name is unclear, transliterate that part. Set `conf` to `low`.
7. **Keep it short.** One name in `ko`. Up to 2 `alt` names that people actually use, such as an everyday word or an older term. If there are none, leave `alt` empty.
8. **Confidence:**
   - `high`: a standard Korean term exists and you are sure of it.
   - `medium`: built by the rules above from clear parts.
   - `low`: partly transliterated or uncertain.

Output: one JSON object per line, for every input item, in input order:
`{"id": "MONDO:...", "ko": "...", "alt": ["..."], "conf": "high|medium|low"}`
