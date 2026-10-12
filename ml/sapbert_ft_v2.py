"""SapBERT fine-tuning, round 2: the pilot's MONDO pairs plus reviewed typed queries and NCBI Disease Corpus mentions.

    CUDA_VISIBLE_DEVICES=3 python -I ml/sapbert_ft_v2.py

Added training pairs (all concept-held-out from the pilot gold, like the pilot):
  * Haiku-written queries (synonym / abbreviation / typo / lay) whose Haiku review said valid + match, from review batches that
    rejected >= 80% of the planted wrong pairs;
  * NCBI Disease Corpus TRAIN mentions mapped to one MONDO concept through MONDO xrefs.
Same recipe as the pilot otherwise (InfoNCE, in-batch negatives with one pair per concept per batch, tau 0.05, batch 256,
lr 2e-5, 1 epoch). Fixed before running: it would only be considered for deployment if the paired gold-test macro-F1 CI excluded
zero. Scores: gold test (as the pilot) and NCBI Disease TEST mentions (concept recall@1/@5 over MONDO, an external set written by
paper authors rather than patients).
"""
import glob, json, os, random, sys
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import eval_linking as EL, mondo_index as MI, sapbert_ft_pilot as FP
from build_linking_pools import read_obo
OUTDIR = "/data/hyeongchanahn/adctox/ml_cache/sapbert_ft_v2/"; R = "/home/hyeongchanahn/CONI/adctox/data/curated/"


def extra_pairs(T, held):
    out = {}; rm = json.load(open(R + "train_queries/review_manifest.json")); traps = rm["traps"]; gens = {}
    for k in range(5):
        for i, x in enumerate(json.loads(l) for l in open(R + f"train_queries/gen/gen_{k}.jsonl")): gens[f"g{k}_{i:03d}"] = x
    n_q = 0
    for f in sorted(glob.glob(R + "train_queries/review/review_*.jsonl")):
        L = [json.loads(l) for l in open(f)]; tr = [x for x in L if x["rid"] in traps]
        if not tr or np.mean([x["match"] is False for x in tr]) < 0.8: continue
        for x in L:
            g = gens.get(x["rid"])
            if g and x["validity"] == "valid" and x["match"] is True and g.get("concept") in T and g["concept"] not in held:
                out.setdefault(g["concept"], []).append((T[g["concept"]]["name"], g["query"])); n_q += 1
    n_n = 0
    for r in map(json.loads, open(R + "external/ncbi_disease_mondo.jsonl")):
        if r["split"] == "train" and len(r["mondo"]) == 1 and r["mondo"][0] in T and r["mondo"][0] not in held:
            out.setdefault(r["mondo"][0], []).append((T[r["mondo"][0]]["name"], r["mention"])); n_n += 1
    return out, n_q, n_n


