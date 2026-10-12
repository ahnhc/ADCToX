"""Should the Danish disease trajectories (DTB, Siggaard et al. 2020) become training data for the axis head?

    CUDA_VISIBLE_DEVICES=1 python -I ml/axis_dtb_augment.py [--weight W] [--seeds 300,301,302] [--tag v1] [--write]

DTB targets are built like FinnGen's (vulnerability_model.axis_targets): for each listed pair, log RR minus that outcome's mean
log RR over exposures; per exposure, the mean excess on each axis (outcome ICD-10 ranges as axis_reliability.py); divided by the
axis's spread over exposures. Exposure text is the English KCD name of the ICD-10 3-character code.
Comparison (5 folds, seeds 300-302, never used before): FinnGen priors split by code family (lab.splits 'cluster'), DTB exposures
split by ICD-10 block (letter + first digit, e.g. K7) so near-duplicate codes stay together. Model A trains on the fold's FinnGen
priors; model B on the same plus the fold's DTB exposures. Both are scored on the held-out FinnGen priors and held-out DTB
exposures with the within-disease Spearman across observed axes (>= 4 axes; lab.py's deployed score).
Rule, fixed before running: B is adopted iff its paired DTB difference has CI lower bound > 0 and its paired FinnGen difference
has CI upper bound >= 0 (family / block bootstrap, 2000 draws). If adopted, the shown axes are re-decided on B's out-of-fold
predictions: an axis is shown iff its pooled per-axis Spearman (both sources) has CI lower bound > 0 and neither source alone
has rho < 0 on >= 30 diseases. --write then retrains the deployed axis heads on all FinnGen + all DTB and stores them with the
new hidden axes.

Follow-up (after v1: DTB +0.199 [+0.165, +0.234], FinnGen -0.032 [-0.055, -0.010], not adopted): DTB rows down-weighted in the
masked MSE (--weight). The weight is chosen on seeds 300-302 (the largest DTB gain among weights whose FinnGen CI upper bound
is >= 0), then confirmed once on seeds 400-402 with the same rule; only a confirmed weight may be written.
"""
import argparse, csv, json, os, sys
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import lab, vulnerability_model as VM, axis_reliability as AR, axis_calibration as AC
from vulnerability_model import AXES


def dtb_targets():
    names = {r["상병기호"]: r["영문명"] for r in csv.DictReader(open(AR.RAW + "kcd/hira_sangbyeong_master_2025.9_utf8.csv", encoding="utf-8")) if len(r["상병기호"]) == 3 and r["영문명"]}
    rows = [(r["D1"], r["D2"], np.log(float(r["RR"]))) for r in csv.DictReader(open(AR.RAW + "dtb_siggaard2020/MOESM1_ESM.tsv"), delimiter="\t")
            if float(r["RR"]) > 0 and r["D1"] in names and AR.icd_axis(r["D2"])]
    base = {}
    for _, d2, y in rows: base.setdefault(d2, []).append(y)
    base = {k: np.mean(v) for k, v in base.items()}; per = {}
    for d1, d2, y in rows: per.setdefault(d1, {}).setdefault(AR.icd_axis(d2), {}).setdefault(d2, []).append(y - base[d2])
    codes = sorted(c for c, d in per.items() if len(d) >= 2)
    T = np.array([[np.mean([np.mean(v) for v in per[c][a].values()]) if a in per[c] else np.nan for a in AXES] for c in codes], np.float32)
    T = T / (np.nanstd(T, 0) + 1e-6)
    return codes, [names[c] for c in codes], T


