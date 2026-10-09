# Model card: forward organ-toxicity model

**Status: the model does not beat a base-rate baseline on any of six evaluations. On one of
them -- leave-one-agent-out, which is the task the product performs -- it is no longer
measurably behind one: -0.0121 with an interval spanning zero. Read this section first.**

Figures below are from the re-run on the corrected model. A non-identifiability was found
after the first round, every number was withdrawn, and the re-run reproduced the within-arm
results almost exactly -- see `## The bug that invalidated the first evaluation`.

They are also from a rebuilt corpus. Attribution matches a ClinicalTrials.gov event group
against the names in `conf/adc_registry.yaml`, 17 of whose 35 agents came from the
literature's payload-linker stem sweep, and the corpus on disk predated that growth. Rebuilt
against the current list it holds **22 agents, 299 arms and 4,186 cells** rather than 16, 285
and 3,990. Two headline numbers moved with it: the leave-one-agent-out deficit from -0.0422
to -0.0121, and the across-agent correlation that was this project's only positive result
from rho +0.1332 at p = 0.025 to **+0.0073 at p = 0.4595**. Six more agents erased the
second rather than sharpening it, so there is now no positive result to report.

## Intended use

Research prototype. **It does not rank.** It returns a filtered, non-dominated *set* of
chemically valid, individually precedented ADC configurations with per-organ-system rates
and intervals, weighted against a stated comorbidity profile. A ranked list is printed only
where the leader beats the runner-up on 80% of paired posterior draws, and across 24 targets
by 8 comorbidity profiles that happens in **0 of 192 queries**: the leader wins a median
52.2% of paired draws. Not a clinical decision tool; not validated prospectively; no use in
patient care.

## What the data can identify

Design features -- payload mechanism, linker type, cleavability, DAR, isotype, target --
are **agent-level constants**. Trastuzumab emtansine's 48 arms are 48 observations of its
trial populations but one observation of DM1 chemistry. The data that identifies a design
coefficient is therefore `n_agents x n_axes`:

The numbers below are for every corpus this project has built, generated from
`artifacts/corpus_ablation.json` so the table cannot describe fewer stages than exist. **The
results in this card are fitted on the second row**, the ClinicalTrials.gov corpus read with
the literature's agent list.

<!-- generated: corpus-ablation -->

| stage | agents | arms in the grid | cells | cells that identify a design coefficient | ratio against 100 design parameters | observed | viable LOMO folds |
|---|---|---|---|---|---|---|---|
| ClinicalTrials.gov, the original 18-agent list | 16 | 285 | 3,990 | 224 | 2.24 : 1 | 86.3% | 2 |
| ClinicalTrials.gov, the literature's agent list | 22 | 299 | 4,186 | 308 | 3.08 : 1 | 86.6% | 3 |
| + literature arms for agents already present | 25 | 459 | 6,426 | 350 | 3.5 : 1 | 67.9% | 3 |
| + literature agents | 32 | 482 | 6,748 | 448 | 4.48 : 1 | 66.9% | 3 |
| + the hand-transcribed database | **65** | 613 | 8,582 | **910** | **9.1 : 1** | 63.0% | **4** |

Each stage is a superset of the one before it -- 4 transitions, **0 corpus arms dropped** across all of them -- so a difference in this table is always arms added and never arms lost.

<!-- /generated: corpus-ablation -->

The second row is the one this card did not have. Attribution matches a
ClinicalTrials.gov event group against the names in `conf/adc_registry.yaml`, and 17 of its
35 agents were found by the literature's payload-linker stem sweep -- so **6 agents and 84
identifying cells came out of registry data that was already on disk**, at no cost to the
observed share, and the third mechanism fold opens there rather than with the paper arms.
Extracting the arms bought 42 more identifying cells and took the observed share from 86.6%
to 66.9%.

