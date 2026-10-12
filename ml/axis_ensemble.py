"""Comparison heads shown next to the main axis head, and whether their agreement should gate automatic use.

    CUDA_VISIBLE_DEVICES=1 python -I ml/axis_ensemble.py [--write]
    CUDA_VISIBLE_DEVICES=1 python -I ml/axis_ensemble.py --swap-main [--write]    (v2: Both becomes the main model)

Models (names as the terminal shows them):
  기본 (main)      the deployed axis heads, Danish DTB only (axis_source_compare.py)
  통합 (combined)  FinnGen + DTB, weight 1, seeds 1000-1002 (the FD1 model of axis_source_compare.py)
  이전 (previous)  FinnGen-only axis heads of model 0.1 (vuln_biolord.finngen_axis_2026-10-12.pt)
Agreement of an organ = how many of the three models have it among their top 3 organs with severity > 0.
Check on HuDiNe (independent US cohort, as axis_source_compare.py): for each disease, the main model's top-3 organs are
counted correct when the disease's centred HuDiNe truth on that organ is > 0. Precision is compared between organs that
>= 2 models agree on and organs only the main model names (bootstrap over ICD-9 blocks).
Rule, fixed before running: automatic use (the "자동" fallback) keeps only organs with agreement >= 2 iff that precision
difference has CI lower bound > 0; otherwise agreement is shown but does not gate anything.
--write stores the comparison heads ('axis_models') and the gate ('agree_min') in the deployed checkpoint.

v2 (--swap-main, user decision after v1): the FinnGen + DTB model becomes the main model, because across the three cohorts it
has the best mean (0.363 vs 0.349) and worst case (0.334 vs 0.224) of the within-disease score, though it is lower than DTB
alone on HuDiNe (-0.044 [-0.064, -0.023]). The same agreement rule is re-checked with it as main, and its blank axes are
re-decided on HuDiNe (per-axis CI lower bound > 0, as axis_source_compare.py). Display names are stored with the heads:
Both (main), Den, Fin.
"""
import argparse, json, os, sys
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import vulnerability_model as VM, axis_reliability as AR, axis_dtb_augment as DA, axis_source_compare as SC
from vulnerability_model import AXES
PREV = VM.C + "vuln_biolord.finngen_axis_2026-10-12.pt"


def heads(states, dP):
    nets = []
    for st in states:
        n = VM.axis_net(dP); n.load_state_dict(st); nets.append(n.eval())
    def predict(X):
        with torch.no_grad(): return np.mean([n(torch.tensor(X)).numpy() for n in nets], 0)
    return predict


def sev(Z): return np.clip(Z - np.median(Z, 1, keepdims=True), 0, 1)


def top3(S): return [set(np.argsort(-s)[:3][s[np.argsort(-s)[:3]] > 0]) for s in S]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--write", action="store_true"); ap.add_argument("--swap-main", action="store_true"); a = ap.parse_args()
    m, P, O, rows, nl, nd, up, uo = VM._data(); ck = torch.load(VM.PT, weights_only=False, map_location="cpu"); spread = ck["meta"]["spread"]
    T = VM.axis_targets(m, m.groupby("outcome_name").y.mean(), spread).reindex(up.prior_name).values.astype(np.float32)
    dc, dt, Td = DA.dtb_targets(); Pd = VM._st(dt).astype(np.float32)
    previous = torch.load(PREV, weights_only=False, map_location="cpu")["axis"]
    if a.swap_main:                                                    # heads already trained by v1: Both is main, DTB-only is shown next to it
        alt = {m["name"]: m["axis"] for m in ck["axis_models"]}
        if "combined" in alt: main_states, combined = alt["combined"], ck["axis"]
        else: main_states, combined = ck["axis"], alt["Den"]
        names = ("Both", "Den", "Fin")
    else:
        W = np.r_[np.ones(len(P)), np.ones(len(Pd))].astype(np.float32)
        combined = [DA.train_w(np.r_[P, Pd], np.r_[T, Td], W, s)[0] for s in (1000, 1001, 1002)]; main_states = ck["axis"]; names = ("main", "combined", "previous")
    models = {"main": heads(main_states, P.shape[1]), "combined": heads(combined, P.shape[1]), "previous": heads(previous, P.shape[1])}
    hc, ht, Th = SC.hudine_targets(); Ph = VM._st(ht).astype(np.float32); hb = np.array([c[:2] for c in hc])
    S = {k: sev(f(Ph)) for k, f in models.items()}; tops = {k: top3(v) for k, v in S.items()}
    hit, agree, unit = [], [], []
    for i in range(len(hc)):
        t = Th[i]; ok = ~np.isnan(t); tc = t - np.nanmean(t)
        for j in tops["main"][i]:
            if not ok[j]: continue
            hit.append(float(tc[j] > 0)); agree.append(sum(j in tops[k][i] for k in models)); unit.append(hb[i])
    hit, agree, unit = map(np.array, (hit, agree, unit))
    prec = {int(k): dict(precision=float(hit[agree == k].mean()), n=int((agree == k).sum())) for k in (1, 2, 3) if (agree == k).any()}
    uu = np.unique(unit); by = {u: np.where(unit == u)[0] for u in uu}; rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        ix = np.concatenate([by[u] for u in rng.choice(uu, len(uu))]); h, g = hit[ix], agree[ix]
        if (g >= 2).any() and (g == 1).any(): bs.append(h[g >= 2].mean() - h[g == 1].mean())
    diff = dict(delta=float(hit[agree >= 2].mean() - hit[agree == 1].mean()), lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)))
    res = dict(precision_by_agreement=prec, agreed_minus_single=diff, overall_precision=float(hit.mean()), n_organs=len(hit))
    res["agree_min"] = 2 if diff["lo"] > 0 else 1
    Zm = models["main"](Ph); per = {}
    for j, ax in enumerate(AXES):
        x, y, u = [], [], []
        for z, t, b in zip(Zm, Th, hb):
            ok = ~np.isnan(t)
            if ok.sum() >= 2 and ok[j]: x.append(z[j] - z[ok].mean()); y.append(t[j] - np.nanmean(t)); u.append(b)
        per[ax] = AR.boot_rho(x, y, u) if len(x) >= 10 else None
    res["per_axis_hudine_main"] = per; res["hidden"] = [ax for ax in AXES if per[ax] is None or per[ax]["lo"] <= 0]; res["names"] = names
    json.dump(res, open(AR.RES + ("axis_ensemble_v2.json" if a.swap_main else "axis_ensemble_v1.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "per_axis_hudine_main"}, indent=1))
    if a.write:
        ck["axis"] = main_states; ck["axis_label"] = names[0]; ck["axis_hidden"] = res["hidden"]
        ck["axis_models"] = [dict(name=names[1], axis=combined), dict(name=names[2], axis=previous)]; ck["agree_min"] = res["agree_min"]
        if a.swap_main: ck["meta"]["axis_training"] = "FinnGen priors + DTB exposures (Siggaard 2020), weight 1"
        torch.save(ck, VM.PT); print("written to", VM.PT)


if __name__ == "__main__":
    main()
