"""Runs the from-scratch organ judge (ml/scratch_export.py) on the CPU or GPU: a typed condition -> concept, organs, validity.

    import scratch_runtime as SR; SR.judge(["tuberculosis"]) -> [dict(concept="MONDO:0018076", name="tuberculosis",
        organs=["pulmonary", "infectious_immune"], via="record", valid=0.999, ok=True, sim=1.0)]

Model folder (in the model bundle, 'ScratchJudge/'): a BERT-base encoder trained from random weights on public medical text,
with organ, validity and name-vector outputs; index.npz (name vectors); index_ko.npz (Korean MONDO names, only when present); concepts.json (organs per concept).
Rule, the same as ml/scratch_judge.judge with the evidence table and the MONDO-first margin:
- validity below LOW_VALID: not read as a disease, no organs; from there up to the threshold: read, with `low` set
- the nearest name at or above theta links its concept (a MONDO name within `mondo_first` of a better non-MONDO name wins)
- organs: the concept's own organs (via "label", or "record" when they come from reading its MONDO entry), else the organ
  output on the typed text itself (via "name")
"""
import json, os, re, threading, unicodedata
import numpy as np

_M = {}
_HANGUL = re.compile("[가-힣]")
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


_ORG = {}


def concept_organs():
    """MONDO id -> organs, as the judge gives them for a linked concept (label or record), or {} without the judge. The search list
    and a reading chosen from it use these, so a disease picked from the list gets the organs it gets when typed. No model is loaded."""
    if not available(): return {}
    path = folder()
    if path not in _ORG:
        C = json.load(open(os.path.join(path, "concepts.json"), encoding="utf-8"))
        _ORG[path] = {c: (list(v[1]), v[2]) for c, v in C.items() if c.startswith("MONDO:") and v[1]}
    return {c: o for c, (o, _) in _ORG[path].items()}


def concept_via(concept):
    """"label" or "record": where the judge's organs for a MONDO concept come from; None without the judge or without organs."""
    if not available() or concept_organs() is None: return None
    return _ORG[folder()].get(concept, (None, None))[1]


_CONCEPTS = {}


def concept(c, path=None):
    """(name, organs, via) of a concept in the judge's table, None when absent. No model is loaded."""
    path = path or folder()
    if path is None: return None
    if path not in _CONCEPTS: _CONCEPTS[path] = json.load(open(os.path.join(path, "concepts.json"), encoding="utf-8"))
    row = _CONCEPTS[path].get(c)
    return (row[0], list(row[1]), row[2]) if row else None


def load(path=None):
    path = path or folder()
    with _LOCK:
        if path not in _M:
            import torch, transformers as T
            from safetensors.torch import load_file
            j = json.load(open(os.path.join(path, "judge.json"), encoding="utf-8"))
            tk = T.AutoTokenizer.from_pretrained(path)
            bb = T.AutoModel.from_config(T.AutoConfig.from_pretrained(path), add_pooling_layer=False)
            D = bb.config.hidden_size; sd = {k: v.float() for k, v in load_file(os.path.join(path, "weights.safetensors")).items()}
            heads = {n: torch.nn.Linear(D, k) for n, k in (("organ", 13), ("valid", 1), ("proj", sd["proj.weight"].shape[0]))}
            bb.load_state_dict({k[3:]: v for k, v in sd.items() if k.startswith("bb.") and not k.startswith("bb.pooler.")}, strict=False)
            for n, h in heads.items(): h.load_state_dict({"weight": sd[f"{n}.weight"], "bias": sd[f"{n}.bias"]})
            bb.eval(); [h.eval() for h in heads.values()]
            Z = np.load(os.path.join(path, "index.npz")); ids = [str(x) for x in Z["ids"]]
            C = json.load(open(os.path.join(path, "concepts.json"), encoding="utf-8"))
            ko = os.path.join(path, "index_ko.npz")                      # Korean MONDO names, searched for Hangul input; bundles before 0.9 have none
            Zk = np.load(ko) if os.path.exists(ko) else None
            _M[path] = dict(j=j, tk=tk, bb=bb, heads=heads, E=Z["E"].astype(np.float32), ids=ids,
                            mondo=np.array([i.startswith("MONDO:") for i in ids]), C=C, torch=torch,
                            Ek=Zk["E"].astype(np.float32) if Zk is not None else None, idk=[str(x) for x in Zk["ids"]] if Zk is not None else [])
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


