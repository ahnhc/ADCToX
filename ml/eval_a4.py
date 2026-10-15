"""The shipped pipeline (A4: recommend.resolve, registry -> MONDO -> judge) on the gold queries in English and in Korean.

    CUDA_VISIBLE_DEVICES=2 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<model folder> python ml/eval_a4.py --tag judge1 [--test]
    python ml/eval_a4.py --compare judge2 judge1 [--test]

Korean queries: data/curated/judge2/gen/koeval_*.jsonl, written by Claude Sonnet from the English gold queries (text and
category only; labels stay with the qid). Evaluation only: never a training text. Per-query organs are saved, so two runs
(two model folders) compare with the paired bootstrap of ml/eval_linking.boot. Dev unless --test.
-> ml/results/benchmarks/a4_<tag>.json
"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P, eval_linking as EL

OUT = P.REPO + "ml/results/benchmarks/"


def gold():
    Q = json.load(open(EL.D + "raw/queries_v0.json")); G = {x["qid"]: x for x in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    ko = {}
    for f in sorted(glob.glob(P.REPO + "data/curated/judge2/gen/koeval_*.jsonl")):
        for line in open(f, encoding="utf-8"):
            try: x = json.loads(line); ko[x["qid"]] = x["query_ko"]
            except (ValueError, KeyError): pass
    return Q, [dict(G[q["qid"]], category=q["category"]) for q in Q], [q["group"] or q["qid"] for q in Q], ko


def run(tag):
    os.environ.setdefault("ADC_RESEARCH_MODE", "1")
    import recommend as RC
    Q, _, _, ko = gold(); out = {}
    for lang, texts in (("en", [q["query"] for q in Q]), ("ko", [ko.get(q["qid"]) for q in Q])):
        rows = []
        for q in texts:
            if q is None: rows.append(None); continue
            RC.FALLBACK = {}; _, _, _, notes, pc = RC.resolve([q])
            rows.append(dict(how=dict(notes).get(q, ""), organs=sorted(set().union(*[o for c, o, _ in pc if c == q]) if pc else [])))
        out[lang] = rows
    json.dump(dict(tag=tag, model=P.CACHE, per=out), open(OUT + f"a4_{tag}.json", "w"), ensure_ascii=False)
    return out


def score(per, split):
    Q, gold_, groups, _ = gold(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == split]; res = {}
    for lang, rows in per.items():
        jx = [i for i in ix if rows[i] is not None]; pred = [(None, r["organs"] if r else []) for r in rows]
        m = EL.metrics(pred, gold_, jx)
        res[lang] = dict(n=len(jx), **{k: m[k] for k in ("macro_f1", "exact_set", "coverage", "false_accept_invalid", "accept_ambiguous")},
                         by_category={c: EL.metrics(pred, gold_, [i for i in jx if gold_[i]["category"] == c])["macro_f1"] for c in ("canonical", "synonym", "abbrev", "typo", "lay")})
    return res


def main():
    split = "test" if "--test" in sys.argv else "dev"
    if "--compare" in sys.argv:
        a, b = sys.argv[sys.argv.index("--compare") + 1: sys.argv.index("--compare") + 3]
        A, B = json.load(open(OUT + f"a4_{a}.json"))["per"], json.load(open(OUT + f"a4_{b}.json"))["per"]
        Q, gold_, groups, _ = gold(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == split]; res = {}
        for lang in A:
            jx = [i for i in ix if A[lang][i] is not None and B[lang][i] is not None]
            pa = [(None, r["organs"] if r else []) for r in A[lang]]; pb = [(None, r["organs"] if r else []) for r in B[lang]]
            res[lang] = dict(boot=EL.boot(pa, pb, gold_, jx, groups), a=score({lang: A[lang]}, split)[lang], b=score({lang: B[lang]}, split)[lang])
        print(json.dumps(res, indent=1, ensure_ascii=False)); return
    tag = sys.argv[sys.argv.index("--tag") + 1]; per = run(tag)
    print(json.dumps(score(per, split), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
