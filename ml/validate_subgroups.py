"""Subgroup-incidence validation (pre-registered in ml/docs/validation_plan.md section 0c): where a public document reports,
among patients treated with one ADC, the incidence of an adverse outcome in a stratum the tool reads (CLcr band, hepatic band,
UGT1A1 genotype, LVEF, a registry comorbidity) against a reference stratum, does the tool's order key rise exactly where the
reported incidence rises?

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/validate_subgroups.py [conf/subgroup_evidence.yaml] [--out ml/results/subgroup_validation.json]

Evidence (conf/subgroup_evidence.yaml) is one record per (source, ADC, exposed stratum, outcome) with n and events or %, a
verbatim quote and the saved source text. Each stratum also carries `patient`: the representative inputs of section 0c
(CLcr 100/75/45/20, bilirubin x ULN 0.8/1.2/2.2/4, a registry condition id, or the UGT1A1 flag).

Steps, all fixed before the numbers were seen:
  1. quote check: the quote must occur in the saved text (whitespace collapsed) and every n / events / % must occur in the quote;
     records that fail are dropped and listed.
  2. one outcome per contrast: lowest outcome_rank (1 any Grade>=3 AE, 2 serious AE, 3 a specific AE); among equal ranks the
     outcome with the most events (most information). Contrasts reported by several sources for the same ADC, characteristic and
     exposed patient are kept once: lowest rank, then largest n.
  3. log RR with 95% CI from counts (0.5 added to every cell when a cell is 0); a reported ratio with CI only when the
     source gives no counts for both strata.
  4. flag = the tool's order key for the ADC (worst restriction tier, settled tier, B, Wn) is larger for the exposed patient.
  5. DerSimonian-Laird random-effects meta-regression of log RR on flag; the decision statistic is the flag coefficient (the
     difference in pooled log RR, flagged - not flagged): the tool's flags match real excess incidence if its 95% CI is above 0.
     Pooled estimates are not given for a group with fewer than 5 contrasts. Reported for all contrasts, for post_approval only,
     without OCR-read sources, and by characteristic (descriptive).
  Dropped before step 2: treatment actions (dose reduction, discontinuation ...) and, for hepatic strata, liver-test outcomes.
"""
import json, math, re, sys
import numpy as np, yaml
sys.path[:0] = ["/home/hyeongchanahn/CONI/adctox/ml", "/home/hyeongchanahn/CONI/adctox/src"]

R = "/home/hyeongchanahn/CONI/adctox/"
LABS = ("crcl", "bili", "ast", "alt", "lvef", "child_pugh", "ugt1a1_28_homozygous")
MIN_GROUP = 5
ACTION = re.compile(r"leading to|dose adjustment|discontinu|reduction|withdraw|delay|interruption", re.I)   # treatment actions, not adverse events
LIVER_LAB = re.compile(r"\bALT\b|\bAST\b|\bALP\b|GGT|bilirubin|aminotransferase", re.I)             # part of the definition of a hepatic stratum


def _collapse(s): return re.sub(r"\s+", " ", s).strip()


def _num_in(x, quote):
    """the stated number appears in the quote as a token (57, 57.0, 57%, (57) ...)."""
    if x is None or x == "": return True
    v = float(x); forms = {f"{v:g}", f"{v:.1f}", f"{v:.2f}", f"{v:.3f}", str(x)}       # YAML drops trailing zeros (1.90 -> 1.9)
    q = re.sub(r"(?<=\d),(?=\d{3}\b)", "", quote)                                       # thousands separators (1,581)
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", q) for f in forms)


N_IN_SOURCE = False       # post hoc (added after the first run): accept an n printed anywhere in the source (table headers), not only in the quote


def check(rec):
    """-> None if the record passes, else the reason."""
    try: text = _collapse(open(rec["local_text"], errors="replace").read())
    except OSError: return "source text missing"
    q = _collapse(rec.get("quote") or "")
    if not q or q not in text: return "quote not found in source text"
    if not _counts(rec):
        if not rec.get("hr"): return "neither counts nor a ratio"
        if not all(_num_in(rec["hr"].get(k), q) for k in ("value", "lo", "hi")): return "ratio not in quote"
        return None
    for side in ("exposed", "reference"):
        s = rec[side]
        if not s.get("n"): return f"{side} n missing"
        if s.get("events") in (None, "") and s.get("pct") in (None, ""): return f"{side} events/% missing"
        for k in ("n", "events", "pct"):
            if not _num_in(s.get(k), q) and not (k == "n" and N_IN_SOURCE and _num_in(s.get(k), text)): return f"{side} {k} not in quote"
    return None


