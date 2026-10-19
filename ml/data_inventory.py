"""What the judge's training data holds and lacks, by language and input type, next to how the judge scores on the same types.

    ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache copy> python ml/data_inventory.py [--runs s1s7,s1s8,s1s9]
    -> ml/results/data_inventory.json, printed tables (the reading is in ml/docs/data_inventory.md)

Items are rebuilt the way ml/gemma_judge2.py builds them (same sources, gold concepts and their relatives left out, same dedupe),
without the GPU: KCD names are counted, not embedded. Each item gets
  lang  ko (Hangul, no Latin letters), mixed (Hangul and Latin), en (Latin, no Hangul), other
  type  the gold query categories (canonical, synonym, abbrev, typo, lay) where the source says which, plus symptom, junk, kcd
Scores: the per-category and per-organ dev F1 of the bench runs (ml/results/benchmarks/bench_single_<run>.json), seed mean.
"""
import argparse, collections, glob, json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P, linking_models as LM, suggest as SG
from build_linking_pools import read_obo

AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
G2 = P.REPO + "data/curated/judge2/gen/"; HAN = re.compile("[가-힣ㄱ-ㅎㅏ-ㅣ]"); LAT = re.compile("[A-Za-z]")
CATS = ["canonical", "synonym", "abbrev", "typo", "lay"]
KIND = {"formal": "canonical", "short": "abbrev", "everyday": "lay", "spoken": "lay", "typo": "typo", "abbrev": "abbrev"}


def lang(s):
    h, l = bool(HAN.search(s)), bool(LAT.search(s))
    return "mixed" if h and l else "ko" if h else "en" if l else "other"


def jl(pattern):
    out = []
    for f in sorted(glob.glob(G2 + pattern)):
        for line in open(f, encoding="utf-8"):
            try: out.append(json.loads(line))
            except ValueError: pass
    return out


def items():
    """[(text, concept or None, valid, src, type)] as gemma_judge2 builds them (before its leak drop)."""
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels(); prof = SG.profiles(); pid = {p["id"] for p in prof}
    out = []
    def add(text, t, src, typ, valid=1.0):
        if text and str(text).strip(): out.append((str(text).strip(), t if (t is not None and t not in held) else None, valid, src, typ))
    for t in labels:
        if t not in held and t in T:
            add(T[t]["name"], t, "mondo_names", "canonical")
            for q in T[t]["syn"][:5]: add(q, t, "mondo_names", "abbrev" if (len(q) <= 6 and q.upper() == q) else "synonym")
    for f in sorted(glob.glob(P.REPO + "data/curated/train_queries/review/review2_*.jsonl")):
        for x in map(json.loads, open(f)):
            if x.get("validity") == "valid" and x.get("match") is True and x["concept"] in labels and x["concept"] not in held: add(x["query"], x["concept"], "train_queries", x["category"])
    ext = P.REPO + "data/curated/external/mentions_mondo.jsonl"
    if os.path.exists(ext):
        for r in map(json.loads, open(ext)):
            if r["split"] == "train" and len(r["mondo"]) == 1 and r["mondo"][0] in labels and r["mondo"][0] not in held: add(r["mention"], r["mondo"][0], "external", "mention")
    for p in prof:
        for k in p.get("ko", []): add(k, p["id"], "profiles", "canonical")
        for k in p.get("ko_lay", []): add(k, p["id"], "profiles", "lay")
        for k in p.get("en", []): add(k, p["id"], "profiles", "synonym")
        for k in p.get("abbr", []): add(k, p["id"], "profiles", "abbrev")
        for k in p.get("symptoms_ko", [])[:3] + p.get("symptoms_en", [])[:3]: add(k, p["id"], "profiles", "symptom")
    Z = np.load(os.path.join(P.CACHE, "mondo_index.npz"), allow_pickle=True)
    for k in [str(x) for x in Z["ko_keys"]][:20000]: add(k, None, "kcd", "kcd")
    for x in jl("ko_*.jsonl"):
        if x.get("id") in T: add(x.get("text"), x["id"], "gen_ko", KIND.get(x.get("kind"), x.get("kind")))
    for x in jl("sym_*.jsonl"):
        if x.get("id") in pid: add(x.get("text"), x["id"], "gen_sym", "symptom")
    for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")):
        if x["conf"] == "low" or x["id"] not in T: continue
        add(x["ko"], x["id"], "mondo_ko", "canonical")
        for k in x["alt"]: add(k, x["id"], "mondo_ko", "synonym")
    for x in jl("ko2_*.jsonl"):
        if x.get("id") in T: add(x.get("text"), x["id"], "ko2", KIND.get(x.get("kind"), x.get("kind")))
    for x in jl("junk_*.jsonl"): add(x.get("text"), None, "junk", "junk", 0.0)
    out = list({(x[0], x[1], x[2]): x for x in out}.values())
    return out, labels


