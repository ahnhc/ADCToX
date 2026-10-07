# Model card: forward organ-toxicity model

**Status: the model does not beat its baseline. Read this section first.**

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

### Pre-specified primary metric: within-arm axis ranking

AUROC for "this axis is among the arm's observed top three", averaged over folds.

| split | model | mechanism-mean baseline | global-axis-mean baseline | delta vs mech | 95% CI |
|---|---|---|---|---|---|
| leave-one-agent-out (16 folds) | 0.825 | 0.839 | **0.844** | −0.014 | [−0.033, +0.004] |
| leave-one-mechanism-out (2 folds) | 0.856 | 0.871 | **0.871** | −0.016 | [−0.025, −0.006] |

**The model is worse than the baseline on both splits, and significantly so on
leave-one-mechanism-out.** The best predictor of the three is the global axis mean, which
contains no design information at all.

### Why the pre-specified gate was unfireable

The plan set the gate at "macro AUC below 0.65 triggers the cut order". The model scores
0.825, so that gate reads PASS -- but a **constant** global-axis-mean predictor scores
0.844 on the same metric. A gate that a design-blind constant clears is not a gate. It is
reported for the record and not used; the gate that means something is the delta against
the strongest baseline, and by that gate the model fails.

This is a mistake in the plan, not in the fitting, and it is worth stating plainly: an
absolute threshold on a metric dominated by base rates cannot detect the failure it was
meant to detect.

### Why the within-arm metric cannot separate the model from the base rate

The task ranks 14 axes inside one arm. Axis base rates are consistent enough across arms
that a single fixed ordering -- constitutional, gastrointestinal and infectious near the
top, otologic near the bottom -- is close to optimal for every arm. The model knows those
base rates too (`mu_axis`), then perturbs them with design effects that are small relative
to the between-axis spread. A small perturbation of a near-optimal ordering can only lose.

So the negative result above is real but narrow: it says the design terms do not improve
*within-arm axis ranking*. It does not by itself say the design terms carry no signal.

### Secondary metric, added after seeing the above

Across-agent, within-axis rank correlation: for one axis, can the model order the agents
from low to high? This is the comparison the product actually makes ("is lung risk high
for *this* design"), and the global axis mean has zero discriminative power on it by
construction, being constant across agents.

Adding a metric after seeing a negative result risks post-hoc selection, so: the reason
for adding it is stated above and is independent of the outcome, and the pass threshold
was fixed before running it -- mean Spearman above +0.3 with a bootstrap CI excluding
zero. Results are in `artifacts/forward_other_metrics.json` under
`across_agent_spearman`; both metrics are always reported together.

## Where the model fails, and why that is informative

The worst folds are the agents whose toxicity signature differs most from the other
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
