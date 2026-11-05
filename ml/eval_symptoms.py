"""Symptom / sentence search (ml/suggest.symptoms) on data/curated/disease_profiles/symptom_eval_v0.jsonl.

    python ml/eval_symptoms.py [--out v1]

The queries were written by a separate Claude Sonnet agent from the disease names only, without seeing the profiles; they are
synthetic, so these numbers say whether the search works at all, not how it does on real users (that needs task 3's real inputs).
Split by target disease (hash): dev for tuning, test reported once. Hit = target or an also_ok concept in the top k.
-> ml/results/benchmarks/symptom_search_v0.json
"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recommend as RC, suggest as SG

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "disease_profiles") + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "benchmarks", "symptom_search_v0.json")


def split(t): return "dev" if int(hashlib.sha256(t.encode()).hexdigest(), 16) % 2 == 0 else "test"


def run(Q):
    rows = []
    for q in Q:
        got = [s[1] for s, _ in SG.symptoms(RC, q["query"], limit=5)]
        ok = {q["target"], *q.get("also_ok", [])}; rank = next((i + 1 for i, g in enumerate(got) if g in ok), None)
        rows.append(dict(qid=q["qid"], lang=q["lang"], split=split(q["target"]), rank=rank))
    return rows


def summary(rows):
    out = {}
    for name, f in [("all", lambda r: True), ("ko", lambda r: r["lang"] == "ko"), ("en", lambda r: r["lang"] == "en")]:
        R = [r for r in rows if f(r)]
        if R: out[name] = dict(n=len(R), **{f"top{k}": round(sum(1 for r in R if r["rank"] and r["rank"] <= k) / len(R), 3) for k in (1, 3, 5)})
    return out


def main():
    Q = [json.loads(l) for l in open(D + "symptom_eval_v0.jsonl", encoding="utf-8") if l.strip()]
    have = {p["id"] for p in SG.profiles()}; Q = [q for q in Q if q["target"] in have]
    rows = run(Q)
    dev = summary([r for r in rows if r["split"] == "dev"])
    report = dict(n_queries=len(Q), n_profiles=len(SG.profiles()), dev=dev, test=summary([r for r in rows if r["split"] == "test"]),
                  note="synthetic queries (Claude Sonnet, written without the profiles); not real user input")
    out = OUT.replace("_v0", "_" + sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    os.makedirs(os.path.dirname(OUT), exist_ok=True); json.dump(report, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(dict(dev=dev, test=report["test"]), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
