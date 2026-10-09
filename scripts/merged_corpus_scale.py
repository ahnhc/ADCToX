"""What does the teammate-supplied database buy, in the units this project argues in?

The corpus-expansion argument in this report has one shape throughout: an addition is worth
having only if it raises *identifying cells per design parameter*, because design features
are agent-level constants and arms are nearly free. The literature sweep was measured that
way (negative results 11 and 32: six more agents bought 84 identifying cells and no
observations). The same measurement, applied here.

Three questions, and the third is the one that matters most:

  1. How many agents does the merged corpus hold, against the 32 the automated pipeline
     reached and the 54 the project plan called a hard ceiling?
  2. Does the identification ratio cross the plan's 8:1 floor, which is the threshold it set
     for a mechanism-by-axis interaction and never reached?
  3. Does the **payload vocabulary still grow as fast as the corpus**? That is negative
     result 6, this report's most load-bearing structural claim, and it has only ever been
     measured at 17 and 31 agents with the rest projected. A corpus of 70 agents either
     confirms it at double the N or refutes it.

Counted on normalised payload identities, not raw strings: 33 of their `Payload` spellings
stand for 19 payloads, and counting the strings would inflate the vocabulary by 70% and
manufacture a confirmation of result 6.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy
import corpus_ablation as _ablation

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The plan's own floor for identifying a level-by-axis interaction, and its rule for whether
# a mechanism can serve as a held-out fold. Imported from the ablation script where they are
# defined, so the two cannot drift.
DESIGN_PARAMETERS = _ablation.DESIGN_PARAMETERS
IDENTIFICATION_FLOOR = 8.0
MIN_AGENTS_FOR_HOLDOUT = 3
MIN_N = 30


def _first_number(text: str) -> float | None:
    import re
    s = str(text).split("|")[0]
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s.replace("–", "-"))]
    if not nums:
        return None
    # A range takes its midpoint; a tolerance takes its centre, which is the leading number.
    if "-" in s and len(nums) >= 2 and nums[1] > nums[0] and "±" not in s:
        return (nums[0] + nums[1]) / 2
    return nums[0]


def _atlas_design(workbook: pathlib.Path, slots: dict) -> pd.DataFrame:
    m = pd.read_excel(workbook, sheet_name="ADC_MASTER")
    m["agent"] = m["ADC ID"].astype(str).str.lower().str.replace("-", "_")

    def resolve(row) -> tuple[str | None, str | None, str | None]:
        for field in ("Payload",):
            for alt in str(row.get(field) or "").split("|"):
                pid = slots["payload_identity"].get(alt.strip())
                if pid:
                    return pid, slots["mechanism_of_payload"].get(pid), \
                        slots["family_of_payload"].get(pid)
        # Fall back to the class label, which names a family rather than a molecule.
        CLASS = {"Auristatin": "MMAE", "Maytansinoid": "DM1", "Calicheamicin": "calicheamicin",
                 "PBD dimer": "SG3199", "PBD": "SG3199", "Duocarmycin": "seco-DUBA",
                 "Exatecan derivative": "exatecan", "Camptothecin derivative": "SN-38",
                 "Tubulysin": "tubulysin"}
        for alt in str(row.get("Payload class") or "").split("|"):
            pid = CLASS.get(alt.strip())
            if pid:
                return pid, slots["mechanism_of_payload"].get(pid), \
                    slots["family_of_payload"].get(pid)
        return None, None, None

    got = m.apply(resolve, axis=1, result_type="expand")
    m[["payload", "mechanism", "payload_family"]] = got
    def _cleavable(v) -> bool | None:
        for alt in str(v).split("|"):
            if alt.strip() in slots["cleavable_of_linker_type"]:
                return slots["cleavable_of_linker_type"][alt.strip()]
        return None

    m["cleavable"] = m["Linker type"].map(_cleavable)
    m["dar"] = m["DAR"].map(_first_number)
    return m[["agent", "payload", "mechanism", "payload_family", "cleavable", "dar",
              "Target"]].rename(columns={"Target": "target"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=pathlib.Path,
                    default=ROOT / "data" / "raw" / "atlas" / "2026-10-10" / "adc_db.xlsx")
    ap.add_argument("--slots", type=pathlib.Path,
                    default=ROOT / "conf" / "ontology" / "atlas_design_slots.yaml")
    ap.add_argument("--atlas", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "atlas")
    ap.add_argument("--ours", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_final")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "merged_corpus_scale.json")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    args = ap.parse_args()

    slots = yaml.safe_load(args.slots.read_text(encoding="utf-8"))
    axes = list(Taxonomy().axis_order)

    atlas_arms = pd.read_parquet(args.atlas / "arms_raw.parquet")
    atlas_obs = pd.read_parquet(args.atlas / "observations_raw.parquet")
    keep = atlas_arms[atlas_arms.n_at_risk >= args.min_n]
    atlas_obs = atlas_obs[atlas_obs.arm_key.isin(set(keep.arm_key))]

    design = _atlas_design(args.workbook, slots)
    keep = keep.merge(design, on="agent", how="left")
    unassignable = set(slots.get("unassignable") or {})
    usable = keep[keep.mechanism.notna() & ~keep.agent.isin(unassignable)]

    ours = pd.read_parquet(args.ours / "arms.parquet")
    ours_agents = set(ours.agent.dropna().unique())
    atlas_agents = set(usable.agent)
    merged_agents = ours_agents | atlas_agents

    # Identifying cells: an agent-by-axis cell with an observation. Design features are
    # agent-level constants, so this is the sample size the design coefficients see.
    atlas_cells = (
        atlas_obs[atlas_obs.arm_key.isin(set(usable.arm_key))]
        .merge(usable[["arm_key", "agent"]].drop_duplicates(), on="arm_key", how="left",
               suffixes=("", "_arm"))
        .drop_duplicates(["agent", "axis"])
    )
    ours_obs = pd.read_parquet(args.ours / "observations.parquet")
    ours_cells = ours_obs.drop_duplicates(["agent", "axis"])
    merged_cells = (
        pd.concat([ours_cells[["agent", "axis"]], atlas_cells[["agent", "axis"]]])
        .drop_duplicates()
    )

    def ratio(n_cells: int) -> float:
        return round(n_cells / DESIGN_PARAMETERS, 2)

    # Negative result 6, re-measured. Payload identity and family vocabularies at each size.
    ours_payloads = set(ours.payload.dropna().unique())
    ours_families = set(ours.payload_family.dropna().unique())
    atlas_payloads = set(usable.payload.dropna().unique())
    atlas_families = set(usable.payload_family.dropna().unique())

    rows = []
    for name, agents, cells, pays, fams in [
        ("registry + literature (ours)", ours_agents, len(ours_cells),
         ours_payloads, ours_families),
        ("atlas only", atlas_agents, len(atlas_cells), atlas_payloads, atlas_families),
        ("merged", merged_agents, len(merged_cells),
         ours_payloads | atlas_payloads, ours_families | atlas_families),
    ]:
        rows.append({
            "corpus": name,
            "agents": len(agents),
            "identifying_cells": int(cells),
            "cells_per_design_parameter": ratio(int(cells)),
            "meets_identification_floor": ratio(int(cells)) >= IDENTIFICATION_FLOOR,
            "payload_identities": len(pays),
            "payload_families": len(fams),
            "payloads_per_agent": round(len(pays) / max(len(agents), 1), 3),
        })

    # Fold viability on the merged mechanism assignment.
    ours_mech = ours.dropna(subset=["agent", "mechanism"]).drop_duplicates("agent")[
        ["agent", "mechanism"]]
    atlas_mech = usable.drop_duplicates("agent")[["agent", "mechanism"]]
    mech = pd.concat([ours_mech, atlas_mech]).drop_duplicates("agent")
    folds = (
        mech.groupby("mechanism").agent.nunique().rename("agents").reset_index()
        .assign(holdout_viable=lambda d: d.agents >= MIN_AGENTS_FOR_HOLDOUT)
        .sort_values("agents", ascending=False)
    )

    doc = {
        "min_n": args.min_n,
        "design_parameters": DESIGN_PARAMETERS,
        "identification_floor": IDENTIFICATION_FLOOR,
        "corpora": rows,
        "new_agents": sorted(atlas_agents - ours_agents),
        "agents_lost_to_unassignable_payload": sorted(unassignable),
        "folds": folds.to_dict("records"),
        "n_viable_folds": int(folds.holdout_viable.sum()),
        "atlas_arms_at_min_n": int(len(usable)),
    }
    write_json(args.out, doc)

    print(f"{'corpus':30} {'agents':>7} {'cells':>7} {'ratio':>7} {'floor':>6} "
          f"{'payloads':>9} {'families':>9} {'pay/agent':>10}")
    for r in rows:
        print(f"{r['corpus']:30} {r['agents']:>7} {r['identifying_cells']:>7} "
              f"{r['cells_per_design_parameter']:>7} "
              f"{'yes' if r['meets_identification_floor'] else 'no':>6} "
              f"{r['payload_identities']:>9} {r['payload_families']:>9} "
              f"{r['payloads_per_agent']:>10}")
    print()
    print(f"new agents: {len(doc['new_agents'])}")
    print(f"folds ({doc['n_viable_folds']} viable at >={MIN_AGENTS_FOR_HOLDOUT} agents):")
    for f in doc["folds"]:
        print(f"  {f['mechanism']:16} {f['agents']:3} agents  "
              f"{'VIABLE' if f['holdout_viable'] else 'single-agent case'}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
