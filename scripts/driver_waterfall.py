"""Does the per-axis explanation add up to the number above it?

Every organ row carries a waterfall of the fitted terms that produced its rate, each with
its source, plus the label rules and expression flags that may have raised its band. The
response also reports the gap between those terms' sum and the rate shown, with a note
saying the difference is Jensen's inequality: the terms are posterior means in logit space,
so they decompose the mean logit exactly and the mean rate only approximately.

That note is only acceptable if the gap is small, and it had never been measured. This
measures it across the design space and the comorbidity profiles, and writes the figures the
report quotes. The failure it guards against is a term added to the model and not to the
decomposition -- not hypothetical, since the model terms were once omitted from the driver
list altogether, leaving a banded axis showing a band and a weight with no account of
either.
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
from fastapi.testclient import TestClient

from adctox.api.main import app
from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]

# One per payload mechanism where the design space allows it, with a feasible linker and
# conjugation for each. Not every slot combination: the waterfall is a property of the
# model terms, and the terms that vary across these are the ones it decomposes.
DESIGNS = [
    ("DXd", "GGFG", "interchain_cysteine", 8.0),
    ("MMAE", "vc_PABC", "interchain_cysteine", 4.0),
    ("DM1", "SMCC", "lysine", 3.5),
    ("MMAF", "mc", "interchain_cysteine", 4.0),
    ("SG3199", "val_ala_PABC_PEG8", "interchain_cysteine", 2.0),
    ("DGN549", "SMCC", "lysine", 2.0),
]
PROFILES = {
    "none": [],
    "hepatic": ["cirrhosis"],
    "renal + pulmonary": ["ckd_stage_4_5", "interstitial_lung_disease"],
    "dermatologic": ["severe_psoriasis"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "driver_waterfall.json")
    args = ap.parse_args()

    client = TestClient(app)
    gaps: list[float] = []
    rows: list[dict] = []
    for payload, linker, conj, dar in DESIGNS:
        for label, conditions in PROFILES.items():
            r = client.post("/api/v1/assess", json={
                "design": {
                    "target_antigen": "ERBB2", "payload": payload, "linker": linker,
                    "conjugation": conj, "dar": dar,
                    "isotype": "IgG1", "masking": "none",
                },
                "comorbidity_profile": {"conditions": conditions},
            })
            if r.status_code != 200:
                raise SystemExit(f"{payload}/{label}: {r.status_code} {r.text[:200]}")
            here = [
                abs(row["driver_sum"]["gap"])
                for row in r.json()["organ_risks"]
                if (row.get("driver_sum") or {}).get("gap") is not None
            ]
            gaps += here
            rows.append({
                "payload": payload, "profile": label,
                "axes": len(here),
                "worst_gap": max(here) if here else None,
            })

    g = np.asarray(gaps, dtype=float)
    summary = {
        "designs": len(DESIGNS),
        "profiles": len(PROFILES),
        "rows_checked": int(g.size),
        "worst_gap": float(g.max()),
        "median_gap": float(np.median(g)),
        "mean_gap": float(g.mean()),
        "rows_over_1pp": int((g > 0.01).sum()),
        "bound_the_test_holds": 0.01,
    }
    print(f"  {'payload':10s} {'profile':18s} {'axes':>5s} {'worst':>9s}")
    for row in rows:
        print(f"  {row['payload']:10s} {row['profile']:18s} {row['axes']:5d} "
              f"{row['worst_gap']:9.6f}")
    print()
    for k, v in summary.items():
        print(f"  {k:24s} {v}")
    write_json(args.out, {"summary": summary, "rows": rows})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
