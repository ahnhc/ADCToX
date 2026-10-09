"""Is a leave-one-mechanism-out delta comparable across corpora?

The headline validation is leave-one-mechanism-out, and every corpus expansion has made it
worse: macro delta -0.0200 on the registry corpus, -0.1613 at 32 agents, -0.121 at 65. The
obvious reading is that the expansions damage generalisation, and it is probably right, but
one confound has to be removed first and it is mechanical.

Holding out a mechanism removes its agents from training. The expansions are **tubulin-heavy**
-- tubulin is 10 of 22 agents on the registry corpus, 16 of 32, and 41 of 65 -- so the
tubulin fold removes 45%, 50% and 63% of the corpus in turn. A fold that trains on a third
of the data is not the same test as one that trains on half, and tubulin is the fold that
dominates the macro average.

So this puts every fold's delta beside the share it removes, and asks whether the
degradation tracks the share. If it does, part of the headline is the expansion's
composition rather than its quality, and the comparison needs saying differently.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds
from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]

CORPORA = [
    ("registry", "artifacts", "data/processed"),
    ("expanded", "artifacts/with_literature_final", "data/processed/with_literature_final"),
    ("expanded, absences dropped", "artifacts/with_literature_dropabs",
     "data/processed/with_literature_final"),
    ("merged", "artifacts/with_atlas", "data/processed/with_atlas"),
    ("merged, absences dropped", "artifacts/with_atlas_dropabs",
     "data/processed/with_atlas"),
]


def _shares(corpus: pathlib.Path, axes: list[str]) -> dict[str, dict]:
    """How much of the grid each mechanism carries, in agents and in cells."""
    data = ds.load(corpus, axes, kind="other")
    agents_of: dict[str, set[int]] = collections.defaultdict(set)
    for agent, mech in zip(data.arm_agent_idx, data.arm_mech_idx):
        agents_of[data.mechanisms[int(mech)]].add(int(agent))
    cell_mech = np.asarray(data.arm_mech_idx)[data.arm_idx]
    out = {}
    for mi, name in enumerate(data.mechanisms):
        out[name] = {
            "agents": len(agents_of[name]),
            "agent_share": round(len(agents_of[name]) / max(len(data.agents), 1), 4),
            "cell_share": round(float((cell_mech == mi).mean()), 4),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "fold_comparability.json")
    args = ap.parse_args()

    axes = list(Taxonomy().axis_order)
    rows = []
    share_cache: dict[str, dict] = {}
    for label, art, corpus_rel in CORPORA:
        metrics = ROOT / art / "forward_other_metrics.json"
        corpus = ROOT / corpus_rel
        if not metrics.exists() or not (corpus / "arms.parquet").exists():
            continue
        if corpus_rel not in share_cache:
            share_cache[corpus_rel] = _shares(corpus, axes)
        shares = share_cache[corpus_rel]
        cv = (json.loads(metrics.read_text(encoding="utf-8")).get("cv") or {})
        lomo = cv.get("leave_one_mechanism_out") or {}
        for fold in lomo.get("folds") or []:
            name = fold.get("fold")
            sh = shares.get(name, {})
            rows.append({
                "corpus": label,
                "fold": name,
                "delta_auc": round(float(fold["delta_auc"]), 4),
                "agents_held_out": sh.get("agents"),
                "agent_share_held_out": sh.get("agent_share"),
                "cell_share_held_out": sh.get("cell_share"),
            })

    usable = [r for r in rows if r["agent_share_held_out"] is not None]
    rho = None
    if len(usable) >= 6:
        d = np.array([r["delta_auc"] for r in usable])
        s = np.array([r["agent_share_held_out"] for r in usable])
        rd, rs = np.argsort(np.argsort(d)), np.argsort(np.argsort(s))
        rho = round(float(np.corrcoef(rd.astype(float), rs.astype(float))[0, 1]), 4)

    # The like-for-like macro: the same three folds every corpus has, so a corpus is not
    # penalised for having gained a fourth and harder fold.
    common = sorted(
        set.intersection(*[
            {r["fold"] for r in rows if r["corpus"] == c}
            for c in {r["corpus"] for r in rows}
        ]) if rows else set()
    )
    like_for_like = {}
    for corpus in sorted({r["corpus"] for r in rows}):
        sel = [r["delta_auc"] for r in rows
               if r["corpus"] == corpus and r["fold"] in common]
        if sel:
            like_for_like[corpus] = {
                "folds": common,
                "macro_delta": round(float(np.mean(sel)), 4),
            }

    doc = {
        "rows": rows,
        "common_folds": common,
        "like_for_like_macro": like_for_like,
        "summary": {
            "spearman_delta_vs_agent_share_held_out": rho,
            "reading": (
                "A fold that removes more of the corpus is a harder test, and the "
                "expansions are tubulin-heavy, so the tubulin fold removes a larger share "
                "each time. The correlation above is how much of the cross-corpus "
                "degradation that accounts for."
                if rho is not None else
                "Not enough fitted folds yet to relate the delta to the share held out."
            ),
        },
    }
    write_json(args.out, doc)

    print(f"{'corpus':28} {'fold':16} {'delta':>8} {'agents out':>11} "
          f"{'agent share':>12} {'cell share':>11}")
    for r in rows:
        ash = r["agent_share_held_out"]
        csh = r["cell_share_held_out"]
        print(f"{r['corpus']:28} {r['fold']:16} {r['delta_auc']:>8.4f} "
              f"{str(r['agents_held_out']):>11} "
              f"{(f'{ash:.3f}' if ash is not None else '-'):>12} "
              f"{(f'{csh:.3f}' if csh is not None else '-'):>11}")
    print()
    if common:
        print(f"like-for-like macro over {common}:")
        for c, v in like_for_like.items():
            print(f"  {c:28} {v['macro_delta']:+.4f}")
    if rho is not None:
        print()
        print(f"delta vs share held out: Spearman {rho:+.4f}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
