"""Task A: comorbidity -> organ-outcome hazard ratio, learned from the FinnGen mapping.

Question the product needs answered: for a patient with prior disease X, how much more
likely is an event in organ Y -- i.e. which organs are already vulnerable. This replaces the
hand-set organ weights (``comorbidity_weights`` in design/search.py) with something fitted.

What it is NOT: a drug-toxicity model. FinnGen hazard ratios are natural disease progression.

Three held-out regimes, increasingly strict, because the easy one flatters:
  pair     (prior, outcome) pairs unseen -- fill-in-the-blank among known diseases
  prior    whole prior diseases unseen   -- a comorbidity the model never saw
  cluster  whole ICD-style families unseen (K11_*, N14_* ...) -- no near-duplicate
           definitions of the same disease can leak across the split
Baselines are lookup tables built from training rows only; a model that cannot beat them
has learned nothing the registry's own labels did not already say.
"""
import json, sys, warnings
import numpy as np, pandas as pd, torch, torch.nn as nn
import lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.decomposition import PCA

warnings.filterwarnings("ignore")
SRC = "/data/hyeongchanahn/adctox/ml_cache/"
EMB = "/data/hyeongchanahn/adctox/ml_cache/sapbert.npz"
import os
SKIP_GBM = os.environ.get("SKIP_GBM") == "1"          # ablation runs compare the MLP only
MODELS = ["lookup", "mlp"] + ([] if SKIP_GBM else ["lightgbm"])
KIND = os.environ.get("EMB_KIND", "sapbert")          # sapbert | tfidf | random (identity-only control)
OUT = f"/home/hyeongchanahn/CONI/adctox/ml/results/task_a_{KIND}.json"
DEV = "cuda:0"
SEEDS, FOLDS = 3, 5

# ---------------------------------------------------------------- data
m = pd.read_parquet(SRC + "finngen.parquet")
m = m[(m.qc_flag == "OK") & (m.hr > 0) & (m.hr <= 100)].reset_index(drop=True)
m["y"] = np.log(m.hr)
m["dom"] = m.mapped_toxicity_domain.str.split(" / ").str[0]
m["fam"] = m.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0]       # K11, N14, C3 ...
m["chap"] = m.prior_name.str.extract(r"^([A-Za-z]+)")[0]
z = np.load(EMB, allow_pickle=True); idx = {k: i for i, k in enumerate(z["keys"])}
E = z["emb"]
if KIND != "sapbert":      # same strings, same dimensionality, different amount of semantics
    keys = list(z["keys"])
    if KIND == "tfidf":
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        E = TruncatedSVD(768, random_state=0).fit_transform(TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit_transform(keys))
    else:
        E = np.random.default_rng(0).standard_normal((len(keys), 768))
    E = (E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)).astype(np.float32)
pe = np.stack([E[idx[s.strip()]] for s in m.prior_longname.fillna(m.prior_name)])
oe = np.stack([E[idx[s.strip()]] for s in m.outcome_longname])
lag = pd.get_dummies(m.hr_lag).values.astype(np.float32)
dom = pd.get_dummies(m.dom).values.astype(np.float32)
y = m.y.values.astype(np.float32)
print(f"rows {len(m)}  priors {m.prior_name.nunique()}  families {m.fam.nunique()}  outcomes {m.outcome_name.nunique()}", flush=True)

# ---------------------------------------------------------------- models
class Net(nn.Module):
    def __init__(s, d_ctx, h=256, p=0.25):
        super().__init__()
        s.fp = nn.Sequential(nn.Linear(768, h), nn.GELU(), nn.Dropout(p))
        s.fo = nn.Sequential(nn.Linear(768, h), nn.GELU(), nn.Dropout(p))
        s.head = nn.Sequential(nn.Linear(3 * h + d_ctx, h), nn.GELU(), nn.Dropout(p), nn.Linear(h, 1))
    def forward(s, p, o, c):
        a, b = s.fp(p), s.fo(o)
        return s.head(torch.cat([a, b, a * b, c], 1)).squeeze(1)

