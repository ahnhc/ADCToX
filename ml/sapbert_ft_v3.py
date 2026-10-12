"""SapBERT fine-tuning, round 3 (model 0.2): round-2 pairs plus the train splits of four public mention corpora.

    CUDA_VISIBLE_DEVICES=3 python -I ml/sapbert_ft_v3.py

Why continued training rather than training from scratch: SapBERT itself was trained on ~4M UMLS synonym pairs, which this
project cannot use; the ~120k pairs here can only adjust it. The question left is how much of it to adjust, so two ways are
compared: every layer ("full") or only the top 4 encoder layers with embeddings and lower layers frozen ("top4"), each for 1 and
2 epochs. Everything below was fixed before any run.

Training pairs (concept held out from the gold exactly as rounds 1-2: gold concepts, their parents and children never train):
  MONDO (name, exact synonym) + (name, typo) pairs; reviewed typed queries; single-concept TRAIN mentions of NCBI Disease,
  BC5CDR, MedMentions st21pv and COMETA (data/curated/external/mentions_mondo.jsonl), each paired with the concept name.
Recipe otherwise as rounds 1-2: InfoNCE with in-batch negatives (one pair per concept per batch), tau 0.05, batch 256, lr 2e-5
(top4: 3e-5), warmup 100 steps then linear decay, CLS pooling, max length 48.
Selection (dev only): the mean of the gold-dev macro-F1 (bare linker, crosswalk organs, theta tuned on dev, as rounds 1-2) and the
mean external-dev concept recall@1 over the four corpora. Only the selected variant is scored on test.
Deployment rule (pre-registered in model_review_2026-10-12.md, round 3 section 6): the paired gold-test macro-F1 CI lower bound
> 0, AND no external corpus whose paired test recall@1 CI lies wholly below 0. Bootstraps resample query groups (gold) or
documents (external), 2000 draws.
"""
import json, os, random, shutil, sys
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import eval_linking as EL, mondo_index as MI, sapbert_ft_pilot as FP, sapbert_ft_v2 as V2
from build_linking_pools import read_obo
OUTDIR = "/data/hyeongchanahn/adctox/ml_cache/sapbert_ft_v3/"; R = "/home/hyeongchanahn/CONI/adctox/data/curated/"
SOURCES = ("ncbi", "bc5cdr", "medmentions", "cometa")
VARIANTS = [("full", 1), ("full", 2), ("top4", 1), ("top4", 2)]


def training_pairs(T, concepts, nonhuman, held, rng):
    pairs = {}
    for t in concepts:
        if t in held or t in nonhuman: continue
        names = [T[t]["name"]] + T[t]["syn"]; pairs[t] = [(names[0], s) for s in names[1:]] + [(names[0], FP.typo(rng.choice(names), rng))]
    ex, n_q, _ = V2.extra_pairs(T, held)                            # reviewed queries + NCBI train (duplicates of the merged file are dropped in main)
    for t, P in ex.items(): pairs.setdefault(t, []).extend(P)
    n_ext = {s: 0 for s in SOURCES}; seen = set()
    for r in map(json.loads, open(R + "external/mentions_mondo.jsonl")):
        if r["split"] != "train" or len(r["mondo"]) != 1: continue
        t = r["mondo"][0]
        if t not in T or t in held or t in nonhuman or (t, r["mention"].lower()) in seen: continue
        seen.add((t, r["mention"].lower())); pairs.setdefault(t, []).append((T[t]["name"], r["mention"])); n_ext[r["source"]] += 1
    return pairs, n_q, n_ext


