#!/usr/bin/env python
"""Resolve event groups to agents, build the (arm x axis) observation table, run Gate 1b.

Gate 1a (taxonomy coverage) is a necessary check but a weak one. Gate 1b is the one that
catches a wrong axis mapping: if the corpus is assembled correctly, the baseline-centered
organ fingerprint of each payload mechanism must reproduce the pharmacology that is
already in the FDA labels -- tubulin payloads topping the haematologic and neurologic
axes, topoisomerase-I payloads topping pulmonary and gastrointestinal. If it does not,
the mapping is wrong and no amount of modelling will fix it.

Writes data/processed/arms.parquet and observations.parquet.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.extract.arm_resolver import Registry, resolve_study  # noqa: E402
from adctox.taxonomy import (  # noqa: E402
    AXIS_DROPPED,
    AXIS_EXCLUDED,
    AXIS_UNMAPPED,
    Taxonomy,
    parse_frequency_threshold,
)

SENTINELS = {AXIS_UNMAPPED, AXIS_EXCLUDED, AXIS_DROPPED}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/processed"))
    ap.add_argument("--min-n", type=int, default=30)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    registry = Registry.load()
    tax = Taxonomy()
    dict_path = args.out / "pt_soc_dictionary.json"
    if dict_path.exists():
        tax.load_pt_dictionary(dict_path)

    arm_rows: list[dict] = []
    obs_rows: list[dict] = []
    layers: Counter[str] = Counter()

    for path in sorted(args.studies.glob("*.json")):
        study = json.loads(path.read_text(encoding="utf-8"))
        ae = (study.get("resultsSection") or {}).get("adverseEventsModule") or {}
        if not ae:
            continue
        proto = study.get("protocolSection") or {}
        status = proto.get("statusModule") or {}
        design = proto.get("designModule") or {}
        threshold = parse_frequency_threshold(ae.get("frequencyThreshold"))
        phases = (design.get("phases") or [])
        start = (status.get("startDateStruct") or {}).get("date")
        posted = (status.get("resultsFirstPostDateStruct") or {}).get("date")

        resolved = resolve_study(study, registry)
        by_gid = {r.group_id: r for r in resolved}
        for r in resolved:
            layers[r.layer] += 1
            spec = registry.agents.get(r.agent) if r.agent else None
            arm_rows.append(
                {
                    "nct_id": r.nct_id,
                    "group_id": r.group_id,
                    "arm_key": f"{r.nct_id}:{r.group_id}",
                    "title": r.title,
                    "agent": r.agent,
                    "layer": r.layer,
                    "is_monotherapy": r.is_monotherapy,
                    "is_comparator": r.is_comparator,
                    "n_combo_agents": len(r.combo_agents),
                    "n_at_risk_other": r.n_at_risk_other,
                    "n_at_risk_serious": r.n_at_risk_serious,
                    "frequency_threshold": threshold,
                    "phase": phases[0] if phases else None,
                    "start_date": start,
                    "results_posted": posted,
                    "mechanism": spec["mechanism"] if spec else None,
                    "payload_family": spec["payload_family"] if spec else None,
                    "payload": spec["payload"] if spec else None,
                    "linker_type": spec["linker_type"] if spec else None,
                    "linker_cleavable": spec["linker_cleavable"] if spec else None,
                    "dar": spec["dar"] if spec else None,
                    "isotype": spec["isotype"] if spec else None,
                    "target": spec["target"] if spec else None,
                    "conventional_adc": spec["conventional_adc"] if spec else None,
                }
            )

        # (arm x axis) observations, aggregated over terms within an axis.
        # Serious and other events are kept apart: `frequencyThreshold` truncates
        # otherEvents only, so pooling them would mix a censored and an uncensored
        # measurement of the same axis.
        agg: dict[tuple[str, str, str], dict] = {}
        for kind in ("otherEvents", "seriousEvents"):
            tag = "serious" if kind == "seriousEvents" else "other"
            for event in ae.get(kind) or []:
                axis, _prov = tax.resolve(event.get("term"), event.get("organSystem"))
                if axis in SENTINELS:
                    continue
                for stat in event.get("stats") or []:
                    gid = stat.get("groupId")
                    if gid not in by_gid:
                        continue
                    affected = stat.get("numAffected")
                    at_risk = stat.get("numAtRisk")
                    if affected is None or not at_risk:
                        continue
                    key = (gid, axis, tag)
                    cur = agg.setdefault(
                        key,
                        {"max_affected": 0, "sum_affected": 0, "at_risk": at_risk, "n_terms": 0},
                    )
                    cur["max_affected"] = max(cur["max_affected"], affected)
                    cur["sum_affected"] += affected
                    cur["n_terms"] += 1
                    cur["at_risk"] = max(cur["at_risk"], at_risk)

        for (gid, axis, tag), v in agg.items():
            r = by_gid[gid]
            obs_rows.append(
                {
                    "arm_key": f"{r.nct_id}:{gid}",
                    "nct_id": r.nct_id,
                    "agent": r.agent,
                    "axis": axis,
                    "kind": tag,
                    # The binomial numerator is the max over terms in the axis, not the
                    # sum: a patient with both nausea and vomiting is one patient with
                    # GI toxicity, and summing would let an axis exceed its denominator.
                    "n_affected": v["max_affected"],
                    "n_at_risk": v["at_risk"],
                    "sum_affected_terms": v["sum_affected"],
                    "n_terms": v["n_terms"],
                    "frequency_threshold": threshold,
                }
            )

    arms = pd.DataFrame(arm_rows)
    obs = pd.DataFrame(obs_rows)

    # ------------------------------------------------------------------- funnel
    n_at_risk = arms[["n_at_risk_other", "n_at_risk_serious"]].max(axis=1)
    arms["n_at_risk"] = n_at_risk
    attributed = arms["agent"].notna()
    big = arms["n_at_risk"] >= args.min_n
    print("Event-group funnel")
    print(f"  studies with AE module          : {arms['nct_id'].nunique():,}")
    print(f"  total event groups              : {len(arms):,}")
    print(f"  n_at_risk >= {args.min_n:<19d}: {int(big.sum()):,}")
    print(f"  attributed to one ADC           : {int(attributed.sum()):,}")
    print(f"  attributed AND n >= {args.min_n:<12d}: {int((attributed & big).sum()):,}")
    surv = arms[attributed & big]
    print(f"    monotherapy                   : {int((surv['is_monotherapy'] == True).sum()):,}")
    print(f"    combination                   : {int((surv['is_monotherapy'] == False).sum()):,}")
    print(f"\n  resolution layers")
    for layer, n in layers.most_common():
        print(f"    {n:6,d}  {layer}")

    print(f"\nSurviving arms: {len(surv):,} across {surv['agent'].nunique()} agents")
    print(f"  distinct targets   : {surv['target'].nunique()}")
    print(f"  distinct mechanisms: {surv['mechanism'].nunique()}")
    print(f"\n  {'mechanism':16s} {'arms':>6s} {'agents':>7s}  holdout")
    for mech, grp in surv.groupby("mechanism"):
        n_ag = grp["agent"].nunique()
        print(f"  {mech:16s} {len(grp):6,d} {n_ag:7d}  {'VIABLE' if n_ag >= 3 else 'degenerate'}")

    print(f"\n  {'agent':28s} {'arms':>5s} {'patients':>9s}")
    for agent, grp in surv.groupby("agent"):
        print(f"  {agent:28s} {len(grp):5,d} {int(grp['n_at_risk'].sum()):9,d}")

    # --------------------------------------------------- (arm x axis) fill rate
    keep = obs[obs["arm_key"].isin(set(surv["arm_key"]))]
    cells = keep.groupby(["arm_key", "axis"]).size()
    n_cells = len(cells)
    print(f"\n(arm x axis) observations")
    print(f"  surviving arms x 14 axes : {len(surv) * 14:,}")
    print(f"  cells with data          : {n_cells:,}")
    print(f"  fill rate                : {100 * n_cells / max(len(surv) * 14, 1):.1f}%")
    print(f"  identifying cells (agents x 14) : {surv['agent'].nunique() * 14:,}")

    # ------------------------------------------------------------------ GATE 1b
    print(f"\n{'=' * 72}\nGATE 1b -- mechanism organ fingerprints (baseline-centered)\n{'=' * 72}")
    # Serious-only, monotherapy-only: the cleanest signal available. Rates are logit-
    # transformed, then the per-axis mean over all arms is removed, because the raw
    # profile is dominated by "every cytotoxic hits GI and blood" and that baseline
    # alone reproduces a 0.75 correlation with any drug.
    base = keep.merge(
        surv[["arm_key", "mechanism", "is_monotherapy"]], on="arm_key", how="inner"
    )
    base = base[(base["kind"] == "serious") & (base["is_monotherapy"] == True)]
    if base.empty:
        print("  no monotherapy serious-event rows; cannot run Gate 1b")
        return 1
    base["rate"] = base["n_affected"] / base["n_at_risk"]
    eps = 0.5 / base["n_at_risk"]
    base["logit"] = ((base["rate"] + eps) / (1 - base["rate"] + eps)).apply(math.log)
    axis_mean = base.groupby("axis")["logit"].mean()
    base["centered"] = base["logit"] - base["axis"].map(axis_mean)

    prof = base.groupby(["mechanism", "axis"])["centered"].mean().unstack(fill_value=float("nan"))
    expected = {
        "tubulin": {"haematologic", "neurologic"},
        "topo1": {"pulmonary", "gastrointestinal"},
        "dna_cleave": {"hepatic"},
    }
    ok = True
    for mech, want in expected.items():
        if mech not in prof.index:
            print(f"  {mech:16s} absent from monotherapy corpus -- cannot check")
            continue
        row = prof.loc[mech].dropna().sort_values(ascending=False)
        top3 = set(row.head(3).index)
        hit = want & top3
        verdict = "PASS" if hit else "FAIL"
        if not hit:
            ok = False
        print(f"\n  {mech} ({verdict}: expected any of {sorted(want)} in top 3)")
        for axis, val in row.head(5).items():
            mark = " <--" if axis in want else ""
            print(f"      {axis:22s} {val:+.3f}{mark}")

    # Persist the fingerprints. The report quotes these values, so printing them and
    # dropping them would leave a figure in the prose with nothing behind it.
    fingerprints = {
        mech: {axis: float(val) for axis, val in row.dropna().items()}
        for mech, row in prof.iterrows()
    }
    arms.to_parquet(args.out / "arms.parquet", index=False)
    obs.to_parquet(args.out / "observations.parquet", index=False)
    (args.out / "arm_funnel.json").write_text(
        json.dumps(
            {
                "event_groups": len(arms),
                "attributed": int(attributed.sum()),
                "surviving_arms": len(surv),
                "monotherapy": int((surv["is_monotherapy"] == True).sum()),
                "agents": int(surv["agent"].nunique()),
                "arm_axis_cells": int(n_cells),
                "identifying_cells": int(surv["agent"].nunique() * 14),
                "layers": dict(layers),
                "gate_1b_pass": bool(ok),
                "mechanism_fingerprints_centered": fingerprints,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {args.out}/arms.parquet, observations.parquet, arm_funnel.json")
    print(f"\nGATE 1b {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
