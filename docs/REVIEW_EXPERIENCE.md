# Evidence review in 0.6.15

The browser still uses the existing model and deterministic label rules. This release changes how the evidence is reviewed, not the trained model or the clinical thresholds.

## User flow

1. Add conditions and, when known, the cancer. Registry selections and model-read text remain distinct.
2. Enter available lab values. Missing values stay unknown; reference ULNs retain their documented defaults. “No flag triggered” is not a clinical normal-range assertion.
3. Review the matched concept and organ associations. The score is not individual toxicity risk.
4. Choose the condition to examine first when several conditions are present.
5. Compare restrictions, patient-organ warnings and other warnings. Each ADC now shows cancer-match status. Return directly to conditions or labs when information is missing.
6. Open an ADC to read trial population, treatment/comparator sample sizes and the ClinicalTrials.gov source. Save a plain-text review locally when needed. The export includes inputs, missing values, conditional rules, warnings and trial context. It is not sent to a service.

## Code map

- `ml/web/app.js`: DOM rendering and interaction for the five steps.
- `ml/web/review.js`: pure lab-state, indication-state and export functions, tested by `tests/js/review.js`.
- `ml/web/app.css`: layout, typography, responsive presentation; Intel One Mono is the shipped UI face.
- `ml/webapp.py`: API adapter, per-request recommendation state and serial analysis worker.
- `ml/recommend.py`: condition analysis and evidence ordering.
- `ml/restrictions.py`, `ml/labs.py`: deterministic restrictions and lab parsing.
- `ml/scratch_runtime.py`: released model inference.
- `scripts/build_ubuntu_release.py`, `scripts/build_windows_release.py`: portable app and Windows packaging.

The existing API and research modules were inspected for their relationship to this flow. This release does not claim a repository-wide rewrite, model improvement or measured speedup. It isolates reusable presentation rules instead of duplicating them in the export.

## Experimental files

The untracked antigravity files `adc_designer.py`, `drug_toxicity.py`, `validate_de_novo.py` and its report are preserved in the original working copy. They are not imported by the released app or embedded by the portable builder. Their hand-set scores and synthetic checks are not clinical validation and are not included as achieved results in the final report.
