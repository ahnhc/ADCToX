"""Audit the registry's pinned MONDO identifiers against what they actually name.

The plan's instruction was to pin all 40 identifiers by hand into a checked-in CSV and
never resolve at runtime, because a search API silently mis-resolved 3 of 36 test
conditions -- `ocular surface disease` to `brain small vessel disease 1`, and so on. The
pinning was done. It did not help, because the pins themselves are wrong: building the
MONDO organ derivation, which is the first consumer of that column, immediately showed
identifiers for chronic kidney disease pointing at cardiomyopathy and interstitial lung
disease pointing at cervix squamous papilloma.

Nothing had been harmed, only because nothing read the column until now. That is the
argument for building an independent layer even when it is not expected to beat the hand
map: it audits the thing it is independent of.

This script proposes a correction for every pin by matching the registry's own label and
notes against MONDO names and exact synonyms, and prints the matched name beside each
proposal so a human decides. It writes a candidate CSV and never edits the registry --
runtime resolution is what the plan forbids, and silently rewriting a curated file would be
worse.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.provenance import stamp  # noqa: E402
import yaml  # noqa: E402

from derive_organ_axes import ancestors, parse_obo  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "comorbidity_registry.csv"
CROSSWALK = ROOT / "conf" / "ontology" / "mondo_organ_axis.yaml"
# The ontology root. Pinning it is a deliberate "no disease term applies", which five
# conditions need: a prior anthracycline exposure, prior chest radiation, prior corneal
# surgery, a prior transplant and a prior bowel resection are not diseases, and no disease
# ontology can place them. Counting those as wrong pins would bury the real errors.
ROOT_TERM = "MONDO:0000001"

SYNONYM = re.compile(r'^synonym: "([^"]+)" (EXACT|NARROW|BROAD|RELATED)')


def parse_synonyms(path: pathlib.Path) -> dict[str, set[str]]:
    """`id -> exact synonyms`. Only EXACT, because a BROAD synonym of a different disease
    matches far too readily -- the failure mode this script exists to catch."""
    out: dict[str, set[str]] = {}
    cur: str | None = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("id: "):
                cur = line[4:].strip()
            elif cur:
                m = SYNONYM.match(line.strip())
                if m and m.group(2) == "EXACT":
                    out.setdefault(cur, set()).add(m.group(1).lower())
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obo", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "mondo_id_audit.json")
    ap.add_argument("--candidates", type=pathlib.Path,
                    default=ROOT / "artifacts" / "mondo_id_candidates.csv")
    args = ap.parse_args()

    names, parents_map = parse_obo(args.obo)
    ancestor_to_axis = {
        k.lower(): v
        for k, v in yaml.safe_load(
            CROSSWALK.read_text(encoding="utf-8")
        )["ancestor_to_axis"].items()
    }
    synonyms = parse_synonyms(args.obo)
    by_name: dict[str, list[str]] = {}
    for mid, name in names.items():
        by_name.setdefault(_norm(name), []).append(mid)
    for mid, syns in synonyms.items():
        for syn in syns:
            by_name.setdefault(_norm(syn), []).append(mid)

    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    findings: list[dict] = []
    for row in rows:
        cid, pinned, label = row["id"], row["mondo_id"].strip(), row["label"].strip()
        pinned_name = names.get(pinned)
        # Candidates: the registry label, and the label with common qualifiers stripped.
        queries = [label]
        stripped = re.sub(
            r"\b(chronic|severe|active|prior|history\s+of|controlled|reduced|stage\s*\S+)\b",
            " ", label, flags=re.I)
        if _norm(stripped) != _norm(label):
            queries.append(stripped)
        proposals: list[tuple[str, str, str]] = []
        for q in queries:
            for mid in by_name.get(_norm(q), [])[:3]:
                proposals.append((q, mid, names.get(mid, "?")))
        matches_pin = pinned_name is not None and _norm(pinned_name) in {
            _norm(q) for q in queries
        } or any(
            _norm(s) in {_norm(q) for q in queries} for s in synonyms.get(pinned, ())
        )
        # The decisive test for a *wrong* pin, as opposed to a broader or placeholder
        # one: do the organs the pinned term implies overlap the organs the hand map
        # assigns? A pin naming a parent of the right disease still lands on the right
        # organ. A pin naming an unrelated disease does not, and that is the failure the
        # plan predicted and hand-pinning was supposed to prevent.
        hand = {a.strip() for a in row["organ_axes"].split(";") if a.strip()}
        pin_axes: set[str] = set()
        if pinned_name:
            for a in ancestors(pinned, parents_map) | {pinned}:
                axis = ancestor_to_axis.get(names.get(a, "").lower())
                if axis:
                    pin_axes.add(axis)
        verdict = (
            "pin_absent" if pinned and pinned_name is None and pinned.startswith("MONDO")
            else "not_mondo" if pinned and not pinned.startswith("MONDO")
            else "root_placeholder" if pinned == ROOT_TERM
            else "pin_matches_label" if matches_pin
            else "pin_broader_same_organ" if pinned_name and (pin_axes & hand)
            else "pin_names_unrelated_disease" if pinned_name
            else "no_pin"
        )
        findings.append({
            "id": cid, "label": label, "pinned": pinned,
            "pinned_names": pinned_name, "verdict": verdict,
            "hand_axes": sorted(hand), "pin_implied_axes": sorted(pin_axes),
            "proposals": [
                {"query": q, "mondo_id": m, "mondo_name": n} for q, m, n in proposals
            ],
        })

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["verdict"]] = counts.get(f["verdict"], 0) + 1
    print(f"조건 {len(rows)}개의 핀 검사")
    for v, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {v:28s} {n:3d}")

    wrong = [f for f in findings if f["verdict"] == "pin_names_unrelated_disease"]
    print(f"\n핀이 무관한 질병을 가리키는 {len(wrong)}건 "
          "(핀이 함의하는 장기가 수작업 장기와 겹치지 않음)")
    for f in wrong:
        prop = f["proposals"][0] if f["proposals"] else None
        suggest = f"{prop['mondo_id']} \"{prop['mondo_name']}\"" if prop else "제안 없음"
        print(f"  {f['id']:26s} {f['pinned']:16s} \"{f['pinned_names']}\"  "
              f"핀장기={f['pin_implied_axes']} 수작업={f['hand_axes']}")
        print(f"  {'':26s} {'→ 제안':16s} {suggest}")

    absent = [f for f in findings if f["verdict"] == "pin_absent"]
    if absent:
        print(f"\n이 스냅샷에 없는 핀 {len(absent)}건")
        for f in absent:
            prop = f["proposals"][0] if f["proposals"] else None
            print(f"  {f['id']:26s} {f['pinned']:16s} "
                  f"→ {prop['mondo_id'] + ' ' + prop['mondo_name'] if prop else '제안 없음'}")

    nopro = [f for f in findings
             if f["verdict"] in ("pin_names_unrelated_disease", "pin_absent", "not_mondo")
             and not f["proposals"]]
    if nopro:
        print(f"\n제안을 찾지 못한 {len(nopro)}건 (라벨이 MONDO 용어가 아닐 수 있습니다)")
        for f in nopro:
            print(f"  {f['id']:26s} \"{f['label']}\"")

    args.candidates.parent.mkdir(parents=True, exist_ok=True)
    with args.candidates.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "label", "pinned", "pinned_names", "verdict",
                    "proposed_id", "proposed_name", "hand_axes"])
        for f in findings:
            prop = f["proposals"][0] if f["proposals"] else {}
            w.writerow([f["id"], f["label"], f["pinned"], f["pinned_names"] or "",
                        f["verdict"], prop.get("mondo_id", ""),
                        prop.get("mondo_name", ""), f["hand_axes"]])

    args.out.write_text(json.dumps({
        "provenance": stamp({"registry": REGISTRY}),
        "n_conditions": len(rows),
        "verdict_counts": counts,
        "n_pin_wrong": len(wrong),
        "n_pin_absent": len(absent),
        "findings": findings,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n→ {args.out}\n→ {args.candidates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
