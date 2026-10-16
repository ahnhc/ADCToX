"""Task A evaluation: typed condition -> concept -> organs, on the adjudicated pilot set (data/curated/disease_linking/gold_v0.jsonl).

    CUDA_VISIBLE_DEVICES=1 python -I ml/eval_linking.py [--refresh]

Systems (ml/docs/archive/model_accuracy_plan_2026-10-12.md section 6.1):
  A0  exact alias: registry label, else a MONDO name / exact synonym after case and punctuation folding
  A1  character TF-IDF top-1 over MONDO strings, acceptance threshold tuned on dev
  A2  SapBERT top-1, THETA = 0.75 (the shipped linker on its own)
  A3  BioLORD top-1 over MONDO strings, threshold tuned on dev
  A4  the shipped resolve() (registry -> MONDO -> borrowed organs), no learned fallback
  A4f A4 + the 'auto' learned fallback for unmapped inputs (what the wizard does by default)
  A5  SapBERT top-1 with non-human-animal concepts removed and a similarity + top1-top2 margin gate tuned on dev
Concept-level organs come from the project's MONDO crosswalk (index 'axes'); registry hits use the registry organs.

Gold organs were judged by annotators from clinical knowledge, not from the crosswalk, so A2-A5 organ scores are not circular.
The gold is LLM-annotated (two Sonnet annotators + adjudication): a silver set. Numbers are pilot estimates, not expert-gold accuracy.
Concept groups are split 50/50 into dev/test by a fixed hash; thresholds are chosen on dev, scores are reported on test (and all).
CIs: bootstrap over concept groups (each hard input is its own group), paired between systems.
"""
import argparse, hashlib, json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P
D = P.REPO + "data/curated/disease_linking/"; OUT = P.REPO + "ml/results/benchmarks/"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def split_of(group):
    return "dev" if int(hashlib.sha1(group.encode()).hexdigest(), 16) % 2 == 0 else "test"


def system_outputs(queries, refresh=False, tag="v0"):
    """runs the models once and caches every system's raw top-k / decision per query."""
    path = D + f"raw/system_outputs_{tag}.json"
    if os.path.exists(path) and not refresh: return json.load(open(path))
    os.environ.setdefault("ADC_RESEARCH_MODE", "1")
    import torch, recommend as RC, mondo_index as MI, vulnerability_model as VM
    from build_linking_pools import read_obo
    from sklearn.feature_extraction.text import TfidfVectorizer
    T = read_obo(); idx = np.load(MI.C + "mondo_index.npz", allow_pickle=True); ids = [str(x) for x in idx["ids"]]
    rows = [s for t in dict.fromkeys(ids) for s in [T[t]["name"]] + T[t]["syn"]]
    axes_of = {}
    for t, a in zip(ids, idx["axes"]): axes_of.setdefault(t, [AXES[k] for k in np.where(a > 0)[0]])
    nonhuman = {t for t in axes_of if "non-human animal" in T[t]["name"]}
    texts = [q["query"] for q in queries]; dev = "cuda:0" if torch.cuda.is_available() else "cpu"
    def topk(S, k=10, drop=frozenset()):
        out = []
        for row in S:
            seen, picks = set(), []
            for j in np.argsort(-row)[:k * 30]:
                c = ids[j]
                if c in seen or c in drop: continue
                seen.add(c); picks.append([c, float(row[j])])
                if len(picks) == k: break
            out.append(picks)
        return out
    E = idx["E"].astype(np.float32); Sq = MI._embed(texts, dev).astype(np.float32) @ E.T
    sap, sap_h = topk(Sq), topk(Sq, drop=nonhuman); del Sq
    Eb = VM._encoder().encode(rows, batch_size=256, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
    bio = topk(VM._st(texts) @ Eb.T); del Eb
    tf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), sublinear_tf=True).fit(rows); tfi = topk((tf.transform(texts) @ tf.transform(rows).T).toarray())
    exact = {}
    for s, t in zip(rows, ids): exact.setdefault(norm(s), t)
    reg_axes = {r["id"]: r["organ_axes"].split(";") for r in RC._reg.values()}
    a4, a4f = [], []
    for q in texts:
        RC.FALLBACK = {}; _, _, _, notes, pc = RC.resolve([q]); a4.append(dict(how=dict(notes)[q], organs=sorted(set().union(*[o for c, o, _ in pc if c == q]) if pc else [])))
        RC.FALLBACK = {c: 0.25 for c in RC.unresolved([q])}; _, _, _, notes, pc = RC.resolve([q]); RC.FALLBACK = {}
        a4f.append(dict(how=dict(notes)[q], organs=sorted(set().union(*[o for c, o, _ in pc if c == q]) if pc else [])))
    a0 = []
    for q in texts:
        cid = q if q in RC._reg else RC._by_label.get(q.lower())
        if cid: a0.append(dict(concept=RC._reg[cid].get("mondo_id"), organs=reg_axes[cid]))
        elif norm(q) in exact: t = exact[norm(q)]; a0.append(dict(concept=t, organs=axes_of.get(t, [])))
        else: a0.append(dict(concept=None, organs=[]))
    out = dict(axes_of={t: axes_of[t] for t in {c for L in sap + sap_h + bio + tfi for c, _ in L} | {x["concept"] for x in a0 if x["concept"]}},
               nonhuman=sorted(nonhuman & {c for L in sap + bio + tfi for c, _ in L}),
               per=[dict(qid=qq["qid"], sapbert=s1, sapbert_h=s2, biolord=b, tfidf=t, a0=x0, a4=x4, a4f=x5) for qq, s1, s2, b, t, x0, x4, x5 in zip(queries, sap, sap_h, bio, tfi, a0, a4, a4f)])
    json.dump(out, open(path, "w")); return out


