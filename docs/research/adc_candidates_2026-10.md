# ADC candidates beyond the current 14 (checked 2026-10-15)

Scope: every antibody-drug conjugate (and two near-ADC conjugates) that is approved somewhere (FDA, EMA, PMDA/MHLW, NMPA, MFDS) or is filed or in phase 3, **excluding** the 14 agents already in `conf/dailymed_setids.yaml`.
Machine-readable copy: `docs/research/adc_candidates_2026-10.json`. Organ names follow `conf/ontology/axes.yaml`.

How this was checked:
- **DailyMed:** I queried the DailyMed v2 API on 2026-10-15 (database published 2026-10-14) by INN fragment for every candidate, and by payload suffix (`-deruxtecan`, `-vedotin`, `-tirumotecan`, `-mafodotin`, `-ozogamicin`, `-tesirine`, `-sunirine`, `-soravtansine`, `-ravtansine`, `-govitecan`, `-emtansine`).
  - Only two new US set ids exist: BLENREP and LUMOXITI.
  - Every other suffix hit is one of the 14 agents the app already has.
- **Other evidence:** label text is quoted from the SPL XML and from the EMA SmPC PDF. Trial numbers come from PubMed abstracts (efetch). Approval facts come from company releases and trade press.
- **Reliability:** anything marked **UNVERIFIED** came from a single secondary source or was not checked against a primary document.
- **MFDS (Korea):** I found no Korea-first ADC approval. The search tool does not index mfds.go.kr, so this is not proof that none exists.

## Summary table

| Agent (brand) | Status (first / key approval) | US label | DailyMed set id (resolves 2026-10-15) | Organ warnings (label or pivotal trial) |
|---|---|---|---|---|
| belantamab mafodotin (BLENREP) | FDA re-approved 2025-10-23 (BVd, REMS); EU 2025-07-23; JP 2025-05 | **y** | `aef7c34c-fef8-407c-99c0-a68aded53c60` (yes; v1 2025-11-17, v2 2026-10-06) | **Boxed: ocular**; thrombocytopenia; hepatotoxicity G3-4 14%; pneumonia; EU adds pneumonitis and HBV |
| moxetumomab pasudotox (LUMOXITI) | FDA 2018-09-13; off the market 2023 (immunotoxin, not a chemical ADC) | y (historical) | `8ddffb08-aab1-41f5-bbc6-09457e4e80ca` (yes; last 2020-09-08) | **Boxed: capillary leak + HUS**; renal toxicity; not for CrCl <=29 |
| disitamab vedotin (AIDIXI) | NMPA 2021-06-09 (GC), 2021-12-31 (UC), breast (date UNVERIFIED), 2026-03 HER2-low BC, 2026-04 1L UC with toripalimab | n | - | G>=3 TRAE 55.1% (combination); ILD death; neuropathy, GGT (rates UNVERIFIED) |
| sacituzumab tirumotecan (JIATAILAI; MK-2870) | NMPA 2024-11 (TNBC), 2025 x2 (EGFR-mut NSCLC), 2026-02-06 (HR+/HER2- BC); US filing expected Oct-Nov 2026 | n | - | haematologic (neutrophils G>=3 39.9%); no drug-related ILD in Lung04 |
| trastuzumab rezetecan (AIWEIDA; SHR-A1811) | NMPA 2025-05-29 (HER2-mutant NSCLC); breast sNDA under priority review | n | - | haematologic (neutrophils G>=3 40-54%); ILD 3-5% |
| trastuzumab botidotin (SHUTAILAI; A166) | NMPA 2025-10-17 (HER2+ mBC) | n | - | **ocular** (corneal disorders 92.9% any grade); G>=3 TEAE 69.8% |
| becotatug vedotin (MEIYOUHENG; MRG003) | NMPA 2025-10-30 (R/M NPC, 3L+) | n | - | G>=3 TRAE 50.6% (phase 3, secondary report); rash, hypoesthesia, cytopenias |
| izalontamab brengitecan (iza-bren; BL-B01D1) | NMPA 2026-06-22 (NPC, conditional), 2026-07-17 (ESCC); first bispecific ADC | n | - | **haematologic** (G>=3 anaemia 50%, platelets 43%); G>=3 TRAE 80%; 2% TR deaths |
| cetuximab sarotalocan (AKALUX; RM-1929) | Japan 2020-09 conditional (photoimmunotherapy, IR700) | n | - | local/airway: laryngeal edema, haemorrhage, pain, photosensitivity |
| ifinatamab deruxtecan (I-DXd) | FDA BLA (PDUFA 2026-10-10) **withdrawn ~2026-09-25**; phase 3 IDeate-Lung02 ongoing | n | - | **pulmonary**: adjudicated ILD 12.4% (G>=3 4.4%) |
| patritumab deruxtecan (HER3-DXd) | CRL 2024-06; BLA **withdrawn 2025-05-29** | n | - | pulmonary: ILD 5.2% (2 fatal); TR G>=3 57.9% |
| trastuzumab pamirtecan (DB-1303/BNT323) | NMPA BLA accepted 2026-04-09 (HER2+ BC); US BLA planned 2026 (endometrial) | n | - | not collected |
| arcotatug tavatecan (IBI343) | NMPA NDA accepted 2026-06-04 (CLDN18.2 GC, priority) | n | - | data pending (ESMO 2026 LBA) |
| tecotabart vedotin (LM-302) | NMPA application accepted ~2026-06-23 (one Chinese source, UNVERIFIED) | n | - | data pending |
| raludotatug deruxtecan (R-DXd) | phase 2/3 REJOICE-Ovarian01; FDA BTD 2025-09 | n | - | - |
| telisotuzumab adizutecan (Temab-A) | phase 3 mCRC (3 trials) | n | - | FIH GEA: G>=3 TEAE 88% |
| zilovertamab vedotin | phase 3 waveLINE-010 (1L DLBCL) | n | - | - |
| sigvotatug vedotin | phase 3 SigVie-002 **missed OS**; 1L combination phase 3 ongoing | n | - | - |
| rinatabart sesutecan (Rina-S) | phase 3 RAINFOL-02 / RAINFOL-10 | n | - | - |
| puxitatug samrotecan (AZD8205) | phase 3 Bluestar-Endometrial01 | n | - | - |
| tusamitamab ravtansine | **discontinued** 2023-12 (CARMEN-LC03 failed) | n | - | ocular (DM4 class; not collected) |
| upifitamab rilsodotin | **discontinued** 2023-07 (UPLIFT failed; fatal bleeding) | n | - | bleeding (G5 <1%) |

