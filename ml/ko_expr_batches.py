"""Korean expressions, second set (ko2): everyday words, spoken complaints, abbreviations and typos for clinically common
MONDO concepts, written by Claude Haiku 5.5 and checked by a second Haiku pass with planted errors.

    ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache> python ml/ko_expr_batches.py            # concepts and generation batches
    ADC_RESEARCH_MODE=1 python ml/ko_expr_batches.py --verify                         # verification batches from the outputs
    ADC_RESEARCH_MODE=1 python ml/ko_expr_batches.py --merge                          # -> data/curated/judge2/gen/ko2_*.jsonl

Why: the Gemma judge's Korean organ F1 barely moved with tuning (benchmark 2026-10-17, ml/docs/single_model_plan.md), and the
Korean typos, abbreviations and everyday words of the gold set score lowest. The first Korean set (judge2 ko_*) covered the
concepts frequent in English corpora, mostly rare and genetic; this one covers the concepts Korean clinicians code.

Concepts: the 52,626 HIRA KCD Korean names, linked to MONDO through their English KCD names (SapBERT, cosine >= SIM), plus the
exact Korean-name matches of korean/mondo_ko.jsonl. Gold concepts and their relatives are left out (linking_models.gold_held),
so the evaluation stays clean. Ranked by how many KCD names link to the concept; per organ at most PER_ORGAN, so every organ
gets data (the organ F1 target is per organ). Each generation batch: BATCH concepts, each with its MONDO line, Korean name and
organs.
Verification: every output line is shown again with 6% planted errors (an expression of another concept under this one); a
batch's drops are applied only when it catches at least CONTROL_MIN of the planted errors.
"""
import collections, glob, json, os, random, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

R = P.REPO + "data/curated/judge2/"; B = R + "batches/"; OUT = R + "out_ko2/"
SIM, PER_ORGAN, BATCH, SEED, CONTROL_MIN = 0.85, 260, 20, 2031, 0.75
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
HANGUL = re.compile("[가-힣]")


