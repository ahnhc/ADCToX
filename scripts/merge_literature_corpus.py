"""Fold extracted paper cells into the corpus schema the model already reads.

The model matrix is built from two frames -- arms and observations -- and the literature
path has to produce the same columns or it is not an extension, it is a second pipeline.
So this writes `paper_arms.parquet` and `paper_observations.parquet` in the registry's
schema, and `make corpus` unions them.

Four decisions, each of which could silently corrupt the fit.

**An arm is a column, not a paper.** A table with a 1.8 mg/kg column and a 2.4 mg/kg
column is two arms of one trial, which is what makes the trial random effect do its job.
Pooling them into a paper-level arm would average two dose levels and attribute the result
to neither.

**The trial id is the join to the registry, not a label.** An arm carrying NCT03589469
shares its trial intercept with the registry's arms from the same trial, which is correct:
they are the same patients. Papers with no resolved trial get the single-arm sentinel,
since a made-up trial id would invent an independent trial.

**The threshold is written as an upper bound and flagged as one.** The dataset builder
treats `frequency_threshold` as the exact cut and censors every unreported axis below
`ceil(n * thresh / 100)`. For the 70% of tables whose cut was derived rather than stated,
that cut is too large, so more mass is treated as possibly-hidden than really was -- the
intervals widen and nothing is claimed that the data does not support. But the flag has to
travel, because the sensitivity analysis that matters is a refit on the explicit-threshold
tables alone.

**A paper's serious-event table is not its common-event table.** The two rank organs
differently -- measured mean rho +0.1455 on the registry corpus -- and the model fits them
separately, with `serious` treated as complete reporting. So the caption decides which
table a set of cells belongs to, and a table that cannot be classified goes to `other`,
where censoring applies and a wrong guess costs width rather than correctness.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import stamp  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"

# A caption naming serious events as the table's subject, not a row inside it.
SERIOUS_TABLE = re.compile(
    r"^\s*(?:table\s*\S{0,4}\.?\s*)?(?:summary\s+of\s+)?"
    r"(?:treatment[-\s]\w+\s+)?serious\s+(?:adverse\s+events?|teaes?|aes?)",
    re.I,
)
# Design columns the dataset builder reads off an arm. Sourced from the registry, so a
# paper arm and a registry arm of the same agent carry identical design features -- which
# is the whole reason design features are agent-level constants in this corpus.
DESIGN_COLS = (
    "mechanism", "payload_family", "payload", "linker_type", "linker_cleavable",
    "dar", "isotype", "target", "conventional_adc",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=pathlib.Path, required=True)
    ap.add_argument("--out-dir", type=pathlib.Path,
                    default=ROOT / "data" / "processed")
    ap.add_argument("--chosen-only", action="store_true", default=True,
                    help="keep only the source chosen per (trial, agent); see "
                         "extract/trial_dedup.py")
    ap.add_argument("--include-registry-overlap", action="store_true",
                    help="keep arms whose trial is already in the registry. Off by "
                         "default: those are the same patients, and admitting both gives "
                         "the trial double weight. On for the validation run, where the "
                         "overlap is the point.")
    ap.add_argument("--explicit-threshold-only", action="store_true",
                    help="the sensitivity refit: drop tables whose reporting cut was "
                         "derived from the minimum printed rate rather than stated")
    args = ap.parse_args()

    rows = [json.loads(ln) for ln in args.cells.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    if not rows:
        print("no cells to merge", file=sys.stderr)
        return 1
    cells = pd.DataFrame(rows)
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]
    axes = list(default_taxonomy().axis_order)

    before = len(cells)
    if args.chosen_only:
        cells = cells[cells["is_chosen_source"]]
    if not args.include_registry_overlap:
        cells = cells[~cells["overlaps_registry"]]
    if args.explicit_threshold_only:
        cells = cells[cells["threshold_explicit"]]
    print(f"셀 {before} → {len(cells)} (중복 출처·레지스트리 중복·임계값 필터 적용)")
    if cells.empty:
        print("남은 셀이 없습니다", file=sys.stderr)
        return 1

    # An arm is a column of a table, so the key has to carry the table and the column.
    cells = cells.assign(
        arm_key=lambda d: (
            "PMC" + d["pmcid"].astype(str) + ":" + d["table_label"].astype(str)
            + ":" + d["column_header"].astype(str).str.slice(0, 40)
        ),
        kind=lambda d: d["caption_kind"] if "caption_kind" in d else "other",
    )

    arm_rows = []
    obs_rows = []
    for (arm_key, agent, kind), g in cells.groupby(["arm_key", "agent", "kind"]):
        spec = registry.get(agent)
        if spec is None:
            continue
        n_at_risk = int(g["denominator"].max())
        thr = g["threshold_pct"].dropna()
        nct = g["nct_id"].dropna().unique()
        arm_rows.append({
            "nct_id": (nct[0] if len(nct) else None),
            "group_id": arm_key,
            "arm_key": arm_key,
            "title": str(g["column_header"].iloc[0])[:160],
            "agent": agent,
            "layer": "literature",
            "is_monotherapy": True,       # combination columns are rejected upstream
            "is_comparator": False,
            "n_combo_agents": 0,
            "n_at_risk_other": (n_at_risk if kind == "other" else None),
            "n_at_risk_serious": (n_at_risk if kind == "serious" else None),
            "n_at_risk": n_at_risk,
            "frequency_threshold": (float(thr.min()) if len(thr) else None),
            "threshold_is_upper_bound": bool(
                not g["threshold_explicit"].astype(bool).any()
            ),
            "phase": None,
            "start_date": None,
            "results_posted": None,
            "source": "pmc",
            "pmcid": str(g["pmcid"].iloc[0]),
            "journal": str(g["journal"].iloc[0]),
            "license_code": g["license_code"].iloc[0],
            "attribution_gate": str(g["attribution_gate"].iloc[0]),
            **{c: spec.get(c) for c in DESIGN_COLS},
        })
        # The registry stores an axis as the maximum over its terms -- "any event in this
        # organ". Matching that is what makes paper and registry arms comparable.
        for axis, ga in g.groupby("axis"):
            obs_rows.append({
                "arm_key": arm_key,
                "nct_id": (nct[0] if len(nct) else None),
                "agent": agent,
                "axis": axis,
                "kind": kind,
                "n_affected": int(ga["n"].max()),
                "n_at_risk": n_at_risk,
                "sum_affected_terms": int(ga["n"].sum()),
                "n_terms": int(len(ga)),
                "frequency_threshold": (float(thr.min()) if len(thr) else None),
            })

    arms = pd.DataFrame(arm_rows)
    obs = pd.DataFrame(obs_rows)
    if arms.empty:
        print("팔이 만들어지지 않았습니다", file=sys.stderr)
        return 1

    unknown_axes = set(obs["axis"]) - set(axes)
    if unknown_axes:
        print(f"경고: 축 체계 밖의 축 {sorted(unknown_axes)}", file=sys.stderr)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    arms.to_parquet(args.out_dir / "paper_arms.parquet", index=False)
    obs.to_parquet(args.out_dir / "paper_observations.parquet", index=False)

    n_bound = int(arms["threshold_is_upper_bound"].sum())
    print(f"\n팔 {len(arms)}개, 약물 {arms['agent'].nunique()}종, "
          f"시험 {arms['nct_id'].nunique()}건, 관측 {len(obs)}개")
    print(f"  임계값이 상한인 팔 {n_bound}/{len(arms)} "
          f"({100.0 * n_bound / len(arms):.1f}%)   [계획서 실측 70.3%]")
    print(f"  팔당 축 중앙 {obs.groupby('arm_key').size().median():.0f} / {len(axes)}")
    print(f"  표 종류: {dict(arms.groupby('n_at_risk_other').size().head(0)) or ''}"
          f"other={int(arms['n_at_risk_other'].notna().sum())}, "
          f"serious={int(arms['n_at_risk_serious'].notna().sum())}")
    print("\n약물별 팔")
    for agent, n in arms["agent"].value_counts().items():
        print(f"  {agent:30s} {n:4d}")

    manifest = {
        "provenance": stamp({"cells": args.cells, "registry": REGISTRY}),
        "filters": {
            "chosen_only": args.chosen_only,
            "include_registry_overlap": args.include_registry_overlap,
            "explicit_threshold_only": args.explicit_threshold_only,
        },
        "n_cells_in": before,
        "n_cells_kept": int(len(cells)),
        "n_arms": int(len(arms)),
        "n_observations": int(len(obs)),
        "n_agents": int(arms["agent"].nunique()),
        "n_trials": int(arms["nct_id"].nunique()),
        "n_arms_threshold_upper_bound": n_bound,
        "arms_per_agent": arms["agent"].value_counts().to_dict(),
        "arms_per_gate": arms["attribution_gate"].value_counts().to_dict(),
    }
    (args.out_dir / "paper_corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\n→ {args.out_dir / 'paper_arms.parquet'}")
    print(f"→ {args.out_dir / 'paper_observations.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