Not tabled:
- **trastuzumab duocarmazine** (SYD985) received an FDA complete response letter in 2023 and is not approved anywhere (from memory, UNVERIFIED).
- **New indications for agents the app already has** (DATROWAY TNBC 2026-05, ENHERTU early BC 2026-05, TRODELVY 1L TNBC 2026-06, DECNUPAZ 2026-05) are outside this list. They arrive through the existing set ids.

---

## 1. belantamab mafodotin - BLENREP (GSK)

- **Codes:** GSK2857916; US suffix -blmf.
- **Design:**
  - Target: BCMA.
  - Payload: MMAF (cys-mcMMAF).
  - Linker: maleimidocaproyl, **non-cleavable**.
  - DAR: about 4.
  - Antibody: afucosylated IgG1.
- **Approvals:**
  - **US:** first accelerated approval 2020-08 (monotherapy, DREAMM-2), withdrawn 2022-11. Re-approved **2025-10-23** with bortezomib + dexamethasone for adult relapsed/refractory multiple myeloma (RRMM) after >=2 prior lines including a PI and an IMiD, with a REMS. The current SPL indication text confirms this; the date comes from the chemexpress landscape.
  - **EU:** first authorisation **23 July 2025** (SmPC section 9). Covers BVd and BPd.
  - **Japan:** MHLW approval 2025-05. The report is dated 2025-05-20; the exact decision day is UNVERIFIED.
- **DailyMed:** set id `aef7c34c-fef8-407c-99c0-a68aded53c60`, which resolves (HTTP 200).
  - `history.json` shows v1 2025-11-17 and v2 2026-10-06.
  - The 2020-2022 label history is **not** under this set id, so the old label would need its own lookup if dated warnings matter.
- **Boxed warning (US):**
  > WARNING: OCULAR TOXICITY. BLENREP causes changes in the corneal epithelium resulting in changes in vision, including severe visual impairment, and symptoms such as blurred vision and dry eyes. In the clinical study, corneal ulcers, including cases with infection, also occurred ... 83% of patients required a dosage modification due to ocular toxicity ... available only through ... the BLENREP REMS.
