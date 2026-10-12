"""Per-axis calibration of the axis head: remove each axis's offset and scale before the within-disease ranking.

    CUDA_VISIBLE_DEVICES=1 python -I ml/axis_calibration.py [--write]

Why: the axis head (model 0.1) puts Ear first for 27% of 2,000 ICD-10 disease names and Neuro first for 0.9%, because sparse,
selected axes carry a positive mean in its output. The per-axis check (axis_reliability.py) is rank-based within one axis and
cannot see this. Calibration: z'_a = (z_a - mu_a) / sd_a * mean(sd), mu and sd over the head's predictions for the FinnGen
training priors (no outcomes used). Within one axis the order is unchanged; across axes it changes which ones a disease shows.
Scores (both the share of diseases per top axis and the within-disease ranking quality) for raw vs calibrated:
  internal  family-held-out 5-fold CV, seeds 200-202 (as axis_reliability.py); per test prior, Spearman across its observed
            axes between prediction and the centred target (lab.py's deployed score); mu/sd from the fold's training priors
  external  DTB exposures (as axis_reliability.py), same per-exposure Spearman
Rule, fixed before running: adopt calibration unless the paired within-disease difference has its 95% CI wholly below 0 in
either set (bootstrap over families / exposures). --write stores mu and sd in the deployed checkpoint ('axis_mu', 'axis_sd').
"""
import argparse, json, os, sys
import numpy as np, torch
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import lab, vulnerability_model as VM, axis_reliability as AR
from vulnerability_model import AXES
RES = AR.RES


def calib(Z, mu, sd): return (Z - mu) / sd * sd.mean()


def within(Z, T):
    out = []
    for z, t in zip(Z, T):
        ok = ~np.isnan(t)
        out.append(spearmanr(z[ok], t[ok])[0] if ok.sum() >= 4 and np.unique(t[ok]).size > 1 and np.unique(z[ok]).size > 1 else np.nan)
    return np.array(out)


def paired(a, b, units, n=2000):
    k = ~(np.isnan(a) | np.isnan(b)); d = (a - b)[k]; u = np.asarray(units)[k]; uu = np.unique(u); by = {x: d[u == x] for x in uu}
    rng = np.random.default_rng(0); bs = [np.concatenate([by[x] for x in rng.choice(uu, len(uu))]).mean() for _ in range(n)]
    return dict(delta=float(d.mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n=int(k.sum()), raw=float(np.nanmean(b[k])), calibrated=float(np.nanmean(a[k])))


def top_share(Z): return {a: float(np.mean(Z.argmax(1) == k)) for k, a in enumerate(AXES)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); a = ap.parse_args()
    m, P, O, rows, nl, nd, up, uo = VM._data(); ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); spread = ck["meta"]["spread"]
    fam = up.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0].values; raw_s, cal_s, units = [], [], []
    for seed in (200, 201, 202):
        f, _ = lab.splits(m, "cluster", seed); prior_fold = lab.pd.Series(f).groupby(rows["pi"]).first().reindex(range(len(up))).values
        for k in range(lab.FOLDS):
            tr_rows = m[f != k]; base = tr_rows.groupby("outcome_name").y.mean()
            T = VM.axis_targets(m, base.reindex(m.outcome_name.unique()).fillna(tr_rows.y.mean()), spread).reindex(up.prior_name).values.astype(np.float32)
            Ttr = T.copy(); Ttr[prior_fold == k] = np.nan
            st, _ = VM._train_axis(P, Ttr, seed * 10 + k); net = VM.axis_net(P.shape[1]); net.load_state_dict(st); net.eval()
            with torch.no_grad(): Zall = net(torch.tensor(P)).numpy()
            trp = prior_fold != k; mu, sd = Zall[trp].mean(0), Zall[trp].std(0) + 1e-6; te = np.where(prior_fold == k)[0]
            raw_s += list(within(Zall[te], T[te])); cal_s += list(within(calib(Zall[te], mu, sd), T[te])); units += list(fam[te])
            print(f"seed {seed} fold {k}", flush=True)
    internal = paired(np.array(cal_s), np.array(raw_s), units)
    # deployed heads: mu / sd over all FinnGen priors, then DTB and the ICD name list
    VM._ensemble(); dev = VM.DEV
    with torch.no_grad():
        Zp = np.mean([h(torch.tensor(P, device=dev)).cpu().numpy() for h in VM._CK_AXIS], 0)
    mu, sd = Zp.mean(0), Zp.std(0) + 1e-6
    import csv
    names = {r["상병기호"]: r["영문명"] for r in csv.DictReader(open(AR.RAW + "kcd/hira_sangbyeong_master_2025.9_utf8.csv", encoding="utf-8")) if len(r["상병기호"]) == 3 and r["영문명"]}
    rr = {}
    for r in csv.DictReader(open(AR.RAW + "dtb_siggaard2020/MOESM1_ESM.tsv"), delimiter="\t"):
        ax = AR.icd_axis(r["D2"])
        if ax and r["D1"] in names and float(r["RR"]) > 0: rr.setdefault(r["D1"], {}).setdefault(ax, []).append(np.log(float(r["RR"])))
    codes = sorted(c for c, d in rr.items() if len(d) >= 2)
    def heads(texts):
        E = torch.tensor(VM._st(texts), device=dev)
        with torch.no_grad(): return np.mean([h(E).cpu().numpy() for h in VM._CK_AXIS], 0)
    Zd = heads([names[c] for c in codes]); Td = np.array([[np.mean(rr[c][x]) if x in rr[c] else np.nan for x in AXES] for c in codes])
    Td = Td - np.nanmean(Td, 1, keepdims=True)
    external = paired(within(calib(Zd, mu, sd), Td), within(Zd, Td), codes)
    Zn = heads(sorted(names.values()))
    res = dict(internal_within_disease=internal, dtb_within_exposure=external, top_share_raw=top_share(Zn), top_share_calibrated=top_share(calib(Zn, mu, sd)),
               mu=mu.tolist(), sd=sd.tolist())
    res["adopt"] = internal["hi"] >= 0 and external["hi"] >= 0
    json.dump(res, open(RES + "axis_calibration_v1.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("mu", "sd")}, indent=1))
    if a.write and res["adopt"]:
        ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); ck["axis_mu"] = mu.astype(np.float32).tolist(); ck["axis_sd"] = sd.astype(np.float32).tolist()
        torch.save(ck, VM.PT); print("written to", VM.PT)


if __name__ == "__main__":
    main()
