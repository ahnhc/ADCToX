"""Clinician review sheet for the organs where a wrong table costs a warning: common conditions on which the sources disagree.

    python ml/risk_sheet.py [--concepts <ScratchJudge/concepts.json>]
    -> data/curated/team_sheets/6_고위험_장기_검토.csv

Common conditions: the dev-side gold concepts (gold_v0), the registry's MONDO ids, and the disease profiles. Sources compared per concept:
the v5.1 label table (primary + involved), the record-reader table (the installed bundle's concepts.json, where via is "record"), and
for a dev gold concept the gold organs of its dev-side questions. A row is a (concept, organ) pair on which the sources do not all
agree and some ADC label warns on that organ. Rows with a Boxed warning on the organ come first, most ADCs first, then W&P only.

Test side is left out: any concept that a gold_v0 test-split question accepts, and any symptom-eval target in the test split, never
reaches the sheet, and no test-split organ list is read. The sheet carries no answers and changes no label: a label changes only
after a clinician answers.
"""
import csv, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import missed_warnings as MW

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(REPO, "data", "curated", "team_sheets", "6_고위험_장기_검토.csv")
CONCEPTS = os.path.expandvars("%LOCALAPPDATA%/adctox/models/versions/*/ScratchJudge/concepts.json")
SRC = ("registry", "dev_gold", "profile")
HEAD = ["번호", "질환 ID", "질환 이름", "출처", "v5.1 라벨표 장기", "기록 읽기 표 장기", "dev 정답 장기", "쟁점 장기", "쟁점 장기의 경고 수준",
        "Boxed 경고가 있는 ADC 수", "W&P 경고가 있는 ADC 수", "답: 이 질환이 쟁점 장기를 직접 손상시키나 (예/아니오/모르겠음)", "답: 근거나 메모", "검토자"]


def disputes(sources, evidence):
    """sources: {name: set of organs}; evidence: organ -> (n_boxed, n_wp). -> [(organ, n_boxed, n_wp)] for organs on which the sources
    differ and some ADC label warns, Boxed first, then by the number of ADCs."""
    if len(sources) < 2: return []
    union = set().union(*sources.values()); common = set.intersection(*sources.values())
    out = [(o, *evidence.get(o, (0, 0))) for o in union - common if sum(evidence.get(o, (0, 0))) > 0]
    return sorted(out, key=lambda x: (-(x[1] > 0), -x[1], -x[2], x[0]))


def build(concepts, v51, gold_dev, dev_concepts, registry, profiles, test_side, evidence, names=None):
    """-> rows sorted by value. concepts: bundle concepts.json; v51: id -> organ set; gold_dev: id -> organ set (dev-side questions only)."""
    rows = []; pool = {}
    for rank, S in enumerate((registry, dev_concepts, profiles)):
        for c in S: pool.setdefault(c, rank)
    for c, rank in pool.items():
        if c in test_side or c not in v51: continue
        name, organs, via = concepts.get(c, ["", [], ""])
        src = {"v5.1": set(v51[c])}
        if via == "record": src["record"] = set(organs)
        if c in gold_dev: src["gold"] = set(gold_dev[c])
        for o, b, w in disputes(src, evidence):
            rows.append(dict(id=c, name=name or (names or {}).get(c, ""), source=SRC[rank], v51=sorted(src["v5.1"]), record=sorted(src.get("record", [])) if "record" in src else None,
                             gold=sorted(src["gold"]) if "gold" in src else None, organ=o, boxed=b, wp=w, rank=rank))
    rows.sort(key=lambda r: (-(r["boxed"] > 0), -r["boxed"], r["rank"], -r["wp"], r["name"], r["organ"]))
    return rows


def write(rows, path=OUT):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cell = lambda v: "" if v is None else "; ".join(v) or "(없음)"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(HEAD)
        for k, r in enumerate(rows, 1):
            w.writerow([k, r["id"], r["name"], r["source"], cell(r["v51"]), cell(r["record"]), cell(r["gold"]), r["organ"], "Boxed" if r["boxed"] else "W&P", r["boxed"], r["wp"], "", "", ""])


def main():
    import eval_linking as EL, bench_judge as BJ
    a = sys.argv; paths = sorted(glob.glob(a[a.index("--concepts") + 1] if "--concepts" in a else CONCEPTS), key=os.path.getmtime)
    concepts = json.load(open(paths[-1], encoding="utf-8"))
    D = os.path.join(REPO, "data", "curated")
    v51 = {x["id"]: set(x["primary"]) | set(x["involved"]) for x in map(json.loads, open(os.path.join(D, "concept_organs", "v5", "labels_v5_1.jsonl"), encoding="utf-8"))}
    Q = json.load(open(os.path.join(D, "disease_linking", "raw", "queries_v0.json"), encoding="utf-8"))
    G = {x["qid"]: x for x in map(json.loads, open(os.path.join(D, "disease_linking", "gold_v0.jsonl"), encoding="utf-8"))}
    dev_q = [q for q in Q if EL.split_of(q["group"] or q["qid"]) == "dev"]; test_side = {c for q in Q if EL.split_of(q["group"] or q["qid"]) == "test" for c in G[q["qid"]]["concepts"]}
    dev_concepts = {c for q in dev_q for c in G[q["qid"]]["concepts"]}
    gold_dev = {}
    for q in dev_q:
        g = G[q["qid"]]
        if g["validity"] == "valid" and g["best"]: gold_dev.setdefault(g["best"], set()).update(g["organs"])
    test_side |= {s["target"] for s in map(json.loads, filter(str.strip, open(os.path.join(D, "disease_profiles", "symptom_eval_v0.jsonl"), encoding="utf-8"))) if BJ.sym_split(s["target"]) == "test"}
    registry = [r["mondo_id"] for r in csv.DictReader(open(os.path.join(REPO, "conf", "comorbidity_registry.csv"), encoding="utf-8")) if r["mondo_id"]]
    profiles = {r["id"] for f in sorted(glob.glob(os.path.join(D, "disease_profiles", "profiles_*.jsonl"))) for r in map(json.loads, filter(str.strip, open(f, encoding="utf-8"))) if str(r.get("id", "")).startswith("MONDO:")}
    rows = build(concepts, v51, gold_dev, dev_concepts, list(dict.fromkeys(registry)), profiles, test_side, MW.warning_counts())
    write(rows)
    print(f"{len(rows)} rows, {len({r['id'] for r in rows})} concepts, {sum(r['boxed'] > 0 for r in rows)} rows with a Boxed organ -> {OUT}")


if __name__ == "__main__":
    main()
