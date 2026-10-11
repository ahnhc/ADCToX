"""Print every number the ML write-up quotes, from the JSON files in ml/results, so nothing is typed by hand.
Run:  /data/hyeongchanahn/envs/adctox/bin/python -I ml/summarize.py
"""
import json, os
R = "/home/hyeongchanahn/CONI/adctox/ml/results/"
J = lambda n: json.load(open(R + n)) if os.path.exists(R + n) else None
a, tf, rd, kn = J("task_a_sapbert.json"), J("task_a_tfidf.json"), J("task_a_random.json"), J("knn_baseline.json")
REG = {"pair": "known disease, known outcome, unseen pair", "prior": "unseen comorbidity", "cluster": "unseen ICD family (strictest)"}
print("TASK A  R2 / organ-ranking gap over the lookup table [95% CI, bootstrapped over ICD families]\n")
for reg, desc in REG.items():
    print(f"-- {reg}: {desc}")
    rows = [("lookup table", a[reg]["lookup"], None)]
    if kn: rows.append(("kNN on SapBERT (no learning)", kn[reg]["knn"], kn[reg]["knn"].get("organ_rho_vs_lookup")))
    for name, src in [("LightGBM + SapBERT", a), ("MLP + SapBERT", a), ("MLP + TF-IDF", tf), ("MLP + random IDs", rd)]:
        key = "lightgbm" if "Light" in name else "mlp"
        if src and reg in src and key in src[reg]: rows.append((name, src[reg][key], src[reg][key].get("organ_rho_vs_lookup")))
    for name, s, g in rows:
        gap = f"   organ-gap {g['delta']:+.3f} [{g['lo']:+.3f}, {g['hi']:+.3f}]" if g else ""
        print(f"   {name:30s} R2 {s['r2']:+.3f}  Spearman {s['spearman']:.3f}  organ-rho {s['organ_rho']:.3f}  top3 {s['organ_top3']:.3f}{gap}")
print("\nTASK D  (ADC structure -> AE incidence, new ADC / new payload)")
d, d2 = J("task_d.json"), J("task_d2.json")
for reg in ["adc", "payload"]:
    if d and reg in d:
        print(f"-- {reg}: lookup R2 {d[reg]['lookup']['r2']:+.3f} | no-structure MLP {d[reg]['mlp:no_structure']['r2']:+.3f}")
        for k, v in d[reg].items():
            if "vs_no_structure" in v: g = v["vs_no_structure"]; print(f"   {k:26s} structure adds {g['delta_r2']:+.3f} [{g['lo']:+.3f}, {g['hi']:+.3f}]")
    if d2 and reg in d2:
        for k, v in d2[reg].items():
            if "vs_p0" in v: g = v["vs_p0"]; print(f"   ridge correction {k:20s} adds {g['delta_r2']:+.4f} [{g['lo']:+.4f}, {g['hi']:+.4f}]")
v = J("validate_registry.json")
if v:
    print("\nREGISTRY CHECK (41 curated conditions, AUROC of learned organ vulnerability vs curated organs; 0.5 = chance)")
    for tau, dd in v.items():
        s = dd["summary"]; ban = sorted(r["n_banned"] for r in dd["per_condition"])[20]
        print(f"   {tau}: banned-per-condition median {ban:>2} | " + " | ".join(f"{k} {s[k]['mean_auroc']:.3f} [{s[k]['lo']:.2f},{s[k]['hi']:.2f}]" for k in ["mlp", "knn", "raw"])
              + f" | mlp-knn {s['mlp_minus_knn']['delta']:+.3f} [{s['mlp_minus_knn']['lo']:+.2f},{s['mlp_minus_knn']['hi']:+.2f}] | top3 {s['top3_hits_curated']:.2f}")
    print("   chance for 'a curated organ is in the top 3': 0.25")
pc = J("pipeline_comparison.json")
if pc: print("\nPIPELINE\n  ", json.dumps(pc["summary"], indent=1))
