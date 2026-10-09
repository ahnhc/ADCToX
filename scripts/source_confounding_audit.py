"""Which coefficients are confounded with the corpus an arm was read from?

Two were, and the way they were found was the same question twice: a coefficient changed
when the corpus grew, so what is it measuring? `b_combo` went from +0.195 on the registry
corpus to +1.091 on the expanded one, and the reporting-source gap turned out to vary by
axis more than the mechanism effect does. Both are now in the specification.

That is a reason to check the rest rather than a reason to stop. Every arm-level covariate
is measured against the source indicator here, by the two things that decide whether a
coefficient can be separated from it:

* **correlation** -- how much the covariate tracks the source;
* **within-source variance share** -- whether the covariate still varies inside each
  corpus, which is what identifies it when the source term is also in the model. A
  covariate with a high correlation and most of its variance *within* source is fine; one
  that separates completely is not.

For a categorical level the question is separation: does every level appear in both
corpora? `b_combo` failed exactly this -- all 139 combination arms are registry arms and
none of the 194 literature arms is a combination -- and it is the only one that does.
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
import pandas as pd

from adctox.model.dataset import build
from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Above this, a covariate tracks the source closely enough to ask the next question.
CORRELATION_CONCERN = 0.30
# Below this share of variance inside each corpus, a covariate cannot be told from the
# source term even when both are in the model.
WITHIN_SHARE_FLOOR = 0.50
# Confounds already in the specification. A coefficient listed here is flagged *and*
# handled; one flagged without an entry is an open problem.
ADDRESSED = {
    "b_combo (arm_combo)":
        "b_source plus the centred source_axis vector, added after b_combo moved from "
        "+0.195 on the registry corpus to +1.091 on the expanded one",
}

# The two values that argument rests on, recorded as numbers rather than only inside the
# sentence above. They were measured on fits that predate both the corpus rebuild and the
# `b_source` term, so no target regenerates them -- and a figure the report prints has to
# trace to an artefact, which a number embedded in a prose string does not.
B_COMBO_WITHOUT_SOURCE_TERM = {
    "registry": 0.195,
    "expanded": 1.091,
    "note": (
        "Posterior means for b_combo with no source indicator in the model. Both predate "
        "the corpus rebuild -- the registry corpus then held 16 agents and 285 arms, not 22 "
        "and 299 -- and the specification that produced them no longer exists, because "
        "b_source was added in response to exactly this gap. Quoted for the gap between "
        "them, which is the finding, and not as current coefficients."
    ),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_final")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "source_confounding.json")
    args = ap.parse_args()

    axes = list(default_taxonomy().axis_order)
    data = build(
        pd.read_parquet(args.processed / "arms.parquet"),
        pd.read_parquet(args.processed / "observations.parquet"),
        axes, kind="other",
    )
    lit = data.arm_is_literature

    continuous = {
        "b_dar (arm_dar_c)": data.arm_dar_c,
        "b_thresh (arm_thresh_c)": data.arm_thresh_c,
        "b_log_n (arm_log_n_c)": data.arm_log_n_c,
        "b_combo (arm_combo)": data.arm_combo,
        "cleav_axis (arm_cleavable)": data.arm_cleavable,
    }
    rows = []
    for name, v in continuous.items():
        v = np.asarray(v, dtype=float)
        total = float(v.var())
        within = float(
            (lit == 0).mean() * v[lit == 0].var() + (lit == 1).mean() * v[lit == 1].var()
        )
        share = within / total if total > 0 else 1.0
        r = float(np.corrcoef(v, lit)[0, 1])
        # Complete separation: the covariate takes one value throughout a corpus.
        separated = bool(v[lit == 1].std() == 0 or v[lit == 0].std() == 0)
        rows.append({
            "coefficient": name,
            "correlation_with_source": round(r, 3),
            "within_source_variance_share": round(share, 3),
            "separated": separated,
            "confounded": separated or (
                abs(r) >= CORRELATION_CONCERN and share < WITHIN_SHARE_FLOOR
            ),
            # What is already in the specification about it, so a verdict of CONFOUNDED
            # does not read as an open problem. The point of this audit is that two were
            # found and fixed and the rest are clear, not that one is outstanding.
            "addressed_by": ADDRESSED.get(name),
        })

    mech = np.array([data.mechanisms[i] for i in data.arm_mech_idx])
    levels = []
    for m in sorted(set(mech)):
        levels.append({
            "level": m,
            "registry_arms": int(((mech == m) & (lit == 0)).sum()),
            "literature_arms": int(((mech == m) & (lit == 1)).sum()),
        })
    separated_levels = [
        x["level"] for x in levels
        if x["registry_arms"] == 0 or x["literature_arms"] == 0
    ]

    summary = {
        "correlation_concern": CORRELATION_CONCERN,
        "within_share_floor": WITHIN_SHARE_FLOOR,
        "confounded": [r["coefficient"] for r in rows if r["confounded"]],
        "confounded_and_unaddressed": [
            r["coefficient"] for r in rows
            if r["confounded"] and not r["addressed_by"]
        ],
        "mechanism_levels_separated_by_source": separated_levels,
        "smallest_mechanism_cell": min(
            min(x["registry_arms"], x["literature_arms"]) for x in levels
        ),
    }

    print(f"  {'coefficient':28s} {'r':>7s} {'within':>8s} {'sep':>5s} {'verdict':>11s}")
    for r in rows:
        print(f"  {r['coefficient']:28s} {r['correlation_with_source']:+7.3f} "
              f"{r['within_source_variance_share']:8.3f} "
              f"{str(r['separated']):>5s} "
              f"{('CONFOUNDED' if not r['addressed_by'] else 'handled')
                 if r['confounded'] else 'clear':>11s}")
    print(f"\n  {'mechanism':16s} {'registry':>9s} {'literature':>11s}")
    for x in levels:
        print(f"  {x['level']:16s} {x['registry_arms']:9d} {x['literature_arms']:11d}")
    print()
    for k, v in summary.items():
        print(f"  {k:36s} {v}")
    write_json(args.out, {
        "summary": summary,
        "coefficients": rows,
        "mechanisms": levels,
        "b_combo_without_source_term": B_COMBO_WITHOUT_SOURCE_TERM,
    })
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
