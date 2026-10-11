"""Task D, low-variance reformulation: structure enters only as a heavily regularised correction.

task_d_adc_structure_ae.py found that handing the structure columns to a flexible model makes a
new-ADC prediction *worse* (75 ADCs cannot support a free interaction between a payload and
a term). The principled response is not a bigger model but a smaller degree of freedom:

    y_hat = p0(term, grade, context)  +  ridge( payload-class x organ-domain, linker x domain, ... )

p0 is the no-structure model. The correction is fitted on p0's *out-of-ADC* residuals (nested
grouped CV inside the training set) -- in-sample residuals are shrunk and would make the
correction look weaker than it is, or noisier, depending on the model.

One variant is tried. If it does not help, that is the result.
"""
import json, os, warnings
import numpy as np, pandas as pd
import lightgbm as lgb
from scipy.sparse import csr_matrix, hstack
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

warnings.filterwarnings("ignore")
SRC = "/data/hyeongchanahn/adctox/ml_cache/"
EMB = "/data/hyeongchanahn/adctox/ml_cache/sapbert.npz"
OUT = "/home/hyeongchanahn/CONI/adctox/ml/results/task_d2.json"
SEEDS, FOLDS, ALPHAS = 3, 5, [3, 10, 30, 100, 300, 1000]

t = pd.read_pickle(SRC + "tox.pkl"); ms = pd.read_pickle(SRC + "master.pkl")
t = t[t["Canonical observation"].astype(str) == "True"].copy(); t = t[~t["Toxicity domain"].astype(str).str.startswith("Aggregate")]
a = pd.to_numeric(t["Affected n"], errors="coerce"); N = pd.to_numeric(t["At risk N"], errors="coerce"); pct = pd.to_numeric(t["Incidence percent"], errors="coerce")
t["rate"] = np.where(pct.notna(), pct / 100, a / N); t["N"] = N; t = t[t.rate.between(0, 1)].copy()
G = {"Any grade": "any", "Grade 1-2": "g12", "Grade 3": "g3", "Grade 3-4": "g34", "Grade >=3": "g3p", "Grade 4": "g4", "Grade 5": "g5"}
t["grade"] = t["Grade category"].map(G); t = t.dropna(subset=["grade"])
t["y"] = np.log(t.rate.clip(0.005, 0.995) / (1 - t.rate.clip(0.005, 0.995)))
cols = ["Payload", "Payload class", "Payload MOA", "Bystander effect", "Linker type", "Linker mechanism", "Conjugation", "Antibody type"]
t = t.merge(ms[["ADC ID"] + cols], on="ADC ID", how="left", suffixes=("", "_m")); t = t.reset_index(drop=True)
for c in cols: t[c] = t[c].fillna("NA").astype(str)
t["term"] = t["Raw AE term"].astype(str).str.strip(); t["mono"] = (t.Monotherapy == "Yes").astype(float); t["logN"] = np.log(t.N.fillna(t.N.median()).clip(5))
z = np.load(EMB, allow_pickle=True); ix = {k: i for i, k in enumerate(z["keys"])}
TE = np.stack([z["emb"][ix[s]] for s in t.term]).astype(np.float32); y = t.y.values
ctx = np.c_[pd.get_dummies(t.grade).values, pd.get_dummies(t["Toxicity domain"]).values, t.mono, t.logN].astype(np.float32)
dom = t["Toxicity domain"].values; grade = t.grade.values

def p0_fit_predict(tr, te, seed, pca):
    Z = np.c_[pca.transform(TE), ctx]
    g = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.04, num_leaves=31, min_child_samples=25, subsample=0.8, subsample_freq=1,
                          colsample_bytree=0.7, reg_lambda=5, random_state=seed, verbose=-1)
    return g.fit(Z[tr], y[tr]).predict(Z[te])

def design(level_cols, fit_idx):
    """one-hot of (structure level x organ domain x grade-kind); interaction so a payload class can shift only
    the organs it is known to hit rather than everything."""
    gk = np.where(np.isin(grade, ["any", "g12"]), "any", "sev")
    feats = [np.array((t[c].astype(str) + "|" + pd.Series(dom).astype(str) + "|" + pd.Series(gk).astype(str)).tolist(), dtype=object) for c in level_cols]
    enc = [OneHotEncoder(handle_unknown="ignore").fit(f[fit_idx].reshape(-1, 1)) for f in feats]
    return hstack([e.transform(f.reshape(-1, 1)) for e, f in zip(enc, feats)]).tocsr()

