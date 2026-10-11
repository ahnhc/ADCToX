"""Does swapping the hand-set organ severities for the learned ones change what the product proposes?

Runs the same 24 targets x 8 profiles sweep the project already uses (scripts/rank_resolution.py),
twice: once with the registry's curated severities, once with severities learned from FinnGen
(ml/learned_vulnerability.py). `src/` is not edited -- `resolve_comorbidities` is replaced in memory.

Reports how often the shown design set and the lead design differ, and how the two severity
vectors relate. It does not claim the learned one is *right*: that is what the held-out
evaluation of Task A is for. This only shows the plumbing connects and the consequence is real.
Run with the project's .venv (no torch needed).
"""
import json, sys, importlib
from pathlib import Path
import numpy as np, yaml

ROOT = Path("/home/hyeongchanahn/CONI/adctox"); sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import adctox.pipeline as pl
from adctox.model.predict import Posterior
from rank_resolution import PROFILES

AT_RISK_SEVERITY = 0.5         # learned severity >= 0.5 (>= 1.5 SD above a typical prior) counts as "at risk" -> serious table
L = json.load(open(ROOT / "ml/results/learned_vulnerability.json"))["severity"]
orig = pl.resolve_comorbidities

def learned_resolve(condition_ids):
    base = orig(condition_ids)                         # keeps labels / provenance fields
    sev: dict[str, float] = {}
    for cid in condition_ids:
        for a, v in L[cid].items():
            sev[a] = max(sev.get(a, 0.0), v)
    return pl.ComorbidityResolution(sev, {a for a, v in sev.items() if v >= AT_RISK_SEVERITY}, base.per_condition)

post = Posterior.load(ROOT / "artifacts/posterior_other.npz"); sp = ROOT / "artifacts/posterior_serious.npz"; serious = Posterior.load(sp) if sp.exists() else None
doc = yaml.safe_load((ROOT / "conf/adc_registry.yaml").read_text()); agents = doc["agents"] if "agents" in doc else doc
targets = sorted({a["target"] for a in (agents.values() if isinstance(agents, dict) else agents) if a.get("target")})

def run(resolver):
    pl.resolve_comorbidities = resolver; out = {}
    for t in targets:
        for lab, conds in PROFILES.items():
            r = pl.propose(target_antigen=t, condition_ids=conds, posterior=post, top_k=6, serious_posterior=serious)
            out[(t, lab)] = [(c["design"]["payload"], c["design"]["linker"], c["design"]["dar"]) for c in r["candidates"]]
    pl.resolve_comorbidities = orig; return out

cur, lrn = run(orig), run(learned_resolve)
rows = []; jac = []; head_diff = 0; n = 0
for k in cur:
    a, b = set(map(tuple, cur[k])), set(map(tuple, lrn[k]))
    if not a and not b: continue
    n += 1; jac.append(len(a & b) / max(1, len(a | b))); head_diff += int((cur[k][:1] != lrn[k][:1]))
    rows.append(dict(target=k[0], profile=k[1], jaccard=jac[-1], same_head=cur[k][:1] == lrn[k][:1]))
by_prof = {}
for r in rows: by_prof.setdefault(r["profile"], []).append(r["jaccard"])
# responsiveness: how often does the profile change the shown set relative to "no comorbidity"?
def responsive(res):
    ch = tot = 0
    for t in targets:
        base = set(map(tuple, res[(t, "none")]))
        for lab in PROFILES:
            if lab == "none": continue
            tot += 1; ch += int(set(map(tuple, res[(t, lab)])) != base)
    return ch / tot
# agreement between the two severity vectors on the registry itself
import csv
reg = {r["id"]: r for r in csv.DictReader(open(ROOT / "conf/comorbidity_registry.csv"))}
agree = []
for cid, sv in L.items():
    cur_axes = set(reg[cid]["organ_axes"].split(";")); top = max(sv, key=sv.get)
    agree.append(int(top in cur_axes))
summary = dict(queries=n, mean_jaccard_shown_set=float(np.mean(jac)), share_queries_identical_set=float(np.mean(np.array(jac) == 1.0)),
               share_queries_different_lead=head_diff / n, profile_changes_set_curated=responsive(cur), profile_changes_set_learned=responsive(lrn),
               mean_jaccard_by_profile={k: float(np.mean(v)) for k, v in by_prof.items()},
               learned_top_axis_is_a_curated_axis=float(np.mean(agree)), n_conditions=len(agree), at_risk_threshold=AT_RISK_SEVERITY)
json.dump(dict(summary=summary, rows=rows), open(ROOT / "ml/results/pipeline_comparison.json", "w"), indent=1, default=str)
print(json.dumps(summary, indent=1))
