"""Which organ axes can the learned estimate show? Per-axis check of the axis head, internal (FinnGen, family-held-out) and
external (Danish disease trajectories, Siggaard et al. 2020).

    CUDA_VISIBLE_DEVICES=3 python -I ml/axis_reliability.py [--write]

Internal: 5-fold cross-validation with whole FinnGen code families held out (lab.splits 'cluster'), seeds 200-202 (not used
by any earlier run). For each axis, the out-of-fold prediction (centred per prior like the target) is compared with the
observed centred axis target over the test priors that observed that axis: Spearman rho, CI from 2000 family bootstraps.
External: every DTB exposure (ICD-10 3-character code, English name from the HIRA KCD master) gets the deployed axis head's
prediction from its name; its truth is the mean log relative risk of its listed outcomes on each axis (outcome code ranges
below), centred per exposure. Spearman per axis over exposures with >= 1 outcome on that axis, CI from 2000 exposure
bootstraps. DTB lists only significant pairs, like the FinnGen selection.
Rule, fixed before running: an axis is shown (and may be applied automatically) iff its internal CI lower bound is > 0 AND
its DTB rho is not < 0 where DTB has >= 30 exposures on it. Other axes are left blank: no estimate shown, none applied.
--write stores the hidden axes in the deployed checkpoint (vuln_biolord.pt: 'axis_hidden').
"""
import argparse, csv, json, os, sys
import numpy as np, torch
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import lab, vulnerability_model as VM
from vulnerability_model import AXES
RAW = P.REPO + "data/raw/"; RES = P.REPO + "ml/results/benchmarks/"
ICD_AXIS = [("A00", "B99", "infectious_immune"), ("D50", "D79", "haematologic"), ("D80", "D89", "infectious_immune"),
            ("E00", "E90", "metabolic_endocrine"), ("G00", "G99", "neurologic"), ("H00", "H59", "ocular"), ("H60", "H95", "otologic"),
            ("I00", "I99", "cardiovascular"), ("J00", "J99", "pulmonary"), ("K00", "K69", "gastrointestinal"), ("K70", "K77", "hepatic"),
            ("K80", "K95", "gastrointestinal"), ("L00", "L99", "dermatologic"), ("M00", "M99", "musculoskeletal"), ("N00", "N29", "renal")]


def icd_axis(code):
    for lo, hi, a in ICD_AXIS:
        if lo <= code[:3] <= hi: return a
    return None


def boot_rho(x, y, units, n=2000):
    x, y, units = np.asarray(x), np.asarray(y), np.asarray(units); uu = np.unique(units); by = {u: np.where(units == u)[0] for u in uu}
    rng = np.random.default_rng(0); bs = []
    for _ in range(n):
        ix = np.concatenate([by[u] for u in rng.choice(uu, len(uu))])
        if np.unique(x[ix]).size > 1 and np.unique(y[ix]).size > 1: bs.append(spearmanr(x[ix], y[ix])[0])
    return dict(rho=float(spearmanr(x, y)[0]), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)), n=len(x), units=len(uu))


