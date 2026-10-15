"""A reusable MONDO index, so ANY disease name can be linked to its organ system(s) at query time.

  build:  python -I ml/mondo_index.py            -> ml_cache/mondo_index.npz  (SapBERT embeddings of every disease name/exact synonym)
  use:    from mondo_index import link; link(["asthma"]) -> [{mondo, name, sim, axes: [...]}]

Organs come from the project's own ancestor -> axis crosswalk (conf/ontology/mondo_organ_axis.yaml) over the is_a closure.
THETA = 0.75 was fixed before any result existed (ml/link_mondo.py); below it nothing is returned rather than a wrong link."""
import os, re, sys, time, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P
import numpy as np, torch, yaml
import adc_runtime
warnings.filterwarnings("ignore")
C = P.CACHE; OBO = P.REPO + "data/raw_big/mondo/2026-10-07/mondo.obo"
THETA = 0.75; NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]

_ENC = {}                   # (model path, device) -> (tokenizer, model): load SapBERT once per process, not once per query
def _encoder(device):
    from transformers import AutoTokenizer, AutoModel
    name = adc_runtime.encoder_path("SapBERT", NAME); key = (name, device)
    if key not in _ENC:
        _ENC.clear(); mod = AutoModel.from_pretrained(name).to(device).eval()
        _ENC[key] = (AutoTokenizer.from_pretrained(name), mod.half() if device != "cpu" else mod)
    return _ENC[key]

def _embed(strs, device, bs=512):
    tok, mod = _encoder(device); half = device != "cpu"
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
    cross = {k.lower(): v for k, v in yaml.safe_load(open(P.REPO + "conf/ontology/mondo_organ_axis.yaml"))["ancestor_to_axis"].items()}
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
_IDX_E = None               # the index matrix as float32 on the query device, converted once (it was converted for every query)
def close():
    global _IDX, _IDX_E
    _IDX = _IDX_E = None; _ENC.clear()

def _char_feats(s):
    s2 = s.strip(); letters = sum(c.isalpha() for c in s2); vow = sum(c in "aeiouAEIOU" for c in s2)
    return [len(s2) / 30, letters / max(1, len(s2)), vow / max(1, letters), len(s2.split()) / 5, any(c.isdigit() for c in s2), len(s2) <= 3]

def gate_inputs(texts, Q, top_v, top_j, ids):
    """validity-gate features: SapBERT query embedding, top-1 similarity, top-1 minus the best other concept, character stats."""
    rows = []
    for i, t in enumerate(texts):
        jj, vv = top_j[i], top_v[i]; c1 = ids[jj[0]]; s2 = next((v for j, v in zip(jj, vv) if ids[j] != c1), vv[-1])
        rows.append([vv[0], vv[0] - s2] + _char_feats(t))
    return np.c_[Q, np.array(rows, np.float32)]

def link(texts):
    """-> per text {mondo, name, sim, axes, valid}; valid = P(the text names a disease) from the index's validity gate (index v1+),
    None for an older index. axes stay empty below THETA."""
    global _IDX, _IDX_E
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    if _IDX is None:
        _IDX = dict(np.load(adc_runtime.model_path("mondo_index.npz", C + "mondo_index.npz"), allow_pickle=not adc_runtime.restricted_bundle())); _IDX_E = None
        _IDX["_ids"] = [str(x) for x in _IDX["ids"]]
    if _IDX_E is None or _IDX_E.device != torch.device(device): _IDX_E = torch.from_numpy(_IDX["E"].astype(np.float32)).to(device)
    texts = list(texts); Qn = _embed(texts, device).astype(np.float32); Q = torch.from_numpy(Qn).to(device)
    with torch.no_grad(): v, j = (Q @ _IDX_E.T).topk(64, dim=1)
    v, j = v.cpu().numpy(), j.cpu().numpy(); valid = [None] * len(texts)
    if "gate_w" in _IDX:
        X = gate_inputs(texts, Qn, v, j, _IDX["_ids"]); z = ((X - _IDX["gate_mu"]) / _IDX["gate_sd"]) @ _IDX["gate_w"] + _IDX["gate_b"]
        valid = (1 / (1 + np.exp(-z))).tolist()
    out = []
    for i in range(len(texts)):
        cands = concept_candidates(j[i].tolist(), v[i].tolist())
        accept = cands[0][1] >= THETA
        if "rr_w" in _IDX:                                     # learned reranker (index v4+): reorders the 10 nearest concepts
            z = rerank_scores(texts[i], cands); order = sorted(range(len(cands)), key=lambda o: -z[o])
            cands = [cands[o] for o in order]; accept = bool(z[order[0]] >= float(_IDX["rr_threshold"]))
        t0, sim = cands[0][0], cands[0][1]; name, organs = concept(t0)
        top = [(t, s) for t, s, _ in cands[:5]]
        row = dict(mondo=t0, name=name, sim=sim, axes=organs if accept else [],
                   valid=valid[i], gate=None if valid[i] is None else bool(valid[i] >= float(_IDX["gate_threshold"])))
        row["readings"] = readings(texts[i], top, accept)
        row["judged"] = judged_organs(Qn[i]) if "oh_w1" in _IDX else []     # fast organ judgment of the text itself (index v5+)
        row["hpo"] = None if row["axes"] else phenotype(texts[i], Qn[i])
        if row["hpo"] and sim >= THETA:                       # a disease without organ axis vs a symptom with one (amnesia): both readings
            row["readings"].append(dict(mondo=row["hpo"]["hpo"], name=row["hpo"]["name"], organs=row["hpo"]["organs"], why="phenotype"))
        row["ambiguous"] = len({frozenset(r["organs"]) for r in row["readings"]}) >= 2
        out.append(row)
    return out


