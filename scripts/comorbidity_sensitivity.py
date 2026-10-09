"""Does the comorbidity profile change the design the product proposes?

That is the product's central claim -- input (comorbidity profile + target antigen), output
a proposed design -- and it had never been measured. The weights are computed, returned in
`weights_applied`, shown on screen, and visibly move `weighted_risk`. None of that is the
claim. The claim is that the *proposal* responds.

The mechanism that could defeat it is specific. O1 is the only weighted objective, and the
weights enter it alone. When O1 cannot separate the head of the ranking -- which on this
corpus it usually cannot, the leading tie group running to dozens of designs out of 74 --
the display order inside that group falls to O2 and O3, and O2 is the *unweighted* worst
single organ. So the weights decide group membership and then stop mattering.

Measured here over every condition in the closed list singly, plus combinations chosen to
hit the leading payload's own worst organs, across several targets. Reported as the number
of distinct proposals and the share of profiles whose leader differs from the no-comorbidity
baseline, with the leading group size beside it so the cause is visible rather than inferred.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.model.predict import Posterior
from adctox.pipeline import propose
from adctox.provenance import write_json
from adctox.schemas import ComorbidityId

ROOT = pathlib.Path(__file__).resolve().parents[1]

TARGETS = ["HER2", "TROP2", "CD30", "BCMA"]

# Combinations, not arbitrary: each one weights an organ that the leading designs are
# actually predicted to hit, which is where a weighted objective has something to bite on.
COMBINATIONS = [
    ["cirrhosis", "thrombocytopenia"],
    ["cirrhosis", "thrombocytopenia", "mds"],
    ["inflammatory_bowel_disease", "prior_bowel_resection"],
    ["interstitial_lung_disease", "pulmonary_fibrosis"],
    ["keratopathy_history", "dry_eye", "prior_corneal_surgery"],
    ["peripheral_neuropathy", "diabetic_neuropathy"],
    ["ckd_stage_4_5", "interstitial_lung_disease"],
    ["cirrhosis", "ckd_stage_4_5", "heart_failure", "interstitial_lung_disease"],
]


def _slots(design: dict) -> tuple:
    return (design["payload"], design["linker"], design["conjugation"],
            design["dar"], design["isotype"], design["masking"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", type=pathlib.Path, default=ROOT / "artifacts")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "comorbidity_sensitivity.json")
    ap.add_argument("--top-k", type=int, default=6)
    args = ap.parse_args()

    post = Posterior.load(args.artifacts / "posterior_other.npz")
    serious_path = args.artifacts / "posterior_serious.npz"
    serious = Posterior.load(serious_path) if serious_path.exists() else None

    conditions = [c.value for c in ComorbidityId]
    profiles: list[list[str]] = [[]] + [[c] for c in conditions] + COMBINATIONS

    per_target = {}
    for target in TARGETS:
        rows = []
        for profile in profiles:
            # hard_flags off: a label-derived override that hardcodes "prior ILD plus a
            # deruxtecan payload is high risk" would answer this question by fiat. The
            # question is whether the *model* makes the proposal respond.
            out = propose(
                target_antigen=target, condition_ids=profile, posterior=post,
                top_k=args.top_k, serious_posterior=serious, hard_flags=False,
            )
            cands = out["candidates"]
            if not cands:
                continue
            rows.append({
                "profile": profile,
                "leader": _slots(cands[0]["design"]),
                "shown": [_slots(c["design"]) for c in cands],
                "leader_group_size": cands[0].get("group_size"),
                "n_pareto_front": out.get("n_pareto_front"),
                "weighted_risk": cands[0].get("weighted_risk"),
                "worst_axis": cands[0].get("worst_axis"),
                "worst_axis_risk": cands[0].get("worst_axis_risk"),
            })
        if not rows:
            continue
        baseline = next(r for r in rows if r["profile"] == [])
        leaders = collections.Counter(tuple(r["leader"]) for r in rows)
        shown = collections.Counter(tuple(tuple(s) for s in r["shown"]) for r in rows)
        changed = [r["profile"] for r in rows
                   if tuple(r["leader"]) != tuple(baseline["leader"])]
        per_target[target] = {
            "n_profiles": len(rows),
            "n_distinct_leaders": len(leaders),
            "n_distinct_shown_sets": len(shown),
            "n_profiles_changing_the_leader": len(changed),
            "profiles_changing_the_leader": changed,
            "baseline_leader": list(baseline["leader"]),
            "leader_group_size_range": [
                min(r["leader_group_size"] or 0 for r in rows),
                max(r["leader_group_size"] or 0 for r in rows),
            ],
            # The worst axis the display order is actually sorted on. If this never moves,
            # the unweighted tiebreak is what is deciding the proposal.
            "n_distinct_worst_axes": len({r["worst_axis"] for r in rows}),
            "rows": rows,
        }

    total = sum(t["n_profiles"] for t in per_target.values())
    changing = sum(t["n_profiles_changing_the_leader"] for t in per_target.values())
    doc = {
        "summary": {
            "targets": list(per_target),
            "n_profile_target_pairs": total,
            "n_changing_the_leader": changing,
            "fraction_changing_the_leader": changing / total if total else 0.0,
            "reading": (
                f"The comorbidity profile changes the proposed design in {changing} of "
                f"{total} profile-by-target pairs."
                + (
                    " The product's primary input does not reach its primary output."
                    if changing == 0 else
                    " The weights reach the proposal, though the share is small enough to "
                    "report with the group sizes beside it."
                )
            ),
        },
        "by_target": per_target,
    }
    write_json(args.out, doc)
    for t, v in per_target.items():
        print(f"{t:7} leaders {v['n_distinct_leaders']:2}  shown sets "
              f"{v['n_distinct_shown_sets']:2}  leader changed in "
              f"{v['n_profiles_changing_the_leader']:3}/{v['n_profiles']}  "
              f"group {v['leader_group_size_range']}  worst axes "
              f"{v['n_distinct_worst_axes']}")
    print()
    print(" ", doc["summary"]["reading"])
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
