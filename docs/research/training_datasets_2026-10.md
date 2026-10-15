# Additional datasets for ADCTOX: linking, Korean text, organ labels, comorbidity validation, ADC toxicity

Survey date 2026-10-15. Scope: sources **not** already in use (MONDO, HPO + hpoa, LRABR, HIRA KCD
master, MedMentions, NCBI Disease, BC5CDR, COMETA, Claude-generated queries, FinnGen, Danish DTB,
HuDiNe, ClinicalTrials.gov AE, openFDA/DailyMed, SIDER).
Nothing was downloaded for this note.

How sure each fact is. Every row carries one of these tags:

* **[v]** checked on the web on 2026-10-15: the dataset page, the paper or the model card.
* **[k]** from prior knowledge and not re-checked today. Open the page before relying on it.
  This matters most for licences.

Ranking. Each row is scored as *benefit ÷ effort*:

* **Benefit (1–5):** the expected gain on a weak ADCTOX metric.
* **Effort (1–5):** access paperwork plus loader work. Days-scale is 2–3; months-scale is 5.

## 1. Ranked summary

| # | Dataset | Area | Access | Train use / redistribute | Benefit | Effort | B/E | What it improves |
|---|---|---|---|---|---|---|---|---|
| 1 | MeSH C-tree, DOID top classes, ICD-10/11 chapters and Orphanet linearisation, all reached through MONDO xrefs we already hold | 3 organ | open download | yes / yes (attribution) | 5 | 1 | **5.0** | Independent organ ground truth: 3–5 voters per MONDO concept, not 1 |
| 2 | MONDO `disease_has_location` → UBERON + UBERON system partonomy | 3 organ | already on disk (3,372 axioms in mondo.obo); UBERON is CC BY 3.0 | yes / yes | 4 | 1 | **4.0** | Anatomical organ label without needing an `is_a` path |
| 3 | phecodeX (WHO ICD-10 map + `group` category) | 3 organ, 4 validation | GitHub, no LICENSE file **[v]** | training ok in practice; redistribution: ask | 4 | 1.5 | **2.7** | 17-ish category labels per phecode; lets UKB/PheWAS pair tables join to MONDO |
| 4 | MedlinePlus Health Topics XML (`<also-called>`) | 1 linking (lay) | daily XML, no account **[v]** | yes / yes with "from MedlinePlus.gov" | 3 | 1 | **3.0** | ~1,000 topics with lay synonyms, gold-quality |
| 5 | CHV concepts-terms flat file (GWU) | 1 linking (lay) | open download **[v]**; licence text not found | training yes; redistribution unclear | 3 | 1 | **3.0** | ~150k lay strings → UMLS CUI → MONDO via `UMLS:` xref (COMETA already ships a `chv.csv` subset) |
| 6 | KBMC Korean Bio-Medical NER | 2 Korean | Hugging Face, Apache-2.0 **[v]** | yes / yes | 3 | 1 | **3.0** | Korean disease-span extractor for whole sentences (4,162 disease spans, 6,150 sentences) |
| 7 | PsyTAR | 1 linking (lay, symptoms) | bigbio mirror lists CC BY 4.0 **[v]** (original release not checked) | yes / yes | 3 | 1.5 | **2.0** | Patient-written symptom/ADR phrases with UMLS/SNOMED ids |
| 8 | AskAPatient / TwADR-L (Limsopatham & Collier 2016) and MedNorm (2019) | 1 linking (lay) | Zenodo / GitHub **[k]** | research; check each | 3 | 1.5 | **2.0** | ~8.7k + ~5k lay phrases → SNOMED/UMLS; MedNorm merges them into one table |
| 9 | DDXPlus (English release) | 1 symptom→disease | figshare, CC BY **[v]** | yes / yes | 3 | 2 | **1.5** | 1.3M synthetic patients, 49 pathologies: symptom-set → disease eval and negatives for the disease gate |
| 10 | Zhu 2023 (*Cancer*) and Li 2023 (*Cancer Innovation*) ADC TRAE meta-analyses | 5 ADC tox | Li: CC BY 4.0 **[v]**; Zhu: Wiley, check OA **[k]** | facts free; table text per licence | 3 | 1.5 | **2.0** | Pooled per-ADC and per-payload grade ≥3 rates as an outside check on the label ranking |
| 11 | Canada Vigilance, EudraVigilance (adrreports.eu), UK Yellow Card iDAPs | 5 ADC tox | open / web **[k]** | Canada: Open Government Licence; EU/UK: see terms | 3 | 2 | **1.5** | Third and fourth spontaneous-report validators beside FAERS/JADER |
| 12 | SNOMED CT International + Korean Extension (finding site, `363698007`) | 3 organ, 1 linking | Korea is a member and KHIS is the NRC **[v]**; affiliate licence via KHIS/MLDS | yes inside Korea; no redistribution | 5 | 3 | **1.7** | Best concept-level organ truth (finding-site axioms), plus Korean synonyms |
| 13 | UMLS Metathesaurus (UTS licence) | 1 linking | free UTS account, annual report **[k]** | yes; no redistribution of content | 4 | 2.5 | **1.6** | All English synonyms, plus MedDRA Korean if present (check); CODER/KRISSBERT need it |
| 14 | KDCA 국가건강정보포털 health-information API | 2 Korean lay | data.go.kr, free; KOGL type 4 (attribution, non-commercial, **no derivatives**) **[v]** | eval only; no training-derived release | 3 | 2 | **1.5** | Korean lay disease descriptions and alternate names to test Korean free text |
| 15 | KCD-8 index volume (색인) from KOSTAT | 2 Korean | 통계분류포털 / KOSTAT publications **[k]** | KOGL (check type) | 3 | 2 | **1.5** | Many Korean synonyms per code that the HIRA master lacks |
| 16 | Korean NHIS disease networks (Ko 2020 JMIR; Korean claims network) | 4 validation | papers CC BY; **no edge list published** **[v]** | n/a | 3 | 2.5 | **1.2** | Korean-population check; needs an e-mail to the authors |
| 17 | CPRD 308-condition multimorbidity (Kuan 2023 *Lancet Digit Health*) + HDR UK phenotype library | 4 validation, 3 organ | phenotypes CC BY **[k]**; pair data via online tool **[v: tool exists]** | facts yes | 3 | 2.5 | **1.2** | UK primary-care co-occurrence: a validator independent of DTB/FinnGen |
| 18 | UK Biobank published pair tables (inter-disease interactivity network, Bioinformatics; 439-disease genetic comorbidity, medRxiv 2021) | 4 validation | GitHub / journal supplements **[v: exist]** | per paper | 3 | 2.5 | **1.2** | Phecode-level pairs; joins through phecodeX (row 3) |
| 19 | Taiwan NHIRD epidemiological disease network (Jiang 2018 *Sci Rep*) | 4 validation | CC BY article; supplement not checked (PMC captcha) | facts yes | 2 | 2 | **1.0** | East-Asian prevalence structure |
| 20 | KorMedMCQA | 2 Korean | HF, CC BY-NC 2.0 **[v]**, 7,469 questions | non-commercial only | 2 | 1.5 | **1.3** | Mine Korean clinical vignettes for test inputs; not a linking label set |
| 21 | AI Hub medical corpora (초거대AI 헬스케어 질의응답, 전문분야 말뭉치, 필수의료 의학지식) | 2 Korean | AI Hub account + per-dataset application; domestic use, no export **[k]**; some only in the Safe Zone **[v]** | training yes; no redistribution | 3 | 3 | **1.0** | Large Korean patient-question text for lay-term mining and Korean query generation |
| 22 | n2c2 2019 Track 3 (clinical concept normalization) | 1 linking (clinical abbrev.) | DBMI portal DUA; registration said "not open" at check time **[v]** | training yes; no redistribution | 3 | 3.5 | **0.9** | 10,919 note mentions → SNOMED/RxNorm CUIs; clinician shorthand |
| 23 | CADEC | 1 linking (lay) | CSIRO DAP; likely the retired non-commercial CSIRO Data Licence **[v: DAP rule]** | non-commercial | 3 | 2 | **1.5** | 1,250 AskaPatient posts → SNOMED; overlaps with row 8 |
| 24 | SMM4H 2017 Task 3 / later SMM4H normalization | 1 linking | organisers on request; MedDRA labels **[v]** | needs a MedDRA licence for labels | 2 | 3 | 0.7 | Tweets; MedDRA licence blocks easy use |
| 25 | ShARe/CLEF eHealth 2013 | 1 linking | PhysioNet credentialed + CITI **[k]** | yes / no | 2 | 3.5 | 0.6 | Disorder normalization in ICU notes; ICU is a domain mismatch (same reason MIMIC was excluded) |
| 26 | BioRED | 1 linking | NCBI FTP `/pub/lu/BioRED/` **[v]**; licence file not seen | likely public | 1.5 | 1 | 1.5 | 5,545 more PubMed disease mentions → MeSH; little new beyond BC5CDR/NCBI |
| 27 | Symptom2Disease (Kaggle) | 1 symptom→disease | Kaggle, licence on page **[v: size]** | check | 1.5 | 1 | 1.5 | 1,200 lay symptom paragraphs, 24 diseases; small smoke test only |
| 28 | VigiBase extract / VigiAccess | 5 ADC tox | Extract is a paid licence, academic tier **[v]**; VigiAccess is click-through and aggregated | Extract: no redistribution | 3 | 4 | 0.75 | Worldwide reports; VigiAccess SOC counts only as a qualitative check |
| 29 | Mantra GSC, Quaero, TwiMed | 1 linking | small; Mantra/Quaero are not English-lay or Korean **[k]** | various | 1 | 2 | 0.5 | Skip |
| 30 | JMDC (Japan) | 4 validation | commercial; no published pair table found **[v]** | — | 1 | 5 | 0.2 | Skip |

