# ADCTox

Research prototype: given a patient comorbidity profile and a target antigen, propose
ADC designs and predict their organ-system toxicity.

**Not a clinical decision tool.** The request schema contains no free-text patient field,
comorbidities come from a closed list, and nothing is persisted. `tests/test_schemas.py`
asserts those properties.

## Status

Week 1 in progress. Gates passed so far:

| Gate | Check | Result |
|---|---|---|
| 1a | >=85% of AE mass maps to a real organ axis | **99.94%** of eligible mass |
| 1b | Mechanism organ fingerprints reproduce known pharmacology | **PASS** (calicheamicin->hepatic +0.70, topo1->pulmonary/GI top-2, tubulin->neurologic top-3) |

Corpus as built: **288 arms / 17 agents / 3,674 (arm x axis) cells**, of which
**238 cells (17 agents x 14 axes) actually identify the design coefficients** — design
features are agent-level constants, so arms do not multiply design information.

## Quickstart

```bash
uv venv .venv && uv pip install -e .
.venv/bin/python scripts/build_taxonomy.py --studies <ctgov-studies-dir> --out data/processed
.venv/bin/python scripts/build_arms.py     --studies <ctgov-studies-dir> --out data/processed
```

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