# ------------------------------------------------------------------ readings of one typed text
TIE = 0.02                  # concepts within this similarity of the top-1 are also readings of the text
ABBREV = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,5}$")

def concept(mondo):
    """-> (name, organs) of a MONDO concept (or an HPO term of the index's phenotype block) in the active index."""
    if mondo.startswith("HP:") and "hp_ids" in _IDX:
        if "_hp_first" not in _IDX: _IDX["_hp_first"] = {t: k for k, t in reversed(list(enumerate(str(x) for x in _IDX["hp_ids"])))}
        k = _IDX["_hp_first"].get(mondo)
        return (None, []) if k is None else (str(_IDX["hp_names"][k]), [AXES[a] for a in np.where(_IDX["hp_axes"][k] > 0)[0]])
    if "_first" not in _IDX: _IDX["_first"] = {t: k for k, t in reversed(list(enumerate(_IDX["_ids"])))}
    k = _IDX["_first"].get(mondo)
    if k is None: return None, []
    return str(_IDX["names"][k]), [AXES[a] for a in np.where(_IDX["axes"][k] > 0)[0]]

def readings(text, top, accepted=None):
    """possible diseases a typed text may mean: expansions of a known abbreviation (index v2+: NLM SPECIALIST Lexicon LRABR,
    expansions linked to MONDO offline) and near-ties of the SapBERT search. -> [{mondo, name, organs, why}] (at most 6).
    accepted: whether the first of top is taken (the reranker decides it in index v4+); default: similarity >= THETA."""
    out, seen = [], set()
    ok = (top[0][1] >= THETA) if accepted is None else accepted
    def add(t, why):
        if t in seen: return
        name, organs = concept(t)
        if name is None: return
        seen.add(t); out.append(dict(mondo=t, name=name, organs=organs, why=why))
    if top and ok: add(top[0][0], "closest name")
    if "abbr_keys" in _IDX and ABBREV.match(text.strip()):
        for t in abbreviations(text): add(t, "abbreviation")
    if top and ok:
        for t, sim in top[1:]:
            if sim >= top[0][1] - TIE: add(t, "similar name")
    return out[:6]


def abbreviations(text):
    """MONDO ids an abbreviation may stand for (index v2+), most established first; [] for other text."""
    if "abbr_keys" not in _IDX or not ABBREV.match(text.strip()): return []
    if "_abbr" not in _IDX: _IDX["_abbr"] = dict(zip([str(x) for x in _IDX["abbr_keys"]], [str(x) for x in _IDX["abbr_vals"]]))
    return [t for t in _IDX["_abbr"].get(text.strip().lower(), "").split(";") if t]


# ------------------------------------------------------------------ reranker (index v4+)
RR_K = 10                   # concepts reranked: the 10 nearest among the 64 nearest strings


def concept_candidates(jj, vv):
    """-> [(MONDO id, best string similarity, strings of it among the 64 nearest)] for the RR_K nearest concepts."""
    best, cnt = {}, {}
    for j, s in zip(jj, vv):
        t = _IDX["_ids"][j]; cnt[t] = cnt.get(t, 0) + 1
        if t not in best: best[t] = float(s)
    return [(t, best[t], cnt[t]) for t in sorted(best, key=lambda t: -best[t])[:RR_K]]