## 2. Details by area

### Area 1. Disease-mention linking (lay terms, abbreviations, typos, symptoms)

The linker trains and evaluates on corpora that `ml/build_external_linking.py` maps to MONDO through
the `MESH:`, `OMIM:`, `UMLS:` and `SCTID:` xrefs. The current snapshot of `mondo.obo` holds 21,664
UMLS, 9,171 SCTID and 8,212 MESH xrefs. Any source labelled with UMLS CUIs or SNOMED ids therefore
plugs in through the same function. The gap is lay and symptom language: COMETA is the only lay
corpus in use today.

**MedlinePlus Health Topics XML** **[v]**
- URL: https://medlineplus.gov/xml.html (`mplus_topics_YYYY-MM-DD.xml`; a zip variant is posted Tue–Sat)
- Contents: about 1,000 English consumer health topics. `<also-called>` holds lay synonyms. Topics also
  carry MeSH headings, which map to MONDO through `MESH:`.
- Size: a few MB.
- Licence: NLM asks only that the data be credited as coming from MedlinePlus.gov.
- Use: high-precision lay synonym pairs (synonym → topic MeSH → MONDO) for SapBERT fine-tuning, and a
  lay-term eval set. Spanish topics also exist; Korean exists only as PDF handouts, which are not
  useful here.

