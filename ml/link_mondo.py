"""Link every FinnGen prior disease to its nearest MONDO class, and read off ontology features.

Why: a disease name embedding does not know which organ system the disease belongs to, but MONDO's
is_a hierarchy does (the project already ships the ancestor -> organ crosswalk, conf/ontology/
mondo_organ_axis.yaml). The definition text of the linked class is a second, richer input.

The link uses names only (SapBERT cosine against MONDO names + exact synonyms), never an outcome, so the
ontology features cannot carry FinnGen outcome information into the held-out folds.

Gate: the linker is scored on the 41 registry conditions, whose MONDO ids were curated by hand. THETA is
fixed before looking at any downstream result: below it the link is discarded (features zero), not trusted.
Output (cache only; contains FinnGen disease names): $C/mondo_link.pkl
"""
import re, sys, pickle, time, collections, warnings
import numpy as np, pandas as pd, torch, yaml, csv
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
C = "/data/hyeongchanahn/adctox/ml_cache/"; OBO = "/home/hyeongchanahn/CONI/adctox/data/raw_big/mondo/2026-10-07/mondo.obo"
THETA = 0.75
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]

def parse(path):
    T = {}; cur = None; term = False
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": term, cur = True, None; continue
        if line.startswith("["): term = False; continue
        if not term or not line: continue
        if line.startswith("id: "): cur = line[4:].strip(); T[cur] = dict(name="", syn=[], defn="", parents=set(), obs=False)
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:].strip()
        elif line.startswith("is_obsolete: true"): T[cur]["obs"] = True
        elif line.startswith("def: "):
            q = re.match(r'def: "(.*)" \[', line); T[cur]["defn"] = q.group(1) if q else ""
        elif line.startswith("synonym: ") and " EXACT " in line:
            q = re.match(r'synonym: "(.*)" EXACT', line); T[cur]["syn"].append(q.group(1)) if q else None
        elif line.startswith("is_a: "):
            p = line[6:].split()[0]
            if p.startswith(("MONDO:", "HP:")): T[cur]["parents"].add(p)
    return T

def clean(s):
    s = re.sub(r"\((?:[^)]*(?:strict|KELA|require|HDR|definition|operations|surgery)[^)]*)\)", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ,;")

def retry(fn):
    def w(*a, **k):
        for _ in range(120):
            try: return fn(*a, **k)
            except torch.OutOfMemoryError: torch.cuda.empty_cache(); time.sleep(30)
        raise RuntimeError
    return w

@retry
@torch.no_grad()
def embed_all(strs, bs=512):
    from transformers import AutoTokenizer, AutoModel
    name = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"; tok = AutoTokenizer.from_pretrained(name); mod = AutoModel.from_pretrained(name).cuda().half().eval(); out = []
    for i in range(0, len(strs), bs):
        b = tok(strs[i:i + bs], padding=True, truncation=True, max_length=48, return_tensors="pt").to("cuda"); out.append(mod(**b).last_hidden_state[:, 0].float().cpu().numpy())
    E = np.concatenate(out); return E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)

T = parse(OBO)
def anc(t):
    seen, st = set(), list(T[t]["parents"]) if t in T else []
    while st:
        n = st.pop()
        if n in seen: continue
        seen.add(n); st.extend(T[n]["parents"] if n in T else ())
    return seen
disease = {t for t in T if t.startswith("MONDO:") and not T[t]["obs"] and T[t]["name"] and ("MONDO:0000001" in anc(t) or t == "MONDO:0000001")}
print("MONDO diseases:", len(disease), flush=True)
cand, cid = [], []
for t in sorted(disease):
    for s in [T[t]["name"]] + T[t]["syn"]: cand.append(s); cid.append(t)
cross = {k.lower(): v for k, v in yaml.safe_load(open("/home/hyeongchanahn/CONI/adctox/conf/ontology/mondo_organ_axis.yaml"))["ancestor_to_axis"].items()}

m = pd.read_parquet(C + "finngen.parquet"); up = m.drop_duplicates("prior_name")[["prior_name", "prior_longname"]].reset_index(drop=True)
reg = list(csv.DictReader(open("/home/hyeongchanahn/CONI/adctox/conf/comorbidity_registry.csv")))
q_txt = [clean(str(s)) for s in up.prior_longname.fillna(up.prior_name)] + [r["label"] for r in reg]
print("embedding", len(cand), "MONDO strings and", len(q_txt), "queries", flush=True)
EC = embed_all(cand); EQ = embed_all(q_txt)
cid = np.array(cid); best_sim = np.zeros(len(q_txt)); best_id = np.empty(len(q_txt), dtype=object)
for i in range(0, len(q_txt), 256):
    S = EQ[i:i + 256] @ EC.T; j = S.argmax(1); best_sim[i:i + 256] = S[np.arange(len(j)), j]; best_id[i:i + 256] = cid[j]

def axes_of(t):
    v = np.zeros(len(AXES), np.float32)
    for a in anc(t) | {t}:
        ax = cross.get(T[a]["name"].lower()) if a in T else None
        if ax in AXES: v[AXES.index(ax)] = 1
    return v

n = len(up); rows = []
for i in range(n):
    t = best_id[i]; ok = best_sim[i] >= THETA
    rows.append(dict(prior_name=up.prior_name[i], query=q_txt[i], mondo=t, mondo_name=T[t]["name"], sim=float(best_sim[i]), linked=bool(ok),
                     defn=T[t]["defn"] if ok else "", ax=axes_of(t) if ok else np.zeros(len(AXES), np.float32)))
df = pd.DataFrame(rows)
print(f"FinnGen priors linked at sim >= {THETA}: {df.linked.mean():.1%} ({int(df.linked.sum())}/{n}); with a definition: {(df.defn != '').mean():.1%}; any organ axis: {(df.ax.map(lambda v: v.sum() > 0)).mean():.1%}", flush=True)

# gate: the 41 curated registry conditions
ok_exact = ok_axes = scored = 0
for k, r in enumerate(reg):
    t = best_id[n + k]; want = r["mondo_id"].strip(); got_axes = {AXES[a] for a in np.where(axes_of(t) > 0)[0]}; hand = {a for a in r["organ_axes"].split(";")}
    scored += 1; ok_exact += int(t == want); ok_axes += int(bool(got_axes & hand))
print(f"REGISTRY GATE: linker returns the curated MONDO id for {ok_exact}/{scored}; linked class's organ axes overlap the hand axes for {ok_axes}/{scored}", flush=True)
pickle.dump(dict(df=df, axes=AXES, theta=THETA, registry_gate=dict(exact=ok_exact, axes=ok_axes, n=scored)), open(C + "mondo_link.pkl", "wb"))
