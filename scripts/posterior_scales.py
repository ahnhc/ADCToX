"""Which corpus is each parameter's estimate worth taking from?

`sigma_agent` is the residual between-agent scale, and the product adds a draw from it to
every prediction for a new design, because two ADCs with identical slots do differ. So its
value is not a diagnostic -- it sets the width of every interval the product shows.

It is also the parameter most exposed to the confound result 39 found: where an agent's arms
all come from one source, its intercept and the reporting-source term are collinear, so
`u_agent` absorbs the reporting gap and `sigma_agent` measures the two together. That share
differs by corpus, and it differs in the *opposite* direction from the identification ratio:
the merged corpus crosses the 8:1 floor for the design terms and takes the single-source
share from 47% to 67%.

This writes both facts side by side for every posterior on disk, so the serving decision is
read off a table rather than argued. It reports no verdict: which parameter to take from
which corpus is a judgement, and the table is what the judgement has to answer to.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds
from adctox.model.predict import Posterior
from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]

# posterior file -> the processed corpus it was fitted on
CORPORA = [
    ("registry", "artifacts/posterior_other.npz", "data/processed"),
    ("expanded", "artifacts/expanded/posterior_other.npz",
     "data/processed/with_literature_final"),
    ("merged", "artifacts/with_atlas/posterior_other.npz", "data/processed/with_atlas"),
]

SCALES = ("tau_mech", "tau_cleav", "sigma_agent", "sigma_trial",
          "b_combo", "b_dar", "b_thresh", "b_log_n")


def _single_source_share(path: pathlib.Path, grid_arms: set[str]) -> dict:
    """How many agents cannot tell the source term from their own intercept.

    Counted over the *arms the grid keeps*, by arm key, not over every row in the parquet
    and not over every arm of an agent the grid keeps. All three give different answers --
    62%, 64% and 67% on the merged corpus -- because the builder drops arms with no
    observation and below the denominator floor, and an agent whose only registry arm was
    dropped is literature-only as far as the fit is concerned. The fit's view is the one
    that decides whether a parameter is identified. Two quantities under one name is the
    defect negative results 38 and 44 are about, and this is the third place it appeared.
    """
    arms = pd.read_parquet(path / "arms.parquet")
    arms = arms[arms.arm_key.isin(grid_arms)]
    lit = (arms["source"].notna() if "source" in arms.columns
           else pd.Series(False, index=arms.index))
    # Two situations look alike in a share and are opposite in consequence. A corpus with no
    # source variation at all does not sample the source term, so nothing is confounded with
    # the agent intercept and `sigma_agent` means what its name says. A corpus where the
    # variation exists but some agents do not span it estimates the term *and* lets those
    # agents absorb it. Reporting "100% single-source" for the first would read as the worst
    # case when it is the clean one.
    if not lit.any():
        n = int(arms.agent.nunique())
        return {"agents": n, "both_sources": 0, "single_source": n,
                "single_source_share": None,
                "source_term_sampled": False,
                "note": ("No source variation in this corpus, so the source term is not "
                         "sampled and sigma_agent is not confounded with it.")}
    per = arms.assign(lit=lit).groupby("agent")["lit"].agg(["any", "all"])
    both = int(((per["any"]) & (~per["all"])).sum())
    n = len(per)
    return {
        "agents": n,
        "both_sources": both,
        "single_source": n - both,
        "single_source_share": round((n - both) / n, 4) if n else None,
        "source_term_sampled": True,
        "note": ("Source variation exists, so the term is sampled; agents that do not span "
                 "it absorb the reporting gap into their own intercept."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "posterior_scales.json")
    args = ap.parse_args()

    axes = list(Taxonomy().axis_order)
    rows = []
    for name, post_rel, corpus_rel in CORPORA:
        post_path, corpus_path = ROOT / post_rel, ROOT / corpus_rel
        if not post_path.exists() or not (corpus_path / "arms.parquet").exists():
            continue
        post = Posterior.load(post_path)
        data = ds.load(corpus_path, axes, kind="other")
        from adctox.model import forward
        acct = forward.n_free_parameters(data)
        row = {
            "corpus": name,
            "agents_in_grid": len(data.agents),
            "identifying_cells": int(acct["identifying_cells"]),
            "cells_per_design_parameter": acct["design_ratio_vs_identifying"],
            "identifiability": _single_source_share(corpus_path, set(data.arm_keys)),
            "scales": {},
        }
        for scale in SCALES:
            v = getattr(post, scale, None)
            if v is None:
                continue
            a = np.asarray(v, dtype=float).ravel()
            lo, hi = float(np.percentile(a, 5)), float(np.percentile(a, 95))
            row["scales"][scale] = {
                "mean": float(a.mean()), "q05": lo, "q95": hi,
                "width": hi - lo,
                # A zero-width interval is a frozen sampler, not a precise estimate. It is
                # how the DAR parse error of result 47 presented itself, so it is flagged
                # here rather than left for a reader to notice.
                "degenerate": bool(hi - lo < 1e-6),
            }
        rows.append(row)

    degenerate = [
        f"{r['corpus']}/{k}" for r in rows for k, v in r["scales"].items()
        if v["degenerate"]
    ]
    doc = {
        "corpora": rows,
        "summary": {
            "n_posteriors": len(rows),
            "degenerate_parameters": degenerate,
            # The two facts that move in opposite directions, side by side.
            "tradeoff": [
                {"corpus": r["corpus"],
                 "cells_per_design_parameter": r["cells_per_design_parameter"],
                 "single_source_share": r["identifiability"]["single_source_share"],
                 "sigma_agent": r["scales"].get("sigma_agent", {}).get("mean")}
                for r in rows
            ],
        },
    }
    write_json(args.out, doc)

    print(f"{'corpus':10} {'agents':>7} {'cells':>6} {'ratio':>6} "
          f"{'single-source':>14} {'sigma_agent':>24}")
    for r in rows:
        ident = r["identifiability"]
        ss = ident["single_source_share"]
        sa = r["scales"].get("sigma_agent")
        sa_txt = (f"{sa['mean']:+.4f} [{sa['q05']:+.4f},{sa['q95']:+.4f}]"
                  if sa else "-")
        print(f"{r['corpus']:10} {r['agents_in_grid']:>7} {r['identifying_cells']:>6} "
              f"{r['cells_per_design_parameter']:>6} "
              f"{(f'{ss:.0%}' if ss is not None else 'n/a, 1 source'):>14} "
              f"{sa_txt:>24}")
    if degenerate:
        print(f"\nDEGENERATE (zero-width interval, a frozen sampler): {degenerate}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