def main():
    from transformers import AutoTokenizer, AutoModel
    rng = random.Random(FP.SEED); torch.manual_seed(FP.SEED); DEV = FP.DEV
    T = read_obo(); idx = np.load(MI.C + "mondo_index.pre_v1.npz", allow_pickle=True); ids = [str(x) for x in idx["ids"]]
    concepts = list(dict.fromkeys(ids)); rows = [s for t in concepts for s in [T[t]["name"]] + T[t]["syn"]]
    nonhuman = {t for t in concepts if "non-human animal" in T[t]["name"]}
    G = [json.loads(l) for l in open(EL.D + "gold_v0.jsonl")]; held = {c for g in G for c in g["concepts"]}; children = {}
    for t in concepts:
        for p in T[t]["parents"]: children.setdefault(p, set()).add(t)
    held |= {p for c in list(held) for p in T.get(c, {}).get("parents", [])} | {k for c in list(held) for k in children.get(c, ())}
    pairs = {}
    for t in concepts:
        if t in held or t in nonhuman: continue
        names = [T[t]["name"]] + T[t]["syn"]; pairs[t] = [(names[0], s) for s in names[1:]] + [(names[0], FP.typo(rng.choice(names), rng))]
    ex, n_q, n_n = extra_pairs(T, held)
    for t, P in ex.items(): pairs.setdefault(t, []).extend(P)
    total_pairs = sum(map(len, pairs.values())); print("concepts", len(pairs), "pairs", total_pairs, "reviewed queries", n_q, "ncbi mentions", n_n, flush=True)
    tok = AutoTokenizer.from_pretrained(MI.NAME); mod = AutoModel.from_pretrained(MI.NAME).to(DEV)
    opt = torch.optim.AdamW(mod.parameters(), FP.LR, weight_decay=0.01); scaler = torch.amp.GradScaler()
    queue = {t: list(P) for t, P in pairs.items()}; [rng.shuffle(v) for v in queue.values()]; steps = 0; total = total_pairs // FP.BS
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 100) * max(0.0, 1 - s / max(total, 1)))
    while True:
        live = [t for t, v in queue.items() if v]
        if len(live) < FP.BS: break
        rng.shuffle(live); batch = [queue[t].pop() for t in live[:FP.BS]]
        a = tok([x for x, _ in batch], padding=True, truncation=True, max_length=FP.MAXLEN, return_tensors="pt").to(DEV)
        b = tok([y for _, y in batch], padding=True, truncation=True, max_length=FP.MAXLEN, return_tensors="pt").to(DEV); mod.train()
        with torch.autocast("cuda", dtype=torch.float16):
            ea = torch.nn.functional.normalize(mod(**a).last_hidden_state[:, 0].float(), dim=1); eb = torch.nn.functional.normalize(mod(**b).last_hidden_state[:, 0].float(), dim=1)
            lg = ea @ eb.T / FP.TEMP; lab = torch.arange(len(batch), device=DEV); loss = (torch.nn.functional.cross_entropy(lg, lab) + torch.nn.functional.cross_entropy(lg.T, lab)) / 2
        opt.zero_grad(); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step(); steps += 1
    mod.eval(); os.makedirs(OUTDIR, exist_ok=True); mod.save_pretrained(OUTDIR); tok.save_pretrained(OUTDIR)
    Q = json.load(open(EL.D + "raw/queries_v0.json")); Gq = {g["qid"]: g for g in G}; gold = [dict(Gq[q["qid"]], category=q["category"]) for q in Q]
    groups = [q["group"] or q["qid"] for q in Q]; split = [EL.split_of(g) for g in groups]; dev = [i for i, s in enumerate(split) if s == "dev"]; test = [i for i, s in enumerate(split) if s == "test"]
    ax = {}
    for t, a in zip(ids, idx["axes"]): ax.setdefault(t, [EL.AXES[k] for k in np.where(a > 0)[0]])
    keep = torch.tensor([t not in nonhuman for t in ids], device=DEV); id_arr = np.array(ids, dtype=object)
    ncbi = [r for r in map(json.loads, open(R + "external/ncbi_disease_mondo.jsonl")) if r["split"] == "test" and r["mondo"]]
    def topk(tk, md, texts, Ei):
        Eq = FP.embed(tk, md, texts); out = []
        for i in range(0, len(texts), 1024):
            Sm = Eq[i:i + 1024] @ Ei.T; Sm[:, ~keep] = -1; v, j = Sm.topk(200, dim=1)
            for vv, jj in zip(v.tolist(), j.tolist()):
                seen, picks = set(), []
                for x, y in zip(jj, vv):
                    c = id_arr[x]
                    if c in seen: continue
                    seen.add(c); picks.append((c, y))
                    if len(picks) == 10: break
                out.append(picks)
        return out
    res = {}
    for name, (tk, md) in {"frozen": (AutoTokenizer.from_pretrained(MI.NAME), AutoModel.from_pretrained(MI.NAME).to(DEV).eval()), "finetuned_v2": (tok, mod)}.items():
        Ei = FP.embed(tk, md, rows); top = topk(tk, md, [q["query"] for q in Q], Ei); tn = topk(tk, md, [r["mention"] for r in ncbi], Ei)
        pred = lambda th: [(top[i][0][0], ax.get(top[i][0][0], [])) if top[i][0][1] >= th else (None, []) for i in range(len(Q))]
        best = max(np.arange(0.5, 0.99, 0.01), key=lambda th: EL.metrics(pred(th), gold, dev)["macro_f1"])
        V = [i for i in test if gold[i]["validity"] == "valid" and gold[i]["concepts"]]
        res[name] = dict(theta=float(best), test=EL.metrics(pred(best), gold, test), gold_test_recall={k: float(np.mean([bool({c for c, _ in top[i][:k]} & set(gold[i]["concepts"])) for i in V])) for k in (1, 5, 10)},
                         ncbi_test_recall={k: float(np.mean([bool({c for c, _ in tn[i][:k]} & set(r["mondo"])) for i, r in enumerate(ncbi)])) for k in (1, 5, 10)}, _pred=pred(best),
                         _ncbi_hit1=[float(bool({tn[i][0][0]} & set(r["mondo"]))) for i, r in enumerate(ncbi)])
        print(name, {k: v for k, v in res[name].items() if not k.startswith("_") and k != "test"}, "F1 %.3f" % res[name]["test"]["macro_f1"], flush=True)
    res["paired_gold_test_macro_f1"] = EL.boot(res["finetuned_v2"]["_pred"], res["frozen"]["_pred"], gold, test, groups)
    res["paired_gold_test_concept_acc"] = EL.boot(res["finetuned_v2"]["_pred"], res["frozen"]["_pred"], gold, test, groups, key="concept_acc")
    d = np.array(res["finetuned_v2"]["_ncbi_hit1"]) - np.array(res["frozen"]["_ncbi_hit1"]); pm = np.array([r["pmid"] for r in ncbi]); up = np.unique(pm); by = {u: d[pm == u] for u in up}
    rng2 = np.random.default_rng(0); bs = [np.concatenate([by[u] for u in rng2.choice(up, len(up))]).mean() for _ in range(2000)]
    res["paired_ncbi_test_recall1"] = dict(delta=float(d.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n=len(d), abstracts=len(up))
    for k in ("frozen", "finetuned_v2"): res[k].pop("_pred"); res[k].pop("_ncbi_hit1")
    res["config"] = dict(pairs=total_pairs, reviewed_queries=n_q, ncbi_mentions=n_n, steps=steps)
    json.dump(res, open(EL.OUT + "sapbert_ft_v2.json", "w"), indent=1)
    print("gold test macro-F1", res["paired_gold_test_macro_f1"], "concept", res["paired_gold_test_concept_acc"], "ncbi recall@1", res["paired_ncbi_test_recall1"])


if __name__ == "__main__":
    main()
