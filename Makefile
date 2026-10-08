# ADCTox build graph. `make all` from a clean clone must regenerate every number that
# appears in the report; that property is tested in week 4, not assumed.

PY      := .venv/bin/python
# The frozen raw snapshot every analysis reads. Pinned, not `date +%F`: it used to be
# today's date, so from the day after the snapshot was taken every target that reads raw
# data pointed at a directory that does not exist -- and a fetch target would have
# silently created a *new* snapshot underneath a report whose figures came from the old
# one. The plan calls these directories immutable; a floating date is the opposite.
# Override to analyse a different snapshot: `make forward SNAPSHOT=2026-11-01`.
SNAPSHOT ?= 2026-10-07
DATE    := $(SNAPSHOT)
# Fetches write a new dated directory rather than overwriting the pinned one, so
# refetching is additive and the pin has to be moved deliberately.
FETCH_DATE := $(shell date -u +%Y-%m-%d)
# Every artefact records which snapshot produced it; see src/adctox/provenance.py.
export ADCTOX_SNAPSHOT = $(SNAPSHOT)
RAW     := /data/hyeongchanahn/adctox/raw
STUDIES := $(RAW)/ctgov/$(DATE)/studies
ELIG    := $(RAW)/eligibility/$(DATE)
PROC    := data/processed
ART     := artifacts

.PHONY: all env taxonomy corpus eligibility enrichment forward propose test \
        censoring-sensitivity label-history label-changes label-change-eval \
        dose-mod dose-mod-eval module-b hard-flags fold-difficulty lint sync-report \
        check-report clean \
        fetch snapshot-check target-expression expression design-effects across-agent

# `make all` has to produce every figure the report quotes, or the claim that the report
# is regenerable is false. It previously omitted the whole of Module B and the censoring
# sensitivity analysis while the report cited both.
all: taxonomy corpus forward censoring-sensitivity expression enrichment module-b \
     propose test hard-flags fold-difficulty design-effects across-agent check-report

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

# Fetches hit government services, write a new dated snapshot, and are deliberately not
# part of `all`. After fetching, move SNAPSHOT to the new date to analyse it.
fetch: eligibility label-history dose-mod target-expression
	@echo "fetched into $(FETCH_DATE); set SNAPSHOT=$(FETCH_DATE) to analyse it"

eligibility:
	$(PY) scripts/fetch_eligibility.py --out $(RAW)/eligibility/$(FETCH_DATE)

# Per-organ target expression, which is what makes the target antigen a real input at all.
# Before it, swapping the target left every candidate, score and estimate bit-identical.
target-expression:
	$(PY) scripts/fetch_target_expression.py --out $(RAW)/opentargets/$(FETCH_DATE)

# Every target below reads the pinned snapshot, so each depends on this guard. Without it
# a missing snapshot surfaces as a FileNotFoundError from inside a script, or worse as an
# empty result, which this project has already been bitten by.
snapshot-check:
	@for d in $(ELIG) $(RAW)/dailymed/$(DATE) $(RAW)/openfda_label/$(DATE) \
	          $(RAW)/opentargets/$(DATE); do \
	  test -d "$$d" || { \
	    echo "missing raw snapshot: $$d"; \
	    echo "run 'make fetch' and then set SNAPSHOT to the new date"; exit 1; }; \
	done

expression: snapshot-check
	$(PY) scripts/build_target_expression.py --raw $(RAW)/opentargets/$(DATE) --out $(ART)

enrichment: snapshot-check
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
	$(PY) scripts/fetch_label_history.py --out $(RAW)/dailymed/$(FETCH_DATE)

dose-mod:
	$(PY) scripts/fetch_dose_mod.py --out $(RAW)/openfda_label/$(FETCH_DATE)

label-changes: snapshot-check
	$(PY) scripts/label_change_events.py --raw $(RAW)/dailymed/$(DATE) --out $(ART)

label-change-eval: corpus label-changes
	$(PY) scripts/label_change_eval.py --processed $(PROC) --out $(ART)

dose-mod-eval: forward snapshot-check
	$(PY) scripts/dose_mod_eval.py --labels $(RAW)/openfda_label/$(DATE) --out $(ART)

propose: corpus
	$(PY) scripts/propose_demo.py --out $(ART)

test: lint
	$(PY) -m pytest tests/ -q

# Guards against a number being typed into the report by hand and then drifting from the
# code that produced it.
# Regenerate the report's fitted-parameter block before checking it, so a refit cannot
# leave the prose quoting last week's posterior. The report had three stale parameters and
# quoted one number as both current and pre-fix.
# How much of the output is the rule layer rather than the fit? Measured, because a rule
# that raises the band the ILD case study is about would make that case study circular.
lint:
	$(PY) scripts/check_unused_imports.py

# What makes a held-out fold hard. Refutes the model card's earlier reading and replaces
# it with a measurement; `make check-report` depends on it so the generated block cannot
# go stale.
# The ratio that explains the headline failure: how large are the fitted design effects
# against the baseline spread they have to move?
# The one positive signal: across-agent organ ranking once between-agent reporting
# conditions are removed from both series. Reported with its caveats, not as a headline.
across-agent: forward
	$(PY) scripts/across_agent_adjusted.py --processed $(PROC) --out $(ART)

design-effects: forward
	$(PY) scripts/design_effect_size.py --out $(ART)

fold-difficulty: forward
	$(PY) scripts/fold_difficulty.py --out $(ART)

hard-flags: forward
	$(PY) scripts/hard_flag_necessity.py --out $(ART)

sync-report:
	$(PY) scripts/sync_report_numbers.py

check-report: hard-flags fold-difficulty design-effects across-agent sync-report
	$(PY) scripts/check_report.py report/

clean:
	rm -rf $(PROC)/*.parquet $(PROC)/*.json $(ART)/*.json $(ART)/*.npz
