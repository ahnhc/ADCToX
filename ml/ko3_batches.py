"""Korean expressions, third set (ko3; D4 and D5 in ml/docs/data_inventory.md): short everyday words, abbreviations and
Korean-English mixes as Korean charts write them, and everyday words for the organs with few. Written by Claude Haiku 5.5 and
checked by a second Haiku pass with planted errors, as ko2 (ml/ko_expr_batches.py).

    ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache> python ml/ko3_batches.py            # concepts and generation batches
    ADC_RESEARCH_MODE=1 python ml/ko3_batches.py --verify                         # verification batches from the outputs
    ADC_RESEARCH_MODE=1 python ml/ko3_batches.py --merge                          # -> data/curated/judge2/gen/ko3_*.jsonl

Why (S1 dev, data_inventory.md): Korean-script abbreviations were 33 items in all; Korean-English mixes ("DM 2형", "CKD 4기")
almost none, though Korean charts use them all the time; short everyday words (뾰루지, 무좀) are the Korean inputs the judge
rejects most; Korean everyday words cover few otologic, hepatic, renal and pulmonary concepts.
Concepts: (a) the ko2 concepts (the most-coded Korean concepts): short, abbrev and mixed lines; (b) new concepts from the same
KCD-ranked pool for each organ in FILL until it has FILL_TO concepts with Korean everyday words: everyday and spoken lines too.
Gold concepts and their relatives are left out. Verification and its control rule are those of ko2.
"""
import collections, glob, json, os, random, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

R = P.REPO + "data/curated/judge2/"; B = R + "batches/"; OUT = R + "out_ko3/"
BATCH, SEED, CONTROL_MIN, FILL_TO = 20, 2061, 0.75, 400
FILL = ["otologic", "hepatic", "renal", "pulmonary", "dermatologic"]
KINDS = ("short", "abbrev", "mixed", "everyday", "spoken")
HANGUL = re.compile("[가-힣]")


