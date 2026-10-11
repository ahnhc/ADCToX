"""How good a substitute is `min(reported %)` for a reporting cut nobody stated?

Seven AE tables in ten state no frequency cut, and the model is told the cut is *at most*
the smallest printed rate. That substitution is the single most consequential modelling
choice in the literature path -- it decides what every absent organ in every paper arm
means -- and its accuracy had never been measured, for a reason worth stating: the only
subset where the truth is known is the subset where a stated cut exists, and there the
stated cut overrides the substitute. The comparison was being discarded at the moment it
became possible.

So `Threshold` now records `derived_value` on every path, including the ones where a stated
cut wins, and this scores the substitute against the truth on those tables.

What the answer changes. The bound is used in the conservative direction: if the true cut
was 1% and the bound says 11%, an absent event is told "your rate is somewhere below 11%"
when it was really below 1%, so the interval is too wide and power is lost rather than
correctness. But the size matters for a second reason. Negative result 50 narrows the
literature expansion's damage to the arms whose cut is an upper bound or to six agents, and
the mechanism it suspects is exactly this: a bound set far too high. If the bound is
typically a hair above the stated cut, that suspicion is weakened; if it is typically many
points above, it is the leading explanation.

One asymmetry to keep in view. These tables are not a random sample of the others: a table
that states its cut may print more rows, or fewer, than one that does not. The measurement
is on the subset where it can be made, and the artefact records the subset's size.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

import numpy as np
import yaml
from lxml import etree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from adctox.extract.jats_tables import parse_article  # noqa: E402
from adctox.extract.table_to_cells import extract  # noqa: E402
from adctox.provenance import write_json  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402
from extract_pmc_cells import aliases_for  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"
PT_DICT = ROOT / "data" / "processed" / "pt_soc_dictionary.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dirs", type=pathlib.Path, nargs="+",
                    default=sorted((ROOT / "data" / "raw_big" / "pmc").glob("2026-*")))
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "threshold_estimator_accuracy.json")
    args = ap.parse_args()

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]
    alias_map = {k: aliases_for(v) for k, v in registry.items() if v.get("inn")}
    tax = default_taxonomy()
    tax.load_pt_dictionary(PT_DICT)

    pairs: list[dict] = []
    sources = collections.Counter()
    n_tables = n_ae = 0
    for raw in args.raw_dirs:
        manifest = raw / "_manifest.json"
        xml = raw / "xml"
        if not manifest.exists() or not xml.is_dir():
            continue
        records = json.loads(manifest.read_text(encoding="utf-8"))["records"]
        for path in sorted(xml.glob("*.xml")):
            rec = records.get(path.stem.removeprefix("PMC"), {})
            agent = rec.get("agent_hint")
            if agent not in alias_map:
                continue
            try:
                meta, tables = parse_article(path)
            except Exception:
                continue
            others = {k: v for k, v in alias_map.items() if k != agent}
            gate = rec.get("attribution_gate", "title")
            for table in tables:
                n_tables += 1
                if not table.looks_like_ae_table:
                    continue
                n_ae += 1
                try:
                    out = extract(table, agent, alias_map[agent], others, tax,
                                  sibling_tables=tables,
                                  title_names_agent=(gate == "title"))
                except Exception:
                    continue
                thr = out.threshold
                if thr is None:
                    continue
                sources[thr.source] += 1
                # The scorable subset: the caption stated a cut AND the printed rates gave
                # a bound, so both numbers exist for the same table.
                if not (thr.is_explicit and thr.value is not None
                        and thr.derived_value is not None):
                    continue
                # How many rows the table printed, because the overshoot's mechanism is
                # mechanical: a short table's smallest printed rate is far above its cut,
                # since few events cleared it. If the gap tracks the row count the bound
                # is correctable rather than merely noisy.
                n_rows = len({c.row for c in table.cells})
                pairs.append({
                    "n_rows": int(n_rows),
                    "pmcid": path.stem.removeprefix("PMC"),
                    "agent": agent,
                    "journal": meta.get("journal"),
                    "table": table.label or table.caption[:60],
                    "stated": float(thr.value),
                    "derived": float(thr.derived_value),
                    "gap": round(float(thr.derived_value - thr.value), 4),
                    "accepted": bool(out.accepted),
                })

    if not pairs:
        print("no table states a cut and prints a usable rate; nothing to score")
        write_json(args.out, {"n_scorable": 0, "ae_tables": n_ae}, {})
        return 1

    gap = np.array([p["gap"] for p in pairs])
    rows_n = np.array([p["n_rows"] for p in pairs], dtype=float)
    stated = np.array([p["stated"] for p in pairs])
    derived = np.array([p["derived"] for p in pairs])
    # The bound must not fall below the stated cut: `resolve` demotes a table to a bound
    # when it does, so a negative gap here would mean the two numbers came from different
    # tables.
    negative = [p for p in pairs if p["gap"] < -1e-9]
    out = {
        "ae_tables": n_ae,
        "tables_with_a_threshold": int(sum(sources.values())),
        "threshold_sources": dict(sources),
        "n_scorable": len(pairs),
        "scorable_share_of_ae_tables": round(len(pairs) / max(n_ae, 1), 4),
        "gap": {
            "median": round(float(np.median(gap)), 4),
            "mean": round(float(gap.mean()), 4),
            "p90": round(float(np.percentile(gap, 90)), 4),
            "max": round(float(gap.max()), 4),
            "share_within_1pp": round(float((gap <= 1.0).mean()), 4),
            "share_within_2pp": round(float((gap <= 2.0).mean()), 4),
            "share_over_5pp": round(float((gap > 5.0).mean()), 4),
            "share_exact": round(float((np.abs(gap) < 1e-9).mean()), 4),
        },
        "stated_cut": {
            "median": round(float(np.median(stated)), 4),
            "values": dict(collections.Counter(stated.tolist())),
        },
        "derived_bound": {"median": round(float(np.median(derived)), 4)},
        # Does the overshoot track how short the table is? A rank correlation over this
        # many tables carries a sign and not a p-value, and the sign is the claim: a
        # predictable overshoot is a correctable one.
        "gap_vs_rows": (
            {
                "spearman": round(float(__import__("scipy.stats", fromlist=["spearmanr"])
                                        .spearmanr(rows_n, gap).statistic), 4),
                "n": len(pairs),
                "p_withheld_because": f"{len(pairs)} tables; the sign is the claim",
            }
            if len(pairs) >= 6 else {"computed": False}
        ),
        "gap_vs_stated_cut": {
            "spearman": round(float(__import__("scipy.stats", fromlist=["spearmanr"])
                                    .spearmanr(np.array([p["stated"] for p in pairs]),
                                               gap).statistic), 4),
        },
        "negative_gaps": len(negative),
        "pairs": pairs,
        "reading": (
            "The bound is used on the seven tables in ten that state nothing. Here both "
            "numbers exist, so the bound can be scored against the truth. A bound close to "
            "the stated cut means the substitution costs little; a bound many points above "
            "it means every absent organ in those arms is bounded far too loosely, which "
            "is the mechanism negative result 50 suspects."
        ),
    }
    write_json(args.out, out, {})
    g = out["gap"]
    print(f"{n_ae} AE tables, {out['tables_with_a_threshold']} with a threshold, "
          f"{len(pairs)} scorable ({out['scorable_share_of_ae_tables'] * 100:.1f}% of AE tables)")
    print(f"  stated cut median {out['stated_cut']['median']:g}%, "
          f"derived bound median {out['derived_bound']['median']:g}%")
    print(f"  gap (derived - stated): median {g['median']:+.3f}pp, mean {g['mean']:+.3f}, "
          f"p90 {g['p90']:+.3f}, max {g['max']:+.3f}")
    print(f"  within 1pp {g['share_within_1pp'] * 100:.0f}%, within 2pp "
          f"{g['share_within_2pp'] * 100:.0f}%, over 5pp {g['share_over_5pp'] * 100:.0f}%, "
          f"exact {g['share_exact'] * 100:.0f}%")
    gvr = out.get("gap_vs_rows") or {}
    if gvr.get("spearman") is not None:
        print(f"  gap vs printed rows: rho {gvr['spearman']:+.3f} over {gvr['n']} tables; "
              f"gap vs the stated cut itself: rho "
              f"{out['gap_vs_stated_cut']['spearman']:+.3f}")
    if negative:
        print(f"  WARNING {len(negative)} negative gaps; the bound cannot sit below the "
              "stated cut, so the two numbers are not from one table")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
