"""Check extracted paper rates against the registry's own numbers for the same arms.

This is the only external test the extractor gets, and it exists because of an accident of
scope: all 18 registry agents already have ClinicalTrials.gov arms, so fetching their
papers adds no agents. What it adds is an overlap -- the same patients, the same events,
counted twice by two independent routes. One route is a structured public-domain record;
the other is this pipeline reading a PDF-era table out of JATS. If they disagree, the
pipeline is wrong, and that has to be measured before the pipeline is pointed at the ~36
agents that have no registry record to check against.

Three comparisons, in increasing difficulty.

**The denominator.** A paper's column header and the registry's `n_at_risk` describe the
same safety population, so they should be the same integer. This is the cleanest possible
structural check: it depends on the header parse, the span expansion and the arm
attribution all being right, and it does not depend on the row labels or the axis map at
all. A denominator mismatch localises the fault immediately.

**The axis rate.** The registry stores `n_affected` as the maximum over terms within an
axis -- "any event in this organ" -- so the paper's cells are aggregated the same way.
Taking the maximum rather than the sum is what makes the comparison survive a threshold
difference: the largest term in an organ clears both a 5% and a 10% cut, while the sum does
not. Even so this is not expected to agree exactly, and the reasons are listed with the
output rather than discovered afterwards.

**The axis ranking.** The product ranks organs, so the question that matters is whether the
paper route ranks them the way the registry route does, which is a weaker and more
relevant claim than per-cell agreement.

What a disagreement does *not* prove is that the paper is wrong. A journal report and a
registry posting are different data cuts of the same trial, taken at different dates, and
the registry's `frequencyThreshold` differs from the paper's. So the output separates the
failures that can only be the extractor (a wrong denominator, a rate above 100%, a count
above its denominator) from the differences a data cut could explain.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import stamp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OBS = ROOT / "data" / "processed" / "observations.parquet"

# A rate difference this large or smaller is treated as agreement. Chosen to be loose: the
# two routes are different data cuts, and the question here is whether the extractor is
# broken, not whether the two reports are identical.
RATE_TOLERANCE_PP = 5.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    rows = [json.loads(ln) for ln in args.cells.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    if not rows:
        print("no extracted cells; nothing to validate", file=sys.stderr)
        return 1
    cells = pd.DataFrame(rows)
    obs = pd.read_parquet(OBS)

    # ---- hard failures: things no data cut can explain --------------------------
    hard = {
        "count_exceeds_denominator": int((cells["n"] > cells["denominator"]).sum()),
        "rate_above_100": int(
            (100.0 * cells["n"] / cells["denominator"] > 100.0).sum()
        ),
        "arithmetic_gate_failed": int((cells["arithmetic_ok"] == False).sum()),  # noqa: E712
        "denominator_below_3": int((cells["denominator"] < 3).sum()),
    }
    print("추출기 자체 오류 (데이터 cut으로 설명 불가)")
    for k, v in hard.items():
        print(f"  {k:28s} {v:6d}  / {len(cells)}")

    # ---- aggregate the paper cells the way the registry does --------------------
    linked = cells[cells["nct_id"].notna()].copy()
    if linked.empty:
        print("\n시험에 연결된 셀이 없어 비교할 수 없습니다")
        return 1
    paper = (
        linked.groupby(["nct_id", "agent", "axis", "pmcid", "column_header"],
                       as_index=False)
        .agg(n_affected=("n", "max"), n_at_risk=("denominator", "max"),
             n_terms=("n", "size"),
             threshold=("threshold_pct", "min"))
    )
    paper["rate"] = 100.0 * paper["n_affected"] / paper["n_at_risk"]

    reg = obs[obs["agent"].notna()].copy()
    reg["rate"] = 100.0 * reg["n_affected"] / reg["n_at_risk"]

    out: dict = {"provenance": stamp({"observations": OBS, "cells": args.cells}),
                 "extractor_hard_failures": hard,
                 "n_paper_cells": int(len(cells)),
                 "rate_tolerance_pp": RATE_TOLERANCE_PP}

    # ---- the denominator check --------------------------------------------------
    reg_arm = (
        reg.groupby(["nct_id", "agent"], as_index=False)
        .agg(reg_n_at_risk=("n_at_risk", "max"))
    )
    denom = paper.merge(reg_arm, on=["nct_id", "agent"], how="inner")
    if denom.empty:
        print("\n레지스트리와 겹치는 (시험, 약물)이 없습니다 — 검증 불가")
        out["overlap"] = 0
        args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        return 0
    per_arm = denom.drop_duplicates(["nct_id", "agent", "pmcid", "column_header"])
    exact = int((per_arm["n_at_risk"] == per_arm["reg_n_at_risk"]).sum())
    print(f"\n분모 일치: {exact}/{len(per_arm)} "
          f"({100.0 * exact / len(per_arm):.1f}%) "
          f"[헤더 파싱 + colspan + 귀속이 모두 맞아야 통과]")
    mism = per_arm[per_arm["n_at_risk"] != per_arm["reg_n_at_risk"]]
    for _, r in mism.head(12).iterrows():
        print(f"  {r['nct_id']} {r['agent'][:22]:22s} "
              f"논문 {r['n_at_risk']:5d}  레지스트리 {r['reg_n_at_risk']:5d}  "
              f"{str(r['column_header'])[:40]}")
    out["denominator"] = {
        "n_arms_compared": int(len(per_arm)),
        "n_exact": exact,
        "exact_rate": exact / len(per_arm),
        "mismatches": [
            {"nct_id": r["nct_id"], "agent": r["agent"],
             "paper": int(r["n_at_risk"]), "registry": int(r["reg_n_at_risk"]),
             "pmcid": r["pmcid"], "column_header": str(r["column_header"])[:120]}
            for _, r in mism.iterrows()
        ][:60],
    }

    # ---- the rate check, per event table ---------------------------------------
    print(f"\n축별 비율 비교 (허용 {RATE_TOLERANCE_PP:.0f}pp)")
    rate_block: dict = {}
    for kind in ("other", "serious"):
        sub = reg[reg["kind"] == kind][["nct_id", "agent", "axis", "rate",
                                        "n_affected", "n_at_risk"]]
        m = paper.merge(sub, on=["nct_id", "agent", "axis"], how="inner",
                        suffixes=("_paper", "_reg"))
        if m.empty:
            print(f"  {kind:8s} 겹치는 셀 0개")
            rate_block[kind] = {"n": 0}
            continue
        d = (m["rate_paper"] - m["rate_reg"]).to_numpy()
        within = int((np.abs(d) <= RATE_TOLERANCE_PP).sum())
        rho = (
            float(stats.spearmanr(m["rate_paper"], m["rate_reg"]).statistic)
            if len(m) >= 4 else float("nan")
        )
        print(f"  {kind:8s} 셀 {len(m):5d}  "
              f"허용 내 {within:5d} ({100.0 * within / len(m):5.1f}%)  "
              f"중앙 차이 {np.median(d):+6.1f}pp  "
              f"평균 {np.mean(d):+6.1f}pp  Spearman {rho:+.3f}")
        rate_block[kind] = {
            "n": int(len(m)), "n_within_tolerance": within,
            "within_rate": within / len(m),
            "median_delta_pp": float(np.median(d)),
            "mean_delta_pp": float(np.mean(d)),
            "spearman": rho,
            "by_axis": {
                axis: {
                    "n": int(len(g)),
                    "median_delta_pp": float(np.median(
                        g["rate_paper"] - g["rate_reg"])),
                }
                for axis, g in m.groupby("axis")
            },
        }
        print(f"    {'axis':24s} {'셀':>5s} {'중앙차이':>9s}")
        for axis, g in sorted(m.groupby("axis"),
                              key=lambda kv: -abs(np.median(
                                  kv[1]["rate_paper"] - kv[1]["rate_reg"]))):
            md = float(np.median(g["rate_paper"] - g["rate_reg"]))
            print(f"    {axis:24s} {len(g):5d} {md:+8.1f}pp")
    out["rates"] = rate_block

    # ---- the ranking check ------------------------------------------------------
    sub = reg[reg["kind"] == "other"][["nct_id", "agent", "axis", "rate"]]
    m = paper.merge(sub, on=["nct_id", "agent", "axis"], how="inner",
                    suffixes=("_paper", "_reg"))
    rhos: list[float] = []
    for (nct, agent, pmcid, col), g in m.groupby(
        ["nct_id", "agent", "pmcid", "column_header"]
    ):
        if len(g) >= 4 and g["rate_paper"].nunique() > 1 and g["rate_reg"].nunique() > 1:
            rhos.append(float(stats.spearmanr(g["rate_paper"],
                                              g["rate_reg"]).statistic))
    if rhos:
        print(f"\n팔별 축 순위 상관: arm {len(rhos)}개, "
              f"중앙 rho {np.median(rhos):+.3f}, 평균 {np.mean(rhos):+.3f}  "
              f"[제품이 쓰는 건 순위이므로 이게 셀별 일치보다 관련성이 높습니다]")
        out["ranking"] = {
            "n_arms": len(rhos), "median_rho": float(np.median(rhos)),
            "mean_rho": float(np.mean(rhos)),
            "rhos": [round(r, 4) for r in rhos],
        }
    else:
        print("\n순위 상관을 계산할 arm이 없습니다 (축 4개 이상 겹치는 arm 필요)")
        out["ranking"] = {"n_arms": 0}

    out["caveats"] = [
        "A journal report and a registry posting are different data cuts of the same "
        "trial, taken at different dates, so exact agreement is not expected.",
        "The reporting thresholds differ, which changes which terms reach an axis. "
        "Aggregating by the maximum over terms rather than the sum limits but does not "
        "remove the effect.",
        "The registry's own numbers are not ground truth; they are a second measurement.",
        "A paper's column may pool doses the registry splits, or the reverse.",
        "Only the denominator check and the hard-failure counts isolate the extractor; "
        "every rate difference has at least two possible causes.",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
