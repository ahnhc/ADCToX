# ADCTox: what the public data supports

Working draft. Every number here is measured, and `make all` regenerates all of it from
`artifacts/*.json`.

Stated precisely, because the looser version of this claim was false for most of the
project's life. The tables are generated from artefacts between markers in this file, so
they cannot drift. Figures quoted in prose are checked by `make check-report`, which fails
on any decimal it cannot find in an artefact; 19 are allowlisted with a stated reason
each, and superseded figures quoted in before/after comparisons live in
`artifacts/superseded/`. That guard was itself a no-op until recently -- it passed 99% of
randomly fabricated four-decimal figures -- so it now measures and prints its own
false-pass rate on every run. At three decimals it is still weak, which is why figures are
quoted to four where traceability is the point.

## Contents, and what each section found

The lettered sections are in the order they were written, not in order of importance. Each
line says what the section concluded, so a reader can go to the ones that matter to them.

| section | what it found |
|---|---|
| 1. What was built | A comorbidity profile and a target antigen in, proposed designs with per-organ rates out. |
| 2. The corpus | 3,990 cells, but only **224** identify a design coefficient, because design features are agent-level constants. |
| 3. Results | Beats no base-rate baseline, and on leave-one-agent-out is no longer measurably behind one: -0.0121, interval spanning zero. |
| 4. Where it fails | The design terms lose to a base rate by a measurable ratio; the obvious fix is not identifiable at either granularity, and the plan's "the horizon recedes at every level" holds only at the payload level -- the mechanism level doubled to the 8:1 floor. |
| 5. What it does support | The mechanism x axis interaction, linker cleavability, and the censoring treatment. |
| 5b. Censoring | The censoring treatment recovers signal rather than creating it, and `b_thresh` is a confounder control rather than that correction. |
| 5c. Two event tables | The common and serious tables rank organs differently; the serious one recovers the boxed warnings. |
| 5d. Label rules | How much of a band comes from the fit and how much from a label-derived rule, counted. |
| 5e. Target antigen | It was an inert input. Expression data now changes the bands and the stated reasons, and not which design is proposed. |
| 5e-b. Ranking | **The product cannot rank its own proposals in any of 192 queries**, and the comorbidity profile's influence is a function of an arbitrary constant. |
| 5e-c. Ordinal comparison | Every rate now carries its position among the registry chemistries, which recovers a boxed warning on its first use. |
| 5f. The one positive signal | **Gone.** It was +0.13 at p=0.025 on 16 agents and +0.007 at p=0.46 on 22 -- six more agents erased it. |
| 5g. Corpus expansion | The ceiling is 32 agents and not the planned 54, of which **31** publish an any-grade column; the expansion buys the common-events table and not the serious one. |
| 5h. Comorbidity layer | A non-circular holdout against 1,741 trials' exclusion criteria, at AUROC 0.666 against 0.750 circularly. |
| 5i. Its primary validation | Misspecified. The FDA labels argue from clearance, not organ toxicity, and point somewhere else. |
| 6. Exclusion criteria | Expert prior encoded at 4.4x to 127x enrichment -- consistency with known warnings, not prediction. |
| 7. Anticipatory target | Three dated label changes were scorable, mean rank 4.67 of 14, p = 0.51. A case series, not a validation. |
| 8. Dose modification | 78 orderable axis pairs; the ordering comes out clinically sensible without being told. |
| **9. Measured negative results** | **The strongest section. 43 results, each reproducible.** |
| 9b. Clean-clone check | 429 report figures all trace to a tracked artefact from a fresh clone; `make all` offline is impossible by design. |
| 10. Limitations | What this must not be used for. |

## 1. What was built

A system that takes a comorbidity profile and a target antigen and returns proposed ADC
designs with per-organ-system toxicity estimates. Research prototype; not a clinical tool.

The gap it addresses: existing ADC machine-learning work (ADCNet, DumplingGNN, Linker-GPT)
predicts efficacy, cytotoxicity, DAR and linker stability. Nothing predicts organ-level
*clinical* toxicity conditioned on a patient's existing organ damage.

### What it actually delivers, in one paragraph

Given a comorbidity profile and a target antigen, the system enumerates the chemically
valid, individually precedented designs, filters them against six constraints -- five of which reject and one of which
only flags -- and returns
the non-dominated set with a rate and a 90% credible interval on each of fourteen organ
systems, plus the ordinal position of each rate among the registry's chemistries. **It does
not rank the set**: across 24 targets by 8 profiles the leader beats the runner-up on a
median **50.0%** of paired posterior draws against the 80% this interface requires, so
**0 of 192** queries produce a ranked list. The rates come from a hierarchical binomial
model that **does not beat a base-rate baseline on any of six evaluations**, and the
across-agent organ correlation that was this report's one positive result **did not survive
the corpus rebuild**: it is now rho **+0.0073** at permutation **p = 0.4595**, so there is
no positive result here to inherit. The comorbidity profile enters as a displayed weight
rather than a logit; it changes the proposed set of options for six of the seven profiles
that name a condition, somewhere in the weighting constant's range, and changes nothing at
all for the seventh -- a patient with four comorbidities. Which design leads is responsive
to the profile in about a quarter of cases and only ever between two designs, because
**inside a payload mechanism the model cannot tell one payload from another on organ
profile**: its ordering of the four tubulin payloads is uncorrelated with the observed one,
and MMAF corneal toxicity, among the best-established organ effects in the field, is
specifically outside what it can say.

So what the system is for is the filtering, the intervals, and the refusals: it will not
rank what it cannot separate, will not price a payload mechanism it has never seen, and
will not offer a design whose parts have no clinical precedent. Sections 3 and 4 are where
the prediction fails, section 9 is the forty-three measured negative results, and section
10 is what this must not be used for.

## 2. The corpus, and the number that governs everything

Two columns, because which agents the registry knows about decides how much of
ClinicalTrials.gov is usable, and 17 of the 35 names in `conf/adc_registry.yaml` were found
by the literature's payload-linker stem sweep. The first column is the project's starting
point; the second is the same ClinicalTrials.gov data read with the literature's agent list.

| | original 18-agent list | literature's 35-agent list |
|---|---|---|
| ClinicalTrials.gov studies with an adverse-event module | 593 | 593 |
| AE event rows | 67,609 | 67,609 |
| event groups | 2,201 | 2,201 |
| attributable event groups | 781 | **894** |
| attributable to one ADC, n>=30, conventional ADC | **285 arms** | **299 arms** |
| (arm x axis) cells | **3,990** | **4,186** |
| distinct agents | **16** | **22** |
| **cells that identify a design coefficient** | **224** | **308** |
| mechanisms with a usable held-out fold | 2 | **3** |

The last row is the one that matters. Design features -- payload mechanism, linker,
cleavability, DAR, isotype, target -- are **agent-level constants**. Trastuzumab
emtansine's 48 arms are 48 observations of its trial populations and *one* observation of
DM1 chemistry. So the data identifying a design coefficient is `agents x axes` -- 224 in the
first column and 308 in the second -- not 3,990. An earlier draft of this project proposed a 420-parameter design matrix, which is
0.57 observations per parameter: fewer data points than parameters.

### What the corpus drops, and what each axis is made of

Two composition facts, both measured because both are discretionary and neither was
written down.

**The exclusions drop 9.3% of registry adverse-event rows and 4.7% of the patient mass.**
Nine system-organ classes never reach an axis, each with a stated reason in
`conf/ontology/axes.yaml`, and three quarters of the excluded patient mass is one of them:

| excluded system-organ class | rows | patients affected | reason | what is in it |
|---|---|---|---|---|
| injury, poisoning, procedural | 2,594 | 9,308 | not organ attributable | falls 234, contusions 104, fractures |
| psychiatric disorders | 1,551 | **37,394** | not organ attributable | insomnia 298, anxiety 218, depression 195 |
| neoplasms | 990 | 1,640 | indication confounded | |
| reproductive and breast | 690 | 1,686 | indication confounded | |
| five others | 424 | 710 | | |

Psychiatric is 74% of the excluded mass and is dominated by insomnia, anxiety and
depression, which is what makes the reason hold. The CNS-type minority inside it --
confusional state 129 rows, delirium, hallucination -- is 282 of 1,551, and in an oncology
population with brain metastases, opioids and steroids those are multifactorial, which is an
argument for excluding them rather than against. One term was rescued from the
injury/procedural bucket and it is negative result 37.

**One axis is mostly a laboratory finding.** MedDRA files laboratory abnormalities under
`Investigations`, so the taxonomy redistributes them to the organ -- and the hepatic axis
comes out **64% laboratory rows in the registry and 84% in the literature**, against 0-8%
for most axes. Haematologic is 35% and 18%, renal 17% and 31%. So "hepatic risk" is largely
transaminase elevation rather than hepatotoxicity as a clinical event; the interface labels
that axis rather than leaving it to a reader to know.

## 3. Results, after two rounds of correction

Two rounds of correction, in order: a centering bug in the random intercepts, which
invalidated a first round of evaluation entirely; and two bugs in the cross-validation
fold construction, which were leaking a trial into two splits while discarding half the
training arms from a third. Everything below is from after both.

**The model does not beat a base-rate baseline on any of these**, and on one of them it is
no longer measurably worse. The deficit excludes zero on leave-one-mechanism-out and
leave-one-family-out. On **leave-one-agent-out it is -0.0121 with an interval spanning
zero** -- the split that matches what the product does, predicting an agent it has not seen.

That changed with the corpus. On the 16-agent corpus the same split gave -0.0422 with an
interval excluding zero; rebuilding the registry against the current agent list took it to
22 agents and the deficit to a third of its size. Predicting a new agent is the task, and
on it the model is now indistinguishable from a base rate rather than measurably behind
one. It is not ahead: the point estimate is still negative.

The other direction moved too, and against the project. Section 5f's across-agent
correlation was this report's only positive result at 16 agents, at rho +0.1332 with a
permutation p of 0.025. At 22 agents the same estimator gives **+0.0073 at p = 0.4595**.
Six more agents erased it rather than sharpening it, so the report now has no positive
result at all -- which is a cleaner position than one marginal result reported with
caveats, and is the project's own best demonstration of why a p of 0.025 on sixteen units
is not a finding.

