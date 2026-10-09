"""What makes these fits converge, measured across every fit on disk?

A prediction was written down before the merged corpus was fitted: that it would fail its
seed-agreement check. The reasoning was specific. The 32-agent fit failed at 0.722, the
cause was traced to the censoring model applied to arms whose reporting cut is only an upper
bound (negative result 50), and the merged corpus has worse arms of that kind -- the
transcribed cohorts reach a 71% cut against the literature's 63.9%.

The prediction was wrong, and being wrong in a checkable way is what this script exists to
keep. It puts every fit's seed gap beside the two quantities that could explain it -- the
identifying cells per design parameter, and how much of the grid is censored -- so the
condition is read off a table rather than argued from one case.

No verdict is computed. Three or four fits cannot support one, and a script that announced a
rule from four rows would be the same overreach as the prediction it is checking.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]

# label -> (artefact directory, the processed corpus, whether absences were dropped)
FITS = [
    ("registry, default", "artifacts", "data/processed", False),
    ("32 agents, default", "artifacts/with_literature_final",
     "data/processed/with_literature_final", False),
    ("32 agents, absences dropped", "artifacts/with_literature_dropabs",
     "data/processed/with_literature_final", True),
    ("explicit cuts only", "artifacts/with_explicit_threshold",
     "data/processed/with_explicit_threshold", False),
    ("65 agents, default", "artifacts/with_atlas", "data/processed/with_atlas", False),
    ("65 agents, absences dropped", "artifacts/with_atlas_dropabs",
     "data/processed/with_atlas", True),
    ("65 agents, payload family", "artifacts/with_atlas_family",
     "data/processed/with_atlas", False),
]


def _corpus_counts(summary: str) -> dict:
    """Read the counts out of the fit's own corpus line rather than rebuilding the grid.

    The grid is expensive to rebuild and the fit already wrote what it saw; rebuilding could
    also disagree with it if the frames have moved since, which is the failure negative
    result 51 cost an hour to.
    """
    import re

    out: dict = {}
    m = re.search(r"([\d,]+) cells over ([\d,]+) arms", summary or "")
    if m:
        out["cells"] = int(m.group(1).replace(",", ""))
        out["arms"] = int(m.group(2).replace(",", ""))
    m = re.search(r"([\d,]+) observed, ([\d,]+) censored", summary or "")
    if m:
        out["observed"] = int(m.group(1).replace(",", ""))
        out["censored"] = int(m.group(2).replace(",", ""))
    m = re.search(r"\| (\d+) agents", summary or "")
    if m:
        out["agents"] = int(m.group(1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "convergence_conditions.json")
    args = ap.parse_args()

    rows = []
    for label, art, corpus, dropped in FITS:
        path = ROOT / art / "forward_other_metrics.json"
        if not path.exists():
            rows.append({"fit": label, "status": "not fitted yet",
                         "absences_dropped": dropped})
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        sa = doc.get("seed_agreement") or {}
        counts = _corpus_counts(doc.get("corpus", ""))
        params = doc.get("parameters") or {}
        censored_share = (
            counts["censored"] / counts["cells"]
            if counts.get("cells") else None
        )
        rows.append({
            "fit": label,
            "status": "fitted",
            "absences_dropped": dropped,
            "agents": counts.get("agents"),
            "cells": counts.get("cells"),
            "censored": counts.get("censored"),
            "censored_share": round(censored_share, 4) if censored_share else None,
            "identifying_cells": params.get("identifying_cells"),
            "cells_per_design_parameter": params.get("design_ratio_vs_identifying"),
            "worst_seed_gap": sa.get("worst_standardized_gap"),
            "seed_threshold": sa.get("threshold"),
            "converged": sa.get("converged"),
            "tau_mech": (doc.get("tau_mech") or {}).get("mean"),
            "tau_cleav": (doc.get("tau_cleav") or {}).get("mean"),
            "sigma_agent": (doc.get("coefficients") or {}).get("sigma_agent", {}).get("mean"),
        })

    fitted = [r for r in rows if r["status"] == "fitted" and r["converged"] is not None]
    doc = {
        "prediction": {
            "made": "the merged corpus will fail its seed-agreement check",
            "because": ("the 32-agent fit failed at 0.722, the cause was the censoring "
                        "model on upper-bound reporting cuts, and the merged corpus's "
                        "transcribed cohorts reach a 71% cut against the literature's "
                        "63.9%"),
            "outcome": None,  # filled below once the merged fit has landed
        },
        "fits": rows,
        "summary": {
            "n_fitted": len(fitted),
            "n_converged": sum(1 for r in fitted if r["converged"]),
            "failed": [r["fit"] for r in fitted if not r["converged"]],
        },
    }
    merged = next((r for r in fitted if r["fit"] == "65 agents, default"), None)
    if merged:
        doc["prediction"]["outcome"] = (
            "refuted" if merged["converged"] else "confirmed"
        )
        doc["prediction"]["merged_seed_gap"] = merged["worst_seed_gap"]
    write_json(args.out, doc)

    print(f"{'fit':30} {'agents':>7} {'ratio':>6} {'censored':>9} {'share':>6} "
          f"{'seed gap':>9} {'converged':>10}")
    for r in rows:
        if r["status"] != "fitted":
            print(f"{r['fit']:30} {'-- not fitted yet --':>49}")
            continue
        share = r["censored_share"]
        share_txt = f"{share:.2f}" if share is not None else "-"
        gap = r["worst_seed_gap"]
        gap_txt = f"{gap:.3f}" if gap is not None else "-"
        print(f"{r['fit']:30} {str(r['agents']):>7} "
              f"{str(r['cells_per_design_parameter']):>6} {str(r['censored']):>9} "
              f"{share_txt:>6} {gap_txt:>9} {str(r['converged']):>10}")
    if doc["prediction"]["outcome"]:
        print()
        print(f"prediction: {doc['prediction']['outcome']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
