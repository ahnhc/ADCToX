"""How often can the model actually rank the designs it proposes?

The tie machinery exists so the product does not order designs it cannot separate. Whether
that ever fires was never measured, and the one query it was inspected on gave a head group
of 49 out of 74 -- which, if typical, means the ranked list is a fiction almost everywhere
and the honest output is a set.

This sweeps targets against comorbidity profiles and reports the distribution. It is a
property of the posterior's width against the spread of the design space, so it is a
measurement and not a choice: a wider corpus would change it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import yaml

from adctox.pipeline import propose
from adctox.model.predict import Posterior
from adctox.provenance import write_json

ROOT = Path(__file__).resolve().parents[1]

# Profiles chosen to span the organ axes the layer can weight, not to be representative of
# any patient population -- there is no population here to be representative of.
PROFILES: dict[str, list[str]] = {
    "none": [],
    "renal + pulmonary": ["ckd_stage_4_5", "interstitial_lung_disease"],
    "hepatic": ["cirrhosis"],
    "cardiac": ["heart_failure", "reduced_lvef"],
    "neuro + ocular": ["peripheral_neuropathy", "keratopathy_history"],
    "haematologic": ["thrombocytopenia", "mds"],
    # The dermatologic profile is here because it is the one case the target antigen is
    # known to touch: section 5e's expression flag raises the skin band for NECTIN4 and
    # ERBB2 and not for CD19 or TNFRSF8. A sweep without it would be blind to the only
    # input the target has, and would read as though the target never did anything.
    "dermatologic": ["severe_psoriasis", "prior_sjs_ten"],
    "four organs": ["cirrhosis", "ckd_stage_4_5", "heart_failure", "dry_eye"],
}


PROFILES_IDS = {c for conds in PROFILES.values() for c in conds}

# The comorbidity weighting constant. `w_o = 1 + lam * severity_o`, so the shipped lam = 2
# gives an at-risk axis a weight of 3 against 1 for the other thirteen -- the plan's stated
# and defensible preference ("you told us CrCl 25, so the renal axis is weighted 3x"). The
# sweep exists because that constant, and not the patient, turns out to decide how much the
# profile moves the proposal, and the honest thing is to publish the dependence rather than
# to tune the constant until the demo looks responsive.
LAMBDAS = (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 30.0, 50.0, 100.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posterior", default="artifacts/posterior_other.npz")
    ap.add_argument("--serious-posterior", default="artifacts/posterior_serious.npz")
    ap.add_argument("--out", default="artifacts/rank_resolution.json")
    args = ap.parse_args()

    post = Posterior.load(ROOT / args.posterior)
    sp_path = ROOT / args.serious_posterior
    serious = Posterior.load(sp_path) if sp_path.exists() else None
    # Every target with clinical precedent, which is the set the product will be asked
    # about. A target no ADC has been built against gives the same design space anyway --
    # the target enters the model only through a random effect -- so sweeping more would
    # add rows and no information.
    doc = yaml.safe_load((ROOT / "conf" / "adc_registry.yaml").read_text())
    agents = doc["agents"] if isinstance(doc, dict) and "agents" in doc else doc
    agents = list(agents.values()) if isinstance(agents, dict) else agents
    targets = sorted({a["target"] for a in agents if a.get("target")})
    known = set(PROFILES_IDS)

    rows: list[dict] = []
    for target in targets:
        for label, conds in PROFILES.items():
            missing = [c for c in conds if c not in known]
            if missing:
                raise SystemExit(f"unknown comorbidity ids: {missing}")
            out = propose(
                target_antigen=target, condition_ids=conds,
                posterior=post, top_k=6, serious_posterior=serious,
            )
            cands = out["candidates"]
            if not cands:
                continue
            head = cands[0]
            # How much of the output the target antigen is responsible for. Section 5e
            # measured that it changes bands and reasons but not the proposed design, and
            # a sweep that reports resolution without reporting this would invite the
            # reading that the target is still inert.
            from_target = sum(
                1 for c in cands for r in c["organ_risks"]
                if r.get("band_source") == "target_expression"
            )
            rows.append({
                "target": target,
                "profile": label,
                "n_enumerated": out["n_enumerated"],
                "n_passed": out["n_passed_constraints"],
                "n_pareto_front": out["n_pareto_front"],
                "head_group_size": head.get("group_size") or 1,
                "lead_p": head.get("lead_p"),
                "lead_is_decisive": head.get("lead_is_decisive"),
                "shown_all_one_group": all(
                    c["tie_group"] == head["tie_group"] for c in cands
                ),
                "bands_from_target_expression": from_target,
                "slots_shown": [
                    [c["design"]["payload"], c["design"]["linker"], c["design"]["dar"]]
                    for c in cands
                ],
            })

    n = len(rows)
    decisive = sum(1 for r in rows if r["lead_is_decisive"])
    one_set = sum(1 for r in rows if r["shown_all_one_group"])
    heads = np.array([r["head_group_size"] for r in rows], dtype=float)
    passed = np.array([r["n_passed"] for r in rows], dtype=float)
    share = heads / np.maximum(passed, 1)
    summary = {
        "queries": n,
        "decisive_leader": decisive,
        "decisive_share": decisive / n if n else None,
        "all_shown_in_one_group": one_set,
        "one_set_share": one_set / n if n else None,
        "head_group_size_median": float(np.median(heads)),
        "head_group_size_max": float(heads.max()),
        "head_share_of_passing_median": float(np.median(share)),
        "lead_p_median": float(np.median([r["lead_p"] or 0.0 for r in rows])),
        "queries_where_target_changes_a_band": sum(
            1 for r in rows if r["bands_from_target_expression"] > 0
        ),
        # The complementary fact, and the one that keeps the previous line honest: how many
        # distinct sets of designs the sweep proposed in total. One per profile would mean
        # the target changes bands and never the proposal, which is what section 5e found.
        "distinct_proposals": len(
            {json.dumps(r["slots_shown"]) for r in rows}
        ),
        "distinct_profiles": len(PROFILES),
    }

    print(f"  {'target':10s} {'profile':18s} {'passed':>7s} {'front':>6s} "
          f"{'head':>5s} {'lead_p':>7s} {'decisive':>9s}")
    for r in rows:
        print(f"  {r['target']:10s} {r['profile']:18s} {r['n_passed']:7d} "
              f"{r['n_pareto_front']:6d} {r['head_group_size']:5d} "
              f"{(r['lead_p'] or 0):7.3f} {str(r['lead_is_decisive']):>9s}")
    print()
    for k, v in summary.items():
        print(f"  {k:34s} {v}")

    # How much of the proposal is the patient and how much is the weighting constant. For
    # each profile, the lambda at which the proposed set first differs from the one the
    # shipped lambda produces.
    lam_rows: list[dict] = []
    for label, conds in PROFILES.items():
        if not conds:
            continue
        base = None
        first_change = None
        per_lam = []
        for lam in LAMBDAS:
            out = propose(
                target_antigen="ERBB2", condition_ids=conds,
                posterior=post, top_k=6, serious_posterior=serious, lam=lam,
            )
            slots = [
                [c["design"]["payload"], c["design"]["linker"], c["design"]["dar"]]
                for c in out["candidates"]
            ]
            key = json.dumps(slots)
            if lam == 2.0:
                base = key
            per_lam.append({"lam": lam, "slots": slots})
        for row in per_lam:
            if row["lam"] > 2.0 and json.dumps(row["slots"]) != base:
                first_change = row["lam"]
                break
        at_risk_share = None
        out2 = propose(
            target_antigen="ERBB2", condition_ids=conds, posterior=post,
            top_k=6, serious_posterior=serious, lam=2.0,
        )
        w = out2["weights_applied"]
        heavy = [a for a, v in w.items() if v > 1.0]
        if w:
            at_risk_share = sum(w[a] for a in heavy) / sum(w.values())
        lam_rows.append({
            "profile": label,
            "n_at_risk_axes": len(heavy),
            "at_risk_share_of_objective_at_lam_2": at_risk_share,
            "lambda_at_first_change": first_change,
            "distinct_proposals_over_lambda": len(
                {json.dumps(r["slots"]) for r in per_lam}
            ),
        })

    summary["profiles_whose_proposal_is_lambda_sensitive"] = sum(
        1 for r in lam_rows if r["lambda_at_first_change"] is not None
    )
    summary["at_risk_share_of_objective_at_lam_2_median"] = float(
        np.median([
            r["at_risk_share_of_objective_at_lam_2"] for r in lam_rows
            if r["at_risk_share_of_objective_at_lam_2"] is not None
        ])
    )

    print()
    print(f"  {'profile':18s} {'axes':>5s} {'share@lam2':>11s} "
          f"{'first change':>13s} {'distinct':>9s}")
    for r in lam_rows:
        share = r["at_risk_share_of_objective_at_lam_2"]
        print(f"  {r['profile']:18s} {r['n_at_risk_axes']:5d} "
              f"{(share or 0):11.0%} {str(r['lambda_at_first_change']):>13s} "
              f"{r['distinct_proposals_over_lambda']:9d}")

    out_path = ROOT / args.out
    write_json(
        out_path,
        {"summary": summary, "rows": rows, "lambda_sensitivity": lam_rows},
        inputs={"posterior": ROOT / args.posterior, "serious_posterior": sp_path},
    )
    print(f"\n-> {out_path}")


if __name__ == "__main__":
    main()