Every row is the **common-events** table. On the serious table the extension buys almost
nothing -- 17 agents over 290 arms, against the registry's 16 over 284 -- because 405 of the
414 literature arms publish no serious-adverse-event table at all, and the hand-transcribed
database was ingested for its any-grade rows only: its **5,516** severe-grade organ rows
with denominators, over 69 agents, are a severity table and not a seriousness one -- Grade
>=3 is a severity cut where a serious adverse event is a regulatory category, and a severity
table from a paper carries its own reporting cut, so it cannot serve as the uncensored
comparison the serious table provides. A different outcome rather than more of the same. So the two-table comparison this card uses as a robustness
check is available for the registry corpus and for neither extension.

**The measurement that had not come back has come back, and it is why this card still
reports the second row.** The 32-agent corpus's cross-validation is worse than the
22-agent corpus's on every split -- leave-one-mechanism-out -0.156 against -0.0200,
leave-one-family-out -0.155 against -0.0590 -- and its default fit does not converge, at a
worst standardised seed gap of 0.722 against a threshold of 0.3. Dropping uninformative
absences fixes the convergence and leaves the degradation where it was, so the expansion
genuinely costs held-out accuracy rather than merely breaking the sampler. See negative
result 50.

**The last row is a different kind of corpus and changes what is identifiable.** It merges a
hand-transcribed database of 99 ADCs supplied by a collaborator, and at this project's own
quality threshold it reaches 65 agents and 910 identifying cells -- **9.1 : 1, the first time
this project clears the 8:1 floor its own plan set for a level-by-axis interaction** -- and
makes `dna_cleave` a fourth viable fold, four calicheamicin ADCs having published a usable
table where two are approved. Its fits are running and this card will state their results or
say nothing about them.

One thing already measured about it is a reason *not* to serve it. 44 of its 65 agents have
arms from a single reporting source, so the agent random intercept and the source term are
collinear for two thirds of the corpus and `sigma_agent` comes back at +1.0326 against the
registry corpus's +0.3500 -- a between-agent scale with a reporting gap added to it. The
product adds a draw from that parameter to every prediction for a new design, so serving the
merged posterior would report reporting practice as drug uncertainty. The merged corpus is
for the design coefficients and the folds; the registry corpus is for the agent-level
residual, being the only one with no source variation at all. See negative result 48.

Worth reading the arms row against the identifying-cells row. Adding 312 literature arms
for agents already present bought 14 identifying cells; the next 102 arms, belonging to
agents that were not, bought 210. Arms of a known agent are more observations of its trial
populations and none of its chemistry.

## Results

<!-- generated: results-table -->

| evaluation | model | best baseline | delta | 95% CI | |
|---|---|---|---|---|---|
| within-arm ranking, leave-one-agent-out (22) | 0.8053 | 0.8220 | -0.0121 | [-0.0299, +0.0055] | includes 0 |
| within-arm ranking, leave-one-mechanism-out (3) | 0.8568 | 0.8768 | **-0.0200** | [-0.0294, -0.0031] | excludes 0 |
| within-arm ranking, leave-one-family-out (6) | 0.7800 | 0.8390 | **-0.0590** | [-0.0929, -0.0233] | excludes 0 |
| across-agent per-axis Spearman | -0.0152 | +0.1162 | -- | [-0.2054, +0.1614] | includes 0 |
| dose-modification ordering (13) | +0.1797 | +0.1672 | +0.0125 | [-0.0264, +0.0511] | includes 0 |

<!-- /generated: results-table -->

The best within-arm predictor is the global axis mean, which carries no design information.
The dose-modification comparison has now lost favourability twice. It read
+0.039 [+0.003, +0.073] before the centering fix, +0.035 [-0.001, +0.069] after it, and
+0.0125 [-0.0264, +0.0511] once the cross-validation folds were corrected --
because it is computed from held-out fold predictions, so correcting the folds moved it.
The model fell slightly, from +0.1882 to +0.1797, while its baseline rose from +0.1533 to
+0.1672: the same pattern the controlled fold comparison explains, where restoring the
discarded training arms helps a base rate more than it helps the model. In the same output
the model is at chance on naming the organ each label fears most (1/13 against 0.93
expected), naming gastrointestinal for 8 of 13 drugs because that is the axis base rate.

