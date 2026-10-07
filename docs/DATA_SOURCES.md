# Data sources, licences and what may be redistributed

Every source here was verified live on 2026-10-07. Counts are measured, not estimated.

| Source | Used for | Licence | Redistribution posture |
|---|---|---|---|
| ClinicalTrials.gov API v2 | arm-level adverse events, eligibility text, the PT->SOC dictionary | US Government public domain | Derived numbers published freely |
| openFDA drug label | design metadata, hepatic/renal impairment statements | public domain | Quoted freely |
| DailyMed SPL history | dated label-change detection | public domain | Quoted freely |
| Human Protein Atlas / GTEx | **not ingested in this build** -- see note | CC BY 4.0 / open | n/a |
| SIDER 4.1 | reference lookup only, never a training source | CC BY-SA 4.0 | Not redistributed |
| MONDO | comorbidity organ mapping | CC BY 4.0 | Attributed |
| AHRQ Elixhauser CMR | comorbidity severity ordering | US Government public domain | Attributed |
| PMC Open Access subset | literature adverse-event tables | per-article; recorded per row | See below |

## MedDRA

MedDRA is licensed terminology. We do not hold a licence and do not need one: the
preferred-term and System Organ Class strings we rely on arrive **inside** public-domain
FDA and ClinicalTrials.gov records.

What we are careful about is redistribution. Publishing a 7,000-term PT -> SOC dictionary
would arguably redistribute a substantial portion of MedDRA, so:

* the dictionary is built locally by `scripts/build_taxonomy.py` and is gitignored;
* only the script that regenerates it from public-domain records ships;
* the axis grouping (`conf/ontology/axes.yaml`) is our own definition, not a MedDRA
  hierarchy, and that is stated wherever the taxonomy is described.

The claim is therefore **not** "we do not use MedDRA" -- the SOC layer *is* the MedDRA
SOC layer, and saying otherwise to a reader who knows the licence would backfire. The
claim is that we redistribute no MedDRA artefact.

## PMC Open Access

The extraction pipeline is structurally confined to the OA subset: `efetch` refuses full
text for non-OA articles ("The publisher of this article does not allow downloading of
the full text in XML form"), so there is no path by which the automated route touches
licensed full text.

Within the OA subset the licence still varies per article, and the per-row `license_code`
is recorded so the posture can be applied row by row:

* **extracted numbers** -- published for every row. A measured incidence is a fact, not
  a copyrightable expression.
* **verbatim table and caption text** -- published only for CC BY articles (about 39% of
  the ADC OA corpus). For CC BY-NC-ND and TDM-licensed articles we publish the number,
  the PMCID, the table label and a paraphrase.

Bulk access uses the AWS Open Data mirror (`pmc-oa-opendata`), which is the sanctioned
bulk route; the PMC website's terms prohibit systematic downloading from the site itself.

## Sources deliberately not used

| Source | Why not |
|---|---|
| adctoxicityatlas.org | No stated licence, no download, no API. Cited as prior work; nothing ingested. |
| ADCdb | Same -- `/download` exposes no file and no licence text. Cited only. |
| DisGeNET | The free academic tier needs an institutional e-mail and a licence application; the full database is a paid subscription. Open Targets (CC0) and DISEASES (CC BY) cover the same ground. |
| KEGG | FTP and bulk access require a paid academic subscription. Reactome (CC0) is used instead. |
| CTD | Downloads are reachable unauthenticated, but the licence obliges a backlink from every display context plus usage reporting. Reactome covers the pathway side under CC0. |
| MIMIC-IV | Excluded on relevance, not access: it is an ICU database and ADC patients are ambulatory oncology, so exposure is essentially absent. |
| FAERS, as an incidence source | Disproportionality has no denominator. Retained only as a qualitative consistency check. |

## Sources listed in the plan but not ingested in this build

Recorded here rather than left as an unmarked row, because a source listed in this table
reads as a source the pipeline uses.

**Human Protein Atlas / GTEx** -- intended to supply per-organ target expression for
constraint C3, the selectivity index. Nothing in the repository fetches it, so C3 is
implemented, threaded through three layers of call signature, and never evaluated: no
candidate is screened on selectivity. `ConstraintEngine.active_constraints()` reports it
as declared-but-inactive so the gap is stated at runtime too.

The omission is deliberate as well as unfinished. GTEx reports `ERBB2` at a median 86.7
TPM in aorta and 66.6 in tibial artery, which would have the index call HER2 an artery
gene; HER2 cardiotoxicity is real but cardiomyocyte, not aortic smooth muscle. The plan
already concluded that the index belongs on screen as a flag rather than in the ranking.
What was wrong was not the decision but leaving it silent.

**MONDO** is used for the hand-pinned `mondo_id` column in the comorbidity registry,
which was curated against it; the ontology is not loaded at runtime. **SIDER** is cited
for the negative result that chemistry-to-organ transfer cannot be learned from it, and
is not read by any code path.
