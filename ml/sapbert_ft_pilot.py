"""Pilot: does contrastive fine-tuning of SapBERT on MONDO (concept-held-out) improve linking on the pilot gold?

    CUDA_VISIBLE_DEVICES=3 python -I ml/sapbert_ft_pilot.py

Training pairs: (name, exact synonym) and (name, synthetic 1-2 character typo of the name or a synonym) for human MONDO
disease concepts. Every concept that appears in ANY gold record's acceptable set is removed from training, and so are its
direct parents and children (a concept-holdout; the pretrained SapBERT may still have seen them via UMLS, which this cannot
undo). One configuration, fixed before looking at test: InfoNCE with in-batch negatives (one pair per concept per batch),
temperature 0.05, batch 256, lr 2e-5, 1 epoch, CLS pooling, max length 48 (the shipped linker's settings).
The fine-tuned model re-embeds the whole MONDO index (query and index must share the encoder). Non-human-animal concepts are
dropped from retrieval for BOTH frozen and fine-tuned models. The acceptance threshold is tuned on the dev split for each model
separately; scores on the test split. Concept-level organs use the existing crosswalk for both, so only the linker differs.
Nothing is deployed: the checkpoint stays in the research cache.
"""
import json, os, random, sys, time
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import eval_linking as EL, mondo_index as MI
from build_linking_pools import read_obo
OUTDIR = "/data/hyeongchanahn/adctox/ml_cache/sapbert_ft_pilot/"; DEV = "cuda:0"
TEMP, BS, LR, EPOCHS, MAXLEN, SEED = 0.05, 256, 2e-5, 1, 48, 0


def typo(s, rng):
    s = list(s)
    for _ in range(rng.choice([1, 2])):
        if len(s) < 4: break
        i = rng.randrange(1, len(s) - 1); op = rng.choice("dsit")
        if op == "d": del s[i]
        elif op == "s": s[i] = rng.choice("abcdefghijklmnopqrstuvwxyz")
        elif op == "i": s.insert(i, rng.choice("abcdefghijklmnopqrstuvwxyz"))
        else: s[i], s[i + 1] = s[i + 1], s[i]
    return "".join(s)


def embed(tok, mod, strs, bs=1024):
    out = []
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        for i in range(0, len(strs), bs):
            b = tok(strs[i:i + bs], padding=True, truncation=True, max_length=MAXLEN, return_tensors="pt").to(DEV); out.append(mod(**b).last_hidden_state[:, 0].float())
    E = torch.cat(out); return torch.nn.functional.normalize(E, dim=1)


