"""Batches for the second Gemma judge (one model, several outputs): Haiku 5.5 writes the training texts, Sonnet the Korean eval.

    ADC_RESEARCH_MODE=1 python ml/judge2_batches.py

data/curated/judge2/batches/
  sym_NN.json   disease profiles (id, names) -> 10 patient-style sentences each (symptoms, history, tests), Korean and English.
                The generators never see data/curated/disease_profiles/symptom_eval_v0.jsonl.
  ko_NN.json    frequent MONDO concepts of the training sources (external corpus mentions, reviewed queries) -> Korean
                expressions (formal, everyday, spoken). Gold concepts and their relatives are left out.
  junk_NN.json  instructions only -> inputs that name no condition (gibberish, placeholders, food, people, objects).
  koeval_NN.json the gold queries (text and category only, no labels) -> Korean versions for evaluation; never training.
Outputs go to data/curated/judge2/gen/<batch>.jsonl.
"""
import collections, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P, eval_linking as EL, linking_models as LM, suggest as SG
from build_linking_pools import read_obo

R = P.REPO + "data/curated/"; OUT = R + "judge2/"


def chunks(xs, n): k = (len(xs) + n - 1) // n; return [xs[i:i + k] for i in range(0, len(xs), k)]


def main():
    T = read_obo(); held = LM.gold_held(T); os.makedirs(OUT + "batches", exist_ok=True); os.makedirs(OUT + "gen", exist_ok=True)
    prof = [dict(id=p["id"], name=p["name"], en=p.get("en", [])[:3], ko=p.get("ko", [])[:2]) for p in SG.profiles()]
    for i, b in enumerate(chunks(prof, 20)): json.dump(b, open(OUT + f"batches/sym_{i:02d}.json", "w"), ensure_ascii=False, indent=0)
    c = collections.Counter()
    for r in map(json.loads, open(R + "external/mentions_mondo.jsonl")):
        if r["split"] == "train" and len(r["mondo"]) == 1: c[r["mondo"][0]] += 1
    for f in glob.glob(R + "train_queries/review/review2_*.jsonl"):
        for x in map(json.loads, open(f)): c[x["concept"]] += 1
    con = [dict(id=t, name=T[t]["name"], syn=T[t]["syn"][:3]) for t, _ in c.most_common() if t in T and t not in held and not T[t]["name"].startswith("obsolete")]
    for i, b in enumerate(chunks(con, 20)): json.dump(b, open(OUT + f"batches/ko_{i:02d}.json", "w"), ensure_ascii=False, indent=0)
    for i in range(2): json.dump(dict(n=500, part=i), open(OUT + f"batches/junk_{i:02d}.json", "w"))
    Q = [dict(qid=q["qid"], query=q["query"], category=q["category"]) for q in json.load(open(EL.D + "raw/queries_v0.json"))]
    for i, b in enumerate(chunks(Q, 2)): json.dump(b, open(OUT + f"batches/koeval_{i:02d}.json", "w"), ensure_ascii=False, indent=0)
    print(dict(profiles=len(prof), ko_concepts=len(con), gold_queries=len(Q)))


if __name__ == "__main__":
    main()
