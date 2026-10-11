"""External check of Task A against the hand-curated comorbidity registry (conf/comorbidity_registry.csv).

For each of the registry's 41 conditions, train on FinnGen with every prior disease that reads
like it REMOVED (SapBERT cosine >= TAU between the registry label and the FinnGen prior), then
ask whether the learned per-organ vulnerability ranks the curated organ axes above the rest.

What this is: independent labels the model never saw, and a leakage guard that is stricter than
a family split (it removes near-synonyms by meaning, not by code prefix).
What this is not: clinical validation. The registry's organ_axes name the organ the condition
*is a disease of* (cirrhosis -> hepatic), so success means "the model recovers same-organ
excess risk", not that it has learned cross-organ vulnerability.

TAU: 0.80 was declared primary first. It then turned out to ban 0-2 priors per condition (SapBERT cosines between
a registry label and a FinnGen name are low), i.e. a guard with no teeth. 0.65 and 0.50 were added for that reason --
chosen from the ban counts, not from any AUROC -- and all three are reported with their ban counts.
The per-axis standardised score was added after seeing that the unstandardised one puts "musculoskeletal" (72 rows)
in everyone's top three; both are reported.
"""
import json, os, sys, warnings
import numpy as np, pandas as pd, torch, torch.nn as nn
from scipy.stats import rankdata
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
from embed_terms import embed

C = "/data/hyeongchanahn/adctox/ml_cache/"; DEV = "cuda:0"
TAUS = [0.80, 0.65, 0.50]
DOM2AXIS = {"Cardiac": "cardiovascular", "Vascular": "cardiovascular", "Skin": "dermatologic", "Metabolic": "metabolic_endocrine",
            "Renal": "renal", "Hematologic": "haematologic", "Pulmonary": "pulmonary", "Ocular": "ocular", "Hepatic": "hepatic",
            "GI": "gastrointestinal", "Neurologic": "neurologic", "Ear": "otologic", "Musculoskeletal": "musculoskeletal",
            "Infection": "infectious_immune", "Immune": "infectious_immune"}      # Reproductive, constitutional: no counterpart, dropped
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]

m = pd.read_parquet(C + "finngen.parquet")
m = m[(m.qc_flag == "OK") & (m.hr > 0) & (m.hr <= 100)].reset_index(drop=True)
m["y"] = np.log(m.hr); m["dom"] = m.mapped_toxicity_domain.str.split(" / ").str[0]; m["axis"] = m.dom.map(DOM2AXIS)
z = np.load(C + "sapbert.npz", allow_pickle=True); idx = {k: i for i, k in enumerate(z["keys"])}; E = z["emb"]
pe = np.stack([E[idx[s.strip()]] for s in m.prior_longname.fillna(m.prior_name)]); oe = np.stack([E[idx[s.strip()]] for s in m.outcome_longname])
lag = pd.get_dummies(m.hr_lag); LAGS = list(lag.columns); lag = lag.values.astype(np.float32)
domcols = sorted(m.dom.unique()); dom = pd.get_dummies(m.dom)[domcols].values.astype(np.float32)
y = m.y.values.astype(np.float32)
reg = pd.read_csv("/home/hyeongchanahn/CONI/adctox/conf/comorbidity_registry.csv")
RE = embed(list(reg.label)); RE /= np.linalg.norm(RE, axis=1, keepdims=True)
prior_names = m.prior_name.values; uprior, first = np.unique(prior_names, return_index=True); UP = pe[first]          # one embedding per prior
outs = m.drop_duplicates("outcome_name"); OE = np.stack([E[idx[s.strip()]] for s in outs.outcome_longname]); OD = outs.dom.values; OA = outs.dom.map(DOM2AXIS).values

class Net(nn.Module):
    def __init__(s, d_ctx, h=256, p=0.25):
        super().__init__()
        s.fp = nn.Sequential(nn.Linear(768, h), nn.GELU(), nn.Dropout(p)); s.fo = nn.Sequential(nn.Linear(768, h), nn.GELU(), nn.Dropout(p))
        s.head = nn.Sequential(nn.Linear(3 * h + d_ctx, h), nn.GELU(), nn.Dropout(p), nn.Linear(h, 1))
    def forward(s, p, o, c): a, b = s.fp(p), s.fo(o); return s.head(torch.cat([a, b, a * b, c], 1)).squeeze(1)

