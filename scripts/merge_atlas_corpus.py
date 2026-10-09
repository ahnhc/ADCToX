"""Merge the hand-transcribed database into this project's corpus frames.

The frames this writes are the same shape `merge_literature_corpus.py` writes, so the
dataset builder, the forward model and every evaluation read the merged corpus without
knowing it is merged. What is new is one column, `source_tier`, and one refusal.

The refusal is double counting. 10 of the 145 usable atlas cohorts name a trial this corpus
already holds for the same agent, so their patients are already counted; they are dropped,
and the only agent lost entirely is `loncastuximab_tesirine`, which the registry supplies.

The residual exposure is real and is measured rather than waved at. **88 of 145 cohorts name
no NCT number at all**, so for those the check cannot be run. It is only a risk where this
corpus already has arms for that agent -- for a genuinely new agent there is nothing to
collide with -- so the bound is the number of unidentifiable cohorts belonging to agents we
already had, and that number is reported in the artefact as
`residual_overlap_exposure_arms`.

`source_tier` exists because negative result 34 measured the reporting-source gap at up to
1.85 logit on a single axis, larger than the mechanism-by-axis scale the model exists to
estimate. The merged corpus holds four document kinds -- registry record, primary
publication, regulatory label, conference abstract or sponsor presentation -- and a
two-level registry/literature indicator cannot absorb four. Carrying the tier lets the
forward model keep its existing binary and lets a later specification use the finer level
without re-ingesting.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy
import merged_corpus_scale as _scale

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_N = 30


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=pathlib.Path,
                    default=ROOT / "data" / "raw" / "atlas" / "2026-10-10" / "adc_db.xlsx")
    ap.add_argument("--slots", type=pathlib.Path,
                    default=ROOT / "conf" / "ontology" / "atlas_design_slots.yaml")
    ap.add_argument("--atlas", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "atlas")
    ap.add_argument("--base", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_final")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_atlas")
    ap.add_argument("--report", type=pathlib.Path,
                    default=ROOT / "artifacts" / "atlas_merge.json")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    args = ap.parse_args()

    slots = yaml.safe_load(args.slots.read_text(encoding="utf-8"))
    axes = list(Taxonomy().axis_order)

    base_arms = pd.read_parquet(args.base / "arms.parquet")
    base_obs = pd.read_parquet(args.base / "observations.parquet")

    arms = pd.read_parquet(args.atlas / "arms_raw.parquet")
    obs = pd.read_parquet(args.atlas / "observations_raw.parquet")
    arms = arms[arms.n_at_risk >= args.min_n].copy()

    # Trial identifiers, for the one check that stops the same patients being counted twice.
    trial = pd.read_excel(args.workbook, sheet_name="TRIAL")
    trial["agent"] = trial["ADC ID"].astype(str).str.lower().str.replace("-", "_")
    trial["nct"] = trial["NCT number"].astype(str).str.extract(r"(NCT\d{8})")[0]
    arms = arms.merge(trial[["Trial ID", "agent", "nct", "Indication", "Phase"]]
                      .rename(columns={"Trial ID": "trial_id"}),
                      on=["trial_id", "agent"], how="left")

    design = _scale._atlas_design(args.workbook, slots)
    arms = arms.merge(design, on="agent", how="left")
    unassignable = set(slots.get("unassignable") or {})
    arms = arms[arms.mechanism.notna() & ~arms.agent.isin(unassignable)]

    base_pairs = set(zip(base_arms.agent.astype(str), base_arms.nct_id.astype(str)))
    already = arms.apply(lambda r: (str(r.agent), str(r.nct)) in base_pairs, axis=1)
    dropped_dup = int(already.sum())
    arms = arms[~already]

    base_agents = set(base_arms.agent.dropna().astype(str))
    # The bound on what the NCT check could not see.
    blind = arms.nct.isna() & arms.agent.isin(base_agents)
    exposure = {
        "arms_without_nct": int(arms.nct.isna().sum()),
        "residual_overlap_exposure_arms": int(blind.sum()),
        "residual_overlap_exposure_agents": sorted(set(arms.loc[blind, "agent"])),
        "note": ("An atlas cohort with no NCT number cannot be checked against the base "
                 "corpus. The risk only exists where the base corpus already has arms for "
                 "that agent; for a new agent there is nothing to collide with."),
    }

    obs = obs[obs.arm_key.isin(set(arms.arm_key))]

    # --- arms, in the base schema ---
    out_arms = pd.DataFrame({
        "nct_id": arms.nct.fillna("").astype(str),
        "group_id": arms.trial_id.astype(str),
        "arm_key": arms.arm_key.astype(str),
        "title": arms.dose.fillna("").astype(str),
        "agent": arms.agent.astype(str),
        "layer": "atlas",
        "is_monotherapy": arms.monotherapy.astype(str).str.strip().str.lower().eq("yes"),
        "is_comparator": False,
        "n_combo_agents": np.where(
            arms.monotherapy.astype(str).str.strip().str.lower().eq("yes"), 1, 2),
        "n_at_risk_other": arms.n_at_risk.astype(float),
        "n_at_risk_serious": np.nan,
        # The reporting cut, as an upper bound: the smallest percentage the cohort printed.
        "frequency_threshold": arms.frequency_threshold.astype(float),
        "phase": arms.Phase.fillna("").astype(str),
        "start_date": "",
        "results_posted": "",
        "mechanism": arms.mechanism.astype(str),
        "payload_family": arms.payload_family.astype(str),
        "payload": arms.payload.astype(str),
        "linker_type": "",
        "linker_cleavable": arms.cleavable,
        "dar": arms.dar.astype(float),
        "isotype": "",
        "target": arms.target.fillna("").astype(str),
        "conventional_adc": True,
        "n_at_risk": arms.n_at_risk.astype(float),
        "n_at_risk_grade3": np.nan,
        "threshold_is_upper_bound": True,
        "column_outcome": "any_grade",
        "agent_class_column": False,
        "source": "atlas",
        "pmcid": "",
        "journal": "",
        "license_code": "",
        "attribution_gate": "hand_transcribed",
        "source_tier": arms.source_tier.astype(str),
    })

    # --- observations, in the base schema ---
    obs = obs.merge(out_arms[["arm_key", "nct_id", "frequency_threshold"]],
                    on="arm_key", how="left")
    out_obs = pd.DataFrame({
        "arm_key": obs.arm_key.astype(str),
        "nct_id": obs.nct_id.astype(str),
        "agent": obs.agent.astype(str),
        "axis": obs.axis.astype(str),
        "kind": "other",
        "n_affected": obs.n_affected.astype(int),
        "n_at_risk": obs.n_at_risk.astype(int),
        "sum_affected_terms": obs.sum_affected_terms.astype(int),
        "n_terms": obs.n_terms.astype(int),
        "frequency_threshold": obs.frequency_threshold.astype(float),
    })

    # The base frames gain the column so a concat does not produce a ragged frame. The
    # registry and literature arms are a tier each, which is what they already were.
    base_arms = base_arms.copy()
    if "source_tier" not in base_arms.columns:
        # `source` is "pmc" for the literature arms and null for the registry ones -- the
        # registry predates the column. Keyed on that rather than on a guessed sentinel: an
        # earlier version tested `== "ctgov"`, which no row carries, and silently labelled
        # all 2,201 registry arms as publications.
        base_arms["source_tier"] = np.where(
            base_arms["source"].astype(str).eq("pmc"), "publication", "registry")

    merged_arms = pd.concat([base_arms, out_arms], ignore_index=True)
    merged_obs = pd.concat([base_obs, out_obs], ignore_index=True)

    args.out.mkdir(parents=True, exist_ok=True)
    merged_arms.to_parquet(args.out / "arms.parquet", index=False)
    merged_obs.to_parquet(args.out / "observations.parquet", index=False)

    report = {
        "min_n": args.min_n,
        "base": {"arms": int(len(base_arms)), "agents": int(base_arms.agent.nunique()),
                 "observations": int(len(base_obs))},
        "atlas_added": {"arms": int(len(out_arms)), "agents": int(out_arms.agent.nunique()),
                        "observations": int(len(out_obs)),
                        "new_agents": sorted(set(out_arms.agent) - base_agents)},
        "merged": {"arms": int(len(merged_arms)),
                   "agents": int(merged_arms.agent.nunique()),
                   "observations": int(len(merged_obs))},
        "dropped_as_already_counted": dropped_dup,
        "overlap_exposure": exposure,
        "source_tiers": {k: int(v) for k, v in
                         merged_arms.source_tier.value_counts().items()},
        "threshold_is_upper_bound_share": float(
            merged_arms.threshold_is_upper_bound.fillna(False).astype(bool).mean()),
    }
    write_json(args.report, report)

    print(f"base    arms {report['base']['arms']:5}  agents {report['base']['agents']:3}")
    print(f"atlas   arms {report['atlas_added']['arms']:5}  agents "
          f"{report['atlas_added']['agents']:3}  new {len(report['atlas_added']['new_agents'])}")
    print(f"merged  arms {report['merged']['arms']:5}  agents {report['merged']['agents']:3}  "
          f"observations {report['merged']['observations']}")
    print(f"dropped as already counted: {dropped_dup}")
    print(f"residual overlap exposure: {exposure['residual_overlap_exposure_arms']} arms "
          f"over {len(exposure['residual_overlap_exposure_agents'])} agents "
          f"({exposure['arms_without_nct']} atlas arms name no NCT)")
    print(f"source tiers: {report['source_tiers']}")
    print(f"-> {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