**CHV (Consumer Health Vocabulary), GWU / Utah flat files** **[v]**
- URL: https://biomedinfo.smhs.gwu.edu/chv-files
- Contents: the concepts-terms file has one row per lay term with the UMLS CUI and CHV preferred name.
  Last updated in 2011.
- Size: about 150k terms **[k]**.
- Licence: none stated on the download page. CHV is also a UMLS source (see the NLM CHV source docs).
- Already partly in hand: COMETA ships `chv.csv` in `data/raw/cometa/x/cometa/`.
- Use: lay → CUI → MONDO pairs. Treat it as noisy, because CHV includes misspellings, which is useful
  for typo robustness. Keep it as training input only and do not ship the strings.

**PsyTAR** **[v mirror]**
- URL: https://huggingface.co/datasets/bigbio/psytar (loader); the original is from Zolnoori et al.
  2019, *Data in Brief*.
- Contents: 891 AskaPatient reviews of psychiatric drugs. Spans are ADR, WD, SSI and DI, mapped to UMLS
  and SNOMED.
- Size: small (a few thousand spans).
- Licence: CC BY 4.0 as listed by bigbio; confirm against the original release.
- Use: symptom phrases in patient voice, e.g. "couldn't sleep at all" → insomnia. The DI (drug
  indication) spans are lay disease names.

**AskAPatient and TwADR-L (Limsopatham & Collier, ACL 2016); MedNorm (Belousov et al., 2019)** **[k]**
- URLs: Zenodo record for "AskAPatient / TwADR-L" (search Zenodo for "Limsopatham normalisation");
  MedNorm at https://github.com/mbelousov/MedNorm-corpus (verify the URL).
- Contents: AskAPatient has 8,662 lay phrases → SNOMED/AMT in 10 folds. TwADR-L has tweets → SIDER/MedDRA.
  MedNorm harmonises about 28k phrases from CADEC, TwADR-L, SMM4H and others to UMLS, MedDRA and SNOMED.
- Licence: research release; MedDRA labels inherit MedDRA's licence. Use the UMLS/SNOMED columns only.
- Use: the largest lay-phrase → concept set short of UMLS. Most items are symptoms and ADRs, so they
  train the "symptom sentence → condition" path and the disease gate's negatives.

**CADEC** **[v DAP rules]**
- URL: CSIRO Data Access Portal (search "CADEC" at data.csiro.au).
- Contents: 1,250 AskaPatient posts on arthritis drugs, with spans normalised to SNOMED CT, AMT and MedDRA.
- Licence: the DAP record most likely carries the retired *CSIRO Data Licence*, which is non-commercial.
  Read the record before downloading.
- Use: subsumed by MedNorm if MedNorm is obtained.

**DDXPlus** **[v]**
- URL: https://figshare.com/articles/dataset/DDXPlus_Dataset/20043374 (English release dated 2023-05-09)
- Contents: 1.3M synthetic patients across 49 pathologies, each with about 10 symptoms and 3
  antecedents, a differential diagnosis and a ground-truth pathology. The evidences are structured
  questions with English text.
- Size: on the order of 1 GB uncompressed **[k]**. Load only the release JSON plus a test split.
- Licence: CC BY (the version shown on figshare).
- Use, as evaluation more than training:
  1. Render "patient has X, Y, Z" sentences and check that the gate refuses to emit a disease the text
     does not name. ADCTOX links stated comorbidities and does not diagnose.
  2. The antecedent field holds real comorbidities (e.g. COPD, diabetes); pair the evidence text with
     the antecedent as lay paraphrases.
- Caveat: the 49 pathologies are an emergency/respiratory mix, so coverage of oncology comorbidity is thin.

**n2c2 2019 Track 3 (clinical concept normalization)** **[v]**
- URL: https://portal.dbmi.hms.harvard.edu/projects/n2c2-2019-t3
- Contents: i2b2 2010 discharge summaries; problems, tests and treatments → UMLS CUIs restricted to
  SNOMED CT and RxNorm (UMLS 2017AB).
- Size: about 10.9k mentions in 100 + 100 notes **[k]**.
- Access: DBMI portal DUA. The page said registration was "not open" at check time, so e-mail the n2c2
  team.
- Use: real clinician shorthand ("s/p CABG", "HTN", "DM2") as an abbreviation eval set. Do not
  redistribute.

