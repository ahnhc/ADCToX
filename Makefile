# ADCTox build graph. `make all` from a clean clone must regenerate every number that
# appears in the report; that property is tested in week 4, not assumed.

PY      := .venv/bin/python
DATE    := $(shell date -u +%Y-%m-%d)
RAW     := /data/hyeongchanahn/adctox/raw
STUDIES := $(RAW)/ctgov/$(DATE)/studies
ELIG    := $(RAW)/eligibility/$(DATE)
PROC    := data/processed
ART     := artifacts

.PHONY: all env taxonomy corpus eligibility enrichment forward propose test check-report clean

all: taxonomy corpus forward enrichment propose test

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

forward: corpus
	$(PY) scripts/fit_forward.py --processed $(PROC) --out $(ART) --kind other
	$(PY) scripts/fit_forward.py --processed $(PROC) --out $(ART) --kind serious

# Sensitivity check for the censoring treatment: refit with missing cells imputed as
# zeros and show what that does to the threshold coefficient. The censored model is only
# credible if the naive alternative visibly misbehaves.
censoring-sensitivity: corpus
	$(PY) scripts/censoring_sensitivity.py --processed $(PROC) --out $(ART)

propose:
	$(PY) scripts/propose_demo.py --out $(ART)

test:
	$(PY) -m pytest tests/ -q

# Guards against a number being typed into the report by hand and then drifting from the
# code that produced it.
check-report:
	$(PY) scripts/check_report.py report/

clean:
	rm -rf $(PROC)/*.parquet $(PROC)/*.json $(ART)/*.json $(ART)/*.npz
