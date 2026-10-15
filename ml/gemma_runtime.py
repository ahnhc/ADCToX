"""Runs the quantized Gemma organ judge (ml/gemma_export.py) on the CPU or GPU: no generation, 13 organ probabilities per text.

    import gemma_runtime as GR; GR.judge(["당뇨", "water on the lungs"]) -> [["metabolic_endocrine"], ["pulmonary"]]

Model folder (in the model bundle, 'GemmaJudge/'): config.json (Gemma 4 text config, first 18 layers), tokenizer files,
weights-*.safetensors and judge.json (prompt, head, per-organ temperature and threshold).
Weights: linear layers int8 with one scale per output row, run by PyTorch's weight-only int8 kernel with bf16 inputs (memory
stays int8; 99.5% of the organ decisions equal the float model's); the word tables int8 per row, looked up row by row, so only
the rows of the typed tokens are expanded. Dynamic int8 (which also rounds the inputs) changed most decisions and is not used.
"""
import json, os, threading
import numpy as np

AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
_M = {}
_X = {}                                                                 # the extra outputs of a four-output judge (models 0.6+)
_LOCK = threading.Lock()


def folder():
    """the judge's folder in the active model bundle, or None (older bundles have none)."""
    try:
        import adc_runtime
        d = adc_runtime.active_directory()
        if d is None:
            import adc_paths as P
            d = P.CACHE
        p = os.path.join(str(d), "GemmaJudge")
        return p if os.path.exists(os.path.join(p, "judge.json")) else None
    except Exception:
        return None


def available(): return folder() is not None


def _qembedding(torch, q, s, bits, dim, scale):
    class QEmbedding(torch.nn.Module):
        """rows stored as int8 (or two 4-bit values per byte) with one float scale per row; only looked-up rows are expanded."""
        def __init__(self):
            super().__init__(); self.q, self.s, self.bits, self.dim, self.embed_scale = q, s, bits, dim, scale; self.dtype = torch.float32
        def forward(self, ids):
            r = self.q[ids]
            if self.bits == 4:
                lo = (r & 0x0F).to(torch.int8) - 8; hi = (r >> 4).to(torch.int8) - 8
                r = torch.stack([lo, hi], -1).reshape(*r.shape[:-1], -1)[..., :self.dim]
            return (r.float() * self.s[ids].unsqueeze(-1) * self.embed_scale).to(self.dtype)
    return QEmbedding()


DYNAMIC = os.environ.get("ADC_JUDGE_DYNAMIC", "pack")     # "pack": int8 weights x bf16 inputs (default); "none": float; "attn"/"all": dynamic int8


def _packlinear(torch, wq, ws, bias):
    class Int8Linear(torch.nn.Module):
        """weights stay int8 in memory (one scale per output row); bf16 inputs, PyTorch's weight-only int8 CPU kernel."""
        def __init__(self):
            super().__init__(); self.wq, self.s = wq.clone(), ws.to(torch.bfloat16).clone(); self.b = None if bias is None else bias.to(torch.bfloat16)
            self.in_features, self.out_features = wq.shape[1], wq.shape[0]
        def forward(self, x):
            shape = x.shape; y = torch._weight_int8pack_mm(x.reshape(-1, shape[-1]).to(torch.bfloat16).contiguous(), self.wq, self.s)
            if self.b is not None: y = y + self.b
            return y.reshape(*shape[:-1], -1)
    m = Int8Linear(); m(torch.zeros(1, wq.shape[1], dtype=torch.bfloat16)); return m


def _qlinear(torch, wq, ws, bias, dynamic=True):
    """int8 per-row weights -> a dynamic-quantized linear (int8 matmul) when asked and the backend supports it, else a float
    linear (weights dequantized once). Dynamic quantization also rounds the inputs to int8 per tensor, which the MLP inputs
    (large outliers) do not survive, so by default only the attention projections run that way."""
    out_f, in_f = wq.shape
    try:
        if not dynamic: raise RuntimeError("float")
        qw = torch._make_per_channel_quantized_tensor(wq, ws.double(), torch.zeros(out_f, dtype=torch.int64), 0)
        m = torch.ao.nn.quantized.dynamic.Linear(in_f, out_f, bias_=bias is not None, dtype=torch.qint8)
        m.set_weight_bias(qw, bias); m(torch.zeros(1, in_f))                # fails here if the backend cannot run it
        return m
    except Exception:
        m = torch.nn.Linear(in_f, out_f, bias=bias is not None)
        with torch.no_grad():
            m.weight.copy_(wq.float() * ws.unsqueeze(1))
            if bias is not None: m.bias.copy_(bias)
        return m