def scores(runs):
    """seed-mean dev F1 per language: by gold query category and per organ."""
    S = {"by_category": {}, "per_organ": {}, "macro": {}}
    import bench_judge as B, eval_linking as EL
    Q, gold, groups, ko, SE = B.questions(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == "dev"]
    for lg in ("en", "ko"):
        cat, org, mac = collections.defaultdict(list), collections.defaultdict(list), []
        for r in runs:
            per = json.load(open(B.OUT + f"bench_{r}.json"))["per"][lg]; jx = [i for i in ix if per[i] is not None]
            m = EL.metrics([((x or {}).get("concept"), (x or {}).get("organs", [])) for x in per], gold, jx); mac.append(m["macro_f1"])
            sc = json.load(open(B.OUT + f"bench_{r}.json"))["scores"]["dev"][lg]["by_category"]
            for c, v in sc.items(): cat[c].append(v)
            for a, v in m["per_organ_f1"].items():
                if v is not None: org[a].append(v)
        S["macro"][lg] = round(float(np.mean(mac)), 3)
        S["by_category"][lg] = {c: round(float(np.mean(v)), 3) for c, v in cat.items()}
        S["per_organ"][lg] = {a: round(float(np.mean(v)), 3) for a, v in org.items()}
    # what the Korean questions are made of
    kt = lambda i: ko.get(Q[i]["qid"]) or Q[i]["query"]
    S["ko_questions"] = dict(collections.Counter(lang(kt(i)) for i in ix))
    S["ko_questions_by_category"] = {c: dict(collections.Counter(lang(kt(i)) for i in ix if Q[i]["category"] == c)) for c in CATS}
    return S


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", default="s1s7,s1s8,s1s9"); a = ap.parse_args()
    its, labels = items(); real = [x for x in its if x[3] != "junk"]
    by = collections.Counter((lang(x[0]), x[4]) for x in its)
    src = collections.Counter((x[3], lang(x[0])) for x in its)
    # concept coverage: labelled training concepts that have at least one text of a language and type
    lab = {x[1] for x in real if x[1] in labels}
    cov = collections.defaultdict(set)
    for x in real:
        if x[1] in labels: cov[(lang(x[0]), x[4])].add(x[1]); cov[(lang(x[0]), "any")].add(x[1])
    per_organ = {}
    for ax in AXES:
        cs = {t for t in lab if ax in labels[t]}
        per_organ[ax] = dict(concepts=len(cs), **{f"{lg}_{ty}": len(cs & cov[(lg, ty)]) for lg in ("en", "ko") for ty in ("any", "canonical", "lay", "typo", "abbrev")})
    res = dict(items=len(its), by_lang_type={f"{l}|{t}": n for (l, t), n in sorted(by.items())}, by_source_lang={f"{s}|{l}": n for (s, l), n in sorted(src.items())},
               labelled_concepts=len(lab), coverage={f"{l}|{t}": len(v) for (l, t), v in sorted(cov.items())}, per_organ=per_organ,
               junk_lang=dict(collections.Counter(lang(x[0]) for x in its if x[3] == "junk")),
               scores=scores([f"single_{r}" for r in a.runs.split(",")]))
    os.makedirs(P.REPO + "ml/results", exist_ok=True)
    json.dump(res, open(P.REPO + "ml/results/data_inventory.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
