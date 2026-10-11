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

---

## Update: BioLORD, a label-based drug side, and the recommender

**Encoder.** Same harness, folds and metrics (`ml/lab.py`; selection seeds 0-2). On unseen ICD families BioLORD-2023 beats SapBERT in the
paired family bootstrap (organ ranking +0.0187 [+0.0035, +0.0345]; R2 0.655 vs 0.622). PubMedBERT is worse (-0.021 [-0.040, -0.003]),
Qwen3-Embedding-0.6B and MedCPT tie, BGE-M3 is the weakest. Everything tried after that was **null or worse** against frozen BioLORD:
precision weighting (-0.0007 [-0.007, +0.005]), MONDO organ axes (+0.0020 [-0.002, +0.007]), MONDO definitions (-0.0022 [-0.007, +0.003]),
a bilinear head (-0.0079 [-0.0137, -0.0024]). LoRA fine-tuning of the encoder (fresh per fold, one pre-declared setting) raised R2 in all
three seeds (0.655 -> 0.684) but not organ ranking, the metric the product uses (+0.0032 [-0.0011, +0.0080]), so it was **not adopted**.
The saved model (`ml/vulnerability_model.py`, `predict(text)`) is frozen BioLORD + MLP head, 5-seed ensemble.

**Drug side.** From the approved labels (`ml/drug_evidence.py`): boxed / section-5 warnings per organ (every organ a heading names; the
boxed headline is split case-insensitively, which the first parser did not do and so missed sacituzumab's boxed diarrhoea), plus the
largest grade >= 3 incidence in the label tables, aggregated within one table (the first version added Grade 3 + Grade 4 across trials),
monotherapy preferred, combination-only and lab-table values marked, and a missing table or row reported as such, never as 0.
Incidence alone recovers the label's warned organs with AUROC 0.670 [0.559, 0.780] over 12 drugs (`ml/matcher2.py`; it misses rare lethal
events: T-DXd 0.48). An earlier attempt on the transcribed trial tables (`ml/matcher.py`) failed for coverage reasons and is kept for the record.

**Label use restrictions** (`conf/label_restrictions.yaml`, `ml/restrictions.py`): 86 rules from sections 4, 8.6, 8.7, 2 and (where section 8
is silent) 12.3 of the 14 labels, each with a verbatim quote that a test checks against the label. Categories: contraindicated > avoid >
insufficient data = no label statement > monitor > no adjustment. Lab values the user did not enter are not guessed from a diagnosis (CKD 3
is an eGFR stage; the labels use Cockcroft-Gault CLcr): the verdict is the set of categories the label allows over the missing range ("Avoid?").

**Does the learned patient weighting help?** Positives = ADCs whose label warns on the condition's organ (40 registry conditions, 12 ADCs),
score = incidence percentile . s (non-circular). Against random weights the learned ones do better (+0.070 [+0.015, +0.123]), but the curated
own organs do better still (0.644 vs 0.512), and adding the learned weights ON TOP of the own organs, which is how the recommender would use
them, makes it worse (`ml/eval_learned_addon.py`, pre-declared f = 0.25 / 0.5: -0.035 [-0.054, -0.016] / -0.054 [-0.079, -0.030]).
With FAERS signals as the positives instead (independent of the label text) the add-on is still worse: -0.025 [-0.046, -0.004] / -0.034 [-0.061, -0.008].
The recommender therefore runs without them by default (`--learned F` to opt in for every condition). The one exception is offered, not applied: when a typed condition maps to no organ at all, the wizard says so and asks whether to use the learned estimate for that condition only (`--learned-fallback F`); understood conditions are never changed by it, the patient line marks it 'not validated', and the model returns organs even for typos or nonsense, so the prompt asks to check the spelling first. Predicting a later disease from a comorbidity is not the same
question as ADC toxicity given that comorbidity. Inference was also aligned with training: training only ever saw the lag one-hot in the context
vector (`lab.py`: `cat([eye[lag], eye[nl+dom]])[:, :nl+nd]` keeps the first block), and the first `predict` set the domain bits as well
(mean |change| in severity 0.005 after the fix). Retraining with the domain actually included would be a new model and was not done.

