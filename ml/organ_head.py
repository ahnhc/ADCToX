"""Fast organ judgment: a small network that reads the SapBERT vector of the typed text (the one mondo_index.link already
computes) and outputs the 13 organs directly. A student of the Haiku labels (distillation): it needs no extra download, takes
well under a millisecond on a CPU, and answers even when the text matches no disease name closely.

    CUDA_VISIBLE_DEVICES=1 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<copy of the cache> python ml/organ_head.py [--dry]

Training texts (never a gold concept or its parents / children), each with the organs of its concept from
linking_models.load_organ_labels (Haiku 4.5 / 5.5 labels; clinician labels win when present):
  MONDO names and up to 5 exact synonyms of every labelled concept; reviewed Haiku queries (train_queries gen/gen2);
  external corpus train mentions (MedMentions, NCBI, BC5CDR, COMETA).
768 -> 512 -> 13, binary cross-entropy; 10% of the concepts held out to stop training and set one threshold per organ.
Then the rule that combines it with the linker is chosen on the gold dev split (organ macro-F1, invalid input accepted not
above the linker alone). Writes oh_* keys into the index (v5) unless --dry.
"""
import glob, json, os, random, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P, eval_linking as EL, mondo_index as MI, linking_models as LM
from build_linking_pools import read_obo

R = P.REPO + "data/curated/"; DEV = "cuda:0" if torch.cuda.is_available() else "cpu"; AXES = MI.AXES; SEED = 3


def texts(T, labels, held):
    out = []
    for t, org in labels.items():
        if t in held or t not in T: continue
        for s in [T[t]["name"]] + T[t]["syn"][:5]: out.append((s, t))
    for f in sorted(glob.glob(R + "train_queries/review/review2_*.jsonl")):
        for x in map(json.loads, open(f)):
            if x.get("validity") == "valid" and x.get("match") is True and x["concept"] in labels and x["concept"] not in held: out.append((x["query"], x["concept"]))
    for r in map(json.loads, open(R + "external/mentions_mondo.jsonl")):
        if r["split"] == "train" and len(r["mondo"]) == 1 and r["mondo"][0] in labels and r["mondo"][0] not in held: out.append((r["mention"], r["mondo"][0]))
    return list(dict.fromkeys(out))


def embed(xs):
    if MI._IDX is None: MI.link(["x"])
    return np.concatenate([MI._embed(xs[i:i + 2048], DEV).astype(np.float32) for i in range(0, len(xs), 2048)])


def head_probs(W, Q):
    h = np.maximum(Q @ W["oh_w1"] + W["oh_b1"], 0); return 1 / (1 + np.exp(-(h @ W["oh_w2"] + W["oh_b2"])))


def train(X, Y, groups):
    rng = random.Random(SEED); torch.manual_seed(SEED); ug = sorted(set(groups)); rng.shuffle(ug); val = set(ug[: len(ug) // 10])
    iv = np.array([g in val for g in groups]); Xt, Yt = torch.from_numpy(X[~iv]).to(DEV), torch.from_numpy(Y[~iv]).to(DEV)
    net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], 512), torch.nn.ReLU(), torch.nn.Dropout(0.2), torch.nn.Linear(512, len(AXES))).to(DEV)
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4); lossf = torch.nn.BCEWithLogitsLoss(); best = (1e9, None)
    for ep in range(30):
        net.train(); perm = torch.randperm(len(Xt), device=DEV)
        for i in range(0, len(Xt), 512):
            b = perm[i:i + 512]; opt.zero_grad(); loss = lossf(net(Xt[b]), Yt[b]); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad(): vl = float(lossf(net(torch.from_numpy(X[iv]).to(DEV)), torch.from_numpy(Y[iv]).to(DEV)))
        if vl < best[0]: best = (vl, {k: v.detach().cpu().numpy().copy() for k, v in net.state_dict().items()}, ep)
    sd = best[1]; W = dict(oh_w1=sd["0.weight"].T.astype(np.float32), oh_b1=sd["0.bias"].astype(np.float32), oh_w2=sd["3.weight"].T.astype(np.float32), oh_b2=sd["3.bias"].astype(np.float32))
    pv = head_probs(W, X[iv]); thr = []
    for k in range(len(AXES)):                                   # per-organ threshold with the best F1 on the held-out concepts
        y = Y[iv][:, k] > 0; best_t = (0, 0.5)
        for t in np.arange(0.2, 0.81, 0.05):
            p = pv[:, k] >= t; tp = (p & y).sum(); f = 2 * tp / max(1, p.sum() + y.sum())
            if f > best_t[0]: best_t = (f, float(t))
        thr.append(best_t[1])
    W["oh_thr"] = np.array(thr, np.float32)
    yv = Y[iv] > 0; pp = pv >= W["oh_thr"]; f1 = [2 * (pp[:, k] & yv[:, k]).sum() / max(1, pp[:, k].sum() + yv[:, k].sum()) for k in range(len(AXES))]
    return W, dict(epochs=best[2] + 1, val_loss=best[0], val_macro_f1=float(np.mean(f1)), n_train=int((~iv).sum()), n_val=int(iv.sum()))


