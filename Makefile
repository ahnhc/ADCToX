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
# What the post-fit measurements actually consume. They depended on the `forward`
# target, which is .PHONY -- so running any one of them alone refit the whole model,
# about an hour, to produce a file that was already on disk. Inside `make all` the
# phony prerequisite runs once and the waste is invisible, which is why this went
# unnoticed.
#
# And the fix did not work for a second reason, which looked identical from outside. This
# line stood *above* `ART := artifacts`, and `:=` expands immediately, so the prerequisite
# was `/forward_other_metrics.json` -- a path at the filesystem root that never exists.
# Make therefore rebuilt it every single time, exactly as the phony version had. The
# symptom was unchanged, so the first fix appeared to have failed to apply rather than to
# have been undone by a variable order. Definition order matters with `:=`; `=` would have
# deferred the expansion and hidden the ordering entirely.
FORWARD_METRICS := $(ART)/forward_other_metrics.json

.PHONY: all env taxonomy corpus eligibility enrichment forward propose test \
        censoring-sensitivity label-history label-changes label-change-eval \
        dose-mod dose-mod-eval module-b hard-flags fold-difficulty lint sync-report \
        residual-scale comorbidity-sensitivity payload-compression \
        atlas-ingest atlas-merge merged-scale precedent-audit \
        source-confounding-atlas axis-evidence posterior-scales \
        convergence-conditions design-balance \
        check-report clean \
        fetch snapshot-check target-expression expression design-effects across-agent \
        pmc-fetch pmc-yield pmc-extract pmc-validate pmc-merge pmc-merge-explicit \
        corpus-ablation discover mondo-audit mondo-axes exclusion-holdout \
        rank-resolution dar-gap driver-waterfall row-grade-exposure outcome-tables \
        granularity-ratio source-axis source-confounding axis-composition \
        label-impairment inverse-retrieval comorbidity literature expensive \
        pmc-fetch-discovered pmc-fetch-codenames

# `make all` has to produce every figure the report quotes, or the claim that the report
# is regenerable is false. It previously omitted the whole of Module B and the censoring
# sensitivity analysis while the report cited both.
all: taxonomy corpus forward censoring-sensitivity expression enrichment module-b \
     comorbidity literature \
     propose test hard-flags fold-difficulty design-effects across-agent residual-scale \
     comorbidity-sensitivity payload-compression axis-evidence posterior-scales \
     convergence-conditions design-balance \
     rank-resolution driver-waterfall outcome-tables row-grade-exposure dar-gap \
     granularity-ratio source-axis source-confounding axis-composition \
     check-report

# Module B: the dated label-change case series and the dose-modification ordering
# comparison. Both depend on fetched label data, so the fetches are separate targets --
# they hit government services and should not re-run on every build.
module-b: label-changes label-change-eval dose-mod-eval

# The comorbidity layer's own evaluations. Same split as Module B: these read raw snapshots
# that `make fetch` produces and never fetch anything themselves, so `all` can depend on
# them while remaining offline.
#
# `mondo-audit` comes first on purpose. It is the check that found 8 of 41 pinned MONDO
# identifiers naming unrelated diseases, and `mondo-axes` consumes those identifiers -- so
# running the derivation before the audit would derive organs from whatever the pins happen
# to say.
comorbidity: mondo-audit mondo-axes exclusion-holdout label-impairment

# The literature corpus's own measurements, in the order they depend on each other:
# feasibility, then extraction, then the registry comparison, then the merged frames and
# the nested-corpus table the report quotes.
literature: pmc-yield pmc-extract pmc-validate pmc-merge corpus-ablation

# Deliberately not in `all`: one posterior refit per approved agent, about four hours.
# Expensive evaluations are run on request, the way `fetch` is.
expensive: inverse-retrieval

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
# Depends on the corpus *file*, not on the phony `forward`, so it rebuilds when the corpus
# is newer and not on every invocation. `forward` still does the whole job -- both tables
# and both posteriors -- and remains what you run to refit deliberately.
#
# One thing mtimes cannot tell you: `make corpus` rewrites these frames even when it
# reproduces them row for row, so an interrupted build, or a rebuild run for any other
# reason, leaves the frames newer than a fit that is still perfectly valid for them -- and
# every downstream measurement target then pays for a full refit. The provenance input hash
# does not settle it either, because the hashed directory contains stamps carrying their own
# write time (see `src/adctox/provenance.py`). What settles it is comparing the quantities
# the fit scored against the frames on disk: the per-fold, per-axis observed rates in
# `$(ART)/forward_other_fold_predictions.parquet`, which are a pure function of the grid. If
# all of them match, `touch $(ART)/forward_*_metrics.json` is correcting make's bookkeeping
# rather than hiding a stale fit. If any differ, refit.
$(FORWARD_METRICS): $(PROC)/arms.parquet $(PROC)/observations.parquet
	$(PY) scripts/fit_forward.py --processed $(PROC) --out $(ART) --kind other

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
across-agent: $(FORWARD_METRICS)
	$(PY) scripts/across_agent_adjusted.py --processed $(PROC) --out $(ART)