Deltas are paired against the strongest baseline for that split, because the model's own
interval excluding zero would only say the target ordering is not random. Each delta is
the mean over folds of (fold AUC minus that fold's better baseline), which is the
quantity the interval is computed on; the other aggregation, a difference of macro
averages, is in the artefact and differs where the winning baseline varies by fold.

<!-- generated: results-table -->

| evaluation | model | best baseline | delta | 95% CI | |
|---|---|---|---|---|---|
| within-arm ranking, leave-one-agent-out (22) | 0.8053 | 0.8220 | -0.0121 | [-0.0299, +0.0055] | includes 0 |
| within-arm ranking, leave-one-mechanism-out (3) | 0.8568 | 0.8768 | **-0.0200** | [-0.0294, -0.0031] | excludes 0 |
| within-arm ranking, leave-one-family-out (6) | 0.7800 | 0.8390 | **-0.0590** | [-0.0929, -0.0233] | excludes 0 |
| across-agent per-axis Spearman | -0.0152 | +0.1162 | -- | [-0.2054, +0.1614] | includes 0 |
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
cleavability entered as a raw indicator which, being nearly constant across the agents,
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
| trastuzumab emtansine | **-0.1165** | 0 | 0.20 | no |
| mirvetuximab soravtansine | **-0.0945** | 0 | 0.20 | no |
| belantamab mafodotin | **-0.0543** | 1 | 0.70 | no |
| gemtuzumab ozogamicin | **-0.0484** | 1 | 1.00 | no |

Sole-of-family agents among the four worst folds: 0/4. Mean delta +0.0227 for the 2 sole-of-family agents against -0.0156 for the 20 that share one -- no separation. Rank correlation of fold delta with same-payload siblings +0.206, with family share of its mechanism +0.242.
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

### 4.0 Why the design terms lose to a base rate: a ratio

The model losing to a predictor that knows only the per-axis base rates was an empirical
fact without a mechanism. The mechanism is a ratio, and it is measurable from the fitted
coefficients alone.

Within one arm the organ ranking is set by `mu_axis` plus the design effects. The baseline
spread is **sd 0.989** across the fourteen axes. Against that:

| mechanism | agents | effect sd | ratio to baseline | rank corr with baseline | axis positions moved |
|---|---|---|---|---|---|
| dna_alkyl | 2 | 0.629 | 0.64 | 0.701 | 20 |
| dna_cleave | 2 | 0.582 | 0.59 | 0.895 | 22 |
| dna_crosslink | 4 | 0.318 | 0.32 | 0.969 | 10 |
| topo1 | 4 | 0.338 | 0.34 | 0.978 | 8 |
| tubulin | 10 | 0.281 | 0.28 | 0.947 | 10 |

Cleavability sits at ratio 0.245, rank
correlation 0.943.

**The mechanisms with the most evidence reshuffle the organ order least.** Tubulin, with
seven agents, moves the ranking by a correlation of
0.947
-- which is to say barely. So on the within-arm metric the model is predicting the
baseline's ordering with a small perturbation, and a small perturbation of a good
predictor is a slightly worse predictor. That is the delta, explained.

**And the mechanism with one agent reshuffles the order most.** The relationship is
monotone in agent count -- ratios of 0.71, 0.61, 0.36, 0.36 and 0.29 for 1, 2, 2, 4 and 7
agents -- which is the shape of overfitting on thin data, not of a chemistry effect
emerging as evidence accumulates.

| mechanism | axis | effect | arms | agents |
|---|---|---|---|---|
| dna_alkyl | ocular | +1.98 | 2 | 1 |
| dna_cleave | ocular | -1.50 | 20 | 2 |
| tubulin | neurologic | +1.06 | 163 | 7 |
| topo1 | gastrointestinal | +1.03 | 68 | 4 |
| dna_alkyl | hepatic | -1.00 | 1 | 1 |
| dna_alkyl | haematologic | -0.97 | 2 | 1 |

The rank correlation between an effect's magnitude and the arms behind it is
**-0.231**: the largest fitted effects sit on the
thinnest evidence. `dna_alkyl`'s ocular coefficient reaches +1.98 on two arms of one drug,
beside tubulin's neurologic at +1.06 on 163 arms of seven -- and only the second is a
chemistry effect.

**The cause is a missing term.** `u_agent` is one scalar per agent, so it cannot absorb an
agent's idiosyncratic *organ profile*. An agent whose ocular rate is unusual has nowhere
to put it except `mech_axis[its mechanism, ocular]`. For a mechanism carried by a single
drug, the mechanism coefficient therefore *is* that drug's agent effect, and the model has
no way to know the difference. This is the project's central structural finding -- a design
coefficient is identified by agents, not arms -- appearing for the first time in the fitted
parameters rather than in a parameter count.

### 4.0b The missing term, added and measured

Section 4.0 names the cause: `u_agent` is one scalar per agent and cannot absorb an
agent's idiosyncratic organ *profile*, so for a single-drug mechanism the mechanism
coefficient is that drug's agent effect. The fix is an agent x axis deviation, and it was
built, run and kept behind `forward.USE_AGENT_AXIS` with the comparison in
`artifacts/cv_agent_axis.log`.

It converged -- worst standardized seed gap 0.133 -- and moved the right way. The thin
cell shrank more than the thick one, which is what the diagnosis predicted:

| | dna_alkyl / ocular (2 arms) | tubulin / neurologic (163 arms) |
|---|---|---|
| without | +1.989 | +1.064 |
| with | +0.626 | +0.529 |

And it split the splits:

| split | without | with |
|---|---|---|
| leave-one-agent-out | -0.0422 | **-0.0340** |
| leave-one-family-out | -0.0783 | **-0.0510** |
| leave-one-mechanism-out | -0.0191 | -0.0280 |

Agent and family holdout improve; mechanism holdout worsens. That is coherent rather than
puzzling: absorbing an agent's idiosyncrasy leaves a cleaner shared signal when you hold
out an agent or a family, but when you remove a whole mechanism there is no agent term to
help and `tau_mech` is smaller than it was, so there is less left to predict with.

**It is not enough.** All three splits still fail, `tau_mech` falls from
0.590 to 0.359 and `tau_cleav` from 0.278 to
0.151, so the term is absorbing design signal and not only idiosyncrasy --
cleavability was the one design axis this corpus identified comfortably. It is left off by
default: a structure that improves two splits, worsens a third and fixes none of them is
not an improvement to ship silently, and the log is kept the way the payload-family
attempts were, because a structure that does not work is a result.

### 4.1 The obvious fix is not identifiable, in either form

| model | worst standardized seed gap | outcome |
|---|---|---|
| mechanism only | 0.239 | converged |
| + payload family, additive | **0.686** | tau_mech fell 0.592 -> 0.436 as tau_family took 0.396; LOMO delta worsened to -0.022 |
| + payload family, nested | **0.577** | tau_mech 0.453 / tau_family 0.391 |

Additive fails for a clear reason: family determines mechanism, so two independent terms
compete for one variance. Nesting is the textbook correction and did not rescue it --
with 8 families across 5 mechanisms and 22 agents there is not enough information to
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

### 4.3 More data reaches it at two granularities and not at the third

The plan's claim was that the resolution which would improve prediction recedes as fast as
it is approached: each new agent brings a new payload, so the corpus can triple and
identifying-cells-per-design-parameter stays flat. Its table put that at 2.12, 2.91 and 2.84
over corpora of 17, 32 and 54 agents.

**Two of those three rows were projections, and the third corpus does not exist.** The
ceiling is 32 agents, of which 31 publish an any-grade column (section 5g), and the payload
vocabulary was projected to reach 12 classes and then 20. It reaches **16 payload identities
and 8 families** at 31 agents. Measured the plan's own way -- identifying cells over
`(levels - 1) x 14 axes`, which reproduces its mechanism-level 4.25, 6.40 and 9.00 exactly:

| granularity | original list, 16 agents | literature's list, 22 | + arms, 25 | full, 32 | change |
|---|---|---|---|---|---|
| payload identity | 1.78 : 1 (10 levels) | 2.20 (11) | 2.50 (11) | 2.13 : 1 (16 levels) | **1.20x** |
| payload family | 2.67 : 1 (7 levels) | 3.14 (8) | 3.57 (8) | 4.57 : 1 (8 levels) | 1.71x |
| payload mechanism | 4.00 : 1 (5 levels) | 5.50 (5) | 6.25 (5) | **8.00 : 1** (5 levels) | **2.00x** |

So the receding horizon is real and it is **specific to the payload level**. There the
vocabulary grew from 10 to 16 while the corpus grew from 16 to 32, and the ratio moved 20%
-- and it went *backwards* at the last step, 2.50 to 2.13, because the agents the extraction
added brought five new payloads with them. At the family level the vocabulary grew by one
and the ratio rose by seven tenths. At the mechanism level it did not grow at all -- the
taxonomy was frozen at seven before extraction and five appear in every stage -- and the
ratio **doubled to exactly the plan's 8:1 floor**.

That is the honest position and it is better than this report previously stated: the level
the model actually uses is identified at the threshold the plan set for it, the level that
would improve prediction is the one that recedes, and the family level in between sits at
4.57 against the 6.00 the plan projected it would need.

The first row counts the 16 agents the fitted model can represent. The registry holds 17
with usable arms; one is an immunotoxin -- an antibody-toxin fusion with no linker and no
conjugation chemistry -- and the design matrix has no slots to describe it. Both numbers
appear in this report and they count different populations.

The structural finding stands, narrowed: it showed up three times independently -- in the
parameter counting at the payload level, in the per-fold failure pattern, and in the
identification failure of both family parameterizations -- and the plan's version of it
overstated the case by projecting a payload vocabulary that grew faster than the one that
exists.

## 5. What the model does support

<!-- generated: fitted-parameters -->
`tau_cleav` 0.2871 [0.2027, 0.4133] -- the scale of the cleavable-versus-non-cleavable linker contrast across axes. Clear of zero, and about 0.5293 times the mechanism scale -- so linker cleavability shifts the organ profile, and shifts it less than the payload mechanism does. This is the one design axis the corpus identifies comfortably: cleavability is binary and needs only 8 agents to estimate, against the 40 a mechanism level needs and the 80 a payload level would.

`tau_mech` 0.5424 [0.4494, 0.6398] -- the mechanism x axis interaction is supported by the data rather than asserted by a parameter count: the scale clears zero, and it is the largest of the design scales in this block.

`sigma_agent` 0.3433 [0.2423, 0.4898] -- the residual between-agent scale left after the design slots, at 0.6329 times the mechanism x axis scale (`tau_mech` 0.5424). Comparable in magnitude, so the slots account for part of the between-agent variation and leave a residual of the same order as the mechanism effect itself. Agent identity carries information the seven design slots do not. On the seriousEvents table, which has no censored cells, the same ratio is above one and the reading reverses -- see `artifacts/residual_scale.json`.

`b_combo` +0.1930 [+0.1645, +0.2202] -- combination arms do report higher rates -- on this corpus, where every arm is a ClinicalTrials.gov record. On the literature-extended corpus the same coefficient reaches +1.091 without a source indicator, because every combination arm is a registry arm and none of the 194 literature arms is one, so it estimates the corpus rather than the regimen. That pair was measured before the corpus rebuild and before `b_source` existed, so the registry value beside it there is +0.195 rather than the figure above; both are recorded under `b_combo_without_source_term` in `artifacts/source_confounding.json` and neither is regenerated by any target, because the specification that produced them was replaced in response to them. See negative result 33.

`b_log_n` +0.0336 [+0.0236, +0.0435] -- an ascertainment effect that would have been attributed to the design had it not been controlled. It takes the opposite sign on the seriousEvents table (-0.2063 against +0.0336 here), which is the largest disagreement between the two tables in this block, so what it absorbs is not one effect measured twice. Treat it as a per-table nuisance term and not as an estimate of how ascertainment works.

`b_dar` +0.0385 [-0.0430, +0.1220] -- includes zero. DAR is an agent-level constant and is confounded with agent identity here. The pharmacokinetic literature supports a DAR effect; this corpus does not resolve one.

`b_thresh` +0.0341 [+0.0292, +0.0393] -- the reporting-threshold covariate. Not the censoring correction: it is 3.7318 times larger on the seriousEvents table, which has no censored cells at all, so it is substantially absorbing trial-level reporting practice.

Convergence stands in for R-hat: the model is refit under a second seed and posterior means compared. The worst standardized gap is 0.0987 pooled standard deviations, on `sigma_agent`, against a threshold of 0.3 -- acceptable.
<!-- /generated: fitted-parameters -->

Qualitatively the corpus is sound. Baseline-centered mechanism fingerprints reproduce the
boxed warnings unprompted: calicheamicin tops hepatic at +0.70 (veno-occlusive disease),
topoisomerase-I payloads top pulmonary and gastrointestinal, tubulin payloads place
neurologic in their top three.

### The per-axis explanation adds up, and that was never checked

Every organ row carries a waterfall: the fitted terms that produced its rate, each with its
source, plus the label rules and expression flags that may have raised its band. The
response also reports the gap between the terms' sum and the rate shown, with a note saying
the difference is Jensen's inequality -- the terms are posterior means in logit space, so
they decompose the mean logit exactly and the mean rate only approximately.

That note is only acceptable if the gap is small, and it had never been measured. Over six
payload chemistries by four comorbidity profiles, 336 rows: **largest absolute gap 0.0128,
median 0.0054.** So a reader adding up the contributions on screen lands within about half a
percentage point of the number above them and within 1.3 points at worst, and the
explanation is an explanation rather than an illustration.

Those figures were 0.0047 and 0.0012 on the 16-agent corpus. The gap scales with the
posterior variance and `sigma_agent` went from 0.159 to 0.343 when the corpus was rebuilt,
so it grew with the width of the posterior rather than with any change to the decomposition.
Raising the bound to match would be fitting the test to the data, so the **sign** is checked
instead, and that is what separates Jensen from a missing term: the sigmoid is convex below
0.5, so there the mean rate exceeds the rate implied by the mean logit and the gap is
negative. Measured, it is negative in **156 of 165** cells below rate 0.5 and positive in 3
of 3 above it. A term in the model and absent from the decomposition would shift every cell
the same way wherever its rate sat. That failure is not hypothetical: the model terms were
once omitted from the driver list altogether, leaving a banded axis showing a band and a
weight with no account of either.

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
genuine zero, 0 of its 3,976 cells are censored. So a censoring adjustment fitted on that
table should be zero. It is not:

| table | censored cells | `b_thresh` |
|---|---|---|
| otherEvents | 471 of 3,990 | +0.033 [+0.028, +0.039] |
| seriousEvents | **0** of 3,976 | **+0.131 [+0.113, +0.147]** |

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
shared mechanisms the two fits agree on organ ranking at a mean Spearman of only **+0.282**
-- and each table turns out to recover a different part of the approved label:

| label warning | rank in common table | rank in serious table |
|---|---|---|
| ENHERTU boxed warning: interstitial lung disease (topo-I → pulmonary) | 11 / 14 | **5 / 14** |
| PADCEV boxed warning: SJS/TEN (tubulin → dermatologic) | 14 / 14 | **4 / 14** |
| BESPONSA boxed warning: hepatotoxicity/VOD (calicheamicin → hepatic) | **2 / 14** | 3 / 14 |
| ZYNLONTA: myelosuppression (PBD → haematologic) | **10 / 14** | 14 / 14 |

The serious table ranks the boxed-warning organ higher in **2 of the 4** label-verified
pairs, and the two it wins are the two the common table buries: topoisomerase-I pulmonary
moves from 11th to 5th and tubulin dermatologic from last to 4th. The two it loses are a
calicheamicin hepatic signal the common table already has at 2nd, and ZYNLONTA's
myelosuppression -- a Warning rather than a boxed warning, where the common table is the
right one. Each table is right about its own outcome.

These ranks moved with the corpus rebuild and the direction of the finding did not: on the
16-agent corpus the pulmonary pair was 10th against 2nd and the dermatologic 13th against
1st, so the serious table's advantage on the two boxed warnings the common table buries is
smaller than it was and still there. The mean agreement rose from +0.1455 to +0.282, which
makes the tables less different than this section first reported and not similar.

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
| common rate on measured common edges (0.0645, 0.2157) | 14.0% | moderate |
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

## 5e-b. The product cannot rank its own proposals, in any of 192 queries

The interface was built to refuse to order designs it cannot separate: a ranked list is
printed only where the leader beats the runner-up on 80% of paired posterior draws, and
otherwise the head of the list is an unordered set. Whether that threshold ever fires was
never measured. It fires everywhere.

<!-- generated: rank-resolution -->

| quantity | value |
|---|---|
| queries swept (24 targets x 8 comorbidity profiles) | 192 |
| **queries with a decisive leader** | **0** |
| queries where every displayed candidate is in one tie group | 48 |
| median tie-group size at the head | 45.5 |
| median share of constraint-passing candidates in that group | 66% |
| median P(leader beats runner-up) | 0.5000 |

**0.5000** against the 0.800 required, and it barely moves across targets or profiles. This is not a threshold set too strictly: a leader that wins 50% of paired draws is a coin flip.

<!-- /generated: rank-resolution -->

The number is what it is because the posterior intervals on a single axis span roughly 0.17
to 0.28 while the designs differ by a few hundredths. **The ranked list of candidates this
product was specified to emit does not exist.** What exists is a filtered, non-dominated set
with per-axis intervals, and the interface now says so in those words rather than printing
"Rank 1" six times.

The fix for that display was not cosmetic, and four defects in the ranking layer came out
of looking at it -- an exact tie read as a loss, a transitive grouping rule, a non-dominated
candidate displaced by a dominated one, and six cards showing three payload chemistries with
two of them doubled while three non-dominated payloads went unshown. All four are in section
9. None was covered by any of the 413 tests passing at the time.

The last one changes what the product is for. Since the ranking does not resolve, the six
cards are a sample of the non-dominated set, and the sampling rule is doing the work the
ranking cannot. It now takes one candidate per payload chemistry before a second of any,
because payload is the dominant lever in this model: for the renal-plus-pulmonary HER2 query
the cards went from `DGN549, DGN549, DM1, DM1, DM4, DM4` to `DGN549, DM1, DM4, MMAE, MMAF,
SG3199`, six payloads with six different nearest approved ADCs. One of those six sits outside
the leading tie group, so it carries its rank and the interface says why it is there.

### The same sweep measures what the target antigen is worth

Section 5e found the target had been an inert input and reports what the expression flag
bought. The sweep quantifies the remainder:

| quantity | value |
|---|---|
| queries where the target changes at least one risk band | 49 of 192 (26%) |
| distinct sets of proposed designs across all 192 queries | **4** |
| comorbidity profiles swept | 8 |

Four distinct proposals from 192 queries, and fewer than one per profile. So the target
changes bands and stated reasons in a quarter of queries and changes the proposed designs in
none of them, which is exactly what section 5e claims and is now measured over the whole
input space rather than on the handful of targets it was spot-checked on. The comorbidity
profile does not do much better: eight profiles produce four distinct design sets, because
the weighting changes which axes are penalised and the payload ordering survives it.

### And the comorbidity profile's influence is a function of an arbitrary constant

The patient enters the objective as `w_o = 1 + lambda * severity_o`, and the shipped
`lambda = 2` gives an at-risk organ a weight of 3 against 1 for the other thirteen. That is
the plan's stated and defensible preference -- *you told us CrCl 25, so the renal axis is
weighted 3x* -- and it is also the reason the profile moves the proposal so little:

The quantity swept is the set of designs the product displays, which after the selection
fix spans the payload chemistries on the Pareto front -- so the question it answers is
whether the *options offered* change, not whether an ordering within them does.

| profile | at-risk axes | share of the objective at lambda = 2 | lambda where the shown set first changes | distinct sets over lambda in [0, 100] |
|---|---|---|---|---|
| renal + pulmonary | 2 | 33% | 5 | 5 |
| hepatic | 1 | 19% | 50 | 2 |
| cardiac | 1 | 19% | 5 | 3 |
| neuro + ocular | 2 | 33% | 30 | 2 |
| haematologic | 1 | 19% | 8 | 5 |
| dermatologic | 1 | 19% | 20 | 4 |
| **four organs** | 4 | 53% | **never** | **1** |

Two thirds to four fifths of the objective is organs the patient has no stated problem with.
Raising `lambda` until every profile gets its own set is not a fix -- it is choosing a
constant to make the output look responsive. The constant is the most arbitrary quantity in
the system, the plan picked 2 precisely because 3x is a preference a reader can check, and
the dependence is not monotone: the switch points run from 5 to 50 with no ordering by the
number of at-risk axes, and a hepatic profile needs a 51x weighting before its options
change at all.

The last row is the one worth keeping. **A patient with four comorbidities receives the same
proposal at every value of the constant**, because four at-risk axes out of fourteen spread
the weight back towards uniform and the payload that is best on their average is the payload
that is best overall. The comorbidity layer has the most influence on the simplest patient
and none on the most complex one, which is the opposite of useful. Seven profiles is not
enough to call that a law -- the single-concern profiles give switch points from 5 to 50 with
no clean ordering -- but the four-organ invariance is measured and it is the case a clinician
would care about most.

## 5e-c. A rate needs a comparison, and the comparison recovers a boxed warning

"Gastrointestinal 0.59, high" is close to unreadable. The plan specified an ordinal
position with its denominator and banned percentiles -- on roughly twenty reference
chemistries a percentile invents resolution the sample cannot carry -- and the field had
never been built. It is built now: the same posterior's prediction for the *slots* of
every registry ADC with a fully stated chemistry, agent-level residual off, ranked against
the queried design.

Two rules make it a claim rather than a decoration. It **follows the band's table**: an
at-risk axis is banded on the serious table, and ranking a serious rate against
common-table chemistries -- an order of magnitude larger -- would make every such row read
as unusually safe. And a registry agent with **no stated DAR is excluded, not given the
corpus mean**, which would seat it at the centre of the comparison on a missing value;
twelve of the registry's 34 conventional conjugates have no DAR in any source, so 22
reference chemistries remain -- and five of those 22 are absent from the 16-agent fit, so
their rates are out-of-corpus predictions exactly as the queried design's is. Registry and
not corpus, which is the consistent footing and which the field now says.

It is also not a comparison against what those agents were *observed* to do. The posterior
integrates out the per-agent effect, so an agent's fitted rate cannot be recovered from it,
and the observed rates are censored at each trial's reporting cut, which leaves "higher
than" undefined for a large share of cells. Model against model is the claim the available
quantities support, and the field says so in its own `basis` string.

**The first thing it did was recover a boxed warning.** For a trastuzumab-deruxtecan-shaped
design -- DXd on GGFG at DAR 8 -- queried for a patient with interstitial lung disease:

| axis | band basis | band | ordinal |
|---|---|---|---|
| gastrointestinal | common | high | #3 of 23 |
| **pulmonary** | **serious** | **high** | **#1 of 23** |
| hepatic | common | moderate | #11 of 23 |
| neurologic | common | moderate | #14 of 23 |

Highest predicted serious pulmonary rate of any chemistry in the registry, which is
trastuzumab deruxtecan's boxed interstitial-lung-disease warning. The band alone said
`high`; the ordinal says *how* high, and on this axis there is nothing above it.

### What the ordinal is worth, which is the next section's number

An ordinal position asserts that the ordering means something, so it inherits whatever
skill the across-agent ranking has -- and that is the quantity section 5f measures. It is
the one positive result in this report and it is weak: after removing the reporting
conditions from both series, the mean per-axis Spearman correlation between predicted and
observed across-agent rankings is **+0.17, 95% CI [+0.03, +0.32], permutation p = 0.005**,
and the unadjusted estimate is +0.10 with an interval that includes zero.

So the comparator is the product's most readable field and it rests on a correlation of
about 0.17. That is enough to prefer it to a bare rate, which carries no comparison at all,
and not enough to treat a one-place difference as real. The interface prints the denominator
beside every rank for exactly that reason, and the two cases below are both extremes --
first and nineteenth of twenty-three -- rather than fine distinctions.

**The second thing it did was make a proposal's weak point legible.** For the renal and
pulmonary profile the leading proposal is DGN549 on SMCC, and its hepatic axis is **#1 of
23** -- the worst chemistry in the registry for the liver. The interface already warned that
hepatic was in the high band and unweighted, because the patient named no liver condition.
The ordinal turns that warning into a number. Conversely its haematologic axis bands `high`
at **#19 of 23**: every chemistry is high on that organ, and this chemistry is better than
eighteen of the twenty-two alternatives. A band cannot say either of those things.

## 5f. The one positive signal disappeared when the corpus grew, which settles it

This section used to be the exception. On the 16-agent corpus the across-agent organ
ranking, with between-agent reporting conditions removed, came out at rho **+0.1332** with
a permutation p of **0.025** -- and because a constant per-axis predictor cannot score on
this metric by construction, beating chance was beating the baseline.

Rebuilding the registry corpus against the current agent list took it to 22 agents. The
same estimator now gives rho **+0.0073**, bootstrap over axes [-0.1791, +0.1753],
permutation p **0.4595**:

| variant | 16 agents | 22 agents |
|---|---|---|
| unadjusted | +0.0966 | **-0.0152** |
| adjusted, within-trial blind (headline) | +0.1332, p = 0.025 | **+0.0073, p = 0.4595** |
| adjusted, joint coefficients | +0.1729, p = 0.005 | +0.0590, p = 0.1648 |
| adjusted, design-blind coefficients | +0.1013, p = 0.068 | -0.0042, p = 0.5298 |

**Six more agents did not sharpen the effect; they erased it.** A real correlation gains
precision as n grows -- the bootstrap interval should narrow around a stable centre. This
one moved its centre to zero and kept its width, which is what a sample-size artefact does.
And the six agents arrived from ClinicalTrials.gov records that were already on disk, so
there is no reporting-selection story to explain it away: they are the same kind of data as
the sixteen.

So the report has no positive result, and that is a cleaner position than one marginal
result reported with caveats. The project's own best demonstration of why a p of 0.025 on
sixteen units is not a finding is that this one did not survive going to twenty-two. The
section is kept in full below, because the measurement problem it starts from is real and
the adjustment it builds is the right one -- the conclusion is what changed.

The artefact states its own verdict now, computed from its numbers rather than written
beside them. The previous version carried the sentence "beats chance at p = 0.025" in a
`reading` field, and that sentence survived the corpus change intact: a stale conclusion
reads as a finding in a way a stale number does not.

### The measurement problem it starts from

The across-agent metric ranks the agents by predicted and by observed rate within one
organ axis, and correlates. It is the comparison the product actually makes, and unlike
the within-arm metric a constant per-axis predictor has no discriminative power on it by
construction.

But the agents were studied under conditions that differ more than the effect being
measured:

| reporting condition | range across agents | logit impact |
|---|---|---|
| combination fraction | 0.00 to 0.96 | ~0.19 |
| reporting threshold | -2.25 to +0.75 | ~0.10 |
| trial size | -0.44 to +0.57 | ~0.04 |

Trastuzumab emtansine's arms are 96% combination; six agents have none. Against a tubulin
mechanism effect of sd 0.278, roughly 0.33 logit of the between-agent spread is study
design rather than chemistry. So the observed ranking is partly a ranking of how each drug
happened to be tested.

### Removing it from both series

The adjustment subtracts the reporting contribution from the predicted and the observed
series alike, leaving each agent's profile at a common reference. The direction was not
assumed: a shared artefact would have inflated the correlation, and removing it would then
have lowered the result.

| adjustment | b_combo | mean rho | 95% CI (axis bootstrap) | permutation p |
|---|---|---|---|---|
| unadjusted | 0.0000 | +0.0966 | [-0.0632, +0.2586] | — |
| adjusted design blind coefficients | 0.0319 | +0.1013 | [-0.0544, +0.2572] | 0.0683 |
| adjusted within trial blind | 0.0482 | +0.1332 | [-0.0189, +0.2903] | 0.0250 |
| adjusted joint coefficients | 0.1950 | +0.1729 | [+0.0319, +0.3156] | 0.0050 |

The headline is the third row -- the combination effect estimated **within trials and
design-blind**, from trial fixed effects plus the covariate and nothing about chemistry.
It gives mean Spearman +0.1332 at **p = 0.0250** by permutation.

### Why this is suggestive and not a result

1. The result depends on the adjustment: unadjusted the mean is +0.0966 with an interval spanning zero.
2. b_combo spans 0.032 to 0.195 across three estimators, and the headline sits between them at 0.048.
3. b_combo is identified within trials from only 6 trials and 20 arms.
4. b_thresh has zero within-trial variance and is therefore not identifiable except between trials, where it is confounded; the headline estimator sets it to zero rather than using a confounded value.
5. The permutation test and the bootstrap over axes disagree for the headline estimator: p = 0.025 against an interval that includes zero. The per-axis correlations are heterogeneous, so the mean is not reliably positive under axis resampling.

The two tests disagree for a reason worth stating. The permutation shuffles agent labels
within each axis, which preserves the dependence between axes and asks the right question
-- is the model's agent ranking better than a random one. The bootstrap resamples axes,
which assumes they are independent when one agent's organs covary, and it is telling us
something different: the per-axis correlations are heterogeneous enough that the mean is
not reliably positive if you had drawn a different set of organs.

Both readings are legitimate and they are reported together. What would settle it is more
agents, not more analysis: with 22 agents a per-axis Spearman has a standard error near
0.28, so only the mean over axes is usable at all.

### What it does not change

The within-arm result stands. Correcting the reporting conditions does nothing for it,
because there the model and the baseline are compared on the same arm under the same
conditions, and the failure is the ratio in section 4.0: where the evidence is good the
design effects are too small to move the organ ranking.

## 5g. The corpus was agent-limited, and the limit turned out to be measurable

Section 5f ends by saying the one positive signal needs more agents rather than more
analysis. That was a verdict on the data, not a plan, because the plan's own estimate --
about 54 ADCs have published a per-organ safety table with a denominator -- had never been
checked. It has now been checked, by building the extraction path and then exhausting three
routes to new agents.

### Why arms are not agents, measured in one table

| stage | agents | arms in the grid | cells | cells that identify a design coefficient | observed | viable LOMO folds |
|---|---|---|---|---|---|---|
| ClinicalTrials.gov, the original 18-agent list | 16 | 285 | 3,990 | 224 | 86.3% | 2 |
| ClinicalTrials.gov, the literature's agent list | **22** | 299 | 4,186 | **308** | 86.6% | **3** |
| + literature arms for agents already present | 25 | 459 | 6,426 | 350 | 67.9% | 3 |
| + literature agents | **32** | 482 | 6,748 | 448 | 66.9% | 3 |

**The second row was not in this report and it is where most of the value is.** Attribution
matches a ClinicalTrials.gov event group against the names and aliases in
`conf/adc_registry.yaml`, and 17 of that file's 35 agents were found by the literature's
payload-linker stem sweep. So the first stage had been labelled "ClinicalTrials.gov only"
while being computed with a literature-derived agent list -- and separating the two shows
that **naming the agents bought 6 agents and 84 identifying cells out of data that was
already on disk, at no cost to the observed share**, 86.3% to 86.6%, because nothing about
the reporting changed.

Against that, extracting the arms bought 42 more identifying cells and took the observed
share from 86.6% to 67.9%. Two contributions were being reported as one, and they are
opposite in kind: the first is free of the literature's reporting selection entirely, and
the second is what section 5g's negative ablation result is about.

The three corpora nest exactly -- 312 arms added at the first step and 102 at the second,
with **zero** arms dropped at either -- so a difference between fits is attributable to
what was added. That is checked in `artifacts/corpus_ablation.json`, not assumed.

The arms column is the grid and not the corpus, and the two differ by 191 arms at the
literature-arms step. Six filters stand between them: an attributable agent, a denominator of at least 30,
a conventional conjugate, publishing the table in question, reporting the any-grade outcome
the registry's `otherEvents` reports, and naming one agent rather than a class of them. The
fifth is the expensive one: 154 of the 414 literature arms report a grade-restricted tail, a
death count, a serious-event column or a clinical action, and one agent -- naratuximab
emtansine -- has no any-grade column anywhere, which is why the agent count here is 31 and
not the 32 the discovery sweep found. The artefact reports both counts side by side,
because reading a corpus figure off a grid column is how this table gets misread. All three
stages are derived from the one merged corpus, which makes the nesting true by construction;
the middle stage used to be a separate directory on disk, and it went stale the moment the
merge gained a column.

Read the identifying-cells column against the arms column. Naming the agents adds 14 grid
arms and buys **84** identifying cells. Extracting 351 corpus arms of agents already present
buys **42**. The 75 arms belonging to agents the extraction added buy **98**. So the cheapest
identification in the project came from reading a name off a paper, and the most expensive
from reading a table off one. Section 2
states the reason abstractly; this is it arithmetically. Design features are agent-level
constants, so arms of an agent already in the corpus are additional observations of its
trial populations and *no* additional observation of its chemistry.

The 14 is not zero only because one agent crossed the 30-patient floor on the strength of
its literature arms.

### The first ablation result is negative, and it says why

Adding 312 literature arms for agents already in the corpus made the model *worse* against
its own baseline, on both metrics:

| | ClinicalTrials.gov only | + literature arms |
|---|---|---|
| leave-one-agent-out macro AUC | 0.8036 | 0.7213 |
| better baseline on the same folds | 0.8458 | 0.7994 |
| **delta** | **-0.0422** | **-0.0782** |
| across-agent mean rho | +0.097 [-0.064, +0.263] | -0.070 [-0.189, +0.065] |

This is what the ablation was built to detect, and the cell composition says what happened:

| | observed | censored |
|---|---|---|
| ClinicalTrials.gov only | 86.2% | 11.8% |
| + literature arms | 67.5% | **28.7%** |
| + literature agents | 66.1% | 30.4% |

**A paper's adverse-event table is sparse in a way a registry record is not.** A registry
arm reports most of its organs; a paper reports a handful, so the other ten or eleven axes
arrive as censored cells. Of the 2,058 cells the literature arms add, about 1,290 are
censored -- and for 83% of paper arms the censoring boundary is an *upper* bound derived
from the minimum printed rate rather than a stated cut. So the model is told "this organ's
rate is below X" with X too large, for thousands of cells at once. Section 5g's threshold
discussion called that conservative because it widens intervals; at this volume it is not
conservative, it is wrong information in bulk.

That makes the explicit-threshold subset the decisive experiment rather than a robustness
check, and `make pmc-merge-explicit` already builds it: 52 arms over 7 agents, every one
with a cut the caption stated. If the degradation is the bounded threshold, it should not
appear there.

It also sharpens what the 32-agent fit can show. If more agents improve things despite
carrying the same sparsity, the agents are doing real work; if they do not, the literature
path needs the threshold handled differently before its arms belong in the corpus at all.

### The expansion buys one table and not the other, and a bug was hiding it

The literature expansion was measured on the common-events table, where it takes the corpus
from 22 agents to 32. On the serious table it buys **one**: 23 agents against the
registry's 22. 405 of the 414 literature arms publish no serious-adverse-event table at
all -- neither a denominator nor a single row -- so the serious fit sees 9 new arms.

| table | agents | gained from the literature | arms | cells |
|---|---|---|---|---|
| otherEvents | **32** | **+10** | 482 | 6,748 |
| seriousEvents | **23** | **+1** | 304 | 4,256 |

This was invisible until it was looked for, because the corpus builder was manufacturing the
missing arms. An arm's denominator is stored per table, but the arm-level `n_at_risk` is the
*maximum* of the two, and the grid builder fell back to it whenever the per-table value was
absent. So an arm that published only a common-events table still carried a positive
denominator when the serious grid was built, with every axis missing: **4,256 cells, none of
them observed,** each asserting either a zero or a censoring bound for a table the paper
never printed. The serious grid looked like 8,316 cells over 594 arms. It was 4,060 over
290, and the padding was all fabrication.

The consequence is not only that a bug is gone. **The serious table cannot serve as the
robustness check for the expanded corpus**, which is the role section 5b gives it and the
role it still plays for the registry. Where the two tables disagree on an expanded-corpus
agent, there is usually no serious evidence for that agent to disagree with. Section 5c's
finding -- that the two tables rank organs differently, and that the serious table recovers
the boxed warnings -- was measured on the registry and stands there; it does not extend to
the 10 agents the literature's arms added.

A second, smaller correction came out of the same place. ClinicalTrials.gov `seriousEvents`
really is complete -- the registry lists every serious event with no frequency cut -- so an
absent organ there is a true zero, and the builder encoded that. But a paper's serious table
is selected like any other table, and the completeness branch fired before the
selected-absence check, so the 9 literature arms that *do* publish one were asserting zeros
for about 81 axes they never reported. A zero is a stronger false statement than a bound, so
completeness is now claimed only for arms whose cut is not merely derived from their own
printed rates. Registry arms are never in that category, and their rows are unchanged.

### The third fold was free, and this report credited it to the wrong thing

`dna_crosslink` crosses the three-agent floor -- 2 agents to 4 -- so the headline validation
is leave-one-mechanism-out over tubulin, topoisomerase-I and DNA crosslinking rather than
the first two alone. This report said the literature arms bought that. They did not:

| stage | dna_crosslink agents | arms | viable |
|---|---|---|---|
| ClinicalTrials.gov, original agent list | 2 | 7 | no |
| ClinicalTrials.gov, literature's agent list | **4** | 10 | **yes** |
| + literature arms | 4 | 14 | yes |
| + literature agents | 5 | 16 | yes |

The fold opens at the **agent-list** stage, on ClinicalTrials.gov records that were already
on disk and unattributable only because nothing had named the drug. Not one paper arm is
involved. The literature arms later add a fifth agent to the mechanism, by which point the
fold was already viable.

The plan predicted the third fold at N=32 and predicted the rest correctly: `dna_cleave`
stays at 2 agents and `dna_alkyl` at 2, because two calicheamicin ADCs and two duocarmycin
ADCs are all that have published a usable table anywhere. Those folds are not waiting on
more work, and the project does not claim them.

### The ceiling is 32, not 54

Three routes, each measured before any design feature was curated -- which is the only
reason the curation cost what it did.

| route | agents found | with a machine-readable safety table |
|---|---|---|
| INN search over 41 payload-linker stems | 23 | 16 |
| deeper re-search of the 5 stems that hit the fetch cap | 5 | **0** |
| code-name search for the 10 that had failed | 10 retried | 2 |

The second row is the informative one. Those five are all vedotins, found only because the
first sweep truncated; between them they have 7 open-access articles and 4 adverse-event
tables, none of which parses to a count with a denominator. Curating them would have been
roughly 50 hand-sourced field values for nothing.

So the plan's figure of about 54 is not supported. The agents exist -- over 370 ADCs have
entered the clinic -- but the ones outside this corpus have not published a per-organ table
with a denominator, and three independent search routes agree on that.

### The discovery method, and why it should be unbiased

An ADC's international nonproprietary name is two words: an antibody stem, then a
payload-linker stem coined for the conjugate chemistry. `vedotin` is MMAE on a cleavable
dipeptide, `deruxtecan` is DXd on a GGFG tetrapeptide, `tesirine` is a pyrrolobenzodiazepine
dimer. That vocabulary is closed, so searching each stem finds every agent built on that
chemistry whether or not anyone has reviewed it.

The first method tried was biased by construction and is recorded because the bias is easy
to repeat. Harvesting ADC names from the 1,319 articles already fetched found 18
non-registry agents -- but that corpus was assembled by searching for the 18 registry
agents, so it sees another ADC only when a paper mentions it beside one of those. Six of
the 18 were misspellings of registry drugs.

Two stems were removed after the deep sweep: `doxorubicin` and `paclitaxel` are free-drug
names rather than conjugate stems, so "<antibody> <stem>" matches co-administration with
the punctuation lost. They returned "trastuzumab doxorubicin" and "bevacizumab paclitaxel",
neither of which is an ADC.

### Code names had to come from the data

Ten agents yielded nothing from an INN-only search, and several of them are drugs whose
primary reports use a code name and never the INN. Recalling the mapping was not an option:
a wrong code name misattributes every row of an agent, which is the failure mode this
project measures at a 75% false-positive rate for loose attribution. So code names were
harvested only from papers whose *titles* already name the INN, which makes the paper itself
the evidence for the mapping. Searching them alongside the INN roughly doubled the hit count
for several agents and recovered two.

## 5h. The comorbidity layer, and the holdout it unlocks

The comorbidity registry maps 41 conditions to organ axes and a severity, both assigned by
hand. The assignment was defensible and it had one structural problem: the hands that made
it were reading trial exclusion criteria, so recovering exclusion criteria from it is
circular. The only non-circular holdout left was about 28 cells of FDA label impairment
text.

A MONDO `is_a` closure has no such problem. MONDO was curated for disease classification
rather than for this project and touches no exclusion text, so the same recovery test
becomes legitimate -- over 3,762 trials instead of 28 cells. That is the whole argument for
building the layer, and it is the reason to build it even where it is not expected to beat
the hand map.

### First, it audited the registry, and the registry failed

The plan required all 40 MONDO identifiers to be pinned by hand into a checked-in CSV, with
no runtime resolution, because a search API had silently mis-resolved 3 of 36 test
conditions -- returning `brain small vessel disease 1` for `ocular surface disease`, and
`familial long QT syndrome` for `QT prolongation`. The pinning was done. It did not help:
**8 of 41 pins named an unrelated disease.**

| condition | pinned identifier named | should name |
|---|---|---|
| chronic kidney disease, stage 3 | cardiomyopathy | chronic kidney disease |
| chronic kidney disease, stage 4-5 | cardiomyopathy | chronic kidney disease |
| dry eye disease | idiopathic cardiomyopathy | dry eye syndrome |
| interstitial lung disease | cervix squamous papilloma | interstitial lung disease |
| immune thrombocytopenia | renal tubular transport disease | thrombocytopenia due to immune destruction |
| chronic anaemia | familial hyperlipidemia | anemia |
| QT prolongation | tick-borne encephalitis | nothing -- see below |
| prior SJS/TEN | secondary intestinal lymphangiectasia | Stevens-Johnson syndrome |

Three further pins were absent from the ontology snapshot and one was an HPO term rather
than a MONDO one. Nothing had broken, only because nothing read the column: this derivation
is its first consumer and it failed on contact. Hand-pinning is not a substitute for
checking what the pin names.

Twelve identifiers were corrected, each verified twice -- the term's own name matches the
condition, and the organ its closure derives matches the hand-assigned organ. The audit now
reports zero wrong and zero absent.

QT prolongation stays on the ontology root deliberately. MONDO has `long QT syndrome`, but
that is a hereditary channelopathy while the trial criterion is a drug-induced ECG finding
-- the exact mis-resolution the plan flagged. Five other conditions share the root because
a prior anthracycline, chest radiation, corneal surgery, transplant or bowel resection is
not a disease, and no disease ontology can place one.

### The holdout: 0.666 non-circularly, against 0.750 circularly

For each condition, find the trials whose eligibility text names it, and ask whether the
organ axes its MONDO closure derives are the axes those trials express concern about.

| mapping | AUROC | permutation p |
|---|---|---|
| MONDO-derived (non-circular) | **0.666** | **0.0005** |
| hand-assigned (circular, reported as a ceiling) | 0.750 | 0.0005 |

The permutation shuffles axis assignments *within* each condition, holding the number
assigned fixed, because the eleven cells of one condition are not independent -- their
shares sum to one -- so a standard error over 286 cells would treat 26 conditions as 286.
The null sits at 0.493 with a 95th percentile of 0.571.

The hand map wins by 0.085, which bounds what its circularity buys. A small gap is the
informative outcome: the hand map is not living off the leak.

### Two corrections without which the number is worthless

**Protocol verbosity.** Any protocol detailed enough to name a comorbidity sets thresholds
on several organs, so raw rates come out enriched on every axis at once. The signature is
both medians positive, with `ocular` the top-enriched axis for both cirrhosis and chronic
kidney disease. Normalising to each trial's share of concern makes protocol length cancel,
putting unassigned axes at -0.033 and raising the AUROC from 0.605 to 0.666. This is the reporting-channel artifact the plan
names for FAERS, in a different dataset.

**Shared regular expressions.** The organ-concern rules were also written by reading
exclusion criteria, and several of them *are* condition names -- `cirrhosis` is a hepatic
rule, `peripheral neuropath` a neurologic one, `inflammatory bowel|crohn` and `pancreatitis`
gastrointestinal ones, `hepatitis [bc]`, `hiv` and `autoimmune` infectious ones. For those
seven conditions, "this trial mentions the condition" and "this trial flags the organ" are
the same regex and the test measures nothing. Each condition's own matching patterns are
removed before its trials are flagged, which leaves bilirubin, AST/ALT and Child-Pugh
standing for cirrhosis on the hepatic axis.

### What it does and does not establish

Fifteen of 41 conditions are excluded, each with a reason. Six derive no organ because
they are prior exposures rather than diseases. A guard drops any condition whose matcher
hits more than a quarter of the corpus, which is how the root-pinned six announced
themselves: the root's synonyms were reaching their matchers, each hit about 60% of trials,
and their enrichments came out identical to three decimal places.

MONDO is an audit of the hand map, not a replacement for it. Of the 21 axes it adds, **12
are hepatic conditions acquiring `gastrointestinal` and `metabolic_endocrine`** through two
ancestors, because MONDO files the liver in the digestive and endocrine systems. That is
upper-ontology placement, not a claim that a cirrhotic patient faces elevated
gastrointestinal adverse-event risk, and twelve axes from one placement are one piece of
evidence rather than twelve. The plan's "multiple parents are a feature" is half right: a
feature when it reflects multi-organ involvement, since hepatitis B is genuinely hepatic
and immune, and an artifact when it reflects where a curator filed an organ.

This validates the organ mapping. The severity weights are still hand-assigned and
untested, and the disease-disease coupling term is unbuilt -- for a reason the measurements
supply rather than for lack of time.

### Why the coupling term is not built

The plan's third component is `Coupling(a,c)`, a disease-disease term from FAERS indication
co-occurrence, with the lift between two conditions standing in for one amplifying the
other's organ risk. Two measurements argue against spending days on it.

The plan's own FAERS figures carry a channel confound it names: the lifts are 6.41 for
hypertension with hypothyroidism and 4.35 for heart failure with renal failure, but every
rheumatoid pair *shrinks* -- hypertension with rheumatoid arthritis comes out at 0.68 --
because rheumatoid reports arrive through biologic safety programmes that do not enumerate
concomitant cardiometabolic drugs. A term whose sign depends on which safety programme
filed the report is not measuring disease biology.

The second is new here. Section 5i found that every cross-organ effect the FDA labels
document is renal and raises risk elsewhere or systemically, which is the signature of a
clearance effect. **Disease co-occurrence cannot represent that.** Renal impairment raises
deruxtecan ILD because clearance falls and exposure rises, not because kidney disease and
interstitial lung disease co-occur in patients. So the coupling term would add a quantity
with a known reporting artefact, modelling a mechanism the only available evidence says is
the wrong one.

What the evidence would support is a clearance term -- hepatic and renal impairment raising
exposure, and therefore every axis, by an amount depending on the payload's elimination
route. That is a different model from the one the plan specifies, and 18 ordinal cells and
three sentences are not enough to fit it. Both are stated rather than built.

## 5i. The comorbidity layer's primary validation was misspecified

The plan names one validation as the single thing to build for the comorbidity layer: the
FDA label hepatic and renal impairment sections, coded as a four-level ordinal -- no
adjustment, monitor, avoid, not established -- and correlated against the model's organ
ranking. Its appeal is real. The text is graded rather than boilerplate, a regulator
adjudicated it, and it never saw this corpus.

It was built. The correlation is null: Spearman rho -0.047 at p 0.85 over 18 cells, and
+0.112 at p 0.77 with `not_established` dropped.

### The null is the right answer, and the same text says why

A label's impairment section argues from **clearance**, not from organ-specific event
rates. Measured on the same sections, pharmacokinetic language -- exposure, clearance, AUC,
unconjugated payload -- outnumbers organ-event language about six to one, and the ratio
holds whether the window is the subsection alone (6 cells to 1) or 900 characters around
the phrase (10 to 2).

| what the impairment section argues from | cells |
|---|---|
| pharmacokinetics (exposure, clearance) | 6 |
| systemic adverse reactions | 3 |
| an organ-specific event | 1 |

ADCETRIS tells you to avoid moderate hepatic impairment because "MMAE **exposure** and
adverse reactions are increased". Inotuzumab ozogamicin's section opens "based on a
population pharmacokinetic analysis, the **clearance** of inotuzumab ozogamicin ...". The
model predicts how often a given organ has an event. These are different quantities, and
correlating them was never the right test -- which is a finding about the plan rather than
about the model, and the reason this section exists instead of a reported null.

### What the labels do support, and it points somewhere else

Three cross-organ sentences, and **every one of them is renal**:

- trastuzumab deruxtecan: "A higher incidence of Grade 1 and 2 ILD/pneumonitis has been
  observed in patients with moderate renal impairment." (the sentence the plan quotes)
- datopotamab deruxtecan: "Monitor patients with renal impairment for increased adverse
  reactions, including respiratory reactions."
- pivekimab sunirine: a higher incidence of Grade >=3 adverse events, serious adverse
  events and dose delays in moderate renal impairment.

All renal, all raising risk in a *different* organ or systemically. That is the signature of
a clearance effect, not of tissue overlap.

And it has a consequence the plan did not anticipate. Its coupling term is built from MONDO
tissue overlap and FAERS disease co-occurrence, and **neither mechanism can produce a
renal-impairment-raises-pulmonary-ILD link**, because that link is pharmacokinetic. The one
cross-organ effect the labels document is not of the kind the layer models. A layer that
modelled clearance organs -- hepatic and renal impairment raising systemic exposure, and
therefore every axis, by an amount depending on the payload's elimination route -- would fit
this evidence better. It is not built, because 18 ordinal cells and three sentences are not
enough to fit it on, and saying so is more useful than fitting it anyway.

### The severity column has no validation path at all

The comorbidity layer has two hand-assigned columns, and this round separated them. The
organ mapping now has an independent MONDO derivation that recovers exclusion concern at
AUROC 0.666. The severity column has nothing of the kind, and the reason is in its own
documentation: **34 of 41 severity values cite trial exclusion criteria as their basis** --
"Child-Pugh B/C excluded in ADC protocols", "HBV exclusion present in 54% of ADC
protocols". One value of 41 cites a label.

So severity cannot be validated against exclusion criteria, because it was assigned from
them, and the plan's designated alternative has just been shown to measure clearance rather
than organ event rates. Both paths are closed.

The plan's own design decision is what makes that tolerable, and it was made for a
different reason. Severity enters as a displayed weight, `w_o = 1 + lambda * severity_o`,
never as a logit -- the plan's words are that a term with zero training rows must not drive
a core function and that the weight must be shown on screen. An unvalidated number
presented as a transparent preference is honest; the same number presented as a prediction
would not be. `/assess` reports it as an `elicited_prior` driver and `/propose` as
`weight_applied` on each axis, and tests now fail if either ever labels it `model`.

Two things follow. The scale is coarser than it looks -- 17 of 41 values sit at exactly 1.0
and 13 at 0.6, so it is effectively three levels and the second decimal is not a
measurement. And Elixhauser comorbidity weights, which the plan proposed as the citable
replacement, would not fix this: they are calibrated to all-cause in-hospital mortality,
which is further from "how much should this organ's risk be up-weighted for an outpatient
receiving an ADC" than the label text was, and with the label ordinal misspecified there
would be no way to check whether the substitution helped. Importing a mis-calibrated
external weight with no validation path is worse than a hand-assigned one that says where
it came from.

### One parser bug the plan's own numbers caught

The section finder terminated each organ's block with a lookahead on a newline, after the
newlines had been collapsed by whitespace normalisation, so the lookahead could never fire
and nine of fourteen renal sections came back as absent. The plan's measured figure --
renal text present in 13 of 14 labels -- is what exposed it. Without that number, a parser
silently dropping twelve of twenty-eight cells would have been indistinguishable from a thin
corpus, and the null would have been reported as an underpowered test rather than a
misspecified one.

After the fix, nine of ten remaining gaps are genuine label silence: sacituzumab govitecan
and polatuzumab vedotin mention renal zero times in Use in Specific Populations.

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
6. **Payload-identity interactions are unreachable at any corpus size, and the two coarser
   levels are not** (section 4.3). The plan's claim was that the identification ratio stays
   flat at every granularity as the corpus grows -- 2.12, 2.91, 2.84 over 17, 32 and 54
   agents -- and two of those rows were projections of a 54-agent corpus that was measured
   not to exist and of a payload vocabulary that grew faster than the real one. Measured the
   plan's own way, from 16 agents to 32: payload identity 1.78 to 2.13 (**1.20x**, 10 levels
   to 16, and *backwards* at the last step, 2.50 to 2.13, because the agents the extraction
   added brought five new payloads), family 2.67 to 4.57 (1.71x, 7 to 8), mechanism 4.00 to
   **8.00** (2.00x, 5 to 5, the taxonomy frozen before extraction). So the receding horizon
   is real and specific to the payload level -- and the level the model actually uses now
   reaches the plan's 8:1 floor exactly, which is better than this report previously said.