- **Warnings and precautions (US):**
  - 5.1 Ocular Toxicity: in DREAMM-7, 92% any grade, **77% Grade 3-4**.
  - 5.2 BLENREP REMS.
  - 5.3 Thrombocytopenia: Grade 3 in 29%, Grade 4 in 45%.
  - 5.4 Embryo-fetal Toxicity.
- **EU SmPC 4.4 headings:** Ocular adverse reactions; Thrombocytopenia; Infusion-related reactions; Pneumonitis; Hepatitis B virus reactivation.
- **Renal impairment:**
  - US: there is no 8.x renal subsection. 12.3 reads:
    > No clinically significant differences in the pharmacokinetics of belantamab mafodotin-blmf were observed based on ... mild to severe renal impairment and kidney failure (eGFR <30 mL/min)
  - EU SmPC 4.2:
    > No dose adjustment is recommended in patients with mild (eGFR 60-89 mL/min), moderate (eGFR 30-59 mL/min), severe renal impairment (eGFR < 30 mL/min not requiring dialysis), or end-stage renal disease (eGFR < 15 mL/min requiring dialysis) (see section 5.2).
- **Hepatic impairment:**
  - US 8.6:
    > No dose adjustment is recommended for patients with mild hepatic impairment (total bilirubin > upper limit of normal [ULN] to ≤1.5 × ULN and any aspartate aminotransferase [AST] or total bilirubin ≤ULN with AST >ULN). The recommended dose of BLENREP has not been established in patients with moderate or severe hepatic impairment [see Clinical Pharmacology (12.3)].
  - EU SmPC 4.2: there are limited data in moderate or severe impairment, and Blenrep "should only be used in these patients if the potential benefits outweigh any potential risks".
- **Grade 3-4 by organ** (US Table 4/5, DREAMM-7 BVd arm, n=242):

  | Organ | Grade 3-4 events |
  |---|---|
  | Ocular | reduction in BCVA 57%; corneal exam findings 72%; blurred vision 22%; cataract 8%; dry eye 7%; eye irritation 5%; visual impairment 5% |
  | Haematologic (lab) | platelets 74%; lymphocytes 53%; neutrophils 17%; leukocytes 11% |
  | Hepatic | hepatotoxicity (grouped term) 14%; GGT increase is among the >=10% G3-4 lab abnormalities |
  | Infection | pneumonia 16%; COVID-19 5% |
  | GI | diarrhea 4% |
  | Constitutional | fatigue 6% |

  For comparison, DREAMM-8 (BPd) reported ocular G3-4 of 43% (NEJM 2024, PMID 38828951).
- **Sources:**
  - https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=aef7c34c-fef8-407c-99c0-a68aded53c60
  - https://www.ema.europa.eu/en/documents/product-information/blenrep-epar-product-information_en.pdf
  - https://www.gsk.com/en-gb/media/press-releases/european-commission-approves-blenrep-belantamab-mafodotin-for-the-treatment-of-patients-with-relapsed-and-refractory-multiple-myeloma/
  - https://www.thepharmaletter.com/gsks-blenrep-combination-approved-by-japan-mhlw
  - https://www.chemexpress.com/news-and-events/news/adc-global-landscape-2026H1

## 2. moxetumomab pasudotox - LUMOXITI (AstraZeneca), withdrawn

- **What it is:** a CD22 Fv genetically fused to PE38 (Pseudomonas exotoxin). It is a recombinant immunotoxin with no chemical linker and no DAR. `conf/adc_registry.yaml` already carries it as `fusion`, DAR 1.
- **Approval history:** FDA 2018-09-13 for relapsed/refractory hairy cell leukemia after >=2 prior therapies including a purine nucleoside analog. Withdrawn from the market in 2023. The EU authorisation and withdrawal dates are UNVERIFIED.
- **DailyMed:** set id `8ddffb08-aab1-41f5-bbc6-09457e4e80ca` still resolves; latest SPL 2020-09-08.
- **Boxed warning:** CAPILLARY LEAK SYNDROME and HEMOLYTIC UREMIC SYNDROME.
- **Warnings and precautions:** 5.1 Capillary Leak Syndrome; 5.2 Hemolytic Uremic Syndrome; 5.3 Renal Toxicity; 5.4 Infusion Related Reactions; 5.5 Electrolyte Abnormalities.
- **Renal impairment:**
  - Limitations of Use:
    > LUMOXITI is not recommended in patients with severe renal impairment (CrCl ≤ 29 mL/min)
  - 5.3: renal toxicity adverse events occurred in 26% (34/129).
    > Grade 3 acute kidney injury occurred in 1.6% (2/129) of patients.
  - 8.5: renal toxicity was 40% vs 20% in patients >=65 vs <65.