def train(tr, va, seed):
    torch.manual_seed(seed); ctx = np.c_[lag, dom].astype(np.float32); mu, sd = y[tr].mean(), y[tr].std()
    T = lambda a, ix: torch.tensor(a[ix], device=DEV); net = Net(ctx.shape[1]).to(DEV); opt = torch.optim.AdamW(net.parameters(), 3e-3, weight_decay=1e-2)
    P, O, Cx, Y = T(pe, tr), T(oe, tr), T(ctx, tr), torch.tensor((y[tr] - mu) / sd, device=DEV); best, bad, st = 1e9, 0, None
    for ep in range(200):
        net.train(); perm = torch.randperm(len(tr), device=DEV)
        for i in range(0, len(tr), 8192):
            j = perm[i:i + 8192]; l = nn.functional.huber_loss(net(P[j], O[j], Cx[j]), Y[j]); opt.zero_grad(); l.backward(); opt.step()
        net.eval()
        with torch.no_grad(): v = nn.functional.mse_loss(net(T(pe, va), T(oe, va), T(ctx, va)), torch.tensor((y[va] - mu) / sd, device=DEV)).item()
        if v < best - 1e-4: best, bad, st = v, 0, {k: x.clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 15: break
    net.load_state_dict(st); net.eval(); return net, mu, sd


import time as _time
def _retry_oom(fn):
    """The GPUs are shared and other jobs fill them; wait and retry instead of losing hours of folds."""
    def w(*a, **k):
        for _ in range(120):
            try: return fn(*a, **k)
            except torch.OutOfMemoryError: torch.cuda.empty_cache(); _time.sleep(30)
        raise RuntimeError("GPU stayed full for an hour")
    return w
train = _retry_oom(train)

@torch.no_grad()
def predict_label(net, mu, sd, vec):
    """predicted logHR for one new comorbidity against every outcome, averaged over the lags."""
    outp = []
    for li, lg in enumerate(LAGS):
        c = np.zeros((len(OE), len(LAGS) + len(domcols)), np.float32); c[:, li] = 1
        for k, d in enumerate(domcols): c[OD == d, len(LAGS) + k] = 1
        p = net(torch.tensor(np.repeat(vec[None], len(OE), 0), device=DEV), torch.tensor(OE, device=DEV), torch.tensor(c, device=DEV))
        outp.append(p.cpu().numpy() * sd + mu)
    return np.mean(outp, 0)

def axis_vuln(per_outcome, base):
    """excess over what a typical training prior shows for the same outcome, averaged inside each axis"""
    ex = per_outcome - base
    return {a: (float(np.nanmean(ex[OA == a])) if ((OA == a) & ~np.isnan(ex)).any() else np.nan) for a in AXES}

def auroc(score, pos):
    s = np.array([score[a] for a in AXES]); ok = ~np.isnan(s); p = np.array([a in pos for a in AXES]) & ok; n = ~np.array([a in pos for a in AXES]) & ok
    if p.sum() == 0 or n.sum() == 0: return np.nan
    r = rankdata(s[ok]); okp = p[ok]; return (r[okp].sum() - okp.sum() * (okp.sum() + 1) / 2) / (okp.sum() * (~okp).sum())

out = {}
for TAU in TAUS:
    rows = []
    sim = RE @ (UP / np.linalg.norm(UP, axis=1, keepdims=True)).T
    for i, r in reg.iterrows():
        banned = set(uprior[sim[i] >= TAU]); keep = ~np.isin(prior_names, list(banned))
        trall = np.where(keep)[0]; rng = np.random.default_rng(i); up = np.unique(prior_names[trall]); vk = set(rng.choice(up, max(5, len(up) // 10), replace=False))
        isv = np.isin(prior_names[trall], list(vk)); va, tr = trall[isv], trall[~isv]
        # base rate per outcome from the same training set (logHR of a typical prior, lag-averaged)
        d = m.iloc[trall]; base = d.groupby("outcome_name").y.mean().reindex(outs.outcome_name).fillna(d.y.mean()).values
        preds = []
        for sd_ in range(3):
            net, mu, sd = train(tr, va, sd_); preds.append(predict_label(net, mu, sd, RE[i].astype(np.float32)))
        pm = np.mean(preds, 0); v_mlp = axis_vuln(pm, base)
        # spread of a typical training prior's excess in each axis: the yardstick for the standardised score
        ex_tr = d.assign(ex=d.y.values - d.outcome_name.map(d.groupby("outcome_name").y.mean()).values).assign(axis=lambda q: q.dom.map(DOM2AXIS))
        spread = ex_tr.groupby(["prior_name", "axis"]).ex.mean().groupby("axis").std().reindex(AXES)
        v_std = {a: (v_mlp[a] / spread[a] if spread[a] > 0 else np.nan) for a in AXES}
        # kNN baseline: the observed excess logHR of the 10 most similar *kept* priors, no learning at all
        kept_u = np.array([u for u in uprior if u not in banned]); ksim = RE[i] @ (UP[np.isin(uprior, kept_u)] / np.linalg.norm(UP[np.isin(uprior, kept_u)], axis=1, keepdims=True)).T
        nn_ = kept_u[np.argsort(-ksim)[:10]]; dd = m[m.prior_name.isin(nn_)].groupby("outcome_name").y.mean().reindex(outs.outcome_name)
        v_knn = axis_vuln(dd.values, base)
        v_raw = {a: (float(np.mean(pm[OA == a])) if (OA == a).any() else np.nan) for a in AXES}          # uncentred: what you get without removing the outcome base rate
        pos = set(r.organ_axes.split(";"))
        rows.append(dict(id=r.id, n_banned=len(banned), mlp=auroc(v_mlp, pos), mlp_std=auroc(v_std, pos), knn=auroc(v_knn, pos), raw=auroc(v_raw, pos),
                         top3=[a for a, _ in sorted(v_mlp.items(), key=lambda kv: -np.nan_to_num(kv[1], nan=-9))[:3]], curated=sorted(pos)))
        print(f"tau {TAU} {r.id:28s} banned {len(banned):3d}  AUROC mlp {rows[-1]['mlp']:.2f} std {rows[-1]['mlp_std']:.2f} knn {rows[-1]['knn']:.2f} raw {rows[-1]['raw']:.2f}  top3 {rows[-1]['top3']}  curated {sorted(pos)}", flush=True)
    df = pd.DataFrame(rows); rng = np.random.default_rng(0); print("banned per condition: median", df.n_banned.median(), "min", df.n_banned.min(), "max", df.n_banned.max(), flush=True)
    summ = {}
    for k in ["mlp", "mlp_std", "knn", "raw"]:
        v = df[k].dropna().values; bs = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(3000)]
        summ[k] = dict(mean_auroc=float(v.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n=len(v))
    dlt = (df.mlp - df.knn).dropna().values; bs = [dlt[rng.integers(0, len(dlt), len(dlt))].mean() for _ in range(3000)]
    summ["mlp_minus_knn"] = dict(delta=float(dlt.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))
    summ["top1_hits_curated"] = float(np.mean([r["top3"][0] in r["curated"] for r in rows])); summ["top3_hits_curated"] = float(np.mean([bool(set(r["top3"]) & set(r["curated"])) for r in rows]))
    out[f"tau_{TAU}"] = dict(summary=summ, per_condition=rows)
    print(f"\n=== TAU {TAU}: mean AUROC (0.5 = chance) ===", json.dumps(summ, indent=1), flush=True)
os.makedirs("/home/hyeongchanahn/CONI/adctox/ml/results", exist_ok=True)
json.dump(out, open("/home/hyeongchanahn/CONI/adctox/ml/results/validate_registry.json", "w"), indent=1, default=str)
