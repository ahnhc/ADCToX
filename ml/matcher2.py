"""Drug side rebuilt on the approved labels, where every drug is reported the same way.

t_warn[adc, organ]  regulator-assigned: 1.0 boxed warning, 0.6 section-5 warning, else 0 (latest DailyMed label,
                    parsed by adctox.validation.label_change, the project's own section-5 -> organ parser).
t_inc [adc, organ]  grade >= 3 incidence from the label's own adverse-reaction tables, as a percentile among the scored ADCs.
t = t_warn + (1 - t_warn) * 0.4 * t_inc  -- a warning dominates, incidence grades the rest. (The first version capped a sum at 1, which let a
section-5 warning plus a high incidence percentile tie a boxed warning; found when T-DXd came 5th for an ILD patient, and fixed to the stated intent.)

Why two layers: incidence alone under-rates rare but lethal events (T-DXd ILD is a boxed warning at ~1% grade >= 3), and a
warning alone cannot tell two flagged drugs apart.

Two evaluations, because the warning layer is circular against label warnings by construction:
  (1) drug side, non-circular: does t_inc ALONE recover the organs the label warns about?  (per-drug AUROC over organs)
  (2) matching, for each of the 41 registry comorbidities: positives = ADCs whose label warns on the comorbidity's organ(s);
      AUROC of sum_o w_o * t_o. 'inc_only' is the non-circular variant; 'full' includes the warning layer and therefore mainly
      tests whether the learned vulnerability points at the right organ.  Baselines: no patient weights, hand-set severities,
      other conditions' weights (null).
"""
import json, re, sys, csv, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/hyeongchanahn/CONI/src"); sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/src")
from adctox.validation.label_change import parse_version
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
import matcher as M
from matcher import AXES, DOM, auroc, C, R
DM = "/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07/"
W_BOXED, W_SEC5, W_INC = 1.0, 0.6, 0.4

def warnings_table():
    man = json.load(open(DM + "_manifest.json"))["agents"]; rows = {}
    for agent in man:
        files = sorted(int(re.search(r"v(\d+)\.html", f).group(1)) for f in __import__("os").listdir(DM + agent) if re.match(r"v\d+\.html", f))
        v = files[-1]; lv = parse_version(__import__("pathlib").Path(DM + f"{agent}/v{v}.html"), agent, v, None)
        t = np.zeros(len(AXES)); kind = {}
        for a, heads in lv.axes.items():
            if a in AXES: t[AXES.index(a)] = max(t[AXES.index(a)], W_SEC5); kind[a] = "W&P"
        for a in lv.boxed_axes:
            if a in AXES: t[AXES.index(a)] = W_BOXED; kind[a] = "boxed"
        rows[agent.replace("_", "-")] = (t, kind, v)
    return rows

def incidence_table():
    t = pd.read_pickle(C + "tox.pkl"); ms = pd.read_pickle(C + "master.pkl").drop_duplicates("ADC ID").set_index("ADC ID")
    L = t[(t["Canonical observation"].astype(str) == "True") & (t["Source type"] == "Regulatory label via DailyMed")].copy()
    L["pct"] = pd.to_numeric(L["Incidence percent"], errors="coerce"); L = L.dropna(subset=["pct"]); L["term"] = L["Raw AE term"].astype(str).str.lower().str.strip()
    cum = L[L["Grade category"].isin(["Grade 3-4", "Grade >=3"])].groupby(["ADC ID", "term", "Toxicity domain"]).pct.max()
    part = L[L["Grade category"].isin(["Grade 3", "Grade 4"])].groupby(["ADC ID", "term", "Toxicity domain"]).pct.sum()
    both = pd.concat([cum, part]).groupby(level=[0, 1, 2]).max().rename("r").reset_index()
    both["axis"] = both["Toxicity domain"].astype(str).str.split(" / ").str[0].map(DOM)
    inc = both.dropna(subset=["axis"]).groupby(["ADC ID", "axis"]).r.max().unstack().reindex(columns=AXES).fillna(0.0) / 100.0
    return inc, ms

