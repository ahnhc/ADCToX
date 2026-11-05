"""Second dev set: the 10,066 accepted query variants (data/curated/query_variants/accepted.jsonl), scored on one model bundle.

    python ml/eval_query_variants.py --bundle <folder with ScratchJudge/> [--json out.json]
    python ml/eval_query_variants.py                                    # the active model bundle

Each row is a respelling, typo, lay phrase, shorthand or abbreviation of one concept. The gold organs are that concept's organs in
the bundle's own concepts.json, so the score says whether a messy phrase reaches the same organs as the concept's standard name.
It does not say whether those organs are clinically right.

Read it as easy-biased. Every concept here has label organs in the bundle's table, which the judge was trained on, and that table is the
gold. The phrasings were written and checked by language models, and a concept has about 1.3 of them. Use the score to compare phrasing
types and bundles with each other. Do not quote it as accuracy on unseen diseases: that is the gold_v0 dev score (ml/bench_judge.py).
The 95% interval resamples concepts, not phrasings.
"""
import argparse, collections, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ACCEPTED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "query_variants", "accepted.jsonl")
TYPES = ("variant", "typo", "lay", "shorthand", "abbrev")
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]


def load_items(path=ACCEPTED):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def _macro(tp, fp, fn):
    s = 2 * tp + fp + fn
    return float(np.nanmean(np.where(s > 0, 2 * tp / np.maximum(s, 1), np.nan)))


def score(items, rows, concepts, n_boot=1000, seed=0):
    """items: accepted.jsonl rows; rows: scratch_runtime.judge output per item; concepts: the bundle's concepts.json.
    -> {type or 'all': n, concepts, macro_f1, ci95 (resampling concepts), reject, exact}."""
    per = {t: collections.defaultdict(lambda: np.zeros(39)) for t in TYPES}
    cnt = {t: collections.Counter() for t in TYPES}
    for a, r in zip(items, rows):
        g = set(concepts.get(a["id"], ["", [], ""])[1]); p = set(r["organs"]); v = np.zeros(39)
        for k, o in enumerate(AXES): v[k] = o in g and o in p; v[13 + k] = o in p and o not in g; v[26 + k] = o in g and o not in p
        per[a["category"]][a["id"]] += v
        c = cnt[a["category"]]; c["n"] += 1; c["reject"] += not r["ok"]; c["exact"] += g == p
    rng = np.random.default_rng(seed); out = {}
    for name, ts in [(t, [t]) for t in TYPES] + [("all", list(TYPES))]:
        by = collections.defaultdict(lambda: np.zeros(39))
        for t in ts:
            for cid, v in per[t].items(): by[(t if len(ts) == 1 else "all", cid)] += v
        M = np.array(list(by.values())); n = sum(cnt[t]["n"] for t in ts)
        if not n: continue
        tot = M.sum(0); stat = lambda x: _macro(x[:13], x[13:26], x[26:])
        boots = [stat(np.bincount(rng.integers(0, len(M), len(M)), minlength=len(M)) @ M) for _ in range(n_boot)]
        out[name] = dict(n=n, concepts=len(M), macro_f1=stat(tot), ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                         reject=sum(cnt[t]["reject"] for t in ts) / n, exact=sum(cnt[t]["exact"] for t in ts) / n)
    return out


def run(bundle=None, items=None):
    import scratch_runtime as SR
    path = os.path.join(bundle, "ScratchJudge") if bundle and not os.path.exists(os.path.join(bundle, "judge.json")) else bundle
    path = path or SR.folder()
    items = items or load_items(); rows = SR.judge([a["query"] for a in items], path)
    concepts = json.load(open(os.path.join(path, "concepts.json"), encoding="utf-8"))
    res = score(items, rows, concepts); res["_held_in_table"] = sum(concepts.get(a["id"], ["", [], ""])[2] == "label" for a in items) / len(items)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--bundle", default=None); ap.add_argument("--json", default=None); a = ap.parse_args()
    res = run(a.bundle)
    print("easy-biased second dev set: compare phrasing types and bundles with each other, not as accuracy on unseen diseases")
    print(f"{'type':10} {'n':>6} {'concepts':>8} {'macro-F1':>9} {'95% (concepts)':>16} {'rejected':>9} {'exact set':>10}")
    for k in list(TYPES) + ["all"]:
        if k in res: r = res[k]; print(f"{k:10} {r['n']:6d} {r['concepts']:8d} {r['macro_f1']:9.3f} [{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}] {r['reject']:9.3f} {r['exact']:10.3f}")
    print(f"phrasings whose concept has v5.1 label organs in the bundle: {res['_held_in_table']:.3f}")
    if a.json: json.dump(res, open(a.json, "w", encoding="utf-8"), indent=1)
