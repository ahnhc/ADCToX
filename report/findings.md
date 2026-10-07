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

## Results, verified after the fix

All five evaluations were re-run on the corrected model. **The model does not beat a
base-rate baseline on any of them.** Deltas are paired against the strongest baseline for
that split, because the model's own interval excluding zero would only say the target
ordering is not random.

| evaluation | model | best baseline | delta | 95% CI | |
|---|---|---|---|---|---|
| within-arm ranking, leave-one-agent-out (16) | 0.827 | 0.844 | -0.012 | [-0.031, +0.005] | includes 0 |
| within-arm ranking, leave-one-mechanism-out (2) | 0.854 | 0.871 | **-0.018** | [-0.027, -0.009] | excludes 0, negative |
| within-arm ranking, leave-one-family-out (4) | 0.770 | 0.853 | **-0.080** | [-0.124, -0.035] | excludes 0, negative |
| across-agent per-axis Spearman | +0.054 | +0.026 | — | [-0.115, +0.218] | includes 0; threshold was +0.3 |
| dose-modification ordering agreement | +0.188 | +0.153 | +0.035 | [-0.001, +0.069] | includes 0 |

The best within-arm predictor of the three is the global axis mean, which carries no
design information at all.

The dose-modification comparison was the one favourable result before the fix
(+0.039 [+0.003, +0.073]) and lost its significance after it (+0.035 [-0.001, +0.069]).
It also carries its own refutation in the same output: top-organ agreement is 1 of 13
against 0.93 expected by chance, and the model names gastrointestinal as the most-affected
axis for 9 of 13 drugs, which is the axis base rate rather than a per-drug judgement.

### The withdrawal was precautionary, and the re-run upheld the main result

A non-identifiability was found after the first round (see below) and every number was
withdrawn rather than annotated. The re-run then reproduced the within-arm results almost
exactly -- leave-one-mechanism-out moved from -0.016 to -0.018, leave-one-family-out from
-0.069 to -0.080 -- because the bug's severity scaled inversely with corpus size: on the
full 285-arm corpus `tau_cleav` was 0.299 before the fix and 0.273 after, while on a
153-arm subset it had run to 3.872.

So the withdrawal cost nothing and settled something. It also identified where the bug
*did* matter: the label-change analysis fits on pre-date subsets, which are exactly the
small corpora where the degeneracy was severe, and those predictions were unusable.

### The gate was unfireable, independently of all of this

The protocol said "macro AUC below 0.65 triggers the cut order". The model scores 0.827
and passes -- but a constant global-axis-mean predictor scores 0.844 on the same metric.
**A gate a design-blind constant clears is not a gate.** This is a property of the metric,
not of the model or the bug, and the lesson generalizes: an absolute threshold on a
base-rate-dominated metric cannot detect the failure it was written for. Replaced by the
paired delta, which the model fails.

### Why the within-arm metric cannot settle it alone

That task ranks 14 axes *inside one arm*, and axis base rates are consistent enough across
arms that one fixed ordering is near-optimal everywhere. A model that knows those base
rates and then perturbs them with design effects has little to gain and much to lose. The
across-agent comparison is the one that can show design signal, since a constant predictor
has no discriminative power there by construction -- and it comes back at +0.054 with an
interval spanning zero, against a threshold of +0.3 declared before the run.

Per-axis, that mean hides the structure that matters. Neurologic (+0.61), musculoskeletal
(+0.51) and gastrointestinal (+0.49) correlate positively; renal (-0.57), otologic (-0.37)
and pulmonary (-0.27) anti-correlate, and they cancel. Renal and otologic are the two
sparsest axes, so noise accounts for them. Pulmonary has 5,009 rows and does not, and the
likely cause is ascertainment: a trial that mandates chest imaging reports far more
pulmonary events than one recording symptoms, which dominates any across-agent comparison
on an axis that needs active surveillance to be seen at all.

### 3.1 The bug
### 3.1 The bug