def decide(sysout, gold, theta_tf, theta_bio, a5):
    """-> {system: per-query (concept or None, organ list)}"""
    ax = sysout["axes_of"]; P = {k: [] for k in ["A0", "A1", "A2", "A3", "A4", "A4f", "A5"]}
    for r in sysout["per"]:
        P["A0"].append((r["a0"]["concept"], r["a0"]["organs"]))
        t, s = r["tfidf"][0]; P["A1"].append((t, ax.get(t, [])) if s >= theta_tf else (None, []))
        t, s = r["sapbert"][0]; P["A2"].append((t, ax.get(t, [])) if s >= 0.75 else (None, []))
        t, s = r["biolord"][0]; P["A3"].append((t, ax.get(t, [])) if s >= theta_bio else (None, []))
        P["A4"].append((None, r["a4"]["organs"])); P["A4f"].append((None, r["a4f"]["organs"]))
        (t, s), (_, s2) = r["sapbert_h"][0], r["sapbert_h"][1]
        P["A5"].append((t, ax.get(t, [])) if s >= a5[0] and s - s2 >= a5[1] else (None, []))
    return P


def metrics(pred, gold, ix):
    """organ macro-F1 over the 13 axes (valid queries; a rejected valid query counts as an empty prediction), micro-F1,
    exact-set match, concept top-1 accuracy (valid queries whose gold has a concept), false acceptance on invalid and ambiguous."""
    V = [i for i in ix if gold[i]["validity"] == "valid"]; tp = np.zeros(13); fp = np.zeros(13); fn = np.zeros(13); exact = []; conc = []
    for i in V:
        g, p = set(gold[i]["organs"]), set(pred[i][1])
        for k, a in enumerate(AXES): tp[k] += a in g and a in p; fp[k] += a in p and a not in g; fn[k] += a in g and a not in p
        exact.append(g == p)
        if gold[i]["concepts"] and pred[i][0] is not None: conc.append(pred[i][0] in gold[i]["concepts"])
        elif gold[i]["concepts"]: conc.append(False)
    if all(pred[i][0] is None for i in V): conc = []                          # systems without a concept output (A4)
    f1 = np.where(tp + fp + fn > 0, 2 * tp / np.maximum(2 * tp + fp + fn, 1), np.nan)
    inv = [i for i in ix if gold[i]["validity"] == "invalid"]; amb = [i for i in ix if gold[i]["validity"] == "ambiguous"]
    acc = lambda L: float(np.mean([bool(pred[i][1]) for i in L])) if L else None
    return dict(macro_f1=float(np.nanmean(f1)), micro_f1=float(2 * tp.sum() / max(2 * tp.sum() + fp.sum() + fn.sum(), 1)), exact_set=float(np.mean(exact)) if exact else None,
                concept_acc=float(np.mean(conc)) if conc else None, coverage=float(np.mean([bool(pred[i][1]) for i in V])) if V else None,
                false_accept_invalid=acc(inv), accept_ambiguous=acc(amb), n_valid=len(V), n_invalid=len(inv), n_ambiguous=len(amb), per_organ_f1=dict(zip(AXES, [None if np.isnan(x) else float(x) for x in f1])))


