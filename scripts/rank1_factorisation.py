"""The plan's only lever for improving identification without new agents, and it is dead.

Every route to a better cells-per-parameter ratio in this project needs more agents, and
the ceiling is measured: about 54 from the literature, 65 with the collaborator's database,
and no path beyond. The plan names one exception -- *"범주형 × 축은 필요 시 rank-1 인자화로
파라미터 축소"* -- a rank-1 factorisation of the mechanism-by-axis interaction, which would
replace `K x A` free effects with a mechanism scale times an axis profile.

The arithmetic is attractive. The interaction is identified as `(K-1) x A = 56` of the 100
design parameters; rank 1 needs `K + A - 1 = 18`. Against 308 identifying cells that moves
the ratio from 3.08:1 to about 4.97:1, which is the largest single improvement available to
this corpus and costs nothing to collect.

What it costs instead is what the factorisation assumes: that every mechanism has the *same*
organ profile up to one multiplier. This scores that assumption against the fitted
posterior, three ways -- how much of the matrix rank 1 reproduces, whether each mechanism's
organ *ordering* survives, and whether any mechanism needs a negative multiplier, which
would mean its profile is the mirror image of the shared one rather than a scaled copy.

The ordering is the one that matters. A factorisation that loses variance but keeps each
mechanism's worst organ in place would still be usable, because the product's output is a
ranking. One that moves the worst organ is not, whatever its variance share.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model.predict import Posterior  # noqa: E402
from adctox.provenance import write_json  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

# How many posterior draws to factorise individually. The mean matrix is one object and its
# rank-1 share is one number; the per-draw distribution says whether that number is a
# property of the posterior or of the averaging.
N_DRAWS = 200


def _rank1(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    u, s, vt = np.linalg.svd(matrix, full_matrices=False)
    return np.outer(u[:, 0] * s[0], vt[0]), u[:, 0] * s[0], vt[0], s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--posterior", type=pathlib.Path,
                    default=ROOT / "artifacts" / "posterior_other.npz")
    ap.add_argument("--metrics", type=pathlib.Path,
                    default=ROOT / "artifacts" / "forward_other_metrics.json",
                    help="for the identifying-cell count the ratio is computed against")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "rank1_factorisation.json")
    args = ap.parse_args()

    post = Posterior.load(args.posterior)
    draws = np.asarray(post.mech_axis)
    mean = draws.mean(axis=0)
    K, A = mean.shape
    approx, scales, profile, sv = _rank1(mean)
    share = (sv ** 2) / (sv ** 2).sum()

    step = max(1, draws.shape[0] // N_DRAWS)
    per_draw = []
    for d in range(0, draws.shape[0], step):
        s = np.linalg.svd(draws[d], compute_uv=False)
        per_draw.append(float((s ** 2 / (s ** 2).sum())[0]))

    rows = []
    for i, mech in enumerate(post.mechanisms):
        full_order = np.argsort(-mean[i])
        r1_order = np.argsort(-approx[i])
        rows.append({
            "mechanism": mech,
            "scale": round(float(scales[i]), 4),
            "scale_is_negative": bool(scales[i] < 0),
            "ordering_spearman": round(float(stats.spearmanr(mean[i], approx[i]).statistic), 4),
            "worst_axis_full": post.axes[int(full_order[0])],
            "worst_axis_rank1": post.axes[int(r1_order[0])],
            "worst_axis_preserved": bool(full_order[0] == r1_order[0]),
            "top3_preserved": sorted(full_order[:3].tolist()) == sorted(r1_order[:3].tolist()),
        })

    identified_full = (K - 1) * A
    identified_rank1 = K + A - 1
    # The ratio the saving would buy, computed rather than quoted. It was typed as "about
    # 4.97:1" and the number guard caught it, which is the guard working: the figure
    # depends on the fit's design-parameter count and its identifying cells, and both move.
    import json as _json

    ratio_now = ratio_rank1 = None
    if args.metrics.exists():
        par = _json.loads(args.metrics.read_text(encoding="utf-8"))["parameters"]
        cells, design = par["identifying_cells"], par["design"]
        ratio_now = round(cells / design, 2)
        ratio_rank1 = round(cells / (design - (identified_full - identified_rank1)), 2)
    out = {
        "mechanisms": list(post.mechanisms),
        "axes": list(post.axes),
        "singular_value_share": [round(float(x), 4) for x in share],
        "rank1_share_of_mean_matrix": round(float(share[0]), 4),
        "rank2_share_of_mean_matrix": round(float(share[:2].sum()), 4),
        "rank1_share_per_draw": {
            "n_draws_scored": len(per_draw),
            "median": round(float(np.median(per_draw)), 4),
            "q05": round(float(np.percentile(per_draw, 5)), 4),
            "q95": round(float(np.percentile(per_draw, 95)), 4),
        },
        "parameters": {
            "full_interaction_identified": identified_full,
            "rank1_identified": identified_rank1,
            "saved": identified_full - identified_rank1,
            "identification_ratio_now": ratio_now,
            "identification_ratio_under_rank1": ratio_rank1,
        },
        "shared_profile_most_to_least": [
            post.axes[int(j)] for j in np.argsort(-profile)
        ],
        "per_mechanism": rows,
        "worst_axis_preserved": sum(1 for r in rows if r["worst_axis_preserved"]),
        "negative_scales": [r["mechanism"] for r in rows if r["scale_is_negative"]],
        "verdict": None,
        "reading": (
            "A rank-1 interaction says every mechanism shares one organ profile up to a "
            "multiplier. The variance share says how much of the fitted matrix that "
            "reproduces; the per-mechanism ordering says whether the product's output "
            "survives it. A negative multiplier is the sharper failure: it does not scale "
            "the shared profile, it inverts it, which as biology says one mechanism's "
            "organ profile is the mirror image of another's."
        ),
    }
    preserved = out["worst_axis_preserved"]
    out["verdict"] = (
        "usable" if preserved == len(rows) and not out["negative_scales"] else
        f"not usable: the worst organ moves for {len(rows) - preserved} of {len(rows)} "
        f"mechanisms"
        + (f" and {len(out['negative_scales'])} need an inverted profile"
           if out["negative_scales"] else "")
    )
    write_json(args.out, out, {"posterior": args.posterior})

    print(f"mechanism x axis is {K} x {A}; rank 1 reproduces "
          f"{out['rank1_share_of_mean_matrix'] * 100:.1f}% of the mean matrix "
          f"(rank 2: {out['rank2_share_of_mean_matrix'] * 100:.1f}%), and "
          f"{out['rank1_share_per_draw']['median'] * 100:.1f}% of a typical draw")
    print(f"identified design parameters {identified_full} -> {identified_rank1}, "
          f"saving {out['parameters']['saved']}"
          + (f"; identification ratio {ratio_now}:1 -> {ratio_rank1}:1"
             if ratio_now else ""))
    print(f"\n{'mechanism':16s} {'scale':>8s} {'rho':>8s} {'worst (full)':>20s} "
          f"{'worst (rank 1)':>20s}")
    for r in rows:
        print(f"{r['mechanism']:16s} {r['scale']:+8.3f} {r['ordering_spearman']:+8.3f} "
              f"{r['worst_axis_full']:>20s} {r['worst_axis_rank1']:>20s}"
              f"{'' if r['worst_axis_preserved'] else '   <- MOVED'}")
    print(f"\nshared profile, most to least susceptible: "
          f"{', '.join(out['shared_profile_most_to_least'][:5])} ...")
    if out["negative_scales"]:
        print(f"mechanisms needing an inverted profile: {out['negative_scales']}")
    print(f"\nverdict: {out['verdict']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