def main():
    wt = warnings_table(); inc, ms = incidence_table(); ids = sorted(set(wt) & set(inc.index)); print(f"ADCs with both a current label and label tables: {len(ids)}\n  {ids}\n  missing a table: {sorted(set(wt) - set(inc.index))}", flush=True)
    W = np.stack([wt[i][0] for i in ids]); I = inc.loc[ids].values; Ipct = pd.DataFrame(I).rank(pct=True, method="average").values
    T_full = W + (1.0 - W) * W_INC * Ipct; T_inc = Ipct
    warned = W > 0
    # (1) drug side, non-circular: t_inc alone vs the label's warning organs
    d1 = [auroc(Ipct[k], warned[k]) for k in range(len(ids)) if 0 < warned[k].sum() < len(AXES)]
    rng = np.random.default_rng(0); b = [np.nanmean([d1[j] for j in rng.integers(0, len(d1), len(d1))]) for _ in range(2000)]
    print(f"\n(1) incidence layer alone recovers the organs the label warns about: mean AUROC {np.nanmean(d1):.3f} [{np.percentile(b, 2.5):.3f}, {np.percentile(b, 97.5):.3f}] over {len(d1)} drugs (0.5 = chance)")
    for k, i in enumerate(ids):
        if 0 < warned[k].sum(): print(f"     {i:28s} AUROC {auroc(Ipct[k], warned[k]):.2f}  warns on: {', '.join(f'{a}({wt[i][1][a]})' for a in sorted(wt[i][1]))}")
    # (2) matching over the registry comorbidities
    L = json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"]; reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}
    wv = lambda c: np.array([L[c][a] for a in AXES])
    def hand(c): v = np.zeros(len(AXES)); [v.__setitem__(AXES.index(a), float(reg[c]["severity"])) for a in reg[c]["organ_axes"].split(";") if a in AXES]; return v
    rows = []; allc = list(L)
    for c in allc:
        ax = [AXES.index(a) for a in reg[c]["organ_axes"].split(";") if a in AXES]; pos = warned[:, ax].any(1)
        if pos.sum() == 0 or pos.sum() == len(ids): continue
        null_f = np.mean([auroc(T_full @ wv(o), pos) for o in rng.choice([x for x in allc if x != c], 20, replace=False)])
        null_i = np.mean([auroc(T_inc @ wv(o), pos) for o in rng.choice([x for x in allc if x != c], 20, replace=False)])
        rows.append(dict(cond=c, n_pos=int(pos.sum()), full=auroc(T_full @ wv(c), pos), full_hand=auroc(T_full @ hand(c), pos), full_uniform=auroc(T_full.sum(1), pos), full_null=null_f,
                         inc=auroc(T_inc @ wv(c), pos), inc_hand=auroc(T_inc @ hand(c), pos), inc_uniform=auroc(T_inc.sum(1), pos), inc_null=null_i))
    df = pd.DataFrame(rows); print(f"\n(2) matching: {len(df)} registry conditions with at least one warned and one unwarned ADC of {len(ids)}")
    cols = ["full", "full_hand", "full_uniform", "full_null", "inc", "inc_hand", "inc_uniform", "inc_null"]; out = {}
    for k in cols:
        v = df[k].dropna().values; bs = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(3000)]; out[k] = (v.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5))
    print("   mean AUROC [95% CI over conditions]   learned w | hand-set | no patient weights | other conditions' w (null)")
    for pre, name in (("full", "warning + incidence (circular for warned organs)"), ("inc", "incidence only (non-circular)")):
        g = [out[pre], out[pre + "_hand"], out[pre + "_uniform"], out[pre + "_null"]]
        print(f"   {name:48s} " + " | ".join(f"{x[0]:.3f} [{x[1]:.2f},{x[2]:.2f}]" for x in g))
    # paired: learned minus null / uniform, per condition
    for pre in ("full", "inc"):
        for base in ("uniform", "null", "hand"):
            d = (df[pre] - df[f"{pre}_{base}"]).dropna().values; bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(3000)]
            print(f"   {pre}: learned minus {base:8s} {d.mean():+.3f} [{np.percentile(bs, 2.5):+.3f}, {np.percentile(bs, 97.5):+.3f}]")
    demo = {}
    for cids in (["interstitial_lung_disease"], ["cirrhosis"], ["ckd_stage_4_5"], ["dry_eye"], ["peripheral_neuropathy"]):
        w = np.maximum.reduce([wv(c) for c in cids]); s = T_full @ w; order = np.argsort(s)
        demo["+".join(cids)] = dict(lowest=[(ids[i], round(float(s[i]), 2)) for i in order[:4]],
                                    highest=[(ids[i], round(float(s[i]), 2), [AXES[k] for k in np.argsort(-(T_full[i] * w))[:2]]) for i in order[::-1][:3]])
        print(f"\n{'+'.join(cids)}\n   lowest burden : {demo['+'.join(cids)]['lowest']}\n   highest burden: {demo['+'.join(cids)]['highest']}")
    json.dump(dict(adcs=ids, drug_side_auroc=dict(mean=float(np.nanmean(d1)), ci=[float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))], n=len(d1)), matching={k: list(map(float, v)) for k, v in out.items()},
                   per_condition=rows, demo=demo, weights=dict(boxed=W_BOXED, sec5=W_SEC5, inc=W_INC)), open(R + "ml/results/matcher2.json", "w"), indent=1, default=str)

if __name__ == "__main__":
    main()