design-effects: $(FORWARD_METRICS)
	$(PY) scripts/design_effect_size.py --out $(ART)

fold-difficulty: $(FORWARD_METRICS)
	$(PY) scripts/fold_difficulty.py --out $(ART)

hard-flags: $(FORWARD_METRICS)
	$(PY) scripts/hard_flag_necessity.py --out $(ART)

# How much of the between-agent variation the seven design slots actually account for:
# sigma_agent over tau_mech, on both tables. The ratio is what the report makes a claim
# about, and it was a hand-written word until it went stale -- see negative result 38.
residual-scale: $(FORWARD_METRICS)
	$(PY) scripts/residual_scale.py --artifacts $(ART) --out $(ART)/residual_scale.json

# The teammate-supplied ADC database. The workbook is not redistributed -- see
# data/raw/atlas/*/_manifest.json for its hash -- so these two targets are skipped rather
# than failed where it is absent. docs/TEAMMATE_DATA_USE.md is the hand-off note.
atlas-ingest:
	$(PY) scripts/ingest_atlas_db.py

# The merge has to run before the scale measurement, because the ladder reads the merged
# grid: the plan's ratio is defined on agents x axes and only the dataset builder knows how
# many agents the grid keeps.
atlas-merge: atlas-ingest
	$(PY) scripts/merge_atlas_corpus.py

merged-scale: atlas-merge
	$(PY) scripts/merged_corpus_scale.py

# Are the hand-curated precedent counts that drive O3 and the Tier-1 gate right? They had
# never been checked against a corpus. See negative result 46.
precedent-audit: atlas-merge
	$(PY) scripts/precedent_audit.py

# The same separability audit on the merged corpus. It answers a question the merge raises
# and does not settle: crossing the identification floor for the *design* terms made the
# *agent* random effect less identifiable, because 42 of the 46 added agents have arms from
# one source only. See negative result 48.
source-confounding-atlas: atlas-merge
	$(PY) scripts/source_confounding_audit.py \
	  --processed $(PROC)/with_atlas --out $(ART)/source_confounding_atlas.json

# How many agents does each organ axis rest on, and which axes stop growing as the corpus
# does? Thirteen of fourteen gain agents; otologic gains nothing from 46 new ones, which is
# negative result 34's reporting selection in its total form.
axis-evidence:
	$(PY) scripts/axis_evidence.py

# Which corpus is each parameter's estimate worth taking from? The identification ratio and
# the agent-source identifiability move in opposite directions, so "bigger" does not decide.
# See negative result 48.
posterior-scales:
	$(PY) scripts/posterior_scales.py

# What makes these fits converge? A prediction that the merged corpus would fail its
# seed-agreement check was written down before it was fitted, and this is where it is
# checked against every fit on disk rather than argued from one case.
convergence-conditions:
	$(PY) scripts/convergence_conditions.py

# Is each design contrast estimated from agents on both sides of it? The report called
# cleavability "the one design axis the corpus identifies comfortably" and the floor was
# being checked against the wrong count. See negative result 54.
design-balance:
	$(PY) scripts/design_balance.py

# Does the comorbidity profile reach the proposed design? The product's primary input
# against its primary output, which had never been measured. See negative result 40.
comorbidity-sensitivity: $(ART)/posterior_other.npz
	$(PY) scripts/comorbidity_sensitivity.py --artifacts $(ART) \
	  --out $(ART)/comorbidity_sensitivity.json

# How much of the payload-level organ spread survives a mechanism-level model? The cost of
# result 6's structural decision, measured at the output. See negative result 41.
payload-compression: $(ART)/posterior_other.npz
	$(PY) scripts/payload_axis_compression.py --processed $(PROC) --artifacts $(ART) \
	  --out $(ART)/payload_axis_compression.json

sync-report:
	$(PY) scripts/sync_report_numbers.py

check-report: hard-flags fold-difficulty design-effects across-agent residual-scale \
               sync-report
	$(PY) scripts/check_report.py report/

