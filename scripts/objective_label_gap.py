"""Does `worst_axis_risk` equal the risk on `worst_axis`? Not exactly, and by how much.

The two fields sit adjacent in every candidate card and in the API response, and they are
computed differently. The axis is `argmax_a mean_draws(p_a)`; the risk is
`mean_draws(max_a p_a)`. Max-then-mean is never smaller than mean-then-max, and the two
differ whenever the worst axis is not the same axis in every posterior draw.

That is the project's recurring defect in the product's own output: a field whose name says
"the risk on that axis" carrying "the expected worst risk across axes". It is not a bug in
either quantity -- the risk is objective O2 as the plan defines it, `min max_o p_o`, and the
objective has to be the expectation of the maximum or a candidate that is terrible on a
different organ in every draw would score well. The axis is a display label for it.

So the question is not which is right but whether the gap is large enough to mislead. The
interface prints risks to two significant figures, so a gap under 0.005 can never change a
displayed digit and a gap over 0.01 sometimes will. This sweeps the product's own query
space and reports the distribution, the worst case, and the share of candidates where the
gap would move a displayed figure.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The API rounds both fields to four decimals, so a difference of this size carries no
# information about the aggregation. Anything at or below it is reported as zero.
ROUNDING = 1.5e-4

# The same profiles the rank-resolution sweep uses, so the two artefacts describe one query
# space. Conditions are ids from the closed list; the empty profile is the unweighted case,
# where the weighted and unweighted fields must coincide exactly.
PROFILES: list[list[str]] = [
    [],
    ["ckd_stage_4_5"],
    ["interstitial_lung_disease"],
    ["peripheral_neuropathy"],
    ["heart_failure", "reduced_lvef"],
    ["cirrhosis"],
    ["ckd_stage_4_5", "peripheral_neuropathy"],
    ["thrombocytopenia", "mds", "prior_hsct", "neutropenia_chronic"],
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "objective_label_gap.json")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--targets", type=int, default=6,
                    help="how many registry targets to sweep, in registry order")
    args = ap.parse_args()

    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    targets = [t["id"] for t in client.get("/api/v1/ontology").json()["targets"]]
    targets = targets[: args.targets]

    rows: list[dict] = []
    for target in targets:
        for profile in PROFILES:
            resp = client.post("/api/v1/propose", json={
                "comorbidity_profile": {
                    "conditions": profile,
                    "cohort": {"age_band": "65_74", "sex": "female"},
                },
                "target_antigen": target,
                "top_k": args.top_k,
            })
            if resp.status_code != 200:
                rows.append({"target": target, "profile": profile,
                             "status": resp.status_code})
                continue
            doc = resp.json()
            weights = doc["weights_applied"]
            for cand in doc["candidates"]:
                risk = {o["organ_axis"]: o["point_estimate"] for o in cand["organ_risks"]}
                rows.append({
                    "target": target,
                    "profile": profile,
                    "design": cand["design"],
                    "unweighted_gap": round(
                        cand["worst_axis_risk"] - risk[cand["worst_axis"]], 6),
                    "weighted_gap": round(
                        cand["weighted_worst_axis_risk"]
                        - weights[cand["weighted_worst_axis"]]
                        * risk[cand["weighted_worst_axis"]], 6),
                    "axes_agree": cand["worst_axis"] == cand["weighted_worst_axis"],
                    "weighted_worst_axis_weight": weights[cand["weighted_worst_axis"]],
                })

    scored = [r for r in rows if "unweighted_gap" in r]
    if not scored:
        print("no candidate scored; is the posterior on disk?")
        return 1
    uw = np.array([r["unweighted_gap"] for r in scored])
    wt = np.array([r["weighted_gap"] for r in scored])

    # Two significant figures is the interface's rule, so a rate near 0.33 displays to
    # 0.005 and a gap below that can never move a digit. Above 0.01 it sometimes will.
    DISPLAY_RESOLUTION = 0.005
    out = {
        "queries": len({(r["target"], tuple(r["profile"])) for r in scored}),
        "candidates": len(scored),
        "targets": targets,
        "profiles": PROFILES,
        "display_resolution": DISPLAY_RESOLUTION,
        "unweighted": _summarise(uw, DISPLAY_RESOLUTION),
        "weighted": _summarise(wt, DISPLAY_RESOLUTION),
        # Both fields come out of the API rounded to four decimals, so a gap that is
        # truly zero can read as -1e-4. The tolerance is that rounding and not a fudge: a
        # 1e-9 threshold reported Jensen as violated on every run, which is a measurement
        # of the response format rather than of the model.
        "rounding_tolerance": ROUNDING,
        "negative_gaps": int((uw < -ROUNDING).sum() + (wt < -ROUNDING).sum()),
        "reading": (
            "The axis is the argmax of the mean and the risk is the mean of the maximum, "
            "so the risk is the expected worst rate across axes and not the rate on the "
            "named axis. Both are correct quantities -- the risk is objective O2 as the "
            "plan defines it -- and the field name says the second. The gap is what "
            "decides whether that matters."
        ),
    }
    # A negative gap beyond the rounding is impossible: the mean of a maximum cannot fall
    # below the maximum of the means. One would mean the two fields were computed from
    # different draws or different weights.
    out["jensen_holds"] = out["negative_gaps"] == 0
    write_json(args.out, out, {})

    for name, s in (("unweighted", out["unweighted"]), ("weighted", out["weighted"])):
        print(f"{name:11s} median {s['median']:+.6f}  p95 {s['p95']:+.6f}  "
              f"max {s['max']:+.6f}  over display resolution: "
              f"{s['share_over_display_resolution'] * 100:.1f}%")
    print(f"{out['candidates']} candidates over {out['queries']} queries; "
          f"Jensen holds: {out['jensen_holds']}")
    print(f"-> {args.out}")
    return 0


def _summarise(gaps: np.ndarray, resolution: float) -> dict:
    return {
        "n": int(gaps.size),
        "median": round(float(np.median(gaps)), 6),
        "mean": round(float(gaps.mean()), 6),
        "p95": round(float(np.percentile(gaps, 95)), 6),
        "max": round(float(gaps.max()), 6),
        "share_zero_within_rounding": round(float((np.abs(gaps) <= ROUNDING).mean()), 4),
        "share_over_display_resolution": round(float((gaps > resolution).mean()), 4),
    }


if __name__ == "__main__":
    raise SystemExit(main())