A sixth evaluation sits outside this table because it has no baseline column and is not a
rank-correlation: the anticipatory test, which asks whether a model fit only on data
public before a given date ranked the organ FDA was about to add a warning for. It is
reported in `report/findings.md` section 7. Result: 3 of 7 label-change events were
scorable, mean predicted rank 4.6667 of 14 against a null of 7.5, 1 of 3 in the top
three, p = 0.5149. The mean rank beats the null and the test cannot establish it -- at
three events only 3 of 3 reaches p<0.05. It is a case series with a permutation test.

### The gate, which stands regardless

The original gate -- macro AUC below 0.65 triggers the cut order -- is unfireable and has
been replaced. A constant global-axis-mean predictor scores about 0.84 on that metric, so
a 0.65 threshold is cleared by a predictor that knows nothing about the design. This is
independent of the bug: it is a property of the metric, and an absolute threshold on a
base-rate-dominated metric cannot detect the failure it was written to detect. The gate is
now the paired delta against the strongest baseline.

### What the within-arm metric can and cannot show

The pre-specified metric ranks 14 axes *inside one arm*. Axis base rates are consistent
enough across arms that a single fixed ordering is close to optimal everywhere, so a model
that knows those base rates and then perturbs them with design effects has little room to
gain and plenty to lose. Whatever the re-run shows, that metric alone cannot establish that
the design terms carry no signal; the across-agent comparison is the one that can, and both
are reported together.

## The bug that invalidated the first evaluation

Found by reading one prediction that could not be true: on a 153-arm corpus the model put
the otologic axis at 0.9997 where its observed rate is 0.04.

Two coupled degeneracies:

1. **Random intercepts were not constrained to sum to zero.** A non-centered `sigma * u`
   with `u ~ Normal(0, 1)` lets the random effects carry a common offset, which is exactly
   collinear with the axis intercept. The fit could place `mu_axis` far from the data and
   pull every observed arm back with its random effect. In sample this is harmless; out of
   sample it is ruinous, because a design with no trial and no agent drops the random
   effects and inherits the uncompensated intercept.
2. **Cleavability entered as a raw indicator.** Three of twenty-two agents carry a
   non-cleavable linker, so the indicator is nearly constant and behaves as a second
   per-axis intercept, unidentified against `mu_axis`. Growing the corpus does not relieve
   this. The count runs 2 of 16 on the original agent list, 3 of 22 once the literature's
   names are used, and 3 of 32 with its arms -- a 12.5%, 13.6%, 9.4% share -- so tripling
   the agents left the indicator no less nearly constant. Non-cleavable linkers are a fixed
   minority of the chemistry rather than an under-sampled corner, and the reparameterization
   is load-bearing at any corpus size this project can reach.

| | before | after |
|---|---|---|
| `tau_cleav` | 3.872 (eight times its prior scale) | 0.391 |
| `tau_mech` | 0.157 | **0.531** |
| max predicted rate | 1.0000 | 0.3930 |

The `tau_mech` recovery is the consequential line: the degenerate cleavability term had
been absorbing the mechanism effect, so the first evaluation measured a model whose main
effect was being soaked up by an artefact.

## Where the model fails, and why the pattern is informative

The previous version of this section claimed that every large miss is an agent that is the
sole representative of its payload *family* inside a broader mechanism class. It said,
correctly, that the figures came from the pre-fix model and that whether the pattern
survived a re-run was itself a result.

**It did not survive.** On the split-corrected folds, none of the four worst is the sole
representative of its family, and the two worst are each other's only family sibling.

<!-- generated: fold-difficulty -->

