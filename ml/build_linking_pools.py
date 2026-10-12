"""Candidate pools for the disease-linking gold (data/curated/disease_linking/).

    CUDA_VISIBLE_DEVICES=3 python -I ml/build_linking_pools.py

Annotators choose concepts from a pool instead of searching all of MONDO. The pool for one query is the union of
SapBERT top-8, BioLORD top-5 and character TF-IDF top-8 (each de-duplicated to concepts) plus the concept(s) matching the
query writer's intended name. Pools are shuffled, so annotators cannot tell which system proposed what or which concept
was intended. The per-system ranks are saved separately (pools_v0_systems.json) and never shown to annotators.
Writes raw/pools_v0.json and annot/shard_<k>.txt (the files annotators read).
"""
import json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
D = "/home/hyeongchanahn/CONI/adctox/data/curated/disease_linking/"; OBO = "/home/hyeongchanahn/CONI/adctox/data/raw_big/mondo/2026-10-07/mondo.obo"
SHARDS = 4


def read_obo():
    T, cur = {}, None
    for line in open(OBO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": cur = None; continue
        if line.startswith("[") or not line: continue
        if line.startswith("id: "): cur = line[4:].strip(); T[cur] = dict(name="", syn=[], defn="", parents=[])
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:].strip()
        elif line.startswith("def: "): q = re.match(r'def: "(.*)"', line); T[cur]["defn"] = q.group(1) if q else ""
        elif line.startswith("synonym: ") and " EXACT " in line: q = re.match(r'synonym: "(.*)" EXACT', line); T[cur]["syn"].append(q.group(1)) if q else None
        elif line.startswith("is_a: "): T[cur]["parents"].append(line[6:].split()[0])
    return T


def concept_topk(S, ids, k):
    out = []
    for row in S:
        seen, picks = set(), []
        for j in np.argsort(-row)[:k * 20]:
            c = ids[j]
            if c in seen: continue
            seen.add(c); picks.append((c, float(row[j])))
            if len(picks) == k: break
        out.append(picks)
    return out


def main():
    import mondo_index as MI, vulnerability_model as VM
    from sklearn.feature_extraction.text import TfidfVectorizer
    Q = json.load(open(D + "raw/queries_v0.json")); T = read_obo()
    idx = np.load(MI.C + "mondo_index.npz", allow_pickle=True); ids = [str(x) for x in idx["ids"]]; strs = []
    for t, n in zip(ids, idx["names"]): strs.append(str(n))
    # the index stores names per row; rebuild the row strings (name + exact synonyms, in build order)
    rows, rid = [], []
    seen_order = list(dict.fromkeys(ids))
    for t in seen_order:
        for s in [T[t]["name"]] + T[t]["syn"]: rows.append(s); rid.append(t)
    assert len(rows) == len(ids) and rid == ids, "index rows no longer match the MONDO snapshot"
    texts = [q["query"] for q in Q]
    Eq = MI._embed(texts, "cuda:0"); Sap = concept_topk(Eq @ idx["E"].astype(np.float32).T, ids, 8)
    enc = VM._encoder().encode; Eb_rows = enc(rows, batch_size=256, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32); Eb_q = VM._st(texts); Bio = concept_topk(Eb_q @ Eb_rows.T, ids, 5)
    tf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), lowercase=True, min_df=1, sublinear_tf=True).fit(rows)
    Xr = tf.transform(rows); Tf = concept_topk((tf.transform(texts) @ Xr.T).toarray(), ids, 8)
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip(); exact = {}
    for s, t in zip(rows, ids): exact.setdefault(norm(s), set()).add(t)
    intended = sorted({q["intended"] for q in Q if q["intended"]}); iv = {}
    if intended:
        Ei = MI._embed(intended, "cuda:0"); Si = concept_topk(Ei @ idx["E"].astype(np.float32).T, ids, 2); Ti = concept_topk((tf.transform(intended) @ Xr.T).toarray(), ids, 2)
        for n, s1, s2 in zip(intended, Si, Ti): iv[n] = sorted(exact.get(norm(n), set())) or list(dict.fromkeys([c for c, _ in s1] + [c for c, _ in s2]))
    rng = np.random.default_rng(20261012); pools, systems = [], []
    for q, a, b, c in zip(Q, Sap, Bio, Tf):
        cand = list(dict.fromkeys([x for x, _ in a] + [x for x, _ in b] + [x for x, _ in c] + iv.get(q["intended"], [])))
        rng.shuffle(cand)
        pools.append(dict(qid=q["qid"], query=q["query"], pool=cand))
        systems.append(dict(qid=q["qid"], sapbert=a, biolord=b, tfidf=c, intended_ids=iv.get(q["intended"], [])))
    json.dump(pools, open(D + "raw/pools_v0.json", "w"), indent=0); json.dump(systems, open(D + "raw/pools_v0_systems.json", "w"), indent=0)
    def line(t):
        e = T[t]; syn = "; ".join(e["syn"][:3]); par = ", ".join(T[p]["name"] for p in e["parents"][:2] if p in T)
        d = e["defn"][:140] + ("..." if len(e["defn"]) > 140 else "")
        return f"  - {t} | {e['name']}" + (f" | syn: {syn}" if syn else "") + (f" | is_a: {par}" if par else "") + (f" | def: {d}" if d else "")
    order = rng.permutation(len(pools)); per = np.array_split(order, SHARDS)
    for k, part in enumerate(per):
        with open(D + f"annot/shard_{k}.txt", "w") as fh:
            for i in sorted(part):
                p = pools[i]; fh.write(f"### {p['qid']}\nquery: {p['query']}\ncandidates:\n" + "\n".join(line(t) for t in p["pool"]) + "\n\n")
    print("queries", len(pools), "mean pool", np.mean([len(p["pool"]) for p in pools]), "shards", [len(x) for x in per])
    hit = np.mean([bool(set(s["intended_ids"])) for s, q in zip(systems, Q) if q["intended"]]); print("intended concept resolved for", hit)


if __name__ == "__main__":
    main()
