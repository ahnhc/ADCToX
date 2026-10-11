"""Patient comorbidities (and, optionally, lab values) in; every approved ADC out, ordered by what its label says about THIS patient.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/recommend.py ckd_stage_3 heart_failure --crcl 45 --lvef 48
    lab-report values: --lab creatinine=1.3 --lab age=70 --lab sex=F --lab weight=55 --lab bilirubin=2.0 --lab ast=50 ... (ml/labs.py FIELDS)
    or already in label form: --crcl --bili --ast --alt (x ULN) --child-pugh A|B|C --lvef --ugt1a1-28-homozygous

Order, most favourable first (a lexicographic key, so nothing below can buy back anything above):
  1. label use restriction for this patient (ml/restrictions.py, conf/label_restrictions.yaml), worst case over the lab
     values that were not entered: contraindicated > avoid > insufficient data = no label statement > monitor > none;
     within a tier, a restriction that holds whatever the missing values are ranks behind one that only might.
  2. boxed warnings on the patient's organs, compared priority level by level: the organs of the level-1 condition(s) first,
     then level 2, ... (a count per level, so one hit on a higher level outweighs any number on lower ones).
  3. section-5 warnings (no boxed one) on the patient's organs, level by level in the same way.
  Levels: with two or more conditions on different organs the wizard asks the user to order them (--priority 2,1 on the
  command line, aligned with the conditions); by default the curated severity order, equal severities sharing a level.
  B / Wn (sums of s_o) are still returned: they compare different patients (ml/validate_outcomes.py, validate_subgroups.py).
  s_o = the patient's vulnerability of organ o, 0-1: the curated severity of the conditions whose own organ it is
  (max over conditions). B and Wn can only grow when any s_o grows, so a more vulnerable patient never gets a lower
  concern for a drug that warns on that organ. There is no weighted mean and no per-patient min-max: the first version
  (a weighted mean rescaled 0-100) could fall when an organ became more vulnerable and always gave its best drug 0%.
Not in the order, shown for reading: grade >= 3 incidence on the patient's organs (absolute %, with 'no data' / 'not
reported' written out, never read as 0), and boxed warnings on organs the patient is not vulnerable in.

The learned cross-organ vulnerability (FinnGen model, ml/vulnerability_model.py) is OFF by default: in the only non-circular
test it did not improve matching (+0.033 [-0.018, +0.087], ml/README.md), and comorbidity -> later disease is a different
question from ADC toxicity given the comorbidity. --learned F turns it on for every condition as s_o = max(own, F * learned).
When a typed condition maps to no organ at all (not in the registry, no MONDO organ, no similar registry condition), the
wizard says so and offers the learned estimate for THAT condition only (--learned-fallback F on the command line); conditions
that were understood are never changed by it, and the patient line marks the estimate as not validated.

This orders label evidence for one patient. It is not a probability of an adverse event and has not been validated against
patient outcomes (ml/docs/validation_plan.md).
"""
import csv, json, os, re, sys, warnings
for _k, _v in (("HF_HUB_DISABLE_PROGRESS_BARS", "1"), ("TRANSFORMERS_VERBOSITY", "error"), ("TQDM_DISABLE", "1"), ("HF_HUB_VERBOSITY", "error")):
    os.environ.setdefault(_k, _v)     # model loading bars and hub warnings are noise in a clinical table
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
import drug_evidence as DE, restrictions as RS
AXES = DE.AXES; R = RS.R
LEARNED_FRACTION = 0.0      # off by default; see the module docstring
FALLBACK = {}               # condition text -> learned fraction, only for conditions that map to no organ (asked in the wizard)
PRIORITY = {}               # condition text -> level the user set (1 = avoid its organs' toxicity first); default = severity order
REG_NEAR = 0.80             # a free-text condition is 'the same as' a registry condition at this BioLORD cosine -> its curated organs
MONDO_SEVERITY = 0.80       # organs read off the MONDO hierarchy have no curated severity; one fixed value, not fitted
MATCH_COS = 0.60            # last resort: borrow the organs of a loosely similar registry condition
CONTEXT = {"concomitant_bleomycin": "Concomitant bleomycin (co-medication, no organ)"}     # inputs that are not diseases but a label rule names
EN = {"haematologic": "Haematologic", "hepatic": "Hepatic", "cardiovascular": "Cardiovascular", "pulmonary": "Pulmonary", "renal": "Renal",
      "gastrointestinal": "GI", "neurologic": "Neurologic", "ocular": "Ocular", "dermatologic": "Dermatologic", "metabolic_endocrine": "Metabolic",
      "musculoskeletal": "Musculoskeletal", "infectious_immune": "Immune", "otologic": "Otologic"}

_reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}
_by_label = {r["label"].lower(): r["id"] for r in _reg.values()}


class _Loading:
    """one-line spinner while the text encoders load (terminal only); replaces the libraries' progress bars."""
    def __init__(self, text, done): self.text, self.done = text, done
    def __enter__(self):
        import threading, time
        self.t0 = time.time(); self.on = sys.stderr.isatty(); self.stop = threading.Event()
        def spin():
            for ch in __import__("itertools").cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
                if self.stop.wait(0.1): break
                sys.stderr.write(f"\r  {ch} {self.text}"); sys.stderr.flush()
        if self.on: self.th = threading.Thread(target=spin, daemon=True); self.th.start()
        return self
    def __exit__(self, *exc):
        import time
        if self.on:
            self.stop.set(); self.th.join(); sys.stderr.write(f"\r\033[K  ✓ {self.done} ({time.time() - self.t0:.1f}s)\n"); sys.stderr.flush()


def own_vec(cid):
    v = np.zeros(len(AXES))
    for a in _reg[cid]["organ_axes"].split(";"):
        if a in AXES: v[AXES.index(a)] = float(_reg[cid]["severity"])
    return v


_FREE = {}                  # free-text conditions -> (embeddings, registry embeddings, MONDO links), per process


def resolve(conditions):
    """-> (s over AXES, own-organ set, registry ids present, [(input, how it was read)], [(input, its organs, its value)])"""
    ws, notes, ids, own_axes, pc = [np.zeros(len(AXES))], [], set(), set(), []
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and c not in CONTEXT]
    if free:
        key = tuple(free)
        if key not in _FREE:
            with _Loading("Loading weights · 질환 해석 모델 (BioLORD · MONDO)", "질환 해석 모델 준비 완료"):
                import vulnerability_model as VM, mondo_index as MI
                E = VM._st(free + [_reg[i]["label"] for i in _reg]); _FREE[key] = (E[:len(free)], E[len(free):], MI.link(free))
        import vulnerability_model as VM
        reg_ids = list(_reg); Ef, Er, links = _FREE[key]; learned_free = VM.predict(free) if LEARNED_FRACTION > 0 or FALLBACK else None
    L = json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"] if LEARNED_FRACTION > 0 else None
    fi = 0
    for c in conditions:
        if c in CONTEXT: ids.add(c); notes.append((c, CONTEXT[c])); continue
        cid = c if c in _reg else _by_label.get(c.lower())
        if cid:
            own, how = own_vec(cid), f"registry: {_reg[cid]['label']}"; ids.add(cid); lv = np.array([L[cid][a] for a in AXES]) if L else None
        else:
            sims = Er @ Ef[fi]; k = int(sims.argmax()); lk = links[fi]; rl = _reg[reg_ids[k]]["label"]
            lv = np.array([learned_free[fi][a] for a in AXES]) if learned_free else None
            if sims[k] >= REG_NEAR: own, how = own_vec(reg_ids[k]), f"free text; same as registry '{rl}' (cos {sims[k]:.2f})"; ids.add(reg_ids[k])
            elif lk["axes"]:
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in lk["axes"]]
                how = f"free text; MONDO '{lk['name']}' (sim {lk['sim']:.2f}) -> organs: {', '.join(lk['axes'])}"
            elif sims[k] >= MATCH_COS: own, how = own_vec(reg_ids[k]), f"free text; organs borrowed from registry '{rl}' (cos {sims[k]:.2f})"
            else:
                own, how = np.zeros(len(AXES)), "free text; not understood (no organ)"
                if FALLBACK.get(c) and lv is not None:
                    f = max(FALLBACK[c], LEARNED_FRACTION); top = [AXES[k] for k in np.argsort(-lv)[:3] if f * lv[k] >= 0.01]
                    ws.append(f * lv); how += f"; FinnGen learned estimate x{f:g} used (not validated): {', '.join(EN[a] for a in top) or 'no organ'}"
                    if top: pc.append((c, set(top), float(f * lv.max())))
            fi += 1
        own_axes |= {AXES[k] for k in np.where(own > 0)[0]}
        if own.max() > 0: pc.append((c, {AXES[k] for k in np.where(own > 0)[0]}, float(own.max())))
        ws.append(np.maximum(own, LEARNED_FRACTION * lv) if lv is not None and LEARNED_FRACTION > 0 else own); notes.append((c, how))
    return np.maximum.reduce(ws), own_axes, ids, notes, pc