7. **Fc silencing is not a design lever.** Three primary papers contradict each other on
   the mechanism, no approved ADC uses it, and no training arm carries it. It is not
   offered as a design slot.
8. **Membrane permeability runs the wrong way for ocular toxicity.** MMAF is the least
   permeable auristatin and has the worst keratopathy; the mechanism is corneal
   macropinocytosis, not diffusion.
9. **Gene-set overlap does not beat a disease ontology.** Jaccard over Open Targets gene
   sets predicts same-organ pairs at AUC 0.748, a task MONDO's `is_a` closure answers
   exactly and for free.
10. **The literature corpus's ceiling is 32 agents, not the ~54 the plan estimated,** and
    31 of those 32 publish an any-grade column, which is what the forward model can fit.
    Three independent search routes agree. The decisive one: re-searching the five
    payload-linker stems that had hit the fetch cap found 5 further agents and **0** of
    them has a parseable safety table, so the next tier of the literature yields nothing.
11. **Naming an agent is worth more than extracting its arms, and this report credited the
    wrong one.** Attribution matches a ClinicalTrials.gov event group against the names in
    `conf/adc_registry.yaml`, and 17 of its 35 agents came from the literature's
    payload-linker stem sweep -- so the stage this report called "ClinicalTrials.gov only"
    was already using a literature-derived agent list. Separated: **naming the agents bought
    6 agents and 84 identifying cells out of registry data already on disk, at no cost to
    the observed share** (86.3% to 86.6%), and opened the third mechanism fold.
    Extracting 351 arms of agents already present bought 42 identifying cells and took the
    observed share to 67.9%. The two contributions are opposite in kind -- the first carries
    none of the literature's reporting selection -- and were being reported as one. Section
    5g.