@lab.retry_oom
def train_w(P, T, W, seed, epochs=500, patience=30):
    """vulnerability_model._train_axis with a weight per row (FinnGen 1, DTB --weight) in the masked MSE."""
    import torch.nn as nn
    rng = np.random.default_rng(seed); ok = np.where((~np.isnan(T)).sum(1) >= 2)[0]; va = rng.choice(ok, max(1, len(ok) // 10), replace=False); tr = np.setdiff1d(ok, va)
    Tc = T - np.nanmean(T, 1, keepdims=True); M = torch.tensor((~np.isnan(Tc)) * W[:, None], device=VM.DEV, dtype=torch.float32)
    Tt = torch.tensor(np.nan_to_num(Tc), device=VM.DEV, dtype=torch.float32); Pt = torch.tensor(P, device=VM.DEV); torch.manual_seed(seed)
    net = VM.axis_net(P.shape[1]).to(VM.DEV); opt = torch.optim.AdamW(net.parameters(), 1e-3, weight_decay=1e-2)
    loss = lambda ix: (((net(Pt[ix]) - Tt[ix]) ** 2) * M[ix]).sum() / M[ix].sum()
    trt, vat = torch.tensor(tr, device=VM.DEV), torch.tensor(va, device=VM.DEV); best, bad, st = 1e9, 0, None
    for ep in range(epochs):
        net.train(); perm = trt[torch.randperm(len(trt), device=VM.DEV)]
        for i in range(0, len(perm), 128):
            l = loss(perm[i:i + 128]); opt.zero_grad(); l.backward(); opt.step()
        net.eval()
        with torch.no_grad(): v = loss(vat).item()
        if v < best - 1e-5: best, bad, st = v, 0, {k: x.detach().cpu().clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience: break
    return st, best


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); ap.add_argument("--weight", type=float, default=1.0)
    ap.add_argument("--seeds", default="300,301,302"); ap.add_argument("--tag", default="v1"); a = ap.parse_args()
    m, P, O, rows, nl, nd, up, uo = VM._data(); ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); spread = ck["meta"]["spread"]
    fam = up.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0].values
    codes, texts, Td = dtb_targets(); Pd = VM._st(texts).astype(np.float32); block = np.array([c[:2] for c in codes]); print("DTB exposures", len(codes), flush=True)
    sA_f, sB_f, u_f, sA_d, sB_d, u_d = [], [], [], [], [], []; oof = {AXES[k]: dict(fin=([], [], []), dtb=([], [], [])) for k in range(len(AXES))}
    for seed in [int(x) for x in a.seeds.split(",")]:
        f, _ = lab.splits(m, "cluster", seed); prior_fold = lab.pd.Series(f).groupby(rows["pi"]).first().reindex(range(len(up))).values
        ub = np.unique(block); rng = np.random.default_rng(seed); rng.shuffle(ub); bf = {b: i % lab.FOLDS for i, b in enumerate(ub)}; dfold = np.array([bf[b] for b in block])
        for k in range(lab.FOLDS):
            tr_rows = m[f != k]; base = tr_rows.groupby("outcome_name").y.mean()
            T = VM.axis_targets(m, base.reindex(m.outcome_name.unique()).fillna(tr_rows.y.mean()), spread).reindex(up.prior_name).values.astype(np.float32)
            Ttr = T.copy(); Ttr[prior_fold == k] = np.nan; Tdtr = Td.copy(); Tdtr[dfold == k] = np.nan
            nets = {}
            W = np.r_[np.ones(len(P)), np.full(len(Pd), a.weight)].astype(np.float32)
            for name, (PP, TT, WW) in {"A": (P, Ttr, W[:len(P)]), "B": (np.r_[P, Pd], np.r_[Ttr, Tdtr], W)}.items():
                st, _ = train_w(PP, TT, WW, seed * 10 + k); net = VM.axis_net(P.shape[1]); net.load_state_dict(st); nets[name] = net.eval()
            tf, td = np.where(prior_fold == k)[0], np.where(dfold == k)[0]
            with torch.no_grad():
                Z = {n: (net(torch.tensor(P[tf])).numpy(), net(torch.tensor(Pd[td])).numpy()) for n, net in nets.items()}
            sA_f += list(AC.within(Z["A"][0], T[tf])); sB_f += list(AC.within(Z["B"][0], T[tf])); u_f += list(fam[tf])
            sA_d += list(AC.within(Z["A"][1], Td[td])); sB_d += list(AC.within(Z["B"][1], Td[td])); u_d += list(block[td])
            for src, ZZ, TT, uu in (("fin", Z["B"][0], T[tf], fam[tf]), ("dtb", Z["B"][1], Td[td], block[td])):
                for z, t, u in zip(ZZ, TT, uu):
                    ok = ~np.isnan(t)
                    if ok.sum() < 2: continue
                    zc, tc = z - z[ok].mean(), t - np.nanmean(t)
                    for j in np.where(ok)[0]: L = oof[AXES[j]][src]; L[0].append(zc[j]); L[1].append(tc[j]); L[2].append(u)
            print(f"seed {seed} fold {k}", flush=True)
    res = dict(finngen=AC.paired(np.array(sB_f), np.array(sA_f), u_f), dtb=AC.paired(np.array(sB_d), np.array(sA_d), u_d), n_dtb=len(codes), weight=a.weight, seeds=a.seeds)
    res["adopt"] = res["dtb"]["lo"] > 0 and res["finngen"]["hi"] >= 0
    per_axis, shown, hidden = {}, [], []
    for ax_, d in oof.items():
        x = d["fin"][0] + d["dtb"][0]; y = d["fin"][1] + d["dtb"][1]; u = [f"f:{v}" for v in d["fin"][2]] + [f"d:{v}" for v in d["dtb"][2]]
        r = dict(pooled=AR.boot_rho(x, y, u), finngen=AR.boot_rho(*d["fin"]) if len(d["fin"][0]) >= 10 else None, dtb=AR.boot_rho(*d["dtb"]) if len(d["dtb"][0]) >= 10 else None)
        ok = r["pooled"]["lo"] > 0 and not any(s is not None and s["n"] >= 30 and s["rho"] < 0 for s in (r["finngen"], r["dtb"]))
        per_axis[ax_] = r; (shown if ok else hidden).append(ax_)
        print(f"{ax_:20s} pooled {r['pooled']['rho']:+.3f} [{r['pooled']['lo']:+.3f}, {r['pooled']['hi']:+.3f}]",
              *(f"{s} {r[s]['rho']:+.3f} n={r[s]['n']}" for s in ("finngen", "dtb") if r[s]), "->", "show" if ok else "blank")
    res.update(per_axis_B=per_axis, shown_B=shown, hidden_B=hidden)
    json.dump(res, open(AR.RES + f"axis_dtb_augment_{a.tag}.json", "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("finngen", "dtb", "adopt", "hidden_B")}, indent=1))
    if a.write and res["adopt"]:
        T = VM.axis_targets(m, m.groupby("outcome_name").y.mean(), spread).reindex(up.prior_name).values.astype(np.float32)
        W = np.r_[np.ones(len(P)), np.full(len(Pd), a.weight)].astype(np.float32)
        heads = [train_w(np.r_[P, Pd], np.r_[T, Td], W, 1000 + s) for s in range(VM.SEEDS)]
        ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); ck["axis"] = [st for st, _ in heads]; ck["axis_hidden"] = hidden
        ck["meta"]["axis_training"] = f"FinnGen priors + DTB exposures ({len(codes)}, Siggaard 2020, weight {a.weight})"
        torch.save(ck, VM.PT); print("written to", VM.PT, "hidden", hidden)


if __name__ == "__main__":
    main()