def _counts(rec):
    """both strata have n and events or %: counts are used, a reported ratio only when they are missing."""
    return all(rec.get(s, {}).get("n") and (rec[s].get("events") not in (None, "") or rec[s].get("pct") not in (None, "")) for s in ("exposed", "reference"))


def _events(s): return float(s["events"]) if s.get("events") not in (None, "") else round(float(s["pct"]) / 100 * float(s["n"]))


def log_rr(rec):
    """-> (log RR, variance)."""
    if not _counts(rec):
        h = rec["hr"]; return math.log(h["value"]), ((math.log(h["hi"]) - math.log(h["lo"])) / (2 * 1.959964)) ** 2
    a, n1 = _events(rec["exposed"]), float(rec["exposed"]["n"]); c, n0 = _events(rec["reference"]), float(rec["reference"]["n"])
    if 0 in (a, c, n1 - a, n0 - c): a, c, n1, n0 = a + .5, c + .5, n1 + 1, n0 + 1
    return math.log((a / n1) / (c / n0)), 1 / a - 1 / n1 + 1 / c - 1 / n0


def choose(recs):
    """step 2: one record per contrast, one contrast per (ADC, characteristic, exposed patient)."""
    tot = lambda r: (_events(r["exposed"]) + _events(r["reference"])) if _counts(r) else 0
    by = {}
    for r in recs: by.setdefault((r["source_url"], r["adc"], r["exposed"]["label"], r["reference"]["label"]), []).append(r)
    one = [min(g, key=lambda r: (r["outcome_rank"], -tot(r))) for g in by.values()]
    pk = lambda r: (r["adc"], r["characteristic"], json.dumps(r["exposed"]["patient"], sort_keys=True))
    by = {}
    for r in one: by.setdefault(pk(r), []).append(r)
    n = lambda r: float(r["exposed"].get("n") or 0) + float(r["reference"].get("n") or 0)
    return [min(g, key=lambda r: (r["outcome_rank"], -n(r))) for g in by.values()]


def tool_key(adc, patient):
    import recommend as RC
    p = dict(patient); conds = p.pop("conditions", []); labs = {k: p[k] for k in LABS if k in p}
    x = {r["adc"]: r for r in RC.recommend(list(conds), labs)[0]}[adc]
    return (x["tier"], x["verdict"].worst_known, x["B"], x["Wn"])


def dl_metareg(y, v, X):
    """DerSimonian-Laird (method of moments) random-effects meta-regression -> (beta, se, tau2)."""
    y, v, X = np.asarray(y, float), np.asarray(v, float), np.asarray(X, float); k, p = X.shape
    W = np.diag(1 / v); A = np.linalg.inv(X.T @ W @ X); b = A @ X.T @ W @ y; Q = float((y - X @ b) @ W @ (y - X @ b))
    denom = np.trace(W) - np.trace(A @ X.T @ W @ W @ X); tau2 = max(0.0, (Q - (k - p)) / denom) if denom > 0 else 0.0
    Ws = np.diag(1 / (v + tau2)); As = np.linalg.inv(X.T @ Ws @ X); bs = As @ X.T @ Ws @ y
    return bs, np.sqrt(np.diag(As)), tau2


def pooled(c):
    if len(c) < MIN_GROUP: return None
    b, se, t = dl_metareg([x["log_rr"] for x in c], [x["var"] for x in c], np.ones((len(c), 1)))
    return dict(k=len(c), rr=math.exp(b[0]), ci=[math.exp(b[0] - 1.96 * se[0]), math.exp(b[0] + 1.96 * se[0])], tau2=t)


def analyse(contrasts):
    f, nf = [c for c in contrasts if c["flag"]], [c for c in contrasts if not c["flag"]]
    out = dict(k=len(contrasts), flagged=pooled(f), not_flagged=pooled(nf),
               sign_agreement=(sum((c["log_rr"] > 0) == c["flag"] for c in contrasts) / len(contrasts)) if contrasts else None)
    if len(f) >= MIN_GROUP and len(nf) >= MIN_GROUP:
        X = np.column_stack([np.ones(len(contrasts)), [float(c["flag"]) for c in contrasts]])
        b, se, t = dl_metareg([c["log_rr"] for c in contrasts], [c["var"] for c in contrasts], X)
        lo, hi = b[1] - 1.96 * se[1], b[1] + 1.96 * se[1]
        out["flag_effect"] = dict(ratio_of_rr=math.exp(b[1]), ci=[math.exp(lo), math.exp(hi)], tau2=t, flags_match_excess=bool(lo > 0))
    else: out["flag_effect"] = None
    return out


