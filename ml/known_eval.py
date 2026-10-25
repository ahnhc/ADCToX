"""A second benchmark: diseases the judge was trained on, typed in ways it never saw. The gold benchmark (ml/bench_judge.py)
holds its diseases and their relatives out of training, so it measures only how a judge guesses the organs of a disease it does
not know; in the app nearly every disease is in the organ table, and finding the right disease is what counts there.

    ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache> python ml/known_eval.py --batches       # Korean generation batches (Haiku)
    ADC_RESEARCH_MODE=1 python ml/known_eval.py --verify | --merge                    # verification batches; the Korean set
    ADC_RESEARCH_MODE=1 python ml/known_eval.py --english                             # the English set (licensed corpora: local)
    CUDA_VISIBLE_DEVICES=1 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<model folder> python ml/known_eval.py --run single --name s2ds7
        [SCRATCH_DIR=... for --run scratch]  -> ml/results/benchmarks/known_<name>.json

Questions (all of labelled concepts that are not gold concepts or relatives; organ answer = the organ table, the app's answer):
  en   test-split mentions of NCBI Disease, BC5CDR, MedMentions st21pv and COMETA with exactly one MONDO concept
       (data/curated/external/mentions_mondo.jsonl; training reads only the train split), at most PER_CONCEPT per concept
  ko   Korean expressions written for this set by Claude Haiku 5.5 (everyday, typo, mixed Korean-English or abbreviation,
       spoken) for PER_ORGAN concepts of each organ from the KCD-ranked pool, checked by a second Haiku pass with planted errors
       (as ko2); data/curated/known_eval/ko.jsonl
  Every question whose normalised text is a training text of any source, or a gold question, is dropped, so each is new phrasing.
Split: dev and test by concept (hash), as the gold set splits by query group. Look at test once, at the end.
Scores: organ macro F1 (eval_linking.metrics), concept accuracy, per question kind.
"""
import argparse, collections, glob, hashlib, json, os, random, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

R = P.REPO + "data/curated/known_eval/"; B = R + "batches/"; OUT = R + "out/"
EN = P.REPO + "data/curated/external/known_eval_en.jsonl"
PER_ORGAN, PER_CONCEPT, BATCH, SEED, CONTROL_MIN = 30, 3, 20, 2071, 0.75
KINDS = ("everyday", "typo", "mixed", "spoken")


def split_of(t): return "dev" if int(hashlib.sha256(t.encode()).hexdigest(), 16) % 2 == 0 else "test"


def training_texts():
    """normalised text of every training item of every source (judge_data with nothing left out) and every gold question."""
    import judge_data as JD, tuning_ledger as TL
    its, _, _ = JD.items(); return {TL.norm(x[0]) for x in its} | set(TL.eval_concepts())


