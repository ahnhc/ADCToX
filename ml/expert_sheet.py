"""Blind expert check of the organ answers (docs/competition_plan.md, criterion 5): gold test diseases, two systems' answers mixed.

    ADC_RESEARCH_MODE=1 python ml/expert_sheet.py --a scratch_x2e7 --b single_v51as7          # after the one test scoring
    ADC_RESEARCH_MODE=1 python ml/expert_sheet.py score <filled sheet.csv>
    -> data/curated/competition/expert_sheet.csv   one row per (disease, answer): the canonical name of each gold test disease
                                                   and one system's organs; the reviewer marks every organ correct or wrong and
                                                   writes the missing organs. Which system gave the answer is not shown: rows
                                                   are shuffled, and when both systems give the same organs they share one row
       /data/hyeongchanahn/adctox/work/competition/expert_key.json   row -> systems (kept out of git and away from reviewers)
`score` reads a filled sheet back and gives each system's organ precision and recall as the reviewers judged them.
"""
import csv, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P, eval_a4 as E4, eval_linking as EL
from drug_evidence import AXES

SHEET = P.REPO + "data/curated/competition/expert_sheet.csv"
KEY = "/data/hyeongchanahn/adctox/work/competition/expert_key.json"
COLS = ["row", "disease", "organs_given", "wrong_organs", "missing_organs", "comment"]


def make(a, b, seed=0):
    Q, gold, groups, _ = E4.gold()
    B = {n: json.load(open(P.REPO + f"ml/results/benchmarks/bench_{n}.json"))["per"]["en"] for n in (a, b)}
    ix = [i for i, (q, g) in enumerate(zip(Q, groups)) if EL.split_of(g) == "test" and q["category"] == "canonical"]
    items = []
    for i in ix:
        ans = {n: sorted((B[n][i] or {}).get("organs", [])) for n in (a, b)}
        for o in {tuple(v) for v in ans.values()}:
            items.append(dict(qid=Q[i]["qid"], disease=Q[i]["query"], organs=list(o), systems=sorted(n for n, v in ans.items() if tuple(v) == o)))
    random.Random(seed).shuffle(items)
    os.makedirs(os.path.dirname(SHEET), exist_ok=True); os.makedirs(os.path.dirname(KEY), exist_ok=True)
    with open(SHEET, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(COLS)
        for k, it in enumerate(items, 1): w.writerow([k, it["disease"], "; ".join(it["organs"]) or "none", "", "", ""])
    json.dump(dict(a=a, b=b, seed=seed, axes=AXES, rows={k: it for k, it in enumerate(items, 1)}), open(KEY, "w"), indent=1)
    print(f"{len(ix)} diseases, {len(items)} rows -> {SHEET}; key -> {KEY}")


def score(path):
    key = json.load(open(KEY)); S = {n: dict(tp=0, fp=0, fn=0) for n in (key["a"], key["b"])}
    split = lambda s: {x.strip() for x in (s or "").replace(",", ";").split(";") if x.strip() and x.strip() != "none"}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        it = key["rows"][str(int(r["row"]))]; given = set(it["organs"]); wrong = split(r["wrong_organs"]) & given; miss = split(r["missing_organs"]) - given
        bad = (split(r["wrong_organs"]) - given) | (miss - set(AXES))
        if bad: print(f"row {r['row']}: not an organ of this row or not an axis: {sorted(bad)}")
        miss &= set(AXES)
        for n in it["systems"]:
            S[n]["tp"] += len(given - wrong); S[n]["fp"] += len(wrong); S[n]["fn"] += len(miss)
    for n, s in S.items():
        p = s["tp"] / max(1, s["tp"] + s["fp"]); rc = s["tp"] / max(1, s["tp"] + s["fn"])
        print(f"{n:24} precision {p:.3f}  recall {rc:.3f}  F1 {2 * p * rc / max(1e-9, p + rc):.3f}  ({s})")


if __name__ == "__main__":
    a = sys.argv
    if a[1:2] == ["score"]: score(a[2])
    else: make(a[a.index("--a") + 1], a[a.index("--b") + 1], int(a[a.index("--seed") + 1]) if "--seed" in a else 0)
