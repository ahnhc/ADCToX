"""What kind of event is each organ axis made of?

An axis is "any event in this organ", pooled over MedDRA preferred terms, and the terms are
not all the same kind of thing. MedDRA files laboratory abnormalities under
`Investigations` rather than under the organ, so the taxonomy redistributes them -- "alanine
aminotransferase increased" to hepatic, "neutrophil count decreased" to haematologic -- and
without that the hepatic axis would be almost empty while a quarter of the corpus sat in a
bucket with no organ.

The redistribution is right and it has a consequence worth stating: the hepatic axis is
**predominantly a laboratory abnormality rate**, 56% of registry rows and 84% of literature
rows, against 0-8% for most axes. Renal is 15% and 31%. So "hepatic risk 0.18" is mostly
"transaminase elevation", not hepatotoxicity as a clinical event, and a patient who declares
cirrhosis is up-weighting a laboratory finding.

That changes what the number means rather than whether it is right, which is why it belongs
on the screen and not only in a limitations list.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _walk(node, out: list) -> None:
    if isinstance(node, dict):
        if "term" in node and "organSystem" in node:
            # `stats` carries the per-group counts; the patient mass is what decides
            # whether an exclusion is large, and a row count alone would weight a term
            # reported in one small arm the same as one reported in forty.
            affected = 0
            for stat in node.get("stats") or []:
                try:
                    affected += int(stat.get("numAffected") or 0)
                except (TypeError, ValueError):
                    pass
            out.append((node.get("term"), node.get("organSystem"), affected))
        for v in node.values():
            _walk(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", type=pathlib.Path,
                    default=pathlib.Path("/data/hyeongchanahn/adctox/raw/ctgov"))
    ap.add_argument("--cells", type=pathlib.Path,
                    default=pathlib.Path(
                        "/data/hyeongchanahn/adctox/processed/all_cells.jsonl"))
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "axis_composition.json")
    args = ap.parse_args()

    tax = default_taxonomy()
    axes = list(tax.axis_order)

    registry_total: collections.Counter = collections.Counter()
    registry_lab: collections.Counter = collections.Counter()
    registry_mass: collections.Counter = collections.Counter()
    excluded_rows: collections.Counter = collections.Counter()
    excluded_mass: collections.Counter = collections.Counter()
    excluded_terms: collections.Counter = collections.Counter()
    studies = sorted(args.studies.glob("*/studies"))
    if studies:
        for path in sorted(studies[-1].glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            pairs: list = []
            _walk(doc, pairs)
            for term, soc, affected in pairs:
                axis, prov = tax.resolve(term, soc)
                if axis == "__excluded__":
                    # Casefolded, because the registry carries 22 ALL-CAPS duplicates of
                    # its own system-organ class strings and the taxonomy already folds
                    # them. Counting them apart would split one exclusion into two rows
                    # and understate the larger of them.
                    key = str(soc).casefold()
                    excluded_rows[key] += 1
                    excluded_mass[key] += affected
                    excluded_terms[(key, str(term).casefold())] += 1
                    continue
                if not axis or axis.startswith("__"):
                    continue
                registry_total[axis] += 1
                registry_mass[axis] += affected
                if "investigation" in str(prov).lower():
                    registry_lab[axis] += 1

    lit_total: collections.Counter = collections.Counter()
    lit_lab: collections.Counter = collections.Counter()
    if args.cells.exists():
        for line in args.cells.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            cell = json.loads(line)
            lit_total[cell["axis"]] += 1
            if "investigation" in str(cell.get("row_provenance", "")).lower():
                lit_lab[cell["axis"]] += 1

    rows = []
    for axis in axes:
        rt, rl = registry_total.get(axis, 0), registry_lab.get(axis, 0)
        lt, ll = lit_total.get(axis, 0), lit_lab.get(axis, 0)
        rows.append({
            "axis": axis,
            "registry_rows": rt, "registry_lab_rows": rl,
            "registry_lab_share": round(rl / rt, 3) if rt else None,
            "literature_cells": lt, "literature_lab_cells": ll,
            "literature_lab_share": round(ll / lt, 3) if lt else None,
        })

    # An axis is lab-dominated if either source puts most of its rows there.
    dominated = [
        r["axis"] for r in rows
        if max(r["registry_lab_share"] or 0, r["literature_lab_share"] or 0) >= 0.5
    ]
    # The exclusions drop a tenth of all registry rows, which is the largest discretionary
    # decision in the corpus, and `conf/ontology/axes.yaml` records it as nine one-word
    # reasons. Measuring what is in each bucket is what makes those reasons checkable.
    reasons = tax.excluded_reasons() if hasattr(tax, "excluded_reasons") else {}
    excluded = []
    for soc, n in excluded_rows.most_common():
        top = [
            {"term": t, "rows": c}
            for (s_, t), c in excluded_terms.most_common()
            if s_ == soc
        ][:6]
        excluded.append({
            "soc": soc, "rows": n,
            "patients_affected": int(excluded_mass[soc]),
            "reason": reasons.get(soc),
            "top_terms": top,
        })
    resolved = int(sum(registry_total.values()))
    summary = {
        "lab_dominated_axes": dominated,
        "registry_rows_resolved": resolved,
        "registry_rows_excluded": int(sum(excluded_rows.values())),
        "excluded_share_of_rows": round(
            sum(excluded_rows.values()) / (resolved + sum(excluded_rows.values())), 3
        ) if resolved else None,
        "excluded_patients_affected": int(sum(excluded_mass.values())),
        "resolved_patients_affected": int(sum(registry_mass.values())),
        "excluded_share_of_patients": round(
            sum(excluded_mass.values())
            / (sum(registry_mass.values()) + sum(excluded_mass.values())), 3
        ) if registry_mass else None,
        "literature_cells": int(sum(lit_total.values())),
    }

    print(f"  {'axis':20s} {'reg rows':>9s} {'reg lab':>8s} {'lit cells':>10s} "
          f"{'lit lab':>8s}")
    for r in rows:
        print(f"  {r['axis']:20s} {r['registry_rows']:9d} "
              f"{(r['registry_lab_share'] or 0):8.0%} {r['literature_cells']:10d} "
              f"{(r['literature_lab_share'] or 0):8.0%}")
    print()
    for k, v in summary.items():
        print(f"  {k:28s} {v}")
    print(f"\n  {'excluded SOC':46s} {'rows':>6s} {'patients':>9s}  reason")
    for e in excluded:
        print(f"  {e['soc'][:46]:46s} {e['rows']:6d} {e['patients_affected']:9d}  "
              f"{e['reason']}")
    write_json(args.out, {"summary": summary, "axes": rows, "excluded": excluded})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
