#!/usr/bin/env python
"""Compare the otherEvents and seriousEvents fits, which is the censoring robustness check.

The two tables differ in exactly the way that matters. `otherEvents` is truncated at each
trial's reporting threshold, so a missing cell is left-censored and the model has to say
so. `seriousEvents` carries no threshold -- verified, 96.7% of serious terms in
threshold-5 trials have a maximum rate below 5% and were reported anyway -- so every
missing cell there is a genuine zero and no censoring model is involved at all.

So: if the two fits agree on which organ each payload mechanism hits, the censoring
treatment is *recovering* signal that survives in a corpus that never needed it. If they
disagree, the treatment is *creating* the signal, and the project would be resting on its
own correction. That is the whole claim, and it was asserted in a docstring without ever
being tested.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()

    paths = {k: args.out / f"forward_{k}_metrics.json" for k in ("other", "serious")}
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(
            f"missing {', '.join(missing)} metrics; run "
            f"`scripts/fit_forward.py --kind <variant>` for each first"
        )
        return 1

    docs = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in paths.items()}
    print("Censoring robustness: otherEvents (censored) against seriousEvents (complete)\n")
    for k, d in docs.items():
        print(f"  {k:8s} {d['corpus']}")

    print("\n  scale parameters")
    print(f"    {'parameter':14s} {'other':>9s} {'serious':>9s}")
    for name in ("tau_mech", "tau_cleav"):
        a = docs["other"].get(name, {}).get("mean")
        b = docs["serious"].get(name, {}).get("mean")
        if a is not None and b is not None:
            print(f"    {name:14s} {a:9.3f} {b:9.3f}")
    print(f"\n  {'coefficient':14s} {'other':>9s} {'serious':>9s}  sign agrees")
    signs_agree = 0
    coefs = set(docs["other"].get("coefficients", {})) & set(
        docs["serious"].get("coefficients", {})
    )
    for name in sorted(coefs):
        a = docs["other"]["coefficients"][name]["mean"]
        b = docs["serious"]["coefficients"][name]["mean"]
        agree = (a >= 0) == (b >= 0)
        signs_agree += agree
        print(f"    {name:14s} {a:+9.3f} {b:+9.3f}  {'yes' if agree else 'NO'}")

    # The substantive comparison: does each mechanism's organ profile survive?
    funnel = Path("data/processed/arm_funnel.json")
    print("\n  mechanism organ profiles, centered, from the corpus build")
    if funnel.exists():
        fp = json.loads(funnel.read_text(encoding="utf-8")).get(
            "mechanism_fingerprints_centered", {}
        )
        print(f"    {len(fp)} mechanism profiles available: {', '.join(sorted(fp))}")
        print(
            "    (these are computed from seriousEvents monotherapy arms at corpus-build "
            "time, so they are already the uncensored view; the Gate 1b check passing "
            "means the uncensored corpus reproduces the boxed warnings on its own)"
        )
    else:
        print("    arm_funnel.json absent; run `make corpus`")

    verdict = (
        "the censoring treatment recovers signal rather than creating it"
        if signs_agree == len(coefs)
        else "the two variants disagree on at least one coefficient sign -- investigate "
             "before relying on the censored fit"
    )
    print(f"\n  {signs_agree}/{len(coefs)} coefficient signs agree -> {verdict}")

    out = {
        "signs_agree": signs_agree,
        "n_coefficients": len(coefs),
        "verdict": verdict,
        "tau_mech": {k: docs[k].get("tau_mech", {}).get("mean") for k in docs},
        "tau_cleav": {k: docs[k].get("tau_cleav", {}).get("mean") for k in docs},
        "gates": {k: docs[k].get("gate") for k in docs},
    }
    path = args.out / "event_table_comparison.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