def train(pairs, kind, epochs, rng):
    from transformers import AutoTokenizer, AutoModel
    tok = AutoTokenizer.from_pretrained(MI.NAME); mod = AutoModel.from_pretrained(MI.NAME).to(FP.DEV); lr = FP.LR
    if kind == "top4":
        n = mod.config.num_hidden_layers; lr = 3e-5
        for name, p in mod.named_parameters():
            p.requires_grad = any(name.startswith(f"encoder.layer.{i}.") for i in range(n - 4, n)) or name.startswith("pooler.")
    params = [p for p in mod.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr, weight_decay=0.01); scaler = torch.amp.GradScaler()
    total = epochs * sum(map(len, pairs.values())) // FP.BS
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 100) * max(0.0, 1 - s / max(total, 1))); steps = 0
    for _ in range(epochs):
        queue = {t: list(P) for t, P in pairs.items()}; [rng.shuffle(v) for v in queue.values()]
        while True:
            live = [t for t, v in queue.items() if v]
            if len(live) < FP.BS: break
            rng.shuffle(live); batch = [queue[t].pop() for t in live[:FP.BS]]
            a = tok([x for x, _ in batch], padding=True, truncation=True, max_length=FP.MAXLEN, return_tensors="pt").to(FP.DEV)
            b = tok([y for _, y in batch], padding=True, truncation=True, max_length=FP.MAXLEN, return_tensors="pt").to(FP.DEV); mod.train()
            with torch.autocast("cuda", dtype=torch.float16):
                ea = torch.nn.functional.normalize(mod(**a).last_hidden_state[:, 0].float(), dim=1); eb = torch.nn.functional.normalize(mod(**b).last_hidden_state[:, 0].float(), dim=1)
                lg = ea @ eb.T / FP.TEMP; lab = torch.arange(len(batch), device=FP.DEV); loss = (torch.nn.functional.cross_entropy(lg, lab) + torch.nn.functional.cross_entropy(lg.T, lab)) / 2
            opt.zero_grad(); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step(); steps += 1
    return tok, mod.eval(), steps


