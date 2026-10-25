"""A Jev-style organ judge on Gemma 4 E2B: the text part of the model with LoRA adapters and a 13-way probability head (no
text generation), distilled from the Haiku concept-organ labels; English and Korean input.

    CUDA_VISIBLE_DEVICES=1 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache copy> HF_HOME=/data/hyeongchanahn/hf \
        python ml/gemma_judge.py --layers 35 --tag full      # all decoder layers
    ... --layers 18 --tag half                                 # only the first 18 layers (half the size and time)

Prompt: "Condition: <text>\\nOrgans it directly affects:"; the head reads the hidden state of the last prompt token.
Training texts = ml/organ_head.texts (names, synonyms, reviewed queries, corpus mentions) + Korean names, everyday words and
symptoms of the disease profiles; gold concepts and relatives excluded. 10% of the concepts are held out: early stopping,
per-organ temperature (calibration, as Jev aims for) and per-organ thresholds. Then the gold dev split: the judge alone and in
place of the small head under the app's 'fill' rule. Weights: $ADCTOX_CACHE/gemma_judge_<tag>/ (LoRA, head, calibration).
"""
import argparse, json, os, random, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P, eval_linking as EL, mondo_index as MI, linking_models as LM, organ_head as OH, suggest as SG
from build_linking_pools import read_obo

GEMMA = os.environ.get("GEMMA_MODEL", "google/gemma-4-E2B")                 # GEMMA_MODEL / GEMMA_REV: another Gemma 4 size (e.g. E4B)
REV = os.environ.get("GEMMA_REV", "d29ff6b45f081a49ee2733a859c9c9c2d95d1a6f" if GEMMA == "google/gemma-4-E2B" else None)
AXES = MI.AXES; DEV = "cuda:0"
PROMPT = "Condition: {}\nOrgans it directly affects:"


def korean_texts(labels, held):
    out = []
    for p in SG.profiles():
        if p["id"] in labels and p["id"] not in held:
            for k in p.get("ko", []) + p.get("ko_lay", []) + p.get("symptoms_ko", [])[:3] + p.get("care_ko", [])[:2]: out.append((k, p["id"]))
    return out


def load_backbone(layers):
    import transformers as T
    from huggingface_hub import snapshot_download
    path = snapshot_download(GEMMA, revision=REV, cache_dir=os.environ.get("GEMMA_CACHE", "/data/hyeongchanahn/hf/hub"))
    full = T.AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16)
    lm = full.model.language_model                                   # text decoder only; vision and audio towers are dropped
    if layers < len(lm.layers): lm.layers = lm.layers[:layers]      # stop after the first layers; the per-layer tables keep their shape
    del full
    lm.gradient_checkpointing_enable(); lm.config.use_cache = False
    return T.AutoTokenizer.from_pretrained(path), lm, path


class Judge(torch.nn.Module):
    def __init__(self, lm, hidden):
        super().__init__(); self.lm = lm; self.head = torch.nn.Linear(hidden, len(AXES))
    def forward(self, ids, mask):
        h = self.lm(input_ids=ids, attention_mask=mask).last_hidden_state
        last = mask.sum(1) - 1                                       # right padding: the last real token
        return self.head(h[torch.arange(len(h)), last].float())


def batches(tok, items, bs, shuffle, rng):
    idx = list(range(len(items)))
    if shuffle: rng.shuffle(idx)
    for i in range(0, len(idx), bs):
        b = [items[j] for j in idx[i:i + bs]]
        enc = tok([PROMPT.format(t) for t, _ in b], return_tensors="pt", padding=True, truncation=True, max_length=48)
        yield enc["input_ids"], enc["attention_mask"], b


