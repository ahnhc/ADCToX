# ADCTox: what the public data supports

Working draft. Every number is measured and regenerable by `make all`; none is typed by
hand. Figures and tables are produced from `artifacts/*.json`.

## 1. What was built

A system that takes a comorbidity profile and a target antigen and returns proposed ADC
designs with per-organ-system toxicity estimates. Research prototype; not a clinical tool.

The gap it addresses: existing ADC machine-learning work (ADCNet, DumplingGNN, Linker-GPT)
predicts efficacy, cytotoxicity, DAR and linker stability. Nothing predicts organ-level
*clinical* toxicity conditioned on a patient's existing organ damage.

## 2. The corpus, and the number that governs everything

| | count |
|---|---|
| ClinicalTrials.gov studies with an adverse-event module | 593 |
| AE event rows | 67,609 |
| event groups | 2,201 |
| attributable to one ADC, n>=30, conventional ADC | **285 arms** |
| (arm x axis) cells, 91% fill | **3,990** |
| distinct agents | **16** |
| **cells that identify a design coefficient** | **224** |

The last row is the one that matters. Design features -- payload mechanism, linker,
cleavability, DAR, isotype, target -- are **agent-level constants**. Trastuzumab
emtansine's 48 arms are 48 observations of its trial populations and *one* observation of
DM1 chemistry. So the data identifying a design coefficient is `agents x axes = 224`, not
3,990. An earlier draft of this project proposed a 420-parameter design matrix, which is
0.57 observations per parameter: fewer data points than parameters.

## 3. The forward model does not beat its baseline

Pre-specified metric: AUROC for "this axis is among the arm's observed top three".

| split | model | mechanism-mean | **global axis mean** | delta | 95% CI |
|---|---|---|---|---|---|
| leave-one-agent-out (16 folds) | 0.825 | 0.839 | **0.844** | -0.014 | [-0.033, +0.004] |
| leave-one-mechanism-out (2 folds) | 0.856 | 0.871 | **0.871** | -0.016 | [-0.025, -0.006] |

The best of the three predictors is the global axis mean, which carries no design
information at all.

### 3.1 The gate we set could not fire

The protocol said "macro AUC below 0.65 triggers the cut order". The model scores 0.825
and passes -- but a constant global-axis-mean predictor scores 0.844 on the same metric.
**A gate that a design-blind constant clears is not a gate.** This was an error in the
protocol, not in the fitting, and it is worth stating because the failure mode is general:
an absolute threshold on a metric dominated by base rates cannot detect the failure it was
written to detect.

### 3.2 Why that metric cannot separate the model from the base rate

The task ranks 14 axes *inside one arm*. Axis base rates are consistent enough across
arms that a single fixed ordering is close to optimal everywhere. The model knows those
base rates too, then perturbs them with design effects that are small relative to the
between-axis spread. Perturbing a near-optimal ordering can only lose.

The negative result is therefore real but narrow: design terms do not improve within-arm
axis ranking. It does not establish that they carry no signal, which is a different
comparison -- across agents, within an axis -- and is reported separately.

## 4. Where it fails is the most informative result

| held-out agent | delta | signature | family status |
|---|---|---|---|
| trastuzumab emtansine | **-0.115** | thrombocytopenia, ocular, hepatic | only DM1 agent |
| belantamab mafodotin | -0.064 | keratopathy | only MMAF agent |
| mirvetuximab soravtansine | -0.050 | ocular | only DM4 agent |
| polatuzumab vedotin | -0.040 | — | one of four MMAE agents |

Every large miss is an agent that is the sole representative of its payload *family*
inside a broader mechanism class. Held out, it is predicted from chemistry that behaves
differently: T-DM1's platelet and ocular profile from MMAE's neuropathy.

### 4.1 The obvious fix is not identifiable, in either form

| model | worst standardized seed gap | outcome |
|---|---|---|
| mechanism only | 0.239 | converged |
| + payload family, additive | **0.686** | tau_mech fell 0.592 -> 0.436 as tau_family took 0.396; LOMO delta worsened to -0.022 |
| + payload family, nested | **0.577** | tau_mech 0.453 / tau_family 0.391 |

