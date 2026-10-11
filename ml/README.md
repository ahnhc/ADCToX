# ml/ -- what can actually be learned here, and what cannot

Every number below is printed by `ml/summarize.py` from `ml/results/*.json`. Environment:
`/data/hyeongchanahn/envs/adctox` (torch 2.11 + CUDA 12.8). Caches: `python -I ml/prepare_data.py`, then
`python -I ml/embed_terms.py`. The collaborator workbooks and these caches are not redistributed
(`docs/TEAMMATE_DATA_USE.md`).

## Result 1 -- comorbidity -> organ vulnerability is learnable (Task A)

Data: FinnGen hazard ratios, 59,157 rows, 1,616 prior diseases x 193 outcomes. Target: log HR.
Features: SapBERT embeddings of the disease and outcome names (a pretrained biomedical language model).
Three held-out regimes; the baseline is a lookup table built from training rows only.

| regime | model | R2 | organ-ranking gain over lookup [95% CI over ICD families] |
|---|---|---|---|
| unseen pair | MLP + SapBERT | 0.866 (lookup 0.352) | +0.240 [+0.192, +0.311] |
| unseen comorbidity | MLP + SapBERT | 0.737 (lookup 0.647) | +0.029 [+0.017, +0.043] |
| unseen ICD family | MLP + SapBERT | 0.631 (lookup 0.570) | +0.040 [+0.023, +0.059] |

What carries it is the **pretrained embedding**, not the trained head:

* TF-IDF text features: no gain on unseen comorbidities or families (R2 0.540 < lookup 0.570 on families).
* Identity-only random embeddings: worse than lookup (organ-ranking -0.076 [-0.131, -0.035] on unseen comorbidities).
* **A training-free kNN over the same SapBERT space matches the MLP on organ ranking in every regime**
  (family regime: +0.039 [+0.024, +0.059] vs +0.040). The MLP wins on R2 for unseen pairs (0.866 vs 0.721) and
  is within 0.015 elsewhere. Do not write "the MLP beats nearest-neighbour" -- it does not, on the metric the product uses.
* LightGBM on PCA-reduced embeddings is below the MLP on unseen comorbidities (+0.012 [-0.001, +0.027]).

## Result 2 -- external check against the hand-curated registry (41 conditions)

For each `conf/comorbidity_registry.csv` condition: retrain with every FinnGen disease whose SapBERT cosine to the
label is >= tau removed, then ask whether the learned per-organ vulnerability ranks the curated organs above the rest.

| tau (median diseases removed) | MLP AUROC | kNN AUROC | curated organ in top 3 |
|---|---|---|---|
| 0.80 (0) | 0.855 [0.79, 0.91] | 0.835 | 88% |
| 0.65 (2) | 0.845 [0.78, 0.91] | 0.857 | 83% |
| 0.50 (12) | 0.804 [0.72, 0.87] | 0.748 | 71% |

Chance is 0.5 AUROC and 25% for "in the top 3". MLP vs kNN is not distinguishable at any tau.
**This is a sanity check, not clinical validation:** the registry's organ_axes name the organ a condition is a
disease *of*, so success means "recovers same-organ excess risk", not cross-organ vulnerability. Only 51% of
conditions have the learned top-1 organ among the curated ones.

## Result 3 -- ADC structure -> adverse-event incidence is NOT learnable here (Task D)

15,210 rows, 75 ADCs, 33 payloads, 906 AE terms. For a new ADC and for a new payload, structure features make a flexible
model *worse* (-0.009 to -0.093 R2, most intervals exclude 0). A heavily regularised
`payload-class x organ-domain` correction on top of the no-structure model adds +0.002 [-0.003, +0.007]
(ridge alpha chosen at its ceiling, i.e. the data asked for the correction to be shrunk to nothing). This agrees with the
project's own axis-level finding that design terms do not beat a base rate. The no-structure model (term + grade) does beat the
lookup (R2 0.52 vs 0.47), but that is term-level frequency, not anything about the ADC.

## Result 4 -- arm-level population features (measured before this directory existed)

Predicting organ events across arms of the same agent, grouped by trial: biological features (cancer type, combination,
exclusion-criteria flags) gave -0.018 within-axis AUC against the per-agent mean; the +0.08 that appeared came entirely from
reporting-process variables (reporting threshold, sample size, phase, year, eligibility-text length). Not a usable task.

## Connecting it to the product (`compare_pipeline.py`, `learned_vulnerability.py`)

Replacing the hand-set severities with learned ones (centred per condition: a serious disease raises risk on every organ, so
the condition's median organ is subtracted first) changes the shown design set in 37.5% of the 192 target x profile queries and
the lead design in 25%. Profiles change the set in 86% of queries vs 43% with the curated severities. That is *responsiveness*,
not correctness -- this project has already shown responsiveness is a function of an arbitrary constant (`lam`).
`src/` was not edited; the swap is done in memory.

## What was tried and how it was decided (nothing here was hidden)

* The first quick TF-IDF tests (scratchpad) showed no gain on unseen comorbidities; SapBERT was then tried and kept. TF-IDF and
  random embeddings were re-run as controls with identical settings.
* Batch size 1024 -> 8192 (GPUs were shared and kernel launches were the bottleneck); all variants re-run under it.
* Registry check: tau 0.80 was declared first, then found to remove 0-2 diseases (a guard with no teeth); 0.65 and 0.50 were added
  *because of the ban counts, not the AUROC*. The per-axis standardised score was added after seeing "musculoskeletal" in
  everyone's top 3; both are reported (they agree).
* Task D: two structure formulations (free models; regularised residual). Both null. No third was tried.
* Severity centring in `learned_vulnerability.py` was added after seeing that the uncentred version marks every organ of a
  cirrhotic patient as at risk. It is a logic fix of the mapping, not a tuned constant; the 1-SD scale is a choice.
* Bootstrap CIs resample whole ICD families, because diseases in one family are not independent. Registry CIs resample
  conditions (n = 41, so they are wide).

## Limits that must travel with any claim

1. FinnGen hazard ratios are natural disease progression. They say which organ is *already* vulnerable, not that an ADC is toxic to it.
2. The pairs in FinnGen are a curated candidate list (87% of HRs > 1), so this learns the size of a risk among pairs that were
   reported, not whether a pair is reportable.
3. Near-duplicate disease definitions exist; the family and similarity-guarded regimes address, but cannot rule out, leakage.
4. No end-to-end fine-tuning of SapBERT was attempted. No prospective or clinical validation exists.
