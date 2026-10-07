# Model card: forward organ-toxicity model

**Status: cross-validation is being re-run. Every previously reported CV number was
produced with an identified bug present and has been withdrawn. Read this section first.**

A non-identifiability was found after the first evaluation round and is described in
`## The bug that invalidated the first evaluation` below. Until the re-run completes, this
card states what the corpus is and what the bug was, and quotes no performance figure.

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

**Withdrawn pending re-run.** The first evaluation round reported the model losing to a
base-rate baseline on three held-out splits. Those numbers were produced before the
non-identifiability below was fixed, and that bug was demonstrably suppressing the
mechanism effect -- its scale recovered from 0.157 to 0.531 once the degeneracy was
removed. A result obtained from a model whose main effect was being absorbed elsewhere
cannot be reported, in either direction.

The artefacts are retained with a `.pre-centering-bug` suffix for comparison once the
re-run lands, not for quotation.

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

`tau_mech` 0.592 [0.503, 0.711] -- the mechanism x axis interaction is supported by the
data rather than asserted by the parameter count.
`sigma_agent` 0.121 [0.076, 0.189] -- small, so the design slots account for much of the
between-agent variation. That is consistent with the mechanism effects being real while
still being too coarse for the outliers above.
`b_dar` +0.038 [−0.004, +0.080] -- includes zero. DAR is an agent-level constant and is
confounded with agent identity at this corpus size. The pharmacokinetic literature
supports a DAR effect; this corpus does not resolve one.
`b_log_n` +0.030 [+0.020, +0.041] -- larger arms report higher rates. An ascertainment
effect that would have been attributed to the design had it not been controlled.

Convergence is checked by refitting under a second seed; the worst standardized gap in
posterior means was 0.239 pooled standard deviations, which is acceptable.

## What this model must not be used for

* Any claim of chemical generalization to an unseen payload structure. Not supported, and
  separately refuted: the chemistry corpus has no relatives for 9 of 11 payload classes.
* Any efficacy claim. No efficacy model is used.
* Any patient-specific risk statement. The comorbidity layer is an elicited prior with
  zero training rows and is labelled `elicited_prior` in every response.
* Ranking candidates whose credible intervals overlap. The API collapses those into
  explicitly indistinguishable groups.
