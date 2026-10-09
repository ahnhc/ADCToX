"""Derive each comorbidity's organ axes from MONDO, independently of the hand map.

The registry's `organ_axes` column is hand-assigned, and it was assigned by reading trial
exclusion criteria. That makes exclusion recovery a circular test of it: the thing being
predicted is the thing the mapping came from. The only non-circular holdout left is about
28 cells of FDA label impairment text.

A MONDO `is_a` closure is independent by construction. It touches no exclusion text, and
MONDO was curated for disease classification rather than for this project, so recovering
exclusion criteria from a MONDO-derived mapping is a legitimate holdout over 1,741 trials
-- two orders of magnitude more power than the label cells. That is the reason to build it.
It is not an attempt to be *better* than the hand map, and this script reports agreement
rather than claiming an improvement.

Three things worth knowing before reading the output.

Multiple parents are a feature. Cirrhosis is hepatobiliary and digestive, and a comorbidity
that compromises two organs should score on two axes.

One registry condition resolves to an HPO term rather than a MONDO one -- thrombocytopenia
is HP:0001873 -- which the plan flagged after finding 2 of 49 test conditions did this.
HPO terms are not in `mondo.obo`, so that condition derives nothing and is reported as
such rather than silently dropped.

`constitutional` is unreachable from any disease ontology because it is a MedDRA reporting
class (fatigue, pyrexia, weight loss) and not an organ. Stated, not silently empty.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import stamp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "comorbidity_registry.csv"
CROSSWALK = ROOT / "conf" / "ontology" / "mondo_organ_axis.yaml"


def parse_obo(path: pathlib.Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    """`id -> name` and `id -> direct is_a parents`, for non-obsolete terms."""
    names: dict[str, str] = {}
    parents: dict[str, set[str]] = {}
    cur: str | None = None
    obsolete = False
    in_term = False
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line == "[Term]":
                in_term, cur, obsolete = True, None, False
                continue
            if line.startswith("["):
                in_term = False
                continue
            if not in_term or not line:
                continue
            if line.startswith("id: "):
                cur = line[4:].strip()
            elif line.startswith("name: ") and cur:
                names[cur] = line[6:].strip()
            elif line.startswith("is_obsolete: true"):
                obsolete = True
                if cur:
                    names.pop(cur, None)
                    parents.pop(cur, None)
            elif line.startswith("is_a: ") and cur and not obsolete:
                # The line carries an optional trailing qualifier block and an optional
                # comment:
                #   is_a: MONDO:0005154 {source="DOID:5082", ...} ! liver disorder
                # Splitting on "!" alone leaves the `{...}` attached to the identifier, so
                # every parent id came out unmatchable and 34 of 38 conditions derived no
                # organ while the term counts looked healthy. Take the first token.
                rest = line[6:].strip()
                parent = rest.split()[0] if rest else ""
                if parent.startswith(("MONDO:", "HP:", "UPHENO:")):
                    parents.setdefault(cur, set()).add(parent)
    return names, parents


def ancestors(term: str, parents: dict[str, set[str]]) -> set[str]:
    """Transitive `is_a` closure, excluding the term itself."""
    seen: set[str] = set()
    stack = list(parents.get(term, ()))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(parents.get(node, ()))
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obo", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "mondo_organ_axes.json")
    args = ap.parse_args()

    cross = yaml.safe_load(CROSSWALK.read_text(encoding="utf-8"))
    ancestor_to_axis = {k.lower(): v for k, v in cross["ancestor_to_axis"].items()}
    conditions = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))

    names, parents = parse_obo(args.obo)
    print(f"mondo.obo: {len(names):,} terms, {len(parents):,} with a parent")

    derived: dict[str, dict] = {}
    unresolvable: list[dict] = []
    for row in conditions:
        cid, mondo = row["id"], row["mondo_id"].strip()
        hand = {a.strip() for a in row["organ_axes"].split(";") if a.strip()}
        if not mondo or mondo not in names:
            unresolvable.append({
                "id": cid, "mondo_id": mondo, "hand_axes": sorted(hand),
                "reason": ("not a MONDO term" if mondo and not mondo.startswith("MONDO")
                           else "id absent from this mondo.obo snapshot"),
            })
            continue
        anc = ancestors(mondo, parents)
        hits: dict[str, list[str]] = collections.defaultdict(list)
        for a in anc:
            axis = ancestor_to_axis.get(names.get(a, "").lower())
            if axis:
                hits[axis].append(names[a])
        derived[cid] = {
            "mondo_id": mondo,
            "mondo_name": names[mondo],
            "n_ancestors": len(anc),
            "derived_axes": sorted(hits),
            "via": {axis: sorted(terms) for axis, terms in sorted(hits.items())},
            "hand_axes": sorted(hand),
            "agree": sorted(hand & set(hits)),
            "hand_only": sorted(hand - set(hits)),
            "mondo_only": sorted(set(hits) - hand),
        }

    exact = sum(1 for d in derived.values() if not d["hand_only"] and not d["mondo_only"])
    overlap = sum(1 for d in derived.values() if d["agree"])
    empty = [c for c, d in derived.items() if not d["derived_axes"]]
    print(f"\n조건 {len(conditions)}개 중 MONDO로 해결 {len(derived)}, "
          f"해결 불가 {len(unresolvable)}")
    print(f"  수작업 매핑과 완전 일치   {exact}/{len(derived)}")
    print(f"  최소 한 축 공유          {overlap}/{len(derived)}")
    print(f"  MONDO가 축을 못 준 조건  {len(empty)}  {', '.join(empty[:6])}")

    print(f"\n  {'condition':26s} {'hand':34s} {'mondo'}")
    for cid, d in sorted(derived.items()):
        mark = " " if not d["hand_only"] and not d["mondo_only"] else "~"
        print(f"{mark} {cid:26s} {';'.join(d['hand_axes'])[:34]:34s} "
              f"{';'.join(d['derived_axes'])[:52]}")
    if unresolvable:
        print("\n해결 불가:")
        for u in unresolvable:
            print(f"  {u['id']:26s} {u['mondo_id']:16s} {u['reason']}")

    # Which direction the disagreements run. A MONDO-only axis is the layer adding an organ
    # the hand map omitted; a hand-only axis is the hand map asserting one the ontology
    # does not support, and those are the cells where circularity could be hiding.
    hand_only = collections.Counter(
        a for d in derived.values() for a in d["hand_only"]
    )
    mondo_only = collections.Counter(
        a for d in derived.values() for a in d["mondo_only"]
    )
    print(f"\n수작업에만 있는 축 (총 {sum(hand_only.values())}): "
          f"{dict(hand_only.most_common(8))}")
    print(f"MONDO에만 있는 축 (총 {sum(mondo_only.values())}): "
          f"{dict(mondo_only.most_common(8))}")

    out = {
        "provenance": stamp({"registry": REGISTRY, "crosswalk": CROSSWALK}),
        "obo_terms": len(names),
        "n_conditions": len(conditions),
        "n_resolved": len(derived),
        "n_unresolvable": len(unresolvable),
        "n_exact_agreement": exact,
        "n_sharing_an_axis": overlap,
        "exact_agreement_rate": exact / len(derived) if derived else None,
        "sharing_rate": overlap / len(derived) if derived else None,
        "conditions_with_no_derived_axis": empty,
        "hand_only_axis_counts": dict(hand_only),
        "mondo_only_axis_counts": dict(mondo_only),
        "derived": derived,
        "unresolvable": unresolvable,
        "axes_not_derivable": cross.get("axes_not_derivable", {}),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
