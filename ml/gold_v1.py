"""gold_v1: the gold benchmark re-labelled under the v5 two-tier standard (2026-10-22), and re-scoring of stored results on it.

    python ml/gold_v1.py build                  # gold_v1/{claude_labels,adjudication}.jsonl + v5 labels -> gold_v1/concepts.jsonl, gold_v1.jsonl
    python ml/gold_v1.py build11                # gold_v1/concepts_v5_1.jsonl (ml/relabel_v5_1.py) -> gold_v1_1.jsonl
    python ml/gold_v1.py rescore <result.json>  # a bench_*.json -> dev macro-F1 on gold_v0, gold_v1 (primary ∪ involved) and gold_v1 primary

How the 211 gold concepts were labelled (none of them, nor their parents or children, is a training concept):
1. GPT label: concept_organs/v5/labels_v5.jsonl (gpt-6.1-sol, 3 passes + adjudication + audit; the gold concepts were mixed in unmarked).
2. Claude label: 9 independent Claude Opus 5.5 agents, blind to every other label, same GUIDE_v5.md and evidence (gold_v1/claude_labels.jsonl).
3. Where 1 and 2 differ (organ set, primary set or no_axis), two adjudicators saw both as anonymous A/B in random order: a Claude
   agent (gold_v1/adjudication.jsonl) and GPT via Codex (gold_v1/adjudication_gpt.jsonl). See build() for how they are combined.
gold_v1.jsonl is gold_v0.jsonl with `organs` replaced by primary ∪ involved of the question's `best` concept, and `organs_primary`
added; questions without a `best` concept keep their gold_v0 organs. gold_v0.jsonl is never changed.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P

D = P.REPO + "data/curated/disease_linking/"; G1 = D + "gold_v1/"
V5 = P.REPO + "data/curated/concept_organs/v5/labels_v5.jsonl"


def jl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def build():
    """final label per gold concept. GPT and Claude labels agree -> that label. They differ -> two adjudicators, a Claude agent
    (adjudication.jsonl) and GPT gpt-6.1-sol via Codex (adjudication_gpt.jsonl), each saw both labels as anonymous A/B. Each judge
    preferred its own model's label (26 of 33 each), so an organ's tier is final only where the two judges agree; where they differ,
    the human gold_v0 label breaks the tie (organ in gold_v0 -> kept, primary if either judge said primary; otherwise left out)."""
    import collections
    gpt = {r["id"]: r for r in jl(V5)}; cl = {r["id"]: r for r in jl(G1 + "claude_labels.jsonl")}
    adj = {r["id"]: r for r in jl(G1 + "adjudication.jsonl")}; adg = {r["id"]: r for r in jl(G1 + "adjudication_gpt.jsonl")}
    g0 = collections.defaultdict(list)
    for g in jl(D + "gold_v0.jsonl"):
        if g["validity"] == "valid" and g.get("best"): g0[g["best"]].append(frozenset(g["organs"]))
    g0 = {c: collections.Counter(v).most_common(1)[0][0] for c, v in g0.items()}
    tier = lambda r, o: "P" if o in r["primary"] else "I" if o in r["involved"] else "-"
    out = []; ties = 0
    for t in sorted(cl):
        if t not in adj: r = gpt[t]; out.append(dict(id=t, primary=sorted(r["primary"]), involved=sorted(r["involved"]), no_axis=bool(r.get("no_axis")), how="GPT and Claude agree")); continue
        a, b = adj[t], adg[t]; P_, I_ = [], []
        for o in sorted(set(a["primary"]) | set(a["involved"]) | set(b["primary"]) | set(b["involved"])):
            ta, tb = tier(a, o), tier(b, o)
            if ta == tb: f = ta
            else:
                ties += 1; f = ("P" if "P" in (ta, tb) else "I") if o in g0.get(t, ()) else "-"
            (P_ if f == "P" else I_ if f == "I" else []).append(o)
        out.append(dict(id=t, primary=P_, involved=I_, no_axis=bool(a.get("no_axis")) and bool(b.get("no_axis")), how="two adjudicators (+ gold_v0 tie-break)"))
    open(G1 + "concepts.jsonl", "w", encoding="utf-8").write("".join(json.dumps(x) + "\n" for x in out))
    print(dict(organ_ties_broken_by_gold_v0=ties))
    write_questions(out, D + "gold_v1.jsonl")


def write_questions(out, path):
    C = {x["id"]: x for x in out}; n = 0; rows = []
    for g in jl(D + "gold_v0.jsonl"):
        c = C.get(g.get("best")) if g["validity"] == "valid" else None
        if c: g = dict(g, organs=sorted(set(c["primary"]) | set(c["involved"])), organs_primary=c["primary"]); n += 1
        rows.append(g)
    open(path, "w", encoding="utf-8").write("".join(json.dumps(x) + "\n" for x in rows))
    print(dict(out=os.path.basename(path), concepts=len(out), adjudicated=sum(not x["how"].startswith("GPT and Claude agree") for x in out), questions=len(rows), relabelled_questions=n))


def golds():
    """-> {name: gold list aligned with bench_judge.questions()} for gold_v0, gold_v1 and gold_v1 primary."""
    import bench_judge as B
    Q, g0, groups, ko, SE = B.questions(); v1 = {x["qid"]: x for x in jl(D + "gold_v1.jsonl")}
    g1 = [dict(g, organs=v1[g["qid"]]["organs"]) for g in g0]
    g1p = [dict(g, organs=v1[g["qid"]].get("organs_primary", v1[g["qid"]]["organs"])) for g in g0]
    G = dict(gold_v0=g0, gold_v1=g1, gold_v1_primary=g1p)
    if os.path.exists(D + "gold_v1_1.jsonl"):
        v11 = {x["qid"]: x for x in jl(D + "gold_v1_1.jsonl")}; G["gold_v1_1"] = [dict(g, organs=v11[g["qid"]]["organs"]) for g in g0]
    return G, groups


def rescore(path, split="dev"):
    import eval_linking as EL
    G, groups = golds(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == split]; per = json.load(open(path))["per"]; out = {}
    for lg in ("en", "ko"):
        rows = per[lg]; pred = [((r or {}).get("concept"), (r or {}).get("organs", [])) for r in rows]; jx = [i for i in ix if rows[i] is not None]
        out[lg] = {k: round(EL.metrics(pred, g, jx)["macro_f1"], 4) for k, g in G.items()}
    return out


if __name__ == "__main__":
    if sys.argv[1] == "build": build()
    elif sys.argv[1] == "build11": write_questions(jl(G1 + "concepts_v5_1.jsonl"), D + "gold_v1_1.jsonl")
    else: print(json.dumps(rescore(sys.argv[2]), indent=1))