def batches():
    import ko_expr_batches as KE
    KE.PER_ORGAN = 10 ** 9; pool, _ = KE.concepts(); rng = random.Random(SEED); rng.shuffle(pool)
    per, pick = collections.Counter(), []
    for r in sorted(pool, key=lambda r: -r["kcd_links"]):
        need = [a for a in r["organs"] if per[a] < PER_ORGAN]
        if need: pick.append(dict(id=r["id"], concept=r["concept"], ko=r["ko"])); per.update(r["organs"])
    rng.shuffle(pick); os.makedirs(B, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(B + "ke_*.json"): os.remove(f)
    for n, k in enumerate(range(0, len(pick), BATCH)): json.dump(pick[k:k + BATCH], open(B + f"ke_{n:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(dict(concepts=len(pick), per_organ=dict(per), batches=(len(pick) + BATCH - 1) // BATCH), open(B + "ke_manifest.json", "w"), indent=1)
    print(len(pick), dict(per))


def outputs(prefix):
    rows = []
    for f in ([OUT + f"{prefix}.jsonl"] if os.path.exists(OUT + f"{prefix}.jsonl") else sorted(glob.glob(OUT + f"{prefix}_*.jsonl"))):
        for l in open(f, encoding="utf-8"):
            try: rows.append(json.loads(l))
            except ValueError: pass
    return rows


def verify_batches():
    import tuning_ledger as TL
    con = {x["id"]: x for f in glob.glob(B + "ke_[0-9]*.json") for x in json.load(open(f, encoding="utf-8"))}; seen = training_texts(); rows, dup = [], set()
    for r in outputs("ke"):
        t, txt, kind = r.get("id"), str(r.get("text", "")).strip(), r.get("kind")
        if t in con and kind in KINDS and txt and len(txt) <= 60 and TL.norm(txt) not in seen and (t, TL.norm(txt)) not in dup:
            dup.add((t, TL.norm(txt))); rows.append(dict(id=t, text=txt, kind=kind))
    rng = random.Random(SEED + 1); rng.shuffle(rows); man = {}; k = (len(rows) + 9) // 10
    for f in glob.glob(B + "kev_*.json"): os.remove(f)
    for n, s in enumerate(range(0, len(rows), k)):
        part = [dict(i=s + j, id=r["id"], concept=con[r["id"]]["concept"], ko=con[r["id"]]["ko"], text=r["text"], kind=r["kind"]) for j, r in enumerate(rows[s:s + k])]; ctl = {}
        for j in range(max(5, len(part) * 6 // 100)):
            a, b = rng.sample(range(len(part)), 2)
            if part[a]["id"] != part[b]["id"]:
                c = dict(part[a], i=-(1000 * n + j + 1), text=part[b]["text"], kind=part[b]["kind"]); part.insert(rng.randrange(len(part) + 1), c); ctl[str(c["i"])] = "drop"
        json.dump(part, open(B + f"kev_{n:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0); man[f"kev_{n:02d}"] = ctl
    json.dump(dict(rows=rows, controls=man), open(B + "kev_manifest.json", "w", encoding="utf-8"), ensure_ascii=False); print(dict(rows=len(rows), batches=len(man)))


def merge():
    m = json.load(open(B + "kev_manifest.json", encoding="utf-8")); rows = m["rows"]; drop, rep = set(), {}
    for n, ctl in m["controls"].items():
        got = {str(r.get("i")): r.get("verdict") for r in outputs(n)}; caught = float(np.mean([got.get(c) == "drop" for c in ctl])); ok = caught >= CONTROL_MIN
        rep[n] = dict(controls=round(caught, 3), passed=ok)
        if ok: drop |= {int(i) for i, v in got.items() if v == "drop" and not i.startswith("-")}
        else: drop |= {x["i"] for x in json.load(open(B + f"{n}.json", encoding="utf-8")) if x["i"] >= 0}
    keep = [dict(r, split=split_of(r["id"])) for i, r in enumerate(rows) if i not in drop]
    open(R + "ko.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
    st = dict(kept=len(keep), dropped=len(drop), kinds=dict(collections.Counter(r["kind"] for r in keep)), concepts=len({r["id"] for r in keep}), batches=rep)
    json.dump(st, open(R + "ko_report.json", "w"), indent=1); print(json.dumps({k: v for k, v in st.items() if k != "batches"}, indent=1))


def english():
    import linking_models as LM, tuning_ledger as TL
    from build_linking_pools import read_obo
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels(); seen = training_texts(); per, out = collections.Counter(), []
    for r in map(json.loads, open(P.REPO + "data/curated/external/mentions_mondo.jsonl")):
        if r["split"] != "test" or len(r["mondo"]) != 1: continue
        t = r["mondo"][0]
        if t in held or t not in labels or TL.norm(r["mention"]) in seen or per[t] >= PER_CONCEPT: continue
        per[t] += 1; seen.add(TL.norm(r["mention"])); out.append(dict(id=t, text=r["mention"], kind=r["source"], split=split_of(t)))
    open(EN, "w", encoding="utf-8").write("".join(json.dumps(x) + "\n" for x in out))
    print(dict(questions=len(out), concepts=len(per), kinds=dict(collections.Counter(x["kind"] for x in out))))


def questions():
    import linking_models as LM
    labels, _ = LM.load_organ_labels(); Q = {}
    for lg, f in (("en", EN), ("ko", R + "ko.jsonl")):
        if os.path.exists(f): Q[lg] = [dict(r, organs=sorted(labels[r["id"]])) for r in map(json.loads, open(f, encoding="utf-8"))]
    return Q


def run(system, name, split="dev"):
    import bench_judge as BJ, eval_linking as EL
    Q = questions(); S = dict(base=BJ.Base, single=BJ.Single, scratch=BJ.Scratch)[system](); res, per = {}, {}
    for lg, qs in Q.items():
        rows = S.gold([q["text"] for q in qs]); per[lg] = rows
        gold = [dict(validity="valid", concepts=[q["id"]], best=q["id"], organs=q["organs"], category=q["kind"]) for q in qs]
        ix = [i for i, q in enumerate(qs) if q["split"] == split]
        m = EL.metrics([((r or {}).get("concept"), (r or {}).get("organs", [])) for r in rows], gold, ix)
        kinds = {}
        for k in sorted({q["kind"] for q in qs}):
            jx = [i for i in ix if qs[i]["kind"] == k]
            if jx: kinds[k] = round(EL.metrics([((r or {}).get("concept"), (r or {}).get("organs", [])) for r in rows], gold, jx)["macro_f1"], 3)
        res[lg] = dict(n=len(ix), macro_f1=m["macro_f1"], concept_acc=m["concept_acc"], per_organ_f1=m["per_organ_f1"], by_kind=kinds)
    json.dump(dict(name=name, system=system, split=split, scores=res, per=per), open(BJ.OUT + f"known_{name}.json", "w"), ensure_ascii=False)
    print(json.dumps({lg: {k: v for k, v in r.items() if k != "per_organ_f1"} for lg, r in res.items()}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--batches", action="store_true"); ap.add_argument("--verify", action="store_true"); ap.add_argument("--merge", action="store_true")
    ap.add_argument("--english", action="store_true"); ap.add_argument("--run", default=None); ap.add_argument("--name", default=None); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.batches: batches()
    elif a.verify: verify_batches()
    elif a.merge: merge()
    elif a.english: english()
    elif a.run: run(a.run, a.name or a.run, "test" if a.test else "dev")
