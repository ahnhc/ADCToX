#!/usr/bin/env python
"""Score the model against dated organ-warning additions to approved ADC labels.

The question, stated so it can only be answered one way: for each date on which FDA added
an organ warning to an ADC's label, did a model fit **only on trial data that was public
before that date** rank that organ highly for that drug?

This is the project's one anticipatory target. Everything else measures agreement with
warnings that already existed at approval.

Design decisions that determine whether the answer means anything:

* **Cutoff is results-posted date, not trial start.** The question is what a modeller
  could have known, and a trial's adverse-event table is not knowable until it is posted.
* **The drug's own earlier trials stay in.** They were public, so excluding them would
  answer a different and easier question. If the model ranks the organ highly using only
  pre-change public data, the signal was already there before the label moved -- which is
  the interesting claim.
* **Its own post-change arms are excluded** by the same cutoff, which is what stops this
  being circular.
* **The null is explicit.** Fourteen axes, so a uniformly random rank has mean 7.5 and
  P(top three) = 3/14 = 0.214. Power at this sample size is reported before the result.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from math import comb
from pathlib import Path

import jax
import numpy as np
import pandas as pd
import yaml
from numpyro.infer import MCMC, NUTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

from adctox.model import dataset as ds, forward  # noqa: E402
from adctox.taxonomy import Taxonomy  # noqa: E402

CONF = Path(__file__).resolve().parents[1] / "conf"
N_AXES = 14
P_TOP3 = 3 / N_AXES


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except ValueError:
            continue
    return None


def binom_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def power_table(n: int) -> list[tuple[int, float]]:
    return [(k, binom_tail(k, n, P_TOP3)) for k in range(1, n + 1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=Path, default=Path("artifacts/label_change_events.json"))
    ap.add_argument("--processed", type=Path, default=Path("data/processed"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--samples", type=int, default=200)
    ap.add_argument("--min-arms", type=int, default=60,
                    help="skip an event whose pre-date corpus is smaller than this")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tax = Taxonomy()
    axes = list(tax.axis_order)
    events = json.loads(args.events.read_text(encoding="utf-8"))["axis_additions"]
    registry = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))["agents"]
    arms_all = pd.read_parquet(args.processed / "arms.parquet")
    obs_all = pd.read_parquet(args.processed / "observations.parquet")

    print(f"{len(events)} dated axis additions")
    print(f"\nPower before looking at any result (null P(top 3) = {P_TOP3:.3f}):")
    for k, p in power_table(len(events)):
        flag = "  <- significant at 0.05" if p < 0.05 else ""
        print(f"  {k}/{len(events)} in top 3  ->  p = {p:.4f}{flag}")

    results = []
    for ev in sorted(events, key=lambda e: str(e["date"])):
        when = _parse_date(ev["date"])
        if when is None:
            print(f"\n! {ev['agent']}: unparseable date {ev['date']!r}, skipped")
            continue
        agent, axis = ev["agent"], ev["axis"]

        posted = arms_all["results_posted"].map(_parse_date)
        before = arms_all[posted.notna() & (posted < when)]
        keep = set(before["arm_key"])
        try:
            data = ds.build(before, obs_all[obs_all["arm_key"].isin(keep)], axes, kind="other")
        except ValueError as exc:
            print(f"\n{agent} / {axis} @ {ev['date']}: no usable corpus ({exc})")
            results.append({**ev, "status": "no_corpus"})
            continue
        if data.n_arms < args.min_arms:
            print(f"\n{agent} / {axis} @ {ev['date']}: only {data.n_arms} arms before the "
                  f"date, below the {args.min_arms} floor -- skipped rather than scored on noise")
            results.append({**ev, "status": "too_few_arms", "n_arms": data.n_arms})
            continue

        spec = registry[agent]
        if spec["payload_family"] not in data.families:
            print(f"\n{agent} / {axis} @ {ev['date']}: payload family "
                  f"{spec['payload_family']} absent from the pre-date corpus -- the model "
                  f"has no coefficient and must refuse rather than extrapolate")
            results.append({**ev, "status": "family_absent", "n_arms": data.n_arms})
            continue

        # Same logic as the C6 design constraint: if the corpus at that date held no
        # usable evidence for this chemistry on the organ that was about to be added, the
        # model cannot be asked to rank it and scoring the event would score noise. The
        # distinction matters here because the whole analysis is about what was knowable.
        from adctox.model.predict import MIN_ARMS_FOR_A_BAND

        mech_i = data.mechanisms.index(spec["mechanism"])
        axis_i = axes.index(axis)
        mcmc = MCMC(
            NUTS(forward.model, target_accept_prob=0.8, max_tree_depth=8),
            num_warmup=args.warmup, num_samples=args.samples, num_chains=1,
            progress_bar=False,
        )
        mcmc.run(jax.random.PRNGKey(31), data=data)
        post = mcmc.get_samples()

        from adctox.model.predict import Posterior, predict_draws

        p = Posterior.from_samples(post, data)
        n_arms_axis = int(p.evidence_arms[mech_i, axis_i])
        n_agents_axis = int(p.evidence_agents[mech_i, axis_i])
        if n_arms_axis < MIN_ARMS_FOR_A_BAND:
            print(f"\n{agent} / {axis} @ {ev['date']}")
            print(f"  corpus before that date: {data.n_arms} arms, {len(data.agents)} agents")
            print(f"  but only {n_arms_axis} arm(s) of {spec['mechanism']} chemistry "
                  f"reported on the {axis} axis by then -- not scorable, because a rank "
                  f"produced from that is noise rather than a prediction")
            results.append(
                {**ev, "status": "axis_unevidenced_at_date", "n_arms": int(data.n_arms),
                 "n_arms_on_axis": n_arms_axis}
            )
            continue
        draws = predict_draws(
            p,
            mechanisms=[spec["mechanism"]],
            families=[spec["payload_family"]],
            dars=np.array([float(spec["dar"])]),
            cleavables=np.array([float(bool(spec["linker_cleavable"]))]),
            include_agent_variation=False,
        )
        rates = draws[:, 0, :].mean(axis=0)
        order = np.argsort(-rates)
        rank = int(np.where(order == axes.index(axis))[0][0]) + 1

        print(f"\n{agent} / {axis} @ {ev['date']}")
        print(f"  corpus before that date: {data.n_arms} arms, {len(data.agents)} agents")
        print(f"  evidence for {spec['mechanism']} on {axis} by then: "
              f"{n_arms_axis} arms / {n_agents_axis} agents")
        print(f"  predicted rank of {axis}: {rank}/{N_AXES}"
              f"{'  (top 3)' if rank <= 3 else ''}")
        top = [f"{axes[i]} {rates[i]:.3f}" for i in order[:4]]
        print(f"  model's top axes: {', '.join(top)}")
        results.append(
            {**ev, "status": "scored", "n_arms": int(data.n_arms),
             "n_agents": len(data.agents), "rank": rank, "in_top3": rank <= 3,
             "n_arms_on_axis": n_arms_axis, "n_agents_on_axis": n_agents_axis,
             "predicted_rate": float(rates[axes.index(axis)])}
        )

    scored = [r for r in results if r.get("status") == "scored"]
    # Everything below was printed and never saved, so the report could not cite this
    # evaluation at all without typing its numbers by hand. Accumulated here and written
    # with the artefact.
    summary: dict = {"n_scored": len(scored), "n_not_scorable": len(results) - len(scored)}
    print(f"\n{'=' * 74}")
    if scored:
        ranks = [r["rank"] for r in scored]
        hits = sum(r["in_top3"] for r in scored)
        p_val = binom_tail(hits, len(scored), P_TOP3)
        summary.update({
            "mean_rank": float(np.mean(ranks)),
            "null_mean_rank": (N_AXES + 1) / 2,
            "top3_hits": int(hits),
            "p_value": float(p_val),
            "significant": bool(p_val < 0.05),
            "ranks_by_agent": {},
        })
        print(f"{len(scored)} events scored ({len(results) - len(scored)} not scorable)")
        print(f"  mean rank {np.mean(ranks):.2f} / {N_AXES}  (null mean 7.5)")
        print(f"  top-3 hits {hits}/{len(scored)}  ->  p = {p_val:.4f}"
              f"{'  significant' if p_val < 0.05 else '  NOT significant'}")
        per_agent = {}
        for r in scored:
            per_agent.setdefault(r["agent"], []).append(r["rank"])
        print(f"\n  per agent (concentration check):")
        summary["ranks_by_agent"] = {a: list(rs) for a, rs in per_agent.items()}
        summary["n_independent_drugs"] = len(per_agent)
        for a, rs in per_agent.items():
            print(f"    {a:26s} ranks {rs}")
        if len(per_agent) > 1:
            for drop in per_agent:
                rest = [r for r in scored if r["agent"] != drop]
                if not rest:
                    continue
                h = sum(r["in_top3"] for r in rest)
                pv = binom_tail(h, len(rest), P_TOP3)
                summary.setdefault("leave_one_agent_out", {})[drop] = {
                    "top3_hits": int(h), "n": len(rest), "p_value": float(pv),
                }
                print(f"    leave-{drop.split('_')[0]}-out: {h}/{len(rest)} top-3, "
                      f"p = {pv:.4f}")
        print(f"\n  Power recomputed on the scorable subset, which is what the test "
              f"actually runs on:")
        for k, pv in power_table(len(scored)):
            flag = "  <- significant at 0.05" if pv < 0.05 else ""
            print(f"    {k}/{len(scored)} in top 3  ->  p = {pv:.4f}{flag}")
        reachable = [k for k, pv in power_table(len(scored)) if pv < 0.05]
        summary["power_on_scorable_subset"] = [
            [int(k), float(pv)] for k, pv in power_table(len(scored))
        ]
        # The structural point: at this n the test can essentially only succeed perfectly
        # or be inconclusive. Recorded so the limitation travels with the result.
        summary["min_hits_for_significance"] = int(reachable[0]) if reachable else None
        print(f"\n  This is a case series with a permutation test, not a validation study:"
              f" {len(scored)} events across {len(per_agent)} independent drugs."
              + (f" Only {reachable[0]}/{len(scored)} or better can reach p<0.05, so a "
                 f"single miss ends it." if reachable else
                 " No outcome at this sample size reaches p<0.05."))
    else:
        print("No event was scorable. Reporting that, rather than relaxing the floors.")

    path = args.out / "label_change_eval.json"
    write_json(
        path,
        {"null_p_top3": P_TOP3, "power": power_table(len(events)),
         "summary": summary, "results": results},
        {"processed": args.processed, "events": args.out / "label_change_events.json"},
    )
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
