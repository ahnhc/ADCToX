"""Learned reranker of the 10 nearest MONDO concepts (task 2 of docs/TEAM_HANDOFF.md), written into the index (v4).

    CUDA_VISIBLE_DEVICES=1 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<copy of the cache> python ml/rerank_train.py [--dry]

Training pairs (typed text -> concept), never a gold concept or its parents / children:
  external  MedMentions, NCBI Disease, BC5CDR, COMETA train splits (data/curated/external/mentions_mondo.jsonl)
  haiku     generated queries that passed review (data/curated/train_queries/, batches with >= 80% trap rejection)
  haiku2    round 2 (gen/gen2_*, review/review2_*): synonym, abbreviation, typo and lay inputs, kept when a second agent says valid + match
  typo      one or two character edits of MONDO names and synonyms
  abbrev    abbreviations whose LRABR expansions name exactly one MONDO concept
Features: mondo_index.rr_features (computed the same way at run time). Logistic regression, one row per candidate.
The acceptance threshold is chosen on the gold dev split (organ macro-F1, false acceptance of invalid input not above the
current linker); the test split is not used here. --dry reports without writing the index.
"""
import glob, json, os, random, re, sys
from collections import Counter
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P, eval_linking as EL, mondo_index as MI, linking_models as LM
from build_linking_pools import read_obo

R = P.REPO + "data/curated/"; DEV = "cuda:0" if torch.cuda.is_available() else "cpu"; SEED = 11


def pairs(T, held):
    rng = random.Random(SEED); out = []; ok = lambda t: t in T and t not in held and "non-human" not in T[t]["name"]
    ext = [json.loads(l) for l in open(R + "external/mentions_mondo.jsonl")]
    by = {}
    for r in ext:
        if r["split"] == "train" and len(r["mondo"]) == 1 and ok(r["mondo"][0]): by.setdefault(r["source"], []).append((r["mention"], r["mondo"][0]))
    for s, L in by.items():
        L = list(dict.fromkeys(L)); rng.shuffle(L); out += [(q, t, "external_" + s) for q, t in L[:4000]]
    rm = json.load(open(R + "train_queries/review_manifest.json")); traps = set(rm["traps"]); gens = {}
    for k in range(5):
        for i, x in enumerate(json.loads(l) for l in open(R + f"train_queries/gen/gen_{k}.jsonl")): gens[f"g{k}_{i:03d}"] = x
    for k in range(5):
        f = R + f"train_queries/review/review_{k}.jsonl"
        if not os.path.exists(f): continue
        L = [json.loads(l) for l in open(f)]; tr = [x for x in L if x["rid"] in traps]
        if not tr or np.mean([x["match"] is False for x in tr]) < 0.8: continue
        out += [(gens[x["rid"]]["query"], gens[x["rid"]]["concept"], "haiku") for x in L
                if x["rid"] not in traps and x["rid"] in gens and x["validity"] == "valid" and x["match"] is True and ok(gens[x["rid"]]["concept"])]
    for f in sorted(glob.glob(R + "train_queries/review/review2_*.jsonl")):          # round 2: written and reviewed by different agents
        for x in map(json.loads, open(f)):
            if x.get("validity") == "valid" and x.get("match") is True and ok(x.get("concept", "")): out.append((x["query"], x["concept"], "haiku2_" + x.get("category", "")))
    names = [(s, t) for t in T if t.startswith("MONDO:") and ok(t) for s in [T[t]["name"]] + T[t]["syn"] if 6 <= len(s) <= 40]
    for s, t in rng.sample(names, 4000):
        w = list(s)
        for _ in range(rng.choice((1, 1, 2))):
            i = rng.randrange(1, len(w) - 1); op = rng.choice("dsr")
            if op == "d": del w[i]
            elif op == "s": w[i], w[i + 1] = w[i + 1], w[i]
            else: w[i] = rng.choice("abcdefghijklmnopqrstuvwxyz")
        out.append(("".join(w), t, "typo"))
    MI.link(["x"]); ab = [(k, v.split(";")) for k, v in zip(MI._IDX["abbr_keys"], MI._IDX["abbr_vals"])]
    out += [(str(k), v[0], "abbrev") for k, v in ab if len(v) == 1 and ok(v[0])]
    return out