def predict(model, tok, texts, bs=128):
    model.eval(); out = []
    with torch.no_grad():
        for ids, mask, _ in batches(tok, [(t, None) for t in texts], bs, False, None):
            out.append(model(ids.to(DEV), mask.to(DEV)).float().cpu().numpy())
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--layers", type=int, default=35); ap.add_argument("--tag", default="full")
    ap.add_argument("--rank", type=int, default=16); ap.add_argument("--epochs", type=int, default=2); ap.add_argument("--lr", type=float, default=2e-4)
    a = ap.parse_args(); rng = random.Random(5); torch.manual_seed(5)
    from peft import LoraConfig, get_peft_model
    T_ = read_obo(); held = LM.gold_held(T_); labels, _ = LM.load_organ_labels()
    data = OH.texts(T_, labels, held) + korean_texts(labels, held); data = list(dict.fromkeys(data))
    concepts = sorted({t for _, t in data}); rng.shuffle(concepts); val_c = set(concepts[: len(concepts) // 10])
    Y = {t: np.array([a_ in labels[t] for a_ in AXES], np.float32) for t in concepts}
    train = [(q, t) for q, t in data if t not in val_c]; val = [(q, t) for q, t in data if t in val_c]
    print(f"texts {len(data)} (korean {sum(any('가' <= c <= '힣' for c in q) for q, _ in data)}), train {len(train)}, val {len(val)}", flush=True)
    Q = json.load(open(EL.D + "raw/queries_v0.json")); links = MI.link([q["query"] for q in Q]); MI.close(); torch.cuda.empty_cache()   # linker first, then Gemma
    tok, lm, path = load_backbone(a.layers); tok.padding_side = "right"
    lm = get_peft_model(lm, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model = Judge(lm, lm.config.hidden_size).to(DEV)
    params = [p for p in model.parameters() if p.requires_grad]; print("trainable", sum(p.numel() for p in params), flush=True)
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0); lossf = torch.nn.BCEWithLogitsLoss()
    steps = a.epochs * (len(train) // 32 + 1); sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=steps, pct_start=0.05)
    best = (1e9, None); t0 = time.time()
    for ep in range(a.epochs):
        model.train()
        for k, (ids, mask, b) in enumerate(batches(tok, train, 32, True, rng)):
            y = torch.from_numpy(np.stack([Y[t] for _, t in b])).to(DEV)
            loss = lossf(model(ids.to(DEV), mask.to(DEV)), y); opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            if k % 500 == 0: print(f"ep {ep} step {k} loss {loss.item():.4f} {time.time() - t0:.0f}s", flush=True)
        zv = predict(model, tok, [q for q, _ in val]); yv = np.stack([Y[t] for _, t in val])
        vl = float(lossf(torch.from_numpy(zv), torch.from_numpy(yv)))
        print(f"epoch {ep} val loss {vl:.4f}", flush=True)
        if vl < best[0]: best = (vl, ep, {k_: v.detach().cpu().clone() for k_, v in model.state_dict().items() if "lora" in k_ or k_.startswith("head")}, zv)
    model.load_state_dict(best[2], strict=False); zv = best[3]; yv = np.stack([Y[t] for _, t in val])
    out = P.CACHE + f"gemma_judge_{a.tag}/"; os.makedirs(out, exist_ok=True); torch.save(best[2], out + "adapter_head.pt")
    temp, thr = [], []                                               # per-organ temperature (calibration) and threshold
    for k in range(len(AXES)):
        tz = min(np.arange(0.5, 3.01, 0.1), key=lambda s: float(lossf(torch.from_numpy(zv[:, k] / s), torch.from_numpy(yv[:, k]))))
        p = 1 / (1 + np.exp(-zv[:, k] / tz)); y = yv[:, k] > 0
        t_best = max(np.arange(0.2, 0.81, 0.05), key=lambda t_: 2 * ((p >= t_) & y).sum() / max(1, (p >= t_).sum() + y.sum()))
        temp.append(float(tz)); thr.append(float(t_best))
    temp, thr = np.array(temp, np.float32), np.array(thr, np.float32)
    pv = 1 / (1 + np.exp(-zv / temp)) >= thr
    f1 = [2 * (pv[:, k] & (yv[:, k] > 0)).sum() / max(1, pv[:, k].sum() + (yv[:, k] > 0).sum()) for k in range(len(AXES))]
    # gold dev: judge alone, and in place of the small head under the app's fill rule
    G = {x["qid"]: x for x in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [dict(G[q["qid"]], category=q["category"]) for q in Q]; groups = [q["group"] or q["qid"] for q in Q]
    dev = [i for i, g in enumerate(groups) if EL.split_of(g) == "dev"]
    zg = predict(model, tok, [q["query"] for q in Q]); J = 1 / (1 + np.exp(-zg / temp)) >= thr
    def run(rule):
        out = []
        for lk, j in zip(links, J):
            jo = [AXES[k] for k in np.where(j)[0]]; ok = lk.get("gate") is not False; lo = lk["axes"]
            if rule == "linker": out.append((lk["mondo"] if lo else None, lo))
            elif rule == "judge": out.append((None, jo if ok else []))
            elif rule == "fill_judge": out.append((lk["mondo"] if lo else None, lo or (jo if ok else [])))
            elif rule == "fill_head": out.append((lk["mondo"] if lo else None, lo or (lk.get("judged", []) if ok else [])))
        return out
    ev = {r: {k: EL.metrics(run(r), gold, dev)[k] for k in ("macro_f1", "false_accept_invalid", "coverage")} for r in ("linker", "fill_head", "judge", "fill_judge")}
    ko = [("당뇨", "metabolic_endocrine"), ("콩팥병", "renal"), ("치매", "neurologic"), ("간경화", "hepatic"), ("천식", "pulmonary"), ("녹내장", "ocular"), ("중풍", "neurologic"), ("통풍", "musculoskeletal")]
    zk = predict(model, tok, [k for k, _ in ko]); jk = 1 / (1 + np.exp(-zk / temp)) >= thr
    res = dict(tag=a.tag, layers=a.layers, rank=a.rank, epochs_best=best[1] + 1, val_loss=best[0], val_macro_f1=float(np.mean(f1)), n_train=len(train),
               gold_dev=ev, korean_examples={k: [AXES[i] for i in np.where(j)[0]] for (k, _), j in zip(ko, jk)}, minutes=round((time.time() - t0) / 60, 1))
    print(json.dumps(res, indent=1, ensure_ascii=False))
    np.savez(out + "calibration.npz", temp=temp, thr=thr); json.dump(dict(res, backbone=GEMMA, revision=REV, prompt=PROMPT), open(out + "info.json", "w"), indent=1, ensure_ascii=False)
    json.dump(res, open(P.REPO + f"ml/results/benchmarks/gemma_judge_{a.tag}.json", "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