def boot(predA, predB, gold, ix, groups, key="macro_f1", n=1000):
    rng = np.random.default_rng(0); ug = sorted({groups[i] for i in ix}); by = {g: [i for i in ix if groups[i] == g] for g in ug}; d = []
    for _ in range(n):
        s = [i for g in rng.choice(ug, len(ug)) for i in by[g]]; a, b = metrics(predA, gold, s)[key], metrics(predB, gold, s)[key]
        if a is not None and b is not None: d.append(a - b)
    return dict(delta=metrics(predA, gold, ix)[key] - metrics(predB, gold, ix)[key], lo=float(np.percentile(d, 2.5)), hi=float(np.percentile(d, 97.5)))


def error_analysis(sysout, gold, ix):
    """where the shipped SapBERT linker goes wrong on valid queries, and what each error type would need."""
    ax = sysout["axes_of"]; c = dict(top1_right=0, gold_in_2_10=0, gold_not_in_top10=0, no_gold_concept=0, right_concept_wrong_organs=0, right_concept_below_theta=0, nonhuman_top1=0)
    by_cat = {}; nh = set(sysout["nonhuman"])
    for i in ix:
        g = gold[i]
        if g["validity"] != "valid": continue
        r = sysout["per"][i]; top = [t for t, _ in r["sapbert"]]
        if top[0] in nh: c["nonhuman_top1"] += 1
        if not g["concepts"]: c["no_gold_concept"] += 1; continue
        if top[0] in g["concepts"]:
            c["top1_right"] += 1
            if r["sapbert"][0][1] < 0.75: c["right_concept_below_theta"] += 1
            elif set(ax.get(top[0], [])) != set(g["organs"]): c["right_concept_wrong_organs"] += 1
            k = "top1_right"
        elif set(top[1:]) & set(g["concepts"]): c["gold_in_2_10"] += 1; k = "gold_in_2_10"
        else: c["gold_not_in_top10"] += 1; k = "gold_not_in_top10"
        by_cat.setdefault(g["category"], {}).setdefault(k, 0); by_cat[g["category"]][k] += 1
    return dict(counts=c, by_category=by_cat)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--refresh", action="store_true"); ap.add_argument("--gold", default=D + "gold_v0.jsonl"); ap.add_argument("--tag", default="v0"); ap.add_argument("--queries", default=D + "raw/queries_v0.json"); a = ap.parse_args()
    queries = json.load(open(a.queries)); qi = {q["qid"]: q for q in queries}
    G = {g["qid"]: g for g in map(json.loads, open(a.gold))}; gold = [dict(G[q["qid"]], category=q["category"]) for q in queries]
    groups = [q["group"] or q["qid"] for q in queries]; split = [split_of(g) for g in groups]
    sysout = system_outputs(queries, a.refresh, a.tag)
    dev = [i for i, s in enumerate(split) if s == "dev"]; test = [i for i, s in enumerate(split) if s == "test"]; allix = list(range(len(queries)))
    # thresholds on dev: maximise organ macro-F1 subject to false acceptance on invalid inputs <= 5% where reachable
    def tune(make):
        best = None
        for cand in make["grid"]:
            P = decide(sysout, gold, *make["args"](cand)); m = metrics(P[make["sys"]], gold, dev); ok = (m["false_accept_invalid"] or 0) <= 0.05
            score = (ok, m["macro_f1"])
            if best is None or score > best[0]: best = (score, cand)
        return best[1]
    th_tf = tune(dict(sys="A1", grid=np.arange(0.3, 1.0, 0.025), args=lambda c: (c, 0.6, (0.75, 0.0))))
    th_bio = tune(dict(sys="A3", grid=np.arange(0.4, 0.95, 0.025), args=lambda c: (th_tf, c, (0.75, 0.0))))
    a5 = tune(dict(sys="A5", grid=[(s, m) for s in np.arange(0.6, 0.95, 0.025) for m in (0.0, 0.01, 0.02, 0.04, 0.06, 0.08)], args=lambda c: (th_tf, th_bio, c)))
    P = decide(sysout, gold, th_tf, th_bio, a5)
    res = dict(thresholds=dict(A1=float(th_tf), A3=float(th_bio), A5=[float(a5[0]), float(a5[1])]), n=dict(dev=len(dev), test=len(test)),
               test={k: metrics(v, gold, test) for k, v in P.items()}, all={k: metrics(v, gold, allix) for k, v in P.items()}, paired_test={})
    for x, z in [("A2", "A4"), ("A5", "A4"), ("A5", "A2"), ("A4f", "A4"), ("A3", "A2"), ("A0", "A4")]:
        res["paired_test"][f"{x}-{z}:macro_f1"] = boot(P[x], P[z], gold, test, groups)
    # precision-coverage of SapBERT top-1 over all valid queries (threshold sweep; concept precision among accepted)
    pc = []
    for th in np.arange(0.5, 1.0, 0.025):
        acc = [i for i in allix if gold[i]["validity"] == "valid" and gold[i]["concepts"] and sysout["per"][i]["sapbert_h"][0][1] >= th]
        V = [i for i in allix if gold[i]["validity"] == "valid" and gold[i]["concepts"]]
        inv = [i for i in allix if gold[i]["validity"] in ("invalid", "ambiguous")]
        pc.append(dict(theta=round(float(th), 3), coverage=len(acc) / len(V), concept_precision=float(np.mean([sysout["per"][i]["sapbert_h"][0][0] in gold[i]["concepts"] for i in acc])) if acc else None,
                       hard_input_accept=float(np.mean([sysout["per"][i]["sapbert_h"][0][1] >= th for i in inv]))))
    res["sapbert_precision_coverage"] = pc
    res["recall_at_k"] = {s: {k: float(np.mean([bool(set(t for t, _ in sysout["per"][i][s][:k]) & set(gold[i]["concepts"])) for i in allix if gold[i]["validity"] == "valid" and gold[i]["concepts"]])) for k in (1, 5, 10)} for s in ("sapbert", "sapbert_h", "biolord", "tfidf")}
    res["errors_sapbert_all"] = error_analysis(sysout, gold, allix)
    res["by_category_test_macro_f1"] = {s: {c: metrics(P[s], gold, [i for i in test if gold[i]["category"] == c])["macro_f1"] for c in ("canonical", "synonym", "abbrev", "typo", "lay")} for s in ("A2", "A4", "A5")}
    os.makedirs(OUT, exist_ok=True); json.dump(res, open(OUT + f"linking_{a.tag}.json", "w"), indent=1)
    for k in ("test",):
        print(f"{'sys':5s} {'macroF1':>8s} {'microF1':>8s} {'exact':>6s} {'concept':>8s} {'cover':>6s} {'FA_inv':>7s} {'acc_amb':>7s}")
        for s, m in res[k].items():
            f = lambda x: "  -   " if x is None else f"{x:6.3f}"
            print(f"{s:5s} {m['macro_f1']:8.3f} {m['micro_f1']:8.3f} {f(m['exact_set'])} {f(m['concept_acc']):>8s} {f(m['coverage'])} {f(m['false_accept_invalid']):>7s} {f(m['accept_ambiguous']):>7s}")
    for k, v in res["paired_test"].items(): print(f"{k:22s} {v['delta']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}]")
    print("thresholds", res["thresholds"]); print("recall@k", json.dumps(res["recall_at_k"])); print("errors", json.dumps(res["errors_sapbert_all"]))


if __name__ == "__main__":
    main()
