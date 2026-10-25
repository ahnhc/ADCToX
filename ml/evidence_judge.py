"""Evidence reader for the from-scratch judge: organs of a MONDO concept read from its ontology record, not from its name.

    CUDA_VISIBLE_DEVICES=<gpu or empty> ADC_RESEARCH_MODE=1 ADCTOX_LABELS=v51 ADCTOX_CACHE=<cache> \
        python ml/evidence_judge.py train --backbone /data/hyeongchanahn/adctox/work/pretrain_p3_48h --tag ev2s7 [--epochs 3] [--seed 7]
    python ml/evidence_judge.py score --tag ev2s7 --x2 x2s7       # gold and known (dev) with the evidence rule, from stored rows

Why: the name-only judge links most unseen-disease questions to the right MONDO concept or a close relative (the index holds every
MONDO name), but such a concept has no organ label, so the judge falls back to guessing from the name. The ontology still knows a
lot about it: definition, parents, anatomical location, causal genes and HPO phenotypes with frequencies, the same record the v5
labellers read. This model learns to read that record. Organ labels of a perfectly linked concept read this way score 0.863 on
gold_v0 dev (the v5.1 label of the gold concept), so reading is not the bottleneck; learning to read without a large LM is.

Rule (offline, on the judge's stored rows): linked concept with a label -> the label (as before); linked concept without a label
-> this model's organs for that concept; not linked -> the name judge's organs (as before).

Model: the from-scratch pretrained encoder (ml/scratch_pretrain.py; no label seen before) with an organ head, trained on evidence
texts. It is separate from the name judge, so held-out concepts are unseen by both. Training
concepts are the labelled ones (ADCTOX_LABELS); gold concepts and their parents and children have no label and are never trained
on, and their names are blanked from the parents/grandparents/children of training records. 10% of the training concepts are
held out for per-organ thresholds. Record fields used: name, synonyms, definition, parents, grandparents, children, MONDO
locations and features, genes, HPO phenotypes (data/curated/concept_organs/v5/input/concepts.jsonl); never xrefs or labels.
-> $ADCTOX_CACHE/evidence_judge_<tag>/ (model.pt, calibration.json, pred.npz: organ probabilities for every concept)
"""
import argparse, json, os, random, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P

EVID = P.REPO + "data/curated/concept_organs/v5/input/concepts.jsonl"
MAXLEN = int(os.environ.get("EV_MAXLEN", "192"))


def records(): return {r["id"]: r for r in map(json.loads, open(EVID, encoding="utf-8"))}


def text(r, blank=frozenset(), drop_def=False):
    """one evidence string; names in `blank` (gold-related concepts) are left out of the relatives."""
    rel = lambda xs: [x for x in xs if x not in blank]
    parts = [r["name"]]
    if r.get("synonyms"): parts.append("also " + ", ".join(r["synonyms"][:4]))
    if r.get("definition") and not drop_def: parts.append(r["definition"])
    if r.get("hpo_phenotypes"): parts.append("phenotypes: " + "; ".join(str(h) for h in r["hpo_phenotypes"][:15]))
    if r.get("mondo_locations"): parts.append("location: " + ", ".join(map(str, r["mondo_locations"])))
    if r.get("mondo_features"): parts.append("features: " + ", ".join(map(str, r["mondo_features"])))
    if rel(r.get("parents", [])): parts.append("is a: " + ", ".join(rel(r["parents"])))
    if rel(r.get("grandparents", [])): parts.append("under: " + ", ".join(rel(r["grandparents"])))
    if rel(r.get("children_sample", [])): parts.append("kinds: " + ", ".join(rel(r["children_sample"])[:5]))
    if r.get("genes"): parts.append("genes: " + ", ".join(map(str, r["genes"][:6])))
    return " . ".join(parts)