def default_levels(pc):
    """condition -> priority level (1 = avoid first): the registry severity order, equal severities share a level."""
    vals = sorted({round(v, 3) for _, _, v in pc}, reverse=True)
    return {c: vals.index(round(v, 3)) + 1 for c, _, v in pc}


def priority(pc):
    """-> {condition: level}, from PRIORITY (set in the wizard or by --priority) over the defaults, renumbered 1, 2, 3 ..."""
    lv = {**default_levels(pc), **{c: v for c, v in PRIORITY.items() if c in {x for x, _, _ in pc}}}
    d = {v: k for k, v in enumerate(sorted(set(lv.values())), 1)}
    return {c: d[v] for c, v in lv.items()}


def unresolved(conditions):
    """typed conditions that map to no organ (what the wizard asks about); learned estimates play no part in this."""
    global LEARNED_FRACTION, FALLBACK
    keep = LEARNED_FRACTION, FALLBACK; LEARNED_FRACTION, FALLBACK = 0.0, {}
    try: return [c for c, how in resolve(conditions)[3] if how.startswith("free text; not understood")]
    finally: LEARNED_FRACTION, FALLBACK = keep


def _lab_organs(raw, s, own_axes, notes, pc):
    """abnormal lab values mark their organ (ml/labs.py FLAGS), in place; -> the restriction inputs derived from raw."""
    import labs as LB
    lab, flags, lnotes = LB.derive(raw); by = {}
    for organ, why in flags: by.setdefault(organ, []).append(why.split(" (")[0])
    for organ, whys in by.items():
        name = "Lab: " + ", ".join(whys); k = AXES.index(organ)
        s[k] = max(s[k], MONDO_SEVERITY); own_axes.add(organ); pc.append((name, {organ}, MONDO_SEVERITY)); notes.append((name, f"lab value -> organ: {organ}"))
    notes += [("Lab", n) for n in lnotes]
    return lab


def patient_conditions(conditions, raw=None):
    """[(condition or lab flag, organs, value)] as the priority step sees them."""
    s, own_axes, ids, notes, pc = resolve(conditions)
    if raw: _lab_organs(raw, s.copy(), set(own_axes), [], pc)
    return pc


def recommend(conditions, labs=None, raw=None):
    """-> rows (ordered), s {axis: value}, notes, checks. labs: restriction inputs as the rules read them (x ULN, CLcr);
    raw: lab-report values (ml/labs.py FIELDS), converted here; an abnormal value also marks its organ."""
    import labs as LB
    labs = dict(labs or {}); s, own_axes, ids, notes, pc = resolve(conditions); E = DE.evidence(); adcs = sorted(E)
    if raw:
        labs = {**_lab_organs(raw, s, own_axes, notes, pc), **labs}
        conditions = list(conditions) + [c for c, _, _ in pc if c.startswith("Lab: ")]
    lv = priority(pc); nlev = max(lv.values(), default=0); org_lv = {}
    for c, orgs, _ in pc:
        for a in orgs: org_lv[a] = min(org_lv.get(a, nlev), lv[c])
    for k, a in enumerate(AXES):                       # organs only a learned estimate put there come after every listed condition
        if s[k] > 0 and a not in org_lv: org_lv[a] = nlev + 1
    L = max(org_lv.values(), default=0)
    per_level = lambda organs: tuple(sum(org_lv[a] == k for a in organs) for k in range(1, L + 1))
    prio = sorted(((lv[c], c, sorted(orgs, key=AXES.index)) for c, orgs, _ in pc), key=lambda x: (x[0], conditions.index(x[1])))
    p = RS.Patient(conditions=ids, organs=own_axes, **labs); V = RS.judge(p, adcs); rows = []
    for adc in adcs:
        e = E[adc]; org = e["organs"]; v = V[adc]
        boxed = [a for a in AXES if s[AXES.index(a)] > 0 and org[a]["level"] == "boxed"]
        warn = [a for a in AXES if s[AXES.index(a)] > 0 and org[a]["level"] == "W&P"]
        B = sum(s[AXES.index(a)] for a in boxed); Wn = sum(s[AXES.index(a)] for a in warn)
        elsewhere = [a for a in AXES if s[AXES.index(a)] == 0 and org[a]["level"] == "boxed"]
        rows.append(dict(Bl=per_level(boxed), Wl=per_level(warn), priority=prio, adc=adc, name=e["name"], version=e["version"], date=e["date"], verdict=v, restriction=RS.summary(v), restriction_ko=RS.summary(v, ko=True), tier=v.worst_possible,
                         B=round(B, 3), Wn=round(Wn, 3), boxed=boxed, warn=warn, elsewhere=elsewhere, organs=org, has_tables=e["has_tables"]))
    # restriction tier (worst case), settled tier, then boxed warnings on the level-1 organs, level-2 organs, ..., then the other
    # warnings level by level. Within one patient this is the order; B and Wn (severity sums) stay for comparisons across patients.
    rows.sort(key=lambda r: (r["tier"], r["verdict"].worst_known, r["Bl"], r["Wl"], r["name"]))
    prev = None
    for r in rows:
        k = (r["tier"], r["verdict"].worst_known, r["Bl"], r["Wl"]); r["tie"] = bool(prev and k == prev["key"]); r["rank"] = prev["rank"] if r["tie"] else (prev["rank"] + 1 if prev else 1)
        r["key"] = k; prev = r
    for i in range(len(rows) - 1):
        if rows[i + 1]["tie"]: rows[i]["tie"] = True
    return rows, {a: round(float(s[k]), 2) for k, a in enumerate(AXES) if s[k] > 0}, notes, checks(ids, E, V)