- **Hepatic impairment:** there is no 8.x subsection. 12.3 says PK in moderate to severe hepatic impairment (total bilirubin >1.5 ULN) "is unknown".
- **Grade >=3 by organ:**
  - HUS: G3 3%, G4 0.8%.
  - Acute kidney injury G3: 1.6%.
  - Infusion-related reactions G3: 3.8%.
- **Recommendation:** do not add it as a recommendable agent. It is off the market.

## 3. disitamab vedotin - AIDIXI (RemeGen; ex-China rights: Pfizer)

- **Codes:** RC48.
- **Design:** HER2 target; MMAE payload; mc-vc-PABC linker (cleavable); DAR about 4.
- **NMPA approvals:**
  - 2021-06-09 (conditional): HER2-overexpressing (IHC 2+/3+) gastric/GEJ cancer after >=2 chemotherapy lines.
  - 2021-12-31 (conditional): HER2-expressing urothelial carcinoma after platinum.
  - HER2+ breast cancer with liver metastases (date UNVERIFIED).
  - 2026-03: HER2-low breast cancer with liver metastases.
  - 2026-04: first-line HER2-expressing (IHC 1+/2+/3+) urothelial carcinoma with toripalimab.
- **US:** no BLA found.
- **Label:** the Chinese label was not retrieved, so warnings and renal/hepatic text are UNVERIFIED.
- **Trial evidence** (RC48-C016, NEJM 2025, PMID 41124210):
  - Grade >=3 treatment-related adverse events (TRAE): 55.1% vs 86.9% for chemotherapy.
  - Treatment-related deaths: 3 (1.2%), one each from acute respiratory failure, **ILD** and pneumonia.
  - Most common events: GGT increase, neutropenia, hypokalemia, lipase increase, hypoesthesia and peripheral neuropathy. Organ-level G>=3 rates are in the supplement and were not extracted.
- **Sources:**
  - https://pubmed.ncbi.nlm.nih.gov/41124210/
  - https://hemonc.org/wiki/Disitamab_vedotin_(Aidixi)
  - https://allsci.com/news/approvals/remegen-adds-5th-china-indication-for-her2-adc-in-urothelial-carcinoma/

## 4. sacituzumab tirumotecan - JIATAILAI (Kelun-Biotech; ex-China: Merck as MK-2870)

- **Design:** TROP2 target; KL610023 payload (belotecan-derived topoisomerase I inhibitor); pH-sensitive cleavable linker; DAR 7.4 (Kelun).
- **NMPA approvals** (four indications, wording from Kelun 2026-07-30):
  - TNBC after >=2 prior lines (2024-11).
  - EGFR-mutant non-squamous NSCLC after EGFR-TKI and platinum.
  - EGFR-mutant non-squamous NSCLC after EGFR-TKI. Exact dates for both NSCLC indications are UNVERIFIED (a database lists 2025-03-04 and 2025-09-30).
  - HR+/HER2- breast cancer (2026-02-06).
- **NMPA pending:** first-line NSCLC with pembrolizumab, and first-line TNBC.
- **US:** Breakthrough Therapy Designation 2024-12 for EGFR-mutant NSCLC. A national priority voucher was reported 2025-12. Submission is expected Oct-Nov 2026. Not on DailyMed.
- **Trial evidence:**
  - OptiTROP-Lung04 (NEJM 2026, PMID 41124220): treatment-related G>=3 58.0% vs 53.8%; neutrophil decrease 39.9%; treatment-related SAE 9.0% vs 17.6%; no drug-related ILD reported (secondary reports).
  - OptiTROP-Breast01 (PMID 40217078, conference data): G>=3 neutrophils 32.3%, anaemia 27.7%, WBC 25.4%. The stomatitis G>=3 rate was not found.

