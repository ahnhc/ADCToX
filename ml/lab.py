"""Experiment harness for Task A. One config in, one comparable result out.

Same data filter, same folds and same metrics as task_a_comorbidity_risk.py, so every config is
comparable with every earlier number. Each run also scores a training-free kNN over the *same*
embedding, so "the embedding got better" and "the learned head got better" stay separable.

Pre-declared protocol (written before the bake-off ran):
  * selection runs use fold seeds 0,1,2; the config that is carried forward is then re-run on
    fold seeds 100,101,102 and only that confirmation number is quoted as the result;
  * the decision metric is the strictest regime (unseen ICD family): organ-ranking gain over the
    lookup table, with R2 as the tie-break; a change is "better" only if the paired,
    family-bootstrapped difference to the incumbent excludes zero.

Per-prior results go to the cache (FinnGen disease codes), only summaries to ml/results/lab/.
"""
import argparse, json, os, pickle, time, warnings
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P
import numpy as np, pandas as pd, torch, torch.nn as nn
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")

C = P.CACHE; RES = P.REPO + "ml/results/lab/"; FOLDS = 5
DEV = "cuda:0"
TAU_SE = 0.25      # precision weights: w = 1 / (se^2 + TAU_SE^2), so a few tiny-se rows cannot dominate; then clipped at W_MAX x mean
W_MAX = 5.0

def retry_oom(fn):
    def w(*a, **k):
        for _ in range(120):
            try: return fn(*a, **k)
            except (torch.OutOfMemoryError, RuntimeError) as e:       # shared GPUs: also cuBLAS/cuDNN allocation failures, not only OOM
                if not isinstance(e, torch.OutOfMemoryError) and not any(k in str(e) for k in ("CUBLAS", "CUDNN", "out of memory", "CUDA error")): raise
                print(f"   [retry] {type(e).__name__}: {str(e)[:160]}", flush=True); torch.cuda.empty_cache(); time.sleep(30)
        raise RuntimeError("GPU stayed full")
    return w

# ------------------------------------------------------------------ data
def load_rows():
    m = pd.read_parquet(C + "finngen.parquet"); m = m[(m.qc_flag == "OK") & (m.hr > 0) & (m.hr <= 100)].reset_index(drop=True)
    m["y"] = np.log(m.hr); m["dom"] = m.mapped_toxicity_domain.str.split(" / ").str[0]
    m["fam"] = m.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0]; m["chap"] = m.prior_name.str.extract(r"^([A-Za-z]+)")[0]
    se = (np.log(m.ci_max.clip(lower=1e-9)) - np.log(m.ci_min.clip(lower=1e-9))) / (2 * 1.96)
    se = se.where(np.isfinite(se) & (se > 0), np.nan); m["se"] = se.fillna(se.median())
    w = 1.0 / (m.se ** 2 + TAU_SE ** 2); w = (w / w.mean()).clip(upper=W_MAX); m["w"] = w / w.mean()
    return m

def table(m, emb_name, extra=None):
    z = np.load(C + ("sapbert.npz" if emb_name == "sapbert" else f"emb_{emb_name}.npz"), allow_pickle=True)
    ix = {k: i for i, k in enumerate(z["keys"])}; E = z["emb"].astype(np.float32)
    up = m.drop_duplicates("prior_name").reset_index(drop=True); uo = m.drop_duplicates("outcome_name").reset_index(drop=True)
    P = np.stack([E[ix[s.strip()]] for s in up.prior_longname.fillna(up.prior_name)]); O = np.stack([E[ix[s.strip()]] for s in uo.outcome_longname])
    if extra is not None:
        X = np.load(C + extra, allow_pickle=True); xm = dict(zip(X["priors"], X["feat"])); P = np.c_[P, np.stack([xm[p] for p in up.prior_name]).astype(np.float32)]
    pidx = {p: i for i, p in enumerate(up.prior_name)}; oidx = {o: i for i, o in enumerate(uo.outcome_name)}
    lags = sorted(m.hr_lag.unique()); doms = sorted(m.dom.unique())
    rows = dict(pi=m.prior_name.map(pidx).values, oi=m.outcome_name.map(oidx).values, li=m.hr_lag.map({l: i for i, l in enumerate(lags)}).values,
                di=m.dom.map({d: i for i, d in enumerate(doms)}).values)
    return P, O, rows, len(lags), len(doms), up