def checks(ids, E, V):
    """patient checklist: guideline / label tests the conditions call for, and the lab values that would settle a '?' restriction."""
    import yaml
    out = []
    for c in yaml.safe_load(open(R + "conf/patient_checks.yaml"))["checks"]:
        if set(c["conditions"]) & ids:
            names = [E[a]["name"] for a in sorted(E) if c.get("headings") and any(re.search(c["headings"], h.lower()) for o in E[a]["organs"].values() for _, h in o["headings"])]
            out.append((c["test"], names, c["source"]))
    need = sorted({m for v in V.values() for m in v.missing})
    if need: out.append(("enter " + "; ".join(need) + " to settle the restrictions that are not yet certain", [], None))
    return out


# ------------------------------------------------------------------------------------------------ display
def _width(t):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)


def _inc_text(o):
    if o["inc_status"] == "no data": return "no label table"
    if o["inc_status"] == "not reported": return "G>=3 not reported"
    x = o["inc"]; return f"G>=3 {x['pct']:g}% {x['term'].rstrip('*†‡§¶#^±※♦àèðþýßø0123456789, ')}" + (" [combo]" if x["combo"] else "") + (" [lab]" if x["lab"] else "")


TONE = {"contraindicated": "31", "avoid": "31", "insufficient_data": "33", "no_statement": "33", "reduce_dose": "36", "monitor": "36", "no_adjustment": "32"}


def _restriction_cell(v, paint, color):
    """-> (plain text, painted text). Settled verdicts bold; ones a missing value could reach plain (with '?' only without colour)."""
    parts = RS.summary_parts(v)
    if not parts: return "-", "-"
    plain, out = [], []
    for c, ds, sure in parts:
        txt = f"{RS.TABLE[c]}{'' if sure or color else '?'} ({', '.join(ds)})"
        plain.append(txt); out.append(paint(txt, TONE[c] + (";1" if sure else "")))
    return "  ".join(plain), "  ".join(out)


