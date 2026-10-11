"""Does the learned cross-organ vulnerability add anything ON TOP OF the curated own organs? (the recommender's actual choice)

For each registry condition c: positives = ADCs whose label warns on c's own organ(s) (the only per-drug truth available here;
not patient outcomes). Score each ADC by T_inc . s, where T_inc is the grade >= 3 incidence percentile (warnings excluded, so
the score does not contain the positives' definition) and s is either
    own        curated severity on the condition's own organs (what the recommender uses by default)
    own+L(f)   max(own, f * learned)                             (what --learned f does)
AUROC per condition, paired difference own+L(f) - own, bootstrap over conditions. Pre-declared: f in {0.25, 0.5}, decision =
the 95% interval of the paired difference excludes 0 in the positive direction. Repeated with positives from FAERS
(post-marketing disproportionality, ml/validate_faers.py), which do not come from the label text at all.
Writes ml/results/learned_addon.json.
"""
import json, csv, sys
sys.path[:0] = ['/home/hyeongchanahn/CONI/adctox/ml', '/home/hyeongchanahn/CONI/adctox/src']
import numpy as np, pandas as pd
import matcher2 as M2
from matcher import AXES, auroc, R

def main():
    wt = M2.warnings_table(); inc, _ = M2.incidence_table(); ids = sorted(set(wt) & set(inc.index))
    W = np.stack([wt[i][0] for i in ids]); Tinc = pd.DataFrame(inc.loc[ids].values).rank(pct=True, method="average").values
    L = json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"]; reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}
    def own(c): v = np.zeros(len(AXES)); [v.__setitem__(AXES.index(a), float(reg[c]["severity"])) for a in reg[c]["organ_axes"].split(";") if a in AXES]; return v
    lv = lambda c: np.array([L[c][a] for a in AXES]); rows = []
    for c in reg:
        ax = [AXES.index(a) for a in reg[c]["organ_axes"].split(";") if a in AXES]; pos = (W[:, ax] > 0).any(1)
        if pos.sum() in (0, len(ids)): continue
        r = dict(cond=c, n_pos=int(pos.sum()), own=auroc(Tinc @ own(c), pos))
        for f in (0.25, 0.5): r[f"own_L{f}"] = auroc(Tinc @ np.maximum(own(c), f * lv(c)), pos)
        rows.append(r)
    df = pd.DataFrame(rows); rng = np.random.default_rng(0); out = dict(n_conditions=len(df), n_adcs=len(ids), mean={}, paired={})
    for k in ("own", "own_L0.25", "own_L0.5"): out["mean"][k] = float(df[k].mean())
    print(f"{len(df)} registry conditions x {len(ids)} ADCs; score = incidence percentile . s (non-circular)")
    m = out["mean"]; print(f"   mean AUROC   own {m['own']:.3f} | own+0.25L {m['own_L0.25']:.3f} | own+0.5L {m['own_L0.5']:.3f}")
    for f in (0.25, 0.5):
        d = (df[f"own_L{f}"] - df["own"]).values; bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(5000)]
        lo, hi = np.percentile(bs, [2.5, 97.5]); out["paired"][str(f)] = dict(mean=float(d.mean()), ci=[float(lo), float(hi)], helps=bool(lo > 0), hurts=bool(hi < 0))
        print(f"   own+{f}L minus own  {d.mean():+.3f} [{lo:+.3f}, {hi:+.3f}]  -> {'adds' if lo > 0 else 'worse' if hi < 0 else 'no demonstrated gain'}")
    out["faers"] = faers_truth(ids, Tinc, own, lv, reg, rng)
    json.dump(dict(out, per_condition=rows), open(R + "ml/results/learned_addon.json", "w"), indent=1)


def faers_truth(ids, Tinc, own, lv, reg, rng):
    """The same comparison with positives taken from post-marketing reports instead of the labels: ADCs with a FAERS
    disproportionality signal on the condition's own organ (ml/results/faers_validation.json). Independent of the label text."""
    F = json.load(open(R + "ml/results/faers_validation.json")); sig = {(c["adc"], c["organ"]): c["signal"] for c in F["cells"]}
    keep = [k for k, a in enumerate(ids) if a in F["adcs"]]; rows = []
    for c in reg:
        ax = [a for a in reg[c]["organ_axes"].split(";") if a in AXES]
        pos = np.array([any(sig.get((ids[k], a), False) for a in ax) for k in keep])
        if pos.sum() in (0, len(keep)): continue
        T = Tinc[keep]; r = dict(cond=c, n_pos=int(pos.sum()), own=auroc(T @ own(c), pos))
        for f in (0.25, 0.5): r[f"own_L{f}"] = auroc(T @ np.maximum(own(c), f * lv(c)), pos)
        rows.append(r)
    df = pd.DataFrame(rows); res = dict(n_conditions=len(df), n_adcs=len(keep), mean={k: float(df[k].mean()) for k in ("own", "own_L0.25", "own_L0.5")}, paired={})
    m = res["mean"]; print(f"\nFAERS positives (independent of labels): {len(df)} conditions x {len(keep)} ADCs")
    print(f"   mean AUROC   own {m['own']:.3f} | own+0.25L {m['own_L0.25']:.3f} | own+0.5L {m['own_L0.5']:.3f}")
    for f in (0.25, 0.5):
        d = (df[f"own_L{f}"] - df["own"]).values; bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(5000)]
        lo, hi = np.percentile(bs, [2.5, 97.5]); res["paired"][str(f)] = dict(mean=float(d.mean()), ci=[float(lo), float(hi)], helps=bool(lo > 0), hurts=bool(hi < 0))
        print(f"   own+{f}L minus own  {d.mean():+.3f} [{lo:+.3f}, {hi:+.3f}]  -> {'adds' if lo > 0 else 'worse' if hi < 0 else 'no demonstrated gain'}")
    return res

if __name__ == "__main__":
    main()