12. **Searching for drug names inside a corpus assembled by searching for drug names is
    circular.** Harvesting ADC names from the 1,319 articles fetched for the 18 registry
    agents found 18 "new" agents, of which six were misspellings of registry drugs and the
    rest were visible only because they appear beside a registry agent. The payload-linker
    stem vocabulary gives an unbiased handle; the corpus does not.
13. **A reporting threshold is a property of row selection, not of cell values.** Pooling
    every cell of a table and taking the minimum printed rate manufactures a contradiction
    with the stated cut in any table that breaks events out by grade -- which is most of
    them. It demoted 44 of the 45 tables whose caption stated a cut, and put the measured
    explicit-threshold rate at 0.6% against the plan's 19.3%. Reading one rate per row
    fixes it.
14. **An inferred denominator is 88.3% precise and that is not good enough.** A table's
    `n (%)` cells identify their own denominator, and on the 162 columns that state one the
    inference produced a value for 143 and got 19 wrong -- mostly by one or two patients,
    which no downstream check can see, because the arithmetic gate would re-derive both the
    count and the percentage from the same wrong N. Requiring the integer to appear
    independently elsewhere in the article gave 124 of 124 correct and rejected all 19.
15. **Hand-pinning an ontology identifier does not make it right.** The plan required all
    40 MONDO identifiers to be pinned by hand rather than resolved at runtime, because a
    search API had silently mis-resolved 3 of 36 test conditions. The pinning was done and
    **8 of 41 pins named an unrelated disease** -- chronic kidney disease pinned to
    cardiomyopathy, interstitial lung disease to cervix squamous papilloma. A higher error
    rate than the API it was protecting against. Nothing had broken only because nothing
    read the column until the MONDO derivation became its first consumer. Section 5h.
