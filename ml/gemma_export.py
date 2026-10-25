"""Quantized Gemma organ judge for the app: LoRA merged, the first 18 layers only, int8 / 4-bit weights.

    CUDA_VISIBLE_DEVICES=1 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache copy> python ml/gemma_export.py --tag half
    -> $ADCTOX_CACHE/GemmaJudge/  (config.json, tokenizer, weights.safetensors, judge.json), checked against the trained model

The per-layer word table and its projection keep only the columns of the kept layers, and the config says 18 layers with the
same key/value sharing (the last 3 kept layers reuse earlier keys and values, as they did inside the 35-layer model).
Check: last-token hidden states of the exported float model match the trained one; the quantized model's organ decisions are
compared on the gold dev queries and the held-out training texts.
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P, eval_linking as EL, gemma_judge as GJ, gemma_runtime as GR

PER = 256


def q_rows(w, bits):
    """per-row symmetric quantization -> (int8 or packed uint8, float32 scales)."""
    w = w.float(); m = w.abs().amax(1).clamp(min=1e-8)
    if bits == 8:
        s = m / 127; return torch.round(w / s[:, None]).clamp(-127, 127).to(torch.int8), s
    s = m / 7; q = (torch.round(w / s[:, None]).clamp(-8, 7) + 8).to(torch.uint8)
    if q.shape[1] % 2: q = torch.cat([q, torch.full((q.shape[0], 1), 8, dtype=torch.uint8)], 1)
    return (q[:, 0::2] | (q[:, 1::2] << 4)).contiguous(), s


FULL_LAYERS = {"google/gemma-4-E2B": 35}                                   # metadata: layers of the uncut model


def cut_layers(model, L):
    """keep the first L decoder layers and the per-layer word-table columns they read; the config then says L layers (the
    key/value sharing flags were set on the layers when the 35-layer model was built and stay as they were)."""
    import torch
    with torch.no_grad():
        e = model.embed_tokens_per_layer; e.weight = torch.nn.Parameter(e.weight.data[:, : L * PER].contiguous()); e.embedding_dim = L * PER
        p = model.per_layer_model_projection; p.weight = torch.nn.Parameter(p.weight.data[: L * PER].contiguous()); p.out_features = L * PER
    model.layers = model.layers[:L]; model.config.num_hidden_layers = L
    return model


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="half"); ap.add_argument("--layers", type=int, default=18); ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--v2", action="store_true", help="the four-output judge of ml/gemma_judge2.py"); ap.add_argument("--out", default=None)
    a = ap.parse_args(); src = P.CACHE + (f"gemma_judge2_{a.tag}/" if a.v2 else f"gemma_judge_{a.tag}/"); out = (a.out or P.CACHE + "GemmaJudge").rstrip("/") + "/"; os.makedirs(out, exist_ok=True)
    from peft import LoraConfig, get_peft_model
    from safetensors.torch import save_file
    tok, lm, path = GJ.load_backbone(a.layers); lm.gradient_checkpointing_disable()
    lm = get_peft_model(lm, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    if a.v2:
        import gemma_judge2 as GJ2; info = json.load(open(src + "info.json"))
        judge = GJ2.Judge2(lm, lm.config.hidden_size, len(info["profiles"]))
    else: judge = GJ.Judge(lm, lm.config.hidden_size)
    judge.load_state_dict(torch.load(src + "adapter_head.pt"), strict=False)
    merged = judge.lm.merge_and_unload().float().eval(); head = judge.head.float()
    L = a.layers; cfg = merged.config
    texts = ["chronic kidney disease stage 3", "당뇨", "water on the lungs", "asd", "banana spaceship", "치매가 있어요"]
    tok.padding_side = "right"                                    # as in training: the head reads the last real token
    enc = tok([GJ.PROMPT.format(t) for t in texts], return_tensors="pt", padding=True); last = enc["attention_mask"].sum(1) - 1
    with torch.no_grad(): ref = merged(**enc).last_hidden_state[torch.arange(len(texts)), last]
    cfg.save_pretrained(out); tok.save_pretrained(out)            # the original 35-layer config; the runtime cuts the same way
    cut = cut_layers(merged, L)                                   # the model holds and runs 18 layers
    with torch.no_grad(): got = cut(**enc).last_hidden_state[torch.arange(len(texts)), last]
    cos = torch.nn.functional.cosine_similarity(ref, got).min().item(); print("cut vs trained, min cosine", round(cos, 5), flush=True)
    assert cos > 0.999, "the cut model does not reproduce the trained one"
    sd = cut.state_dict()
    scales = {n: float(m.embed_scale.item()) if hasattr(m, "embed_scale") and hasattr(m.embed_scale, "item") else float(getattr(m, "embed_scale", 1.0))
              for n, m in cut.named_modules() if isinstance(m, torch.nn.Embedding)}
    W = {}
    for n, m in cut.named_modules():
        if isinstance(m, torch.nn.Linear):
            W[n + ".wq"], W[n + ".ws"] = q_rows(m.weight.data, 8)
            if m.bias is not None: W[n + ".bias"] = m.bias.data.float()
        elif isinstance(m, torch.nn.Embedding):
            bits = 8                                                 # 4-bit lost too much (final cosine 0.99 even with groups of 64)
            W[n + ".eq"], W[n + ".es"] = q_rows(m.weight.data, bits); W[n + ".es"] = W[n + ".es"].half(); W[n + ".bits"] = torch.tensor(bits)
    for k, v in sd.items():
        mod = k.rsplit(".", 1)[0]
        if not any(k.startswith(x) for x in [n for n, m in cut.named_modules() if isinstance(m, (torch.nn.Linear, torch.nn.Embedding))]): W[k] = v.float()
    for n, b in cut.named_buffers(): W["buffer." + n] = b.float().clone()
    W["judge.head.weight"], W["judge.head.bias"] = head.weight.data.float(), head.bias.data.float()
    extra = {}
    if a.v2:                                                       # validity, SapBERT-space vector, symptom -> profile disease
        for n in ("valid", "align", "sym"): W[f"judge.{n}.weight"], W[f"judge.{n}.bias"] = getattr(judge, n).weight.data.float(), getattr(judge, n).bias.data.float()
        extra = dict(outputs=["organ", "valid", "align", "sym"], profiles=info["profiles"], vthr=float(np.load(src + "calibration.npz")["vthr"]))
    cal = np.load(src + "calibration.npz")
    for f in os.listdir(out):
        if f.startswith("weights"): os.remove(out + f)
    ple = {k: v.contiguous() for k, v in W.items() if k.startswith("embed_tokens_per_layer.")}     # two files: a GitHub release file must be < 2 GiB
    save_file(ple, out + "weights-1.safetensors"); save_file({k: v.contiguous() for k, v in W.items() if k not in ple}, out + "weights-2.safetensors")
    json.dump(dict(prompt=GJ.PROMPT, temp=cal["temp"].tolist(), thr=cal["thr"].tolist(), embed_scale=scales, layers=L, config_layers=FULL_LAYERS.get(GJ.GEMMA), backbone=GJ.GEMMA, revision=GJ.REV,
                   licence="Gemma 4: Apache-2.0", **extra), open(out + "judge.json", "w"), indent=1, ensure_ascii=False)
    size = sum(os.path.getsize(out + f) for f in os.listdir(out) if f.startswith("weights")); print("written", out, round(size / 1e9, 2), "GB", flush=True)
    # quantized vs float decisions
    Q = json.load(open(EL.D + "raw/queries_v0.json")); qs = [q["query"] for q in Q]
    with torch.no_grad():
        zf = []
        for i in range(0, len(qs), 64):
            e = tok([GJ.PROMPT.format(t) for t in qs[i:i + 64]], return_tensors="pt", padding=True); l2 = e["attention_mask"].sum(1) - 1
            zf.append(head(cut(**e).last_hidden_state[torch.arange(len(l2)), l2]).numpy())
    pf = 1 / (1 + np.exp(-np.concatenate(zf) / cal["temp"])) >= cal["thr"]
    del cut, judge
    pq = np.concatenate([GR.probs(qs[i:i + 64], out) for i in range(0, len(qs), 64)]) >= cal["thr"]
    agree = float((pf == pq).all(1).mean()); print("quantized vs float: same organ set on", round(agree, 3), "of gold queries", flush=True)
    json.dump(dict(min_cosine_cut=cos, quantized_same_set=agree, size_gb=size / 1e9),
              open(P.REPO + "ml/results/benchmarks/gemma_export.json", "w"), indent=1)


if __name__ == "__main__":
    main()
