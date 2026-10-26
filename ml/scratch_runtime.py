"""Runs the from-scratch organ judge (ml/scratch_export.py) on the CPU or GPU: a typed condition -> concept, organs, validity.

    import scratch_runtime as SR; SR.judge(["tuberculosis"]) -> [dict(concept="MONDO:0018076", name="tuberculosis",
        organs=["pulmonary", "infectious_immune"], via="record", valid=0.999, ok=True, sim=1.0)]

Model folder (in the model bundle, 'ScratchJudge/'): a BERT-base encoder trained from random weights on public medical text,
with organ, validity and name-vector outputs; index.npz (name vectors); concepts.json (organs per concept).
Rule, the same as ml/scratch_judge.judge with the evidence table and the MONDO-first margin:
- validity below the threshold: not read as a disease, no organs
- the nearest name at or above theta links its concept (a MONDO name within `mondo_first` of a better non-MONDO name wins)
- organs: the concept's own organs (via "label", or "record" when they come from reading its MONDO entry), else the organ
  output on the typed text itself (via "name")
"""
import json, os, threading
import numpy as np

_M = {}
_LOCK = threading.Lock()


def folder():
    """the judge's folder in the active model bundle, or None (bundles before models 0.7 have none)."""
    try:
        import adc_runtime
        d = adc_runtime.active_directory()
        if d is None:
            import adc_paths as P
            d = P.CACHE
        p = os.path.join(str(d), "ScratchJudge")
        return p if os.path.exists(os.path.join(p, "judge.json")) else None
    except Exception:
        return None


def available(): return os.environ.get("ADC_SCRATCH_JUDGE", "1") != "0" and folder() is not None


def load(path=None):
    path = path or folder()
    with _LOCK:
        if path not in _M:
            import torch, transformers as T
            from safetensors.torch import load_file
            j = json.load(open(os.path.join(path, "judge.json")))
            tk = T.AutoTokenizer.from_pretrained(path)
            bb = T.AutoModel.from_config(T.AutoConfig.from_pretrained(path), add_pooling_layer=False)
            D = bb.config.hidden_size; sd = {k: v.float() for k, v in load_file(os.path.join(path, "weights.safetensors")).items()}
            heads = {n: torch.nn.Linear(D, k) for n, k in (("organ", 13), ("valid", 1), ("proj", sd["proj.weight"].shape[0]))}
            bb.load_state_dict({k[3:]: v for k, v in sd.items() if k.startswith("bb.") and not k.startswith("bb.pooler.")}, strict=False)
            for n, h in heads.items(): h.load_state_dict({"weight": sd[f"{n}.weight"], "bias": sd[f"{n}.bias"]})
            bb.eval(); [h.eval() for h in heads.values()]
            Z = np.load(os.path.join(path, "index.npz")); ids = [str(x) for x in Z["ids"]]
            C = json.load(open(os.path.join(path, "concepts.json"), encoding="utf-8"))
            _M[path] = dict(j=j, tk=tk, bb=bb, heads=heads, E=Z["E"].astype(np.float32), ids=ids,
                            mondo=np.array([i.startswith("MONDO:") for i in ids]), C=C, torch=torch)
        return _M[path]


def _outputs(M, texts, bs=64):
    torch = M["torch"]; zo, zv, va = [], [], []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            e = M["tk"]([str(t).strip() for t in texts[i:i + bs]], padding=True, truncation=True, max_length=M["j"]["maxlen"], return_tensors="pt")
            m = e["attention_mask"]; h = M["bb"](input_ids=e["input_ids"], attention_mask=m).last_hidden_state
            h = (h * m[..., None]).sum(1) / m.sum(1, keepdim=True).clamp(min=1)
            zo.append(M["heads"]["organ"](h).numpy()); zv.append(M["heads"]["valid"](h)[:, 0].numpy())
            va.append(torch.nn.functional.normalize(M["heads"]["proj"](h), dim=-1).numpy())
    return np.concatenate(zo), np.concatenate(zv), np.concatenate(va)


def judge(texts, path=None):
    """-> one dict per text: concept (or None), name, organs, via ("label", "record", "name" or None), valid, ok, sim."""
    texts = list(texts)
    if not texts: return []
    M = load(path); j = M["j"]; AX = j["axes"]
    zo, zv, va = _outputs(M, texts); S = va @ M["E"].T; jj = S.argmax(1); s = S.max(1)
    Sm = np.where(M["mondo"][None], S, -9); jm = Sm.argmax(1); sm = Sm.max(1)
    po = 1 / (1 + np.exp(-zo / np.array(j["temp"]))); pv = 1 / (1 + np.exp(-zv)); rows = []
    for k in range(len(texts)):
        ok = bool(pv[k] >= j["vthr"])
        if not ok: rows.append(dict(concept=None, name="", organs=[], via=None, valid=float(pv[k]), ok=False, sim=float(s[k]))); continue
        c, sim = (M["ids"][jj[k]], float(s[k])) if s[k] >= j["theta"] else (None, float(s[k]))
        if sm[k] >= j["theta"] and sm[k] >= s[k] - j["mondo_first"]: c, sim = M["ids"][jm[k]], float(sm[k])
        name, organs, via = M["C"].get(c, ["", [], ""]) if c else ("", [], "")
        if not organs: organs, via = [AX[a] for a in np.where(po[k] >= np.array(j["thr"]))[0]], "name"
        rows.append(dict(concept=c, name=name, organs=list(organs), via=via, valid=float(pv[k]), ok=True, sim=sim))
    return rows