def _hangul(M, text): return M["Ek"] is not None and bool(_HANGUL.search(unicodedata.normalize("NFC", str(text))))


NEAR, CANDIDATES = 64, 8        # strings looked at, concepts kept
LOW_VALID = 0.9                 # the threshold rejects TB, shingles, migrane: under it the read stands with a mark, and only this low is it dropped


def _candidates(M, sims, near, first, first_sim):
    best = {first: first_sim} if first else {}
    for i in near[np.argsort(-sims[near])]:
        if sims[i] < M["j"]["theta"]: break
        best.setdefault(M["ids"][i], float(sims[i]))
    return [dict(concept=c, name=M["C"].get(c, ["", [], ""])[0], organs=list(M["C"].get(c, ["", [], ""])[1]), via=M["C"].get(c, ["", [], ""])[2], sim=best[c]) for c in list(best)[:CANDIDATES]]


def judge(texts, path=None):
    """-> one dict per text: concept (or None), name, organs, via ("label", "record", "name" or None), valid, ok, sim, and p: the
    calibrated organ output on the text itself, {axis: probability} for all 13 (what the screens show as the organ probabilities);
    judged: the organs that output gives; candidates: the concepts nearest the text at or above theta, the linked concept first,
    [dict(concept, name, organs, via, sim)]."""
    texts = list(texts)
    if not texts: return []
    M = load(path); j = M["j"]; AX = j["axes"]
    zo, zv, va = _outputs(M, texts); S = va @ M["E"].T; jj = S.argmax(1); s = S.max(1); n = min(NEAR, S.shape[1]); near = np.argpartition(-S, n - 1, axis=1)[:, :n]
    Sm = np.where(M["mondo"][None], S, -9); jm = Sm.argmax(1); sm = Sm.max(1)
    cid = [M["ids"][i] for i in jj]; mid = [M["ids"][i] for i in jm]; s, sm = s.copy(), sm.copy()
    for k, t in enumerate(texts):
        if _hangul(M, t):                                                # a Korean name of the same concept counts as its English name
            Sk = va[k] @ M["Ek"].T; i = int(Sk.argmax())
            if Sk[i] > s[k]: cid[k], s[k] = M["idk"][i], Sk[i]
            if Sk[i] > sm[k]: mid[k], sm[k] = M["idk"][i], Sk[i]
    po = 1 / (1 + np.exp(-zo / np.array(j["temp"]))); pv = 1 / (1 + np.exp(-zv)); rows = []
    for k in range(len(texts)):
        ok = bool(pv[k] >= min(LOW_VALID, j["vthr"])); p = {a: float(x) for a, x in zip(AX, po[k])}; low = bool(pv[k] < j["vthr"])
        if not ok: rows.append(dict(concept=None, name="", organs=[], via=None, valid=float(pv[k]), ok=False, low=False, sim=float(s[k]), p=p, judged=[], candidates=[])); continue
        c, sim = (cid[k], float(s[k])) if s[k] >= j["theta"] else (None, float(s[k]))
        if sm[k] >= j["theta"] and sm[k] >= s[k] - j["mondo_first"]: c, sim = mid[k], float(sm[k])
        name, organs, via = M["C"].get(c, ["", [], ""]) if c else ("", [], "")
        judged = [AX[a] for a in np.where(po[k] >= np.array(j["thr"]))[0]]
        if not organs: organs, via = judged, "name"
        rows.append(dict(concept=c, name=name, organs=list(organs), via=via, valid=float(pv[k]), ok=True, low=low, sim=sim, p=p, judged=judged, candidates=_candidates(M, S[k], near[k], c, sim)))
    return rows


def nearest(text, k=5, path=None):
    """-> the k concepts whose names lie nearest the text, at or above theta, best first: (concept, name, sim); [] when
    the validity output says the text is not a disease name. The search box's AI suggestions."""
    M = load(path); j = M["j"]
    _, zv, va = _outputs(M, [text])
    if 1 / (1 + np.exp(-zv[0])) < j["vthr"]: return []
    ids, S = M["ids"], va[0] @ M["E"].T; out, seen = [], set()
    if _hangul(M, text): ids, S = ids + M["idk"], np.concatenate([S, va[0] @ M["Ek"].T])
    for i in np.argsort(-S):
        if S[i] < j["theta"] or len(out) == k: break
        c = ids[i]
        if c in seen: continue
        seen.add(c); name = M["C"].get(c, [""])[0]
        if name: out.append((c, name, float(S[i])))
    return out
