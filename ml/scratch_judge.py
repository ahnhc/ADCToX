"""A judge trained from scratch: a small Transformer encoder with random initial weights, its own tokenizer, and only this
repository's data (plus UMLS when ml/umls_build.py has made its files). No pretrained model of any kind.

    CUDA_VISIBLE_DEVICES=0 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache copy> python ml/scratch_judge.py --tag x1 --stage "X1 ..." \
        [--seed 7] [--drop ko3,umls] [--compare-to s2ds7]
    -> $ADCTOX_CACHE/scratch_judge_<tag>/ (model.pt, tokenizer.json, index.npz, calibration.json), run card ml/results/tuning/<tag>.json

Why: the tuned Gemma learns organs for English names but carries little of it to Korean names it has not seen (S2,
ml/docs/data_inventory.md section 6): inside Gemma a Korean name and its English name are not the same disease. A model built
from scratch can learn both languages in one space from the start, and Korean disease names are compositional (신/콩팥 renal,
간 hepatic, 폐 pulmonary), which character-level input can use. It is also small enough to run on any computer.

Text: Unicode NFD, so a Hangul syllable becomes its jamo and a Korean typo changes one or two symbols, not the whole token.
Tokenizer: BPE (HF tokenizers) trained on every training text and pair, VOCAB symbols.
Encoder: DIM wide, LAYERS layers, HEADS heads, pre-norm, mean pooling. Outputs: valid (1), organ (13), vec (PROJ, unit length).
Stage 1 (names): InfoNCE over same-disease name pairs (judge_data.pairs: MONDO synonyms, Korean-English MONDO names, KCD
Korean-English names, every training text with its concept name, UMLS synonyms), in-batch negatives, tau TAU.
Stage 2 (judge): the gemma_judge2 items (judge_data.items): organ and valid BCE, with the pair loss kept on.
Pretrained backbone (--backbone, e.g. BAAI/bge-m3, FacebookAI/xlm-roberta-large, intfloat/multilingual-e5-large,
Qwen/Qwen3-Embedding-0.6B): the same outputs, stages, data, calibration and rule on top of that model (its own tokenizer, text as
typed, mean pooling, backbone lr --lr, heads --head-lr); the resolved model revision goes on the run card.
Held out: 10% of the concepts (their items and pairs), for model selection, organ calibration and theta; 10% of the junk (valid
threshold), as gemma_judge2. Calibration, valid threshold and the final organ rule are those of the Gemma single benchmark:
nearest MONDO name (index of every MONDO name and synonym, embedded by this encoder) with cosine >= theta -> that concept's
organs, else the organ head. theta is chosen on the held-out concepts, never on the evaluation questions.
"""
import argparse, collections, json, math, os, random, sys, time, unicodedata
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P

AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
VOCAB, DIM, LAYERS, HEADS, PROJ, MAXLEN, TAU = 16000, 384, 6, 6, 256, 48, 0.05
DEV = "cuda:0"


def prep(t): return unicodedata.normalize("NFD", str(t).strip())


def train_tokenizer(texts, path):
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers, normalizers
    tk = Tokenizer(models.BPE(unk_token="[UNK]")); tk.normalizer = normalizers.NFD()
    tk.pre_tokenizer = pre_tokenizers.Sequence([pre_tokenizers.Whitespace(), pre_tokenizers.Digits(individual_digits=True)])
    tk.train_from_iterator(texts, trainers.BpeTrainer(vocab_size=VOCAB, min_frequency=2, special_tokens=["[PAD]", "[UNK]", "[CLS]"]))
    tk.save(path); return tk


def hf_path(name):
    if os.path.isdir(name): return name                                      # a local model folder (ml/scratch_pretrain.py)
    from huggingface_hub import snapshot_download
    return snapshot_download(name, cache_dir=os.environ.get("HF_CACHE", os.path.expanduser("~/.cache/huggingface/hub")))


class HFTok:
    """a pretrained model's tokenizer, text as typed."""
    def __init__(self, name):
        import transformers as T
        self.tk = T.AutoTokenizer.from_pretrained(hf_path(name))
    def __call__(self, texts):
        e = self.tk([str(t).strip() for t in texts], padding=True, truncation=True, max_length=MAXLEN, return_tensors="pt")
        return e["input_ids"].to(DEV), e["attention_mask"].to(DEV).bool()