def _table(rows, paint=lambda t, c: t, color=False):
    """-> (table lines, index of the line of each row)."""
    tone = {4: "31;1", 3: "31", 2: "33", 1: "36", 0: "32", -1: ""}
    org_txt = lambda xs: ", ".join(EN[a] for a in xs) or "-"
    head = ["#", "ADC", "Label restriction", "Primary", "Secondary", "Primary"]
    cells, prev_rank, starts = [], None, set()
    for i, r in enumerate(rows):
        if r["rank"] != prev_rank and i: starts.add(i)
        rk = "" if prev_rank == r["rank"] else str(r["rank"]); prev_rank = r["rank"]; rplain, rpaint = _restriction_cell(r["verdict"], paint, color)
        cells.append([(rk, ""), (r["name"][:26], ""), (rplain, rpaint), (org_txt(r["boxed"]), "31" if r["boxed"] else ""),
                      (org_txt(r["warn"]), "33" if r["warn"] else ""), (org_txt(r["elsewhere"]), "90")])
    wd = [max([_width(head[c])] + [_width(row[c][0]) for row in cells]) for c in range(len(head))]
    wd[5] = max(wd[5], len("Other organs")); span = wd[3] + wd[4] + 3
    if span < len("Your organs"): wd[4] += len("Your organs") - span; span = len("Your organs")
    line = lambda l, m, rr: l + m.join("─" * (x + 2) for x in wd) + rr
    pad = lambda s, n: s + " " * (n - _width(s))
    out = ["┌" + "┬".join("─" * (x + 2) for x in wd[:3]) + "┬" + "─" * (span + 2) + "┬" + "─" * (wd[5] + 2) + "┐",
           "│ " + " │ ".join(" " * x for x in wd[:3]) + " │ " + pad("Your organs", span) + " │ " + pad("Other organs", wd[5]) + " │",
           "│" + "│".join(" " * (x + 2) for x in wd[:3]) + "├" + "─" * (wd[3] + 2) + "┬" + "─" * (wd[4] + 2) + "┼" + "─" * (wd[5] + 2) + "┤",
           "│ " + " │ ".join(pad(h, x) for h, x in zip(head, wd)) + " │", line("├", "┼", "┤")]
    thin = "├" + "┼".join("╌" * (x + 2) for x in wd) + "┤"; at = []
    for i, row in enumerate(cells):
        if i in starts: out.append(paint(thin, "90"))
        cell = lambda pl, c, j: (c if j == 2 else paint(pl, c))                       # column 2 arrives already painted
        at.append(len(out)); out.append("│ " + " │ ".join(cell(pl, c, j) + " " * (x - _width(pl)) for j, ((pl, c), x) in enumerate(zip(row, wd))) + " │")
    out.append(line("└", "┴", "┘"))
    return out, at


WHEN_TXT = {"crcl_lt": "CLcr < {}", "crcl_ge": "CLcr ≥ {}", "bili_gt": "bilirubin > {}×ULN", "bili_le": "bilirubin ≤ {}×ULN",
            "ast_gt": "AST > {}×ULN", "ast_le": "AST ≤ {}×ULN", "alt_gt": "ALT > {}×ULN", "alt_le": "ALT ≤ {}×ULN",
            "lvef_lt": "LVEF < {}%", "platelets_lt": "platelets < {}k", "anc_lt": "ANC < {}k", "hba1c_ge": "HbA1c ≥ {}%"}


def _when(w):
    parts = []
    for k, v in w.items():
        if k in WHEN_TXT: parts.append(WHEN_TXT[k].format(v))
        elif k == "esrd": parts.append("ESRD/dialysis" if v else "not on dialysis")
        elif k == "child_pugh": parts.append("Child-Pugh " + "/".join(v))
        elif k == "condition": parts.append(" or ".join(_reg[c]["label"] if c in _reg else c for c in v))
        elif k == "ugt1a1_28_homozygous": parts.append("UGT1A1*28 homozygous")
    return ", ".join(parts)


def reason_rows(r):
    """[(organ, status, basis)] per label domain: what is settled and on what, or what would settle it."""
    v = r["verdict"]; doms = {}; out = []
    for c, rr in v.known: doms.setdefault(rr["domain"], ([], []))[0].append((c, rr))
    for c, rr in v.possible: doms.setdefault(rr["domain"], ([], []))[1].append((c, rr))
    silent = dict(v.silent)
    for d in sorted(set(doms) | set(silent)):
        kn, po = doms.get(d, ([], []))
        top = max([RS.TIER[c] for c, _ in kn] + [-1]); po = [x for x in po if RS.TIER[x[0]] > top]
        if kn:
            c, rr = max(kn, key=lambda x: RS.TIER[x[0]]); out.append((d, RS.TABLE[c], _when(rr["when"]) or "-", c, True))
        elif d in silent and silent[d]: out.append((d, "No data", "label says nothing for this patient", "no_statement", True))
        if po or (d in silent and not silent[d]):
            c, rr = max(po, key=lambda x: RS.TIER[x[0]]) if po else ("no_statement", None)
            cond = _when(rr["when"]) if rr else ""
            out.append((d, RS.TABLE[c], f"if {cond}" if cond else f"depends on {RS.NEEDS.get(d, d)}", c, False))
    return out