def concepts():
    import torch, linking_models as LM, mondo_index as MI, tuning_ledger as TL
    from build_linking_pools import read_obo
    from sample_label_concepts import line
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels()
    MI.link(["x"]); Z = MI._IDX; E = torch.from_numpy(Z["E"].astype(np.float32)).cuda(); ids = Z["_ids"]
    kv = [str(x) for x in Z["ko_vals"]]; hits = collections.Counter()
    for i in range(0, len(kv), 4096):
        v = torch.from_numpy(MI._embed(kv[i:i + 4096], "cuda:0").astype(np.float32)).cuda(); s, j = (v @ E.T).max(1)
        for ss, jj in zip(s.cpu().numpy(), j.cpu().numpy()):
            if ss >= SIM: hits[str(ids[jj])] += 1
    mk = {x["id"]: x for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8"))}
    kcd = {TL.norm(k) for k in Z["ko_keys"]}
    for t, x in mk.items():
        if any(TL.norm(n) in kcd for n in [x["ko"]] + x["alt"]): hits[t] += 1
    pool = [t for t, _ in hits.most_common() if t in T and t not in held and labels.get(t) and t in mk and not T[t]["name"].startswith("obsolete")]
    pick, per = [], collections.Counter()
    for t in pool:                                                       # most-coded first, until each of its organs is full
        if all(per[a] >= PER_ORGAN for a in labels[t]): continue
        pick.append(t); per.update(labels[t])
    rows = [dict(id=t, concept=line(T, t), ko=mk[t]["ko"], alt=mk[t]["alt"][:2], organs=sorted(labels[t], key=AXES.index), kcd_links=hits[t]) for t in pick]
    return rows, dict(kcd_linked=len(hits), pool=len(pool), picked=len(pick), per_organ=dict(per))


def batches():
    rows, stats = concepts(); rng = random.Random(SEED); rng.shuffle(rows); os.makedirs(B, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    for f in glob.glob(B + "ko2_*.json"): os.remove(f)
    n = 0
    for k in range(0, len(rows), BATCH):
        json.dump(rows[k:k + BATCH], open(B + f"ko2_{n:03d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0); n += 1
    stats["batches"] = n; json.dump(stats, open(B + "ko2_manifest.json", "w"), indent=1); print(json.dumps(stats, indent=1))


def outputs(prefix):
    """rows of out_ko2/<prefix>_*.jsonl, or of out_ko2/<prefix>.jsonl when prefix names one batch."""
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
    """keep Korean expressions of a known concept and kind; drop duplicates and exact copies of the concept's MONDO Korean name."""
    con = {x["id"]: x for f in glob.glob(B + "ko2_[0-9]*.json") for x in json.load(open(f, encoding="utf-8"))}
    seen, out = set(), []
    for r in rows:
        t, txt, kind = r.get("id"), str(r.get("text", "")).strip(), r.get("kind")
        if t not in con or kind not in ("everyday", "spoken", "abbrev", "typo") or not txt or len(txt) > 60: continue
        if kind != "abbrev" and not HANGUL.search(txt): continue
        if txt == con[t]["ko"] or (t, txt) in seen: continue
        seen.add((t, txt)); out.append(dict(id=t, text=txt, kind=kind))
    return out, con


def verify_batches():
    rows, con = clean(outputs("ko2")); rng = random.Random(SEED + 1); rng.shuffle(rows); man = {}
    for f in glob.glob(B + "ko2v_*.json"): os.remove(f)
    k = (len(rows) + 39) // 40
    for n, s in enumerate(range(0, len(rows), k)):
        part = [dict(i=s + j, id=r["id"], concept=con[r["id"]]["concept"], ko=con[r["id"]]["ko"], text=r["text"], kind=r["kind"]) for j, r in enumerate(rows[s:s + k])]
        ctl = {}
        for j in range(max(5, len(part) * 6 // 100)):                        # an expression of another concept under this one
            a, b = rng.sample(range(len(part)), 2)
            if part[a]["id"] == part[b]["id"]: continue
            c = dict(part[a], i=-(1000 * n + j + 1), text=part[b]["text"], kind=part[b]["kind"]); part.insert(rng.randrange(len(part) + 1), c); ctl[str(c["i"])] = "drop"
        json.dump(part, open(B + f"ko2v_{n:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0); man[f"ko2v_{n:02d}"] = ctl
    json.dump(dict(rows=rows, controls=man), open(B + "ko2v_manifest.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(dict(expressions=len(rows), batches=len(man)))


def merge():
    m = json.load(open(B + "ko2v_manifest.json", encoding="utf-8")); rows = m["rows"]; drop, rep = set(), {}
    for n, ctl in m["controls"].items():
        got = {str(r.get("i")): r.get("verdict") for r in outputs(n)}
        caught = np.mean([got.get(c) == "drop" for c in ctl]) if ctl else 0.0; ok = caught >= CONTROL_MIN
        rep[n] = dict(controls=round(float(caught), 3), passed=bool(ok), answered=sum(1 for c in got if not c.startswith("-")))
        if ok: drop |= {int(i) for i, v in got.items() if v == "drop" and not i.startswith("-")}
    keep = [r for i, r in enumerate(rows) if i not in drop]
    for f in glob.glob(R + "gen/ko2_*.jsonl"): os.remove(f)
    for k in range(0, len(keep), 2000):
        open(R + f"gen/ko2_{k // 2000:02d}.jsonl", "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in keep[k:k + 2000]))
    stats = dict(generated=len(rows), dropped=len(drop), kept=len(keep), kinds=dict(collections.Counter(x["kind"] for x in keep)),
                 concepts=len({x["id"] for x in keep}), batches_passed=sum(r["passed"] for r in rep.values()), batches=len(rep), per_batch=rep)
    json.dump(stats, open(R + "gen/ko2_report.json", "w"), indent=1); print(json.dumps({k: v for k, v in stats.items() if k != "per_batch"}, indent=1))


if __name__ == "__main__":
    if "--verify" in sys.argv: verify_batches()
    elif "--merge" in sys.argv: merge()
    else: batches()