On a 153-arm corpus the model predicted the otologic axis at 0.9997 against an observed
rate of 0.04. Two coupled degeneracies: the random intercepts were not constrained to sum
to zero, so they could carry a common offset collinear with the axis intercept; and
cleavability entered as a raw indicator which, being nearly constant across 16 agents,
acted as a second per-axis intercept. In sample both are harmless. Out of sample they are
not, because predicting a design with no trial and no agent drops the random effects and
inherits an intercept nothing compensates for.

| | before | after |
|---|---|---|
| `tau_cleav` | 3.872 (eight times its prior scale) | 0.391 |
| `tau_mech` | 0.157 | **0.531** |
| max predicted rate | 1.0000 | 0.3930 |

After the fix, predictions track the observed per-axis rates across all fourteen axes.

### 3.2 The gate was unfireable, independently of the bug

The protocol said "macro AUC below 0.65 triggers the cut order". A constant
global-axis-mean predictor scores about 0.84 on that metric. **A gate that a design-blind
constant clears is not a gate**, and this holds whatever the re-run shows: it is a property
of the metric, not of the model. The failure mode is general -- an absolute threshold on a
base-rate-dominated metric cannot detect the failure it was written for. Replaced by the
paired delta against the strongest baseline.

### 3.3 What the within-arm metric can establish

It ranks 14 axes inside one arm, and axis base rates are consistent enough across arms
that one fixed ordering is near-optimal. A model that knows those base rates and perturbs
them has little to gain there. So that metric alone cannot show the design terms carry no
signal; the across-agent comparison can, and both are reported together.

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

### 4.2 The two levels fail in opposite directions, which closes the question

Put the two results together and the corpus has answered:

* **Mechanism is identifiable but too coarse.** It converges (worst seed gap 0.239) and
  its interaction is supported (tau_mech 0.592 [0.503, 0.711]), yet holding out a payload
  family costs 0.069 AUC against the baseline, because families inside one mechanism do
  not behave alike.
* **Family would capture that but is not identifiable.** Both parameterizations fail to
  converge, additive for an obvious reason and nested despite being the correct fix.

There is no resolution in between. Mechanism is the finest level this data can estimate
and it is coarser than the phenomenon.

### 4.3 And more data would not reach it

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

## 5b. Is the censoring treatment recovering signal or creating it?

This is the project's most consequential modelling choice, so it is tested rather than
asserted. Three fits of the same model: the censored likelihood; the same cells with
censored entries imputed as zeros; and the 42-arm subset of studies that report completely,
where no censoring model is needed at all.

| treatment | `b_thresh` |
|---|---|
| censored | +0.0331 [+0.0277, +0.0383] |
| zero-imputed | +0.0183 [+0.0136, +0.0231] |
| completely-reported subset only | +0.0417 [-0.7572, +0.8010] |

**The direction was predicted wrongly and the measurement corrected it.** We expected
zero-imputation to inflate the threshold coefficient, with the correction absorbing an
artefact. It shrinks it, and the mechanism is clear in hindsight: imputed zeros land in
exactly the high-threshold trials, dragging their fitted rates down and the coefficient
with them.

That also overturns an earlier claim of ours. We had written that `b_thresh` including zero
was evidence the censoring was working; it is the opposite. A trial reporting only above
5% shows you its high-rate terms, so its *observed* cells are systematically higher. The
censored likelihood accounts for the cells that are missing; this coefficient absorbs the
selection on the cells that are present. A non-zero value is expected and necessary.

**The check that actually decides it is the profile comparison, and it passes.** Censored
full corpus against completely-reported subset, per mechanism: calicheamicin +0.829,
topoisomerase-I +0.785, tubulin +0.662. The two corpora agree on which organ each payload
mechanism hits, so the treatment recovers signal that survives in data that never needed
correcting. Had they disagreed, the project would have been resting on its own correction.

The completely-reported subset is small enough that its own coefficient interval spans
[-0.76, +0.80], which is why agreement is assessed on the profiles rather than on
coefficients.

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
