"""How much of the payload-level organ spread can the product express?

Result 6 established that a payload-level by-axis interaction is unidentifiable at any
corpus size the field will produce, and the model is specified at the mechanism level
instead. That was a modelling decision taken on identification grounds and it is correct.
This measures what it costs at the output, which had never been quantified.

The test is confined *inside* each payload mechanism, because that is where the model has
nothing left to say: two designs sharing a mechanism differ only by linker cleavability,
DAR and the arm-level covariates, so their predicted organ profiles are nearly the same by
construction. If the agents in that mechanism show a wide spread on some organ, the model
cannot reproduce it for a design it has not seen -- the spread is real, it is absorbed into
`u_agent`, and `u_agent` is set to zero when scoring a proposal.

Ocular is the case that matters. MMAF corneal toxicity is among the best-established organ
effects in the whole field, and MMAF, MMAE, DM1 and DM4 are one mechanism.

Two honest caveats, both of which cut the same way. The observed per-payload means are
confounded with indication, line of therapy and trial: they are an upper bound on what a
payload term could explain, not an estimate of it. And the model's spread is computed with
the agent residual off, which is the configuration a proposal is actually scored in. So the
ratio below bounds the gap rather than estimating it, and the bound is the point: wherever
the observed spread is wide and the predicted spread is flat, the product returns a
mechanism average and cannot do otherwise.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.model import dataset as ds
from adctox.model.dataset import OBSERVED
from adctox.model.predict import Posterior, predict_draws
from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]

# A mechanism needs this many distinct payloads before "spread across payloads within the
# mechanism" means anything.
MIN_PAYLOADS = 2
# And a payload needs this many observed arm-axis cells before its mean is worth comparing.
MIN_CELLS = 3


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation without a scipy dependency, which this repo avoids in scripts."""
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = float(np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))
    return 0.0 if denom == 0 else float((ra * rb).sum() / denom)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed", type=pathlib.Path, default=ROOT / "data" / "processed")
    ap.add_argument("--artifacts", type=pathlib.Path, default=ROOT / "artifacts")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "payload_axis_compression.json")
    args = ap.parse_args()

    tax = Taxonomy()
    axes = list(tax.axis_order)
    data = ds.load(args.processed, axes, kind="other")
    arms = pd.read_parquet(args.processed / "arms.parquet")
    payload_of = (
        arms.dropna(subset=["agent", "payload"])
        .drop_duplicates("agent").set_index("agent")["payload"].to_dict()
    )
    mech_of = (
        arms.dropna(subset=["agent", "mechanism"])
        .drop_duplicates("agent").set_index("agent")["mechanism"].to_dict()
    )

    agent_of_cell = np.array([data.agents[i] for i in data.arm_agent_idx])[data.arm_idx]
    observed = data.status == OBSERVED
    rate = data.n_affected / np.maximum(data.n_at_risk, 1)

    post = Posterior.load(args.artifacts / "posterior_other.npz")

    rows = []
    for ai, axis in enumerate(axes):
        sel = observed & (data.axis_idx == ai)
        if not sel.any():
            continue
        frame = pd.DataFrame({
            "agent": agent_of_cell[sel],
            "rate": rate[sel],
        })
        frame["payload"] = frame.agent.map(payload_of)
        frame["mechanism"] = frame.agent.map(mech_of)
        frame = frame.dropna(subset=["payload", "mechanism"])
        for mech, sub in frame.groupby("mechanism"):
            per = sub.groupby("payload")["rate"].agg(["mean", "count"])
            per = per[per["count"] >= MIN_CELLS]
            if len(per) < MIN_PAYLOADS:
                continue
            lo, hi = float(per["mean"].min()), float(per["mean"].max())
            # The model's own spread over the same payloads, scored the way a proposal is
            # scored: each real agent's slots, agent residual off. Inside a mechanism the
            # only levers left are the payload family -- which the fit has disabled, so it
            # contributes nothing -- cleavability and DAR. That is the whole vocabulary the
            # product has for telling MMAF from DM1.
            if mech not in post.mechanisms:
                continue
            slots = (
                arms[arms.agent.isin(sub.agent.unique())]
                .dropna(subset=["payload", "linker_cleavable", "dar"])
                .drop_duplicates("payload")
            )
            slots = slots[slots.payload.isin(per.index)]
            if len(slots) < MIN_PAYLOADS:
                continue
            draws = predict_draws(
                post,
                mechanisms=[mech] * len(slots),
                families=[
                    f if isinstance(f, str) else "" for f in slots.payload_family
                ],
                dars=slots.dar.to_numpy(dtype=float),
                cleavables=slots.linker_cleavable.to_numpy().astype(bool),
                include_agent_variation=False,
            )
            pred = draws[:, :, ai].mean(axis=0)
            preds = [float(x) for x in pred]
            model_by_payload = {
                str(pl): round(float(x), 4)
                for pl, x in zip(slots.payload, pred)
            }
            rows.append({
                "axis": axis,
                "mechanism": mech,
                "n_payloads": int(len(per)),
                "payloads": {k: round(float(v), 4) for k, v in per["mean"].items()},
                # Counts beside the means, and the largest rate in the comparison. A fold
                # computed on rates of a few per thousand is arithmetic rather than a
                # finding, and the report has to be able to tell the two apart: otologic
                # shows the largest fold in this table on rates under 5%.
                "payload_cells": {k: int(v) for k, v in per["count"].items()},
                "observed_max_rate": round(hi, 4),
                "observed_lo": round(lo, 4),
                "observed_hi": round(hi, 4),
                "observed_fold": round(hi / lo, 2) if lo > 0 else None,
                "model_by_payload": model_by_payload,
                "model_lo": round(min(preds), 4) if preds else None,
                "model_hi": round(max(preds), 4) if preds else None,
                "model_fold": (
                    round(max(preds) / min(preds), 2)
                    if preds and min(preds) > 0 else None
                ),
            })

    # Which granularity actually carries the signal? `granularity_ratio.py` answers the
    # identification side -- how many cells per parameter each level would need. This is the
    # other half: given the observations, how much of the within-mechanism spread does each
    # level explain? The plan asserts the ocular axis is driven by "payload family plus a
    # non-cleavable indicator". Both are testable and neither survives, because the two
    # high-ocular payloads straddle both families and both cleavability values.
    granularity = []
    for ai, axis in enumerate(axes):
        sel = observed & (data.axis_idx == ai)
        if not sel.any():
            continue
        frame = pd.DataFrame({"agent": agent_of_cell[sel], "rate": rate[sel]})
        for col, src in (("payload", payload_of), ("mechanism", mech_of)):
            frame[col] = frame.agent.map(src)
        frame["family"] = frame.agent.map(
            arms.dropna(subset=["agent", "payload_family"])
            .drop_duplicates("agent").set_index("agent")["payload_family"].to_dict()
        )
        frame["cleavable"] = frame.agent.map(
            arms.dropna(subset=["agent", "linker_cleavable"])
            .drop_duplicates("agent").set_index("agent")["linker_cleavable"].to_dict()
        )
        frame = frame.dropna(subset=["payload", "mechanism", "family", "cleavable"])
        for mech, sub in frame.groupby("mechanism"):
            if sub.payload.nunique() < 3:
                continue
            row = {"axis": axis, "mechanism": mech,
                   "n_payloads": int(sub.payload.nunique())}
            for level in ("payload", "family", "cleavable"):
                means = sub.groupby(level)["rate"].mean()
                row[f"{level}_levels"] = int(len(means))
                row[f"{level}_fold"] = (
                    round(float(means.max() / means.min()), 2)
                    if len(means) > 1 and means.min() > 0 else None
                )
            granularity.append(row)

    usable = [r for r in rows if r["observed_fold"] and r["model_fold"]]
    for r in usable:
        r["compression"] = round(r["observed_fold"] / r["model_fold"], 2)
        # Compression is about magnitude. The sharper question is whether the model gets the
        # *order* of the payloads right inside the mechanism, because a flat prediction that
        # at least ranks them could still be useful and one that inverts them cannot.
        common = [k for k in r["payloads"] if k in r["model_by_payload"]]
        if len(common) >= 3:
            obs = np.array([r["payloads"][k] for k in common])
            mod = np.array([r["model_by_payload"][k] for k in common])
            r["within_mechanism_spearman"] = round(_spearman(obs, mod), 4)
            r["n_payloads_ranked"] = len(common)
    usable.sort(key=lambda r: -(r["compression"] or 0))

    doc = {
        "thresholds": {"min_payloads": MIN_PAYLOADS, "min_cells": MIN_CELLS},
        "rows": rows,
        "granularity": granularity,
        "summary": {
            "n_axis_mechanism_pairs": len(rows),
            "n_comparable": len(usable),
            "worst": usable[0] if usable else None,
            "within_mechanism_spearman": {
                f"{r['axis']}/{r['mechanism']}": r["within_mechanism_spearman"]
                for r in usable if "within_mechanism_spearman" in r
            },
            # Mean rank agreement is the headline rather than any single axis: with four
            # payloads a single rho takes one of ten values, so one axis is noisy and the
            # average over the axes is the statement.
            "mean_within_mechanism_spearman": (
                round(float(np.mean([
                    r["within_mechanism_spearman"] for r in usable
                    if "within_mechanism_spearman" in r
                ])), 4)
                if any("within_mechanism_spearman" in r for r in usable) else None
            ),
            "median_compression": (
                round(float(np.median([r["compression"] for r in usable])), 2)
                if usable else None
            ),
        },
    }
    write_json(args.out, doc)

    print(f"{'axis':22} {'mechanism':14} {'payloads':>8} {'obs fold':>9} "
          f"{'model fold':>11} {'compression':>12}")
    for r in usable[:12]:
        print(f"{r['axis']:22} {r['mechanism']:14} {r['n_payloads']:8} "
              f"{r['observed_fold']:9.2f} {r['model_fold']:11.2f} {r['compression']:12.2f}")
    if usable:
        w = usable[0]
        print()
        print(f"  worst: {w['axis']} within {w['mechanism']} -- observed "
              f"{w['observed_lo']:.4f}..{w['observed_hi']:.4f} ({w['observed_fold']:.2f}x) "
              f"against a model spread of {w['model_fold']:.2f}x")
        print(f"  payloads: {w['payloads']}")
        ranked = [r for r in usable if "within_mechanism_spearman" in r]
        if ranked:
            print()
            print("  within-mechanism rank agreement, observed against model:")
            for r in sorted(ranked, key=lambda r: r["within_mechanism_spearman"]):
                print(f"    {r['axis']:22} {r['mechanism']:10} rho "
                      f"{r['within_mechanism_spearman']:+.4f} over "
                      f"{r['n_payloads_ranked']} payloads")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