## 5. trastuzumab rezetecan - AIWEIDA (Hengrui; ex-China: Glenmark)

- **Codes:** SHR-A1811.
- **Design:** HER2 target; SHR9265 payload (topoisomerase I inhibitor); cleavable linker. DAR about 6 (UNVERIFIED).
- **NMPA:**
  - Approved 2025-05-29: HER2-activating-mutation NSCLC after >=1 prior therapy.
  - Breast cancer sNDA accepted 2025-09 with priority review. Approval not confirmed.
- **Trial evidence:**
  - HORIZON-Lung (Lancet Oncol 2025, PMID 40020696, n=94): G3-4 TRAE neutrophils 40%, WBC 27%, anaemia 23%, platelets 11%. ILD was a treatment-related SAE in 5%. No treatment-related deaths.
  - HORIZON-Breast01 (Lancet Oncol 2026, PMID 42385760, n=142): G>=3 neutrophils 54%, WBC 20%, platelets 11%. ILD 3% (one G3).

## 6. trastuzumab botidotin - SHUTAILAI (Kelun-Biotech)

- **Codes:** A166.
- **Design** (Kelun HKEX filing 2025-10-17): HER2 target; Duo-5 payload (MMAF-derived auristatin); stable enzyme-cleavable linker; **DAR 2**.
- **NMPA:** approved 2025-10-17 for HER2+ unresectable/metastatic breast cancer after >=1 prior anti-HER2 therapy.
- **Trial evidence** (KL166-III-06 vs T-DM1, JCO 2026, PMID 42727044):
  - G>=3 treatment-emergent adverse events (TEAE): 69.8% vs 63.7%.
  - **Ocular** toxicity dominates: corneal disorders 92.9%, dry eye 61.5% (any grade). It is the main cause of dose reduction. The G>=3 ocular rate is not in the abstract (UNVERIFIED).
  - Pulmonary, haematologic, hepatic and GI toxicity are described only as "low".
- **App relevance:** its organ profile is close to BLENREP's (MMAF class, ocular).

## 7. becotatug vedotin - MEIYOUHENG (Lepu Biopharma)

- **Codes:** MRG003.
- **Design** (Lepu HKEX 2025-10-30): EGFR target; MMAE payload; valine-citrulline linker, cleaved by lysosomal protease. DAR UNVERIFIED (about 3.8 in the literature).
- **NMPA:** approved 2025-10-30 for recurrent/metastatic nasopharyngeal carcinoma (NPC) after >=2 chemotherapy lines and a PD-(L)1 inhibitor. First EGFR ADC approved in China.
- **Trial evidence:**
  - Phase 3 (ASCO 2025 LBA6005): G>=3 TRAE 50.6%, per a secondary summary (UNVERIFIED).
  - Phase IIa (Med 2026, PMID 41720100, n=61): G>=3 TRAE 39%.
  - Combination study (JCO 2026, PMID 42641116): pruritus, hypoesthesia, anaemia and rash were the most common events.
  - Organs to flag: dermatologic (EGFR), neurologic (MMAE) and haematologic.

## 8. izalontamab brengitecan - iza-bren (Sichuan Biokin / SystImmune; BMS ex-China)

- **Codes:** BL-B01D1.
- **Design:** EGFR x HER3 **bispecific** target; Ed-04 payload (topoisomerase I inhibitor); cleavable linker; DAR about 8 (registry value).
- **NMPA approvals:**
  - 2026-06-22 (conditional, priority review): recurrent/metastatic NPC after >=2 chemotherapy lines and PD-(L)1. First approved bispecific ADC worldwide.
  - 2026-07-17: esophageal squamous cell carcinoma (ESCC) after platinum and PD-(L)1.
- **Trial evidence** (BL-B01D1-303, Lancet 2025, PMID 41125110):
  - G>=3 TRAE 80% vs 62%.
  - Haematologic G>=3: anaemia 50%, WBC 43%, platelets 43%, neutrophils 38%.
  - Serious TRAE 43%; 4 (2%) treatment-related deaths.
  - Non-haematologic events mostly G1-2.

## 9. cetuximab sarotalocan - AKALUX (Rakuten Medical)