Additive fails for a clear reason: family determines mechanism, so two independent terms
compete for one variance. Nesting is the textbook correction and did not rescue it --
with 7 families across 5 mechanisms and 16 agents there is not enough information to
separate between-mechanism from within-mechanism spread, whatever the parameterization.

### 4.2 And more data would not reach it

Measured across corpus sizes, the payload *identity* vocabulary grows as fast as the
corpus:

| corpus | agents | identifying cells | payload classes | design params | cells per param |
|---|---|---|---|---|---|
| registry only | 17 | 238 | 9 | 112 | 2.12 |
| + INN-named literature | 32 | 448 | **12** | 154 | 2.91 |
| + code-named literature | 54 | 756 | **20** | 266 | **2.84** |

Tripling the corpus leaves the ratio flat, because each new agent brings a new payload.
**The resolution that would improve prediction recedes as fast as it is approached.** This
is the project's central structural finding, and it showed up three times independently:
in the parameter counting, in the per-fold failure pattern, and in the identification
failure of both family parameterizations.

## 5. What the model does support

`tau_mech` 0.592 [0.503, 0.711] -- the mechanism x axis interaction is supported by the
data rather than asserted by a parameter count.
`sigma_agent` 0.121 [0.076, 0.189] -- small, so the design slots account for much of the
between-agent variation.
`b_combo` +0.202 [+0.171, +0.233] -- combination arms do report higher rates.
`b_log_n` +0.030 [+0.020, +0.041] -- larger arms report higher rates, an ascertainment
effect that would have been attributed to the design had it not been controlled.
`b_dar` +0.038 [-0.004, +0.080] -- includes zero. DAR is an agent-level constant and is
confounded with agent identity here. The pharmacokinetic literature supports a DAR effect;
this corpus does not resolve one.

Qualitatively the corpus is sound. Baseline-centered mechanism fingerprints reproduce the
boxed warnings unprompted: calicheamicin tops hepatic at +0.70 (veno-occlusive disease),
topoisomerase-I payloads top pulmonary and gastrointestinal, tubulin payloads place
neurologic in their top three.

## 6. The exclusion-criteria signal

1,281 ADC trials against 2,481 oncology controls, all with eligibility text. Enrichment
over the control base rate, exclusion-polarity statements only:

| payload mechanism | n | pulmonary | neurologic | ocular | hepatic |
|---|---|---|---|---|---|
| base rate (oncology) | 2,481 | 22.7% | 11.5% | 1.7% | 10.8% |
| tubulin | 664 | 1.6x | **8.0x** | **17.8x** | 1.9x |
| topo1 | 406 | **5.8x** | 1.0x | 14.3x | 0.8x |
| enediyne (calicheamicin) | 180 | 0.4x | 0.5x | 0.2x | **3.8x** |
| duocarmycin | 7 | 7.5x | 0.5x | 13.6x | 1.9x |

Polarity separation is essential and was not obvious. Pooling inclusion lab floors with
explicit exclusions hides the signal: the hepatic base rate falls from 64.2% to 10.8% once
bilirubin and transaminase floors are removed, and only then does the calicheamicin
veno-occlusive signal appear at all.

The boilerplate diagnostic names the organs that carry no information: cardiovascular and
infectious/immune vary only 1.8x across mechanisms, because every oncology protocol has an
LVEF floor and a hepatitis-B exclusion. Ocular varies 109x and is the most discriminative.

**This is consistency, not anticipation.** For almost every agent the warning this
recovers was already in the label at approval. Conflating the two would be the easiest way
to overstate this project.

## 7. The one anticipatory target

openFDA does not serve label history. DailyMed does, so 183 label versions across 14 ADCs
were diffed on section-5 headings and boxed-warning headlines.

