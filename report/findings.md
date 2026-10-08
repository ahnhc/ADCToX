# ADCTox: what the public data supports

Working draft. Every number here is measured, and `make all` regenerates all of it from
`artifacts/*.json`.

Stated precisely, because the looser version of this claim was false for most of the
project's life. The tables are generated from artefacts between markers in this file, so
they cannot drift. Figures quoted in prose are checked by `make check-report`, which fails
on any decimal it cannot find in an artefact; 16 are allowlisted with a stated reason
each, and superseded figures quoted in before/after comparisons live in
`artifacts/superseded/`. That guard was itself a no-op until recently -- it passed 99% of
randomly fabricated four-decimal figures -- so it now measures and prints its own
false-pass rate on every run. At three decimals it is still weak, which is why figures are
quoted to four where traceability is the point.

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

## 3. Results, after two rounds of correction

Two rounds of correction, in order: a centering bug in the random intercepts, which
invalidated a first round of evaluation entirely; and two bugs in the cross-validation
fold construction, which were leaking a trial into two splits while discarding half the
training arms from a third. Everything below is from after both.

**The model does not beat a base-rate baseline on any of these.** On the three
within-arm splits the deficit now excludes zero, which it did not on leave-one-agent-out
before the folds were fixed -- correcting them made the verdict stronger rather than
weaker, and the subsection "The folds themselves were wrong" below explains why that is
the correct direction.