def setup(backbone):
    import scratch_judge as SJ
    SJ.DEV = "cuda:0" if torch.cuda.is_available() else "cpu"; SJ.MAXLEN = MAXLEN
    if SJ.DEV == "cpu": torch.set_num_threads(int(os.environ.get("EV_THREADS", "32")))
    m = SJ.Enc(hf=backbone)
    if SJ.DEV == "cpu": m.bb.gradient_checkpointing_disable()                             # memory is not the limit on the CPU; speed is
    return SJ, m.to(SJ.DEV), SJ.HFTok(backbone)


def probs(SJ, model, tk, texts, bs=64):
    model.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=SJ.DEV != "cpu"): zo, _, _ = model(SJ.encode(tk, texts[i:i + bs]))
            out.append(torch.sigmoid(zo.float()).cpu().numpy())
    return np.concatenate(out)


def train(a):
    import linking_models as LM, tuning_ledger as TL
    from build_linking_pools import read_obo
    rng = random.Random(a.seed); torch.manual_seed(a.seed); np.random.seed(a.seed)
    SJ, model, tk = setup(a.backbone); AX = SJ.AXES
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels(); R = records()
    blank = frozenset(n for t in held if t in T for n in [T[t]["name"]])
    cs = sorted(c for c in labels if c in R and c not in held); rng.shuffle(cs); val = sorted(cs[: len(cs) // 10]); tr = [c for c in cs if c not in set(val)]
    print("train concepts", len(tr), "held out", len(val), flush=True)
    y = lambda c: np.array([a_ in labels[c] for a_ in AX], np.float32)
    out = P.CACHE + f"evidence_judge_{a.tag}/"; os.makedirs(out, exist_ok=True)
    TL.write_card(a.tag, dict(tag=a.tag, stage=a.stage, note=a.note, started=time.strftime("%Y-%m-%d %H:%M"), args=vars(a), git=TL.git_state(),
                              data=dict(evidence=EVID, n_train=len(tr), n_val=len(val), labels=os.environ.get("ADCTOX_LABELS", "v4")), backbone=dict(model=a.backbone)))
    opt = torch.optim.AdamW([{"params": [p for n, p in model.named_parameters() if not n.startswith("organ.")], "lr": a.lr},
                             {"params": model.organ.parameters(), "lr": a.lr * 30}], weight_decay=0.01)
    bce = torch.nn.BCEWithLogitsLoss(); steps = a.epochs * (len(tr) // a.bs); step = 0; t0 = time.time()
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / 200) * max(0.0, 1 - s / max(1, steps)))
    for ep in range(a.epochs):
        rng.shuffle(tr); model.train(); ex = [(c, text(R[c], blank, drop_def=rng.random() < a.drop_def)) for c in tr]
        batches = []                                                                      # similar lengths together (less padding), batch order random
        for i in range(0, len(ex), a.bs * 50):
            blk = sorted(ex[i:i + a.bs * 50], key=lambda e: len(e[1])); batches += [blk[j:j + a.bs] for j in range(0, len(blk) - a.bs + 1, a.bs)]
        rng.shuffle(batches)
        for bb in batches:
            b = [c for c, _ in bb]; X = [t for _, t in bb]
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=SJ.DEV != "cpu"): zo, _, _ = model(SJ.encode(tk, X))
            loss = bce(zo.float(), torch.from_numpy(np.stack([y(c) for c in b])).to(zo.device))
            opt.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step(); step += 1
            if step % 50 == 0: print(f"ep {ep} step {step}/{steps} loss {loss.item():.4f} {time.time() - t0:.0f}s", flush=True)
            if a.smoke and step >= 20: break
        if a.smoke: break
    vc = val[: 200 if a.smoke else None]; pv = probs(SJ, model, tk, [text(R[c], blank) for c in vc]); yv = np.stack([y(c) for c in vc]) > 0
    thr = [float(max(np.arange(0.1, 0.91, 0.05), key=lambda t_: 2 * ((pv[:, k] >= t_) & yv[:, k]).sum() / max(1, (pv[:, k] >= t_).sum() + yv[:, k].sum()))) for k in range(13)]
    f1 = float(np.mean([2 * ((pv[:, k] >= thr[k]) & yv[:, k]).sum() / max(1, (pv[:, k] >= thr[k]).sum() + yv[:, k].sum()) for k in range(13)]))
    print("val concepts", len(vc), "macro F1", round(f1, 4), flush=True)
    ids = sorted(R); pa = probs(SJ, model, tk, [text(R[c], blank if c not in held else frozenset()) for c in ids[: 300 if a.smoke else None]])
    torch.save(model.state_dict(), out + "model.pt"); np.savez(out + "pred.npz", ids=np.array(ids[: len(pa)]), p=pa.astype(np.float16))
    json.dump(dict(thr=thr, val_f1=f1, backbone=a.backbone, maxlen=MAXLEN), open(out + "calibration.json", "w"), indent=1)
    c = json.load(open(TL.CARDS + f"{a.tag}.json")); c.update(finished=time.strftime("%Y-%m-%d %H:%M"), results=dict(val_f1=f1, thr=thr)); TL.write_card(a.tag, c)
    print("->", out, flush=True)


