"""Option 1: match a patient's comorbidities to EXISTING ADCs, lowest organ burden first.

    score(adc | patient) = sum_o  w_o(patient) * t_o(adc)

w_o  learned organ vulnerability of the comorbidity (ml/learned_vulnerability.py), 0-1, relative across organs.
t_o  the ADC's observed severe (grade >= 3) adverse-event burden in organ o, from the transcribed trial tables,
     converted to a percentile among ADCs so it lives on the same 0-1 footing as w. This is a RECORD of what was
     observed, not a prediction: structure -> toxicity was measured and is not learnable (ml/README.md).

How t_o is built (and why it is a lower bound): per (ADC, trial, organ) take the largest severe-term rate -- patients
overlap across terms, so a sum would overcount -- then pool over trials weighted by trial size. A trial that reports
severe events but lists nothing for an organ contributes 0 there: severe-event tables carry a reporting cut, so 0
means "below the cut", not "none". ADCs with < MIN_PATIENTS patients of severe-grade evidence are not scored.

Evaluation is against the label-derived hard flags (conf/hard_flags.yaml): e.g. for a patient with interstitial lung
disease, does the score put DXd/exatecan ADCs among the high-burden ones? That is CONSISTENCY with warnings the
trials themselves helped write, not independent validation, and it is reported as such.
"""
import json, re, sys, warnings
import numpy as np, pandas as pd, yaml
warnings.filterwarnings("ignore")
C = "/data/hyeongchanahn/adctox/ml_cache/"; R = "/home/hyeongchanahn/CONI/adctox/"
MIN_PATIENTS = 100; MIN_TERMS = 15
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
DOM = {"Cardiac": "cardiovascular", "Vascular": "cardiovascular", "Skin": "dermatologic", "Metabolic": "metabolic_endocrine", "Endocrine": "metabolic_endocrine",
       "Renal": "renal", "Hematologic": "haematologic", "Pulmonary": "pulmonary", "Ocular": "ocular", "Hepatic": "hepatic", "GI": "gastrointestinal",
       "Neurologic": "neurologic", "Musculoskeletal": "musculoskeletal", "Infection": "infectious_immune", "Immune": "infectious_immune"}

def canon_payload(s):
    s = str(s).lower()
    if "calicheamicin" in s: return "calicheamicin"
    if "dxd" in s or "exatecan" in s: return "dxd_exatecan"
    if "mmaf" in s: return "mmaf"
    if "mmae" in s: return "mmae"
    return "other"

