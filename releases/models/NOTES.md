Model bundle 0.2.

- Learned organ estimate: axis heads trained on FinnGen endpoint summaries together with the published Danish disease trajectories (Siggaard et al. 2020, CC BY 4.0). Two comparison heads (Danish only, FinnGen only) ship alongside; the app shows all three and applies automatically only organs at least two models place in their top three. Metabolic/endocrine is left blank because it failed the per-axis check on an independent US cohort (HuDiNe).
- MONDO index v3: validity gate for typed text, abbreviation readings from the NLM SPECIALIST Lexicon (LRABR), a Human Phenotype Ontology block for symptoms, and Korean disease names from the HIRA KCD master (공공누리 제1유형, attribution).
- Unchanged: BioLORD-2023 and SapBERT at the same pinned Hugging Face revisions. SapBERT fine-tuning was evaluated three times and not adopted.

Update through the app with `U` in the condition picker or `adctox --update-models`. Only the head and the index are downloaded; the encoders are reused by SHA256. No FinnGen rows, collaborator workbooks, or Danish source rows are included.