LEVELS = {"payload_class": ["Payload class"], "payload_class+moa": ["Payload class", "Payload MOA"],
          "payload+linker": ["Payload class", "Linker type"], "all_levels": ["Payload class", "Payload MOA", "Linker type", "Antibody type"]}

def fold_group_split(idx, key, k, rng):
    u = key.iloc[idx].unique(); rng.shuffle(u); fm = {x: i % k for i, x in enumerate(u)}; return key.iloc[idx].map(fm).values

def r2(yt, p): return 1 - ((yt - p) ** 2).sum() / ((yt - yt.mean()) ** 2).sum()

results = {}
for regime in ["adc", "payload"]:
    key = t["ADC ID"] if regime == "adc" else t.Payload
    names = ["p0"] + list(LEVELS); per = {n: [] for n in names}; sq = {n: {} for n in names}; alphas = {n: [] for n in LEVELS}
    for seed in range(SEEDS):
        rng = np.random.default_rng(seed); u = key.unique(); rng.shuffle(u); fm = {x: i % FOLDS for i, x in enumerate(u)}; f = key.map(fm).values
        pred = {n: np.zeros(len(t)) for n in names}
        for k in range(FOLDS):
            te = np.where(f == k)[0]; tr = np.where(f != k)[0]; pca = PCA(32, random_state=0).fit(TE[tr])
            pred["p0"][te] = p0_fit_predict(tr, te, seed, pca)
            # out-of-group residuals of p0 inside the training set
            inner = fold_group_split(tr, key, 5, np.random.default_rng(900 + seed * 10 + k)); oof = np.zeros(len(tr))
            for q in range(5):
                itr, ite = tr[inner != q], tr[inner == q]
                oof[inner == q] = p0_fit_predict(itr, ite, seed, PCA(32, random_state=0).fit(TE[itr]))
            res = y[tr] - oof
            for n, lc in LEVELS.items():
                X = design(lc, tr); best = (1e9, None)
                for al in ALPHAS:                # pick alpha by grouped CV on the residuals; never looks at the held-out fold
                    e = 0.0
                    for q in range(5):
                        m = Ridge(alpha=al).fit(X[tr[inner != q]], res[inner != q]); e += ((res[inner == q] - m.predict(X[tr[inner == q]])) ** 2).sum()
                    if e < best[0]: best = (e, al)
                alphas[n].append(best[1])
                pred[n][te] = pred["p0"][te] + Ridge(alpha=best[1]).fit(X[tr], res).predict(X[te])
        for n in names:
            per[n].append(dict(r2=r2(y, pred[n]), spearman=spearmanr(y, pred[n])[0]))
            for adc, ii in t.groupby("ADC ID").indices.items(): sq[n].setdefault(adc, []).append(((y[ii] - pred[n][ii]) ** 2).sum())
        print(f"[{regime}] seed {seed}", {n: round(per[n][-1]["r2"], 4) for n in names}, flush=True)
    sst = {adc: ((y[ii] - y.mean()) ** 2).sum() for adc, ii in t.groupby("ADC ID").indices.items()}; adcs = sorted(sst)
    def gap(n):
        sa = np.array([np.mean(sq[n][x]) for x in adcs]); sb = np.array([np.mean(sq["p0"][x]) for x in adcs]); ss = np.array([sst[x] for x in adcs])
        rng = np.random.default_rng(0); d = []
        for _ in range(3000):
            j = rng.integers(0, len(adcs), len(adcs)); d.append((sb[j].sum() - sa[j].sum()) / ss[j].sum())
        return dict(delta_r2=float((sb.sum() - sa.sum()) / ss.sum()), lo=float(np.percentile(d, 2.5)), hi=float(np.percentile(d, 97.5)))
    summ = {n: dict(r2=float(np.mean([x["r2"] for x in per[n]])), spearman=float(np.mean([x["spearman"] for x in per[n]]))) for n in names}
    for n in LEVELS: summ[n]["vs_p0"] = gap(n); summ[n]["median_alpha"] = float(np.median(alphas[n]))
    results[regime] = summ
    print(f"\n=== held out: {regime} ===")
    for n, s in summ.items():
        g = s.get("vs_p0"); ex = f"   structure correction adds {g['delta_r2']:+.4f} [{g['lo']:+.4f}, {g['hi']:+.4f}] R2  (ridge alpha ~{s['median_alpha']:.0f})" if g else ""
        print(f"{n:20s} R2 {s['r2']:+.4f} Spearman {s['spearman']:.3f}{ex}", flush=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True); json.dump(results, open(OUT, "w"), indent=1)