def _tri(s):
    s = " " + " ".join(re.findall(r"[a-z0-9]+", s.lower())) + " "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def rr_features(text, cands):
    """one row per candidate: similarity, gap to the first, rank, strings hit, spelling overlap with the concept name, how
    common the concept is in the literature, abbreviation-table hit and the shape of the typed text (a BioLORD similarity was
    tried and lowered dev F1: ml/results/benchmarks/rerank_v1.json notes)."""
    q = text.strip(); qw = set(re.findall(r"[a-z0-9]+", q.lower())); qt = _tri(q); ab = set(abbreviations(q)); is_ab = float(bool(ABBREV.match(q)))
    if "_prior" not in _IDX: _IDX["_prior"] = dict(zip([str(x) for x in _IDX.get("rr_prior_ids", [])], [float(x) for x in _IDX.get("rr_prior", [])]))
    top = cands[0][1]; rows = []
    for r, (t, s, c) in enumerate(cands):
        name, organs = concept(t); name = name or ""; nw = set(re.findall(r"[a-z0-9]+", name.lower())); nt = _tri(name); hit = float(t in ab)
        rows.append([s, top - s, r / RR_K, float(r == 0), np.log1p(c), len(qt & nt) / max(1, len(qt | nt)), len(qw & nw) / max(1, len(qw)),
                     len(qw & nw) / max(1, len(nw)), len(nw) / 10, _IDX["_prior"].get(t, 0.0), hit, is_ab, is_ab * hit, is_ab * s,
                     float(bool(organs)), len(q) / 30, float(any(ch.isdigit() for ch in q))])
    return np.array(rows, np.float32)


def rerank_scores(text, cands):
    X = rr_features(text, cands)
    return (((X - _IDX["rr_mu"]) / _IDX["rr_sd"]) @ _IDX["rr_w"] + float(_IDX["rr_b"])).tolist()


def judged_organs(q):
    """organs a small network reads off the text's SapBERT vector (trained on the Haiku concept-organ labels, ml/organ_head.py)."""
    h = np.maximum(q @ _IDX["oh_w1"] + _IDX["oh_b1"], 0); p = 1 / (1 + np.exp(-(h @ _IDX["oh_w2"] + _IDX["oh_b2"])))
    return [AXES[k] for k in np.where(p >= _IDX["oh_thr"])[0]]


# ------------------------------------------------------------------ phenotypes (symptoms, findings) when no disease matches
HPO_THETA = 0.85            # a phenotype (HPO term) is accepted only on a close name match

def phenotype(text, q):
    """-> {hpo, name, sim, organs} from the index's HPO block (index v2+), or None. Organs come from the HPO top-level branch."""
    if "hp_E" not in _IDX: return None
    if "_hpE" not in _IDX: _IDX["_hpE"] = _IDX["hp_E"].astype(np.float32)
    s = _IDX["_hpE"] @ q; k = int(s.argmax()); sim = float(s[k])
    if sim < HPO_THETA: return None
    organs = [AXES[a] for a in np.where(_IDX["hp_axes"][k] > 0)[0]]
    return dict(hpo=str(_IDX["hp_ids"][k]), name=str(_IDX["hp_names"][k]), sim=sim, organs=organs) if organs else None

# ------------------------------------------------------------------ Korean disease names (index v3+: HIRA KCD master, Korean -> English)
HANGUL = re.compile("[가-힣]")

def _ko_norm(s): return re.sub(r"[\s·]", "", re.sub(r"\([^)]*[A-Z][0-9][^)]*\)", "", s)).lower()

def korean(text):
    """English name for a Korean disease name, or None: a curated everyday word or an exact KCD name ('상세불명의 X' counts as X),
    else the most general KCD code whose name ends with the typed words (Korean puts the head noun last: 자폐증 -> 소아기 자폐증). Never a name merely containing them."""
    global _IDX
    if not HANGUL.search(text): return None
    if _IDX is None:
        _IDX = dict(np.load(adc_runtime.model_path("mondo_index.npz", C + "mondo_index.npz"), allow_pickle=not adc_runtime.restricted_bundle()))
        _IDX["_ids"] = [str(x) for x in _IDX["ids"]]
    if "ko_keys" not in _IDX: return None
    if "_ko" not in _IDX: _IDX["_ko"] = {str(k): (str(v), int(r)) for k, v, r in zip(_IDX["ko_keys"], _IDX["ko_vals"], _IDX["ko_rank"])}
    q = _ko_norm(text); hit = _IDX["_ko"].get(q)
    if hit or len(q) < 2: return hit[0] if hit else None
    ends = [k for k in _IDX["_ko"] if k.endswith(q)]                 # the most general code first, then the shortest name
    return _IDX["_ko"][min(ends, key=lambda k: (_IDX["_ko"][k][1], len(k), k))][0] if ends else None

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build": os.environ["ADC_RESEARCH_MODE"] = "1"; build()
    else: [print(r) for r in link(sys.argv[1:] or ["asthma", "hypertension", "rheumatoid arthritis"])]
