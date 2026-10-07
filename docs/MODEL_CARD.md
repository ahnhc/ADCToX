# Model card: forward organ-toxicity model

**Status: the model does not beat a base-rate baseline on any of five evaluations. Read
this section first.**

Figures below are from the re-run on the corrected model. A non-identifiability was found
after the first round, every number was withdrawn, and the re-run reproduced the within-arm
results almost exactly -- see `## The bug that invalidated the first evaluation`.

## Intended use

Research prototype. Ranks chemically valid, individually precedented ADC configurations
by predicted organ-system toxicity against a stated comorbidity profile. Not a clinical
decision tool; not validated prospectively; no use in patient care.

## What the data can identify

Design features -- payload mechanism, linker type, cleavability, DAR, isotype, target --
are **agent-level constants**. Trastuzumab emtansine's 48 arms are 48 observations of its
trial populations but one observation of DM1 chemistry. The data that identifies a design
coefficient is therefore `n_agents x n_axes`:

| | count |
|---|---|
| arms (attributable, n>=30, conventional ADC) | 285 |
| (arm x axis) cells | 3,990 |
| distinct agents | 16 |
| **identifying cells (agents x axes)** | **224** |
| design parameters | 100 |
| ratio against identifying cells | 2.24 : 1 |

## Results

<!-- generated: results-table -->

| evaluation | model | best baseline | delta | 95% CI | |
|---|---|---|---|---|---|
| within-arm ranking, leave-one-agent-out (16) | 0.8036 | 0.8458 | **-0.0422** | [-0.0650, -0.0221] | excludes 0 |
| within-arm ranking, leave-one-mechanism-out (2) | 0.8523 | 0.8715 | **-0.0191** | [-0.0287, -0.0096] | excludes 0 |
| within-arm ranking, leave-one-family-out (4) | 0.7725 | 0.8525 | **-0.0783** | [-0.1223, -0.0317] | excludes 0 |
| across-agent per-axis Spearman | +0.0966 | +0.0263 | -- | [-0.0639, +0.2632] | includes 0 |
| dose-modification ordering (13) | +0.1882 | +0.1533 | +0.0348 | [-0.0007, +0.0693] | includes 0 |

<!-- /generated: results-table -->

The best within-arm predictor is the global axis mean, which carries no design information.
The dose-modification comparison was favourable before the bug fix (+0.039 [+0.003,
+0.073]) and is not after it, and in the same output the model is at chance on naming the
organ each label fears most (1 of 13 against 0.93 expected), naming gastrointestinal for
9 of 13 drugs because that is the axis base rate.

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
2. **Cleavability entered as a raw indicator.** Two of sixteen agents carry a non-cleavable
   linker, so the indicator is nearly constant and behaves as a second per-axis intercept,
   unidentified against `mu_axis`.

| | before | after |
|---|---|---|
| `tau_cleav` | 3.872 (eight times its prior scale) | 0.391 |
| `tau_mech` | 0.157 | **0.531** |
| max predicted rate | 1.0000 | 0.3930 |

The `tau_mech` recovery is the consequential line: the degenerate cleavability term had
been absorbing the mechanism effect, so the first evaluation measured a model whose main
effect was being soaked up by an artefact.

## Where the model failed in the first round, and why the pattern is informative

These per-fold numbers are from the pre-fix model and are listed for the *pattern*, not
the values. Whether the pattern survives the re-run is itself a result.

The worst folds were the agents whose toxicity signature differs most from the other
members of their mechanism group:

| fold | delta vs mech baseline | signature |
|---|---|---|
| trastuzumab emtansine | **−0.115** | thrombocytopenia, ocular, hepatic -- the only DM1 agent |
| belantamab mafodotin | −0.064 | keratopathy -- the only MMAF agent |
| mirvetuximab soravtansine | −0.050 | ocular -- the only DM4 agent |
| polatuzumab vedotin | −0.040 | one of four MMAE agents |

Every large miss is an agent that is the sole representative of its payload *family*
inside a broader mechanism class. Held out, it is predicted from chemistry that behaves
differently: T-DM1's platelet and ocular profile predicted from MMAE's neuropathy.

This is the structural squeeze the project set out to measure, now visible in prediction
rather than only in parameter counting. Payload *mechanism* (6 classes, fixed as the
corpus grows) is identifiable but too coarse to capture T-DM1. Payload *family*
(auristatin / maytansinoid / camptothecin / ...) would capture it but is not identifiable:
the payload vocabulary grows as fast as the corpus does, measured at 9 classes at 17
agents and 20 at 54, leaving the cells-per-parameter ratio flat near 2.8:1 at every size.
The resolution that would help recedes as fast as it is approached.

## Calibration and uncertainty

<!-- generated: fitted-parameters -->
`tau_mech` 0.5928 [0.4928, 0.7008] -- the mechanism x axis interaction is supported by the data rather than asserted by a parameter count.

`sigma_agent` 0.1590 [0.0980, 0.2402] -- small, so the design slots account for much of the between-agent variation.

`b_combo` +0.1950 [+0.1691, +0.2213] -- combination arms do report higher rates.

`b_log_n` +0.0393 [+0.0288, +0.0491] -- an ascertainment effect that would have been attributed to the design had it not been controlled.

`b_dar` +0.0319 [-0.0175, +0.0840] -- includes zero. DAR is an agent-level constant and is confounded with agent identity here. The pharmacokinetic literature supports a DAR effect; this corpus does not resolve one.

`b_thresh` +0.0327 [+0.0272, +0.0375] -- the reporting-threshold covariate. Not the censoring correction: it is four times larger on the seriousEvents table, which has no censored cells at all, so it is substantially absorbing trial-level reporting practice.

Convergence stands in for R-hat: the model is refit under a second seed and posterior means compared. The worst standardized gap is 0.1376 pooled standard deviations, on `b_thresh`, against a threshold of 0.3 -- acceptable.
<!-- /generated: fitted-parameters -->


## What this model must not be used for

* Any claim of chemical generalization to an unseen payload structure. Not supported, and
  separately refuted: the chemistry corpus has no relatives for 9 of 11 payload classes.
* Any efficacy claim. No efficacy model is used.
* Any patient-specific risk statement. The comorbidity layer is an elicited prior with
  zero training rows and is labelled `elicited_prior` in every response.
* Ranking candidates whose credible intervals overlap. The API collapses those into
  explicitly indistinguishable groups.