**7 dated organ-axis additions across 4 agents**, plus 3 escalations into a boxed warning.
Power was fixed before any result: with 14 axes the null P(top three) is 0.214, so 4 of 7
gives p = 0.042. With 4 of the 7 events from brentuximab vedotin alone, the effective
number of independent drugs is 4 and a leave-brentuximab-out sensitivity is mandatory.
**This is a case series with a permutation test, not a validation study.**

Three corrections cut an initial 12 events to 7: gemtuzumab ozogamicin's label history
spans a 2010 withdrawal and 2017 re-approval, so a diff across that boundary compares
different regulatory submissions; granularity is the axis rather than the heading, so a
second warning on an already-flagged organ is not a prediction target; and three regex
patterns were hiding real events, found by reading the unmapped-heading list that the
pipeline reports rather than discards.

## 8. Dose-modification ordering

All 14 labels retrieved, 45 dose-modification tables, 176 parsed entries, 78 orderable
axis pairs -- an ordinal outcome with an order of magnitude more comparisons than the
label-change analysis offers.

The first scale did not discriminate: approved labels say to discontinue for the severe
grade of nearly every reaction, so "strongest action" put almost every axis at the top.
The discriminating quantity is **at what grade the label starts to act** -- withholding at
grade 1 expresses more fear than withholding at grade 3. With that, the ordering comes out
clinically sensible without being told: trastuzumab deruxtecan tops pulmonary (4.8, its
ILD boxed warning), enfortumab vedotin tops dermatologic (SJS/TEN), sacituzumab govitecan
tops gastrointestinal, gemtuzumab and inotuzumab top hepatic (VOD), brentuximab tops
neurologic.

## 9. Measured negative results

1. **Free-drug transfer does not work.** Baseline-centered matched-versus-mismatched gap
   -0.001. ADC payloads are derivatives of drugs with human exposure history, but a free
   drug's organ profile does not predict its conjugate's, because free-drug arms carry
   indication and co-medication rather than drug pharmacology -- vincristine's centered
   signature is immune and infectious, not neuropathy, because it is never given alone.
2. **A raw-profile correlation of +0.75 is achieved by the global mean alone.** Signal
   exists only in the baseline-centered residual.
3. **SIDER cannot train a chemistry-to-organ model.** Drugs average 10.5 of 14 axes
   positive and 22% are positive on all 14, so binary presence measures package-insert
   verbosity. The frequency subset leaves 836 drugs of which 72 are antineoplastic, and
   9 of 11 ADC payload classes have no chemical relative in it at all.
4. **A scaffold-ablation test we had planned as the headline is not diagnostic.** A
   constant predictor scores Spearman 0.66-0.78 against the topoisomerase-I drugs on the
   stated pass criterion, so the test would have produced a convincing-looking "yes"
   meaning nothing. It was not run, and the reason is reported.
5. **Design features are agent-level constants**, so 3,990 cells carry 224 cells' worth of
   design information. A sample-size illusion.
6. **Payload-class interactions are unreachable at any corpus size** (section 4.2).
7. **Fc silencing is not a design lever.** Three primary papers contradict each other on
   the mechanism, no approved ADC uses it, and no training arm carries it. It is not
   offered as a design slot.
8. **Membrane permeability runs the wrong way for ocular toxicity.** MMAF is the least
   permeable auristatin and has the worst keratopathy; the mechanism is corneal
   macropinocytosis, not diffusion.
9. **Gene-set overlap does not beat a disease ontology.** Jaccard over Open Targets gene
   sets predicts same-organ pairs at AUC 0.748, a task MONDO's `is_a` closure answers
   exactly and for free.

## 10. Limitations

* Tier 2 novelty -- a new molecule in a known chemical family -- is not supported, and the
  system refuses to give a point estimate outside Tier 1.
* No efficacy model. The one public ADC activity dataset (435 rows) is beaten by a
  decision tree on SMILES string length and DAR under a leakage-free grouped split.
* The comorbidity layer has zero training rows and is an elicited prior throughout,
  labelled `elicited_prior` in every API response.
* Two of six payload mechanisms can serve as a held-out fold. Calicheamicin ADCs number
  two worldwide, immunotoxins one, photoimmunotherapy one; these do not improve with
  corpus size.