16. **The number guard verifies about 70% of the report tightly and almost nothing for 6%,
    and now says which.** "Every figure traces to an artefact" means the figure's string
    appears somewhere in a pool of 19,449 values, and in a pool that dense a three-decimal
    number appears by coincidence most of the time -- the guard's own measured false-pass
    rate on deliberately fabricated figures is 100% at two decimals, 88% at three and 27%
    at four. So it now reports how many pool entries each passing figure matches: **28.7%
    match exactly one** and are tightly pinned, 41.8% match two to five, 18.7% match six to
    fifty, and **5.9% match more than fifty** and are checked by nothing at all. The worst
    are figures of the form `1.00`, which match 15,688 pool entries -- real values from real
    artefacts that this method cannot verify, because every probability of one and every
    ratio of one looks identical. The rate also degrades as the project measures more: the
    pool grew from 15,184 values to 20,453 over this round and the three-decimal false-pass
    rate went 75% to 91%, which is the opposite of the direction a guard should move. That is a limit of existence-checking rather than a defect
    in those figures, and closing it would require each figure to cite its own artefact and
    key path.

    The same inspection found that the guard had never looked at a figure ending a
    sentence. Its figure pattern excluded a following period, so the most common position
    for a number in prose was skipped outright -- 18 figures, including `0.0345`, `0.2120`
    and `3.872`. All 18 trace to artefacts now that they are read, so nothing was wrong in
    the report; the guard had simply been checking 390 of 408 figures while reporting that
    every figure traced.
