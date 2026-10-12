"""Which disease-pair source should train the axis head: FinnGen, the Danish DTB, or both? Judged on a third, independent cohort.

    CUDA_VISIBLE_DEVICES=1 python -I ml/axis_source_compare.py [--write]

Sources (targets built the same way: excess log RR or log HR over the outcome's mean across exposures, averaged per axis,
divided by the axis's spread, centred per disease by the trainer):
  F  FinnGen endpoint summaries (collaborator workbooks; mostly significant pairs), 1,616 priors
  D  Danish disease trajectories (Siggaard et al. 2020, ICD-10, significant directional pairs), English KCD names
  H  HuDiNe (Hidalgo et al. 2009, US Medicare, ICD-9 3-digit, ALL co-occurring pairs with >= 10 patients, undirected), names
     from the CMS ICD-9-CM v32 descriptions. H is never used for training: it is the referee.
Candidates: F only, D only, F + D (D weight 1), F + D (D weight 0.5); each an ensemble of 3 axis heads.
Scores: within-disease Spearman across the disease's observed axes (>= 4), the deployed ranking score.
  referee   all models trained on all of their data, scored on H
  in-domain 5-fold CV (seed 500): F held out by code family, D by ICD-10 block; each model scored on both held-out sets
Rule, fixed before running: the model with the highest referee score is deployed if its paired referee difference against
the current FinnGen-only model has CI lower bound > 0 (bootstrap over ICD-9 blocks, first two digits); otherwise FinnGen
stays. Axes of the deployed model are shown iff their per-axis Spearman on H has CI lower bound > 0.
"""
import argparse, collections, json, os, sys
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import lab, vulnerability_model as VM, axis_reliability as AR, axis_calibration as AC, axis_dtb_augment as DA
from vulnerability_model import AXES
ICD9_AXIS = [(1, 139, "infectious_immune"), (240, 278, "metabolic_endocrine"), (279, 279, "infectious_immune"), (280, 289, "haematologic"),
             (320, 359, "neurologic"), (360, 379, "ocular"), (380, 389, "otologic"), (390, 459, "cardiovascular"), (460, 519, "pulmonary"),
             (520, 569, "gastrointestinal"), (570, 573, "hepatic"), (574, 579, "gastrointestinal"), (580, 593, "renal"),
             (680, 709, "dermatologic"), (710, 739, "musculoskeletal")]


def icd9_axis(code):
    if not code.isdigit(): return None
    n = int(code)
    for lo, hi, a in ICD9_AXIS:
        if lo <= n <= hi: return a
    return None


def hudine_targets():
    cat = collections.defaultdict(list)
    for line in open(AR.RAW + "icd9cm/x/CMS32_DESC_LONG_DX.txt", encoding="latin1"):
        c, n = line.rstrip("\r\n").split(" ", 1)
        if c[0].isdigit(): cat[c[:3]].append((c, n.strip()))
    names = {k: sorted(v, key=lambda x: (len(x[0]), not x[0].endswith("9"), x[0]))[0][1] for k, v in cat.items()}
    pairs = []
    for line in open(AR.RAW + "hudine/AllNet3.net"):
        p = line.split()
        if len(p) < 6 or int(p[4]) < 10 or float(p[5]) <= 0: continue
        for a, b in ((p[0], p[1]), (p[1], p[0])):
            if a in names and icd9_axis(b): pairs.append((a, b, np.log(float(p[5]))))
    base = collections.defaultdict(list)
    for _, b, y in pairs: base[b].append(y)
    base = {k: np.mean(v) for k, v in base.items()}; per = {}
    for a, b, y in pairs: per.setdefault(a, {}).setdefault(icd9_axis(b), []).append(y - base[b])
    codes = sorted(c for c, d in per.items() if len(d) >= 4)
    T = np.array([[np.mean(per[c][x]) if x in per[c] else np.nan for x in AXES] for c in codes], np.float32)
    return codes, [names[c] for c in codes], T / (np.nanstd(T, 0) + 1e-6)