class Enc(torch.nn.Module):
    def __init__(self, vocab=None, hf=None):
        super().__init__()
        if hf:
            import transformers as T
            self.bb = T.AutoModel.from_pretrained(hf_path(hf)); D = self.bb.config.hidden_size
            if self.bb.supports_gradient_checkpointing: self.bb.gradient_checkpointing_enable()   # MPNet (BioLORD) has none
        else:
            D = DIM; self.emb = torch.nn.Embedding(vocab, DIM, padding_idx=0); self.pos = torch.nn.Embedding(MAXLEN + 1, DIM)
            layer = torch.nn.TransformerEncoderLayer(DIM, HEADS, 4 * DIM, dropout=0.1, batch_first=True, norm_first=True, activation="gelu")
            self.enc = torch.nn.TransformerEncoder(layer, LAYERS, enable_nested_tensor=False); self.norm = torch.nn.LayerNorm(DIM)
        self.organ = torch.nn.Linear(D, 13); self.valid = torch.nn.Linear(D, 1); self.proj = torch.nn.Linear(D, PROJ)
    def forward(self, b):
        ids, m = b
        if hasattr(self, "bb"): h = self.bb(input_ids=ids, attention_mask=m.long()).last_hidden_state
        else: h = self.norm(self.enc(self.emb(ids) + self.pos(torch.arange(ids.shape[1], device=ids.device))[None], src_key_padding_mask=~m))
        h = (h * m[..., None]).sum(1) / m.sum(1, keepdim=True).clamp(min=1)
        return self.organ(h), self.valid(h)[:, 0], torch.nn.functional.normalize(self.proj(h), dim=-1)


def encode(tk, texts):
    if isinstance(tk, HFTok): return tk(texts)
    rows = [[2] + e.ids[:MAXLEN] for e in tk.encode_batch([prep(t) for t in texts])]
    L = max(map(len, rows)); ids = torch.tensor([r + [0] * (L - len(r)) for r in rows], device=DEV); return ids, ids != 0


def predict(model, tk, texts, bs=None):
    bs = bs or (256 if isinstance(tk, HFTok) else 1024); model.eval(); out = [[], [], []]
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for i in range(0, len(texts), bs):
            for k, z in enumerate(model(encode(tk, texts[i:i + bs]))): out[k].append(z.float().cpu().numpy())
    return [np.concatenate(o) if o else np.zeros((0,)) for o in out]


def nce(model, tk, batch):
    """symmetric InfoNCE over (a, b, concept) pairs; pairs of the same concept are not negatives of each other."""
    _, _, va = model(encode(tk, [p[0] for p in batch])); _, _, vb = model(encode(tk, [p[1] for p in batch]))
    s = va @ vb.T / TAU; c = [p[2] or f"_{k}" for k, p in enumerate(batch)]
    same = torch.tensor([[x == y for y in c] for x in c], device=DEV) & ~torch.eye(len(batch), dtype=torch.bool, device=DEV)
    s = s.masked_fill(same, -1e4); y = torch.arange(len(batch), device=DEV)
    return (torch.nn.functional.cross_entropy(s, y) + torch.nn.functional.cross_entropy(s.T, y)) / 2


def load(folder):
    from tokenizers import Tokenizer
    cfg = json.load(open(folder + "calibration.json"))
    if cfg.get("backbone"): tk = HFTok(cfg["backbone"]); model = Enc(hf=cfg["backbone"]).to(DEV)
    else: tk = Tokenizer.from_file(folder + "tokenizer.json"); model = Enc(tk.get_vocab_size()).to(DEV)
    model.load_state_dict(torch.load(folder + "model.pt", map_location=DEV)); model.eval()
    Z = np.load(folder + "index.npz", allow_pickle=True); return model, tk, cfg, Z["E"], [str(x) for x in Z["ids"]]