def main(paths, out=None):
    recs = [r for p in paths for r in (yaml.safe_load(open(p)) or {}).get("evidence", [])]
    dropped = []; ok = []
    for r in recs:
        why = ("treatment action, not an adverse event" if ACTION.search(r.get("outcome", "")) else
               "liver test outcome defines the hepatic stratum" if r.get("characteristic") == "hepatic" and LIVER_LAB.search(r.get("outcome", "")) else None)
        why = why or ("post-baseline characteristic" if r.get("characteristic") == "post_baseline" else ("no representative patient" if not (r.get("exposed", {}).get("patient") is not None and r.get("reference", {}).get("patient") is not None) else check(r)))
        (dropped.append(dict(id=r.get("id"), reason=why)) if why else ok.append(r))
    contrasts = []
    for r in choose(ok):
        ke, kr = tool_key(r["adc"], r["exposed"]["patient"]), tool_key(r["adc"], r["reference"]["patient"]); lr, v = log_rr(r)
        contrasts.append(dict(id=r["id"], adc=r["adc"], characteristic=r["characteristic"], exposed=r["exposed"]["label"], reference=r["reference"]["label"],
                              outcome=r["outcome"], outcome_rank=r["outcome_rank"], basis=r["basis"], source=r["source_url"], ocr=bool(r.get("ocr")),
                              rr=math.exp(lr), ci=[math.exp(lr - 1.96 * math.sqrt(v)), math.exp(lr + 1.96 * math.sqrt(v))], log_rr=lr, var=v,
                              key_exposed=[float(x) for x in ke], key_reference=[float(x) for x in kr], flag=bool(ke > kr)))
    res = dict(records=len(recs), passed=len(ok), dropped=dropped, contrasts=contrasts, all=analyse(contrasts),
               post_approval=analyse([c for c in contrasts if c["basis"] == "post_approval"]),
               no_ocr=analyse([c for c in contrasts if not c["ocr"]]),
               by_characteristic={ch: analyse([c for c in contrasts if c["characteristic"] == ch]) for ch in sorted({c["characteristic"] for c in contrasts})},
               note="Tool keys are (worst restriction tier, settled tier, B, Wn) from ml/recommend.py. label_basis contrasts are not independent of the label rules.")
    print(f"{len(recs)} records, {len(ok)} pass the quote check, {len(contrasts)} contrasts")
    for c in sorted(contrasts, key=lambda c: (c["adc"], c["characteristic"])):
        print(f"  {'FLAG' if c['flag'] else '    '} {c['adc'][:22]:22s} {c['exposed'][:38]:38s} vs {c['reference'][:24]:24s} {c['outcome'][:28]:28s} RR {c['rr']:.2f} [{c['ci'][0]:.2f}, {c['ci'][1]:.2f}] {c['basis']}")
    for name, a in [("all", res["all"]), ("post_approval", res["post_approval"]), ("no_ocr", res["no_ocr"])] + list(res["by_characteristic"].items()):
        print(f"{name}: k={a['k']}, sign agreement {a['sign_agreement']}")
        for g in ("flagged", "not_flagged"):
            if a[g]: print(f"   {g}: pooled RR {a[g]['rr']:.2f} [{a[g]['ci'][0]:.2f}, {a[g]['ci'][1]:.2f}] (k={a[g]['k']})")
        if a["flag_effect"]: e = a["flag_effect"]; print(f"   flagged / not flagged: {e['ratio_of_rr']:.2f} [{e['ci'][0]:.2f}, {e['ci'][1]:.2f}] -> {'flags match excess' if e['flags_match_excess'] else 'not shown'}")
    if out: json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--n-in-source" in a: N_IN_SOURCE = True; a.remove("--n-in-source")
    out = a[a.index("--out") + 1] if "--out" in a else None
    paths = [x for i, x in enumerate(a) if x != "--out" and (i == 0 or a[i - 1] != "--out")] or [R + "conf/subgroup_evidence.yaml"]
    main(paths, out)
