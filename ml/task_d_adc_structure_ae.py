"""Task D: ADC structure -> incidence of a named adverse-event term, for an ADC the model never saw.

The question is not "how well can we predict a rate" -- term and grade alone already explain
most of that -- but "what does the ADC's structure add". So every structure model is scored
against the *same* model with the structure columns removed, paired by held-out ADC.

Regimes: leave-ADC-out (a new molecule), leave-payload-out (a new payload: no training ADC
shares the held-out one's cytotoxic agent), which is the one the design question needs.
"""
import json, os, warnings
import numpy as np, pandas as pd, torch, torch.nn as nn
import lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.decomposition import PCA

warnings.filterwarnings("ignore")
SRC = "/data/hyeongchanahn/adctox/ml_cache/"
EMB = "/data/hyeongchanahn/adctox/ml_cache/sapbert.npz"
OUT = "/home/hyeongchanahn/CONI/adctox/ml/results/task_d.json"
DEV = "cuda:0"            # set CUDA_VISIBLE_DEVICES to pick the card
SEEDS, FOLDS = 3, 5

t = pd.read_pickle(SRC + "tox.pkl"); ms = pd.read_pickle(SRC + "master.pkl")
t = t[t["Canonical observation"].astype(str) == "True"].copy()
t = t[~t["Toxicity domain"].astype(str).str.startswith("Aggregate")]
a = pd.to_numeric(t["Affected n"], errors="coerce"); N = pd.to_numeric(t["At risk N"], errors="coerce")
pct = pd.to_numeric(t["Incidence percent"], errors="coerce")
t["rate"] = np.where(pct.notna(), pct / 100, a / N); t["N"] = N
t = t[t.rate.between(0, 1)].copy()
G = {"Any grade": "any", "Grade 1-2": "g12", "Grade 3": "g3", "Grade 3-4": "g34", "Grade >=3": "g3p", "Grade 4": "g4", "Grade 5": "g5"}
t["grade"] = t["Grade category"].map(G); t = t.dropna(subset=["grade"])
t["y"] = np.log((t.rate.clip(0.005, 0.995)) / (1 - t.rate.clip(0.005, 0.995)))
STRUCT = {"payload": ["Payload", "Payload class", "Payload MOA", "Bystander effect"],
          "linker": ["Linker type", "Linker mechanism", "Conjugation", "Conjugation site"],
          "antibody": ["Target", "Antibody type", "IgG subtype"]}
t = t.merge(ms[["ADC ID", "DAR"] + sum(STRUCT.values(), [])], on="ADC ID", how="left", suffixes=("", "_m"))
t["DAR_n"] = pd.to_numeric(t["DAR"], errors="coerce")
t["mono"] = (t["Monotherapy"] == "Yes").astype(float); t["logN"] = np.log(t.N.fillna(t.N.median()).clip(5))
t["term"] = t["Raw AE term"].astype(str).str.strip(); t = t.reset_index(drop=True)
z = np.load(EMB, allow_pickle=True); ix = {k: i for i, k in enumerate(z["keys"])}
TE = np.stack([z["emb"][ix[s]] for s in t.term]).astype(np.float32)
y = t.y.values.astype(np.float32)
print(f"rows {len(t)}  ADCs {t['ADC ID'].nunique()}  payloads {t.Payload.nunique()}  terms {t.term.nunique()}  grades {t.grade.value_counts().to_dict()}", flush=True)

grade_oh = pd.get_dummies(t.grade).values.astype(np.float32)
dom_oh = pd.get_dummies(t["Toxicity domain"]).values.astype(np.float32)
base_ctx = np.c_[grade_oh, dom_oh, t.mono.values, t.logN.values].astype(np.float32)
codes = {c: t[c].fillna("NA").astype(str).astype("category").cat.codes.values for c in sum(STRUCT.values(), [])}   # a blank field is its own category, never -1
FEATS = {"no_structure": [], "payload": STRUCT["payload"], "payload+linker": STRUCT["payload"] + STRUCT["linker"],
         "all_structure": sum(STRUCT.values(), [])}