**ShARe/CLEF eHealth 2013 Task 1** **[k]**
- Access: PhysioNet credentialed access with CITI training.
- Contents: MIMIC-II notes; disorder spans → SNOMED CUIs.
- Verdict: same ICU-domain objection that `docs/DATA_SOURCES.md` raises against MIMIC-IV. Low priority.

**SMM4H** **[v]**
- The 2017 Task 3 normalization set has 6,650 training phrases and 2,500 evaluation phrases → MedDRA PT.
- Verdict: the labels are MedDRA codes. ADCTOX holds no MedDRA licence (see `docs/DATA_SOURCES.md`),
  so this set needs a re-mapping step through UMLS (MDR → CUI → MONDO), which in turn needs a UTS
  account. Low priority.

**BioRED** **[v]**
- URL: ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/
- Contents: 600 PubMed abstracts in the 2022 release (1,000 in BC8) with 5,545 disease mentions →
  MeSH. NCBI-produced, so very likely public domain; no licence file was seen.
- Verdict: in-domain with BC5CDR and NCBI, so marginal benefit. Add it only as extra PubMed-style eval
  because the loader is the existing PubTator function.

**Symptom2Disease** **[v]**
- URL: https://www.kaggle.com/datasets/niyarrbarman/symptom2disease
- Contents: 1,200 lay first-person symptom paragraphs over 24 diseases (50 each).
- Licence: see the Kaggle page.
- Use: a 30-minute smoke test of whole-sentence input. Too small and too templated to train on.

**UMLS Metathesaurus** **[k]**
- Access: free UTS licence with an annual usage report. SNOMED content is free to use in member
  countries, and Korea is a member (see area 3).
- Use:
  - Synonym expansion for every MONDO concept through `UMLS:` xrefs.
  - Prerequisite for CODER (GanjinZero, UMLS-trained, MIT code) and for running KRISSBERT end to end.
  - Check whether the current release includes Korean MedDRA (`MDRKO`) strings. If it does, that is a
    licensed Korean synonym layer.
- Redistribution: none. Embeddings of UMLS strings are a grey zone, so keep them local, as is already
  done for MedDRA.

**KRISSBERT** **[v]**
- URL: https://huggingface.co/microsoft/BiomedNLP-KRISSBERT-PubMed-UMLS-EL
- Licence: MIT for the weights; the UMLS dictionary is needed to build its prototype index.
- What it is: a self-supervised UMLS linker from Zhang et al. 2021, reported at up to +20 points over
  earlier self-supervised linkers.
- Use: another bake-off arm in `ml/embed_bakeoff.py`, not a dataset. Its PubMed self-supervision recipe
  could also generate MONDO-specific training mentions.

**Skip:** Mantra GSC (multilingual EMEA/patent titles, no Korean), Quaero (French), TwiMed (small,
sentence-level, access by request).

### Area 2. Korean medical text

**KBMC, Korean Bio-Medical Corpus (LREC-COLING 2024)** **[v]**
- URL: https://huggingface.co/datasets/SungJoo/KBMC (`KBMC.tsv`, 1.5 MB)
- Contents: 6,150 sentences and 153,971 tokens in BIO tags. Spans are 4,162 disease, 841 body-part and
  396 treatment. ChatGPT-assisted, with human review.