- **What it is:** an EGFR antibody conjugated to the IR700 photoabsorber, activated with 690 nm light (photoimmunotherapy). It is not a cytotoxic-payload ADC.
- **Japan:** conditional early approval 2020-09 for unresectable locally advanced or recurrent head and neck cancer.
- **Label:** the PMDA label was not retrieved.
- **Reported risks** (retrospective series): tumor or carotid haemorrhage, laryngeal edema, pain, mucositis, photosensitivity.
- **Fit for the app:** poor. Its toxicity is local and procedural, not systemic organ toxicity.

## 10. ifinatamab deruxtecan - I-DXd (Daiichi Sankyo / Merck)

- **Design:** B7-H3 target; DXd payload; GGFG cleavable linker; DAR about 4 (UNVERIFIED).
- **FDA:** BLA accepted with priority review on 2026-04-13 (PDUFA 2026-10-10) for ES-SCLC after platinum. **Voluntarily withdrawn ~2026-09-25** after the FDA said IDeate-Lung01 did not support accelerated approval. The phase 3 IDeate-Lung02 continues.
- **Trial evidence** (IDeate-Lung01, JCO 2026, PMID 41086386, n=137 at 12 mg/kg):
  - G>=3 TRAE 36.5%.
  - **ILD 12.4% (G>=3 4.4%)**.
  - Treatment-related deaths 4.4%.
- **Sources:**
  - https://www.targetedonc.com/view/fda-application-withdrawn-for-i-dxd-in-small-cell-lung-cancer
  - https://www.biopharminternational.com/view/daiichi-sankyo-merck-pull-ifinatamab-deruxtecan-bla-sclc

## 11. patritumab deruxtecan - HER3-DXd (Daiichi Sankyo / Merck)

- **Design:** HER3 target; DXd payload; GGFG linker; DAR 8.
- **FDA:** complete response letter 2024-06 (third-party manufacturing inspection). BLA **withdrawn 2025-05-29** because the HERTHENA-Lung02 overall survival result was not significant.
- **Safety** (HERTHENA-Lung02, from secondary reports):
  - Treatment-related G>=3: 57.9% vs 46.1%.
  - Adjudicated ILD 5.2%, including 2 fatal cases.
- **Sources:**
  - https://www.thepharmaletter.com/biotechnology/daiichi-and-merck-pull-patritumab-deruxtecan-bla
  - https://www.onclive.com/view/patritumab-deruxtecan-does-not-improve-overall-survival-in-egfr-mutated-nsclc

## 12-14. Filed in China, no label yet

| Agent (code) | Target | Payload | Filing | Source |
|---|---|---|---|---|
| trastuzumab pamirtecan (DB-1303 / BNT323) | HER2 | topoisomerase I inhibitor; DAR about 8 (UNVERIFIED) | NMPA BLA accepted 2026-04-09 for HER2+ breast cancer. US BLA planned in 2026 for endometrial cancer (Breakthrough Therapy 2023; Fern-EC-01 phase 3 ongoing) | https://www.biontech.com/int/en/home/mediaroom/news/press-releases/2026/04/biontech-and-dualitybios-antibody-drug-conjugate-trastuzumab.html |
| arcotatug tavatecan (IBI343 / TAK-921) | CLDN18.2 | topoisomerase I inhibitor | NMPA NDA accepted 2026-06-04 with priority review, for 3L+ CLDN18.2+ gastric/GEJ cancer. G-HOPE-001 met its primary endpoint; ESMO 2026 late-breaking abstract | https://www.biospace.com/press-releases/worlds-first-cldn18-2-adc-for-regulatory-review-innovent-biologics-announces-ibi343-arcotatug-tavatecan-met-primary-endpoint-in-international-phase-3-study-in-advanced-refractory-gastric-cancer-and-nda-accepted-by-china-nmpa |
| tecotabart vedotin (LM-302) | CLDN18.2 | MMAE | NMPA application accepted ~2026-06-23 for 3L+ gastric/GEJ cancer. Single Chinese-language source (UNVERIFIED) | https://stock.10jqka.com.cn/20260623/c677649925.shtml |

## 15-22. Phase 3 or discontinued (no label; no organ evidence collected)