clean:
	rm -rf $(PROC)/*.parquet $(PROC)/*.json $(ART)/*.json $(ART)/*.npz

# ---------------------------------------------------------------- literature corpus
# Three PMC snapshots, because the agents were found three ways and each needed its own
# search: the registry agents by INN, the newly discovered agents by INN, and the ten that
# an INN-only search missed by code name. They are separate directories rather than one
# because each has its own fetch funnel and manifest, and merging them would lose the
# record of which route found which agent.
PMC_RAW   := $(RAW)/pmc/$(SNAPSHOT)
PMC_DISC  := $(RAW)/pmc/$(SNAPSHOT)-discovery
PMC_CODE  := $(RAW)/pmc/$(SNAPSHOT)-codename
# Extracted cells are a large intermediate, so they live with the other large outputs
# rather than in `data/processed`, which holds the model's input frames. Writing a 4 MB
# jsonl into the latter is what the project's own layout rule forbids, and having two
# candidate locations for one artefact is how `make literature` came to rebuild a 16-agent
# corpus while the 32-agent one sat somewhere else.
CELLS_DIR := /data/hyeongchanahn/adctox/processed
ALL_CELLS := $(CELLS_DIR)/all_cells.jsonl

pmc-fetch: ## PMC OA candidate discovery + JATS download for every registry agent
	$(PY) scripts/fetch_pmc_candidates.py --out $(RAW)/pmc/$(FETCH_DATE) \
	  --retmax 400

# The two follow-on fetches, kept separate because each answered a different question and
# each is reproducible only with its own agent list. The discovered agents came from
# `make discover`; the code names were harvested from papers whose titles already named the
# INN, which is what makes the mapping evidence rather than recollection -- see
# docs/DATA_SOURCES.md.
pmc-fetch-discovered: ## the agents the stem sweep found, by INN
	$(PY) scripts/fetch_pmc_candidates.py \
	  --out $(RAW)/pmc/$(FETCH_DATE)-discovery --retmax 300 \
	  --inns "$$(cat conf/discovered_agents.txt | tr '\n' ',' | sed 's/,$$//')"

pmc-fetch-codenames: ## the ten an INN-only search missed, by code name
	$(PY) scripts/fetch_pmc_candidates.py \
	  --out $(RAW)/pmc/$(FETCH_DATE)-codename --retmax 300 \
	  --inns "$$(cat conf/codename_agents.txt | tr '\n' ',' | sed 's/,$$//')"

pmc-yield: snapshot-check ## feasibility gate: recoverable agents, image-only rate by journal
	$(PY) scripts/measure_table_yield.py --raw-dir $(PMC_RAW) \
	  --out artifacts/table_yield.json

pmc-extract: snapshot-check ## full extraction funnel -> attributed arm-axis cells
	$(PY) scripts/extract_pmc_cells.py --raw-dir $(PMC_RAW) \
	  --out artifacts/pmc_extraction.json \
	  --cells-out $(CELLS_DIR)/pmc_cells.jsonl
	@test -d $(PMC_DISC) && $(PY) scripts/extract_pmc_cells.py --raw-dir $(PMC_DISC) \
	  --out artifacts/discovery_extraction.json \
	  --cells-out $(CELLS_DIR)/discovery_cells.jsonl || \
	  echo "no discovery snapshot; skipping (run 'make pmc-fetch-discovered')"
	@test -d $(PMC_CODE) && $(PY) scripts/extract_pmc_cells.py --raw-dir $(PMC_CODE) \
	  --out artifacts/codename_extraction.json \
	  --cells-out $(CELLS_DIR)/codename_cells.jsonl || \
	  echo "no code-name snapshot; skipping"
	$(PY) scripts/merge_cell_files.py $(CELLS_DIR)/pmc_cells.jsonl \
	  $(wildcard $(CELLS_DIR)/discovery_cells.jsonl) \
	  $(wildcard $(CELLS_DIR)/codename_cells.jsonl) --out $(ALL_CELLS)

pmc-validate: ## extracted rates vs the registry's own numbers for the same arms
	$(PY) scripts/validate_pmc_against_ctgov.py --cells $(ALL_CELLS) \
	  --out artifacts/pmc_validation.json

MONDO_OBO := $(RAW)/mondo/$(DATE)/mondo.obo

mondo-audit: ## check every pinned MONDO id against what it actually names
	$(PY) scripts/audit_mondo_ids.py --obo $(MONDO_OBO)

mondo-axes: ## derive each comorbidity's organ axes from the MONDO is_a closure
	$(PY) scripts/derive_organ_axes.py --obo $(MONDO_OBO)

# The plan's most important evaluation and its most expensive: one refit per approved
# agent, because a model that has seen a drug's pivotal trials cannot be asked to propose
# its design. Budget about four hours on the registry corpus.
inverse-retrieval:
	$(PY) scripts/inverse_retrieval.py --processed $(PROC) --out $(ART)/inverse_retrieval.json

label-impairment: ## FDA label hepatic/renal guidance vs the model's organ ranking
	$(PY) scripts/label_impairment_eval.py --labels $(RAW)/openfda_label/$(DATE)

exclusion-holdout: ## MONDO organ mapping vs trial exclusion criteria, non-circularly
	$(PY) scripts/exclusion_holdout.py --obo $(MONDO_OBO) --eligibility $(ELIG)

corpus-ablation: ## the three nested corpora, agents/arms/cells/identifying-cells/folds
	$(PY) scripts/corpus_ablation.py

# Can the product rank at all? The tie machinery was written to stop the system ordering
# designs it cannot separate, and whether it ever fires was never measured. It fires on
# every query: 0 of 192 have a decisive leader. In `all` because the report quotes it.
rank-resolution: ## how often the proposal ranking resolves, over targets x profiles
	$(PY) scripts/rank_resolution.py

# Which registry agents still have no drug-to-antibody ratio, and whether the articles
# already on disk state it. In `all`, because the report quotes its figures and the claim
# that `make all` regenerates every number has to hold for them too. It reads the raw PMC
# snapshot and fetches nothing, like the other corpus measurements.
dar-gap: ## search the harvested articles for the registry's missing DAR values
	$(PY) scripts/dar_gap.py

# Does the per-axis explanation add up to the number above it? The waterfall's own gap,
# measured across the design space, because the Jensen's-inequality note beside it is only
# acceptable if the gap is small and that had never been checked.
driver-waterfall: ## the gap between the driver terms' sum and the rate they explain
	$(PY) scripts/driver_waterfall.py

# The outcome filter works on column headers; a grade can also sit in the row label. This
# bounds how often one of those decides an axis, which is 6 observations of 2,696.
row-grade-exposure: ## how often a grade in a row label decides an axis
	$(PY) scripts/row_grade_exposure.py

# Three outcome tables and which can carry the model. The severe-tail columns the any-grade
# grid excludes form a literature-only third table; it reaches more agents than the registry
# and a sixth of the observations per agent, so it is measured and not fitted.
outcome-tables: ## agents, observations and identification ratio per outcome table
	$(PY) scripts/outcome_tables.py

# At which granularity does the identification ratio recede as the corpus grows? The plan
# said every level; measured, only the payload level. Two of its three rows were projections.
granularity-ratio: ## identification ratio by payload / family / mechanism granularity
	$(PY) scripts/granularity_ratio.py

# Is the literature-versus-registry gap one number or fourteen? Measured on the agents with
# arms from both sources, so the chemistry is held fixed: fourteen, Q = 80 on 11 df.
source-axis: ## heterogeneity of the reporting-source gap across organ axes
	$(PY) scripts/source_axis_heterogeneity.py

# Which other coefficients track the corpus an arm was read from? One of five, and it is
# handled; every mechanism level appears in both corpora.
source-confounding: ## audit every arm-level covariate against the source indicator
	$(PY) scripts/source_confounding_audit.py

# What kind of event each axis is made of. MedDRA files laboratory abnormalities under
# `Investigations`, so the taxonomy redistributes them -- and the hepatic axis comes out
# 64% laboratory rows in the registry, against 0-8% for most axes. The interface says so.
axis-composition: ## laboratory share of each organ axis, per source
	$(PY) scripts/axis_composition.py

# Which posterior should the product serve? Not in `all`: it needs the expanded corpus's
# posterior, which `make expensive` territory produces, and a change the user never sees is
# not a reason to prefer either corpus.
posterior-choice: ## what changes in the product's output between the two posteriors
	$(PY) scripts/posterior_choice.py

discover: ## find every ADC that has published, by payload-linker name stem
	$(PY) scripts/discover_adc_agents.py --out $(ART)/adc_discovery.json --retmax 400

pmc-merge: ## fold the extracted cells into the corpus schema the model reads
	$(PY) scripts/merge_literature_corpus.py --cells $(ALL_CELLS) \
	  --union $(PROC)/with_literature_final

# The sensitivity refit the censoring treatment needs: 70% of paper tables state no
# reporting cut, so their cut is an upper bound derived from the minimum printed rate.
# This drops them and keeps only the tables that stated one.
# `--union` is the part that was missing. Without it this target writes only the paper
# frames, and the *merged* corpus the sensitivity refit actually reads --
# `$(PROC)/with_explicit_threshold` -- was produced once by hand and then went stale: it
# held 22 agents while the corpus it is compared against had grown to 34. Fitting it would
# have compared "explicit cuts on 22 agents" against "min-reported cuts on 34", confounding
# the treatment with twelve agents, which is the same defect `corpus_ablation._frames`
# documents for the middle ablation stage. A directory no flag reproduces is a directory
# that drifts.
pmc-merge-explicit:
	$(PY) scripts/merge_literature_corpus.py --cells $(ALL_CELLS) \
	  --explicit-threshold-only --out-dir $(PROC)/explicit_threshold \
	  --union $(PROC)/with_explicit_threshold