# ------------------------------------------------------------------ models
class TwoTower(nn.Module):
    def __init__(s, dP, dO, d_ctx, h=256, p=0.25):
        super().__init__()
        s.fp = nn.Sequential(nn.Linear(dP, h), nn.GELU(), nn.Dropout(p)); s.fo = nn.Sequential(nn.Linear(dO, h), nn.GELU(), nn.Dropout(p))
        s.head = nn.Sequential(nn.Linear(3 * h + d_ctx, h), nn.GELU(), nn.Dropout(p), nn.Linear(h, 1))
    def forward(s, p, o, oi, li, ctx):
        a, b = s.fp(p), s.fo(o); return s.head(torch.cat([a, b, a * b, ctx], 1)).squeeze(1)

class Bilinear(nn.Module):
    """y = b(prior) + c(outcome, lag) + s_lag * <u(prior text), w_outcome>.
    The 193 outcomes are all seen in training, so they get free vectors (plus a text prior); only the prior is cold-start."""
    def __init__(s, dP, dO, n_out, n_lag, R=32, h=256, p=0.25):
        super().__init__()
        s.n_lag = n_lag; s.fu = nn.Sequential(nn.Linear(dP, h), nn.GELU(), nn.Dropout(p), nn.Linear(h, R))
        s.fb = nn.Sequential(nn.Linear(dP, 64), nn.GELU(), nn.Linear(64, 1)); s.wf = nn.Embedding(n_out, R); nn.init.normal_(s.wf.weight, std=0.1)
        s.wt = nn.Linear(dO, R, bias=False); s.bo = nn.Embedding(n_out * n_lag, 1); nn.init.zeros_(s.bo.weight); s.ls = nn.Parameter(torch.ones(n_lag))
    def forward(s, p, o, oi, li, ctx):
        u = s.fu(p); w = s.wf(oi) + s.wt(o)
        return (u * w).sum(1) * s.ls[li] + s.fb(p).squeeze(1) + s.bo(oi * s.n_lag + li).squeeze(1)

@retry_oom
def fit_predict(arch, P, O, rows, nl, nd, y, w, tr, va, te, seed, weighted, reps):
    mu, sd = y[tr].mean(), y[tr].std(); outs = []
    Pt, Ot = torch.tensor(P, device=DEV), torch.tensor(O, device=DEV)
    ri = {k: torch.tensor(v, device=DEV) for k, v in rows.items()}; ctxm = torch.eye(nl + nd, device=DEV)
    ctx_of = lambda ix: torch.cat([ctxm[ri["li"][ix]], ctxm[nl + ri["di"][ix]]], 1)[:, :nl + nd]
    yt = torch.tensor((y - mu) / sd, device=DEV, dtype=torch.float32); wt = torch.tensor(w, device=DEV, dtype=torch.float32)
    def fwd(net, ix): return net(Pt[ri["pi"][ix]], Ot[ri["oi"][ix]], ri["oi"][ix], ri["li"][ix], ctx_of(ix))
    for r in range(reps):
        torch.manual_seed(seed * 101 + r)
        net = (TwoTower(P.shape[1], O.shape[1], nl + nd) if arch == "twotower" else Bilinear(P.shape[1], O.shape[1], O.shape[0], nl)).to(DEV)
        opt = torch.optim.AdamW(net.parameters(), 3e-3, weight_decay=1e-2); trt, vat, tet = [torch.tensor(a, device=DEV) for a in (tr, va, te)]
        best, bad, st = 1e9, 0, None
        for ep in range(200):
            net.train(); perm = trt[torch.randperm(len(trt), device=DEV)]
            for i in range(0, len(perm), 8192):
                j = perm[i:i + 8192]; l = nn.functional.huber_loss(fwd(net, j), yt[j], reduction="none")
                l = (l * wt[j]).mean() if weighted else l.mean(); opt.zero_grad(); l.backward(); opt.step()
            net.eval()
            with torch.no_grad(): v = nn.functional.mse_loss(fwd(net, vat), yt[vat]).item()      # validation is unweighted on purpose
            if v < best - 1e-4: best, bad, st = v, 0, {k: x.clone() for k, x in net.state_dict().items()}
            else:
                bad += 1
                if bad >= 15: break
        net.load_state_dict(st); net.eval()
        with torch.no_grad(): outs.append(fwd(net, tet).cpu().numpy() * sd + mu)
    return np.mean(outs, 0)