def struct_matrix(cols, train_idx):
    """categoricals as codes; a category unseen in training becomes NaN (LightGBM) / unknown (MLP)."""
    M = np.full((len(t), len(cols) + 1), np.nan, dtype=np.float32)
    for j, c in enumerate(cols):
        seen = set(codes[c][train_idx]); M[:, j] = np.where(np.isin(codes[c], list(seen)), codes[c], np.nan)
    M[:, -1] = t.DAR_n.values
    return M

class Net(nn.Module):
    def __init__(s, n_cat, card, d_ctx, h=192, p=0.3):
        super().__init__()
        s.emb = nn.ModuleList([nn.Embedding(c + 1, 8) for c in card])      # last index = unknown
        s.ft = nn.Sequential(nn.Linear(768, h), nn.GELU(), nn.Dropout(p))
        s.fs = nn.Sequential(nn.Linear(8 * n_cat + 1, h), nn.GELU(), nn.Dropout(p)) if n_cat else None
        s.head = nn.Sequential(nn.Linear((3 if n_cat else 1) * h + d_ctx, h), nn.GELU(), nn.Dropout(p), nn.Linear(h, 1))
    def forward(s, te, cat, dar, ctx):
        a = s.ft(te)
        if s.fs is None: return s.head(torch.cat([a, ctx], 1)).squeeze(1)
        b = s.fs(torch.cat([e(cat[:, j]) for j, e in enumerate(s.emb)] + [dar[:, None]], 1))
        return s.head(torch.cat([a, b, a * b, ctx], 1)).squeeze(1)

def fit_nn(cols, tr, va, te, seed, trall):
    torch.manual_seed(seed); torch.cuda.manual_seed(seed)
    M = struct_matrix(cols, trall); card = [int(np.nanmax(M[:, j])) + 1 for j in range(len(cols))]
    cat = np.where(np.isnan(M[:, :-1]), np.array(card)[None, :], M[:, :-1]).astype(np.int64) if cols else np.zeros((len(t), 0), np.int64)
    dar = np.nan_to_num((M[:, -1] - np.nanmean(M[trall, -1])) / (np.nanstd(M[trall, -1]) + 1e-6)).astype(np.float32)
    mu, sd = y[tr].mean(), y[tr].std()
    T = lambda arr, ix: torch.tensor(arr[ix], device=DEV)
    net = Net(len(cols), card, base_ctx.shape[1]).to(DEV); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=5e-2)
    Y = torch.tensor((y[tr] - mu) / sd, device=DEV); args = lambda ix: (T(TE, ix), T(cat, ix), T(dar, ix), T(base_ctx, ix))
    A = args(tr); best, bad, state = 1e9, 0, None
    for ep in range(200):
        net.train(); perm = torch.randperm(len(tr), device=DEV)
        for i in range(0, len(tr), 512):
            j = perm[i:i + 512]; c = A[1][j].clone()
            if cols:   # category dropout -> learns the "unknown" embedding the held-out payload will need
                drop = torch.rand(c.shape, device=DEV) < 0.15; c[drop] = torch.tensor(card, device=DEV)[None, :].expand_as(c)[drop]
            loss = nn.functional.huber_loss(net(A[0][j], c, A[2][j], A[3][j]), Y[j]); opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad(): v = nn.functional.mse_loss(net(*args(va)), torch.tensor((y[va] - mu) / sd, device=DEV)).item()
        if v < best - 1e-4: best, bad, state = v, 0, {k: x.clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 12: break
    net.load_state_dict(state); net.eval()
    with torch.no_grad(): return net(*args(te)).cpu().numpy() * sd + mu

def fit_gbm(cols, tr, te, seed, trall, pca):
    Z = np.c_[pca.transform(TE), base_ctx, struct_matrix(cols, trall)]
    g = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.04, num_leaves=31, min_child_samples=25, subsample=0.8,
                          subsample_freq=1, colsample_bytree=0.7, reg_lambda=5, random_state=seed, verbose=-1)
    return g.fit(Z[tr], y[tr]).predict(Z[te])

def lookup(tr, te):
    d = t.iloc[tr]; mu = d.y.mean(); g = d.groupby(["term", "grade"]).y.mean(); g2 = d.groupby(["Toxicity domain", "grade"]).y.mean()
    x = t.iloc[te]
    return np.array([g.get((a, b), g2.get((c, b), mu)) for a, b, c in zip(x.term, x.grade, x["Toxicity domain"])])