def boot_docs(a, b, docs, n=2000):
    d = np.asarray(a, float) - np.asarray(b, float); docs = np.asarray(docs); up = np.unique(docs); by = {u: d[docs == u] for u in up}
    rng = np.random.default_rng(0); bs = [np.concatenate([by[u] for u in rng.choice(up, len(up))]).mean() for _ in range(n)]
    return dict(delta=float(d.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n=len(d), docs=len(up))


def main():
    from transformers import AutoTokenizer, AutoModel
    rng = random.Random(FP.SEED); torch.manual_seed(FP.SEED)
    T = read_obo(); idx = np.load(MI.C + "mondo_index.pre_v1.npz", allow_pickle=True); ids = [str(x) for x in idx["ids"]]
    concepts = list(dict.fromkeys(ids)); rows = [s for t in concepts for s in [T[t]["name"]] + T[t]["syn"]]
    nonhuman = {t for t in concepts if "non-human animal" in T[t]["name"]}
    G = [json.loads(l) for l in open(EL.D + "gold_v0.jsonl")]; held = {c for g in G for c in g["concepts"]}; children = {}
    for t in concepts:
        for p in T[t]["parents"]: children.setdefault(p, set()).add(t)
    held |= {p for c in list(held) for p in T.get(c, {}).get("parents", [])} | {k for c in list(held) for k in children.get(c, ())}
    pairs, n_q, n_ext = training_pairs(T, concepts, nonhuman, held, rng)
    for t in pairs:                                                  # the merged file already holds the NCBI train mentions
        pairs[t] = list(dict.fromkeys(pairs[t]))
    total_pairs = sum(map(len, pairs.values())); print("concepts", len(pairs), "pairs", total_pairs, "queries", n_q, "external", n_ext, flush=True)
    train_strings = {y.lower() for P in pairs.values() for _, y in P}

    Q = json.load(open(EL.D + "raw/queries_v0.json")); Gq = {g["qid"]: g for g in G}; gold = [dict(Gq[q["qid"]], category=q["category"]) for q in Q]
    groups = [q["group"] or q["qid"] for q in Q]; split = [EL.split_of(g) for g in groups]
    dev = [i for i, s in enumerate(split) if s == "dev"]; test = [i for i, s in enumerate(split) if s == "test"]
    ax = {}
    for t, a in zip(ids, idx["axes"]): ax.setdefault(t, [EL.AXES[k] for k in np.where(a > 0)[0]])
    keep = torch.tensor([t not in nonhuman for t in ids], device=FP.DEV); id_arr = np.array(ids, dtype=object)
    ext = [r for r in map(json.loads, open(R + "external/mentions_mondo.jsonl")) if r["split"] in ("dev", "test")]

    def top1(tk, md, texts, Ei):
        Eq = FP.embed(tk, md, texts); out = []
        for i in range(0, len(texts), 1024):
            Sm = Eq[i:i + 1024] @ Ei.T; Sm[:, ~keep] = -1; v, j = Sm.max(1)
            out += [(id_arr[jj], vv) for vv, jj in zip(v.tolist(), j.tolist())]
        return out

    def score(tk, md):
        Ei = FP.embed(tk, md, rows); tg = top1(tk, md, [q["query"] for q in Q], Ei); te = top1(tk, md, [r["mention"] for r in ext], Ei)
        pred = lambda th: [(tg[i][0], ax.get(tg[i][0], [])) if tg[i][1] >= th else (None, []) for i in range(len(Q))]
        th = max(np.arange(0.5, 0.99, 0.01), key=lambda t: EL.metrics(pred(t), gold, dev)["macro_f1"])
        hit = [float(c in r["mondo"]) for (c, _), r in zip(te, ext)]
        ext_dev = {s: float(np.mean([h for h, r in zip(hit, ext) if r["source"] == s and r["split"] == "dev"])) for s in SOURCES}
        out = dict(theta=float(th), gold_dev_f1=EL.metrics(pred(th), gold, dev)["macro_f1"], ext_dev_recall1=ext_dev)
        out["select"] = (out["gold_dev_f1"] + float(np.mean(list(ext_dev.values())))) / 2
        return out, pred(th), hit

    res = {"config": dict(pairs=total_pairs, concepts=len(pairs), reviewed_queries=n_q, external_train=n_ext, variants=VARIANTS)}
    frozen = (AutoTokenizer.from_pretrained(MI.NAME), AutoModel.from_pretrained(MI.NAME).to(FP.DEV).eval())
    res["frozen"], f_pred, f_hit = score(*frozen); print("frozen", res["frozen"], flush=True)
    best = None
    for kind, ep in VARIANTS:
        name = f"{kind}_{ep}ep"; rng_v = random.Random(FP.SEED); torch.manual_seed(FP.SEED)
        tk, md, steps = train(pairs, kind, ep, rng_v); s, p, h = score(tk, md); s["steps"] = steps; res[name] = s
        print(name, s, flush=True)
        if best is None or s["select"] > res[best[0]]["select"]:
            best = (name, p, h); md.save_pretrained(OUTDIR); tk.save_pretrained(OUTDIR)
        del md; torch.cuda.empty_cache()
    name, b_pred, b_hit = best; res["selected"] = name
    # ---- test, once, for the selected variant
    res["paired_gold_test_macro_f1"] = EL.boot(b_pred, f_pred, gold, test, groups)
    res["paired_gold_test_concept_acc"] = EL.boot(b_pred, f_pred, gold, test, groups, key="concept_acc")
    res["gold_test_f1"] = dict(frozen=EL.metrics(f_pred, gold, test)["macro_f1"], selected=EL.metrics(b_pred, gold, test)["macro_f1"])
    res["external_test"] = {}
    for s in SOURCES:
        ix = [i for i, r in enumerate(ext) if r["source"] == s and r["split"] == "test"]
        un = [i for i in ix if ext[i]["mention"].lower() not in train_strings]
        res["external_test"][s] = dict(frozen=float(np.mean([f_hit[i] for i in ix])), selected=float(np.mean([b_hit[i] for i in ix])),
                                       paired=boot_docs([b_hit[i] for i in ix], [f_hit[i] for i in ix], [ext[i]["doc"] for i in ix]),
                                       unseen_strings=boot_docs([b_hit[i] for i in un], [f_hit[i] for i in un], [ext[i]["doc"] for i in un]) if un else None)
    worse = [s for s, v in res["external_test"].items() if v["paired"]["hi"] < 0]
    res["deploy"] = dict(gold_ci_above_zero=res["paired_gold_test_macro_f1"]["lo"] > 0, external_worse=worse,
                         passed=res["paired_gold_test_macro_f1"]["lo"] > 0 and not worse)
    json.dump(res, open(EL.OUT + "sapbert_ft_v3.json", "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("selected", "paired_gold_test_macro_f1", "paired_gold_test_concept_acc", "gold_test_f1", "deploy")}, indent=1))
    for s, v in res["external_test"].items(): print(s, "frozen %.3f selected %.3f" % (v["frozen"], v["selected"]), v["paired"], "unseen", v["unseen_strings"])


if __name__ == "__main__":
    main()
