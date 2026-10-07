#!/usr/bin/env python
"""End-to-end demonstration of the Week-2 gate: two inputs in, fourteen numbers out.

Run it with no model artefact present and it fits one first, so the gate can be
demonstrated from a clean clone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

from adctox.model.predict import Posterior  # noqa: E402
from adctox.pipeline import propose  # noqa: E402
from adctox.taxonomy import Taxonomy  # noqa: E402




def _ensure_posterior(
    processed: Path, out: Path, warmup: int, samples: int, kind: str = "other"
) -> Posterior:
    """Fit-and-cache the posterior for one event table.

    `kind` is parameterized because the censoring robustness check needs the serious-event
    posterior to compare mechanism profiles against. The product itself always uses
    "other": serious events are too sparse per axis to rank designs on.
    """
    path = out / f"posterior_{kind}.npz"
    if path.exists():
        return Posterior.load(path)
    print(f"{path} absent; fitting one ...", flush=True)
    import jax
    from numpyro.infer import MCMC, NUTS

    from adctox.model import dataset as ds, forward

    tax = Taxonomy()
    data = ds.load(processed, list(tax.axis_order), kind=kind)
    mcmc = MCMC(
        NUTS(forward.model, target_accept_prob=0.8, max_tree_depth=8),
        num_warmup=warmup, num_samples=samples, num_chains=1, progress_bar=False,
    )
    mcmc.run(jax.random.PRNGKey(20261007), data=data)
    post = Posterior.from_samples(mcmc.get_samples(), data)
    out.mkdir(parents=True, exist_ok=True)
    post.save(path)
    print(f"saved {path}", flush=True)
    return post


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, default=Path("data/processed"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    ap.add_argument("--target", default="ERBB2")
    ap.add_argument(
        "--conditions",
        default="interstitial_lung_disease,ckd_stage_3",
        help="comma-separated ids from conf/comorbidity_registry.csv",
    )
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--warmup", type=int, default=400)
    ap.add_argument("--samples", type=int, default=400)
    ap.add_argument("--kind", default="other", choices=["other", "serious"])
    ap.add_argument(
        "--fit-only",
        action="store_true",
        help="build and cache the posterior, then stop (used by the censoring check)",
    )
    args = ap.parse_args()

    posterior = _ensure_posterior(
        args.processed, args.out, args.warmup, args.samples, kind=args.kind
    )
    if args.fit_only:
        return 0
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    # The serious-event fit, when built, is what makes an at-risk axis answer the
    # question actually asked. The API loads both, so the demo must too, or the artefact
    # the report cites for the end-to-end gate would not describe the shipped behaviour.
    serious_path = args.out / "posterior_serious.npz"
    serious = Posterior.load(serious_path) if serious_path.exists() else None
    if serious is None:
        print(
            f"note: {serious_path} absent, so every axis is banded on the any-grade "
            "table. Build it with `--kind serious --fit-only` for the shipped behaviour.",
            flush=True,
        )
    result = propose(
        target_antigen=args.target,
        condition_ids=conditions,
        posterior=posterior,
        top_k=args.top_k,
        serious_posterior=serious,
    )

    print(f"\ntarget {args.target} | comorbidities {conditions}")
    print(f"enumerated {result['n_enumerated']} -> "
          f"{result['n_passed_constraints']} pass constraints")
    print("\nweights applied (shown to the user, since they are a declared preference):")
    for axis, w in sorted(result["weights_applied"].items(), key=lambda kv: -kv[1]):
        if w > 1.0:
            basis = next(
                (c["severity_basis"] for c in result["comorbidity_resolution"]
                 if axis in c["organ_axes"]), "",
            )
            print(f"  {axis:22s} x{w:.1f}   {basis[:54]}")

    print(f"\ntop {args.top_k} candidates")
    for c in result["candidates"]:
        tie = "" if c["distinguishable"] else "  [tied, not distinguishable]"
        pareto = "  [Pareto front]" if c.get("on_pareto_front") else ""
        flag = "  [contains a zero-approval component]" if c["has_unapproved_component"] else ""
        d = c["design"]
        print(f"\n  rank {c['rank']}{tie}{pareto}{flag}")
        print(f"    {d['payload']} / {d['linker']} / DAR {d['dar']} / "
              f"{d['conjugation']} / {d['isotype']} / mask {d['masking']}")
        print(f"    weighted risk {c['weighted_risk']:.3f} | worst axis "
              f"{c['worst_axis']} {c['worst_axis_risk']:.3f} | precedent {c['precedent_score']:.2f}")
        print(f"    binding constraint: {c['binding_constraint']}")
        print(f"    nearest real ADC  : {c['nearest_real_adc']} ({c['nearest_real_diff']})")
        high = c.get("unweighted_high_axes") or []
        if high:
            # Axes the weighted objective did not penalise because the patient stated no
            # vulnerability there. Shown because a candidate can minimise weighted risk
            # while still carrying a high peak elsewhere, and hiding that would mislead.
            print(f"    high-band axes NOT weighted for this patient: {', '.join(high)}")
        at_risk = [r for r in c["organ_risks"] if r["at_risk_for_patient"]]
        for r in at_risk:
            # Print the number the band was computed from, not whichever one came first.
            # These axes are banded on the serious table when it is available, so showing
            # the any-grade rate beside a serious-basis band states a figure that did not
            # produce the band next to it -- the confusion the UI avoids by labelling the
            # basis, and the demo has to avoid it the same way.
            serious = r.get("band_basis") == "serious"
            shown = r["serious_estimate"] if serious else r["point_estimate"]
            # A withheld point estimate is not a formatting edge case: the corpus has too
            # little on that organ for this chemistry to band a rate at all.
            pt = "     n/a" if shown is None else f"{shown:8.4f}"
            iv = r["serious_interval"] if serious else r["interval"]
            span = "" if iv is None else f" [{iv['lo']:.4f}, {iv['hi']:.4f}]"
            ev = f"{r.get('n_supporting_arms', 0)} arms"
            basis = "serious-event" if serious else "any-grade   "
            other = r["point_estimate"] if serious else r["serious_estimate"]
            alt = "" if other is None else (
                f"; any-grade {other:.3f}" if serious else f"; serious {other:.4f}"
            )
            print(f"      * {r['organ_axis']:20s} {pt}{span} {basis} "
                  f"{r['risk_band']:12s} (weight x{r['weight_applied']:.1f}, {ev}{alt})")

    if result["why_not_the_obvious_one"]:
        w = result["why_not_the_obvious_one"]
        print(f"\nwhy not the obvious one")
        verdict = ("would have ranked first" if w.get("would_have_ranked_first")
                   else f"would not have placed (best passing {w['best_passing_weighted_risk']:.3f})")
        print(f"  lowest-risk excluded candidate: {w['design']['payload']} / "
              f"{w['design']['linker']} / DAR {w['design']['dar']} "
              f"(weighted risk {w['weighted_risk']:.3f}; {verdict})")
        for f in w["excluded_by"]:
            print(f"    excluded by: {f}")

    path = args.out / "propose_demo.json"
    write_json(path, result, {"posterior": args.out / f"posterior_{args.kind}.npz"})
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