def fit_nn(tr, va, te, seed):
    torch.manual_seed(seed)
    T = lambda a, ix: torch.tensor(a[ix], device=DEV)
    ctx = np.c_[lag, dom].astype(np.float32); mu, sd = y[tr].mean(), y[tr].std()
    net = Net(ctx.shape[1]).to(DEV); opt = torch.optim.AdamW(net.parameters(), 3e-3, weight_decay=1e-2)
    Xp, Xo, Xc, Y = T(pe, tr), T(oe, tr), T(ctx, tr), torch.tensor((y[tr] - mu) / sd, device=DEV)
    best, bad, state = 1e9, 0, None
    for ep in range(200):
        net.train(); perm = torch.randperm(len(tr), device=DEV)
        for i in range(0, len(tr), 8192):
            j = perm[i:i + 8192]
            loss = nn.functional.huber_loss(net(Xp[j], Xo[j], Xc[j]), Y[j]); opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad():
            v = nn.functional.mse_loss(net(T(pe, va), T(oe, va), T(ctx, va)), torch.tensor((y[va] - mu) / sd, device=DEV)).item()
        if v < best - 1e-4: best, bad, state = v, 0, {k: x.clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 15: break
    net.load_state_dict(state); net.eval()
    with torch.no_grad():
        return net(T(pe, te), T(oe, te), T(ctx, te)).cpu().numpy() * sd + mu


import time as _time
def _retry_oom(fn):
    """The GPUs are shared and other jobs fill them; wait and retry instead of losing hours of folds."""
    def w(*a, **k):
        for _ in range(120):
            try: return fn(*a, **k)
            except torch.OutOfMemoryError: torch.cuda.empty_cache(); _time.sleep(30)
        raise RuntimeError("GPU stayed full for an hour")
    return w
fit_nn = _retry_oom(fit_nn)

def fit_gbm(tr, te, seed, pca):
    Z = np.c_[pca[0].transform(pe), pca[1].transform(oe), lag, dom]
    g = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.08, num_leaves=63, min_child_samples=30,
                          subsample=0.8, subsample_freq=1, colsample_bytree=0.6, reg_lambda=3,
                          random_state=seed, verbose=-1, n_jobs=4)
    return g.fit(Z[tr], y[tr]).predict(Z[te])

def lookup(tr, te, regime):
    d = m.iloc[tr]; mu = d.y.mean()
    if regime == "pair":     # best additive table that exists for a seen prior and outcome
        pm = d.groupby("prior_name").y.mean(); om = d.groupby("outcome_name").y.mean()
        return (m.iloc[te].prior_name.map(pm).fillna(mu) + m.iloc[te].outcome_name.map(om).fillna(mu) - mu).values
    g = d.groupby(["outcome_name", "chap", "hr_lag"]).y.mean(); g2 = d.groupby(["outcome_name", "hr_lag"]).y.mean()
    t = m.iloc[te]
    return np.array([g.get((a, b, c), g2.get((a, c), mu)) for a, b, c in zip(t.outcome_name, t.chap, t.hr_lag)])

# ---------------------------------------------------------------- evaluation
def organ_metrics(te, pred):
    """per held-out prior: does the model rank organs right? Mean over priors, plus per-prior list for CIs."""
    t = m.iloc[te][["prior_name", "dom", "y"]].assign(p=pred).groupby(["prior_name", "dom"]).mean().reset_index()
    rho, hit = {}, {}
    for pn, a in t.groupby("prior_name"):
        if len(a) < 6 or a.y.nunique() < 2 or a.p.nunique() < 2: continue
        rho[pn] = spearmanr(a.y, a.p)[0]
        k = min(3, len(a)); hit[pn] = len(set(a.nlargest(k, "y").dom) & set(a.nlargest(k, "p").dom)) / k
    return rho, hit

def splits(regime, seed):
    rng = np.random.default_rng(seed)
    key = {"pair": m.prior_name + "|" + m.outcome_name, "prior": m.prior_name, "cluster": m.fam}[regime]
    u = key.unique(); rng.shuffle(u); fm = {k: i % FOLDS for i, k in enumerate(u)}
    return key.map(fm).values, key