17. **The comorbidity layer's designated primary validation was misspecified.** The plan
    named the FDA label hepatic and renal impairment sections as the single validation to
    build; the correlation against the model's organ ranking is null at rho -0.047. The
    reason is in the same text: those sections argue from clearance, with pharmacokinetic
    language outnumbering organ-event language about six to one, while the model predicts
    organ-specific event rates. Section 5i.
18. **The one cross-organ effect the labels document is pharmacokinetic, so the planned
    coupling term cannot capture it.** All three cross-organ sentences are renal, raising
    risk in a different organ or systemically -- the signature of a clearance effect.
    Neither MONDO tissue overlap nor FAERS disease co-occurrence, the two mechanisms the
    coupling term is built from, can produce a renal-impairment-raises-pulmonary-ILD link.
19. **A low row-mapping rate looked like a vocabulary problem and was not.** 59.3% of
    adverse-event rows missed the preferred-term dictionary, and the misses were dominated
    not by unknown medical terms but by labels like `1`, `Yes`, `Grade 3`, `Female` and
    `+` -- the stub column of a cross-tab or an over-caught baseline table. Separating
    them moved the mapping rate from 40.7% to 53.7%, against the plan's 50.5%, without a
    single new dictionary entry.
20. **The corpus expansion buys one event table and not the other.** The literature arms
    take the common-events table from 22 agents to 32, and the serious table from 22 to
    **23**: 405 of 414 literature arms publish no serious-adverse-event table at all. This
    was hidden by a builder that fell back to the arm's other-table denominator, padding
    the serious grid with 4,256 cells -- none observed -- that asserted a zero or a bound
    for a table the paper never printed. The serious table remains the robustness check for
    the registry corpus and cannot be one for the expanded corpus.
21. **The product cannot rank its own proposals, in any of 192 queries.** A ranked list is
    printed only where the leader beats the runner-up on 80% of paired posterior draws. The
    leader wins a median 52.2% across 24 targets by 8 comorbidity profiles, and **0 of 192**
    queries clear the bar; the head tie group holds a median 73% of the constraint-passing
    candidates. The output is a non-dominated set, not a ranking, and the interface says so.
22. **The ranking layer's comparison was inverted where it mattered most, and no test
    noticed.** `P(a < b)` reads an exact tie as a loss, and exact ties are the normal case
    because the model has no term separating DM1 from DM4; the two were printed as rank 1
    and rank 2 while pairs genuinely overlapping at P = 0.53 were correctly merged. Grouping
    also chained on adjacent pairs, which is transitive, so with that fixed all 74
    candidates collapsed into one set until membership was anchored on the group's leader.
    And the display took the first six of the ordering, which showed three dominated designs
    while hiding five non-dominated ones. 413 tests passed throughout.
22b. **Six cards showed three payload chemistries, two of them doubled.** With the
    Pareto front selected but ordered by the secondary preference, the displayed designs for
    a HER2 query were `DGN549, DGN549, DM1, DM1, DM4, DM4` -- and DM1 against DM4 is a pair
    this model cannot separate at all -- while MMAE, MMAF and a pyrrolobenzodiazepine went
    unshown despite being non-dominated. Since the ranking does not resolve, the selection
    rule is doing the work the ranking cannot, and it now takes one candidate per payload
    before a second of any.
23. **Four distinct proposals from 192 queries.** The target antigen changes at least one
    risk band in 26% of queries and never changes which designs are proposed; eight
    comorbidity profiles produce four distinct design sets. The payload ordering survives
    every reweighting the comorbidity layer can apply.
24. **The comorbidity profile's influence on the proposal is a function of an arbitrary
    constant, and vanishes for the patients who need it most.** At the shipped weighting
    constant the patient's own at-risk organs carry 19-33% of the objective, and the
    shown set of design options first changes between lambda = 5 and lambda = 50 depending
    on the profile.
    Raising the constant until every profile gets its own answer is choosing a constant to
    produce an appearance, and the dependence is not monotone anyway. The measured case that
    matters: a **four-comorbidity profile receives the same proposal at every lambda from 0
    to 100**, because four at-risk axes out of fourteen return the weighting to near-uniform.
    The layer influences the simplest patient most and the most complex one not at all.

25. **A registry field recorded as unstated was stated three times, and a species label is
    why.** Twelve of 34 conventional conjugates had no drug-to-antibody ratio, and
    tusamitamab ravtansine's entry said the figure appeared nowhere in the fetched corpus.
    Its own population-pharmacokinetic paper gives an average DAR of 3.8, three times --
    and labels its conjugate species `DAR0` through `DAR8`, seven tokens to the one real
    statement, beside the agent's name in the same sentences. Read as the ratio they give
    the agent a DAR of 0, 1 or 8. Searching the 1,471 harvested articles recovers 2 of the 12;
    a third candidate is rejected because its only source is a paper about a different drug.
    The gap is not a search failure: eight agents' ratios are stated in no article on disk,
    and 13 of 468 arms are still fitted at the corpus mean.
26. **A regex guard that never fires is worse than no guard, and this project wrote one.** A
    pattern to bracket the species enumeration -- `DAR1 ... to DAR8` -- failed on the one
    sentence it was written for, because that sentence contains `i.e.` and an abbreviation's
    dot before a space is indistinguishable from a sentence's. The script had reported four
    rejections, so the check looked alive while missing its own motivating case. It was
    deleted rather than patched, and a word-level test does the work. This is the second
    time in this project that a guard passing was mistaken for a guard working; the first
    was a `sed` pattern that never matched and therefore fabricated nothing to detect.

27. **154 of 414 literature arms were reporting a different outcome than the corpus asks
    for.** `otherEvents` on ClinicalTrials.gov is any-grade, all-cause incidence. 142 of the
    paper arms report a single grade or a range of them -- "Grade >=3", "Grade 3-4",
    "Grade 1-2", "Grade 4", "Grade I-II" -- 3 report deaths ("Grade 5"), 1 is a
    serious-event column, 5 report a clinical action per organ ("EV Dose Reduction",
    "Temporary Hold/Delay", "Hospitalization") which is not an incidence at all, and 3 are a
    cross-tab stub or the table's own label column. All were merged in as though they were
    any-grade. The clearest case is a trastuzumab deruxtecan
    arm reporting nausea at **1.4%**, against a median of **67%** across the agent's other
    79 arms. It passed every check the project had: 2/142 is arithmetically consistent, the
    row label maps cleanly, the denominator is stated in its own header, and nothing anywhere
    asked what the column was counting. Setting them aside costs **no agents** -- every
    agent with such an arm also has an any-grade one -- and takes the corpus from 8,232
    cells over 588 arms to 6,552 over 468, with the observed share rising from 59.2% to
    66.1%, and costs one agent: naratuximab emtansine's only table splits the grade scale
    into Grade 1-2, Grade 3 and Grade 4 columns with no any-grade column, so the agent has
    no any-grade evidence at all. Its rate could in principle be reconstructed by summing
    the strata, and is not, because the partition omits grade 5.
28. **The duplicates that were not duplicates are what found it.** Concatenating the three
    snapshots' cell files emitted 277 rows twice, since 25 of the 1,471 articles answer to
    more than one fetch list. 128 were true copies. The other 149 shared the article, table,
    row, parent column header, agent and axis while carrying *different counts* -- which is
    what a grade-stratified table looks like once the grade is dropped from the column
    identity. The corpus was never affected by the copies, because the merge keys
    observations by (arm, axis, kind); the statistics computed per cell were, and
    `pmc_validation.json` sized its rate comparison at 1,372 cells when fewer were distinct.