def reasons(r, checks_=(), color=True):
    """the bottom panel for one row: a small table drawn like the result table (same borders, same colours), then the checks
    that concern this drug."""
    rows = [x[:3] for x in reason_rows(r)]; meta = [x[3:] for x in reason_rows(r)]; out = [r["name"]]
    paint = (lambda s, c: f"\033[{c}m{s}\033[0m" if c else s) if color else (lambda s, c: s)
    if rows:
        head = ("Organ", "Status", "Basis"); wd = [max(_width(x[i]) for x in rows + [head]) for i in range(3)]
        pad = lambda s, n: s + " " * (n - _width(s)); line = lambda l, m, e: l + m.join("─" * (x + 2) for x in wd) + e
        out += [line("┌", "┬", "┐"), "│ " + " │ ".join(pad(h, x) for h, x in zip(head, wd)) + " │", line("├", "┼", "┤")]
        out += ["│ " + " │ ".join(paint(pad(c, x), (TONE[m[0]] + (";1" if m[1] else "")) if i == 1 else "") for i, (c, x) in enumerate(zip(row, wd))) + " │"
                for row, m in zip(rows, meta)] + [line("└", "┴", "┘")]
    else: out.append("이 환자에게 해당하는 투여 제한 없음")
    mine = [test for test, names, _ in checks_ if not names or r["name"] in names]
    if mine: out += ["투여 전 확인"] + [f"  - {x}" for x in mine]
    return out


def browse(rows, checks_=()):
    """interactive view of the result table (terminal only): pick a row to read why it has its restriction."""
    import tui
    lines, at = _table(rows, lambda t, c: f"\033[{c}m{t}\033[0m" if c else t, color=True)
    return tui.browse("", lines, at, [reasons(r, checks_) for r in rows])


