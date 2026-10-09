"""Is the precedent count that drives O3 and the Tier-1 gate right?

`conf/design_space.yaml` carries, for every payload, linker and conjugation chemistry, a
`clinical_adcs` count. Two things in the product rest on it:

  * **O3**, `log(1 + clinical ADCs sharing the configuration)`, the objective that stops the
    search returning designs nobody has ever built.
  * **C4**, the Tier-1 gate, which rejects a design outright if any of its parts has never
    reached the clinic. A count of zero is a refusal.

The counts are stamped `precedent_counts_source: hand_curated_landscape_review`. They have
never been checked against a corpus, because until now no corpus named enough agents to
check them with. The merged corpus names 66, and the hand-transcribed database names 99, so
the check is now possible.

It is a check and not a replacement. The two sources cover different slices -- the registry
is weighted to approved and late-phase agents, the transcribed database to early-phase and
discontinued ones -- so neither count alone is "the" number. What the audit reports is the
count of agents this project can *name*, which is a floor on the truth and the only figure
it can defend, beside the curated number it is meant to test.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=pathlib.Path,
                    default=ROOT / "data" / "raw" / "atlas" / "2026-10-10" / "adc_db.xlsx")
    ap.add_argument("--slots", type=pathlib.Path,
                    default=ROOT / "conf" / "ontology" / "atlas_design_slots.yaml")
    ap.add_argument("--space", type=pathlib.Path,
                    default=ROOT / "conf" / "design_space.yaml")
    ap.add_argument("--merged", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_atlas")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "precedent_audit.json")
    args = ap.parse_args()

    space = yaml.safe_load(args.space.read_text(encoding="utf-8"))
    slots = yaml.safe_load(args.slots.read_text(encoding="utf-8"))

    # Agents this project can name, by payload. The merged frame already carries normalised
    # identities, so this is a count of agents and not of spellings.
    named: dict[str, set[str]] = collections.defaultdict(set)
    if (args.merged / "arms.parquet").exists():
        arms = pd.read_parquet(args.merged / "arms.parquet")
        for agent, payload in arms[["agent", "payload"]].dropna().drop_duplicates().values:
            p = str(payload).strip()
            if p and p.lower() not in ("nan", "none"):
                named[p].add(str(agent))

    # And from the workbook's full 99 agents, which includes agents with no usable toxicity
    # table: precedent is about reaching the clinic, not about publishing a table.
    atlas_named: dict[str, set[str]] = collections.defaultdict(set)
    if args.workbook.exists():
        master = pd.read_excel(args.workbook, sheet_name="ADC_MASTER")
        master["agent"] = master["ADC ID"].astype(str).str.lower().str.replace("-", "_")
        for _, row in master.iterrows():
            for alt in str(row.get("Payload") or "").split("|"):
                pid = slots["payload_identity"].get(alt.strip())
                if pid:
                    atlas_named[pid].add(row["agent"])
                    break

    rows = []
    for payload, entry in space["payloads"].items():
        curated = int(entry.get("clinical_adcs", 0))
        union = named.get(payload, set()) | atlas_named.get(payload, set())
        rows.append({
            "slot": "payload",
            "part": payload,
            "curated": curated,
            "named_in_corpus": len(named.get(payload, set())),
            "named_in_workbook": len(atlas_named.get(payload, set())),
            "named_union": len(union),
            # A curated count below what can be named is an undercount of a quantity the
            # product uses as a floor, which is the direction that matters: C4 refuses a
            # design when the count is zero, and O3 ranks on it.
            "curated_below_named": curated < len(union),
            "agents": sorted(union),
        })

    # Parts the corpus names that the frozen design space does not hold at all. Each one is a
    # design the enumerator cannot propose, however much precedent it has.
    absent = sorted(
        (set(named) | set(atlas_named)) - set(space["payloads"])
    )
    absent_detail = [
        {"part": p,
         "named_union": len((named.get(p, set()) | atlas_named.get(p, set()))),
         "agents": sorted(named.get(p, set()) | atlas_named.get(p, set()))}
        for p in absent
    ]

    disagreeing = [r for r in rows if r["curated"] != r["named_union"]]
    under = [r for r in rows if r["curated_below_named"]]
    worst = max(rows, key=lambda r: abs(r["curated"] - r["named_union"])) if rows else None

    doc = {
        "counts_source": space.get("precedent_counts_source"),
        "design_space_frozen_at": str(space.get("frozen_at")),
        "payloads": rows,
        "payloads_absent_from_design_space": absent_detail,
        "summary": {
            "n_payload_slots": len(rows),
            "n_disagreeing": len(disagreeing),
            "n_curated_below_named": len(under),
            "largest_disagreement": (
                {"part": worst["part"], "curated": worst["curated"],
                 "named_union": worst["named_union"]} if worst else None
            ),
            "n_payloads_absent_from_design_space": len(absent_detail),
            # What it would take to add one: the enumerator needs a free-payload IC50 for
            # constraint C1 and an attachment group for the linker-compatibility matrix,
            # and neither is in either source.
            "blocked_on": "free-payload IC50 (C1) and attachment chemistry (C5)",
        },
    }
    write_json(args.out, doc)

    print(f"precedent counts source: {doc['counts_source']}, frozen "
          f"{doc['design_space_frozen_at']}")
    print()
    print(f"{'payload':16} {'curated':>8} {'corpus':>7} {'workbook':>9} {'union':>6}  verdict")
    for r in sorted(rows, key=lambda r: -abs(r["curated"] - r["named_union"])):
        # The two directions are not symmetric. Below what can be named is an error, and
        # an error in the direction that matters: C4 refuses a design when the count is
        # zero and O3 ranks on it. Above it is merely unverified -- the curation may have
        # known of agents with no usable toxicity table, which this corpus cannot name.
        verdict = ("UNDERCOUNT -- below what can be named" if r["curated_below_named"]
                   else "agrees" if r["curated"] == r["named_union"]
                   else "unverified -- above what can be named")
        print(f"{r['part']:16} {r['curated']:>8} {r['named_in_corpus']:>7} "
              f"{r['named_in_workbook']:>9} {r['named_union']:>6}  {verdict}")
    print()
    print(f"{len(disagreeing)} of {len(rows)} curated counts differ from what can be named. "
          f"{len(under)} are BELOW it, which is an error; the rest are above it, which is "
          "unverified rather than wrong.")
    if absent_detail:
        print(f"\n{len(absent_detail)} payloads the corpus names and the frozen design space "
              "does not hold, so the enumerator cannot propose them:")
        for a in sorted(absent_detail, key=lambda a: -a["named_union"]):
            print(f"  {a['part']:16} {a['named_union']:3} agents")
        print(f"  blocked on: {doc['summary']['blocked_on']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
