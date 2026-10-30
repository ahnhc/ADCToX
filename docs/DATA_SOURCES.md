# Data sources, licences and what may be redistributed

Every source here was verified live on 2026-10-07. Counts are measured, not estimated.

| Source | Used for | Licence | Redistribution posture |
|---|---|---|---|
| ClinicalTrials.gov API v2 | arm-level adverse events, eligibility text, the PT->SOC dictionary | US Government public domain | Derived numbers published freely |
| openFDA drug label | design metadata, hepatic/renal impairment statements | public domain | Quoted freely |
| DailyMed SPL history | dated label-change detection | public domain | Quoted freely |
| GTEx (via Open Targets) | per-organ target expression, bulk RNA | CC0 (Open Targets) | Attributed |
| Tabula Sapiens (via Open Targets) | per-organ and per-cell-type target expression | CC0 (Open Targets) | Attributed |
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

The app's trial table (`data/curated/competition/trial_ae.json`, built by `ml/build_trial_ae.py`)
quotes at most a few event terms per organ and trial, as they appear in the public
ClinicalTrials.gov records, with their counts. It carries no PT -> SOC dictionary; the organ of
each quoted term comes from the record's own SOC through `conf/ontology/axes.yaml`.

## PMC Open Access

The extraction pipeline is structurally confined to the OA subset: `efetch` refuses full
text for non-OA articles ("The publisher of this article does not allow downloading of
the full text in XML form"), so there is no path by which the automated route touches
licensed full text.

Within the OA subset the licence still varies per article, and the per-row `license_code`
is recorded so the posture can be applied row by row. Measured across the 1,471 articles
actually fetched, rather than estimated:

| licence | articles |
|---|---|
| CC BY | 663 |
| CC BY-NC-ND | 526 |
| CC BY-NC | 251 |
| CC BY-NC-SA | 12 |
| TDM | 3 |
| CC BY-ND | 2 |
| CC0 | 1 |
| not stated | 13 |

So 45% is CC BY -- the plan estimated 39% -- and **55% carries an NC or ND restriction**,
which is why this is not a corner case.

* **extracted numbers** -- published for every row. A measured incidence is a fact, not
  a copyrightable expression.
* **verbatim table and caption text** -- not published, for any article. The licence would
  permit it for the CC BY 45%, and the rule is stricter on purpose. Curating 16 agents from
  the primary literature put quoted sentences from 18 papers into `conf/adc_registry.yaml`,
  and 14 of those papers turned out to be CC BY-NC-ND or CC BY-NC. A policy of the form
  "quote CC BY freely, never quote NC-ND" requires whoever edits that hand-maintained file
  next to look up a licence first, and a policy that depends on remembering an exception is
  one that breaks. Every citation is now a paraphrase with the PMCID kept, which costs
  nothing: the design facts are facts and survive it.
  `tests/test_licence_posture.py` fails on any quotation longer than 24 characters, which
  admits a term of art and excludes a reproduced sentence.

Three snapshots were fetched, kept separate because each answered a different question and
each is reproducible only with its own agent list. They overlap: **1,496 files for 1,471
distinct articles**, because 25 papers answer to more than one of the three agent lists. A
plain `cat` of the per-snapshot cell files therefore emitted 277 rows twice, and
`scripts/merge_cell_files.py` now deduplicates and prints what it dropped -- a growing
overlap is a signal about the fetch lists and a silent deduplication would hide it.

The corpus itself was never affected, because the merge keys observations by (arm, axis,
kind) and a duplicate collapses. The statistics computed per cell were: `pmc_validation.json`
reported 6,535 paper cells and sized its rate comparison at 1,372 when fewer were distinct.
And 149 of the 277 were not duplicates at all -- same article, table, row, parent column
header, agent and axis, with *different counts* -- which is what a grade-stratified table
looks like once the grade is dropped from the column identity, and is how the outcome
mismatch in section 9's results 27 and 30 was found.

| snapshot | how the agents were found | articles |
|---|---|---|
| `pmc/<date>` | the 18 registry agents, by INN | 1,319 |
| `pmc/<date>-discovery` | 23 INNs from the payload-linker stem sweep (`conf/discovered_agents.txt`) | 144 |
| `pmc/<date>-codename` | 10 agents an INN-only search missed, by code name (`conf/codename_agents.txt`) | 26 |
| `pmc/<date>-discovery2` | the 5 payload-linker stems whose first sweep hit the fetch cap | 7 |

The fourth row contributes **nothing**, and that is its result rather than an oversight. Its
7 articles hold 12 tables, 4 of them adverse-event tables, and **0 parseable rate cells**:
between them the five agents have no count with a denominator anywhere. The extraction
pipeline has no target for this snapshot for that reason, `artifacts/discovery2_yield.json`
records the measurement, and section 5g's conclusion that the ceiling is 32 agents rather
than the planned 54 rests on it. The four rows sum to the 1,496 files on disk; the 25
articles that answer to more than one agent list are what make that 1,471 distinct.

The code names were harvested only from papers whose *titles* already named the INN, which
makes the paper itself the evidence for the mapping. That matters because a wrong code name
misattributes every row of an agent, and loose detection was measured at a 75%
false-positive rate.

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

**Human Protein Atlas** is still not ingested. Per-organ target expression now comes from
GTEx and Tabula Sapiens through Open Targets, which serves both under one field; HPA adds
immunohistochemistry that would be closer to what an antibody binds, and is the obvious
next addition rather than a gap in what is claimed.

Two sources rather than one, because neither covers the 14 axes alone: GTEx has no eye and
no ear, Tabula Sapiens has no brain. Their units are not comparable -- TPM against
CPM-pseudobulk, with mass-spectrometry PPB also on offer -- so values are never pooled.
Each source is ranked within a target across axes and only the ranks combine.

The aorta objection that made the project plan abandon this constraint does not bite at
axis granularity: GTEx puts `ERBB2` at 86.6 TPM in aorta, but aorta and cardiomyocyte are
both `cardiovascular`, so the axis answer is the same either way. The cell-resolved data
settles which it is -- cardiac myocytes at 112.0 and 103.6 against aortic smooth muscle at
54.7 -- which is why cell types are carried as the evidence behind a flag rather than as
the score.

**MONDO** is used for the hand-pinned `mondo_id` column in the comorbidity registry,
which was curated against it; the ontology is not loaded at runtime. **SIDER** is cited
for the negative result that chemistry-to-organ transfer cannot be learned from it, and
is not read by any code path.