def render(rows, s, notes, checks_, detail=False, color=None):
    import textwrap, shutil
    color = (sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR"))) and not os.environ.get("NO_COLOR") if color is None else color
    paint = lambda t, c: f"\033[{c}m{t}\033[0m" if color and c else t
    cols = shutil.get_terminal_size((110, 24)).columns
    key = min(34, max(len(a) for a, _ in notes)) if notes else 10
    def names(c, how):
        cid = c if c in _reg else _by_label.get(c.lower())
        if cid: return _reg[cid]["label"], KO.get(cid, "")
        if c in CONTEXT: return CONTEXT[c], ""
        if c == "Lab": return how, None
        if c.startswith("Lab: "): return c[5:], "(" + EN[how.rsplit(": ", 1)[-1]] + ")"
        m = re.search(r"(?:MONDO|registry) '([^']+)'", how)
        if "not understood" in how: return c, "(장기 미확인)" + ("  FinnGen estimate, not validated" if "FinnGen" in how else "")
        return c, f"({m.group(1)})" if m else ""
    rowsP = [names(a, b) for a, b in notes]; key = max([_width(a) for a, b in rowsP if b is not None] + [10])
    print("Patient")
    for a, b in rowsP: print(f"  {a}" if b is None else f"  {a}{' ' * (key - _width(a) + 3)}{b}".rstrip())
    prio = rows[0]["priority"] if rows else []
    if len(prio) > 1:
        print("\nPriority (1 = avoid first)")
        nm = lambda c: _reg[c]["label"] if c in _reg else c; w = max(len(nm(c)) for _, c, _ in prio)
        for lvl, c, orgs in prio: print(f"  {lvl}  {nm(c):<{w}}  {', '.join(EN[a] for a in orgs)}")
    print()
    lines, _ = _table(rows, paint, color)
    for ln in lines: print(ln)
    if checks_:
        print("\n투여 전 확인")
        for test, names, src in checks_:
            print(f"  - {test}" + (f"\n      most relevant: {', '.join(names)}" if names else ""))
    if detail:
        print("\nLabel evidence on your organs")
        for r in rows:
            print(f"  {r['name']}  (label v{r['version']}, {r['date']})")
            for a in AXES:
                if a in s:
                    o = r["organs"][a]; hd = "; ".join(f"{sec} {h}" for sec, h in o["headings"]) or "no warning"
                    print(f"      {EN[a]:<15} {o['level']:<5} {hd[:70]:<70}  {_inc_text(o)}")


# ------------------------------------------------------------------------------------------------ input
ORGAN_KO = {"haematologic": "혈액", "hepatic": "간", "cardiovascular": "심혈관", "pulmonary": "폐", "renal": "신장", "gastrointestinal": "위장관",
            "neurologic": "신경", "ocular": "눈", "dermatologic": "피부", "metabolic_endocrine": "대사·내분비", "musculoskeletal": "근골격",
            "infectious_immune": "감염·면역", "otologic": "귀"}
KO = {"chronic_liver_disease": "만성 간질환", "cirrhosis": "간경변", "hepatitis_b_chronic": "만성 B형 간염", "hepatitis_c_chronic": "만성 C형 간염",
      "hepatic_vod_history": "간정맥폐쇄병 병력", "nafld": "비알코올성 지방간", "ckd_stage_3": "만성 콩팥병 3기", "ckd_stage_4_5": "만성 콩팥병 4–5기",
      "dialysis": "투석 중", "heart_failure": "심부전", "reduced_lvef": "좌심실 박출률 저하 (LVEF < 50%)", "prior_anthracycline": "안트라사이클린 치료 경험",
      "coronary_artery_disease": "관상동맥질환", "qt_prolongation": "QT 연장", "interstitial_lung_disease": "간질성 폐질환", "pulmonary_fibrosis": "폐섬유증",
      "copd": "만성 폐쇄성 폐질환", "prior_chest_radiation": "흉부 방사선 치료 경험", "peripheral_neuropathy": "말초신경병증",
      "diabetic_neuropathy": "당뇨병성 말초신경병증", "multiple_sclerosis": "다발성 경화증", "keratopathy_history": "각막병증 병력", "dry_eye": "안구건조증",
      "glaucoma": "녹내장", "prior_corneal_surgery": "각막 수술 경험", "thrombocytopenia": "혈소판감소증", "itp": "면역 혈소판감소증",
      "neutropenia_chronic": "만성 호중구감소증", "anaemia_chronic": "만성 빈혈", "mds": "골수형성이상증후군", "prior_hsct": "조혈모세포이식 경험",
      "inflammatory_bowel_disease": "염증성 장질환", "prior_bowel_resection": "장 절제술 경험", "chronic_pancreatitis": "만성 췌장염",
      "severe_psoriasis": "중증 건선", "prior_sjs_ten": "스티븐스-존슨 증후군/TEN 병력", "type_2_diabetes": "제2형 당뇨병", "hypothyroidism": "갑상선기능저하증",
      "hiv_controlled": "HIV 감염 (치료 중)", "active_autoimmune": "활동성 자가면역질환", "hearing_loss": "감각신경성 난청"}
COND_Q = ("기저질환 선택", "SPACE 선택(복수 가능)  ·  / 검색  ·  ENTER 확정")
PRIORITY_Q = ("어느 질환 쪽 독성을 먼저 피할까요?", "1 = 가장 먼저. 같은 숫자는 같은 순위. 순위가 높은 질환의 장기에 경고가 있는 약이 뒤로 갑니다.")
FALLBACK_Q = ("관련 장기를 찾지 못함: {conds}", "FinnGen 모델 추정 장기를 쓸까요? (검증 안 됨, 오타에도 값이 나오니 철자 확인)")
FALLBACK_OPTS = [("사용 안 함", 0.0), ("사용 (추정값 × 0.25)", 0.25), ("사용 (추정값 × 0.5)", 0.5)]
def _tui_ok():
    try: import curses  # noqa: F401
    except ImportError: return False
    return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb"


def _ask_priority_pc(pc):
    global PRIORITY
    d = default_levels(pc); names = [c for c, _, _ in pc]; show = lambda c: _reg[c]["label"] if c in _reg else c
    print("\n질환 우선순위  자동: " + "  ".join(f"{d[c]} {show(c)}" for c in sorted(names, key=lambda c: d[c])))
    try: raw = input("  직접 정하려면 질환 순서대로 순위 입력 (예: 2 1 1), Enter = 자동 > ").split()
    except EOFError: raw = []
    PRIORITY = dict(zip(names, [int(x) for x in raw])) if len(raw) == len(names) and all(x.isdigit() and int(x) >= 1 for x in raw) else {}


def _ask_fallback(conds, radio=None):
    """ask only when some typed condition maps to no organ; the answer applies to those conditions alone."""
    global FALLBACK
    miss = unresolved(conds)
    if not miss: return
    title, desc = FALLBACK_Q[0].format(conds=", ".join(miss)), FALLBACK_Q[1]
    if radio: k = radio(title, [(n, "") for n, _ in FALLBACK_OPTS], default=0, description=desc)
    else:
        print(f"\n{title}\n  " + desc.replace("\n", "\n  ")); [print(f"  {i}) {n}") for i, (n, _) in enumerate(FALLBACK_OPTS, 1)]
        try: raw = input("  선택 (Enter = 1) > ").strip()
        except EOFError: raw = ""
        k = int(raw) - 1 if raw.isdigit() and 1 <= int(raw) <= len(FALLBACK_OPTS) else 0
    f = FALLBACK_OPTS[k][1]; FALLBACK = {c: f for c in miss} if f > 0 else {}


def wizard(back=False):
    """-> (conditions, labs (x ULN form; empty), colour, raw lab values). One curses screen when possible, plain prompts otherwise.
    back: return from the result screen to the last input step, entries kept."""
    import form, labs as LB
    if _tui_ok():
        r = form.run(sys.modules[__name__], back=back)
        if r is None: sys.exit(0)
        conds, raw = r; return conds, {}, None, raw
    ids = list(_reg)
    try: text = input("기저질환 (번호/ID/영어, 쉼표 구분; ? = 목록) > ")
    except EOFError: text = ""
    while text.strip() == "?":
        for k, i in enumerate(ids, 1): print(f"  {k:>2}) {i:<28} {_reg[i]['label']}")
        try: text = input("기저질환 > ")
        except EOFError: text = ""
    conds = [ids[int(x) - 1] if x.isdigit() and 1 <= int(x) <= len(ids) else x for x in form.split_free(text)] or ["interstitial_lung_disease"]
    raw = {}
    try: has = input("검사 수치가 있나요? (y = 있음, Enter = 없음) > ").strip().lower() == "y"
    except EOFError: has = False
    for k, label, unit, _ in (LB.FIELDS if has else []):
        try: v = input(f"  {label} ({unit}) > ")
        except EOFError: break
        try:
            x = LB.parse(k, v)
            if x is not None: raw[k] = x
        except ValueError as err: print(f"    (ignored: {err})")
    _ask_fallback(conds)
    pc = patient_conditions(conds, raw)
    if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2: _ask_priority_pc(pc)
    return conds, {}, None, raw


def parse_args(argv):
    args, labs, flags, i = [], {}, {"detail": False}, 0
    while i < len(argv):
        a = argv[i]
        if a == "--detail": flags["detail"] = True
        elif a == "--ugt1a1-28-homozygous": labs["ugt1a1_28_homozygous"] = True
        elif a in ("--crcl", "--bili", "--ast", "--alt", "--lvef"): labs[a[2:]] = float(argv[i + 1]); i += 1
        elif a == "--child-pugh": labs["child_pugh"] = argv[i + 1].upper(); i += 1
        elif a == "--learned": flags["learned"] = float(argv[i + 1]); i += 1
        elif a == "--learned-fallback": flags["fallback"] = float(argv[i + 1]); i += 1
        elif a == "--lab":
            import labs as LB
            k, val = argv[i + 1].split("=", 1); flags.setdefault("raw", {})[k.strip().lower()] = LB.parse(k.strip().lower(), val); i += 1
        elif a == "--priority": flags["priority"] = [int(x) for x in argv[i + 1].split(",")]; i += 1
        else: args.append(a)
        i += 1
    return args, labs, flags


def list_conditions():
    print(f"{'ID':<30} {'이름':<46} 장기"); by = {}
    for r in _reg.values(): by.setdefault(r["organ_axes"].split(";")[0], []).append(r)
    for organ, rs in by.items():
        print(f"\n[{organ}]"); [print(f"  {r['id']:<28} {r['label']:<46} {r['organ_axes']}") for r in rs]
    print("\n[context]"); [print(f"  {k:<28} {v}") for k, v in CONTEXT.items()]


if __name__ == "__main__":
    if "--list" in sys.argv: list_conditions(); sys.exit(0)
    args, labs, flags = parse_args(sys.argv[1:])
    if "learned" in flags: LEARNED_FRACTION = flags["learned"]
    if flags.get("fallback") and args: FALLBACK = {c: flags["fallback"] for c in unresolved(args)}
    if flags.get("priority") and args: PRIORITY = dict(zip(args, flags["priority"]))
    back = False
    while True:
        raw = flags.get("raw")
        if args: conds, col = args, None
        elif sys.stdin.isatty(): conds, labs, col, raw = wizard(back)
        else: conds, col = ["interstitial_lung_disease"], None
        print()
        rows, s, notes, ck = recommend(conds, labs, raw)
        if not args and _tui_ok() and browse(rows, ck) == "back": back = True; continue      # PgUp on the result screen
        back = False
        render(rows, s, notes, ck, detail=flags["detail"], color=col)
        if not args:
            import form; form.clear()                                     # the next run starts empty
        if args or not sys.stdin.isatty(): break
        try: again = input("\nRun again with different answers? (y = yes, Enter = exit) > ").strip().lower()
        except EOFError: break
        if again != "y": break