def batches():
    import ko_expr_batches as KE, data_inventory as DI
    old = [x for f in sorted(glob.glob(B + "ko2_[0-9]*.json")) for x in json.load(open(f, encoding="utf-8"))]
    have = {x["id"] for x in old}
    its, labels = DI.items(); lay = collections.defaultdict(set)
    for x in its:
        if x[4] == "lay" and DI.lang(x[0]) == "ko" and x[1] in labels:
            for a in labels[x[1]]: lay[a].add(x[1])
    KE.PER_ORGAN = 10 ** 9; pool, stats = KE.concepts()                      # every KCD-linked concept, most-coded first
    need = {a: max(0, FILL_TO - len(lay[a])) for a in FILL}; new = []
    for r in pool:
        if r["id"] in have: continue
        hit = [a for a in r["organs"] if need.get(a, 0) > 0]
        if not hit: continue
        new.append(dict(r, new=True))
        for a in hit: need[a] -= 1
    if any(need.values()):                                                   # KCD pool used up: other labelled concepts with a Korean name,
        import linking_models as LM                                          # the most synonyms first (a proxy for how common)
        from build_linking_pools import read_obo
        from sample_label_concepts import line
        T = read_obo(); held = LM.gold_held(T); took = have | {r["id"] for r in new}
        mk = {x["id"]: x for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")) if x["conf"] != "low"}
        rest = sorted((t for t in mk if t in labels and t in T and t not in held and t not in took and not T[t]["name"].startswith("obsolete")),
                      key=lambda t: (-len(T[t]["syn"]), t))
        for t in rest:
            hit = [a for a in labels[t] if need.get(a, 0) > 0]
            if not hit: continue
            new.append(dict(id=t, concept=line(T, t), ko=mk[t]["ko"], alt=mk[t]["alt"][:2], organs=sorted(labels[t], key=DI.AXES.index), kcd_links=0, new=True))
            for a in hit: need[a] -= 1
    rows = [dict(x, new=False) for x in old] + new; rng = random.Random(SEED); rng.shuffle(rows)
    os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(B + "ko3_*.json"): os.remove(f)
    n = 0
    for k in range(0, len(rows), BATCH):
        json.dump(rows[k:k + BATCH], open(B + f"ko3_{n:03d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0); n += 1
    st = dict(ko2_concepts=len(old), new_concepts=len(new), still_short=need, batches=n, lay_before={a: len(lay[a]) for a in FILL})
    json.dump(st, open(B + "ko3_manifest.json", "w"), indent=1); print(json.dumps(st, indent=1))


def outputs(prefix):
    rows = []
    files = [OUT + f"{prefix}.jsonl"] if os.path.exists(OUT + f"{prefix}.jsonl") else sorted(glob.glob(OUT + f"{prefix}_*.jsonl"))
    for f in files:
        for l in open(f, encoding="utf-8"):
            l = l.strip()
            if not l: continue
            try: rows.append(dict(json.loads(l), _batch=os.path.basename(f)[:-6]))
            except ValueError: pass
    return rows


def clean(rows):
    """keep expressions of a known concept and kind; Korean in every kind but abbrev; no copies of the concept's Korean names."""
    import tuning_ledger as TL
    con = {x["id"]: x for f in glob.glob(B + "ko3_[0-9]*.json") for x in json.load(open(f, encoding="utf-8"))}
    mk = {x["id"]: x for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8"))}
    seen, out = set(), []
    for r in rows:
        t, txt, kind = r.get("id"), str(r.get("text", "")).strip(), r.get("kind")
        if t not in con or kind not in KINDS or not txt or len(txt) > 60: continue
        if kind in ("everyday", "spoken") and not con[t].get("new"): continue
        if kind != "abbrev" and not HANGUL.search(txt): continue
        names = {TL.norm(n) for n in [con[t]["ko"]] + con[t].get("alt", []) + ([mk[t]["ko"]] + mk[t]["alt"] if t in mk else [])}
        if TL.norm(txt) in names or (t, txt) in seen: continue
        seen.add((t, txt)); out.append(dict(id=t, text=txt, kind=kind))
    return out, con


def verify_batches():
    rows, con = clean(outputs("ko3")); rng = random.Random(SEED + 1); rng.shuffle(rows); man = {}
    for f in glob.glob(B + "ko3v_*.json"): os.remove(f)
    k = (len(rows) + 39) // 40
    for n, s in enumerate(range(0, len(rows), k)):
        part = [dict(i=s + j, id=r["id"], concept=con[r["id"]]["concept"], ko=con[r["id"]]["ko"], text=r["text"], kind=r["kind"]) for j, r in enumerate(rows[s:s + k])]
        ctl = {}
        for j in range(max(5, len(part) * 6 // 100)):
            a, b = rng.sample(range(len(part)), 2)
            if part[a]["id"] == part[b]["id"]: continue
            c = dict(part[a], i=-(1000 * n + j + 1), text=part[b]["text"], kind=part[b]["kind"]); part.insert(rng.randrange(len(part) + 1), c); ctl[str(c["i"])] = "drop"
        json.dump(part, open(B + f"ko3v_{n:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0); man[f"ko3v_{n:02d}"] = ctl
    json.dump(dict(rows=rows, controls=man), open(B + "ko3v_manifest.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(dict(expressions=len(rows), batches=len(man), kinds=dict(collections.Counter(r["kind"] for r in rows))))


def merge():
    m = json.load(open(B + "ko3v_manifest.json", encoding="utf-8")); rows = m["rows"]; drop, rep = set(), {}
    for n, ctl in m["controls"].items():
        got = {str(r.get("i")): r.get("verdict") for r in outputs(n)}
        caught = np.mean([got.get(c) == "drop" for c in ctl]) if ctl else 0.0; ok = caught >= CONTROL_MIN
        rep[n] = dict(controls=round(float(caught), 3), passed=bool(ok), answered=sum(1 for c in got if not c.startswith("-")))
        if ok: drop |= {int(i) for i, v in got.items() if v == "drop" and not i.startswith("-")}
        else: drop |= {x["i"] for x in json.load(open(B + f"{n}.json", encoding="utf-8")) if x["i"] >= 0}   # a failed batch: none of its lines kept
    keep = [r for i, r in enumerate(rows) if i not in drop]
    for f in glob.glob(R + "gen/ko3_*.jsonl"): os.remove(f)
    for k in range(0, len(keep), 2000):
        open(R + f"gen/ko3_{k // 2000:02d}.jsonl", "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in keep[k:k + 2000]))
    stats = dict(generated=len(rows), dropped=len(drop), kept=len(keep), kinds=dict(collections.Counter(x["kind"] for x in keep)),
                 concepts=len({x["id"] for x in keep}), batches_passed=sum(r["passed"] for r in rep.values()), batches=len(rep), per_batch=rep)
    json.dump(stats, open(R + "gen/ko3_report.json", "w"), indent=1); print(json.dumps({k: v for k, v in stats.items() if k != "per_batch"}, indent=1))


if __name__ == "__main__":
    if "--verify" in sys.argv: verify_batches()
    elif "--merge" in sys.argv: merge()
    else: batches()