def judge(texts, folder):
    """-> [dict(concept, organs, valid, sim)] by the rule in the module docstring."""
    import linking_models as LM
    model, tk, cfg, E, ids = load(folder); labels, _ = LM.load_organ_labels()
    zo, zv, va = predict(model, tk, list(texts)); S = va @ E.T; j = S.argmax(1); s = S.max(1)
    po = 1 / (1 + np.exp(-zo / np.array(cfg["temp"]))); pv = 1 / (1 + np.exp(-zv)); rows = []
    for k in range(len(texts)):
        if pv[k] < cfg["vthr"]: rows.append(dict(concept=None, organs=[], valid=float(pv[k]))); continue
        c = ids[j[k]] if s[k] >= cfg["theta"] else None
        lo = sorted(labels.get(c, []), key=AXES.index) if c else []
        rows.append(dict(concept=c, organs=lo or [AXES[a] for a in np.where(po[k] >= np.array(cfg["thr"]))[0]], valid=float(pv[k]), sim=float(s[k])))
    return rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--stage", default="unstaged"); ap.add_argument("--note", default="")
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--drop", default=""); ap.add_argument("--compare-to", default=None)
    ap.add_argument("--pre-epochs", type=int, default=6); ap.add_argument("--epochs", type=int, default=6); ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--bs", type=int, default=256); ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--backbone", default=None, help="a pretrained Hugging Face model instead of the random encoder")
    ap.add_argument("--head-lr", type=float, default=1e-3, help="with --backbone: lr of the output layers")
    ap.add_argument("--distill", default=None, help="teacher npz (ml/distill_teacher.py): adds a loss toward the teacher's organ and validity probabilities")
    ap.add_argument("--distill-w", type=float, default=1.0, help="weight of the distillation loss")
    a = ap.parse_args(); rng = random.Random(a.seed); torch.manual_seed(a.seed); np.random.seed(a.seed)
    import tuning_ledger as TL, judge_data as JD, linking_models as LM
    from build_linking_pools import read_obo
    drop = {x for x in a.drop.split(",") if x}; unknown = drop - set(JD.SOURCES) - set(JD.PAIR_SOURCES)
    if unknown: raise SystemExit(f"unknown sources {sorted(unknown)}")
    if a.backbone:
        rev = os.path.basename(hf_path(a.backbone))
        cfg = dict(backbone=a.backbone, revision=rev, proj=PROJ, maxlen=MAXLEN, tau=TAU, text="as typed, model tokenizer", init="pretrained")
    else: cfg = dict(vocab=VOCAB, dim=DIM, layers=LAYERS, heads=HEADS, proj=PROJ, maxlen=MAXLEN, tau=TAU, text="NFD + BPE", init="random")
    TL.write_card(a.tag, dict(tag=a.tag, stage=a.stage, note=a.note, compare_to=a.compare_to, started=time.strftime("%Y-%m-%d %H:%M"), args=vars(a),
                              git=TL.git_state(), data=TL.manifest(cache=P.CACHE), backbone=dict(model=a.backbone or "scratch transformer (no pretrained weights)", **cfg)))
    items, junk_val, info = JD.items(drop=drop, seed=a.seed); pairs = JD.pairs(drop=drop, seed=a.seed, items_=items)
    T = read_obo(); labels, _ = LM.load_organ_labels()
    concepts = sorted({x[1] for x in items if x[1] is not None}); rng.shuffle(concepts); val_c = set(concepts[: len(concepts) // 10])
    train = [x for x in items if x[1] is None or x[1] not in val_c]; val = [x for x in items if x[1] is not None and x[1] in val_c]
    ptrain = [p for p in pairs if p[2] not in val_c]
    if a.smoke: train, val, ptrain = train[::50], val[::20], ptrain[::50]
    outs = lambda x: [o for o, ok in (("organ", x[2] is not None), ("align", x[1] is not None), ("valid", True)) if ok]
    chk, bad = TL.checks(items, outs)
    TL.write_card(a.tag, dict(checks=chk, items=dict(total=len(items), train=len(train), val=len(val), junk_copies=JD.JUNK_COPIES, **info,
                  by_source=dict(collections.Counter(x[6] for x in train)), pairs=len(ptrain), pairs_by_source=dict(collections.Counter(p[3] for p in ptrain)))))
    if bad: raise SystemExit("pre-training checks failed: " + "; ".join(bad))
    KD = None
    if a.distill:                                                                         # teacher texts naming a validation concept are left out
        import tuning_ledger as TL
        Z = dict(np.load(a.distill, allow_pickle=True))                                   # read each array once (npz members load on every access)
        vn = {TL.norm(n) for t in val_c if t in T for n in [T[t]["name"]] + T[t]["syn"]} | {TL.norm(x[0]) for x in val}
        tx = [str(t) for t in Z["texts"]]; keep = [k for k, t in enumerate(tx) if TL.norm(t) not in vn]
        KD = dict(texts=[tx[k] for k in keep], organ=Z["organ"][keep].astype(np.float32), valid=Z["valid"][keep].astype(np.float32))
        TL.write_card(a.tag, dict(distill=dict(file=a.distill, tags=[str(x) for x in Z["tags"]], texts=len(keep), dropped_val=len(tx) - len(keep), weight=a.distill_w)))
        print("distill texts", len(keep), "dropped (validation concepts)", len(tx) - len(keep), flush=True)
    out = P.CACHE + f"scratch_judge_{a.tag}/"; os.makedirs(out, exist_ok=True)
    corpus = [x[0] for x in items] + [t for p in pairs for t in p[:2]] + [n for t in T.values() for n in [t["name"]] + t["syn"]]
    if a.backbone: tk = HFTok(a.backbone); model = Enc(hf=a.backbone).to(DEV)
    else: tk = train_tokenizer(corpus, out + "tokenizer.json"); model = Enc(tk.get_vocab_size()).to(DEV)
    print("parameters", sum(p.numel() for p in model.parameters()), flush=True)
    bce = torch.nn.BCEWithLogitsLoss(reduction="none"); t0 = time.time()

    def run(epochs, step_fn, n_steps, lr):
        if a.backbone:
            bb = [p for n, p in model.named_parameters() if n.startswith("bb.")]; hd = [p for n, p in model.named_parameters() if not n.startswith("bb.")]
            opt = torch.optim.AdamW([dict(params=bb, lr=lr), dict(params=hd, lr=a.head_lr)], weight_decay=0.01)
        else: opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
        tot = epochs * n_steps
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / 300) * 0.5 * (1 + math.cos(math.pi * min(1, s / tot))))
        return opt, sched

    # ---- stage 1: names
    nb = len(ptrain) // a.bs + 1; opt, sched = run(a.pre_epochs, None, nb, a.lr)
    for ep in range(a.pre_epochs):
        model.train(); rng.shuffle(ptrain)
        for s in range(nb):
            b = ptrain[s * a.bs:(s + 1) * a.bs]
            if len(b) < 8: continue
            with torch.autocast("cuda", dtype=torch.bfloat16): loss = nce(model, tk, b)
            opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step()
            if s % 400 == 0: print(f"names ep {ep} step {s}/{nb} nce {loss.item():.3f} {time.time() - t0:.0f}s", flush=True)
    # ---- stage 2: judge (organ, valid) with the pair loss kept on
    nb = len(train) // a.bs + 1; opt, sched = run(a.epochs, None, nb, a.lr / 2); best = (1e9, None)
    for ep in range(a.epochs):
        model.train(); idx = list(range(len(train))); rng.shuffle(idx)
        for s in range(nb):
            b = [train[j] for j in idx[s * a.bs:(s + 1) * a.bs]]
            if not b: continue
            with torch.autocast("cuda", dtype=torch.bfloat16):
                zo, zv, _ = model(encode(tk, [x[0] for x in b])); m = torch.tensor([x[2] is not None for x in b], device=DEV)
                yo = torch.from_numpy(np.stack([x[2] if x[2] is not None else np.zeros(13, np.float32) for x in b])).to(DEV)
                L = dict(valid=bce(zv.float(), torch.tensor([x[3] for x in b], device=DEV)).mean())
                if m.any(): L["organ"] = bce(zo.float(), yo).mean(1)[m].mean()
                L["nce"] = 0.5 * nce(model, tk, [ptrain[rng.randrange(len(ptrain))] for _ in range(a.bs)])
                if KD:
                    kk = [rng.randrange(len(KD["texts"])) for _ in range(a.bs)]; zo2, zv2, _ = model(encode(tk, [KD["texts"][k] for k in kk]))
                    L["kd"] = a.distill_w * (bce(zo2.float(), torch.from_numpy(KD["organ"][kk]).to(DEV)).mean() + 0.5 * bce(zv2.float(), torch.from_numpy(KD["valid"][kk]).to(DEV)).mean())
                loss = sum(L.values())
            opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step()
            if s % 400 == 0: print(f"judge ep {ep} step {s}/{nb} " + " ".join(f"{k} {v.item():.3f}" for k, v in L.items()) + f" {time.time() - t0:.0f}s", flush=True)
        zo, zv, _ = predict(model, tk, [x[0] for x in val]); mo = np.array([x[2] is not None for x in val])
        yo = np.stack([x[2] for x in val if x[2] is not None]); vl = float(bce(torch.from_numpy(zo[mo]), torch.from_numpy(yo).float()).mean())
        print(f"epoch {ep} val organ loss {vl:.4f}", flush=True)
        TL.write_card(a.tag, dict(epochs=[*json.load(open(TL.CARDS + f"{a.tag}.json")).get("epochs", [])[:ep], dict(epoch=ep + 1, val_organ_loss=round(vl, 4), minutes=round((time.time() - t0) / 60, 1))]))
        if vl < best[0]: best = (vl, ep, {k: v.detach().clone() for k, v in model.state_dict().items()})
    model.load_state_dict(best[2]); torch.save(best[2], out + "model.pt")
    # ---- calibration on the held-out concepts and junk (as gemma_judge2)
    zo, zv, va = predict(model, tk, [x[0] for x in val]); yo = np.stack([x[2] for x in val if x[2] is not None]); zm = zo[mo]
    lf = lambda z, y: float(bce(torch.from_numpy(z), torch.from_numpy(y).float()).mean()); temp, thr = [], []
    for k in range(13):
        tz = min(np.arange(0.5, 3.01, 0.1), key=lambda s_: lf(zm[:, k] / s_, yo[:, k])); p = 1 / (1 + np.exp(-zm[:, k] / tz)); y = yo[:, k] > 0
        tb = max(np.arange(0.2, 0.81, 0.05), key=lambda t_: 2 * ((p >= t_) & y).sum() / max(1, (p >= t_).sum() + y.sum())); temp.append(float(tz)); thr.append(float(tb))
    _, zj, _ = predict(model, tk, junk_val); pr = 1 / (1 + np.exp(-np.concatenate([zv, zj]))); yl = np.r_[np.ones(len(zv)), np.zeros(len(zj))]
    grid = list(np.arange(0.05, 0.96, 0.05)) + [0.97, 0.98, 0.99, 0.995]
    vthr = float(min((t_ for t_ in grid if (pr[yl == 0] >= t_).mean() == 0), default=0.995))
    # ---- index of every MONDO name and synonym, and theta on the held-out concepts
    names = [(t, n) for t, x in T.items() if not x["name"].startswith("obsolete") for n in [x["name"]] + x["syn"]]
    _, _, E = predict(model, tk, [n for _, n in names]); ids = np.array([t for t, _ in names])
    np.savez(out + "index.npz", E=E.astype(np.float16), ids=ids)
    S = va[mo] @ E.T.astype(np.float32); jj = S.argmax(1); ss = S.max(1); po = 1 / (1 + np.exp(-zm / np.array(temp)))
    head = po >= np.array(thr); link = np.array([[a in labels.get(str(ids[j]), ()) for a in AXES] for j in jj])
    def f1(pred):
        f = [2 * (pred[:, k] & (yo[:, k] > 0)).sum() / max(1, pred[:, k].sum() + (yo[:, k] > 0).sum()) for k in range(13)]; return float(np.mean(f))
    thetas = {round(float(t_), 2): f1(np.where(((ss >= t_) & link.any(1))[:, None], link, head)) for t_ in np.arange(0.5, 1.001, 0.05)}
    theta = max(thetas, key=thetas.get)
    json.dump(dict(temp=temp, thr=thr, vthr=vthr, theta=theta, **cfg), open(out + "calibration.json", "w"), indent=1)
    res = dict(epochs_best=best[1] + 1, val_organ_loss=round(best[0], 4), valid_threshold=vthr, theta=theta, theta_val_f1=thetas,
               real_accepted=float((pr[yl == 1] >= vthr).mean()), minutes=round((time.time() - t0) / 60, 1))
    TL.write_card(a.tag, dict(calibration=dict(vthr=vthr, theta=theta), results=res, finished=time.strftime("%Y-%m-%d %H:%M"))); TL.render()
    print(json.dumps(res, indent=1), "->", out)


if __name__ == "__main__":
    main()
