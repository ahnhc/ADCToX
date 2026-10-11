"""Stage-5 patient-level validation harness: does the recommender's verdict for the ADC a patient actually received predict
what happened to that patient? Runs the pre-declared analysis of ml/docs/validation_plan.md on any cohort file in this schema.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/validate_outcomes.py cohort.csv [--out results.json]

Input CSV, one row per patient x administered ADC:
  patient_id, adc (id as in conf/label_restrictions.yaml, e.g. trastuzumab-deruxtecan), conditions (registry ids, ';'-separated),
  crcl, bili, ast, alt, child_pugh, lvef       (blank = not measured; the tool then judges the worst case, as in use)
  outcome                                  (0/1: grade >= 3 adverse event in the patient's vulnerable organs within the window)
  site                                     (optional; bootstrap is clustered by site when present)
Predictors, all computed by ml/recommend.py exactly as the tool would for that patient:
  tool       the full order key for the administered ADC (restriction tier worst case, settled tier, B, Wn), as one rank score
  restrict   restriction tier only
  organ      B then Wn only (label warnings on the patient's organs)
Baselines: label_only (the same ADC's warnings with every organ counted, i.e. no patient information), random.
Metrics: AUROC with a patient (or site-cluster) bootstrap, and the paired difference tool - label_only, the pre-declared decision
statistic: the tool adds patient information only if that interval excludes 0. The tool outputs an order, not a probability, so
calibration is assessed on a probability fitted to that order out of fold (Brier vs base rate, calibration-in-the-large, slope).

There is no patient-level cohort in this repository. tests/test_ml_recommender.py runs the harness on synthetic cohorts with a
known answer to show that it detects a real association and does not invent one.
"""
import csv, json, sys
import numpy as np
sys.path[:0] = ["/home/hyeongchanahn/CONI/adctox/ml", "/home/hyeongchanahn/CONI/adctox/src"]
from matcher import auroc

LABS = ("crcl", "bili", "ast", "alt", "lvef")


def _labs(row):
    out = {k: float(row[k]) for k in LABS if row.get(k) not in (None, "")}
    if row.get("child_pugh"): out["child_pugh"] = row["child_pugh"].strip().upper()
    return out


def features(rows):
    """per row: tool key, restriction tier, organ key, label-only count. Patients sharing inputs share one recommender call."""
    import recommend as RC, drug_evidence as DE
    E = DE.evidence(); cache = {}; out = []
    for r in rows:
        conds = tuple(sorted(c for c in r["conditions"].split(";") if c)); labs = _labs(r); k = (conds, tuple(sorted(labs.items())))
        if k not in cache: cache[k] = {x["adc"]: x for x in RC.recommend(list(conds), labs)[0]}
        x = cache[k][r["adc"]]; org = E[r["adc"]]["organs"]
        out.append(dict(tool=(x["tier"], x["verdict"].worst_known, x["B"], x["Wn"]), restrict=(x["tier"], x["verdict"].worst_known), organ=(x["B"], x["Wn"]),
                        label_only=(sum(o["level"] == "boxed" for o in org.values()), sum(o["level"] == "W&P" for o in org.values()))))
    return out


def _rank(keys):
    """lexicographic keys -> one score with ties kept (average rank)."""
    from scipy.stats import rankdata
    order = sorted(set(keys)); idx = {k: i for i, k in enumerate(order)}
    return rankdata([idx[k] for k in keys])


def analyse(rows, feats, n_boot=2000, seed=0):
    y = np.array([int(r["outcome"]) for r in rows], bool); rng = np.random.default_rng(seed)
    S = {k: _rank([f[k] for f in feats]) for k in ("tool", "restrict", "organ", "label_only")}; S["random"] = rng.random(len(rows))
    sites = np.array([r.get("site") or r["patient_id"] for r in rows]); units = np.unique(sites); by = {u: np.where(sites == u)[0] for u in units}
    res = dict(n=len(rows), events=int(y.sum()), cluster="site" if any(r.get("site") for r in rows) else "patient", auroc={}, paired={})
    boots = {k: [] for k in S}; diff = []
    for _ in range(n_boot):
        j = np.concatenate([by[u] for u in rng.choice(units, len(units))])
        if not (y[j].any() and (~y[j]).any()): continue
        a = {k: auroc(S[k][j], y[j]) for k in S}; [boots[k].append(a[k]) for k in S]; diff.append(a["tool"] - a["label_only"])
    for k in S: res["auroc"][k] = dict(point=float(auroc(S[k], y)), ci=[float(np.percentile(boots[k], 2.5)), float(np.percentile(boots[k], 97.5))])
    lo, hi = np.percentile(diff, [2.5, 97.5]); res["paired"]["tool_minus_label_only"] = dict(mean=float(np.mean(diff)), ci=[float(lo), float(hi)], adds_patient_information=bool(lo > 0))
    res["calibration"] = calibration(S["tool"], y, sites, rng)
    return res


def calibration(score, y, units, rng, k=5):
    """The tool gives an order; a probability is fitted to it out of fold (logistic on the rank score, folds by site or patient),
    then scored: Brier vs the base rate, calibration-in-the-large, calibration slope."""
    from scipy.optimize import minimize
    u = np.unique(units); fold = {x: i % k for i, x in enumerate(rng.permutation(u))}; f = np.array([fold[x] for x in units])
    x = (score - score.mean()) / (score.std() + 1e-12); p = np.zeros(len(y))
    fit = lambda xx, yy: minimize(lambda w: -np.sum(yy * (w[0] + w[1] * xx) - np.log1p(np.exp(w[0] + w[1] * xx))), [0.0, 0.0]).x
    for i in range(k):
        tr, te = f != i, f == i
        if te.any() and yy_ok(y[tr]): a, b = fit(x[tr], y[tr].astype(float)); p[te] = 1 / (1 + np.exp(-(a + b * x[te])))
        else: p[te] = y[tr].mean()
    yf = y.astype(float); z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    a, sl = minimize(lambda w: -np.sum(yf * (w[0] + w[1] * z) - np.log1p(np.exp(w[0] + w[1] * z))), [0.0, 1.0]).x
    citl = minimize(lambda w: -np.sum(yf * (w[0] + z) - np.log1p(np.exp(w[0] + z))), [0.0]).x[0]
    return dict(method=f"{k}-fold out-of-fold logistic on the tool's rank score", brier=float(np.mean((p - yf) ** 2)), brier_base_rate=float(np.mean((yf.mean() - yf) ** 2)),
                calibration_in_the_large=float(citl), calibration_slope=float(sl))


def yy_ok(y): return bool(y.any() and (~y).any())


def main(path, out=None):
    rows = list(csv.DictReader(open(path))); res = analyse(rows, features(rows))
    print(f"{res['n']} patient x ADC rows, {res['events']} events, bootstrap by {res['cluster']}")
    for k, v in res["auroc"].items(): print(f"  AUROC {k:11s} {v['point']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]")
    c = res["calibration"]; print(f"  calibration ({c['method']}): Brier {c['brier']:.3f} vs base rate {c['brier_base_rate']:.3f}, in-the-large {c['calibration_in_the_large']:+.3f}, slope {c['calibration_slope']:.2f}")
    p = res["paired"]["tool_minus_label_only"]; print(f"  tool - label_only  {p['mean']:+.3f} [{p['ci'][0]:+.3f}, {p['ci'][1]:+.3f}]  -> {'adds patient information' if p['adds_patient_information'] else 'not shown'}")
    if out: json.dump(res, open(out, "w"), indent=1)
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    main(a[0], a[a.index("--out") + 1] if "--out" in a else None)
