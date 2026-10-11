"""Patient comorbidities (and, optionally, lab values) in; every approved ADC out, ordered by what its label says about THIS patient.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/recommend.py ckd_stage_3 heart_failure --crcl 45 --lvef 48

Order, most favourable first (a lexicographic key, so nothing below can buy back anything above):
  1. label use restriction for this patient (ml/restrictions.py, conf/label_restrictions.yaml), worst case over the lab
     values that were not entered: contraindicated > avoid > insufficient data = no label statement > monitor > none;
     within a tier, a restriction that holds whatever the missing values are ranks behind one that only might.
  2. B = sum of s_o over the patient's organs o that carry a BOXED warning on the label.
  3. Wn = sum of s_o over the patient's organs o that carry a section-5 warning (and no boxed one).
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


def resolve(conditions):
    """-> (s over AXES, own-organ set, registry ids present, [(input, how it was read)])"""
    ws, notes, ids, own_axes = [np.zeros(len(AXES))], [], set(), set()
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and c not in CONTEXT]
    if free:
        with _Loading("Loading weights · 질환 해석 모델 (BioLORD · MONDO)", "질환 해석 모델 준비 완료"):
            import vulnerability_model as VM, mondo_index as MI
            reg_ids = list(_reg); E = VM._st(free + [_reg[i]["label"] for i in reg_ids]); Ef, Er = E[:len(free)], E[len(free):]
            links = MI.link(free); learned_free = VM.predict(free) if LEARNED_FRACTION > 0 or FALLBACK else None
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
                    f = max(FALLBACK[c], LEARNED_FRACTION); top = [EN[AXES[k]] for k in np.argsort(-lv)[:3] if f * lv[k] >= 0.01]
                    ws.append(f * lv); how += f"; FinnGen learned estimate x{f:g} used (not validated): {', '.join(top) or 'no organ'}"
            fi += 1
        own_axes |= {AXES[k] for k in np.where(own > 0)[0]}
        ws.append(np.maximum(own, LEARNED_FRACTION * lv) if lv is not None and LEARNED_FRACTION > 0 else own); notes.append((c, how))
    return np.maximum.reduce(ws), own_axes, ids, notes


def unresolved(conditions):
    """typed conditions that map to no organ (what the wizard asks about); learned estimates play no part in this."""
    global LEARNED_FRACTION, FALLBACK
    keep = LEARNED_FRACTION, FALLBACK; LEARNED_FRACTION, FALLBACK = 0.0, {}
    try: return [c for c, how in resolve(conditions)[3] if how.startswith("free text; not understood")]
    finally: LEARNED_FRACTION, FALLBACK = keep


def recommend(conditions, labs=None):
    """-> rows (ordered), s {axis: value}, notes, checks"""
    labs = labs or {}; s, own_axes, ids, notes = resolve(conditions); E = DE.evidence(); adcs = sorted(E)
    p = RS.Patient(conditions=ids, organs=own_axes, **labs); V = RS.judge(p, adcs); rows = []
    for adc in adcs:
        e = E[adc]; org = e["organs"]; v = V[adc]
        boxed = [a for a in AXES if s[AXES.index(a)] > 0 and org[a]["level"] == "boxed"]
        warn = [a for a in AXES if s[AXES.index(a)] > 0 and org[a]["level"] == "W&P"]
        B = sum(s[AXES.index(a)] for a in boxed); Wn = sum(s[AXES.index(a)] for a in warn)
        elsewhere = [a for a in AXES if s[AXES.index(a)] == 0 and org[a]["level"] == "boxed"]
        rows.append(dict(adc=adc, name=e["name"], version=e["version"], date=e["date"], verdict=v, restriction=RS.summary(v), tier=v.worst_possible,
                         B=round(B, 3), Wn=round(Wn, 3), boxed=boxed, warn=warn, elsewhere=elsewhere, organs=org, has_tables=e["has_tables"]))
    rows.sort(key=lambda r: (r["tier"], r["verdict"].worst_known, r["B"], r["Wn"], r["name"]))     # a settled restriction ranks behind a possible one of the same tier
    prev = None
    for r in rows:
        k = (r["tier"], r["verdict"].worst_known, r["B"], r["Wn"]); r["tie"] = bool(prev and k == prev["key"]); r["rank"] = prev["rank"] if r["tie"] else (prev["rank"] + 1 if prev else 1)
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
    if need: out.append(("enter " + "; ".join(need) + " to settle the restrictions marked '?'", [], "ml/restrictions.py"))
    return out


# ------------------------------------------------------------------------------------------------ display
def _width(t):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)


def _inc_text(o):
    if o["inc_status"] == "no data": return "no label table"
    if o["inc_status"] == "not reported": return "G>=3 not reported"
    x = o["inc"]; return f"G>=3 {x['pct']:g}% {x['term'].rstrip('*†‡§¶#^±※♦àèðþýßø0123456789, ')}" + (" [combo]" if x["combo"] else "") + (" [lab]" if x["lab"] else "")


def render(rows, s, notes, checks_, detail=False, color=None):
    import textwrap, shutil
    color = (sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR"))) and not os.environ.get("NO_COLOR") if color is None else color
    paint = lambda t, c: f"\033[{c}m{t}\033[0m" if color and c else t
    cols = shutil.get_terminal_size((110, 24)).columns
    key = min(34, max(len(a) for a, _ in notes)) if notes else 10
    print("Patient")
    for a, b in notes:
        lines = textwrap.wrap(b, width=max(30, cols - key - 6)) or [""]
        print(f"  {a:<{key}}  {lines[0]}"); [print(f"  {'':<{key}}  {x}") for x in lines[1:]]
    if s:
        kw = max(len(EN[a]) for a in s); print("\nOrgan vulnerability (s)"); [print(f"  {EN[a]:<{kw}}  {v:.2f}") for a, v in sorted(s.items(), key=lambda kv: -kv[1])]
    print()
    tone = {4: "31;1", 3: "31", 2: "33", 1: "36", 0: "32", -1: ""}
    org_txt = lambda xs: ", ".join(EN[a] for a in xs) or "-"
    head = ["#", "ADC", "Label restriction", "Boxed on your organs", "Warn on your organs", "Boxed elsewhere"]
    cells = []
    for r in rows:
        rk = f"{r['rank']}{'=' if r['tie'] else ''}"; rc = "33" if "?" in r["restriction"] else tone[max(r["verdict"].worst_known, -1)]
        cells.append([(rk, ""), (r["name"][:26], ""), (r["restriction"], rc), (org_txt(r["boxed"]), "31" if r["boxed"] else ""),
                      (org_txt(r["warn"]), "33" if r["warn"] else ""), (org_txt(r["elsewhere"]), "90")])
    wd = [max([_width(head[c])] + [_width(row[c][0]) for row in cells]) for c in range(len(head))]
    line = lambda l, m, rr: l + m.join("─" * (x + 2) for x in wd) + rr
    print(line("┌", "┬", "┐")); print("│ " + " │ ".join(h + " " * (x - _width(h)) for h, x in zip(head, wd)) + " │"); print(line("├", "┼", "┤"))
    for row in cells: print("│ " + " │ ".join(paint(pl, c) + " " * (x - _width(pl)) for (pl, c), x in zip(row, wd)) + " │")
    print(line("└", "┴", "┘"))
    print("Order: label restriction > boxed on your organs > warnings on your organs. Same number with '=' = tie.")
    seen, first = set(), True
    for r in rows:
        for c, rr in r["verdict"].known + r["verdict"].possible:
            if c == "no_adjustment" or (r["name"], rr["quote"]) in seen: continue
            if first: print("\nLabel restrictions (verbatim)"); first = False
            seen.add((r["name"], rr["quote"])); q = rr["quote"] if len(rr["quote"]) <= cols - 52 else rr["quote"][:cols - 55] + "..."
            mark = "" if (c, rr) in r["verdict"].known else "?"
            print(f"  {r['name'][:26]:<26} {RS.SHORT[c] + mark:<18} §{rr['section']:<5} \"{q}\"")
    if checks_:
        print("\nChecks before choosing")
        for test, names, src in checks_:
            print(f"  - {test}" + (f"\n      most relevant: {', '.join(names)}" if names else "") + f"\n      source: {src}")
    if detail:
        print("\nLabel evidence on your organs")
        for r in rows:
            print(f"  {r['name']}  (label v{r['version']}, {r['date']})")
            for a in AXES:
                if a in s:
                    o = r["organs"][a]; hd = "; ".join(f"{sec} {h}" for sec, h in o["headings"]) or "no warning"
                    print(f"      {EN[a]:<15} {o['level']:<5} {hd[:70]:<70}  {_inc_text(o)}")


# ------------------------------------------------------------------------------------------------ input
COND_Q = ("기저질환 선택", "SPACE 선택(복수 가능)  ·  / 검색  ·  ENTER 확정")
LABS_ASK_Q = ("입력할 검사 수치가 있나요?", "")
LABS_PICK_Q = ("검사 수치 선택", "")
LABS_WHY = {"crcl": "신기능", "bili": "간기능", "ast": "간기능", "child_pugh": "간경변 중증도", "lvef": "심기능", "ugt1a1_28_homozygous": "약물 대사 유전형"}
FALLBACK_Q = ("관련 장기를 찾지 못함: {conds}", "FinnGen 모델 추정 장기를 쓸까요? (검증 안 됨, 오타에도 값이 나오니 철자 확인)")
MONDO_Q = ("목록 외 질환의 장기 심각도", "목록에 없는 질환의 장기에 적용할 심각도입니다.  1 = 간경변 등 가장 심각한 질환 수준")
COLOUR_Q = ("색 표시", "Auto: 터미널에서만 색 사용")
FALLBACK_OPTS = [("사용 안 함", 0.0), ("사용, Low 0.25", 0.25), ("사용, Medium 0.5", 0.5)]
MONDO_OPTS = [("Low 0.5", 0.5), ("Medium 0.8", 0.8), ("High 1.0", 1.0)]
COLOURS = [("On", True), ("Auto", None), ("Off", False)]
LAB_FIELDS = [("crcl", "CLcr, Cockcroft-Gault (mL/min)", float), ("bili", "total bilirubin (x ULN)", float), ("ast", "AST (x ULN)", float),
              ("child_pugh", "Child-Pugh class (A/B/C)", lambda x: x.strip().upper() if x.strip().upper() in ("A", "B", "C") else None),
              ("lvef", "baseline LVEF (%)", float), ("ugt1a1_28_homozygous", "UGT1A1*28 homozygous (y/n)", lambda x: {"y": True, "n": False}.get(x.strip().lower()))]


def lab_uses():
    """lab field -> ADC names whose label restrictions it can change (from conf/label_restrictions.yaml), fields most used first."""
    keys = {"crcl": ("crcl_lt", "crcl_ge", "esrd"), "bili": ("bili_gt", "bili_le"), "ast": ("ast_gt", "ast_le"), "child_pugh": ("child_pugh",),
            "lvef": ("lvef_lt",), "ugt1a1_28_homozygous": ("ugt1a1_28_homozygous",)}
    E = DE.evidence(); use = {k: sorted({E[r["adc"]]["name"] for r in RS.load_rules() if r["adc"] in E and set(r["when"]) & set(v)}) for k, v in keys.items()}
    return sorted(((k, q, cast, use[k]) for k, q, cast in LAB_FIELDS), key=lambda x: -len(x[3]))


ABBR = {"Trastuzumab deruxtecan": "T-DXd", "Trastuzumab emtansine": "T-DM1", "Datopotamab deruxtecan": "Dato-DXd"}
def _short(names, n=4):
    s = [ABBR.get(x, x.split()[0]) for x in names]; return ", ".join(s[:n]) + (f" 외 {len(s) - n}개" if len(s) > n else "")


def _ask_labs(tui=None):
    """first: are there any lab values at all? then: which ones (with why each matters); then only those values."""
    labs = {}; fields = lab_uses()
    if tui:
        if tui.radiolist(LABS_ASK_Q[0], [("없음", ""), ("있음", "")], default=0, description=LABS_ASK_Q[1]) == 0: return labs
        items = [(q, f"{LABS_WHY[k]} · {_short(u)}") for k, q, _, u in fields]
        pick = tui.checklist(LABS_PICK_Q[0], items, checked=[], description=LABS_PICK_Q[1], min_one=False) or []
    else:
        try: has = input(f"\n{LABS_ASK_Q[0]} (y = 있음, Enter = 없음) > ").strip().lower()
        except EOFError: has = ""
        if has != "y": return labs
        for i, (k, q, _, u) in enumerate(fields, 1): print(f"  {i}) {q:<32} {LABS_WHY[k]} · {_short(u)}")
        try: raw = input("  번호 (쉼표 구분, Enter = 없음) > ")
        except EOFError: raw = ""
        pick = [int(x) - 1 for x in raw.replace(" ", "").split(",") if x.isdigit() and 1 <= int(x) <= len(fields)]
    if pick: print()
    for k, q, cast, _ in (fields[i] for i in pick):
        try: raw = input(f"  {q} (Enter = 건너뜀) > ").strip()
        except EOFError: break
        if not raw: continue
        try:
            v = cast(raw)
            if v is not None: labs[k] = v
        except ValueError: print("    (ignored: not a number)")
    return labs


def _tui_ok():
    try: import curses  # noqa: F401
    except ImportError: return False
    return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb"


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


def wizard():
    global MONDO_SEVERITY
    if _tui_ok():
        import tui
        ids = list(_reg); items = [("✎ Other (type your own)", "")] + [(f"{i:<28} {_reg[i]['label']}", _reg[i]["organ_axes"]) for i in ids]
        pick = tui.checklist(COND_Q[0], items, checked=[], description=COND_Q[1], min_one=True)
        conds = ["interstitial_lung_disease"] if pick is None else [ids[i - 1] for i in pick if i > 0]
        if pick and 0 in pick:
            try: extra = input("\nType other conditions in English (comma separated, Enter to skip) > ").strip()
            except EOFError: extra = ""
            conds += [t.strip() for t in extra.split(",") if t.strip()]
        conds = conds or ["interstitial_lung_disease"]
        labs = _ask_labs(tui)
        _ask_fallback(conds, tui.radiolist)
        if any(c not in _reg and c.lower() not in _by_label and c not in CONTEXT for c in conds):
            MONDO_SEVERITY = MONDO_OPTS[tui.radiolist(MONDO_Q[0], [(n, "") for n, _ in MONDO_OPTS], default=1, description=MONDO_Q[1])][1]
        col = COLOURS[tui.radiolist(COLOUR_Q[0], [(n, "") for n, _ in COLOURS], default=1, description=COLOUR_Q[1])][1]
    else:
        ids = list(_reg)
        try: raw = input("기저질환 (번호/ID/영어, 쉼표 구분; ? = 목록) > ").strip()
        except EOFError: raw = ""
        while raw == "?":
            for k, i in enumerate(ids, 1): print(f"  {k:>2}) {i:<28} {_reg[i]['label']}")
            try: raw = input("기저질환 > ").strip()
            except EOFError: raw = ""
        conds = [ids[int(t) - 1] if t.strip().isdigit() and 1 <= int(t) <= len(ids) else t.strip() for t in raw.split(",") if t.strip()] or ["interstitial_lung_disease"]
        labs = _ask_labs(); col = None
        _ask_fallback(conds)
    return conds, labs, col


def parse_args(argv):
    args, labs, flags, i = [], {}, {"detail": False}, 0
    while i < len(argv):
        a = argv[i]
        if a == "--detail": flags["detail"] = True
        elif a == "--ugt1a1-28-homozygous": labs["ugt1a1_28_homozygous"] = True
        elif a in ("--crcl", "--bili", "--ast", "--lvef"): labs[a[2:]] = float(argv[i + 1]); i += 1
        elif a == "--child-pugh": labs["child_pugh"] = argv[i + 1].upper(); i += 1
        elif a == "--learned": flags["learned"] = float(argv[i + 1]); i += 1
        elif a == "--learned-fallback": flags["fallback"] = float(argv[i + 1]); i += 1
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
    while True:
        if args: conds, col = args, None
        elif sys.stdin.isatty(): conds, labs, col = wizard()
        else: conds, col = ["interstitial_lung_disease"], None
        print()
        rows, s, notes, ck = recommend(conds, labs); render(rows, s, notes, ck, detail=flags["detail"], color=col)
        if args or not sys.stdin.isatty(): break
        try: again = input("\nRun again with different answers? (y = yes, Enter = exit) > ").strip().lower()
        except EOFError: break
        if again != "y": break
