"""Stage-5 external check on real-world outcome reports: FDA Adverse Event Reporting System (FAERS) via openFDA.

What it can test: whether the organ evidence the recommender orders by (label boxed / section-5 warning on an organ) points at
the organs where each ADC is DISPROPORTIONATELY reported in post-marketing practice. What it cannot test: patient-specific
risk. FAERS has no comorbidity or lab fields and no denominator, so it says nothing about whether a CKD patient does worse on
drug A than drug B; that needs the patient-level cohort in docs/validation_plan.md (ml/validate_outcomes.py runs it).

Method (fixed before the first query):
  * reports per ADC from openFDA /drug/event, counted by MedDRA preferred term (top 500 PTs per drug, the maximum without an
    API key; rarer PTs of the large drugs are cut off, which lowers their mentions in rare organs);
  * PT -> organ axis with the project's own taxonomy (adctox.taxonomy + data/processed/pt_soc_dictionary.json);
    'constitutional' (death, disease progression, fatigue ...) and unmapped PTs are left out;
  * within-class reporting odds ratio: ADC d vs all other ADCs in the set, organ o vs every other organ, on PT mentions;
    signal = ROR lower 95% bound > 1 with >= 3 mentions. Comparing ADCs with ADCs damps the reporting differences between
    oncology and other drug classes, but not notoriety bias: a boxed warning attracts reports (stated with the result);
  * predictors per (ADC, organ) cell: label level (boxed 2, section-5 1, none 0; what the recommender uses), the label tables'
    grade >= 3 incidence (absolute %), and a shuffled control; AUROC against the FAERS signal, bootstrap over ADCs;
  * single-organ patients: for a patient vulnerable only in organ o the recommender orders ADCs by their label level on o;
    Spearman between that level and the FAERS log-ROR on o, per organ with variation in both.
Writes ml/results/faers_validation.json and caches raw API answers in ml_cache/faers/ (FAERS is public domain).
"""
import json, os, sys, time, urllib.parse, urllib.request
import numpy as np
sys.path[:0] = ["/home/hyeongchanahn/CONI/adctox/ml", "/home/hyeongchanahn/CONI/adctox/src"]
import drug_evidence as DE
from matcher import auroc
from adctox.taxonomy import Taxonomy

R = "/home/hyeongchanahn/CONI/adctox/"; CACHE = "/data/hyeongchanahn/adctox/ml_cache/faers/"; AXES = DE.AXES
API = "https://api.fda.gov/drug/event.json"


def fetch(generic):
    os.makedirs(CACHE, exist_ok=True); f = CACHE + generic.replace(" ", "_") + ".json"
    if os.path.exists(f): return json.load(open(f))
    q = f'patient.drug.openfda.generic_name:"{generic}"'; out = dict(generic=generic, retrieved_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    for key, extra in (("total", "&limit=1"), ("pts", "&count=patient.reaction.reactionmeddrapt.exact&limit=500")):
        url = f"{API}?search={urllib.parse.quote(q)}{extra}"
        for attempt in range(5):
            try: d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "adctox-research/1.0"}), timeout=60)); break
            except urllib.error.HTTPError as e:
                if e.code == 404: d = {}; break
                if e.code >= 500 and attempt < 4: time.sleep(2 + 2 * attempt); continue
                raise
        if key == "total": out["n_reports"] = d.get("meta", {}).get("results", {}).get("total", 0); out["last_updated"] = d.get("meta", {}).get("last_updated")
        else: out["pts"] = {r["term"]: r["count"] for r in d.get("results", [])}
        time.sleep(0.4)
    json.dump(out, open(f, "w"), indent=1); return out


