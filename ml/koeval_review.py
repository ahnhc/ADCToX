"""Review of the Korean evaluation questions (E1 in ml/docs/data_inventory.md): would a Korean speaker recognise each one as the
intended disease, and is it the kind of input its category says (a real typo, a real abbreviation, everyday words)?

    ADC_RESEARCH_MODE=1 python ml/koeval_review.py            # batches -> data/curated/judge2/koeval_review/batches/
    ADC_RESEARCH_MODE=1 python ml/koeval_review.py --merge    # decisions, report; rewrites data/curated/judge2/gen/koeval_*.jsonl

Why: the Korean questions are LLM translations of the English gold queries (ml/judge2_batches.py), never checked by a person.
Some are cut-off words labelled abbreviations ("편두"), correct spellings labelled typos, or words whose usual meaning is another
thing ("주사"). The rule and the decision are fixed here before any reviewer runs, and reviewers never see a model output or a
score, so the questions are not chosen by how a model does on them.

Reviewers see each question with its English original, category, intended disease (MONDO name) and the other questions of the
same disease. Two reviewers work independently (Claude Haiku 5.5). Each batch carries CONTROLS planted errors (the Korean text of
another disease put under this one); a reviewer's flags count only when it catches at least CONTROL_MIN of them.
A question changes only when both counted reviewers flag it; the adjudicator then writes the final text from their proposals.
English questions, categories and gold labels never change. Every change is kept with both reasons in decisions.jsonl.
"""
import collections, glob, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

R = P.REPO + "data/curated/judge2/koeval_review/"; B = R + "batches/"; OUT = R + "out/"; GEN = P.REPO + "data/curated/judge2/gen/"
BATCH, CONTROLS, CONTROL_MIN, SEED = 30, 3, 2 / 3, 2041
REASONS = ["unrecognisable", "other_meaning", "wrong_disease", "not_category", "unnatural"]
# Final check of the adjudicated texts (Claude Opus 5.5, 2026-10-18), against the same rules, for the finals that break them. Rule:
# an abbreviation question with no Korean abbreviation in real use takes the English question's abbreviation, as Korean charts
# write it; that also keeps it pointing at the gold concept when the abbreviation is ambiguous (RAD, hydro, tinn, mets).
OVERRIDES = {
    "q0283": ("rosac", "'로사' is not used; no Korean abbreviation for rosacea"),
    "q0203": ("sz d/o", "'뇌전' is a cut word"),
    "q0108": ("RAD", "'RP' is retinitis pigmentosa; the original was right"),
    "q0408": ("메니에르", "'MD' alone is ambiguous; '메니에르' is the Korean short form"),
    "q0163": ("hydro", "the gold concept is hydrocephalus; '수신'/'HCP' do not keep the question"),
    "q0098": ("peric eff", "'PEff' is not used"),
    "q0418": ("tinn", "'귀울' is not used, and the gold concept is tinea infection, not tinnitus"),
    "q0223": ("migr", "'MIG' is not used"),
    "q0540": ("mets", "the question is ambiguous on purpose; '대사 쪽 문제' names one reading"),
}


def questions():
    import eval_a4 as E4
    from build_linking_pools import read_obo
    Q, gold, groups, ko = E4.gold(); T = read_obo()
    if os.path.exists(R + "original_koeval.jsonl"):                       # always the translation as first made, so merging twice is the same
        ko = \
             {json.loads(l)["qid"]: json.loads(l)["query_ko"] for l in open(R + "original_koeval.jsonl", encoding="utf-8") if l.strip()}
    rows = []
    for q, g, grp in zip(Q, gold, groups):
        b = g.get("best") or (g.get("concepts") or [None])[0]
        rows.append(dict(qid=q["qid"], group=grp, category=q["category"], en=q["query"], ko=ko.get(q["qid"]), validity=g.get("validity"),
                         disease=(T[b]["name"] if b in T else None)))
    return rows