def burden():
    """severe-grade burden per (ADC, organ). v2: every severe category, rate-only rows, trial size from all rows of the trial,
    and a coverage floor (MIN_TERMS distinct severe terms) so a sparsely-reported drug cannot look safe by omission."""
    t = pd.read_pickle(C + "tox.pkl"); ms = pd.read_pickle(C + "master.pkl")
    t = t[t["Canonical observation"].astype(str) == "True"].copy()
    t["a"] = pd.to_numeric(t["Affected n"], errors="coerce"); t["N"] = pd.to_numeric(t["At risk N"], errors="coerce"); pct = pd.to_numeric(t["Incidence percent"], errors="coerce")
    t["rate"] = np.where(pct.notna(), pct / 100, t.a / t.N); t = t[t.rate.between(0, 1)]
    Ntr = t.dropna(subset=["N"]).groupby(["ADC ID", "Trial ID"]).N.max().rename("Ntr").reset_index(); Ntr = Ntr[Ntr.Ntr >= 10]
    sv = t[t["Grade category"].isin(["Grade >=3", "Grade 3-4", "Grade 3", "Grade 4", "Grade 5"])].copy()
    sv["term"] = sv["Raw AE term"].astype(str).str.lower().str.strip(); sv["fam"] = np.where(sv["Grade category"].isin(["Grade >=3", "Grade 3-4"]), "cum", "part")
    cum = sv[sv.fam == "cum"].groupby(["ADC ID", "Trial ID", "term", "Toxicity domain"]).rate.max().rename("r").reset_index()
    part = sv[sv.fam == "part"].groupby(["ADC ID", "Trial ID", "term", "Toxicity domain"]).rate.sum().rename("r").reset_index()      # grades 3,4,5 are disjoint: add
    both = pd.concat([cum, part]).groupby(["ADC ID", "Trial ID", "term", "Toxicity domain"]).r.max().reset_index()                  # cumulative wins if both exist
    both["r"] = both.r.clip(0, 1); both["axis"] = both["Toxicity domain"].astype(str).str.split(" / ").str[0].map(DOM)
    both = both.merge(Ntr, on=["ADC ID", "Trial ID"])                                                                               # needs a trial size
    nterms = both.groupby("ADC ID").term.nunique()
    ax = both.dropna(subset=["axis"]).groupby(["ADC ID", "Trial ID", "axis"]).r.max().rename("r").reset_index()
    trial = both.groupby(["ADC ID", "Trial ID"]).Ntr.max().reset_index()
    full = trial.merge(pd.DataFrame([(x, y, o) for (x, y) in trial[["ADC ID", "Trial ID"]].itertuples(index=False) for o in AXES], columns=["ADC ID", "Trial ID", "axis"]), on=["ADC ID", "Trial ID"])
    full = full.merge(ax, on=["ADC ID", "Trial ID", "axis"], how="left").fillna({"r": 0.0})
    g = full.assign(w=full.Ntr * full.r).groupby(["ADC ID", "axis"]).agg(w=("w", "sum"), n=("Ntr", "sum")).reset_index(); g["rate"] = g.w / g.n
    pat = trial.groupby("ADC ID").Ntr.sum(); ntr = trial.groupby("ADC ID").size()
    rate = g.pivot(index="ADC ID", columns="axis", values="rate").reindex(columns=AXES).fillna(0.0)
    info = ms.drop_duplicates("ADC ID").set_index("ADC ID")[["ADC name", "Payload"]].reindex(rate.index); info["pay"] = info.Payload.map(canon_payload)
    info["patients"] = pat; info["trials"] = ntr; info["terms"] = nterms
    keep = (info.patients >= MIN_PATIENTS) & (info.terms >= MIN_TERMS); rate, info = rate[keep], info[keep]
    pct_ = rate.rank(pct=True, method="average")
    return rate, pct_, info