def r2(yt, p): return 1 - ((yt - p) ** 2).sum() / ((yt - yt.mean()) ** 2).sum()

results = {}
for regime in ["adc", "payload"]:
    key = t["ADC ID"] if regime == "adc" else t.Payload
    names = ["lookup"] + [f"{m}:{v}" for m in ["lightgbm", "mlp"] for v in FEATS]
    per = {n: [] for n in names}; per_adc = {n: {} for n in names}
    for seed in range(SEEDS):
        rng = np.random.default_rng(seed); u = key.unique(); rng.shuffle(u); fm = {k: i % FOLDS for i, k in enumerate(u)}
        f = key.map(fm).values; pred = {n: np.zeros(len(t)) for n in names}
        for k in range(FOLDS):
            te = np.where(f == k)[0]; trall = np.where(f != k)[0]
            kk = key.iloc[trall].unique(); r = np.random.default_rng(50 + 10 * seed + k)
            vk = set(r.choice(kk, max(1, len(kk) // 8), replace=False)); isv = key.iloc[trall].isin(vk).values
            va, tr = trall[isv], trall[~isv]; pca = PCA(32, random_state=0).fit(TE[trall])
            pred["lookup"][te] = lookup(trall, te)
            for v, cols in FEATS.items():
                pred[f"lightgbm:{v}"][te] = fit_gbm(cols, tr, te, seed, trall, pca)
                pred[f"mlp:{v}"][te] = np.mean([fit_nn(cols, tr, va, te, seed * 5 + q, trall) for q in range(2)], 0)
        for n in names:
            per[n].append(dict(r2=r2(y, pred[n]), spearman=spearmanr(y, pred[n])[0]))
            for adc, ix in t.groupby("ADC ID").indices.items():       # per-ADC squared error for the paired bootstrap
                per_adc[n].setdefault(adc, []).append(((y[ix] - pred[n][ix]) ** 2).sum())
        print(f"[{regime}] seed {seed}", {n: round(per[n][-1]["r2"], 3) for n in ["lookup", "lightgbm:no_structure", "lightgbm:all_structure", "mlp:no_structure", "mlp:all_structure"]}, flush=True)
    summ = {n: {k: float(np.mean([x[k] for x in per[n]])) for k in ["r2", "spearman"]} for n in names}
    sst = {adc: ((y[ix] - y.mean()) ** 2).sum() for adc, ix in t.groupby("ADC ID").indices.items()}
    def gap(a, b):   # paired bootstrap over held-out ADCs: R2(a) - R2(b)
        adcs = sorted(sst); sa = np.array([np.mean(per_adc[a][x]) for x in adcs]); sb = np.array([np.mean(per_adc[b][x]) for x in adcs]); ss = np.array([sst[x] for x in adcs])
        rng = np.random.default_rng(0); d = []
        for _ in range(3000):
            j = rng.integers(0, len(adcs), len(adcs)); d.append((sb[j].sum() - sa[j].sum()) / ss[j].sum())
        return dict(delta_r2=float((sb.sum() - sa.sum()) / ss.sum()), lo=float(np.percentile(d, 2.5)), hi=float(np.percentile(d, 97.5)))
    for m in ["lightgbm", "mlp"]:
        for v in ["payload", "payload+linker", "all_structure"]:
            summ[f"{m}:{v}"]["vs_no_structure"] = gap(f"{m}:{v}", f"{m}:no_structure")
    summ["mlp:all_structure"]["vs_lookup"] = gap("mlp:all_structure", "lookup")
    results[regime] = summ
    print(f"\n=== held out: {regime} ===")
    for n, s in summ.items():
        g = s.get("vs_no_structure"); extra = f"   structure adds {g['delta_r2']:+.3f} [{g['lo']:+.3f}, {g['hi']:+.3f}] R2 over the same model without it" if g else ""
        print(f"{n:26s} R2 {s['r2']:+.3f} Spearman {s['spearman']:.3f}{extra}", flush=True)

os.makedirs(os.path.dirname(OUT), exist_ok=True); json.dump(results, open(OUT, "w"), indent=1)
