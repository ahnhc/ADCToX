"""Batches for the Haiku labelling round (data/curated/concept_organs/ and data/curated/train_queries/).

    CUDA_VISIBLE_DEVICES=3 python -I ml/sample_label_concepts.py

Concepts in any pilot-gold record, and their direct parents and children, are held out from everything written here (the gold
stays an evaluation set). Concept organ batches: ~4,000 human MONDO disease concepts in three strata:
  common  top-1 SapBERT link (sim >= 0.80) of the FinnGen prior long names: diseases that actually occur in registries
  synonym concepts with >= 3 exact synonyms (a rough proxy for clinical use)
  random  any other human disease concept
16 batches; each concept is in one batch, 20% also in a second batch (agreement), and every batch carries 10 calibration
concepts taken from the gold (their labels are scored against the Sonnet gold, never used for training).
Query-generation batches: 500 'common' training concepts, 100 per batch, for writing typed variants; reviewed by other agents.
"""
import json, os, random, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import mondo_index as MI, lab
from build_linking_pools import read_obo
R = "/home/hyeongchanahn/CONI/adctox/data/curated/"; SEED = 7; N_BATCH = 16


def held_out(T):
    G = [json.loads(l) for l in open(R + "disease_linking/gold_v0.jsonl")]; held = {c for g in G for c in g["concepts"]}; ch = {}
    for t, e in T.items():
        for p in e["parents"]: ch.setdefault(p, set()).add(t)
    return held | {p for c in list(held) for p in T.get(c, {}).get("parents", [])} | {k for c in list(held) for k in ch.get(c, ())}, G


def ancestors(T, t, k=4):
    out, frontier, seen = [], list(T[t]["parents"]), set()
    while frontier and len(out) < k:
        p = frontier.pop(0)
        if p in seen or p not in T: continue
        seen.add(p); out.append(T[p]["name"]); frontier.extend(T[p]["parents"])
    return out


def line(T, t):
    e = T[t]; syn = "; ".join(e["syn"][:4]); d = e["defn"][:200] + ("..." if len(e["defn"]) > 200 else "")
    return f"- {t} | {e['name']}" + (f" | syn: {syn}" if syn else "") + f" | ancestors: {', '.join(ancestors(T, t)) or '-'}" + (f" | def: {d}" if d else "")


def main():
    rng = random.Random(SEED); T = read_obo(); held, G = held_out(T)
    idx = np.load(MI.C + "mondo_index.npz", allow_pickle=True); ids = [str(x) for x in idx["ids"]]; concepts = list(dict.fromkeys(ids))
    human = [t for t in concepts if "non-human animal" not in T[t]["name"] and t not in held]
    m = lab.load_rows(); names = sorted(set(m.prior_longname.dropna().str.strip()))
    Q = MI._embed(names, "cuda:0").astype(np.float32); S = Q @ idx["E"].astype(np.float32).T; hs = set(human); common = []
    for row in S:
        for j in np.argsort(-row)[:30]:
            if ids[j] in hs:
                if row[j] >= 0.80: common.append(ids[j])
                break
    common = list(dict.fromkeys(common)); rest = [t for t in human if t not in set(common)]
    syn3 = [t for t in rest if len(T[t]["syn"]) >= 3]; rng.shuffle(syn3); syn3 = syn3[:1800]
    rnd = [t for t in rest if t not in set(syn3)]; rng.shuffle(rnd); rnd = rnd[:4000 - len(common) - len(syn3)]
    pool = [(t, "common") for t in common] + [(t, "synonym") for t in syn3] + [(t, "random") for t in rnd]; rng.shuffle(pool)
    print("common", len(common), "synonym", len(syn3), "random", len(rnd), "total", len(pool), "held out", len(held), flush=True)
    # calibration concepts: canonical-query best concept of each gold group, organs = gold organs of that record
    Qs = json.load(open(R + "disease_linking/raw/queries_v0.json")); gq = {g["qid"]: g for g in G}
    calib = {}
    for q in Qs:
        g = gq[q["qid"]]
        if q["category"] == "canonical" and g["validity"] == "valid" and g["best"] and g["best"] in T: calib[g["best"]] = g["organs"]
    calib_ids = sorted(calib); rng.shuffle(calib_ids)
    os.makedirs(R + "concept_organs/batches", exist_ok=True); os.makedirs(R + "concept_organs/labels", exist_ok=True)
    primary = [pool[k::N_BATCH] for k in range(N_BATCH)]; overlap_ids = [t for t, _ in pool[:len(pool) // 5]]
    manifest = dict(strata={t: s for t, s in pool}, calibration=calib, batches={})
    for k in range(N_BATCH):
        own = [t for t, _ in primary[k]]; extra = [t for t in overlap_ids if t not in set(own)][k * (len(overlap_ids) // N_BATCH):(k + 1) * (len(overlap_ids) // N_BATCH)]
        cal = calib_ids[(k * 10) % len(calib_ids):(k * 10) % len(calib_ids) + 10]
        items = own + extra + cal; rng.shuffle(items); manifest["batches"][k] = items
        with open(R + f"concept_organs/batches/batch_{k:02d}.txt", "w") as fh: fh.write("\n".join(line(T, t) for t in items) + "\n")
    json.dump(manifest, open(R + "concept_organs/manifest.json", "w"), indent=0)
    # query-generation batches from training 'common' concepts
    os.makedirs(R + "train_queries/batches", exist_ok=True); os.makedirs(R + "train_queries/gen", exist_ok=True); os.makedirs(R + "train_queries/review", exist_ok=True)
    qc = [t for t in common if t in hs]; rng.shuffle(qc); qc = qc[:500]
    for k in range(5):
        with open(R + f"train_queries/batches/gen_{k}.txt", "w") as fh: fh.write("\n".join(line(T, t) for t in qc[k * 100:(k + 1) * 100]) + "\n")
    json.dump(dict(concepts=qc), open(R + "train_queries/manifest.json", "w"))
    print("batches written; per batch", [len(v) for v in manifest["batches"].values()], "calibration concepts", len(calib_ids))


if __name__ == "__main__":
    main()
