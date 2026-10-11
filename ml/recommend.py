"""Patient comorbidities in, a risk percentage for every approved ADC out.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/recommend.py "heart failure" "chronic kidney disease stage 4-5"

risk % = 100 * sum_o w_o * t_o / sum_o w_o
  t_o  the ADC's organ burden, 0-1: label boxed warning 1.0, section-5 warning 0.6; incidence (grade >= 3 percentile) fills at most 0.4 of what a warning leaves open, so a boxed warning always outranks
  w_o  the patient's organ weight, 0-1: the condition's own organ (curated registry severity) or half the learned cross-organ
       vulnerability, whichever is larger; with several conditions the maximum per organ.
100% = a boxed warning on every organ the patient is vulnerable in; 0% = none of them is touched.
The own-organ term is the primary one by construction: summing unconstrained learned weights let a cross-organ association
(ILD -> neurologic) bury a boxed pulmonary warning (T-DXd fell to rank 7 of 12 for an ILD patient; with the own organ it is rank 1).
"""
import csv, json, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
import matcher2 as M2
from matcher import AXES, R
LEARNED_FRACTION = 0.5
REG_NEAR = 0.80             # a free-text condition is 'the same as' a registry condition at this BioLORD cosine -> use its curated organs
MONDO_SEVERITY = 0.80       # organs read off the MONDO hierarchy have no curated severity; one fixed value, not fitted
MATCH_COS = 0.60            # last resort before learned-only: borrow the organs of a loosely similar registry condition
# order for a condition that is not in the registry: near-identical registry entry > MONDO hierarchy > loose registry entry > learned only

_reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}
_by_label = {r["label"].lower(): r["id"] for r in _reg.values()}

def drug_table():
    wt = M2.warnings_table(); inc, ms = M2.incidence_table(); ids = sorted(wt)
    W = np.stack([wt[i][0] for i in ids]); have = np.array([i in inc.index for i in ids])
    Ip = np.full((len(ids), len(AXES)), 0.5)                                 # no label table (gemtuzumab, pivekimab): median, so the warning decides
    sub = pd.DataFrame(inc.loc[[i for i in ids if i in inc.index]].values).rank(pct=True, method="average").values
    Ip[have] = sub; T = W + (1.0 - W) * M2.W_INC * Ip
    names = [(ms.loc[i, "ADC name"] if i in ms.index else i.replace("-", " ").title()) for i in ids]
    return ids, names, T, wt

def own_vec(cid):
    v = np.zeros(len(AXES))
    for a in _reg[cid]["organ_axes"].split(";"):
        if a in AXES: v[AXES.index(a)] = float(_reg[cid]["severity"])
    return v

def patient_weights(conditions):
    """returns (weights over AXES, [(input, how it was understood)])"""
    L = json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"]; ws, notes = [], []
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label]
    if free:
        import vulnerability_model as VM
        reg_ids = list(_reg); E = VM._st(free + [_reg[i]["label"] for i in reg_ids]); Ef, Er = E[:len(free)], E[len(free):]
        learned_free = VM.predict(free)
        import mondo_index as MI
        links = MI.link(free)
    fi = 0
    for c in conditions:
        cid = c if c in _reg else _by_label.get(c.lower())
        if cid:
            ws.append(np.maximum(own_vec(cid), LEARNED_FRACTION * np.array([L[cid][a] for a in AXES]))); notes.append((c, f"registry: {_reg[cid]['label']}"))
        else:
            lv = np.array([learned_free[fi][a] for a in AXES]); sims = Er @ Ef[fi]; k = int(sims.argmax()); lk = links[fi]; rl = _reg[reg_ids[k]]["label"]
            if sims[k] >= REG_NEAR: own, how = own_vec(reg_ids[k]), f"free text; same as registry '{rl}' (cos {sims[k]:.2f})"
            elif lk["axes"]:
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in lk["axes"]]
                how = f"free text; MONDO '{lk['name']}' (sim {lk['sim']:.2f}) -> organs: {', '.join(lk['axes'])}"
            elif sims[k] >= MATCH_COS: own, how = own_vec(reg_ids[k]), f"free text; organs borrowed from registry '{rl}' (cos {sims[k]:.2f})"
            else: own, how = np.zeros(len(AXES)), "free text; learned vulnerability only"
            ws.append(np.maximum(own, LEARNED_FRACTION * lv)); fi += 1; notes.append((c, how))
    return np.maximum.reduce(ws), notes

def recommend(conditions):
    ids, names, T, wt = drug_table(); w, notes = patient_weights(conditions)
    risk = 100 * (T @ w) / w.sum() if w.sum() > 0 else np.zeros(len(ids)); order = np.argsort(-risk)
    rows = []
    for rank, i in enumerate(order, 1):
        contrib = T[i] * w; top = [k for k in np.argsort(-contrib)[:2] if contrib[k] > 0]
        why = ", ".join(f"{AXES[k]}{' [boxed warning]' if wt[ids[i]][1].get(AXES[k]) == 'boxed' else ' [warning]' if AXES[k] in wt[ids[i]][1] else ''}" for k in top)
        rows.append(dict(rank=rank, adc=names[i], id=ids[i], risk_pct=round(float(risk[i]), 1), drivers=why))
    return rows, {AXES[k]: round(float(w[k]), 2) for k in np.argsort(-w) if w[k] > 0}, notes

def list_conditions():
    print(f"{'ID':<30} {'이름':<46} 장기"); by = {}
    for r in _reg.values(): by.setdefault(r["organ_axes"].split(";")[0], []).append(r)
    for organ, rs in by.items():
        print(f"\n[{organ}]"); [print(f"  {r['id']:<28} {r['label']:<46} {r['organ_axes']}") for r in rs]

if __name__ == "__main__":
    if "--list" in sys.argv: list_conditions(); sys.exit(0)
    conds = sys.argv[1:] or ["interstitial_lung_disease"]
    rows, w, notes = recommend(conds)
    print("patient: " + "; ".join(f"{a} ({b})" for a, b in notes)); print("organ weights: " + ", ".join(f"{a} {v}" for a, v in w.items()) + "\n")
    print(f"{'위험도':>7}  {'ADC':<30} 주요 장기"); [print(f"{r['risk_pct']:6.1f}%  {r['adc'][:30]:<30} {r['drivers']}") for r in rows]
    lo = rows[-1]; print(f"\n가장 낮은 위험: {lo['adc']} ({lo['risk_pct']}%)")