| fold | delta vs baseline | same-payload siblings | family share of mechanism | sole of family |
|---|---|---|---|---|
| trastuzumab emtansine | **-0.1165** | 0 | 0.20 | no |
| mirvetuximab soravtansine | **-0.0945** | 0 | 0.20 | no |
| belantamab mafodotin | **-0.0543** | 1 | 0.70 | no |
| gemtuzumab ozogamicin | **-0.0484** | 1 | 1.00 | no |

Sole-of-family agents among the four worst folds: 0/4. Mean delta +0.0227 for the 2 sole-of-family agents against -0.0156 for the 20 that share one -- no separation. Rank correlation of fold delta with same-payload siblings +0.206, with family share of its mechanism +0.242.
<!-- /generated: fold-difficulty -->

What replaces it is coarser and worse for the project. Fold difficulty tracks **how many
agents share the held-out agent's payload**, more strongly than it tracks anything about
families. The four vedotins, each with three same-payload siblings, are all predicted
within 0.03 of their baseline. Trastuzumab emtansine and mirvetuximab soravtansine have no
payload sibling and belong to a two-agent family inside an eight-agent mechanism that
auristatins dominate, and they are the two worst folds by a wide margin.

The squeeze is therefore tighter than this document previously claimed. The level that
predicts held-out performance is payload, and payload is precisely the level this corpus
can never reach: its vocabulary grows as fast as the corpus does, 9 classes at 17 agents to
20 at 54, so the cells-per-parameter ratio stays flat however much data arrives. Payload
*family* at least stops growing, which is why it was worth trying -- and it does not
converge here in either parameterization. So the diagnosis is not "we need the family
level" but "the level that would help is the one that recedes".

### The same squeeze measured at the output, not at the folds

Fold difficulty says payload is the level that predicts held-out performance. The direct
version of that is to ask what the model can say about two payloads *inside* one mechanism,
where cleavability and DAR are the only levers it has left.

<!-- generated: payload-compression -->

Within `tubulin`, over the payloads with enough observed cells, the model's ordering of the payloads on an organ axis is uncorrelated with the observed ordering: **mean Spearman -0.0571** across 14 axes, from -1.0000 on constitutional to +0.8000 on neurologic.

On the ocular axis the observed rates span **0.0698 to 0.5262, a factor of 7.54**, and the model spans **1.27**.

| payload | observed | cells | model |
|---|---|---|---|
| DM4 | 0.5262 | 10 | 0.0817 |
| MMAF | 0.3968 | 24 | 0.1039 |
| DM1 | 0.0880 | 36 | 0.1019 |
| MMAE | 0.0698 | 64 | 0.0834 |

Which granularity recovers the spread, axis by axis: on ocular **7.54x at payload, 1.15x at family, 1.61x at cleavability**; on hepatic **2.99x and 2.99x**; on cardiovascular **4.68x and 3.53x**. So payload family is a serviceable proxy for most organ axes and a useless one for ocular -- and the fit has the family level disabled, which leaves cleavability as the whole vocabulary.

<!-- /generated: payload-compression -->

The two high-ocular payloads are MMAF, which is non-cleavable, and DM4, which is cleavable;
the two low ones are DM1, non-cleavable, and MMAE, cleavable. Cleavability is orthogonal to
ocular risk on this corpus, and the high pair straddles both families, so neither of the two
coarser levels stands in for payload here. **The system distinguishes mechanisms on organ
profile and does not distinguish payloads within one.** MMAF corneal toxicity is among the
best-established organ effects in ADC pharmacology and is the clearest case of something
this model cannot express.

## Calibration and uncertainty