def main():
    E = DE.evidence(); tax = Taxonomy(); tax.load_pt_dictionary(R + "data/processed/pt_soc_dictionary.json")
    raw = {adc: fetch(adc.replace("-", " ")) for adc in sorted(E)}
    used = [a for a in raw if raw[a]["n_reports"] >= 50]; skipped = {a: raw[a]["n_reports"] for a in raw if a not in used}
    M = np.zeros((len(used), len(AXES))); unmapped = {}
    for i, a in enumerate(used):
        for pt, n in raw[a]["pts"].items():
            ax, _ = tax.resolve_term_only(pt)
            if ax in AXES: M[i, AXES.index(ax)] += n
            else: unmapped[ax] = unmapped.get(ax, 0) + n
    tot_d = M.sum(1, keepdims=True); tot_o = M.sum(0, keepdims=True); T = M.sum()
    a_ = M; b_ = tot_d - M; c_ = tot_o - M; d_ = T - tot_d - tot_o + M
    ror = (a_ + .5) * (d_ + .5) / ((b_ + .5) * (c_ + .5)); se = np.sqrt(1 / (a_ + .5) + 1 / (b_ + .5) + 1 / (c_ + .5) + 1 / (d_ + .5))
    lo = np.exp(np.log(ror) - 1.96 * se); signal = (lo > 1) & (M >= 3)
    lvl = np.array([[{"boxed": 2, "W&P": 1}.get(E[a]["organs"][o]["level"], 0) for o in AXES] for a in used], float)
    inc = np.array([[(E[a]["organs"][o]["inc"] or {}).get("pct", np.nan) if E[a]["organs"][o]["inc_status"] == "reported" else (0.0 if E[a]["organs"][o]["inc_status"] == "not reported" else np.nan) for o in AXES] for a in used])
    rng = np.random.default_rng(0); res = dict(source="openFDA /drug/event", last_updated=raw[used[0]].get("last_updated"), adcs=used, skipped_lt50_reports=skipped,
                                              n_reports={a: raw[a]["n_reports"] for a in used}, unmapped_mentions=unmapped, n_cells=int(signal.size), n_signals=int(signal.sum()))
    def boot_auc(score):
        ok = ~np.isnan(score); pt = auroc(score[ok], signal[ok]); bs = []
        for _ in range(2000):
            j = rng.integers(0, len(used), len(used)); s, y = score[j].ravel(), signal[j].ravel(); k = ~np.isnan(s)
            if y[k].any() and (~y[k]).any(): bs.append(auroc(s[k], y[k]))
        return dict(auroc=float(pt), ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], n=int(ok.sum()))
    res["label_level"] = boot_auc(lvl); res["incidence_pct"] = boot_auc(inc)
    sh = np.array([rng.permutation(lvl.ravel()).reshape(lvl.shape) for _ in range(200)])
    res["shuffled_level_mean_auroc"] = float(np.mean([auroc(x.ravel(), signal.ravel()) for x in sh]))
    from scipy.stats import spearmanr
    per = {}
    for k, o in enumerate(AXES):
        if len(set(lvl[:, k])) > 1 and M[:, k].sum() >= 20:
            r, p = spearmanr(lvl[:, k], np.log(ror[:, k])); per[o] = dict(spearman=float(r), p=float(p), n_adc=len(used), levels=lvl[:, k].tolist())
    res["single_organ_patients"] = per; res["single_organ_mean_spearman"] = float(np.mean([v["spearman"] for v in per.values()])) if per else None
    res["cells"] = [dict(adc=a, organ=o, mentions=int(M[i, k]), ror=round(float(ror[i, k]), 3), ror_lo=round(float(lo[i, k]), 3), signal=bool(signal[i, k]), label=int(lvl[i, k]))
                    for i, a in enumerate(used) for k, o in enumerate(AXES)]
    json.dump(res, open(R + "ml/results/faers_validation.json", "w"), indent=1)
    print(f"FAERS (openFDA, data to {res['last_updated']}): {len(used)} ADCs, skipped {skipped}; {res['n_signals']} signals in {res['n_cells']} ADC x organ cells")
    for k in ("label_level", "incidence_pct"):
        x = res[k]; print(f"  AUROC for FAERS signal  {k:14s} {x['auroc']:.3f} [{x['ci'][0]:.3f}, {x['ci'][1]:.3f}]  (n={x['n']})")
    print(f"  shuffled label level (mean of 200)     {res['shuffled_level_mean_auroc']:.3f}")
    print(f"  single-organ patients: Spearman(label level on o, log ROR on o), mean over {len(per)} organs = {res['single_organ_mean_spearman']:.3f}")
    for o, v in per.items(): print(f"     {o:20s} rho {v['spearman']:+.2f}  (p {v['p']:.3f})")


if __name__ == "__main__":
    main()