def auroc(score, pos):
    from scipy.stats import rankdata
    r = rankdata(score); n1 = pos.sum(); n0 = (~pos).sum()
    return np.nan if n1 == 0 or n0 == 0 else (r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

def main():
    rate, pct, info = burden(); print(f"scored ADCs: {len(info)} (>= {MIN_PATIENTS} patients and >= {MIN_TERMS} distinct severe terms); by payload: {info.pay.value_counts().to_dict()}", flush=True)
    L = json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"]
    import csv; reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}
    flags = yaml.safe_load(open(R + "conf/hard_flags.yaml")); flags = flags["flags"] if "flags" in flags else flags
    T = pct.values; names = list(info["ADC name"])
    def wvec(cid): return np.array([L[cid][a] for a in AXES])
    def hand(cid):
        v = np.zeros(len(AXES)); s = float(reg[cid]["severity"])
        for a in reg[cid]["organ_axes"].split(";"): v[AXES.index(a)] = s
        return v
    rows = []; rng = np.random.default_rng(0); allc = [c for c in L]
    for fl in flags:
        want = {"dxd_exatecan" if p.lower() in ("dxd", "exatecan") else p.lower() for p in fl["payloads"]}; pos = info.pay.isin(want).values
        for cid in fl["comorbidities"]:
            if cid not in L or pos.sum() == 0: continue
            s_learn = T @ wvec(cid); s_hand = T @ hand(cid); s_unif = T.sum(1); s_axis = T[:, AXES.index(fl["axis"])]
            others = [c for c in allc if c != cid]; null = np.mean([auroc(T @ wvec(c), pos) for c in rng.choice(others, 20, replace=False)])
            rows.append(dict(flag=fl["id"], condition=cid, axis=fl["axis"], n_pos=int(pos.sum()), n_adc=len(pos), learned=auroc(s_learn, pos), hand=auroc(s_hand, pos),
                             uniform=auroc(s_unif, pos), shuffled_w=float(null), axis_only=auroc(s_axis, pos)))
    df = pd.DataFrame(rows); pd.set_option("display.width", 200)
    print("\nAUROC: does the score put the flagged payload's ADCs among the HIGH-burden ones for this patient? (0.5 = chance)")
    print(df.round(2).to_string(index=False))
    summ = {k: float(df[k].mean()) for k in ["learned", "hand", "uniform", "shuffled_w", "axis_only"]}
    # bootstrap over ADCs (the unit that is sampled), recomputing every row's AUROC
    boots = {k: [] for k in summ}
    for _ in range(1000):
        j = rng.integers(0, len(info), len(info)); Tb = T[j]; ib = info.iloc[j]; vals = {k: [] for k in summ}
        for r in rows:
            fl = next(f for f in flags if f["id"] == r["flag"]); want = {"dxd_exatecan" if p.lower() in ("dxd", "exatecan") else p.lower() for p in fl["payloads"]}; pos = ib.pay.isin(want).values
            if pos.sum() == 0 or (~pos).sum() == 0: continue
            vals["learned"].append(auroc(Tb @ wvec(r["condition"]), pos)); vals["hand"].append(auroc(Tb @ hand(r["condition"]), pos))
            vals["uniform"].append(auroc(Tb.sum(1), pos)); vals["axis_only"].append(auroc(Tb[:, AXES.index(r["axis"])], pos))
            vals["shuffled_w"].append(auroc(Tb @ wvec(rng.choice(allc)), pos))
        for k in summ: boots[k].append(np.nanmean(vals[k]))
    ci = {k: [float(np.percentile(boots[k], 2.5)), float(np.percentile(boots[k], 97.5))] for k in summ}
    print("\nmean AUROC over flag x condition rows [95% CI, bootstrapped over ADCs]")
    for k in ["learned", "hand", "uniform", "shuffled_w", "axis_only"]: print(f"  {k:11s} {summ[k]:.3f} [{ci[k][0]:.3f}, {ci[k][1]:.3f}]")
    # demo: lowest-burden ADCs for a few patients, with the organs that drive the score
    demo = {}
    for cids in (["interstitial_lung_disease"], ["cirrhosis"], ["ckd_stage_4_5"], ["dry_eye"], ["heart_failure", "ckd_stage_4_5"]):
        w = np.maximum.reduce([wvec(c) for c in cids]); s = T @ w; order = np.argsort(s)
        def why(i): c = T[i] * w; top = np.argsort(-c)[:2]; return [f"{AXES[k]} (w {w[k]:.2f} x burden pct {T[i][k]:.2f})" for k in top if c[k] > 0]
        demo["+".join(cids)] = dict(lowest=[dict(adc=names[i], payload=info.pay.iloc[i], score=float(s[i]), patients=int(info.patients.iloc[i])) for i in order[:5]],
                                    highest=[dict(adc=names[i], payload=info.pay.iloc[i], score=float(s[i]), why=why(i)) for i in order[::-1][:3]])
    json.dump(dict(n_adc=len(info), by_payload=info.pay.value_counts().to_dict(), rows=rows, mean_auroc=summ, ci=ci, demo=demo), open(R + "ml/results/matcher.json", "w"), indent=1, default=str)
    for k, v in demo.items():
        print(f"\n{k}\n  lowest burden : {[(d['adc'][:28], d['payload']) for d in v['lowest']]}\n  highest burden: {[(d['adc'][:28], d['payload'], d['why']) for d in v['highest']]}")

if __name__ == "__main__":
    main()