Deltas are paired against the strongest baseline for that split, because the model's own
interval excluding zero would only say the target ordering is not random. Each delta is
the mean over folds of (fold AUC minus that fold's better baseline), which is the
quantity the interval is computed on; the other aggregation, a difference of macro
averages, is in the artefact and differs where the winning baseline varies by fold.

<!-- generated: results-table -->

| evaluation | model | best baseline | delta | 95% CI | |
|---|---|---|---|---|---|
| within-arm ranking, leave-one-agent-out (16) | 0.8036 | 0.8458 | **-0.0422** | [-0.0650, -0.0221] | excludes 0 |
| within-arm ranking, leave-one-mechanism-out (2) | 0.8523 | 0.8715 | **-0.0191** | [-0.0287, -0.0096] | excludes 0 |
| within-arm ranking, leave-one-family-out (4) | 0.7725 | 0.8525 | **-0.0783** | [-0.1223, -0.0317] | excludes 0 |
| across-agent per-axis Spearman | +0.0966 | +0.0263 | -- | [-0.0639, +0.2632] | includes 0 |
| dose-modification ordering (13) | +0.1797 | +0.1672 | +0.0125 | [-0.0264, +0.0511] | includes 0 |

<!-- /generated: results-table -->

The best within-arm predictor of the three is the global axis mean, which carries no
design information at all.

### The folds themselves were wrong, and fixing them made the verdict stronger

One line in `splits.py` carried two bugs that pulled these numbers in opposite directions,
while the module's own docstring asserted the behaviour only one of the three splits
implemented.

*Leakage.* The family and mechanism splits dropped held-out arms but not held-out trials.
NCT03529110 is a T-DXd vs T-DM1 head-to-head -- named in that docstring as the reason whole
trials have to go -- and it leaked in both: holding out one agent left its comparator arm
from the same trial in training, so the held-out arm inherited a trial-level random
intercept fitted from its own comparator. Counting only the 157 arms that carry a trial
effect, leave-one-agent-out leaked 0 trials and the other two leaked 2 each, all of them
that trial.

*Discarding.* Leave-one-agent-out masked on the raw trial index, and arms from single-arm
trials were collapsed onto a shared sentinel index. So holding out any agent with a
single-arm trial matched the sentinel and dropped all 128 of those arms -- belonging to
unrelated agents, whose only shared property is carrying no trial effect. Folds trained on
roughly half the arms they should have: 125 of 285 for T-DM1 against 236 after the fix,
1,980 arm-folds discarded across the sixteen folds.

What the correction did:

| evaluation | before | after |
|---|---|---|
| leave-one-agent-out | -0.0120 [-0.0307, +0.0052], **includes 0** | -0.0422 [-0.0650, -0.0221], **excludes 0** |
| leave-one-mechanism-out | -0.0177 [-0.0265, -0.0090] | -0.0191 [-0.0287, -0.0096] |
| leave-one-family-out | -0.0805 [-0.1240, -0.0345] | -0.0783 [-0.1223, -0.0317] |
| across-agent Spearman | +0.0538 [-0.1149, +0.2177] | +0.0966 [-0.0639, +0.2632] |

**The headline conclusion got stronger, not weaker.** Leave-one-agent-out was the one split
where the deficit could not be distinguished from zero, and the model card said so. With
correct folds it excludes zero, so the model now loses to a base-rate baseline on all three
splits rather than two. Trastuzumab emtansine -- the agent on the far side of the leaking
head-to-head -- moves from a -0.025 fold delta to -0.156, which is the leak made visible.

The across-agent rank correlation moved the other way, nearly doubling to +0.0966, still
with an interval spanning zero. Both directions are consistent with one mechanism: the
extra training data helps a base-rate baseline, which converges quickly, more than it helps
a 184-parameter model, so the within-arm deficit widens; while the model's ability to order
*agents* within an axis -- which needs agents, not cells -- improves.

That last paragraph was an interpretation, and the controlled comparison that settles it
has since been run: patritumab deruxtecan held out, fitted twice with everything identical
except the split construction.

| | train arms | predicted mean | observed | MAE | `b_thresh` |
|---|---|---|---|---|---|
| old split | 150 | 0.1872 | 0.2120 | 0.0701 | **-0.1057** |
| corrected split | 277 | 0.3191 | 0.2120 | 0.1252 | **+0.0345** |
| full corpus (reference) | 285 | — | — | — | **+0.0327** |

**The old fold estimated the threshold coefficient at the wrong sign.** On a training set
cut to 150 arms it came out at -0.1057 where the full corpus gives +0.0327; the corrected
fold recovers +0.0345. So the broken fold's better MAE was a badly biased nuisance
coefficient landing near the held-out truth by coincidence, not a better model. That is
why the correction makes the numbers worse and is still the right correction.

It also exposes something the broken folds were hiding: the corrected fold *over-predicts*
this agent, 0.3191 against an observed 0.2120. Absolute calibration on held-out agents is
poor, and the earlier folds were too mutilated to show it. One fold, one seed, reported as
such.

The dose-modification comparison was the one favourable result before the centering fix
(+0.039 [+0.003, +0.073]), lost its significance after it (+0.035 [-0.001, +0.069]), and
weakened again once the cross-validation folds were corrected, to
+0.0125 [-0.0264, +0.0511]. That third move is not a separate finding: this
comparison is computed from held-out fold predictions, so fixing the folds necessarily
moved it. The informative part is the direction -- the model fell from +0.1882 to
+0.1797 while its baseline rose from +0.1533 to +0.1672, which is the pattern the
controlled fold experiment above accounts for.

It also carries its own refutation in the same output: top-organ agreement is 1/13
against 0.93 expected by chance, and the model names gastrointestinal as the most-affected axis for
8 of 13 drugs, which is the axis base rate rather than a per-drug judgement.

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

The protocol said "macro AUC below 0.65 triggers the cut order". The model scores
0.8036 and passes -- but a constant global-axis-mean predictor scores 0.8437 on
the same metric.
**A gate a design-blind constant clears is not a gate.** This is a property of the metric,
not of the model or the bug, and the lesson generalizes: an absolute threshold on a
base-rate-dominated metric cannot detect the failure it was written for. Replaced by the
paired delta, which the model fails.

### Why the within-arm metric cannot settle it alone

That task ranks 14 axes *inside one arm*, and axis base rates are consistent enough across
arms that one fixed ordering is near-optimal everywhere. A model that knows those base
rates and then perturbs them with design effects has little to gain and much to lose. The
across-agent comparison is the one that can show design signal, since a constant predictor
has no discriminative power there by construction -- and it comes back at +0.0966
[-0.0639, +0.2632], an interval spanning zero, against a threshold of +0.3 declared
before the run.

Per-axis, that mean hides the structure that matters. Neurologic (+0.61), musculoskeletal
(+0.51) and gastrointestinal (+0.49) correlate positively; renal (-0.57), otologic (-0.37)
and pulmonary (-0.27) anti-correlate, and they cancel. Renal and otologic are the two
sparsest axes, so noise accounts for them. Pulmonary has 5,009 rows and does not, and the
likely cause is ascertainment: a trial that mandates chest imaging reports far more
pulmonary events than one recording symptoms, which dominates any across-agent comparison
on an axis that needs active surveillance to be seen at all.

### The centering bug, in detail

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

## 4. Where it fails is the most informative result

The four worst leave-one-agent-out folds, with the two structural features that might
explain them:

<!-- generated: fold-difficulty -->

| fold | delta vs baseline | same-payload siblings | family share of mechanism | sole of family |
|---|---|---|---|---|
| trastuzumab emtansine | **-0.1565** | 0 | 0.29 | no |
| mirvetuximab soravtansine | **-0.1058** | 0 | 0.29 | no |
| belantamab mafodotin | **-0.0981** | 0 | 0.71 | no |
| gemtuzumab ozogamicin | **-0.0697** | 1 | 1.00 | no |

Sole-of-family agents among the four worst folds: 0/4. Mean delta -0.0485 for the 3 sole-of-family agents against -0.0408 for the 13 that share one -- no separation. Rank correlation of fold delta with same-payload siblings +0.771, with family share of its mechanism +0.694.
<!-- /generated: fold-difficulty -->

An earlier version of this section led with the pre-fix figures and read them as showing
that every large miss is an agent which is the sole representative of its payload
*family*. That reading did not survive the split-corrected re-run, and it was
load-bearing: it is the stated reason the project tried a payload-family level at all.
What tracks fold difficulty is how many agents share the held-out agent's **payload**.
`scripts/fold_difficulty.py` computes it.

The mechanism behind it is unchanged and the conclusion is sharper. Held out, an agent is
predicted from chemistry that behaves differently -- T-DM1's platelet and ocular profile
from MMAE's neuropathy -- and the level that would fix that is payload, which is the one
level whose vocabulary grows as fast as the corpus. Family at least stops growing, which is
why it was the one worth trying.

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
  its interaction is supported (`tau_mech` well clear of zero; the interval is in §5,
  quoted once there so a refit cannot leave two copies disagreeing), yet holding out a payload
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

The first row counts the 17 agents in the registry with usable arms. The fitted model uses
**16 and 224 cells**, because one of the 17 is an immunotoxin -- an antibody-toxin fusion
with no linker and no conjugation chemistry -- and the design matrix has no slots to
describe it. Both numbers appear in this report and they count different populations: 17
is what the registry holds, 16 is what the model can represent.

Tripling the corpus leaves the ratio flat, because each new agent brings a new payload.
**The resolution that would improve prediction recedes as fast as it is approached.** This
is the project's central structural finding, and it showed up three times independently:
in the parameter counting, in the per-fold failure pattern, and in the identification
failure of both family parameterizations.

## 5. What the model does support

<!-- generated: fitted-parameters -->
`tau_cleav` 0.2824 [0.1976, 0.4103] -- the scale of the cleavable-versus-non-cleavable linker contrast across axes. Clear of zero, and about half the size of the mechanism scale -- so linker cleavability shifts the organ profile, and shifts it less than the payload mechanism does. This is the one design axis the corpus identifies comfortably: cleavability is binary and needs only 8 agents to estimate, against the 40 a mechanism level needs and the 80 a payload level would.

`tau_mech` 0.5928 [0.4928, 0.7008] -- the mechanism x axis interaction is supported by the data rather than asserted by a parameter count.

`sigma_agent` 0.1590 [0.0980, 0.2402] -- small, so the design slots account for much of the between-agent variation.

`b_combo` +0.1950 [+0.1691, +0.2213] -- combination arms do report higher rates.

`b_log_n` +0.0393 [+0.0288, +0.0491] -- an ascertainment effect that would have been attributed to the design had it not been controlled.

`b_dar` +0.0319 [-0.0175, +0.0840] -- includes zero. DAR is an agent-level constant and is confounded with agent identity here. The pharmacokinetic literature supports a DAR effect; this corpus does not resolve one.

`b_thresh` +0.0327 [+0.0272, +0.0375] -- the reporting-threshold covariate. Not the censoring correction: it is four times larger on the seriousEvents table, which has no censored cells at all, so it is substantially absorbing trial-level reporting practice.

Convergence stands in for R-hat: the model is refit under a second seed and posterior means compared. The worst standardized gap is 0.1376 pooled standard deviations, on `b_thresh`, against a threshold of 0.3 -- acceptable.
<!-- /generated: fitted-parameters -->

Qualitatively the corpus is sound. Baseline-centered mechanism fingerprints reproduce the
boxed warnings unprompted: calicheamicin tops hepatic at +0.70 (veno-occlusive disease),
topoisomerase-I payloads top pulmonary and gastrointestinal, tubulin payloads place
neurologic in their top three.

## 5b. Is the censoring treatment recovering signal or creating it?

This is the project's most consequential modelling choice, so it is tested rather than
asserted. Three fits of the same model: the censored likelihood; the same cells with
censored entries imputed as zeros; and the 42-arm subset of studies that report completely,
where no censoring model is needed at all.

<!-- generated: censoring-sensitivity -->

| treatment | `b_thresh` |
|---|---|
| censored | +0.0331 [+0.0284, +0.0381] |
| zero-imputed | +0.0184 [+0.0130, +0.0233] |
| completely-reported subset only | +0.0015 [-0.7075, +0.7347] |

Agreement on the mechanism organ profiles, censored full corpus against the completely-reported subset: calicheamicin +0.8462, topoisomerase-I +0.8198, tubulin +0.6659 (sorted, so the binding figure is the last at +0.6659). The two corpora agree on which organ each payload mechanism hits, so the censoring treatment recovers signal that survives in data which never needed correcting. Had they disagreed, the project would have been resting on its own correction.

The completely-reported subset is only 42 arms, so its own interval for this coefficient spans [-0.7075, +0.7347] -- which is why agreement between the corpora is assessed on the mechanism profiles rather than on coefficients.
<!-- /generated: censoring-sensitivity -->

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
full corpus against completely-reported subset. The per-mechanism figures are in the
generated block above.

### A free negative control, and a second correction to the same coefficient

The `seriousEvents` table carries **no censoring at all** -- every missing cell there is a
genuine zero, 0 of 3,990 cells are censored. So a censoring adjustment fitted on that
table should be zero. It is not:

| table | censored cells | `b_thresh` |
|---|---|---|
| otherEvents | 471 of 3,990 | +0.033 [+0.028, +0.039] |
| seriousEvents | **0** of 3,990 | **+0.131 [+0.113, +0.147]** |

The coefficient is four times *larger* where there is nothing to correct. So the reporting
threshold is substantially a **trial-level descriptor** -- trials that set a high
threshold differ in era, phase and sponsor reporting practice -- and only partly a
truncation correction. It must stay in the model, as a confounder control, and it must not
be described as the censoring correction. This is the second time this one coefficient's
interpretation needed fixing; both corrections came from a measurement we had not thought
to make.

## 5c. The two event tables rank organs differently, and that is a product finding

`otherEvents` and `seriousEvents` are not two views of one outcome. One asks whether this
chemistry irritates an organ, the other whether it damages it. A grade-1 cough and fatal
interstitial lung disease are both pulmonary and are not the same event. Across the five
shared mechanisms the two fits agree on organ ranking at a mean Spearman of only **+0.1455**
-- and each table turns out to recover a different part of the approved label:

| label warning | rank in common table | rank in serious table |
|---|---|---|
| ENHERTU boxed warning: interstitial lung disease (topo-I → pulmonary) | 10 / 14 | **2 / 14** |
| PADCEV boxed warning: SJS/TEN (tubulin → dermatologic) | 13 / 14 | **1 / 14** |
| BESPONSA boxed warning: hepatotoxicity/VOD (calicheamicin → hepatic) | 3 / 14 | 3 / 14 |
| ZYNLONTA: myelosuppression (PBD → haematologic) | **5 / 14** | 10 / 14 |

The pattern is not noise. The **serious** table recovers the *boxed* warnings, which are
life-threatening events by definition. The **common** table recovers the high-frequency
sections -- and ZYNLONTA's myelosuppression, a Warning rather than a boxed warning, is
where the common table is the better of the two. Each is right about its own outcome.

**This is a finding about our product, not about the censoring.** The system ranked designs
on the common table, so for a patient with pre-existing ILD it placed T-DXd's
boxed-warning organ in the bottom third of fourteen -- the exact case the system exists to
handle. We had not noticed because a label-derived hard flag was raising that axis to
`high` by rule, which masked the underlying term and, worse, made the ILD case study
circular: a rule encoding "prior ILD plus a deruxtecan payload is high risk" decides the
very question the case study asks.

So an axis is now banded on the table that matches the question asked about it: an axis the
patient is vulnerable on is a serious-harm question, the rest are tolerability. The model
now reaches `high` on pulmonary for an ILD patient **on its own**, and the ranking changes
behaviour rather than just numbers -- the top candidate for that patient moves off a
topoisomerase-I payload onto a tubulin one, away from the chemistry that threatens the
declared organ.

### The band thresholds were asserted, and they were unsafe off their own table

Bands were cut at the constants 0.05 and 0.20. On the common table those sit at the 15th
and 60th percentiles of non-zero observed rates, so they were a reasonable guess for the
one table they were chosen against. On the serious table, where rates are an order of
magnitude smaller, 0.05 sits at the **91st** percentile and 0.20 at the **99.4th**: the
constants would render 91% of serious cells `low`. For the deruxtecan design above:

| basis | rate | band |
|---|---|---|
| serious rate on measured serious edges (0.0075, 0.0250) | 3.1% | **high** |
| common rate on measured common edges (0.0645, 0.2174) | 14.0% | moderate |
| serious rate on the old asserted constants (0.05, 0.20) | 3.1% | **low** ← the bug |

The error ran in the most dangerous available direction: reassuring, on the organ named in
a boxed warning, for the patient most exposed to it. Edges are now the 15th/60th percentile
of non-zero observed rates in the table each posterior was fitted on, stored in the
artefact — computed rather than asserted, like the C2 dose floor. `risk_band` requires the
edges instead of defaulting them, because an implicit scale is exactly how this happened.

## 5d. How much work does the label-rule layer do?

The rules are label-derived overrides that can only raise a band. They are a liability if
they are doing the model's job, so each one's marginal contribution is measured.

<!-- generated: hard-flag-necessity -->

| label rule | serious rate | model alone | with rule | |
|---|---|---|---|---|
| `dxd_prior_ild` (ENHERTU) | 0.0277 | high | high | confirmatory |
| `calicheamicin_prior_vod` (BESPONSA) | 0.0166 | moderate | high | **load-bearing** |
| `vedotin_prior_sjs_ten` (PADCEV) | 0.0046 | low | high | **load-bearing** |
| `mmaf_prior_keratopathy` (BLENREP) | 0.0018 | low | high | **load-bearing** |
| `dxd_moderate_renal_pulmonary` (ENHERTU) | 0.0277 | high | high | confirmatory |

The rule layer is load-bearing for **3 of 5** flags. It is confirmatory for `dxd_prior_ild`, `dxd_moderate_renal_pulmonary` -- both deruxtecan/pulmonary -- which means the model now reaches the boxed-warning band there on its own. That matters beyond tidiness: while the rule was raising that band, the ILD case study was deciding its own question.

What the rules still carry is the informative part: MMAE/dermatologic, MMAF/ocular. Both are payload-level effects inside a single mechanism, and both are boxed warnings the model ranks `low`. That is not a bug to fix -- it is the same identification limit this report measures three other ways. The mechanism level is too coarse to separate MMAE from MMAF, and the payload family level does not converge at any corpus size reachable here, so these two warnings cannot come from the fit and have to come from the label.
<!-- /generated: hard-flag-necessity -->

## 5e. The target antigen was an inert input, and what it took to fix

**Measured before the fix: the target changed nothing.** Swapping ERBB2 for CD33, for
NECTIN4, or for an invented string left the 106 enumerated candidates, the 74 constraint
passes, all fourteen organ estimates and every objective score bit-identical. The single
thing it touched was a sentence naming the nearest existing ADC. So the product's headline
-- comorbidity profile *and target antigen* in, design out -- was half false: the system
was a function of the comorbidity profile alone.

The cause was structural. The only route by which a target could matter is per-organ
target expression, constraint C3, and that constraint was declared in the code and never
ingested. It is also the gap that answers a separate question put to this project, whether
AlphaFold would help: the missing quantity is abundance, not structure.

### What the expression data does and does not support

Per-organ expression for all 14 target antigens now comes from GTEx and Tabula Sapiens via
Open Targets. Two sources because neither covers the axes alone -- GTEx has no eye and no
ear, Tabula Sapiens has no brain -- and their units are never pooled, only ranked within a
target.

**It does not predict labelled organ toxicity.** Against the organ concern encoded in 14
approved ADCs' dose-modification tables, AUROC is 0.521 from GTEx and 0.576 from Tabula
Sapiens, and controlling for payload mechanism does not rescue it. That agrees with the
preclinical literature this project already cites: across 14 vedotin ADCs toxicity was
largely antigen-independent and target tissue expression correlated poorly with
dose-limiting toxicity (PMID 38692647).

**It does recover the specific on-target off-tumour cases.** Five textbook pairs, written
down with their mechanisms before the numbers were read:

| target | axis | percentile | mechanism |
|---|---|---|---|
| NECTIN4 | dermatologic | 1.00 | enfortumab vedotin skin toxicity; NECTIN4 is in normal skin |
| CD33 | haematologic | 1.00 | normal myeloid cells |
| CD19 | haematologic | 1.00 | normal B cells |
| ERBB2 | cardiovascular | 0.92 | cardiomyocytes |
| FOLR1 | renal | 0.83 | proximal tubule |

All five land in the target's top quintile, against a chance expectation of one in five.
Counted honestly there are four independent facts rather than five, because the blood
targets are one fact about immune antigens in immune tissue.

So expression locates **which organ a target could reach**, not **how toxic a drug is**.
The threshold is the weakest known case rather than a round number: FOLR1 in kidney sits
at 0.83, so the cut is 0.80 -- the strictest value that still captures all five, where 0.90
drops FOLR1 and 1.00 drops three.

### The aorta objection does not bite at axis granularity

The project plan abandoned this constraint because GTEx reports ERBB2 at 86.6 TPM in aorta,
which reads as "HER2 is an artery gene" when HER2 cardiotoxicity is cardiomyocyte. At axis
granularity the objection dissolves: aorta and cardiomyocyte are both `cardiovascular`, so
the axis answer is the same either way. The cell-resolved data then settles which it is --
cardiac myocytes at 112.0 and 103.6 against aortic smooth muscle at 54.7 -- which is why
cell types are carried as the evidence behind a flag and never as the score itself. Taking
the maximum over cell types was tried and rejected: it put ERBB2's musculoskeletal axis at
182 via erythrocytes and its cardiovascular axis at 141 via a neuron in a ventricle
sample, single rows with no sample count behind them.

### It is a flag, and a rejection rule was built and discarded

A hard constraint was prototyped: reject a candidate when the patient is vulnerable in an
organ, the target is abundant there, and the payload is bystander-permeable. It fired
sensibly -- ERBB2 for a psoriasis patient but not for an ILD/CKD one, FOLR1 the reverse,
TNFRSF8 never -- and it was still discarded, for two measured reasons. It removed **87% of
candidates** whenever it fired, since 92 of 106 carry a permeable payload. And it **never
changed the recommendation**, because the two non-permeable payloads it spares, DM1 and
MMAF, were already the top-ranked ones. Destroying seven eighths of the candidate space to
leave the answer untouched is not a screen.

What ships instead raises the risk band one step on an at-risk axis where the target is
abundant, in the same architecture as the label-derived rules, and names a
`target_expression` driver that states its own weakness. The target now changes the output:
for a psoriasis patient, NECTIN4 and ERBB2 give a `moderate` skin band sourced from
`target_expression` while CD19 and TNFRSF8 give `low` sourced from `model`.

**What it still does not change is the top recommendation.** Rank 1 is DM1/SMCC/DAR 3.5
for every target tested, because that candidate wins on the payload profile whatever the
target. So the honest claim is that the target now changes the risk numbers, the bands and
the stated reasons, and does not yet change which design is proposed first.

## 6. The exclusion-criteria signal

1,281 ADC trials against 2,481 oncology controls, all with eligibility text. Enrichment
over the control base rate, exclusion-polarity statements only:

<!-- generated: exclusion-enrichment -->

| payload mechanism | n | pulmonary | neurologic | ocular | hepatic |
|---|---|---|---|---|---|
| base rate (oncology) | 2,481 | 22.7% | 11.5% | 1.7% | 10.8% |
| tubulin | 664 | 1.6x | **8.0x** | **17.8x** | 1.9x |
| topo1 | 406 | **5.8x** | 1.0x&dagger; | **14.3x** | 0.8x&dagger; |
| dna_cleave | 180 | 0.4x | 0.5x | 0.2x&dagger; | **3.8x** |
| dna_crosslink | 39 | **2.4x** | **3.5x** | 0.7x&dagger; | **5.2x** |
| protein_synth | 15 | 3.0x&dagger; | 0.2x&dagger; | 1.9x&dagger; | 0.3x&dagger; |
| dna_alkyl | 7 | **7.5x** | 0.5x&dagger; | 13.6x&dagger; | 1.9x&dagger; |

Bold is enriched at least 2x **and** significant under Benjamini-Hochberg across all 66 (mechanism, organ) cells at q=0.05 (critical p = 1.82e-02). A dagger marks a cell not distinguishable from the base rate. For most of them the ratio is simply near 1 and there is nothing to distinguish. The ones that matter are the large ratios that still fail: dna_alkyl/ocular at 13.6x on 7 trials, protein_synth/infectious_immune at 5.2x on 15 trials, protein_synth/pulmonary at 3.0x on 15 trials. Each sits on a mechanism carried by a single drug, so the figure is one sponsor's protocol habits rather than a property of the chemistry, and the product suppresses it rather than displaying it.
<!-- /generated: exclusion-enrichment -->

Polarity separation is essential and was not obvious. Pooling inclusion lab floors with
explicit exclusions hides the signal: the hepatic base rate falls from 64.2% to 10.8% once
bilirubin and transaminase floors are removed, and only then does the calicheamicin
veno-occlusive signal appear at all.

The boilerplate diagnostic names the organs that carry little information. Measured spread
across mechanisms, per organ: renal 4.0x, cardiovascular 4.8x, haematologic 4.9x,
gastrointestinal 8.7x, metabolic 17.6x, pulmonary 19.3x, hepatic 19.6x, infectious/immune
21.3x, neurologic 32.3x, dermatologic 84.0x, ocular 109.3x. The flat organs are renal,
cardiovascular and haematologic -- every oncology protocol carries an LVEF floor and a
marrow-reserve floor. An earlier version of this paragraph named cardiovascular and
infectious/immune as the boilerplate pair at "1.8x each"; the first was roughly right and
the second is among the most variable organs in the table.

**This is consistency, not anticipation.** For almost every agent the warning this
recovers was already in the label at approval. Conflating the two would be the easiest way
to overstate this project.

## 7. The one anticipatory target

openFDA does not serve label history. DailyMed does, so 183 label versions across 14 ADCs
were diffed on section-5 headings and boxed-warning headlines.

**7 dated organ-axis additions across 4 agents**, plus 3 escalations into a boxed warning.
Power was fixed before any result: with 14 axes the null P(top three) is 0.214, so 4 of 7
would have given p = 0.042. The concentration concern at that point was brentuximab
vedotin, which contributed 4 of the 7 events, and a leave-brentuximab-out sensitivity was
declared mandatory.

**It turned out not to be needed, for a worse reason.** All four brentuximab events
predate a corpus large enough to fit on -- its earliest addition is 2014, when 29 arms
had posted results against a floor of 60 -- so they are not scorable at all. Rather than
relaxing the floor to recover them, which would score the model on noise and on the
drug most able to dominate the result, they are reported as unscorable. The scored set is
therefore three events from three different drugs, which removes the concentration
problem and most of the power along with it. The leave-one-drug-out check is still run and
reported, now trivially: dropping any one of the three leaves two.
**This is a case series with a permutation test, not a validation study.**

<!-- generated: label-change -->

**3 of 7 events were scorable**; the rest predate a corpus large enough to fit on, and are reported as not scorable rather than scored on noise.

| quantity | value |
|---|---|
| events scored | 3 across 3 independent drugs |
| mean predicted rank | 4.6667 of 14 (null 7.5) |
| in top three | 1 of 3 |
| one-sided p | 0.5149 (not significant) |

The mean rank beats the null, but the test does not reach significance. And it barely could: at 3 scorable events only **3 of 3** or better reaches p<0.05, so a single miss ends it. That is the same defect as the unfireable AUC gate elsewhere in this report -- a test whose outcome was nearly determined by its own sample size. It is reported as a case series with a permutation test, which is what it is.
<!-- /generated: label-change -->

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