def main():
    from transformers import AutoTokenizer, AutoModel
    rng = random.Random(SEED); torch.manual_seed(SEED)
    T = read_obo(); idx = np.load(MI.C + "mondo_index.npz", allow_pickle=True); ids = [str(x) for x in idx["ids"]]
    concepts = list(dict.fromkeys(ids)); rows = [s for t in concepts for s in [T[t]["name"]] + T[t]["syn"]]
    nonhuman = {t for t in concepts if "non-human animal" in T[t]["name"]}
    G = [json.loads(l) for l in open(EL.D + "gold_v0.jsonl")]; held = {c for g in G for c in g["concepts"]}
    children = {}
    for t in concepts:
        for p in T[t]["parents"]: children.setdefault(p, set()).add(t)
    held |= {p for c in list(held) for p in T.get(c, {}).get("parents", [])} | {k for c in list(held) for k in children.get(c, ())}
    pairs = {}
    for t in concepts:
        if t in held or t in nonhuman: continue
        names = [T[t]["name"]] + T[t]["syn"]; P = [(names[0], s) for s in names[1:]] + [(names[0], typo(rng.choice(names), rng))]
        pairs[t] = P
    print("train concepts", len(pairs), "held out", len(held), "pairs", sum(map(len, pairs.values())), flush=True)
    tok = AutoTokenizer.from_pretrained(MI.NAME); mod = AutoModel.from_pretrained(MI.NAME).to(DEV)
    opt = torch.optim.AdamW(mod.parameters(), LR, weight_decay=0.01); scaler = torch.amp.GradScaler()
    # batches: each batch takes one pair from each of BS distinct concepts, until every pair is used once
    queue = {t: list(P) for t, P in pairs.items()}; [rng.shuffle(v) for v in queue.values()]; steps = 0; t0 = time.time()
    total = sum(map(len, pairs.values())) // BS; sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 100) * max(0.0, 1 - s / max(total, 1)))
    for ep in range(EPOCHS):
        while True:
            live = [t for t, v in queue.items() if v]
            if len(live) < BS: break
            rng.shuffle(live); batch = [queue[t].pop() for t in live[:BS]]
            a = tok([x for x, _ in batch], padding=True, truncation=True, max_length=MAXLEN, return_tensors="pt").to(DEV)
            b = tok([y for _, y in batch], padding=True, truncation=True, max_length=MAXLEN, return_tensors="pt").to(DEV)
            mod.train()
            with torch.autocast("cuda", dtype=torch.float16):
                ea = torch.nn.functional.normalize(mod(**a).last_hidden_state[:, 0].float(), dim=1); eb = torch.nn.functional.normalize(mod(**b).last_hidden_state[:, 0].float(), dim=1)
                logits = ea @ eb.T / TEMP; lab = torch.arange(len(batch), device=DEV)
                loss = (torch.nn.functional.cross_entropy(logits, lab) + torch.nn.functional.cross_entropy(logits.T, lab)) / 2
            opt.zero_grad(); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step(); steps += 1
            if steps % 100 == 0: print(f"step {steps}/{total} loss {loss.item():.4f} {time.time() - t0:.0f}s", flush=True)
    mod.eval(); os.makedirs(OUTDIR, exist_ok=True); mod.save_pretrained(OUTDIR); tok.save_pretrained(OUTDIR)
    # evaluation: frozen vs fine-tuned, identical retrieval and decision rule
    Q = json.load(open(EL.D + "raw/queries_v0.json")); Gq = {g["qid"]: g for g in G}; gold = [dict(Gq[q["qid"]], category=q["category"]) for q in Q]
    groups = [q["group"] or q["qid"] for q in Q]; split = [EL.split_of(g) for g in groups]; dev = [i for i, s in enumerate(split) if s == "dev"]; test = [i for i, s in enumerate(split) if s == "test"]
    S = json.load(open(EL.D + "raw/system_outputs_v0.json")); ax = dict(S["axes_of"])
    for t, a in zip(ids, idx["axes"]): ax.setdefault(t, [EL.AXES[k] for k in np.where(a > 0)[0]])
    keep = torch.tensor([t not in nonhuman for t in ids], device=DEV); id_arr = np.array(ids, dtype=object)
    res = {}
    for name, (tk, md) in {"frozen": (AutoTokenizer.from_pretrained(MI.NAME), AutoModel.from_pretrained(MI.NAME).to(DEV).eval()), "finetuned": (tok, mod)}.items():
        Ei = embed(tk, md, rows); Eq = embed(tk, md, [q["query"] for q in Q]); Sm = Eq @ Ei.T; Sm[:, ~keep] = -1
        top = []
        for row in Sm:
            v, j = row.topk(200); seen, picks = set(), []
            for jj, vv in zip(j.tolist(), v.tolist()):
                c = id_arr[jj]
                if c in seen: continue
                seen.add(c); picks.append((c, vv))
                if len(picks) == 10: break
            top.append(picks)
        V = [i for i in range(len(Q)) if gold[i]["validity"] == "valid" and gold[i]["concepts"]]
        rec = {k: float(np.mean([bool({c for c, _ in top[i][:k]} & set(gold[i]["concepts"])) for i in V])) for k in (1, 5, 10)}
        rec_test = {k: float(np.mean([bool({c for c, _ in top[i][:k]} & set(gold[i]["concepts"])) for i in V if i in set(test)])) for k in (1, 5, 10)}
        pred = lambda th: [(top[i][0][0], ax.get(top[i][0][0], [])) if top[i][0][1] >= th else (None, []) for i in range(len(Q))]
        best = max(np.arange(0.5, 0.99, 0.01), key=lambda th: (EL.metrics(pred(th), gold, dev)["macro_f1"]))
        res[name] = dict(recall_all=rec, recall_test=rec_test, theta=float(best), test=EL.metrics(pred(best), gold, test), dev=EL.metrics(pred(best), gold, dev), _pred=pred(best))
        print(name, json.dumps({k: v for k, v in res[name].items() if k != "_pred" and k != "dev"}, default=float)[:900], flush=True)
    res["paired_test_macro_f1"] = EL.boot(res["finetuned"]["_pred"], res["frozen"]["_pred"], gold, test, groups)
    res["paired_test_concept_acc"] = EL.boot(res["finetuned"]["_pred"], res["frozen"]["_pred"], gold, test, groups, key="concept_acc")
    for k in ("frozen", "finetuned"): res[k].pop("_pred")
    res["config"] = dict(temp=TEMP, bs=BS, lr=LR, epochs=EPOCHS, maxlen=MAXLEN, seed=SEED, train_concepts=len(pairs), held_out=len(held), steps=steps)
    json.dump(res, open(EL.OUT + "sapbert_ft_pilot_v0.json", "w"), indent=1)
    print("paired test macro-F1", res["paired_test_macro_f1"], "concept acc", res["paired_test_concept_acc"])


if __name__ == "__main__":
    main()
