"""v5.1 labels: v5 with `involved` organs dropped where two independent Haiku reviews agree (rules: concept_organs/v5/RULE_v5_1.md).

    python ml/relabel_v5_1.py merge <review_dir>    # <review_dir>/in/r_NNN.json, out/r_NNN_{a,b}.jsonl, source.json
    python ml/relabel_v5_1.py final <gpt_dir>       # GPT (Codex) check of every dropped organ: <gpt_dir>/out/*.jsonl {id, drop, keep}

Writes concept_organs/v5/labels_v5_1.jsonl (all concepts, `how` gains "+v5.1 review"), review_v5_1.jsonl (every reviewed organ
with both votes), and disease_linking/gold_v1/concepts_v5_1.jsonl (gold_v1 concepts with the same drops). `primary` never changes.
An organ is dropped only when both votes drop it; a batch with a missing or malformed vote keeps every organ.
"""
import collections, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P

V5 = P.REPO + "data/curated/concept_organs/v5/"; G1 = P.REPO + "data/curated/disease_linking/gold_v1/"


def jl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def votes(d):
    out, bad = {}, []
    for f in sorted(glob.glob(d + "/in/r_*.json")):
        b = os.path.basename(f)[:-5]; items = json.load(open(f, encoding="utf-8")); want = {it["record"]["id"]: set(it["label"]["involved"]) for it in items}
        vv = []
        for v in ("a", "b"):
            p = f"{d}/out/{b}_{v}.jsonl"
            try: rows = {r["id"]: r for r in jl(p)}
            except Exception: rows = {}
            ok = set(rows) == set(want) and all(set(rows[t]["keep"]) | set(rows[t]["drop"]) == want[t] and not set(rows[t]["keep"]) & set(rows[t]["drop"]) for t in want)
            vv.append(rows if ok else None)
        if None in vv: bad.append(b)
        for t, inv in want.items():
            out[t] = dict(involved=sorted(inv), a=vv[0] and vv[0][t], b=vv[1] and vv[1][t])
    return out, bad


def merge(d):
    V, bad = votes(d); src = json.load(open(d + "/source.json")); review = []; drops = {}
    for t, x in V.items():
        for o in x["involved"]:
            da = bool(x["a"]) and o in x["a"]["drop"]; db = bool(x["b"]) and o in x["b"]["drop"]
            review.append(dict(id=t, organ=o, source=src[t], drop_a=da, drop_b=db, dropped=da and db, reason_a=(x["a"] or {}).get("reason", ""), reason_b=(x["b"] or {}).get("reason", "")))
            if da and db: drops.setdefault(t, set()).add(o)
    open(V5 + "review_v5_1.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in review))
    out = []
    for r in jl(V5 + "labels_v5.jsonl"):
        if src.get(r["id"]) == "v5" and r["id"] in drops:
            inv = [o for o in r["involved"] if o not in drops[r["id"]]]
            r = dict(r, involved=inv, organs=sorted(set(r["primary"]) | set(inv)), how=r.get("how", "") + " +v5.1 review", dropped_v5_1=sorted(drops[r["id"]]))
        out.append(r)
    open(V5 + "labels_v5_1.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    g = []
    for r in jl(G1 + "concepts.jsonl"):
        if src.get(r["id"]) == "gold_v1" and r["id"] in drops: r = dict(r, involved=[o for o in r["involved"] if o not in drops[r["id"]]], how=r["how"] + " +v5.1 review")
        g.append(r)
    open(G1 + "concepts_v5_1.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in g))
    n = len(review); a = sum(r["drop_a"] for r in review); b = sum(r["drop_b"] for r in review); both = sum(r["dropped"] for r in review)
    agree = sum(r["drop_a"] == r["drop_b"] for r in review)
    print(json.dumps(dict(organs_reviewed=n, drop_a=a, drop_b=b, dropped_both=both, vote_agreement=round(agree / max(n, 1), 3), concepts_changed=len(drops),
                          gold_concepts_changed=sum(src[t] == "gold_v1" for t in drops), batches_without_two_votes=bad,
                          dropped_by_organ=dict(collections.Counter(r["organ"] for r in review if r["dropped"]).most_common())), indent=1))


def final(d):
    """labels_v5_1_final.jsonl and gold_v1/concepts_v5_1_final.jsonl: a v5.1 drop stands only if GPT (gpt-6.1-sol via Codex,
    ml/codex_batch.py, same RULE_v5_1.md) also drops it; organs GPT keeps go back to `involved`."""
    keep = {}
    for f in glob.glob(d + "/out/*.jsonl"):
        for r in jl(f):
            if r.get("keep"): keep[r["id"]] = set(r["keep"])
    v5 = {r["id"]: r for r in jl(V5 + "labels_v5.jsonl")}; out = []; n = 0
    for r in jl(V5 + "labels_v5_1.jsonl"):
        back = keep.get(r["id"], set()) & set(r.get("dropped_v5_1", []))
        if back:
            inv = [o for o in v5[r["id"]]["involved"] if o in set(r["involved"]) | back]; n += len(back)
            r = dict(r, involved=inv, organs=sorted(set(r["primary"]) | set(inv)), dropped_v5_1=sorted(set(r["dropped_v5_1"]) - back), restored_by_gpt=sorted(back))
        out.append(r)
    open(V5 + "labels_v5_1_final.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    g1 = {r["id"]: r for r in jl(G1 + "concepts.jsonl")}; g = []
    for r in jl(G1 + "concepts_v5_1.jsonl"):
        back = keep.get(r["id"], set()) & (set(g1[r["id"]]["involved"]) - set(r["involved"]))
        if back: r = dict(r, involved=[o for o in g1[r["id"]]["involved"] if o in set(r["involved"]) | back], how=r["how"] + " +GPT restore")
        g.append(r)
    open(G1 + "concepts_v5_1_final.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r) + "\n" for r in g))
    print(json.dumps(dict(organs_restored=n, dropped_final=sum(len(r.get("dropped_v5_1", [])) for r in out), concepts_with_drops=sum(bool(r.get("dropped_v5_1")) for r in out))))


if __name__ == "__main__":
    {"merge": merge, "final": final}[sys.argv[1]](sys.argv[2])
