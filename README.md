# ADCTox

Research prototype: given a patient comorbidity profile and a target antigen, propose
ADC designs and predict their organ-system toxicity.

**Not a clinical decision tool.** The request schema contains no free-text patient field,
comorbidities come from a closed list, and nothing is persisted. `tests/test_schemas.py`
asserts those properties.

## Status

**The forward model does not beat a base-rate baseline on any of five evaluations.** The
cut order below has fired, so this ships as a constraint-based design enumerator that
annotates candidates with organ-toxicity estimates, not as a ranking engine. See
`docs/MODEL_CARD.md` first and `report/findings.md` for the full account.

| gate | check | result |
|---|---|---|
| 1a | >=85% of AE mass maps to a real organ axis | **99.94%** of eligible mass |
| 1b | Mechanism fingerprints reproduce known pharmacology | **pass** — calicheamicin tops hepatic, topo-I tops pulmonary and GI, tubulin puts neurologic in its top three |
| 1c | Attribution loss inside ADC-bearing trials | **4 of 948** event groups |
| 2 | Two inputs in, fourteen organ numbers out, end to end | **pass** |
| 3 | Model beats its strongest baseline | **fail** — delta -0.012 to -0.080 across three splits |

Corpus: **285 arms / 16 agents / 3,990 (arm x axis) cells**, of which **224 cells
(16 agents x 14 axes) identify the design coefficients**, because design features are
agent-level constants. Arms do not multiply design information, and an earlier draft of
this project proposed 420 design parameters against those 224 cells.

What the data does support: the mechanism-by-axis interaction is real
(`tau_mech` 0.58 [0.49, 0.69]), the mechanism fingerprints reproduce the boxed warnings
unprompted, and trial exclusion criteria encode organ concern at 4x to 18x enrichment over
an oncology base rate. What it does not support is ranking one candidate design above
another.

Organ risks come from **two event tables, because they rank organs differently** (mean
Spearman +0.15 across five mechanisms). Any-grade events recover the high-frequency label
sections; serious events recover the boxed warnings -- topoisomerase-I payloads sit 10th
of 14 on pulmonary in the first table and 2nd in the second, and the second is the one
that matches ENHERTU's interstitial-lung-disease warning. A declared comorbidity is a
question about serious harm, so axes the patient is vulnerable on are banded on the
serious table and the rest on any-grade, each row stating its basis. Band edges are
measured per table from its own observed rates; they differ by an order of magnitude, so
bands are not comparable across bases.

## Quickstart

```bash
uv venv .venv && uv pip install -e .
.venv/bin/python scripts/build_taxonomy.py --studies <ctgov-studies-dir> --out data/processed
.venv/bin/python scripts/build_arms.py     --studies <ctgov-studies-dir> --out data/processed
```

`make all` reproduces every figure in the report, and reads one pinned raw snapshot --
`SNAPSHOT`, currently 2026-10-07. The pin is the point: these directories are meant to be
immutable, and the variable used to be `date -u +%Y-%m-%d`, so from the day after the
snapshot was taken every analysis target pointed at a directory that did not exist, and a
fetch would have written a *new* snapshot underneath a report whose numbers came from the
old one.

```bash
make all                        # analyse the pinned snapshot
make fetch                      # re-fetch into today's directory (hits live services)
make all SNAPSHOT=2026-11-01    # analyse a different snapshot, deliberately
```

Fetches are not part of `make all`. If a snapshot is missing, `make` stops with the
directory it wanted and the command to run, rather than failing inside a script or
returning an empty result.

## Cut order — decided up front, not renegotiated late

1. Roll unjoinable arms up to drug level rather than discarding them.
2. Restrict SPL/label table parsing to the case-study agents.
3. Collapse 14 axes to the 6 best-populated (last resort).
4. Literature evidence tier -> labels and trials only.
5. Public URL -> local demo plus screencast.
6. **Never cut**: the four case studies, the censored likelihood, the novelty tiering,
   `source: model/rule` separation, and the measured negative results.

## Hard gates

- Mechanism taxonomy frozen before any extraction (`conf/mechanism_taxonomy.yaml`).
- Corpus frozen end of week 5 regardless of agent count.
- Forward-model underperformance is defined in advance: macro AUC < 0.65 across the 14
  axes on held-out agents triggers the cut order.