29. **A column naming a class of agents defeated the attribution gate.** "Novel anti-HER2
    ADCs (n = 73)" is the comparator arm of a paper about trastuzumab emtansine, and every
    check this project had passed it: the title names the agent, no other ADC appears by
    name anywhere in the table, the column carries its own denominator, and the arithmetic
    is consistent. 22 cells were attributed to trastuzumab emtansine, 11 of them any-grade
    and in the corpus. This is the attribution trap measured at a 75% false-positive rate in
    section 5g, arriving through a door the project had already locked twice -- and found by
    asking of the denominators the same question that had just found the outcome mismatch:
    *what population is this?* The rule added is narrow, because the plural has to be a
    plural of agents: "Pooled RDE 5.6 mg/kg (n = 57)" pools dose-expansion cohorts of one
    agent and is a legitimate arm.
30. **The pattern written to find that defect had the defect in it.** The first version of
    the outcome classifier caught only the severe tail and let two of its own target cases
    through: `grade\s*` cannot cross the "s" of "Grades 3-4", and `3\b` fails before the
    letter in "Grade 3n (%)". It also never considered the low grades, and 42 arms carried
    one -- "Grade 1", "Grade 1-2", "Grade 4", "Grade I-II" -- which are no more any-grade
    than the severe tail is. The first pass found 106 arms; a sweep of all 516 column
    headers found 154. The lesson is the same as negative result 26's: a pattern that fires
    is not a pattern that is right, and the only way to tell was to read every header the
    corpus actually contains rather than the ones the pattern was written from.
31. **The same defect one level down is bounded rather than fixed, and the bound is why.**
    A grade restriction usually sits in the column header. It can also sit in the row --
    "CRS, grade >=3", "Keratopathy, grade 3-4" -- and 14 cells carry one. The merge stores an
    axis as the maximum over its rows, matching the registry's "any event in this organ", so
    such a row is dominated whenever the axis also has an any-grade row with a larger count.
    The exposure is what remains: **6 of 2,696 observations**, worst understatement 20% --
    a maximum of 20 against a row sum of 24. Four are belantamab mafodotin's ocular axis,
    the one its label is defined by, and it has 124 observations there. A row-level filter
    would discard "Keratopathy, grade 2" where it is the only keratopathy row, which costs
    a real signal to correct a fifth of four numbers. The bound is held by a test instead.
32. **More agents buy no observations, which is the mirror image of result 11.** The 112
    severe-tail columns the any-grade grid excludes are not waste: grade 3 and above is the
    threshold clinical practice acts on, so they become a third outcome table. It is
    literature-only, because ClinicalTrials.gov has no grade split at all, which makes it the
    clean form of the question the ablation asks -- can literature arms support a model with
    no registry arms mixed in to carry them? The table reaches **21 agents**, more than the
    registry's 16, at **1.43 observed cells per identifying cell** against the any-grade
    table's 9.97 -- a factor of seven less evidence behind each coefficient. A grade >=3
    table lists only the organs that reached grade 3, so each arm contributes four observed
    axes instead of nine. Result 11 found that more arms bought no
    agents; this finds that more agents buy no observations. The table is built and labelled
    so the set-aside data is inspectable rather than invisible, and no fit is run on it.
33. **A design coefficient was estimating which corpus the arm came from.** Every one of
    the 139 combination arms is a ClinicalTrials.gov arm and none of the 194 literature arms
    is a combination, so `is_combination` and `is_literature` correlate at **-0.53**. Without
    a source term `b_combo` therefore estimated "registry combination against everything
    else" rather than "combination against monotherapy", and its posterior mean went from
    **+0.195** on the registry corpus to **+1.091** on the expanded one -- the reference
    group changing rather than combinations getting worse. Both of those figures come from
    fits that predate the corpus rebuild -- the registry corpus held 16 agents then, and its
    `b_combo` is +0.1930 on the 22-agent corpus section 5 reports -- and the specification
    that produced them no longer exists, so no target regenerates them and they are recorded
    as measurements in `artifacts/source_confounding.json` instead. They are quoted for the
    gap between them, which is the finding. This report was quoting the coefficient as
    "combination arms do report higher rates". With a source indicator added, a smoke fit
    gives `b_combo` **+0.512** and `b_source` **-0.924**: a literature arm reports about
    0.9 logit lower than a registry arm of the same chemistry, which is what a selected
    table with a reporting cut should do. The term is nuisance in the same sense as
    `b_thresh`, which section 5b already shows is substantially absorbing trial-level
    reporting practice rather than correcting censoring, and it is sampled only where the
    indicator varies -- on the registry corpus it would draw its prior and then appear in
    the seed-agreement table as though the fit had estimated it.
34. **And the source gap is not one number but one per organ axis, larger than the
    mechanism effect it was confounding.** It is fitted as a centred axis vector. Every
    figure below is generated, because the hand-typed version of this paragraph went stale
    when the corpus grew: it quoted 12 agents where there are now 17, named cardiovascular
    as the widest negative axis where it is now pulmonary, and listed otologic and renal
    among the measured gaps when neither has enough literature observations to be measured
    at all. See negative result 38.

    <!-- generated: source-axis -->

    Measured on the **17 agents with arms from *both* sources**, which holds the chemistry fixed so the difference is reporting rather than drug, the literature-minus-registry gap runs from **-0.5940 logit on pulmonary** to **+1.8547 on ocular**: heterogeneity **Q = 73.4 on 11 degrees of freedom, p = 2.71e-11**, between-axis standard deviation **0.6280** -- larger than `tau_mech` at 0.5424, the mechanism-by-axis scale the model exists to estimate.

    The direction is what makes it a specification error rather than noise. Papers report **more** than the registry on ocular (+1.8547), dermatologic (+0.6298) -- the signature findings those papers are about -- and **less** on pulmonary (-0.5940), gastrointestinal (-0.4445), hepatic (-0.3596), which are background and fall below a "most common adverse events" cut.

    12 of the 14 axes are compared. An axis needs at least 6 observations on each side to enter. The ones that do not qualify are the same finding in miniature: otologic has 0 literature observations against 96 registry, renal has 5 literature observations against 177 registry -- short on the literature side in every case, which is the reporting selection the included axes quantify, not a gap in the measurement.

    <!-- /generated: source-axis -->

    That pattern is why a single source shift does not suffice. With one shift the
    axis-varying remainder had nowhere to go but `mech_axis`,
    because literature arms are not spread evenly across mechanisms. One consequence is an
    improvement: `mu_axis` now means the registry's reporting level rather than a blend of
    the two, so a prediction for a new design is on the more completely reported scale.
35. **And the other five coefficients are clear, which is why finding two was worth
    checking.** Both confounds came from the same question asked twice -- a coefficient
    moved when the corpus grew, so what is it measuring? -- so `make source-confounding`
    asks it of every arm-level covariate, by the two things that decide separability: how
    much the covariate tracks the source, and whether it still varies *inside* each corpus,
    which is what identifies it when the source term is also in the model.

    | coefficient | correlation with source | variance within source | verdict |
    |---|---|---|---|
    | `b_dar` | +0.022 | 100% | clear |
    | `b_thresh` | +0.199 | 96% | clear |
    | `b_log_n` | +0.070 | 99% | clear |
    | `b_combo` | **-0.523** | 73% | separates completely; handled |
    | `cleav_axis` | +0.033 | 100% | clear |

    `b_thresh` is the one that looks alarming and is not: literature cuts average 1.75
    logit above registry cuts, but **96% of the threshold's variance is within source** and
    its standard deviation inside the literature arms alone is 6.3, so it is identified
    from variation the source term cannot reach. Section 5b's reading of it is unchanged,
    and the smoke fits bear that out -- it moved from +0.055 to +0.051 when the source terms
    went in. And every mechanism level appears in both corpora, the smallest cell being two
    arms against two, so the mechanism-by-axis term and the source term are separately
    identified rather than competing for one contrast.
36. **One organ axis is mostly a laboratory finding, and the number means something
    different because of it.** MedDRA files laboratory abnormalities under `Investigations`
    rather than under the organ, so the taxonomy redistributes them -- "alanine
    aminotransferase increased" to hepatic, "neutrophil count decreased" to haematologic --
    and without that the hepatic axis would be nearly empty while a quarter of the corpus
    sat in a bucket with no organ. The redistribution is right and it has a consequence that
    was never stated: **the hepatic axis is 64% laboratory rows in the registry and 84% in
    the literature**, against 0-8% for most axes. Haematologic is 35% and 18%, renal 17% and
    31%, and hepatic is the only axis over half in either source. So "hepatic risk 0.18" is
    largely transaminase elevation rather than hepatotoxicity as a clinical event, and a
    patient who declares cirrhosis is up-weighting a laboratory finding. It changes what the
    figure means rather than whether it is right, so it is a label on the axis in the
    interface rather than a line in this list -- and where the composition has not been
    measured the interface says nothing, because "not measured" and "not
    laboratory-dominated" must not render the same way.
37. **One clinical event was landing on three different axes by sponsor coding, and 44% of
    it was being discarded.** "Infusion related reaction" appears 408 times in the registry:
    192 rows filed under `immune system disorders`, which map to infectious_immune; 31 under
    `general disorders`, which map to constitutional; and **178 under `injury, poisoning and
    procedural complications`, which are dropped entirely** -- 1,725 patients' worth of a
    named ADC toxicity. MedDRA's primary system-organ class for the term *is*
    injury/poisoning/procedural, which is why it lands there, and that class is excluded for
    procedural harm: 234 rows of falls, 104 of contusions, femur fractures. An infusion
    reaction is a drug reaction that shares their class. So whether it was counted at all,
    and on which axis, was decided by the sponsor's coding rather than by the event. The fix
    is a term-level override applied before the system-organ lookup, by exact normalized
    term rather than by pattern, so an entry can only affect the event it names -- the
    discipline that stops "Blood creatinine increased" being stolen by a renal pattern when
    it is filed under a real class is preserved because nothing in the table is a pattern.

38. **The numbers regenerate and the sentences beside them do not, so the guard that pins
    every figure to an artefact is blind to what the figures are said to mean.** The block
    of fitted parameters in section 5 is generated: each value is read from
    `artifacts/forward_other_metrics.json` and printed to four decimals, and
    `check_report.py` refuses any figure in this report that does not trace to an artefact.
    The sentence *beside* each value was a string in the generator. Looking at all seven,
    **four were making claims the numbers no longer supported, or never had** -- and a fifth
    instance of the same defect turned up outside the block, in an artefact.

    The first was `sigma_agent`, printed with *"small, so the design slots account for much
    of the between-agent variation"* -- a reading written when the parameter stood at 0.159
    on the 16-agent registry corpus. The rebuild moved it to 0.3433 and the sentence did
    not move. Against the scale it was being called small relative to, the residual
    between-agent variation is **0.6329 times** the mechanism-by-axis scale on the
    otherEvents table, and on seriousEvents -- which has **no censored cells at all**, so
    the residual cannot be an artefact of the censoring model -- **1.2060 times** it. Above
    one the claim is not a weaker version of itself but its negation: what distinguishes two
    agents sharing a mechanism, a linker class and a DAR is larger than what the mechanism
    contributes.

    `tau_cleav` carried *"about half the size of the mechanism scale"*. On otherEvents it is
    **0.5293** times that scale, so the sentence was right; on seriousEvents it is
    **0.9833**, effectively the same size. The fraction was not merely exposed to a future
    refit -- it was already false about one of the two tables this report fits, and had been
    since that table was added.

    `b_thresh` carried the report's reason for calling it a reporting covariate rather than
    the censoring correction: *"four times larger on the seriousEvents table"*. Measured, the
    multiple is **3.7318**. Deriving it also answered a question nobody had asked of the
    other coefficients on the same comparison, and `b_log_n` does not survive it: its ratio
    across the two tables is **-6.1448**, a sign flip, so a sentence of that shape would
    have been false in the way that matters -- the two tables are not measuring one thing to
    different degrees. The generated note now says *opposite sign* where the sign flips and
    gives a multiple only where it does not.

    `b_combo`'s note quoted **+1.091** on the expanded corpus against **+0.195** on the
    registry. Both were real measurements, from fits predating both the corpus rebuild and
    the `b_source` term, and neither was in any artefact -- they lived in a log and inside a
    prose string. So the figure traced to nothing, and the registry value quoted in the
    sentence disagreed with the **+0.1930** printed six lines above it. They are recorded as
    measurements now, under `b_combo_without_source_term`, labelled as unregenerable because
    the specification that produced them was replaced in response to them.

    The fifth was not prose at all but a conclusion stored in an artefact:
    `across_agent_adjusted.json` carried a `reading` field asserting the across-agent organ
    ranking beat chance, after the same rebuild had moved that correlation to rho **+0.0073**
    at permutation **p = 0.4595**.

    The remaining three notes were true, and the rule was applied to them anyway, which
    changed what two of them say. `b_log_n` reads *"an ascertainment effect that would have
    been attributed to the design had it not been controlled"* -- accurate, and silent about
    the sign flip above. It now carries it, and says to treat the term as a per-table
    nuisance rather than as an estimate of how ascertainment works. `tau_mech` asserted that the mechanism interaction is *"supported by the data rather
    than asserted by a parameter count"*, which is the premise section 4 reasons from
    together with the mechanism being the largest design scale; both halves are now read
    off, and against every design scale in the block rather than the one that happens to be
    sampled, so enabling the payload-family level cannot quietly invalidate section 4.

    In every one of the five the machine-generated value was right and the hand-written
    sentence next to it was wrong. The pattern is sharp enough to state as a rule: **a
    clause asserting a relation between two printed numbers, or the sign of one, is a
    computation written out in words**, and only the clause supplying the reasoning around
    it is prose. The relational
    clauses are computed now and print the figure they read. Precision turns out to be part
    of the fix rather than a detail: the guard's own measured false-pass rate against
    fabricated figures is **100% at two decimals** and **31% at four**, so a claim stated to
    two was never really checked even when it contained a number. Both halves of that were
    demonstrated while making this fix: the cleavability fraction, printed first as `0.53`,
    passed the guard although no artefact held it, and the threshold multiple printed as
    `3.7318` was rejected until the ratio was written to one. The guard worked as designed
    the moment the claim was stated precisely enough to check, having been invisible to it
    for the whole project.

    The defect was in the test suite too. A test asserting the source gap is axis-specific
    pinned `min_axis == "cardiovascular"` -- the identity of the most negative axis on the
    corpus it was written against -- and the rebuild moved that axis to pulmonary. The
    assertion was a transcript of one corpus wearing the clothes of a claim, and it failed
    for being right about the wrong thing. It now checks what the finding says: the extremes
    are a signature organ and a background organ, ocular is positive, and the background
    organs are negative as a set.

    **A reproducibility guard that checks numbers and not prose leaves the interpretation as
    the one hand-typed thing in the document, and interpretation is what a reader takes away.**

