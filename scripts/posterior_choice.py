"""Which posterior should the product serve, measured rather than argued?

`/propose` serves one fitted posterior. Two are available -- the registry corpus and the
literature-extended one -- and they differ in ways that pull in opposite directions. The
extended corpus has ten more agents and reaches the plan's 8:1 identification floor at the
mechanism level; it also carries the literature's reporting selection, which section 5g
measures as a negative ablation result, and 33% of its cells are censored against 12%.

So the choice is not obvious and should not be made on which number sounds better. This
reports what actually changes in the product's output: the designs it shows, the bands it
assigns, the ordinal comparisons it prints, and whether it can rank at all. A change the
user would never see is not a reason to prefer either.

What this does not decide: whether the extended posterior predicts *better*. That is the
ablation's question and the ablation answers it on held-out agents. This answers the
different question of whether the answer the product gives moves.
"""

from __future__ import annotations

import argparse
import pathlib

from adctox.model.predict import Posterior
from adctox.pipeline import propose
from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]

PROFILES = {
    "none": [],
    "renal + pulmonary": ["ckd_stage_4_5", "interstitial_lung_disease"],
    "hepatic": ["cirrhosis"],
    "cardiac": ["heart_failure", "reduced_lvef"],
    "neuro + ocular": ["peripheral_neuropathy", "keratopathy_history"],
    "haematologic": ["thrombocytopenia", "mds"],
    "dermatologic": ["severe_psoriasis", "prior_sjs_ten"],
    "four organs": ["cirrhosis", "ckd_stage_4_5", "heart_failure", "dry_eye"],
}
TARGETS = ("ERBB2", "TACSTD2", "NECTIN4", "CD33", "FOLR1", "TNFRSF8")


def _slots(result: dict) -> list[tuple]:
    return [
        (c["design"]["payload"], c["design"]["linker"], c["design"]["dar"])
        for c in result["candidates"]
    ]


def _bands(result: dict) -> dict[tuple, str]:
    return {
        (i, row["organ_axis"]): row["risk_band"]
        for i, c in enumerate(result["candidates"])
        for row in c["organ_risks"]
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=pathlib.Path, default=ROOT / "artifacts")
    ap.add_argument("--b", type=pathlib.Path, default=ROOT / "artifacts" / "expanded")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "posterior_choice.json")
    args = ap.parse_args()

    def load(d: pathlib.Path) -> tuple[Posterior, Posterior | None]:
        other = Posterior.load(d / "posterior_other.npz")
        s = d / "posterior_serious.npz"
        return other, (Posterior.load(s) if s.exists() else None)

    missing = [
        str(d / "posterior_other.npz") for d in (args.a, args.b)
        if not (d / "posterior_other.npz").exists()
    ]
    if missing:
        raise SystemExit(f"absent: {missing}; run `make forward` and the expanded fit")

    post_a, serious_a = load(args.a)
    post_b, serious_b = load(args.b)

    rows = []
    for target in TARGETS:
        for label, conditions in PROFILES.items():
            ra = propose(target, conditions, post_a, top_k=6,
                         serious_posterior=serious_a)
            rb = propose(target, conditions, post_b, top_k=6,
                         serious_posterior=serious_b)
            sa, sb = _slots(ra), _slots(rb)
            ba, bb = _bands(ra), _bands(rb)
            shared = set(ba) & set(bb)
            rows.append({
                "target": target, "profile": label,
                "designs_shown_identical": sa == sb,
                "designs_in_common": len(set(sa) & set(sb)),
                "band_cells_compared": len(shared),
                "band_cells_changed": sum(1 for k in shared if ba[k] != bb[k]),
                "head_group_a": ra["candidates"][0].get("group_size"),
                "head_group_b": rb["candidates"][0].get("group_size"),
                "decisive_a": ra["candidates"][0].get("lead_is_decisive"),
                "decisive_b": rb["candidates"][0].get("lead_is_decisive"),
            })

    n = len(rows)
    summary = {
        "agents_a": len(post_a.agents) or None,
        "agents_b": len(post_b.agents) or None,
        "queries": n,
        "queries_with_identical_designs": sum(
            1 for r in rows if r["designs_shown_identical"]
        ),
        "mean_designs_in_common": round(
            sum(r["designs_in_common"] for r in rows) / n, 2
        ),
        "band_cells_changed": sum(r["band_cells_changed"] for r in rows),
        "band_cells_compared": sum(r["band_cells_compared"] for r in rows),
        "queries_decisive_a": sum(1 for r in rows if r["decisive_a"]),
        "queries_decisive_b": sum(1 for r in rows if r["decisive_b"]),
    }
    summary["band_change_share"] = (
        round(summary["band_cells_changed"] / summary["band_cells_compared"], 3)
        if summary["band_cells_compared"] else None
    )

    print(f"  {'target':10s} {'profile':18s} {'same':>5s} {'common':>7s} "
          f"{'bands changed':>14s}")
    for r in rows:
        print(f"  {r['target']:10s} {r['profile']:18s} "
              f"{str(r['designs_shown_identical']):>5s} {r['designs_in_common']:7d} "
              f"{r['band_cells_changed']:6d}/{r['band_cells_compared']:<7d}")
    print()
    for k, v in summary.items():
        print(f"  {k:32s} {v}")
    write_json(args.out, {"summary": summary, "queries": rows})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