**Recommender** (`ml/recommend.py`, redesigned 2026-10-11 after an external review; `ml/docs/recommender_changes.md`). Order, most favourable first,
lexicographic: (1) label restriction for this patient, worst case over missing labs, then whether it is settled; (2) B = sum of s_o over the
patient's organs with a BOXED warning; (3) Wn = the same for section-5 warnings. s_o = curated severity of the conditions whose own organ it is.
B and Wn only grow when s grows. The first version's weighted mean 100 * sum w t / sum w (w = 1 + 9 s) could FALL when an organ became more
vulnerable (d/ds_k = 9 (100 t_k - raw) / sum w), and its per-patient min-max always gave the best drug 0%; both are gone, and nothing is shown
as a percentage. Incidence is displayed (absolute, flagged) but not used in the order; boxed warnings on organs the patient is not vulnerable
in are listed separately; ties are marked '='. A checklist names the tests the conditions call for (`conf/patient_checks.yaml`).
This orders label evidence for one patient. External check on real-world reports (FAERS via openFDA, `ml/validate_faers.py`): the label warning level it
orders by discriminates within-class disproportionality signals with AUROC 0.778 [0.727, 0.837] over 169 ADC x organ cells (shuffled 0.499;
label-table incidence 0.651); calibration of P(signal | label level), leave-one-ADC-out: slope 1.06, in-the-large -0.007, Brier 0.143 vs 0.200;
per organ it agrees except renal (rho -0.08). FAERS has no comorbidities, so this validates the drug-side organ evidence,
not patient-specific risk. Patient level, JADER (PMDA spontaneous reports WITH each case's medical history; 12,973 single-ADC cases,
`ml/validate_jader.py`): among case x organ pairs where the history includes that organ, the label level discriminates reported events in it,
AUROC 0.649 [0.634, 0.665]; out-of-fold calibration slope 1.00, Brier 0.076 vs 0.089; but the warning's
odds ratio is SMALLER in vulnerable cases (0.65 [0.56, 0.74] of the non-vulnerable one), so vulnerability picks the organ to look at and does
not amplify the warned toxicity -- which the lexicographic design reflects and the old lambda-weighting did not. A cohort with a denominator
is still needed; that analysis is implemented (`ml/validate_outcomes.py`, tested on synthetic cohorts) but no cohort exists here
(`ml/docs/validation_plan.md`).
Conditions outside the 41-entry registry are resolved in this order: a near-identical registry entry (BioLORD cosine >= 0.80) > MONDO hierarchy
(`ml/mondo_index.py`, name similarity >= 0.75, severity a fixed 0.8) > a loosely similar registry entry (>= 0.60) > not understood (no organ).
Tests: `tests/test_ml_recommender.py`.

**Running it off this server.** `ml/build_portable.py` makes one-file versions of the program. The light one (`dist/adc_recommender.py`;
Python + numpy) matches typed diseases by spelling only. The full one (`--full`, `dist/adc_recommender_full.py`) is the server program with its
language models: the model code is copied function by function from `ml/vulnerability_model.py`, `ml/mondo_index.py` and `ml/lab.py`, only file
locations change (a `models` folder next to the program, or `ADC_MODEL_DIR`), and the GPU is used when torch sees one, else the CPU.
A test checks that it prints exactly what `ml/recommend.py` prints for typed diseases. For Windows, `ml/build_windows.py --full` writes
`dist/ADC_full_build_on_windows.zip`; `build_full.bat` in it builds a folder (`ml/win/make_folder.py`: PyInstaller one-folder app, CPU PyTorch,
BioLORD-2023 and SapBERT at pinned revisions, a windowless launcher that opens Windows Terminal) that runs without Python or internet.
The folder carries `vuln_biolord.pt` (trained on FinnGen summary statistics; the program prints no FinnGen numbers) by the project owner's decision.
