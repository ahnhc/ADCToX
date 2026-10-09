"""At which granularity does the identification ratio recede, and at which does it improve?

The plan's central structural claim is that the resolution which would improve prediction
recedes as fast as it is approached: each new agent brings a new payload, so tripling the
corpus leaves identifying-cells-per-design-parameter flat. Its table put that at 2.12, 2.91
and 2.84 across corpora of 17, 32 and 54 agents.

Two of those three rows were projections. The 54-agent corpus was measured not to exist --
the ceiling is 32 agents, 31 of which publish an any-grade column -- and the payload
vocabulary was projected to reach 12 classes at the second step and 20 at the third. It
reaches 16 payload identities and 8 families at 31 agents.

Measured, the claim is true at one granularity and false at the two coarser ones. The ratio
is computed the plan's own way: identifying cells over `(levels - 1) x axes`, which
reproduces its 4.25, 6.40 and 9.00 for the mechanism level exactly.
"""

from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from adctox.model.dataset import build
from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The plan's threshold for identifying a level-by-axis interaction.
IDENTIFICATION_FLOOR = 8.0


def _stage(path: pathlib.Path, axes: list[str], keep: set[str] | None):
    arms = pd.read_parquet(path / "arms.parquet")
    obs = pd.read_parquet(path / "observations.parquet")
    if keep is not None:
        arms = arms[
            (arms["source"].isna() if "source" in arms else True)
            | arms["agent"].isin(keep)
        ].reset_index(drop=True)
        obs = obs[obs["arm_key"].isin(set(arms["arm_key"]))].reset_index(drop=True)
    data = build(arms, obs, axes, kind="other")
    inc = set(data.agents)
    payloads = sorted(
        {p for p in arms.loc[arms["agent"].isin(inc), "payload"].dropna()}
    )
    return data, payloads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=pathlib.Path,
                    default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "granularity_ratio.json")
    args = ap.parse_args()

    axes = list(default_taxonomy().axis_order)
    full = args.processed / "with_literature_final"
    registry_agents = set(
        pd.read_parquet(args.processed / "arms.parquet")["agent"].dropna().unique()
    )
    stages = {
        "registry_only": (args.processed, None),
        "plus_literature_arms": (full, registry_agents),
        "plus_literature_agents": (full, None),
    }

    rows = []
    for name, (path, keep) in stages.items():
        data, payloads = _stage(path, axes, keep)
        agents = data.n_contributing_agents
        identifying = agents * len(axes)
        levels = {
            "payload_identity": len(payloads),
            "payload_family": len(data.families),
            "mechanism": len(data.mechanisms),
        }
        row = {"stage": name, "agents": agents, "identifying_cells": identifying,
               "levels": levels, "ratio": {}}
        for level, k in levels.items():
            params = max(k - 1, 1) * len(axes)
            row["ratio"][level] = round(identifying / params, 2)
        rows.append(row)

    first, last = rows[0], rows[-1]
    change = {
        level: round(last["ratio"][level] / first["ratio"][level], 2)
        for level in first["ratio"]
    }
    summary = {
        "identification_floor": IDENTIFICATION_FLOOR,
        # The claim being refuted, recorded beside the refutation. The plan projected the
        # mechanism-level ratio at corpora of 17, 32 and 54 agents assuming the mechanism
        # count would grow 5 -> 6 -> 7 with them. It stayed at 5, and the 54-agent corpus
        # was measured not to exist.
        "plan_projection_mechanism_level": {
            "n17_k5": round(17 * 14 / ((5 - 1) * 14), 2),
            "n32_k6": round(32 * 14 / ((6 - 1) * 14), 2),
            "n54_k7": round(54 * 14 / ((7 - 1) * 14), 2),
        },
        "ratio_change_registry_to_expanded": change,
        "levels_that_clear_the_floor": [
            level for level, v in last["ratio"].items() if v >= IDENTIFICATION_FLOOR
        ],
        "recedes": [level for level, v in change.items() if v < 1.25],
    }

    print(f"  {'stage':24s} {'agents':>7s} {'ident':>6s} "
          + " ".join(f"{k:>18s}" for k in first["ratio"]))
    for r in rows:
        print(f"  {r['stage']:24s} {r['agents']:7d} {r['identifying_cells']:6d} "
              + " ".join(
                  f"{r['ratio'][k]:8.2f} (k={r['levels'][k]:2d})" for k in r["ratio"]
              ))
    print()
    for k, v in summary.items():
        print(f"  {k:36s} {v}")
    write_json(args.out, {"summary": summary, "stages": rows})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