def score(a):
    """dev macro-F1 (English) of the judge's stored rows with the evidence rule, on gold_v0, gold_v1 and known."""
    import gold_v1 as G, eval_linking as EL, known_eval as KE, linking_models as LM, scratch_judge as SJ
    B = P.REPO + "ml/results/benchmarks/"; d = P.CACHE + f"evidence_judge_{a.tag}/"
    Z = np.load(d + "pred.npz"); thr = np.array(json.load(open(d + "calibration.json"))["thr"]); ev = dict(zip(map(str, Z["ids"]), Z["p"].astype(np.float32)))
    labels, _ = LM.load_organ_labels()
    def apply(rows):
        out, n = [], 0
        for r in rows:
            c = (r or {}).get("concept")
            if c and c not in labels and c in ev: r = dict(r, organs=[SJ.AXES[k] for k in np.where(ev[c] >= thr)[0]]); n += 1
            out.append(r)
        return out, n
    P_ = lambda rows: [((r or {}).get("concept"), (r or {}).get("organs", [])) for r in rows]
    Gs, groups = G.golds(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == "dev"]
    Q = KE.questions()["en"]; kg = [dict(validity="valid", concepts=[q["id"]], best=q["id"], organs=q["organs"], category=q["kind"]) for q in Q]
    kx = [i for i, q in enumerate(Q) if q["split"] == "dev"]; res = {}
    for name, use in (("judge", False), ("judge + evidence", True)):
        gr = json.load(open(B + f"bench_scratch_{a.x2}.json"))["per"]["en"]; kr = json.load(open(B + f"known_{a.x2}.json"))["per"]["en"]
        ng = nk = 0
        if use: (gr, ng), (kr, nk) = apply(gr), apply(kr)
        jx = [i for i in ix if gr[i] is not None]
        res[name] = dict(gold_v0=round(EL.metrics(P_(gr), Gs["gold_v0"], jx)["macro_f1"], 4), gold_v1=round(EL.metrics(P_(gr), Gs["gold_v1"], jx)["macro_f1"], 4),
                         known=round(EL.metrics(P_(kr), kg, kx)["macro_f1"], 4), evidence_rows_gold=ng, evidence_rows_known=nk)
    json.dump(dict(tag=a.tag, x2=a.x2, split="dev", scores=res), open(B + f"evidence_{a.tag}_{a.x2}.json", "w"), indent=1); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["train", "score"]); ap.add_argument("--backbone", help="pretrained from-scratch encoder (ml/scratch_pretrain.py output)"); ap.add_argument("--tag", required=True)
    ap.add_argument("--x2"); ap.add_argument("--epochs", type=int, default=3); ap.add_argument("--bs", type=int, default=16); ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--drop-def", type=float, default=0.2); ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--stage", default="X2 evidence reader"); ap.add_argument("--note", default="")
    a = ap.parse_args(); {"train": train, "score": score}[a.cmd](a)
