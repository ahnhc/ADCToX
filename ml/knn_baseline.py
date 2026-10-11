"""No-learning baseline for Task A, on exactly the same folds and metrics as task_a_comorbidity_risk.py.

For a held-out (prior, outcome, lag) row: average the observed logHR of the K most
SapBERT-similar *training* priors that have that (outcome, lag) observed. No fitted parameters.
If the MLP cannot beat this, "deep learning" is decoration and the embedding is doing the work.
Runs on CPU; reads the same splits (same seeds, same fold assignment) as the MLP script.
"""
import json, os, warnings
import numpy as np, pandas as pd
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")
C = "/data/hyeongchanahn/adctox/ml_cache/"; K = 10; SEEDS, FOLDS = 3, 5
OUT = "/home/hyeongchanahn/CONI/adctox/ml/results/knn_baseline.json"
m = pd.read_parquet(C + "finngen.parquet"); m = m[(m.qc_flag == "OK") & (m.hr > 0) & (m.hr <= 100)].reset_index(drop=True)
m["y"] = np.log(m.hr); m["dom"] = m.mapped_toxicity_domain.str.split(" / ").str[0]
m["fam"] = m.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0]; m["chap"] = m.prior_name.str.extract(r"^([A-Za-z]+)")[0]
z = np.load(C + "sapbert.npz", allow_pickle=True); ix = {k: i for i, k in enumerate(z["keys"])}
up = m.drop_duplicates("prior_name").reset_index(drop=True); pidx = {p: i for i, p in enumerate(up.prior_name)}
PE = np.stack([z["emb"][ix[s.strip()]] for s in up.prior_longname.fillna(up.prior_name)]); PE /= np.linalg.norm(PE, axis=1, keepdims=True)
SIM = PE @ PE.T
y = m.y.values; row_p = m.prior_name.map(pidx).values
groups = m.groupby(["outcome_name", "hr_lag"]).indices          # row indices per (outcome, lag)

def knn_predict(train_mask, te):
    pred = np.full(len(m), np.nan); mu = y[train_mask].mean()
    for g, rows in groups.items():
        tr_r = rows[train_mask[rows]]; te_r = np.intersect1d(rows, te)
        if len(te_r) == 0: continue
        if len(tr_r) == 0: pred[te_r] = mu; continue
        S = SIM[np.ix_(row_p[te_r], row_p[tr_r])]; k = min(K, len(tr_r)); nn_ = np.argpartition(-S, k - 1, axis=1)[:, :k]
        w = np.take_along_axis(S, nn_, 1).clip(1e-3); pred[te_r] = (w * y[tr_r][nn_]).sum(1) / w.sum(1)
    return pred

def lookup(tr, te, regime):
    d = m.iloc[tr]; mu = d.y.mean()
    if regime == "pair":
        pm = d.groupby("prior_name").y.mean(); om = d.groupby("outcome_name").y.mean()
        return (m.iloc[te].prior_name.map(pm).fillna(mu) + m.iloc[te].outcome_name.map(om).fillna(mu) - mu).values
    g = d.groupby(["outcome_name", "chap", "hr_lag"]).y.mean(); g2 = d.groupby(["outcome_name", "hr_lag"]).y.mean(); t = m.iloc[te]
    return np.array([g.get((a, b, c), g2.get((a, c), mu)) for a, b, c in zip(t.outcome_name, t.chap, t.hr_lag)])

def organ(pred):
    t = m[["prior_name", "dom", "y"]].assign(p=pred).groupby(["prior_name", "dom"]).mean().reset_index(); rho, hit = {}, {}
    for pn, a in t.groupby("prior_name"):
        if len(a) < 6 or a.y.nunique() < 2 or a.p.nunique() < 2: continue
        rho[pn] = spearmanr(a.y, a.p)[0]; k = min(3, len(a)); hit[pn] = len(set(a.nlargest(k, "y").dom) & set(a.nlargest(k, "p").dom)) / k
    return rho, hit

def splits(regime, seed):                # identical to task_a_comorbidity_risk.py
    rng = np.random.default_rng(seed)
    key = {"pair": m.prior_name + "|" + m.outcome_name, "prior": m.prior_name, "cluster": m.fam}[regime]
    u = key.unique(); rng.shuffle(u); fm = {k: i % FOLDS for i, k in enumerate(u)}; return key.map(fm).values

res = {}
for regime in ["pair", "prior", "cluster"]:
    per = {"lookup": [], "knn": []}
    for seed in range(SEEDS):
        f = splits(regime, seed); P = {k: np.zeros(len(m)) for k in per}
        for k in range(FOLDS):
            te = np.where(f == k)[0]; tr = np.where(f != k)[0]; mask = np.zeros(len(m), bool); mask[tr] = True
            P["lookup"][te] = lookup(tr, te, regime); P["knn"][te] = knn_predict(mask, te)[te]
        for n, v in P.items():
            rho, hit = organ(v); per[n].append(dict(r2=1 - ((y - v) ** 2).sum() / ((y - y.mean()) ** 2).sum(), spearman=spearmanr(y, v)[0], _rho=rho, _hit=hit,
                                                  organ_rho=float(np.mean(list(rho.values()))), organ_top3=float(np.mean(list(hit.values())))))
        print(f"[{regime}] seed {seed}", {n: round(per[n][-1]["r2"], 3) for n in per}, flush=True)
    fam_of = m.drop_duplicates("prior_name").set_index("prior_name").fam
    keys = sorted(set.intersection(*[set(x["_rho"]) for x in per["knn"]], *[set(x["_rho"]) for x in per["lookup"]]))
    a = np.array([np.mean([x["_rho"][p] for x in per["knn"]]) - np.mean([x["_rho"][p] for x in per["lookup"]]) for p in keys])
    fams = np.array([fam_of[p] for p in keys]); uf = np.unique(fams); by = {f_: a[fams == f_] for f_ in uf}; rng = np.random.default_rng(0)
    bs = [np.concatenate([by[f_] for f_ in rng.choice(uf, len(uf))]).mean() for _ in range(2000)]
    res[regime] = {n: {k: float(np.mean([x[k] for x in L])) for k in ["r2", "spearman", "organ_rho", "organ_top3"]} for n, L in per.items()}
    res[regime]["knn"]["organ_rho_vs_lookup"] = dict(delta=float(a.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))
    print(f"=== {regime} ===", json.dumps(res[regime]), flush=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True); json.dump(res, open(OUT, "w"), indent=1)