- Licence: Apache-2.0, so training and redistribution are allowed.
- Use: train or evaluate a Korean span extractor that splits a whole Korean sentence ("당뇨 있고 신장이
  안 좋아요") into disease mentions before MONDO linking.
- Caveat: no normalization ids. Link the spans with the existing KCD/HIRA dictionary to make silver
  pairs, and hand-check 200.

**KDCA 국가건강정보포털 health-information Open API** **[v]**
- URL: https://www.data.go.kr/data/15087442/openapi.do (XML; spec KDCA17-HEALTH-API01-v1.2)
- Contents: physician-reviewed Korean disease articles: names, alternate names, symptom text.
- Licence: KOGL type 4, which means attribution, **non-commercial and no derivatives**. Development keys
  are auto-approved; production keys are reviewed.
- Use: Korean lay vocabulary and an *evaluation* set. "No derivatives" argues against fine-tuning on it
  and shipping the resulting weights; ask KDCA if training use is wanted.

**KCD-8 / KCD-9 from KOSTAT** **[k]**
- KCD-8 is in force. KCD-9 has been announced; confirm its effective date at kssc.kostat.go.kr.
- The HIRA master in hand has one Korean name per code. KOSTAT's printed KCD includes an **index
  volume (색인)** with many inclusion terms and alternate Korean names per code, the Korean analogue of
  the ICD-10 alphabetical index.
- Access: 통계분류포털 (https://kssc.kostat.go.kr) for classification tables (Excel), and KOSTAT
  publications for the index PDF.
- Licence: KOGL type; check per file.
- Use: Korean synonym → KCD → ICD-10 → MONDO (`ICD10WHO:` and `ICD10CM:` xrefs, about 2.4k together)
  for SapBERT Korean fine-tuning.
- Effort: PDF table extraction.

**SNOMED CT Korean Extension (KHIS)** **[v]**
- Korea became the 39th SNOMED International member in 2020. KHIS is the national release centre and
  maintains a Korean Extension with **Korean synonyms**.
- Access: affiliate licence through KHIS (or MLDS). International-edition use in member countries
  carries no SNOMED International fee; KHIS may add conditions.
- Use: Korean synonym strings attached to SCTIDs (9,171 MONDO SCTID xrefs), plus the finding-site use
  in area 3.
- One application unlocks both areas.

**KOSTOM** **[v]**
- The national EMR terminology since 2014, with low uptake. No public download was found.
- Verdict: skip unless KHIS bundles it with the SNOMED Korean Extension.

**KorMedMCQA** **[v]**
- URL: https://huggingface.co/datasets/sean0042/KorMedMCQA
- Contents: 7,469 licensing-exam questions (doctor, nurse, pharmacist, dentist; 2012–2024).
- Licence: CC BY-NC 2.0.
- Use: mine Korean clinical vignettes containing comorbidities as realistic test inputs. It is not a
  linking label set.

**AI Hub (aihub.or.kr) medical datasets** **[k for per-dataset terms]**
- Candidates:
  - 초거대AI 헬스케어 질의응답 데이터: patient questions plus physician answers.
  - 전문분야 말뭉치 (의료/보건).
  - 필수의료 의학지식 데이터.
  - 질병 관련 상담/문진 대화 sets.
- Access: AI Hub account plus a per-dataset application (사용신청서). Datasets with privacy risk are
  usable only inside the **Safe Zone (안심존)** **[v]**. Use is generally limited to domestic users,
  with no export abroad and no redistribution of raw data.
- Feasible here because CONI is in Korea. Have a Korea-resident team member apply in their own name.
- Use: large Korean patient-language text. Mine "증상/병명" phrases, pair them with KCD through the
  dictionary, and use them as Korean lay-query seeds instead of (or to check) Claude-generated Korean
  queries.
- Do not export the raw text into the shipped bundle.

**대한의사협회 의학용어집** **[k]**
- The English↔Korean medical term standard, but copyrighted and searchable online only. Skip.

### Area 3. Disease → organ / body-system labels

The current organ map (`conf/ontology/mondo_organ_axis.yaml`) comes from the MONDO `is_a` closure
alone, which makes it a single voter. Each source below is an independent voter keyed through MONDO
xrefs that are already in `mondo.obo`. Combining them gives:

1. per-axis agreement scores, and
2. a held-out organ truth to measure the MONDO-only map against.

**MeSH 2026 descriptors and tree numbers** **[k]**
- URL: https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/ (desc2026.xml, about 300 MB;
  `.bin` ASCII is smaller)
- Licence: NLM terms (free, with attribution and the MeSH version stated).
- MONDO has 8,212 `MESH:` xrefs.
- C-tree to axis:

| MeSH C branch | Axis |
|---|---|
| C14 Cardiovascular | cardiovascular |
| C06 Digestive (C06.552 Liver, C06.130 Biliary) | gastrointestinal, hepatic |
| C08 Respiratory Tract | pulmonary |
| C12 Urogenital (C12.777 / C12.050 kidney) | renal |
| C10 Nervous System | neurologic |
| C11 Eye | ocular |
| C09 Otorhinolaryngologic (C09.218 ear) | otologic |
| C17 Skin and Connective Tissue (C17.800 skin) | dermatologic |
| C19 Endocrine, C18 Nutritional and Metabolic | metabolic_endocrine |
| C05 Musculoskeletal | musculoskeletal |
| C15 Hemic and Lymphatic | haematologic |
| C01 Infections, C20 Immune System | infectious_immune |

- Use: the cleanest anatomical second voter. Multiple tree numbers per descriptor give the multi-organ
  assignments the scoring layer wants.

**Disease Ontology (DOID)** **[k]**
- URL: https://github.com/DiseaseOntology/HumanDiseaseOntology (`doid.obo`)
- Licence: CC0.
- MONDO has 12,091 `DOID:` xrefs, the second-largest prefix.
- DOID's top level under "disease of anatomical entity" is organ-system classes: cardiovascular system
  disease, gastrointestinal system disease, respiratory system disease, urinary system disease, nervous
  system disease, endocrine system disease, integumentary system disease, musculoskeletal system disease,
  immune system disease, hematopoietic system disease, and so on. These map almost 1:1 onto the axes.
- Effort: a 30-line closure walk.

**ICD-10 / ICD-11 chapters** **[k]**
- MONDO has 2,205 `ICD10CM:`, 209 `ICD10WHO:` and 4,637 `icd11.foundation:` xrefs.
- ICD-10 chapter ranges are a fixed table (I = infectious; III = blood/immune; IV = endocrine/metabolic;
  VI = nervous; VII = eye; VIII = ear; IX = circulatory; X = respiratory; XI = digestive (K70–K77
  liver); XII = skin; XIII = musculoskeletal; XIV = genitourinary (N00–N29 kidney)). No download needed.
- ICD-11 linearisation chapters come from the WHO ICD API (free registration; licence CC BY-ND 3.0 IGO,
  so use the codes and do not modify-and-redistribute the classification).
- Bonus: this is also the bridge that lets KCD (Korean) and HuDiNe/DTB pairs inherit axes without MONDO.

**Orphanet classifications and linearisation** **[v]**
- URL: https://www.orphadata.com (bulk XML: `en_product3_*` per-specialty classification trees and
  `en_product7` linearisation with a single preferred parent)
- Licence: CC BY 4.0, commercial use included.
- MONDO has 10,495 `Orphanet:` xrefs.
- Use: rare-disease organ assignment, where MeSH and ICD are sparse. The classification heads ("rare
  hepatic disease", "rare renal disease", "rare eye disease") map straight to axes.

**HPO organ-system branches** (already on disk)
- The HPO top-level children of "Phenotypic abnormality" (HP:0000118) are organ systems: abnormality of
  the cardiovascular system, of the eye, of the ear, and so on.
- `hpoa.tsv` attaches HPO terms to OMIM/Orphanet diseases → MONDO.
- Voting: fraction of a disease's annotated phenotypes per organ branch, which gives a *soft* organ
  profile per disease for free. Useful as a learned-head feature as well as ground truth.

**MONDO `disease_has_location` → UBERON/CL** **[measured locally]**
- 3,372 `disease_has_location` lines in the 2026-10-07 `mondo.obo`.
- UBERON (CC BY 3.0) `part_of` closure up to system classes (e.g. UBERON:0001009 circulatory system,
  UBERON:0001004 respiratory system) gives an anatomical label.
- Independence: this is not independent of MONDO itself, but it is independent of the `is_a` path the
  current map uses.

**phecodeX** **[v]**
- URL: https://github.com/PheWAS/phecodeX
- Files:
  - `phecodeX_R_map_ICD_10_WHO.csv`: 2,872 of 3,612 phecodes reachable from WHO ICD-10.
  - `phecodeX_R_map.csv`: ICD-9-CM / ICD-10-CM.
  - `phecodeX_R_labels.csv`: has a `group` category column (organ-system groups such as CV, GI, RE, GU,
    NS, EY, EM, DE, MS, ID, BI). Confirm the exact group codes in the file.
- Licence: **the repo has no LICENSE file**. Using it internally for evaluation is standard practice; ask
  VUMC (Lisa Bastarache) before redistributing. Phecode Map 1.2 (https://www.vumc.org/wei-lab/phecode)
  is the older alternative.
- Use:
  1. An organ voter via ICD-10.
  2. The join key for every UK Biobank and PheWAS-catalog pair table in area 4.

**SNOMED CT finding site (363698007) and associated morphology** **[v membership]**
- Concept-level, curated organ ground truth. Its finding-site axioms are the strongest single source
  here.
- MONDO has 9,171 `SCTID:` xrefs.
- Licence: an affiliate licence is needed. In Korea, apply through KHIS (Korea is a member, so no
  International fee for use inside Korea). Never redistribute SNOMED content; ship only derived axis
  labels and get KHIS to confirm that is fine.
- One application also unlocks the Korean Extension (area 2).

**UMLS semantic types**
- `T047` vs `T184` and similar distinguish disease from sign/symptom, not organ. Use them for the
  **disease gate**: label negatives "symptom, not a disease" without hand work. Needs UMLS (area 1).

### Area 4. Disease-pair / comorbidity summary statistics for independent validation

The validators in hand are HuDiNe (US Medicare, ICD-9), Jensen 2014 and Siggaard 2020 (Denmark,
ICD-10) and FinnGen (partial). What is missing is a primary-care source, a biobank source and an
East-Asian source.

**CPRD, Kuan et al. 2023, *Lancet Digital Health* 5:e16** **[v]**
- Data: 308 conditions, 3.87M patients, CPRD + HES, 2010–2015. Co-occurrence beyond chance, stratified
  by sex, age and ethnicity.
- Access: online interactive tools from the UCL MMTRC group; whether a bulk export exists is not
  verified. The 308 phenotype definitions (Read/ICD-10) are in the HDR UK Phenotype Library under CC BY
  **[k]**.
- Use: UK primary-care pairs over ICD-10-defined conditions → MONDO via ICD10 xrefs.
- Next step: check the paper's supplement and the tool for CSV export, or ask the authors.

**UK Biobank published tables** **[v]**
- Bioinformatics paper on an "inter-disease interactivity network": 427 phenotypes, code and data on
  GitHub.
- medRxiv 2021 "genetic comorbidity": 439 diseases, 385k inpatients, with a supplement.
- Both are at phecode level and join through phecodeX.
- UKB itself is application-only (fee). Use only the published tables.

**Korean NHIS** **[v]**
- Ko et al. 2020, *JMIR* 22:e15196 (PMC7180516): NHIS-NSC, 1M people, 2002–2013, 520 KCD-6 codes →
  294 nodes and 3,085 directed edges with RR > 4. CC BY, **but no edge list**: the appendices hold only
  cluster composition and enrichment.
- A Korean nationwide-claims network (SKKU, about 2016): 381 codes → 5,515 pairs with OR > 5.
- Access: request the edge lists from the corresponding authors (Hyun Wook Han for Ko 2020). The raw
  NHIS-NSC needs an NHIS application and an on-site/remote analysis centre (months).
- Value: the only Korean-population check for the vulnerability head, which matters because the app's
  users are Korean.

**Taiwan NHIRD** **[v paper]**
- Jiang et al. 2018, *Sci Rep* 8:4557 (doi 10.1038/s41598-018-21779-y), an epidemiological human
  disease network. CC BY.
- The supplement was not checked (PMC served a captcha); check it on nature.com.

**Japan JMDC** **[v]**
- Commercial claims database (about 14M people). No published all-pairs table was found. Skip.

**PheWAS Catalog** (phewascatalog.org) **[k]**
- SNP–phecode associations, not disease–disease. It could support a "genetic correlation" view, but it
  is not comorbidity validation. Skip for now.

### Area 5. ADC toxicity beyond labels

**Pooled ADC AE meta-analyses**
- Li et al. 2023, *Cancer Innovation* 2:346 (PMC10686142) **[v]**:
  - 138 studies, 15,473 patients, 14 ADCs (T-DM1, T-DXd, SG, EV, BV, Pola, TV, loncastuximab,
    belantamab, disitamab, GO, InO, moxetumomab, RM-1929).
  - Licence CC BY 4.0.
  - Supplement: eFigure 3 gives pooled any-grade / grade ≥3 rates **per ADC**; eTables give rates by
    payload, linker and antibody.
- Zhu et al. 2023, *Cancer* 129:283 **[k: venue; v: numbers]**:
  - 169 trials, 22,492 patients.
  - Per-ADC grade ≥3 rates for neutropenia, thrombocytopenia, ocular and neuropathy events are in the
    supplementary tables.
  - Licence: check Wiley OA status.
- Use: an external ranking check per (ADC, organ axis). Extract numbers only, under the existing PMC
  licence posture: facts are free, verbatim text is not.
- Organ-specific pooled analyses worth pulling the same way **[k]**:
  - T-DXd ILD pooled analysis (Powell et al., *ESMO Open* 2022).
  - Ocular toxicity meta-analyses across MMAF/DM4 ADCs.
  - Peripheral neuropathy across MMAE ADCs.

**Spontaneous-report systems beyond FAERS and JADER** **[k]**
- **Canada Vigilance Adverse Reaction Online Database**: full extract download under the Open
  Government Licence – Canada, so training use and redistribution are fine. Small for ADCs but clean.
  Same disproportionality code as `ml/validate_faers.py`.
- **EudraVigilance, adrreports.eu**: per-substance ICSR counts by SOC/PT and line listings. Free web;
  the EMA terms forbid re-identification and want attribution. No bulk API, so use per-ADC exports
  (about 15 substances).
- **UK MHRA Yellow Card iDAPs**: per-drug PDF/CSV by SOC. Free.
- **VigiBase** **[v]**:
  - VigiAccess is click-through and aggregated by ingredient and region with SOC counts. Fine for
    reading, not for systematic scraping.
  - The VigiBase Extract is an annual paid licence with an academic tier.
  - Custom searches are billed hourly at a non-profit discount.
  - Worth it only if the paper needs a worldwide PV denominator.

## 3. Do first: top 5 with next steps

1. **Multi-source organ ground truth (MeSH + DOID + ICD-10 chapter + Orphanet + HPO + UBERON location).**
   - Download:
     - MeSH `desc2026.xml` (NLM)
     - `doid.obo` (DO GitHub release)
     - Orphadata `en_product3_*.xml` and `en_product7.xml`
     - `uberon-basic.obo`
     - HPO and MONDO are already on disk.
   - Write `ml/organ_voters.py`. For each MONDO id, follow xrefs (`MESH:`, `DOID:`, `ICD10WHO:`/`ICD10CM:`,
     `Orphanet:`, `HP:` via hpoa, `disease_has_location`) and emit
     `{mondo, axis, voter, evidence}` rows into `data/curated/organ_votes.jsonl`.
   - Put each voter's branch → axis table in a YAML next to `conf/ontology/mondo_organ_axis.yaml`.
   - Report per-axis agreement with the current MONDO `is_a` map, and use the majority of the
     non-MONDO voters as the held-out truth for the comorbidity-to-organ step.
   - Effort: about 1–2 days.

2. **phecodeX as organ voter and join key.**
   - Download: `phecodeX_R_map_ICD_10_WHO.csv`, `phecodeX_R_labels.csv` and `phecodeX_R_map.csv` from
     github.com/PheWAS/phecodeX.
   - Add a phecode voter to step 1: ICD-10 → phecode → `group` → axis.
   - Write `ml/phecode_bridge.py` (MONDO ↔ ICD-10 ↔ phecode), so that UK Biobank and CPRD pair tables
     (area 4) load with no new mapping work.
   - E-mail VUMC about redistribution before any derived file ships.
   - Effort: half a day.

3. **Lay-term linking pairs: MedlinePlus + CHV + PsyTAR + AskAPatient/MedNorm.**
   - Download:
     - the MedlinePlus compressed topic XML;
     - the GWU CHV concepts-terms file;
     - `bigbio/psytar` (or the original release);
     - AskAPatient from Zenodo and MedNorm from GitHub (verify the URLs and licences first).
   - Add one function per source to `ml/build_external_linking.py`. Each maps CUI/SNOMED/MeSH → MONDO
     through the existing `xrefs()` and writes into `mentions_mondo.jsonl` with `source=` tags.
   - Keep the provenance split: training sources vs a held-out lay test (PsyTAR DI spans and a 300-item
     MedlinePlus sample).
   - Re-run `ml/eval_linking.py` with a per-source breakdown so the gain on lay input is measured on
     its own.
   - Effort: about 1–2 days.

4. **Korean whole-sentence input: KBMC + KCD index synonyms.**
   - Download `SungJoo/KBMC` from Hugging Face (Apache-2.0, 1.5 MB).
   - Write `ml/kbmc_spans.py`:
     1. Read the BIO tags and keep the disease spans.
     2. Link each span with the current Korean dictionary path (HIRA KCD names) plus SapBERT.
     3. Hand-check 200 spans with the team sheet tooling (`ml/team_sheets.py`).
   - This gives a Korean sentence → span → MONDO eval set.
   - In parallel, fetch the KCD classification Excel and index from kssc.kostat.go.kr to add Korean
     alternate names.
   - Effort: about 2 days.

5. **SNOMED CT affiliate licence via KHIS, started now because it takes weeks.**
   - Apply through KHIS (the Korean NRC) or the SNOMED MLDS for an affiliate licence covering the
     International edition and the Korean Extension.
   - Once granted:
     - `ml/snomed_finding_site.py` reads the RF2 relationship file (attribute 363698007), rolls body
       structures up to the organ axes, and joins MONDO via `SCTID:`. This is the strongest organ voter
       for step 1.
     - Korean Extension descriptions become Korean synonyms for SapBERT.
   - Ship only the derived axis labels, after KHIS confirms that is allowed.
   - Effort: a 1-hour application and about 2 days of code after approval.

Next tier, after the five above:

* E-mail the Ko 2020 (JMIR) authors for the Korean NHIS edge list, and check the Kuan 2023 CPRD tool
  for an export. Both are cheap asks with high validation value.
* Extract numbers from the Li 2023 and Zhu 2023 supplements into the existing PMC-numbers pipeline.
* Add Canada Vigilance as a third spontaneous-report validator.
* Start AI Hub applications in a Korea-resident team member's name.

## Sources checked for this note

- DDXPlus: https://figshare.com/articles/dataset/DDXPlus_Dataset/20043374 ; https://arxiv.org/abs/2205.09148
- KorMedMCQA: https://huggingface.co/datasets/sean0042/KorMedMCQA ; https://arxiv.org/abs/2403.01469
- KBMC: https://huggingface.co/datasets/SungJoo/KBMC ; https://arxiv.org/abs/2403.16158
- CSIRO DAP licences: https://research.csiro.au/dap/licences/csiro-data-licence
- phecodeX: https://github.com/PheWAS/phecodeX ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10627409/
- Orphadata licence / linearisation: https://www.orphadata.com ; https://www162.lamp.le.ac.uk/vocabularies/ordo
- SNOMED Korea / KHIS: https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-starter-guide/14-the-organization-behind-snomed-ct ; https://conf.spaces.snomed.org/wiki/spaces/RMT/pages/414711848
- KOSTOM: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10155087/
- KRISSBERT: https://huggingface.co/microsoft/BiomedNLP-KRISSBERT-PubMed-UMLS-EL
- CHV: https://biomedinfo.smhs.gwu.edu/chv-files ; https://www.nlm.nih.gov/research/umls/sourcereleasedocs/current/CHV
- MedlinePlus XML: https://medlineplus.gov/xml.html ; https://medlineplus.gov/xmldescription.html
- KDCA API: https://www.data.go.kr/data/15087442/openapi.do
- BioRED: https://pmc.ncbi.nlm.nih.gov/articles/PMC9487702
- PsyTAR mirror: https://huggingface.co/datasets/bigbio/psytar
- SMM4H 2017: https://pmc.ncbi.nlm.nih.gov/articles/PMC6188524
- n2c2 2019 T3: https://portal.dbmi.hms.harvard.edu/projects/n2c2-2019-t3 ; https://n2c2.dbmi.hms.harvard.edu/2019-track-3
- Korean networks: https://pmc.ncbi.nlm.nih.gov/articles/PMC7180516/ ; https://pure.skku.edu/en/publications/network-analysis-of-human-diseases-using-korean-nationwide-claims/
- Taiwan: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5852024/
- CPRD Kuan 2023: https://livrepository.liverpool.ac.uk/3167169/
- UK Biobank pair papers: https://www.ukbiobank.ac.uk/publications/discovering-comorbid-diseases-using-an-inter-disease-interactivity-network-based-on-biobank-scale-phewas-data/ ; https://www.medrxiv.org/content/10.1101/2021.01.15.21249242v1
- JMDC: https://www.bridgetodata.org/node/107473
- ADC meta-analyses: https://pmc.ncbi.nlm.nih.gov/articles/PMC10686142/ ; https://ecancer.org/en/news/22395-analysis-reveals-adverse-effects-of-complex-cancer-therapies-called-antibody-drug-conjugates
- VigiBase access: https://who-umc.org/vigibase-data-access/vigibase-extract ; https://who-umc.org/vigibase/vigibase-faqs/