results = {}
for regime in ["pair", "prior", "cluster"]:
    P = {k: np.full(len(m), np.nan) for k in MODELS}
    per = {k: [] for k in P}
    for seed in range(SEEDS):
        f, key = splits(regime, seed); pred = {k: np.zeros(len(m)) for k in P}
        for k in range(FOLDS):
            te = np.where(f == k)[0]; trall = np.where(f != k)[0]
            # inner validation by the same grouping, for early stopping only
            kk = key.iloc[trall].unique(); rng = np.random.default_rng(100 + seed * 10 + k); vk = set(rng.choice(kk, max(1, len(kk) // 10), replace=False))
            isv = key.iloc[trall].isin(vk).values; va, tr = trall[isv], trall[~isv]
            pca = (PCA(48, random_state=0).fit(pe[trall]), PCA(48, random_state=0).fit(oe[trall]))
            pred["lookup"][te] = lookup(trall, te, regime)
            if not SKIP_GBM: pred["lightgbm"][te] = fit_gbm(trall, te, seed, pca)
            pred["mlp"][te] = np.mean([fit_nn(tr, va, te, seed * 7 + r) for r in range(2)], 0)
        for kname, v in pred.items():
            r2 = 1 - ((y - v) ** 2).sum() / ((y - y.mean()) ** 2).sum()
            rho, hit = organ_metrics(np.arange(len(m)), v)
            per[kname].append(dict(r2=r2, spearman=spearmanr(y, v)[0], organ_rho=float(np.mean(list(rho.values()))),
                                   organ_top3=float(np.mean(list(hit.values()))), _rho=rho, _hit=hit))
        print(f"[{regime}] seed {seed} done", {k: round(per[k][-1]['r2'], 3) for k in per}, flush=True)
    summ = {}
    for kname, L in per.items():
        summ[kname] = {mt: float(np.mean([x[mt] for x in L])) for mt in ["r2", "spearman", "organ_rho", "organ_top3"]}
    # paired bootstrap over held-out priors/families for the organ-ranking gap vs lookup
    def boot(model, mt):
        keys = sorted(set.intersection(*[set(x[mt]) for x in per[model]], *[set(x[mt]) for x in per["lookup"]]))
        a = np.array([np.mean([x[mt][p] for x in per[model]]) - np.mean([x[mt][p] for x in per["lookup"]]) for p in keys])
        fam_of = m.drop_duplicates("prior_name").set_index("prior_name").fam; fams = np.array([fam_of[p] for p in keys]); uf = np.unique(fams)
        by = {f_: a[fams == f_] for f_ in uf}; rng = np.random.default_rng(0); bs = []
        for _ in range(2000):                        # resample whole ICD families: priors inside a family are not independent
            pick = rng.choice(uf, len(uf)); v = np.concatenate([by[f_] for f_ in pick]); bs.append(v.mean())
        return dict(delta=float(a.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n_priors=len(a), n_families=len(uf))
    for mdl in [x for x in MODELS if x != "lookup"]:
        summ[mdl]["organ_rho_vs_lookup"] = boot(mdl, "_rho"); summ[mdl]["organ_top3_vs_lookup"] = boot(mdl, "_hit")
    results[regime] = summ
    os.makedirs(os.path.dirname(OUT), exist_ok=True); json.dump(results, open(OUT, "w"), indent=1)
    print(f"\n=== regime: {regime} ===")
    for kname, s in summ.items():
        extra = "" if "organ_rho_vs_lookup" not in s else f"  organ-rho gap vs lookup {s['organ_rho_vs_lookup']['delta']:+.3f} [{s['organ_rho_vs_lookup']['lo']:+.3f}, {s['organ_rho_vs_lookup']['hi']:+.3f}]"
        print(f"{kname:9s} R2 {s['r2']:+.3f}  Spearman {s['spearman']:.3f}  organ-rho {s['organ_rho']:.3f}  top3 {s['organ_top3']:.3f}{extra}", flush=True)

import os; os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(results, open(OUT, "w"), indent=1); print("wrote", OUT)
