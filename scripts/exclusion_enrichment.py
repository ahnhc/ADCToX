#!/usr/bin/env python
"""Measure per-payload-mechanism organ-concern enrichment over an oncology base rate.

The claim this supports, and its exact limits:

*Supported*: trial protocols encode an expert prior about which organ a payload
threatens, and that prior is recoverable at an order of magnitude more trials than have
posted results.

*Not supported*: that the model anticipated anything. For most agents the warning this
recovers was already in the label at approval, so agreement here is **consistency, not
prediction**. The only genuinely anticipatory targets in the public record are dated
post-approval label changes, which are a separate analysis.

Boilerplate control is the whole method. Every oncology protocol has bilirubin,
creatinine and LVEF floors, so raw frequencies are uninformative; it is the ratio to the
control cohort that separates a real drug-specific concern from a universal lab floor.
A Fisher exact test and a Haldane-corrected ratio are reported per cell so a 1-trial
mechanism cannot produce an impressive-looking enrichment unchallenged.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from scipy.stats import fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

from adctox.extract.arm_resolver import Registry  # noqa: E402
from adctox.extract.organ_concern import OrganConcernExtractor  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eligibility", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    ap.add_argument("--polarity", default=None,
                    help="restrict to one polarity (exclusion / lab_floor / monitoring)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    ex = OrganConcernExtractor()
    registry = Registry.load()
    mech_of = {k: v["mechanism"] for k, v in registry.agents.items()}

    adc = json.loads((args.eligibility / "adc_trials.json").read_text(encoding="utf-8"))
    ctrl = json.loads((args.eligibility / "control_trials.json").read_text(encoding="utf-8"))
    adc = [t for t in adc if t.get("eligibility")]
    ctrl = [t for t in ctrl if t.get("eligibility")]
    print(f"ADC trials with eligibility text : {len(adc):,}")
    print(f"Oncology control trials          : {len(ctrl):,}")

    def flags(text: str) -> dict[str, bool]:
        return (
            ex.flags_by_polarity(text, args.polarity) if args.polarity else ex.flags(text)
        )

    organs = ex.organs
    # An organ with no patterns of the requested polarity has a base rate of zero, and a
    # Haldane-corrected ratio against zero is a fabricated number, not a weak one. Those
    # organs are marked N/A rather than reported -- otherwise the table shows figures like
    # 330x for an organ that has no lab-floor pattern at all.
    if args.polarity:
        applicable = {
            organ: any(
                pat.polarity == args.polarity for pat in ex._patterns if pat.organ == organ
            )
            for organ in organs
        }
        skipped = [o for o, ok in applicable.items() if not ok]
        if skipped:
            print(f"\nNot applicable at polarity '{args.polarity}' "
                  f"(no such pattern): {', '.join(skipped)}")
        organs = [o for o in organs if applicable[o]]
    
    base_hits = {o: 0 for o in organs}
    for t in ctrl:
        f = flags(t["eligibility"])
        for o in organs:
            base_hits[o] += bool(f[o])
    base_rate = {o: base_hits[o] / max(len(ctrl), 1) for o in organs}

    # Group ADC trials by payload mechanism. A trial testing two ADCs of different
    # mechanisms is counted under each, which is correct: the protocol was written with
    # both in mind.
    by_mech: dict[str, list[dict]] = defaultdict(list)
    for t in adc:
        mechs = {mech_of[a] for a in t.get("adc_agents", []) if a in mech_of}
        for m in mechs:
            by_mech[m].append(t)

    print(f"\n{'cohort':16s} {'n':>5s}  " + "  ".join(f"{o[:9]:>9s}" for o in organs))
    print(f"{'base: oncology':16s} {len(ctrl):5d}  " +
          "  ".join(f"{100 * base_rate[o]:8.1f}%" for o in organs))

    rows = []
    for mech, trials in sorted(by_mech.items(), key=lambda kv: -len(kv[1])):
        hits = {o: 0 for o in organs}
        for t in trials:
            f = flags(t["eligibility"])
            for o in organs:
                hits[o] += bool(f[o])
        cells = []
        for o in organs:
            a, b = hits[o], len(trials) - hits[o]
            c, d = base_hits[o], len(ctrl) - base_hits[o]
            # Haldane-Anscombe correction keeps a zero cell from producing inf/0.
            ratio = ((a + 0.5) / (b + 0.5)) / ((c + 0.5) / (d + 0.5))
            try:
                _, p = fisher_exact([[a, b], [c, d]])
            except ValueError:
                p = float("nan")
            cells.append({"organ": o, "n_hit": a, "n": len(trials),
                          "rate": a / max(len(trials), 1), "odds_ratio": ratio, "p": p})
        rows.append({"mechanism": mech, "n_trials": len(trials), "cells": cells})
        print(f"{mech:16s} {len(trials):5d}  " +
              "  ".join(f"{c['odds_ratio']:8.1f}x" for c in cells))

    # Boilerplate diagnostic: an organ whose enrichment is flat across every mechanism is
    # a universal lab floor, not a signal. Reporting this is what makes the large ratios
    # elsewhere credible.
    print(f"\nBoilerplate check (spread across mechanisms with >=100 trials)")
    print(f"  {'organ':20s} {'min':>7s} {'max':>7s} {'max/min':>8s}  verdict")
    for i, o in enumerate(organs):
        vals = [r["cells"][i]["odds_ratio"] for r in rows if r["n_trials"] >= 100]
        if len(vals) < 2:
            continue
        lo, hi = min(vals), max(vals)
        spread = hi / lo if lo > 0 else float("inf")
        verdict = "discriminative" if spread >= 4 else "boilerplate"
        print(f"  {o:20s} {lo:7.2f} {hi:7.2f} {spread:8.1f}  {verdict}")

    out = {
        "n_adc": len(adc), "n_control": len(ctrl), "polarity": args.polarity,
        "base_rate": base_rate, "by_mechanism": rows,
    }
    suffix = f"_{args.polarity}" if args.polarity else ""
    path = args.out / f"exclusion_enrichment{suffix}.json"
    write_json(path, out, {"eligibility": args.eligibility})
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
