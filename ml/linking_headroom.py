"""How much of the Task A error each fix could remove: oracle upper bounds on the pilot gold (test split).

    python -I ml/linking_headroom.py      (after ml/eval_linking.py has cached raw/system_outputs_v0.json)

Starting from A2 (SapBERT top-1, THETA 0.75), each oracle repairs one stage and keeps the rest:
  crosswalk   when the linked concept is right, its organs are the gold organs (a perfect MONDO -> organ crosswalk)
  rerank10    when the gold concept is anywhere in SapBERT's top 10, it is chosen (a perfect reranker / fine-tuned linker)
  theta       a right top-1 concept below 0.75 is accepted
  combined    all three
Also: which organs the crosswalk misses or adds for right concepts, and the share of non-human-animal top-1 links.
Oracles are upper bounds, not achievable scores.
"""
import json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_linking as EL


def main():
    Q = json.load(open(EL.D + "raw/queries_v0.json")); G = {g["qid"]: g for g in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [dict(G[q["qid"]], category=q["category"]) for q in Q]; S = json.load(open(EL.D + "raw/system_outputs_v0.json")); ax = S["axes_of"]
    groups = [q["group"] or q["qid"] for q in Q]; test = [i for i, g in enumerate(groups) if EL.split_of(g) == "test"]
    def run(crosswalk=False, rerank=False, theta=False):
        P = []
        for i, r in enumerate(S["per"]):
            g = gold[i]; t, s = r["sapbert"][0]
            if rerank and g["concepts"] and t not in g["concepts"]:
                hit = [(c, x) for c, x in r["sapbert"] if c in g["concepts"]]
                if hit: t, s = hit[0]
            right = g["concepts"] and t in g["concepts"]
            if s < 0.75 and not (theta and right): P.append((None, [])); continue
            P.append((t, g["organs"] if (crosswalk and right) else ax.get(t, [])))
        return P
    out = {}
    for name, kw in [("A2", {}), ("crosswalk", dict(crosswalk=True)), ("rerank10", dict(rerank=True)), ("theta", dict(theta=True)),
                     ("rerank10+theta", dict(rerank=True, theta=True)), ("combined", dict(crosswalk=True, rerank=True, theta=True))]:
        m = EL.metrics(run(**kw), gold, test); out[name] = {k: m[k] for k in ("macro_f1", "micro_f1", "exact_set", "concept_acc", "coverage")}
    miss, extra = Counter(), Counter(); n_right = 0
    for i, r in enumerate(S["per"]):
        g = gold[i]; t = r["sapbert"][0][0]
        if g["validity"] == "valid" and g["concepts"] and t in g["concepts"]:
            n_right += 1; a, b = set(ax.get(t, [])), set(g["organs"])
            for o in b - a: miss[o] += 1
            for o in a - b: extra[o] += 1
    out["crosswalk_errors_on_right_concepts"] = dict(n_right=n_right, missing=dict(miss.most_common()), extra=dict(extra.most_common()),
                                                     empty_crosswalk=sum(1 for i, r in enumerate(S["per"]) if gold[i]["validity"] == "valid" and gold[i]["concepts"] and r["sapbert"][0][0] in gold[i]["concepts"] and not ax.get(r["sapbert"][0][0])))
    nh = set(S["nonhuman"]); V = [i for i in range(len(Q)) if gold[i]["validity"] == "valid"]
    out["nonhuman_top1_valid"] = sum(S["per"][i]["sapbert"][0][0] in nh for i in V) / len(V)
    json.dump(out, open(EL.OUT + "linking_headroom_v0.json", "w"), indent=1); print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