def load(path=None):
    """-> (tokenizer, model, head) built from the quantized folder; once per process."""
    path = path or folder()
    if path in _M: return _M[path]
    import torch, transformers as T
    from safetensors.torch import load_file
    with _LOCK:
        if path in _M: return _M[path]
        cfg = T.AutoConfig.from_pretrained(path); J = json.load(open(os.path.join(path, "judge.json"))); W = {}
        for f in sorted(os.listdir(path)):
            if f.startswith("weights") and f.endswith(".safetensors"): W.update(load_file(os.path.join(path, f)))
        with torch.device("meta"): model = T.AutoModel.from_config(cfg)
        L = J["layers"]; model.layers = model.layers[:L]; model.config.num_hidden_layers = L     # the first L layers (ml/gemma_export.cut_layers)
        # the big modules are replaced while the model is still on the meta device, so they are never allocated in float
        for name, mod in list(model.named_modules()):
            for child, sub in list(mod.named_children()):
                full = f"{name}.{child}" if name else child
                if isinstance(sub, torch.nn.Linear) and full + ".wq" in W:
                    if DYNAMIC == "pack":
                        try: setattr(mod, child, _packlinear(torch, W[full + ".wq"], W[full + ".ws"], W.get(full + ".bias"))); continue
                        except Exception: pass                              # no kernel on this CPU: float weights below
                    dyn = DYNAMIC == "all" or (DYNAMIC == "attn" and ".self_attn." in "." + full + ".")
                    setattr(mod, child, _qlinear(torch, W[full + ".wq"], W[full + ".ws"], W.get(full + ".bias"), dyn and DYNAMIC != "pack"))
                elif isinstance(sub, torch.nn.Embedding) and full + ".eq" in W:
                    bits = int(W[full + ".bits"].item()); scale = float(J["embed_scale"].get(full, 1.0))
                    setattr(mod, child, _qembedding(torch, W[full + ".eq"], W[full + ".es"].float(), bits, sub.embedding_dim, scale))
        model = model.to_empty(device="cpu")                             # only norms and small buffers are left to allocate
        for k in [k for k in W if k.startswith("buffer.")]:               # buffers (rotary tables, embedding scales) as exported
            *parent, leaf = k[len("buffer."):].split("."); mod = model.get_submodule(".".join(parent)) if parent else model
            setattr(mod, leaf, W[k].float()) if leaf not in mod._buffers else mod._buffers.__setitem__(leaf, W[k].float())
        rest = {k: v.float() for k, v in W.items() if not k.endswith((".wq", ".ws", ".eq", ".es", ".bits", ".bias")) and not k.startswith(("judge.", "buffer."))}
        missing = set(model.load_state_dict(rest, strict=False).missing_keys)        # norms first, then the quantized modules
        quant = {k.rsplit(".", 1)[0] for k in W if k.endswith((".wq", ".eq"))}
        left = [k for k in missing if k.rsplit(".", 1)[0] not in quant]
        if left: raise RuntimeError(f"judge weights missing: {left[:5]}")
        for buf_name, buf in model.named_buffers():                         # rotary tables etc.: recomputed from the config
            if buf.is_meta: raise RuntimeError(f"buffer {buf_name} was not initialised")
        if DYNAMIC == "pack":                                              # bf16 activations (the judge was trained in bf16)
            for mm in model.modules():
                if type(mm).__name__ == "QEmbedding": mm.dtype = torch.bfloat16
            for n_, p_ in model.named_parameters(): p_.data = p_.data.to(torch.bfloat16)
        model.eval()
        tok = T.AutoTokenizer.from_pretrained(path); tok.padding_side = "right"
        head = (W["judge.head.weight"].float(), W["judge.head.bias"].float(), np.array(J["temp"], np.float32), np.array(J["thr"], np.float32), J["prompt"])
        _X[path] = {n: (W[f"judge.{n}.weight"].float(), W[f"judge.{n}.bias"].float()) for n in ("valid", "align", "sym") if f"judge.{n}.weight" in W}
        _X[path]["info"] = dict(vthr=J.get("vthr"), profiles=J.get("profiles", []))
        _M[path] = (tok, model, head)
        return _M[path]


def _last(texts, path):
    import torch
    tok, model, head = load(path)
    enc = tok([head[4].format(t) for t in texts], return_tensors="pt", padding=True, truncation=True, max_length=64 if has_extra(path) else 48)
    with _LOCK, torch.no_grad():
        h = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).last_hidden_state
    return h[torch.arange(len(texts)), enc["attention_mask"].sum(1) - 1].float()


def has_extra(path=None):
    """whether the judge also gives validity, a SapBERT-space vector and symptom -> profile scores."""
    path = path or folder()
    if path is None: return False
    try: return "align" in json.load(open(os.path.join(path, "judge.json"))).get("outputs", [])     # without loading the model
    except (OSError, ValueError): return False


def probs(texts, path=None):
    """-> array (texts x 13) of calibrated organ probabilities."""
    _, _, (hw, hb, temp, thr, prompt) = load(path)
    z = (_last(texts, path) @ hw.T + hb).numpy()
    return 1 / (1 + np.exp(-z / temp))


def outputs(texts, path=None):
    """-> dict organ (n x 13 probabilities), and with a four-output judge: valid (n, probability of a real input), valid_ok
    (n bools), vec (n x 768, unit vectors in SapBERT space), sym (n x profiles probabilities), profiles (ids)."""
    import torch
    path = path or folder(); _, _, (hw, hb, temp, thr, prompt) = load(path); h = _last(texts, path); X = _X.get(path, {})
    out = dict(organ=1 / (1 + np.exp(-(h @ hw.T + hb).numpy() / temp)))
    if "align" in X:
        v = 1 / (1 + np.exp(-(h @ X["valid"][0].T + X["valid"][1]).numpy()[:, 0])); out.update(valid=v, valid_ok=v >= X["info"]["vthr"])
        out["vec"] = torch.nn.functional.normalize(h @ X["align"][0].T + X["align"][1], dim=-1).numpy()
        out["sym"] = torch.softmax(h @ X["sym"][0].T + X["sym"][1], -1).numpy(); out["profiles"] = X["info"]["profiles"]
    return out


def judge(texts, path=None):
    """-> per text the organs whose calibrated probability passes that organ's threshold."""
    _, _, (_, _, _, thr, _) = load(path)
    return [[AXES[k] for k in np.where(p >= thr)[0]] for p in probs(texts, path)]
