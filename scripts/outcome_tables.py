"""Three outcome tables, and which of them can carry the model.

`otherEvents` on ClinicalTrials.gov is any-grade, all-cause incidence, and 154 of the 414
literature arms report something else. 112 of those report grade 3 and above -- the
threshold clinical practice acts on -- so rather than discard them they become a third
table, `kind="grade3"`. It is literature-only, because the registry has no grade split at
all, which makes it the clean form of the question the corpus ablation asks: can literature
arms support a model with no registry arms mixed in to carry them?

Measured: no. The table reaches 21 agents, more than the registry's 16, and **1.55 observed
cells per identifying cell** against the any-grade table's 9.97 and the 8:1 the plan set for
identifying a mechanism-by-axis interaction. More agents, each contributing four or five
observed axes instead of twelve, because a grade >=3 table lists only the organs that
reached grade 3.

That is the mirror image of section 5g's finding. There, more arms bought no agents. Here,
more agents buy no observations. The table is built and labelled so the set-aside data is
inspectable rather than invisible, and no fit is run on it.
"""

from __future__ import annotations

import argparse
import pathlib

from adctox.model.dataset import load
from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The ratio the plan set for identifying a mechanism-by-axis interaction.
IDENTIFICATION_FLOOR = 8.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_final")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "outcome_tables.json")
    args = ap.parse_args()

    axes = list(default_taxonomy().axis_order)
    rows = []
    for kind in ("other", "serious", "grade3"):
        try:
            data = load(args.processed, axes, kind=kind)
        except (KeyError, ValueError) as exc:
            rows.append({"kind": kind, "error": str(exc)})
            continue
        observed = int((data.status == 0).sum())
        agents = data.n_contributing_agents
        identifying = agents * len(axes)
        rows.append({
            "kind": kind,
            "agents": agents,
            "arms": data.n_arms,
            "cells": data.n_cells,
            "observed": observed,
            "observed_share": observed / data.n_cells,
            "identifying_cells": identifying,
            "observed_per_identifying_cell": round(observed / identifying, 2),
            "observed_axes_per_arm": round(observed / data.n_arms, 1),
            "can_identify_a_mechanism_interaction":
                observed / identifying >= IDENTIFICATION_FLOOR,
        })

    print(f"  {'table':8s} {'agents':>7s} {'arms':>5s} {'cells':>6s} {'obs':>5s} "
          f"{'obs%':>6s} {'ident':>6s} {'obs:ident':>10s} {'axes/arm':>9s}")
    for r in rows:
        if "error" in r:
            print(f"  {r['kind']:8s} absent: {r['error'][:60]}")
            continue
        print(f"  {r['kind']:8s} {r['agents']:7d} {r['arms']:5d} {r['cells']:6d} "
              f"{r['observed']:5d} {r['observed_share']:6.1%} "
              f"{r['identifying_cells']:6d} {r['observed_per_identifying_cell']:10.2f} "
              f"{r['observed_axes_per_arm']:9.1f}")
    print(f"\n  identification floor {IDENTIFICATION_FLOOR}:1; tables that clear it: "
          + (", ".join(r["kind"] for r in rows
                       if r.get("can_identify_a_mechanism_interaction")) or "none"))
    write_json(args.out, {
        "identification_floor": IDENTIFICATION_FLOOR, "tables": rows,
    })
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