# ------------------------------------------------------------------ baselines + metrics
def lookup(m, tr, te):
    d = m.iloc[tr]; mu = d.y.mean(); g = d.groupby(["outcome_name", "chap", "hr_lag"]).y.mean(); g2 = d.groupby(["outcome_name", "hr_lag"]).y.mean(); t = m.iloc[te]
    return np.array([g.get((a, b, c), g2.get((a, c), mu)) for a, b, c in zip(t.outcome_name, t.chap, t.hr_lag)])

def knn_all(m, rows, SIM, y, mask, K=10):
    pred = np.full(len(m), np.nan); mu = y[mask].mean()
    for g, ix in m.groupby(["outcome_name", "hr_lag"]).indices.items():
        tr_r = ix[mask[ix]]; te_r = ix[~mask[ix]]
        if len(te_r) == 0: continue
        if len(tr_r) == 0: pred[te_r] = mu; continue
        S = SIM[np.ix_(rows["pi"][te_r], rows["pi"][tr_r])]; k = min(K, len(tr_r)); nn_ = np.argpartition(-S, k - 1, axis=1)[:, :k]
        ww = np.take_along_axis(S, nn_, 1).clip(1e-3); pred[te_r] = (ww * y[tr_r][nn_]).sum(1) / ww.sum(1)
    return pred

def organ(m, pred):
    t = m[["prior_name", "dom", "y"]].assign(p=pred).groupby(["prior_name", "dom"]).mean().reset_index(); rho = {}
    for pn, a in t.groupby("prior_name"):
        if len(a) < 6 or a.y.nunique() < 2 or a.p.nunique() < 2: continue
        rho[pn] = spearmanr(a.y, a.p)[0]
    return rho

def splits(m, regime, seed):
    rng = np.random.default_rng(seed); key = {"pair": m.prior_name + "|" + m.outcome_name, "prior": m.prior_name, "cluster": m.fam}[regime]
    u = key.unique(); rng.shuffle(u); fm = {k: i % FOLDS for i, k in enumerate(u)}; return key.map(fm).values, key