def internal():
    m, P, O, rows, nl, nd, up, uo = VM._data(); ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); spread = ck["meta"]["spread"]
    fam = up.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0].values; pred, truth, unit, ax = [], [], [], []
    for seed in (200, 201, 202):
        f, _ = lab.splits(m, "cluster", seed); prior_fold = lab.pd.Series(f).groupby(rows["pi"]).first().reindex(range(len(up))).values
        for k in range(lab.FOLDS):
            tr_rows = m[f != k]; base = tr_rows.groupby("outcome_name").y.mean()
            T = VM.axis_targets(m, base.reindex(m.outcome_name.unique()).fillna(tr_rows.y.mean()), spread).reindex(up.prior_name).values.astype(np.float32)
            Ttr = T.copy(); Ttr[prior_fold == k] = np.nan
            st, _ = VM._train_axis(P, Ttr, seed * 10 + k); net = VM.axis_net(P.shape[1]); net.load_state_dict(st); net.eval()
            te = np.where(prior_fold == k)[0]
            with torch.no_grad(): Z = net(torch.tensor(P[te])).numpy()
            for i, p in enumerate(te):
                t = T[p]; ok = ~np.isnan(t)
                if ok.sum() < 2: continue
                tc = t - np.nanmean(t); zc = Z[i] - Z[i][ok].mean()
                for a in np.where(ok)[0]: pred.append(zc[a]); truth.append(tc[a]); unit.append(fam[p]); ax.append(a)
            print(f"seed {seed} fold {k}", flush=True)
    pred, truth, unit, ax = map(np.array, (pred, truth, unit, ax))
    return {AXES[a]: boot_rho(pred[ax == a], truth[ax == a], unit[ax == a]) for a in range(len(AXES)) if (ax == a).sum() >= 10}


def external():
    names = {}
    for r in csv.DictReader(open(RAW + "kcd/hira_sangbyeong_master_2025.9_utf8.csv", encoding="utf-8")):
        if len(r["상병기호"]) == 3 and r["영문명"]: names[r["상병기호"]] = r["영문명"]
    rr = {}
    for r in csv.DictReader(open(RAW + "dtb_siggaard2020/MOESM1_ESM.tsv"), delimiter="\t"):
        a = icd_axis(r["D2"])
        if a and r["D1"] in names and float(r["RR"]) > 0: rr.setdefault(r["D1"], {}).setdefault(a, []).append(np.log(float(r["RR"])))
    codes = sorted(c for c, d in rr.items() if len(d) >= 2)
    VM._ensemble(); E = torch.tensor(VM._st([names[c] for c in codes]), device=VM.DEV)
    with torch.no_grad(): Z = np.mean([h(E).cpu().numpy() for h in VM._CK_AXIS], 0)
    out = {}; per = {a: ([], [], []) for a in AXES}
    for i, c in enumerate(codes):
        t = np.array([np.mean(rr[c][a]) if a in rr[c] else np.nan for a in AXES]); ok = ~np.isnan(t); tc = t - np.nanmean(t); zc = Z[i] - Z[i][ok].mean()
        for k in np.where(ok)[0]: per[AXES[k]][0].append(zc[k]); per[AXES[k]][1].append(tc[k]); per[AXES[k]][2].append(c)
    for a, (x, y, u) in per.items():
        if len(x) >= 10: out[a] = boot_rho(x, y, u)
    return out, len(codes)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); a = ap.parse_args()
    ext, n_codes = external(); print("DTB exposures", n_codes, flush=True)
    for k, v in ext.items(): print(f"  DTB {k:20s} rho {v['rho']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}] n={v['n']}")
    inn = internal()
    shown, hidden = [], []
    for ax in AXES:
        i, e = inn.get(ax), ext.get(ax)
        ok = i is not None and i["lo"] > 0 and not (e is not None and e["n"] >= 30 and e["rho"] < 0)
        (shown if ok else hidden).append(ax)
        print(f"{ax:20s} internal {i['rho']:+.3f} [{i['lo']:+.3f}, {i['hi']:+.3f}] n={i['n']:5d}" if i else f"{ax:20s} internal -", "|",
              f"DTB {e['rho']:+.3f} [{e['lo']:+.3f}, {e['hi']:+.3f}] n={e['n']}" if e else "DTB -", "->", "show" if ok else "blank")
    res = dict(internal=inn, external_dtb=ext, dtb_exposures=n_codes, shown=shown, hidden=hidden)
    json.dump(res, open(RES + "axis_reliability_v1.json", "w"), indent=1); print("hidden:", hidden)
    if a.write:
        ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); ck["axis_hidden"] = hidden; torch.save(ck, VM.PT); print("written to", VM.PT)


if __name__ == "__main__":
    main()
