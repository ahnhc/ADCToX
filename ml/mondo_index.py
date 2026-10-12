"""A reusable MONDO index, so ANY disease name can be linked to its organ system(s) at query time.

  build:  python -I ml/mondo_index.py            -> ml_cache/mondo_index.npz  (SapBERT embeddings of every disease name/exact synonym)
  use:    from mondo_index import link; link(["asthma"]) -> [{mondo, name, sim, axes: [...]}]

Organs come from the project's own ancestor -> axis crosswalk (conf/ontology/mondo_organ_axis.yaml) over the is_a closure.
THETA = 0.75 was fixed before any result existed (ml/link_mondo.py); below it nothing is returned rather than a wrong link."""
import os, re, sys, time, warnings
import numpy as np, torch, yaml
import adc_runtime
warnings.filterwarnings("ignore")
C = "/data/hyeongchanahn/adctox/ml_cache/"; OBO = "/home/hyeongchanahn/CONI/adctox/data/raw_big/mondo/2026-10-07/mondo.obo"
THETA = 0.75; NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]

def _embed(strs, device, bs=512):
    from transformers import AutoTokenizer, AutoModel
    name = adc_runtime.encoder_path("SapBERT", NAME)
    tok = AutoTokenizer.from_pretrained(name); mod = AutoModel.from_pretrained(name).to(device).eval(); half = device != "cpu"
    if half: mod = mod.half()
    out = []
    with torch.no_grad():
        for i in range(0, len(strs), bs):
            b = tok(strs[i:i + bs], padding=True, truncation=True, max_length=48, return_tensors="pt").to(device); out.append(mod(**b).last_hidden_state[:, 0].float().cpu().numpy())
    E = np.concatenate(out); return (E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)).astype(np.float16 if half else np.float32)

def build():
    T = {}; cur = None; term = False
    for line in open(OBO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": term, cur = True, None; continue
        if line.startswith("["): term = False; continue
        if not term or not line: continue
        if line.startswith("id: "): cur = line[4:].strip(); T[cur] = dict(name="", syn=[], parents=set(), obs=False)
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:].strip()
        elif line.startswith("is_obsolete: true"): T[cur]["obs"] = True
        elif line.startswith("synonym: ") and " EXACT " in line:
            q = re.match(r'synonym: "(.*)" EXACT', line); T[cur]["syn"].append(q.group(1)) if q else None
        elif line.startswith("is_a: "):
            p = line[6:].split()[0]
            if p.startswith(("MONDO:", "HP:")): T[cur]["parents"].add(p)
    memo = {}
    def anc(t):
        if t in memo: return memo[t]
        seen, st = set(), list(T[t]["parents"]) if t in T else []
        while st:
            n = st.pop()
            if n in seen: continue
            seen.add(n); st.extend(T[n]["parents"] if n in T else ())
        memo[t] = seen; return seen
    cross = {k.lower(): v for k, v in yaml.safe_load(open("/home/hyeongchanahn/CONI/adctox/conf/ontology/mondo_organ_axis.yaml"))["ancestor_to_axis"].items()}
    dis = [t for t in T if t.startswith("MONDO:") and not T[t]["obs"] and T[t]["name"] and (t == "MONDO:0000001" or "MONDO:0000001" in anc(t))]
    strs, ids = [], []
    for t in dis:
        for s in [T[t]["name"]] + T[t]["syn"]: strs.append(s); ids.append(t)
    ax = {}
    for t in dis:
        v = np.zeros(len(AXES), np.float32)
        for a in anc(t) | {t}:
            x = cross.get(T[a]["name"].lower()) if a in T else None
            if x in AXES: v[AXES.index(x)] = 1
        ax[t] = v
    print(len(dis), "diseases,", len(strs), "strings", flush=True)
    for _ in range(60):
        try: E = _embed(strs, "cuda:0" if torch.cuda.is_available() else "cpu"); break
        except (torch.OutOfMemoryError, RuntimeError) as e:
            if not any(k in str(e) for k in ("CUBLAS", "out of memory", "CUDA error")): raise
            torch.cuda.empty_cache(); time.sleep(30)
    np.savez(C + "mondo_index.npz", E=E, ids=np.array(ids, dtype=object), names=np.array([T[t]["name"] for t in ids], dtype=object), axes=np.stack([ax[t] for t in ids]))
    print("saved", E.shape)

_IDX = None
def link(texts):
    global _IDX
    if _IDX is None: _IDX = np.load(adc_runtime.model_path("mondo_index.npz", C + "mondo_index.npz"), allow_pickle=not adc_runtime.restricted_bundle())
    Q = _embed(list(texts), "cuda:0" if torch.cuda.is_available() else "cpu"); S = Q @ _IDX["E"].astype(np.float32).T; out = []
    for i in range(len(texts)):
        j = int(S[i].argmax()); sim = float(S[i, j]); ax = _IDX["axes"][j]
        out.append(dict(mondo=str(_IDX["ids"][j]), name=str(_IDX["names"][j]), sim=sim, axes=[AXES[k] for k in np.where(ax > 0)[0]] if sim >= THETA else []))
    return out

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build": os.environ["ADC_RESEARCH_MODE"] = "1"; build()
    else: [print(r) for r in link(sys.argv[1:] or ["asthma", "hypertension", "rheumatoid arthritis"])]