def fit(P_list, T_list, W_list, seeds):
    P, T, W = np.concatenate(P_list), np.concatenate(T_list), np.concatenate(W_list).astype(np.float32); nets = []
    for s in seeds:
        st, _ = DA.train_w(P, T, W, s); net = VM.axis_net(P.shape[1]); net.load_state_dict(st); nets.append(net.eval())
    def predict(X):
        with torch.no_grad(): return np.mean([n(torch.tensor(X)).numpy() for n in nets], 0)
    predict.states = [n.state_dict() for n in nets]
    return predict


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); a = ap.parse_args()
    m, P, O, rows, nl, nd, up, uo = VM._data(); ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); spread = ck["meta"]["spread"]
    fam = up.prior_name.str.extract(r"^([A-Za-z]+\d*)")[0].values
    T = VM.axis_targets(m, m.groupby("outcome_name").y.mean(), spread).reindex(up.prior_name).values.astype(np.float32)
    dc, dt, Td = DA.dtb_targets(); Pd = VM._st(dt).astype(np.float32); block = np.array([c[:2] for c in dc])
    hc, ht, Th = hudine_targets(); Ph = VM._st(ht).astype(np.float32); hblock = np.array([c[:2] for c in hc])
    print("FinnGen", len(P), "DTB", len(Pd), "HuDiNe", len(Ph), flush=True)
    one = lambda n: np.ones(n, np.float32)
    specs = {"F": lambda Pf, Tf, Pdd, Tdd: ([Pf], [Tf], [one(len(Pf))]),
             "D": lambda Pf, Tf, Pdd, Tdd: ([Pdd], [Tdd], [one(len(Pdd))]),
             "FD1": lambda Pf, Tf, Pdd, Tdd: ([Pf, Pdd], [Tf, Tdd], [one(len(Pf)), one(len(Pdd))]),
             "FD05": lambda Pf, Tf, Pdd, Tdd: ([Pf, Pdd], [Tf, Tdd], [one(len(Pf)), 0.5 * one(len(Pdd))])}
    # ---- referee: trained on everything, scored on HuDiNe
    full, ref = {}, {}
    for k, sp in specs.items():
        full[k] = fit(*sp(P, T, Pd, Td), seeds=(1000, 1001, 1002)); ref[k] = AC.within(full[k](Ph), Th); print(k, "referee %.3f" % np.nanmean(ref[k]), flush=True)
    # ---- in-domain CV
    f, _ = lab.splits(m, "cluster", 500); prior_fold = lab.pd.Series(f).groupby(rows["pi"]).first().reindex(range(len(up))).values
    ub = np.unique(block); rng = np.random.default_rng(500); rng.shuffle(ub); bf = {b: i % lab.FOLDS for i, b in enumerate(ub)}; dfold = np.array([bf[b] for b in block])
    cv = {k: dict(fin=np.full(len(P), np.nan), dtb=np.full(len(Pd), np.nan)) for k in specs}
    for fo in range(lab.FOLDS):
        tr_rows = m[f != fo]; base = tr_rows.groupby("outcome_name").y.mean()
        Tf = VM.axis_targets(m, base.reindex(m.outcome_name.unique()).fillna(tr_rows.y.mean()), spread).reindex(up.prior_name).values.astype(np.float32)
        Tft = Tf.copy(); Tft[prior_fold == fo] = np.nan; Tdt = Td.copy(); Tdt[dfold == fo] = np.nan
        tf, td = np.where(prior_fold == fo)[0], np.where(dfold == fo)[0]
        for k, sp in specs.items():
            pr = fit(*sp(P, Tft, Pd, Tdt), seeds=(500 * 10 + fo,))
            cv[k]["fin"][tf] = AC.within(pr(P[tf]), Tf[tf]); cv[k]["dtb"][td] = AC.within(pr(Pd[td]), Td[td])
        print("fold", fo, flush=True)
    res = {"n": dict(finngen=len(P), dtb=len(Pd), hudine=len(Ph)), "models": {}, "paired_vs_F": {}}
    for k in specs:
        res["models"][k] = dict(referee_hudine=float(np.nanmean(ref[k])), cv_finngen=float(np.nanmean(cv[k]["fin"])), cv_dtb=float(np.nanmean(cv[k]["dtb"])))
        if k != "F":
            res["paired_vs_F"][k] = dict(referee_hudine=AC.paired(ref[k], ref["F"], hblock), cv_finngen=AC.paired(cv[k]["fin"], cv["F"]["fin"], fam),
                                         cv_dtb=AC.paired(cv[k]["dtb"], cv["F"]["dtb"], block))
    best = max(specs, key=lambda k: res["models"][k]["referee_hudine"])
    chosen = best if best != "F" and res["paired_vs_F"][best]["referee_hudine"]["lo"] > 0 else "F"
    Zh = full[chosen](Ph); per = {}
    for j, ax in enumerate(AXES):
        x, y, u = [], [], []
        for z, t, b in zip(Zh, Th, hblock):
            ok = ~np.isnan(t)
            if ok.sum() >= 2 and ok[j]: x.append(z[j] - z[ok].mean()); y.append(t[j] - np.nanmean(t)); u.append(b)
        per[ax] = AR.boot_rho(x, y, u) if len(x) >= 10 else None
    hidden = [ax for ax in AXES if per[ax] is None or per[ax]["lo"] <= 0]
    res.update(best_referee=best, chosen=chosen, per_axis_hudine=per, hidden=hidden)
    json.dump(res, open(AR.RES + "axis_source_compare_v1.json", "w"), indent=1)
    for k, v in res["models"].items(): print(f"{k:5s} referee {v['referee_hudine']:.3f}  cv FinnGen {v['cv_finngen']:.3f}  cv DTB {v['cv_dtb']:.3f}")
    for k, v in res["paired_vs_F"].items(): print(k, "vs F:", {s: f"{d['delta']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]" for s, d in v.items()})
    for ax, r in per.items(): print(f"  {ax:20s}", f"{r['rho']:+.3f} [{r['lo']:+.3f}, {r['hi']:+.3f}] n={r['n']}" if r else "-", "blank" if ax in hidden else "")
    print("chosen", chosen, "hidden", hidden)
    if a.write:
        ck = torch.load(VM.PT, weights_only=False, map_location="cpu")
        if chosen != "F":
            ck["axis"] = full[chosen].states
            ck["meta"]["axis_training"] = {"D": "DTB exposures only", "FD1": "FinnGen + DTB", "FD05": "FinnGen + DTB (weight 0.5)"}[chosen]
        ck["axis_hidden"] = hidden; torch.save(ck, VM.PT); print("written to", VM.PT)


if __name__ == "__main__":
    main()