def batches():
    rows = questions(); rng = random.Random(SEED); os.makedirs(B, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(B + "kr_*.json"): os.remove(f)
    by = collections.defaultdict(list)
    for r in rows: by[r["group"]].append(r)
    groups = list(by); rng.shuffle(groups); cur, out = [], []
    for g in groups:
        cur += by[g]
        if len(cur) >= BATCH: out.append(cur); cur = []
    if cur: out.append(cur)
    man = {}
    for n, part in enumerate(out):
        part = [dict(x) for x in part]; ctl = {}
        valid = [x for x in part if x["validity"] == "valid" and x["disease"]]
        others = [x for x in rows if x["group"] not in {y["group"] for y in part} and x["validity"] == "valid" and x["category"] in ("canonical", "lay")]
        for k in range(CONTROLS):
            a = rng.choice(valid); o = rng.choice(others)
            c = dict(a, qid=f"ctl{n:02d}_{k}", ko=o["ko"]); part.insert(rng.randrange(len(part) + 1), c); ctl[c["qid"]] = "fix"
        for x in part: x.pop("validity", None)
        json.dump(part, open(B + f"kr_{n:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0); man[f"kr_{n:02d}"] = ctl
    json.dump(man, open(B + "manifest.json", "w"), indent=1); print(dict(questions=len(rows), batches=len(out)))


def read(f):
    out = {}
    if not os.path.exists(f): return out
    for l in open(f, encoding="utf-8"):
        try: x = json.loads(l); out[str(x["qid"])] = x
        except (ValueError, KeyError): pass
    return out


def merge():
    man = json.load(open(B + "manifest.json")); rows = {r["qid"]: r for r in questions()}; dec, rep = [], {}
    for n, ctl in man.items():
        rv = {k: read(OUT + f"{n}_{k}.jsonl") for k in ("a", "b")}; adj = read(OUT + f"{n}_adj.jsonl"); counted = {}
        for k, v in rv.items():
            caught = sum(v.get(c, {}).get("verdict") == "fix" for c in ctl) / len(ctl); counted[k] = caught >= CONTROL_MIN
            rep[f"{n}_{k}"] = dict(controls=round(caught, 3), counted=counted[k], answered=sum(1 for q in v if not q.startswith("ctl")))
        for q, x in rows.items():
            if q not in {y["qid"] for y in json.load(open(B + f"{n}.json", encoding="utf-8"))}: continue
            fa, fb = (counted[k] and rv[k].get(q, {}).get("verdict") == "fix" for k in ("a", "b"))
            if fa and fb and adj.get(q, {}).get("final") and adj[q]["final"].strip() != (x["ko"] or ""):
                dec.append(dict(qid=q, category=x["category"], en=x["en"], disease=x["disease"], old=x["ko"], new=adj[q]["final"].strip(),
                                reasons=[rv["a"][q].get("reason"), rv["b"][q].get("reason")], proposals=[rv["a"][q].get("proposal"), rv["b"][q].get("proposal")]))
    for d in dec:
        if d["qid"] in OVERRIDES: d["adjudicated"] = d["new"]; d["new"], d["override"] = OVERRIDES[d["qid"]]
    dec = [d for d in dec if d["new"] != d["old"]]
    keep = R + "original_koeval.jsonl"
    if not os.path.exists(keep):                                          # the translation as first made, kept once
        open(keep, "w", encoding="utf-8").write("".join(open(f, encoding="utf-8").read() for f in sorted(glob.glob(GEN + "koeval_*.jsonl"))))
    orig = [json.loads(l) for l in open(keep, encoding="utf-8") if l.strip()]; new = {d["qid"]: d["new"] for d in dec}
    files = sorted(glob.glob(GEN + "koeval_*.jsonl")); k = (len(orig) + len(files) - 1) // len(files)
    for i, f in enumerate(files):
        open(f, "w", encoding="utf-8").write("".join(json.dumps(dict(x, query_ko=new.get(x["qid"], x["query_ko"])), ensure_ascii=False) + "\n" for x in orig[i * k:(i + 1) * k]))
    open(R + "decisions.jsonl", "w", encoding="utf-8").write("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dec))
    stats = dict(questions=len(orig), changed=len(dec), by_category=dict(collections.Counter(d["category"] for d in dec)), overridden=sum("override" in d for d in dec),
                 by_reason=dict(collections.Counter(r for d in dec for r in d["reasons"])), reviewers_counted=sum(v["counted"] for v in rep.values()),
                 reviewers=len(rep), per_reviewer=rep)
    json.dump(stats, open(R + "report.json", "w"), indent=1, ensure_ascii=False); print(json.dumps({k: v for k, v in stats.items() if k != "per_reviewer"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    merge() if "--merge" in sys.argv else batches()