def fam_boot(m, a_by_prior, b_by_prior, n=2000):
    keys = sorted(set(a_by_prior) & set(b_by_prior)); d = np.array([a_by_prior[k] - b_by_prior[k] for k in keys])
    fam = m.drop_duplicates("prior_name").set_index("prior_name").fam; fs = np.array([fam[k] for k in keys]); uf = np.unique(fs)
    by = {f: d[fs == f] for f in uf}; rng = np.random.default_rng(0); bs = [np.concatenate([by[f] for f in rng.choice(uf, len(uf))]).mean() for _ in range(n)]
    return dict(delta=float(d.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n=len(keys))

# ------------------------------------------------------------------ run
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True); ap.add_argument("--emb", default="sapbert"); ap.add_argument("--arch", default="twotower", choices=["twotower", "bilinear"])
    ap.add_argument("--weighted", type=int, default=0); ap.add_argument("--extra", default=None)
    ap.add_argument("--regimes", default="prior,cluster"); ap.add_argument("--seeds", default="0,1,2"); ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args(); seeds = [int(s) for s in a.seeds.split(",")]
    m = load_rows(); P, O, rows, nl, nd, up = table(m, a.emb, a.extra); y = m.y.values.astype(np.float32); w = m.w.values.astype(np.float32)
    Pn = P[:, :O.shape[1]] if a.extra else P; Pn = Pn / np.linalg.norm(Pn, axis=1, keepdims=True); SIM = Pn @ Pn.T
    out = dict(config=vars(a), regimes={}); per_prior = {}
    for regime in a.regimes.split(","):
        acc = {k: [] for k in ["lookup", "knn", "model"]}; rho_acc = {k: {} for k in acc}
        for seed in seeds:
            f, key = splits(m, regime, seed); pred = {k: np.zeros(len(m)) for k in acc}
            for k in range(FOLDS):
                te = np.where(f == k)[0]; trall = np.where(f != k)[0]; mask = np.zeros(len(m), bool); mask[trall] = True
                kk = key.iloc[trall].unique(); r = np.random.default_rng(100 + seed * 10 + k); vk = set(r.choice(kk, max(1, len(kk) // 10), replace=False))
                isv = key.iloc[trall].isin(vk).values; va, tr = trall[isv], trall[~isv]
                pred["lookup"][te] = lookup(m, trall, te); pred["knn"][te] = knn_all(m, rows, SIM, y, mask)[te]
                pred["model"][te] = fit_predict(a.arch, P, O, rows, nl, nd, y, w, tr, va, te, seed, bool(a.weighted), a.reps)
            for n_, v in pred.items():
                rho = organ(m, v); [rho_acc[n_].setdefault(p, []).append(x) for p, x in rho.items()]
                acc[n_].append(dict(r2=1 - ((y - v) ** 2).sum() / ((y - y.mean()) ** 2).sum(), spearman=spearmanr(y, v)[0], organ=float(np.mean(list(rho.values())))))
            print(f"[{a.name}|{regime}] seed {seed}", {n_: round(acc[n_][-1]["r2"], 3) for n_ in acc}, flush=True)
        mean_rho = {n_: {p: float(np.mean(v)) for p, v in rho_acc[n_].items()} for n_ in acc}; per_prior[regime] = mean_rho
        out["regimes"][regime] = {n_: {k: float(np.mean([x[k] for x in L])) for k in ["r2", "spearman", "organ"]} for n_, L in acc.items()}
        out["regimes"][regime]["model_gain_over_lookup"] = fam_boot(m, mean_rho["model"], mean_rho["lookup"])
        out["regimes"][regime]["knn_gain_over_lookup"] = fam_boot(m, mean_rho["knn"], mean_rho["lookup"])
        out["regimes"][regime]["model_minus_knn"] = fam_boot(m, mean_rho["model"], mean_rho["knn"])
        g = out["regimes"][regime]; print(f"== {a.name} | {regime}: model R2 {g['model']['r2']:+.3f} (knn {g['knn']['r2']:+.3f}, lookup {g['lookup']['r2']:+.3f}) | "
              f"gain over lookup {g['model_gain_over_lookup']['delta']:+.3f} [{g['model_gain_over_lookup']['lo']:+.3f},{g['model_gain_over_lookup']['hi']:+.3f}] | "
              f"model-knn {g['model_minus_knn']['delta']:+.3f} [{g['model_minus_knn']['lo']:+.3f},{g['model_minus_knn']['hi']:+.3f}]", flush=True)
    os.makedirs(RES, exist_ok=True); json.dump(out, open(RES + f"{a.name}.json", "w"), indent=1)
    pickle.dump(per_prior, open(C + f"lab_{a.name}.pkl", "wb"))

if __name__ == "__main__":
    main()
