# ADCTox build graph. `make all` from a clean clone must regenerate every number that
# appears in the report; that property is tested in week 4, not assumed.

PY      := .venv/bin/python
DATE    := $(shell date -u +%Y-%m-%d)
RAW     := /data/hyeongchanahn/adctox/raw
STUDIES := $(RAW)/ctgov/$(DATE)/studies
ELIG    := $(RAW)/eligibility/$(DATE)
PROC    := data/processed
ART     := artifacts

.PHONY: all env taxonomy corpus eligibility enrichment forward propose test \
        censoring-sensitivity label-history label-changes label-change-eval \
        dose-mod dose-mod-eval module-b hard-flags sync-report check-report clean

# `make all` has to produce every figure the report quotes, or the claim that the report
# is regenerable is false. It previously omitted the whole of Module B and the censoring
# sensitivity analysis while the report cited both.
all: taxonomy corpus forward censoring-sensitivity enrichment module-b propose test \
     hard-flags check-report

# Module B: the dated label-change case series and the dose-modification ordering
# comparison. Both depend on fetched label data, so the fetches are separate targets --
# they hit government services and should not re-run on every build.
module-b: label-changes label-change-eval dose-mod-eval

env:
	uv venv .venv && uv pip install -e ".[model,api]"

# The PT->SOC dictionary is regenerated from public-domain ClinicalTrials.gov records
# rather than shipped, because MedDRA preferred-term and SOC strings are licensed
# terminology even where individual strings appear in public-domain documents.
taxonomy:
	$(PY) scripts/build_taxonomy.py --studies $(STUDIES) --out $(PROC)

corpus: taxonomy
	$(PY) scripts/build_arms.py --studies $(STUDIES) --out $(PROC)

eligibility:
	$(PY) scripts/fetch_eligibility.py --out $(ELIG)

enrichment:
	$(PY) scripts/exclusion_enrichment.py --eligibility $(ELIG) --out $(ART)
	$(PY) scripts/exclusion_enrichment.py --eligibility $(ELIG) --out $(ART) --polarity exclusion
	$(PY) scripts/exclusion_enrichment.py --eligibility $(ELIG) --out $(ART) --polarity lab_floor

# Two variants, and the comparison between them is the point. `other` carries far more
# signal and needs the censoring model; `serious` is completely reported, so every missing
# cell is a true zero and no censoring is involved. If the two disagree on the mechanism
# profiles, the censoring treatment is doing the work rather than recovering it, and that
# has to be reported.
forward: corpus
	$(PY) scripts/fit_forward.py --processed $(PROC) --out $(ART) --kind other
	$(PY) scripts/fit_forward.py --processed $(PROC) --out $(ART) --kind serious
	$(PY) scripts/propose_demo.py --processed $(PROC) --out $(ART) --kind other --fit-only
	$(PY) scripts/propose_demo.py --processed $(PROC) --out $(ART) --kind serious --fit-only
	$(PY) scripts/compare_event_tables.py --out $(ART)

# Both posteriors are products, not just the metrics. The serious fit is what makes a
# comorbidity question answerable: measured on this corpus the two tables rank organs
# differently, and an axis the patient is vulnerable on is a serious-harm question. With
# only the common posterior present the product still answers but bands every axis on the
# common table, which put T-DXd's boxed-warning organ 10th of 14 for an ILD patient.

# Sensitivity check for the censoring treatment: refit with missing cells imputed as
# zeros and show what that does to the threshold coefficient. The censored model is only
# credible if the naive alternative visibly misbehaves.
censoring-sensitivity: corpus
	$(PY) scripts/censoring_sensitivity.py --processed $(PROC) --out $(ART)

# Fetches hit DailyMed and openFDA; kept out of `all` so a rebuild does not re-pull.
label-history:
	$(PY) scripts/fetch_label_history.py --out $(RAW)/dailymed/$(DATE)

dose-mod:
	$(PY) scripts/fetch_dose_mod.py --out $(RAW)/openfda_label/$(DATE)

label-changes:
	$(PY) scripts/label_change_events.py --raw $(RAW)/dailymed/$(DATE) --out $(ART)

label-change-eval: corpus label-changes
	$(PY) scripts/label_change_eval.py --processed $(PROC) --out $(ART)

dose-mod-eval: forward
	$(PY) scripts/dose_mod_eval.py --labels $(RAW)/openfda_label/$(DATE) --out $(ART)

propose:
	$(PY) scripts/propose_demo.py --out $(ART)

test:
	$(PY) -m pytest tests/ -q

# Guards against a number being typed into the report by hand and then drifting from the
# code that produced it.
# Regenerate the report's fitted-parameter block before checking it, so a refit cannot
# leave the prose quoting last week's posterior. The report had three stale parameters and
# quoted one number as both current and pre-fix.
# How much of the output is the rule layer rather than the fit? Measured, because a rule
# that raises the band the ILD case study is about would make that case study circular.
hard-flags:
	$(PY) scripts/hard_flag_necessity.py --out $(ART)

sync-report:
	$(PY) scripts/sync_report_numbers.py

check-report: hard-flags sync-report
	$(PY) scripts/check_report.py report/

clean:
	rm -rf $(PROC)/*.parquet $(PROC)/*.json $(ART)/*.json $(ART)/*.npz