| Agent (codes) | Target / payload / linker / DAR | Status | Source |
|---|---|---|---|
| raludotatug deruxtecan (R-DXd, DS-6000) | CDH6 / DXd / GGFG / 8 | Phase 2/3 REJOICE-Ovarian01 (NCT06161025) recruiting. FDA Breakthrough Therapy 2025-09. No BLA | https://clinicaltrials.gov/study/NCT06161025 |
| telisotuzumab adizutecan (Temab-A, ABBV-400) | c-Met / topoisomerase I / cleavable / ? | Three phase 3 trials in mCRC (NCT06614192, NCT07525206, NCT06820463). First-in-human in gastroesophageal adenocarcinoma: G>=3 TEAE 88% | https://pubmed.ncbi.nlm.nih.gov/41910595/ |
| zilovertamab vedotin (MK-2140) | ROR1 / MMAE / vc / ~4 | Phase 3 waveLINE-010 (NCT06717347, first-line DLBCL) recruiting | Merck release 2025-02 |
| sigvotatug vedotin (SGN-B6A) | integrin beta-6 / MMAE / vc | Phase 3 SigVie-002 (NCT06012435) missed its OS primary endpoint vs docetaxel. First-line combination phase 3 ongoing | Pfizer topline (barchart) |
| rinatabart sesutecan (Rina-S) | FRalpha / exatecan / ~8 | Phase 3 RAINFOL-02 (NCT06619236) and RAINFOL-10 (NCT07859215) | ClinicalTrials.gov |
| puxitatug samrotecan (AZD8205) | B7-H4 / topoisomerase I / 8 | Phase 3 Bluestar-Endometrial01 | tipranks AZ trial notice |
| tusamitamab ravtansine (SAR408701) | CEACAM5 / DM4 / SPDB / 3.8 | **Discontinued 2023-12**: CARMEN-LC03 failed on PFS | https://www.fiercebiotech.com/biotech/sanofis-oncology-strategy-suffers-another-blow-adc-scrapped-over-phase-3-lung-cancer-fail |
| upifitamab rilsodotin (XMT-1536) | NaPi2b / AF-HPA / Dolaflexin / ~10 | **Discontinued 2023-07**: UPLIFT failed, plus a partial clinical hold for fatal bleeding | https://www.sec.gov/Archives/edgar/data/1442836/000110465923084538/tm2322196d1_8k.htm |

---

## What the app can add now

1. **BLENREP is the only agent ready for `conf/dailymed_setids.yaml`.**
   - Proposed entry: `belantamab_mafodotin: {brand: BLENREP, set_id: "aef7c34c-fef8-407c-99c0-a68aded53c60"}`. The set id resolved and `history.json` returned 2 versions on 2026-10-15.
   - `conf/adc_registry.yaml` already has `belantamab_mafodotin` (MMAF, mc, DAR 4), so only the set id is missing.
   - Caveat: the dated-warning history starts in 2025-11. The 2020-2022 label lives under a different (archived) set id, which I did not look up.
2. **LUMOXITI** (`8ddffb08-aab1-41f5-bbc6-09457e4e80ca`) resolves too, but the product is off the market. At most it could serve as a historical training label; it should not be recommendable.
3. **The six China-only approvals** need a non-DailyMed evidence source: disitamab vedotin, sacituzumab tirumotecan, trastuzumab rezetecan, trastuzumab botidotin, becotatug vedotin and izalontamab brengitecan.
   - Options: the NMPA 说明书 (package insert, via the NMPA/CDE database or the company), or the pivotal-trial safety tables already cited above.
   - None currently has verified label text for renal/hepatic impairment or warnings.
   - Four of the six are already known to the repo. disitamab vedotin, sac-TMT and iza-bren are in `conf/adc_registry.yaml`. trastuzumab rezetecan is only in `conf/discovered_agents.txt`.
   - **trastuzumab botidotin and becotatug vedotin are in neither file.**
4. **Agents to watch for a US label:**
   - **sac-TMT:** US submission expected Oct-Nov 2026 under the national priority voucher, so a fast approval is possible.
   - **trastuzumab pamirtecan:** US BLA planned in 2026.
   - **I-DXd:** off the near-term list after the withdrawal.
   - Re-run the DailyMed check (`spls.json?drug_name=tirumotecan` / `pamirtecan`) monthly.
5. **Cetuximab sarotalocan and the phase 3 / discontinued agents** have no organ-toxicity evidence fit for the recommender and should not be added.