39. **The source term cannot separate reporting from chemistry for half the expanded
    corpus, because half its agents exist in only one source.** Result 33 added `b_source`
    and result 34 made it an axis vector, so the reporting gap would stop being charged to
    the design. Both are necessary and neither is sufficient, and the reason is an
    identifiability condition nobody had checked: a source term can only be told apart from
    an agent's random intercept where that agent has arms on *both* sides of the indicator.
    Measured on the 32-agent corpus, **15 of 32 agents have arms from one source only** --
    10 literature-only, 5 registry-only -- and **5 of those rest on a single arm**. For
    those agents `u_agent` and the source indicator are perfectly collinear: whatever the
    reporting gap is for that drug is indistinguishable from the drug. Only **17 of 32**
    can tell the two apart.

    The consequence is specific rather than general. `sigma_agent` on that corpus is not a
    between-agent scale, it is a between-agent scale and a reporting gap added together,
    and it is therefore not comparable to the same parameter on the registry corpus where
    every agent is a registry agent and the indicator does not vary at all. Comparing them
    across the ablation -- which is what an ablation table invites a reader to do -- would
    be comparing two different quantities with one name.

    This was missed because `make source-confounding` audited *coefficients*: correlation
    with the source and variance within it, for every arm-level covariate, which is where
    results 33 and 35 came from. `u_agent` is a random effect and was outside the audit,
    which left the largest confound of the three outside the instrument built to find
    confounds. The audit now asks the same separability question of the agent level and
    records the per-agent source counts, so the condition is checked on whatever corpus is
    fitted rather than assumed. **An audit covers what its author thought of as a term, and
    a random effect does not look like a term.**

40. **The comorbidity profile reached the proposed design in 4 of 200 cases, and the one
    case that moved was a 0.0005 tiebreak.** The product's claim is (comorbidity profile +
    target antigen) in, proposed design out. The weights were computed, returned in
    `weights_applied`, shown on screen, and visibly moved `weighted_risk` -- 0.2259 with no
    comorbidity, up to 0.3469 and down to 0.2154 across the single-condition profiles.
    None of that is the claim. Measured over every
    condition in the closed 41-item list singly, plus eight combinations chosen to weight
    the leading design's own worst organs, across four targets -- 200 profile-by-target
    pairs -- the proposed design changed in **4**, all four being the same profile, and that
    profile won by flipping the worst organ from gastrointestinal at 0.3290 to
    constitutional at 0.3285.

    The cause is a single line. O1 is the only weighted objective, so the weights enter the
    initial sort and nothing else. On this corpus O1 cannot separate the head of the
    ranking -- the leading tie group runs to **40 to 76 designs** -- and inside a tie group
    the display order came from O2, the *unweighted* worst single organ, and then precedent.
    So the weights decided group membership and then stopped mattering, and what the user
    saw was ordered by a statistic their input could not touch.

    The fix is to order inside the group by the worst organ **under the declared weights**.
    That is not a stronger statistical claim: a tie group is by construction a set O1 cannot
    separate, the card already says so, and an ordering inside it is a stated preference
    either way -- the unweighted version was simply a less relevant stated preference than
    the patient's own. O2 itself stays unweighted on the Pareto front, where its job is to
    stop a design that spreads risk thinly across fourteen axes from winning, and that job
    is about the design rather than the patient. After the change the profile reaches the
    proposal in **52 of 200** pairs, and the displayed set stops collapsing into a single
    tie group: the sweep in section 5c went from **192 of 192** queries where every shown
    candidate shared one group to **48**, so the cards now carry different rank numbers
    rather than six copies of the same one. The ranking itself did not improve and could
    not have -- 0 of 192 queries have a decisive leader before and after, and the median
    leader probability is 0.5000 -- which is the distinction: what changed is which
    stated preference the display obeys, not what the model knows.

    Two things remain true and are the honest limit. There are still only **two distinct
    proposals** across fifty profiles per target, and the behaviour that does appear is
    pharmacologically reasonable rather than impressive: haematologic and neurologic
    comorbidities move the leader from DM1 to MMAF, and a keratopathy history does not,
    which is the right direction given that MMAF is the worst ocular payload in the corpus.
    **A number that is computed, returned and displayed is not thereby in use, and the only
    way to find out is to vary the input and look at the output.**

41. **Inside a payload mechanism the model carries no information about which payload hits
    which organ, and the axis where that costs most is the one the field knows best.**
    Result 6 established that a payload-level by-axis interaction is unidentifiable at any
    corpus size this field will reach, so the model is specified at the mechanism level.
    That decision is correct and this is its price at the output, which had not been
    measured. Two designs sharing a mechanism differ to the model only by linker
    cleavability and DAR, so for a proposal the payload-level spread is unavailable: it is
    real, it is absorbed into `u_agent`, and `u_agent` is set to zero when a new design is
    scored.

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

    The reason is worth stating exactly, because it refutes this project's own plan, which
    plans the ocular axis on "payload family plus a non-cleavable indicator". The two
    high-ocular payloads in the table above are **MMAF, which is non-cleavable, and DM4,
    which is cleavable**; the two low ones are DM1, non-cleavable, and MMAE, cleavable.
    Cleavability is therefore exactly orthogonal to ocular risk here -- each of its values
    holds one high payload and one low one -- and the high pair straddles both payload
    families, so family does not work either. The model, having only cleavability, orders
    the four payloads by it, which is why the rank agreement on ocular is about zero rather
    than merely weak.

    One corollary is worth stating because it reads the other way round. Where the payloads
    genuinely do not differ, the model is the *wider* of the two: on neurologic within
    `topo1` the observed fold is **1.00** -- DXd at 0.1467 against SN-38 at 0.1472 -- and
    the model shows **1.02**, manufactured out of cleavability. So a gap between two
    payloads in this model's output is not evidence that the two payloads differ. The first
    version of the test guarding this measurement asserted that the model spread never
    exceeds the observed one, and that row refuted it.

    This is the structural limit of result 6 arriving at the product, and it bounds what
    may be claimed: the system distinguishes mechanisms on organ profile and does not
    distinguish payloads within one. **MMAF corneal toxicity is among the best-established
    organ effects in ADC pharmacology, and it is the specific thing this model cannot
    say.**

42. **A fix that was applied, was correct, and did nothing, because of the order of two
    lines.** The post-fit measurements -- the organ-rank resolution, the driver waterfall,
    the effect sizes, the fold difficulty -- all read `artifacts/forward_other_metrics.json`
    rather than producing it, and all of them listed the `forward` target as a prerequisite.
    `forward` is `.PHONY`, so running any one of them alone refit the whole model, about an
    hour, to produce a file that was already on disk. Inside `make all` the phony
    prerequisite runs once and the waste is invisible, which is why it went unnoticed for
    the life of the project.

    The fix was to depend on the metrics *file*. It did not work, and the reason is the
    finding. The variable holding its path was assigned one line **above**
    `ART := artifacts`, and `:=` expands immediately, so the prerequisite was
    `/forward_other_metrics.json` -- a path at the filesystem root. Not an error: a
    perfectly valid path that never exists, which make therefore rebuilt every single time.
    The symptom was identical to the phony version, so the fix looked like it had failed to
    apply rather than like it had been undone by the order of two assignments. A deferred
    `=` would have hidden the ordering entirely and worked by accident.

    It was found by noticing a `fit_forward.py` process in its fiftieth minute that no
    deliberate command had started, during a session in which a measurement script had been
    run several times. The cost is not only compute: that process would have overwritten the
    very artefacts the report's figures were being checked against, mid-session, while
    another fit was already running. `tests/test_make_all_regenerates.py` now asserts that
    `make -n` on each measurement target does not mention `fit_forward.py`, and separately
    that the variable expands to a path under `artifacts/`. **A build graph is code, and the
    only evidence that a dependency is wired correctly is that the cheap thing stays
    cheap.**

## 9b. The clean-clone check, run for the first time

The plan's own acceptance test was `git clone` followed by `make all`, with the report's
figures regenerated from scratch. It had never been run. Run now, it establishes one thing
and refutes another.

**What holds.** A fresh clone passes `make check-report` unaided: 19,352 numeric values
across 40 tracked artefacts, **429 decimal figures across the report and the model card,
every one of them tracing to an artefact or to the 19-entry allowlist.** The claim that no
figure in this report was typed by hand is machine-checked from a clone and not only from
the working tree. Every file under `conf/`, `docs/`, `report/`, `src/`, `scripts/`, `tests/`
and `web/` is tracked, so there is no silent reproducibility break of the usual kind -- an
untracked configuration file that only the author's machine has.

**What does not hold: `make all` from a clone is impossible offline, by design.** 273 tests
pass with no data at all; 119 of the 123 errors are the absent PT->SOC dictionary, which is
gitignored on purpose because MedDRA preferred-term and system-organ-class strings are
licensed terminology. The remaining failures are the absent parquet frames. Both are
regenerated by `make fetch` then `make taxonomy`, and both require the network. So the
honest statement of the reproducibility claim is **`git clone` then `make fetch` then
`make all`**, and the plan's offline version of it was never achievable.

**And the check found a bug the working tree could not.** The provenance stamp folded
git's empty output into `None`, so `git status --porcelain` on a clean checkout -- which
prints nothing -- recorded `dirty: null`. Null is also what an unavailable git produces, so
the stamp could not distinguish *this revision does identify the code* from *we could not
tell* -- and the clean case is the only one where that distinction pays for itself. Every
test had passed because every test ran against a dirty tree. The failure mode was reachable
only from a clone, which is the argument for running the check at all.
## 10. Limitations

* Tier 2 novelty -- a new molecule in a known chemical family -- is not supported, and the
  system refuses to give a point estimate outside Tier 1. The refusal is earlier and harder
  than the plan asked for: `payload` is a closed enumeration, so a chemistry the model has
  never seen cannot be named in a request at all and is rejected by the schema. The tier-3
  path, which returns no organ estimate, therefore never fires for an ordinary caller --
  every one of the design space's eleven payloads has a mechanism the full fit covers. It
  stays because any posterior fitted on fewer mechanisms, which is every
  leave-one-mechanism-out fold, puts a design-space payload outside the fit, and then it is
  the only thing between a caller and fourteen extrapolated numbers.
* No efficacy model. The one public ADC activity dataset (435 rows) is beaten by a
  decision tree on SMILES string length and DAR under a leakage-free grouped split.
* The comorbidity layer has zero training rows and is an elicited prior throughout,
  labelled `elicited_prior` in every API response.
* Two of the registry corpus's five payload mechanisms can serve as a held-out fold, and
  three of the expanded corpus's five: `dna_crosslink` crosses the three-agent floor on the
  strength of the literature arms. The remaining two do not improve with corpus size, and
  the reason is arithmetic rather than effort -- calicheamicin ADCs number two worldwide and
  duocarmycin ADCs two. Immunotoxins and photoimmunotherapy are a mechanism each and are
  excluded from the corpus as non-conventional conjugates, which is why the figure is five
  mechanisms here and seven in the plan.