<!-- generated: fitted-parameters -->
`tau_cleav` 0.2871 [0.2027, 0.4133] -- the scale of the cleavable-versus-non-cleavable linker contrast across axes. Clear of zero, and about 0.5293 times the mechanism scale -- so linker cleavability shifts the organ profile, and shifts it less than the payload mechanism does. **It rests on 3 agents at the minority level, below the 8 a binary contrast needs**, and all of them sit in one mechanism (tubulin). So this is not the comfortably identified design axis this report used to call it: the contrast has no variation at all in the other mechanisms, and removing tubulin would remove it entirely. On the corpus merged with the hand-transcribed database the minority level reaches 17 agents across three mechanisms, which is the first corpus where the contrast is between chemistries rather than inside one.

`tau_mech` 0.5424 [0.4494, 0.6398] -- the mechanism x axis interaction is supported by the data rather than asserted by a parameter count: the scale clears zero, and it is the largest of the design scales in this block.

`sigma_agent` 0.3433 [0.2423, 0.4898] -- the residual between-agent scale left after the design slots, at 0.6329 times the mechanism x axis scale (`tau_mech` 0.5424). Comparable in magnitude, so the slots account for part of the between-agent variation and leave a residual of the same order as the mechanism effect itself. Agent identity carries information the seven design slots do not. On the seriousEvents table, which has no censored cells, the same ratio is above one and the reading reverses -- see `artifacts/residual_scale.json`.

`b_combo` +0.1930 [+0.1645, +0.2202] -- combination arms do report higher rates -- on this corpus, where every arm is a ClinicalTrials.gov record. On the literature-extended corpus the same coefficient reaches +1.091 without a source indicator, because every combination arm is a registry arm and none of the 194 literature arms is one, so it estimates the corpus rather than the regimen. That pair was measured before the corpus rebuild and before `b_source` existed, so the registry value beside it there is +0.195 rather than the figure above; both are recorded under `b_combo_without_source_term` in `artifacts/source_confounding.json` and neither is regenerated by any target, because the specification that produced them was replaced in response to them. See negative result 33.

`b_log_n` +0.0336 [+0.0236, +0.0435] -- an ascertainment effect that would have been attributed to the design had it not been controlled. It takes the opposite sign on the seriousEvents table (-0.2063 against +0.0336 here), which is the largest disagreement between the two tables in this block, so what it absorbs is not one effect measured twice. Treat it as a per-table nuisance term and not as an estimate of how ascertainment works.

`b_dar` +0.0385 [-0.0430, +0.1220] -- includes zero. DAR is an agent-level constant and is confounded with agent identity here. The pharmacokinetic literature supports a DAR effect; this corpus does not resolve one.

`b_thresh` +0.0341 [+0.0292, +0.0393] -- the reporting-threshold covariate. Not the censoring correction: it is 3.7318 times larger on the seriousEvents table, which has no censored cells at all, so it is substantially absorbing trial-level reporting practice.

Convergence stands in for R-hat: the model is refit under a second seed and posterior means compared. The worst standardized gap is 0.0987 pooled standard deviations, on `sigma_agent`, against a threshold of 0.3 -- acceptable.
<!-- /generated: fitted-parameters -->


## What this model must not be used for

* Any claim of chemical generalization to an unseen payload structure. Not supported, and
  separately refuted: the chemistry corpus has no relatives for 9 of 11 payload classes.
* Any efficacy claim. No efficacy model is used.
* Any patient-specific risk statement. The comorbidity layer is an elicited prior with
  zero training rows and is labelled `elicited_prior` in every response.
* Ranking candidates at all, on the evidence measured. The API collapses candidates whose
  posteriors overlap into explicitly indistinguishable groups, and on every query swept the
  leading group holds a median 73% of the candidates that pass the constraints. The cards
  are a sample of the non-dominated set, chosen to span the payload chemistries, and the
  response states that selection rule rather than letting the order read as confidence.
* Reading an organ rate's ordinal comparison as a comparison with observed clinical rates.
  It ranks against this model's own prediction for the slots of every registry ADC with a
  fully stated chemistry; the posterior
  integrates out the per-agent effect, and the observed rates are censored at each trial's
  reporting cut.