def gold_eval(W):
    Q = json.load(open(EL.D + "raw/queries_v0.json")); G = {x["qid"]: x for x in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [dict(G[q["qid"]], category=q["category"]) for q in Q]; groups = [q["group"] or q["qid"] for q in Q]
    dev = [i for i, g in enumerate(groups) if EL.split_of(g) == "dev"]
    links = MI.link([q["query"] for q in Q]); H = head_probs(W, embed([q["query"] for q in Q])) >= W["oh_thr"]
    def run(rule):
        out = []
        for lk, h in zip(links, H):
            ho = [AXES[k] for k in np.where(h)[0]]; lo = lk["axes"]; ok = lk.get("gate") is not False
            if rule == "linker": out.append((lk["mondo"] if lo else None, lo))
            elif rule == "head": out.append((None, ho if ok else []))
            elif rule == "fill": out.append((lk["mondo"] if lo else None, lo or (ho if ok else [])))
            elif rule == "union": out.append((lk["mondo"] if lo else None, sorted(set(lo) | set(ho if ok else []))))
        return out
    res = {r: EL.metrics(run(r), gold, dev) for r in ("linker", "head", "fill", "union")}
    return {r: dict(macro_f1=m["macro_f1"], false_accept_invalid=m["false_accept_invalid"], coverage=m["coverage"]) for r, m in res.items()}


def main():
    T = read_obo(); held = LM.gold_held(T); labels, stats = LM.load_organ_labels(); MI.link(["x"])
    data = texts(T, labels, held); print("labels", len(labels), "texts", len(data), flush=True)
    X = embed([q for q, _ in data]); Y = np.array([[a in labels[t] for a in AXES] for _, t in data], np.float32)
    W, info = train(X, Y, [t for _, t in data]); print(json.dumps(info), flush=True)
    ev = gold_eval(W); print(json.dumps(ev, indent=1))
    # rules the app implements (recommend.resolve): the linker alone, or the judgment where the linker finds no organ
    rule = max((r for r in ("linker", "fill") if (ev[r]["false_accept_invalid"] or 0) <= (ev["linker"]["false_accept_invalid"] or 0)), key=lambda r: ev[r]["macro_f1"])
    W["oh_rule"] = np.array(rule)
    res = dict(label_stats={k: v for k, v in stats.items() if k.startswith("n_")}, n_texts=len(data), train=info, dev=ev, chosen_rule=rule)
    json.dump(res, open(P.REPO + "ml/results/benchmarks/organ_head_v1.json", "w"), indent=1, default=float); print("chosen", rule)
    if "--dry" in sys.argv: return
    path = MI.C + "mondo_index.npz"; z = dict(np.load(path, allow_pickle=True)); z.update(W); z["version"] = np.array("v5")
    np.savez(path, **z); print("index v5 written:", path)


if __name__ == "__main__":
    main()