def candidates(texts):
    """the run-time candidate lists (mondo_index.link) for many texts at once."""
    if MI._IDX is None or MI._IDX_E is None: MI.link(["x"])
    E = MI._IDX_E; out = []
    for i in range(0, len(texts), 1024):
        Q = torch.from_numpy(MI._embed(texts[i:i + 1024], DEV).astype(np.float32)).to(E.device)
        with torch.no_grad(): v, j = (Q @ E.T).topk(64, dim=1)
        out += [MI.concept_candidates(jj, vv) for jj, vv in zip(j.cpu().tolist(), v.cpu().tolist())]
    return out


def main():
    from sklearn.linear_model import LogisticRegression
    T = read_obo(); held = LM.gold_held(T); MI.link(["x"])
    prior = {t: float(np.log1p(n)) for t, n in LM.mention_counts().items()}
    MI._IDX["_prior"] = prior
    data = pairs(T, held); print("pairs", Counter(s for _, _, s in data))
    C = candidates([q for q, _, _ in data]); X, y, g, kept = [], [], [], Counter()
    for n, ((q, t, s), c) in enumerate(zip(data, C)):
        if t not in [x[0] for x in c]: continue
        kept[s] += 1; F = MI.rr_features(q, c); X.append(F); y += [x[0] == t for x in c]; g += [n] * len(c)
    X = np.concatenate(X); y = np.array(y); print("queries with the answer in the top 10:", dict(kept), "rows", len(y))
    mu, sd = X.mean(0), X.std(0) + 1e-6; m = LogisticRegression(C=1.0, max_iter=5000).fit((X - mu) / sd, y)
    w, b = m.coef_[0].astype(np.float32), np.float32(m.intercept_[0])
    MI._IDX.update(rr_w=w, rr_b=b, rr_mu=mu.astype(np.float32), rr_sd=sd.astype(np.float32), rr_threshold=np.float32(0))
    # choose the acceptance threshold on the gold dev split
    Q = json.load(open(EL.D + "raw/queries_v0.json")); G = {x["qid"]: x for x in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [dict(G[q["qid"]], category=q["category"]) for q in Q]; groups = [q["group"] or q["qid"] for q in Q]
    dev = [i for i, gr in enumerate(groups) if EL.split_of(gr) == "dev"]
    GC = candidates([q["query"] for q in Q])
    def run(th):
        out = []
        for q, c in zip(Q, GC):
            if th is None: t, ok = c[0][0], c[0][1] >= MI.THETA
            else:
                z = MI.rerank_scores(q["query"], c); o = int(np.argmax(z)); t, ok = c[o][0], z[o] >= th
            out.append((t if ok else None, MI.concept(t)[1] if ok else []))
        return out
    base = EL.metrics(run(None), gold, dev)
    cands = [(EL.metrics(run(th), gold, dev), th) for th in np.arange(-3.0, 1.01, 0.1)]
    fine = [(mm, th) for mm, th in cands if (mm["false_accept_invalid"] or 0) <= (base["false_accept_invalid"] or 0)]
    best, th = max(fine or cands, key=lambda x: x[0]["macro_f1"])
    concept_acc = lambda P_: float(np.mean([p[0] in gold[i]["concepts"] for i, p in zip(dev, [P_[i] for i in dev]) if gold[i]["validity"] == "valid" and gold[i]["concepts"]]))
    res = dict(pairs=dict(Counter(s for _, _, s in data)), kept=dict(kept), weights=dict(zip(
        ["sim", "gap", "rank", "first", "log_strings", "tri_jaccard", "query_words_in_name", "name_words_in_query", "name_len", "prior", "abbr_hit", "is_abbrev", "abbrev_x_hit", "abbrev_x_sim", "has_organ", "query_len", "has_digit"], w.tolist())),
        threshold=float(th), dev_base=dict(macro_f1=base["macro_f1"], false_accept_invalid=base["false_accept_invalid"], concept_acc=concept_acc(run(None))),
        dev_rerank=dict(macro_f1=best["macro_f1"], false_accept_invalid=best["false_accept_invalid"], concept_acc=concept_acc(run(th))))
    print(json.dumps(res, indent=1))
    json.dump(res, open(P.REPO + "ml/results/benchmarks/rerank_v1.json", "w"), indent=1)
    if "--dry" in sys.argv: return
    path = MI.C + "mondo_index.npz"; z = dict(np.load(path, allow_pickle=True))
    pi = sorted(prior); z.update(rr_w=w, rr_b=b, rr_mu=mu.astype(np.float32), rr_sd=sd.astype(np.float32), rr_threshold=np.float32(th),
                                  rr_prior_ids=np.array(pi), rr_prior=np.array([prior[t] for t in pi], np.float32), version=np.array("v4"))
    np.savez(path, **z); print("index v4 written:", path)


if __name__ == "__main__":
    main()
