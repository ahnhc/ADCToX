"""Patient comorbidities in, a risk percentage for every approved ADC out.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/recommend.py "heart failure" "chronic kidney disease stage 4-5"

risk % = 100 * sum_o w_o * t_o / sum_o w_o,   w_o = 1 + LAMBDA * s_o
  t_o  the ADC's organ burden, 0-1: label boxed warning 1.0, section-5 warning 0.6; incidence (grade >= 3 percentile) fills at most 0.4 of what a warning leaves open, so a boxed warning always outranks
  s_o  the patient's organ vulnerability, 0-1: the condition's own organ (curated registry severity) or half the learned cross-organ
       vulnerability, whichever is larger; with several conditions the maximum per organ.
  w_o  every organ counts (weight 1) and the patient's vulnerable organs count up to 1 + LAMBDA. This is the project's own convention
       (design/search.py: w = 1 + lam * severity; here lam = LAMBDA below). A first version dropped the "1 +" and scored only the patient's vulnerable
       organs, which made a drug with a boxed warning in some OTHER organ (sacituzumab govitecan, haematologic, for an ILD patient)
       look like the safest option. 100% = a boxed warning on every organ; 0% = none touched.
The own-organ term is the primary one by construction: summing unconstrained learned weights let a cross-organ association
(ILD -> neurologic) bury a boxed pulmonary warning (T-DXd fell to rank 7 of 12 for an ILD patient; with the own organ it is rank 1).
Rows are printed lowest risk first. The displayed Risk is rescaled per patient so the lowest of these ADCs is 0 and the highest 100 (it says
which ADC is worse FOR THIS PATIENT, not that 0 is risk-free); --raw shows the unscaled index (the weighted mean above, typically 20-60).
"""
import csv, json, os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
import matcher2 as M2
from matcher import AXES, R
LEARNED_FRACTION = 0.5
N_ORGANS = 2                # organs listed per ADC (Primary, Secondary, ...)
LAMBDA = 9.0                # weight of a fully vulnerable organ = 1 + LAMBDA = x10 an ordinary organ. A STATED PREFERENCE, not a fitted value: --lambda N (N = multiplier - 1).
                            # The project's search.py ships lam = 2 (x3), but at x3-x6 a boxed warning in the patient's own organ (T-DXd for an ILD patient) ranked 12th of 14,
                            # behind drugs with scattered section-5 warnings. It reaches 14th between x6 and x8; x10 leaves margin and is identical to x11 and x15 in the cases checked.
EN = {"haematologic": "Haematologic", "hepatic": "Hepatic", "cardiovascular": "Cardiovascular", "pulmonary": "Pulmonary", "renal": "Renal", "gastrointestinal": "GI",
      "neurologic": "Neurologic", "ocular": "Ocular", "dermatologic": "Dermatologic", "metabolic_endocrine": "Metabolic", "musculoskeletal": "Musculoskeletal",
      "infectious_immune": "Immune", "otologic": "Otologic"}
KO = {"haematologic": "혈액", "hepatic": "간", "cardiovascular": "심혈관", "pulmonary": "폐", "renal": "신장", "gastrointestinal": "위장관", "neurologic": "신경",
      "ocular": "눈", "dermatologic": "피부", "metabolic_endocrine": "대사", "musculoskeletal": "근골격", "infectious_immune": "면역", "otologic": "귀"}
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
    ids, names, T, wt = drug_table(); s, notes = patient_weights(conditions)
    w = 1.0 + LAMBDA * s; raw = 100 * (T @ w) / w.sum(); order = np.argsort(raw)          # lowest risk first
    span = raw.max() - raw.min(); risk = 100 * (raw - raw.min()) / span if span > 0 else np.zeros(len(raw))   # 0 = lowest of these ADCs for this patient, 100 = highest
    rows = []
    for rank, i in enumerate(order, 1):
        contrib = T[i] * w; top = [k for k in np.argsort(-contrib)[:2] if contrib[k] > 0]
        lvl = lambda k: wt[ids[i]][1].get(AXES[k], "none")           # 'boxed' | 'W&P' | 'none'
        why = ", ".join(f"{AXES[k]}{' ★박스형 경고' if lvl(k) == 'boxed' else ' (주의)' if lvl(k) != 'none' else ''}" for k in top)
        top = [k for k in np.argsort(-contrib)[:N_ORGANS] if contrib[k] > 0]
        rows.append(dict(rank=rank, adc=names[i], id=ids[i], risk_pct=round(float(risk[i]), 1), raw_pct=round(float(raw[i]), 1), drivers=why,
                         organs=[(AXES[k], lvl(k), float(contrib[k] / w.max())) for k in top]))      # share of the largest possible single-organ contribution, 0-1
    return rows, {AXES[k]: round(float(s[k]), 2) for k in np.argsort(-s) if s[k] > 0}, notes

def list_conditions():
    print(f"{'ID':<30} {'이름':<46} 장기"); by = {}
    for r in _reg.values(): by.setdefault(r["organ_axes"].split(";")[0], []).append(r)
    for organ, rs in by.items():
        print(f"\n[{organ}]"); [print(f"  {r['id']:<28} {r['label']:<46} {r['organ_axes']}") for r in rs]

ORGAN_NAMES = ["Primary", "Secondary", "Tertiary"]

def render(rows, w, notes, show_raw=False, color=None):
    import os, unicodedata
    color = (sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR"))) and not os.environ.get("NO_COLOR") if color is None else color
    paint = lambda t, c: f"\033[{c}m{t}\033[0m" if color else t
    width = lambda t: sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)
    gauge = lambda p: "○◔◑◕●"[min(4, int(p // 20))]
    tone = lambda p: "32" if p < 33.4 else "33" if p < 66.7 else "31"          # Risk column: green / yellow / red thirds
    def organ_cell(a, lv, share):
        tag = " (Boxed)" if lv == "boxed" else " (Warn)" if lv != "none" else ""          # label evidence is written out, never left to bold or colour alone
        txt = EN[a] + tag                                                              # colour = how much this organ drives THIS ADC's risk for THIS patient (same yardstick as the Risk column)
        c = "31" if share >= 0.5 else "33" if share >= 0.25 else "32" if share >= 0.1 else "90"; return txt, paint(txt, c)
    print("patient: " + "; ".join(f"{a} ({b})" for a, b in notes)); print("organ vulnerability: " + ", ".join(f"{EN[a]} {v}" for a, v in w.items()) + "\n")
    n = max(len(r["organs"]) for r in rows); head = ["#", "ADC", "Risk"] + ORGAN_NAMES[:n]; cells = []
    for r in rows:
        og = [organ_cell(a, lv, sh) for a, lv, sh in r["organs"]] + [("", "")] * (n - len(r["organs"])); p = r["raw_pct"] if show_raw else r["risk_pct"]; txt = f"{p:5.1f}% {gauge(r['risk_pct'])}"
        cells.append([(str(r["rank"]), str(r["rank"])), (r["adc"][:28], r["adc"][:28]), (txt, paint(txt, tone(r["risk_pct"])))] + og)
    wd = [max([width(head[c])] + [width(row[c][0]) for row in cells]) for c in range(len(head))]
    line = lambda l, m, rr: l + m.join("─" * (x + 2) for x in wd) + rr; cell = lambda plain, shown, x: shown + " " * (x - width(plain))
    print(line("┌", "┬", "┐")); print("│ " + " │ ".join(cell(h, h, x) for h, x in zip(head, wd)) + " │"); print(line("├", "┼", "┤"))
    for row in cells: print("│ " + " │ ".join(cell(pl, sh, x) for (pl, sh), x in zip(row, wd)) + " │")
    print(line("└", "┴", "┘"))

def _menu(title, options, default):
    """numbered choices; Enter takes the default; '=value' types a custom number where the menu allows it."""
    print(f"\n{title}")
    for i, (_, label) in enumerate(options, 1): print(f"  {i}) {label}" + ("   <- 기본" if i == default else ""))
    while True:
        try: raw = input(f"선택 (Enter = {default}) > ").strip()
        except EOFError: return options[default - 1][0]
        if raw == "": return options[default - 1][0]
        if raw.isdigit() and 1 <= int(raw) <= len(options): return options[int(raw) - 1][0]
        if raw.startswith("="):
            try: return float(raw[1:])
            except ValueError: pass
        print("  번호를 입력하세요" + (" (직접 값은 =7 처럼)." if any(isinstance(v, float) for v, _ in options) else "."))

def _conditions():
    ids = list(_reg)
    print("\n기저질환을 입력하세요. 쉼표로 여러 개 가능합니다.")
    print("  - 목록의 번호/ID, 또는 영어 문장(예: asthma, cerebrovascular disease)   - 목록 보기: ?")
    while True:
        try: raw = input("기저질환 (Enter = interstitial_lung_disease) > ").strip()
        except EOFError: return ["interstitial_lung_disease"]
        if raw == "": return ["interstitial_lung_disease"]
        if raw == "?":
            for k, i in enumerate(ids, 1): print(f"  {k:>2}) {i:<28} {_reg[i]['label']}")
            continue
        out = [ids[int(t) - 1] if t.strip().isdigit() and 1 <= int(t) <= len(ids) else t.strip() for t in raw.split(",") if t.strip()]
        if out: return out

def _tui_ok():
    try: import curses  # noqa: F401
    except ImportError: return False
    return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb"

# One short table per question, the default in the middle; the explanation lives in the description above the list (Korean).
# Multipliers are the real thing (weight of a fully vulnerable organ); LAMBDA = multiplier - 1. Measured on the 14 ADCs in this table
# (ILD patient, T-DXd; 14 = highest risk): x3, x5, x6 -> 12th, x8 and above -> 14th.
EMPHASIS = [("Low", 4.0, "x5"), ("Medium", 9.0, "x10"), ("High", 14.0, "x15")]
LEARNED = [("None", 0.0, "0"), ("Low", 0.25, "0.25"), ("Medium", 0.5, "0.5"), ("High", 0.75, "0.75"), ("Full", 1.0, "1.0")]
MONDO_OPTS = [("Low", 0.5, "0.5"), ("Medium", 0.8, "0.8"), ("High", 1.0, "1.0")]
EMPHASIS_Q = ("취약 장기 가중치", "환자의 취약 장기를 일반 장기의 몇 배로 반영할지 정합니다.\n높을수록 환자 자신의 장기에 걸린 경고가 순위를 좌우합니다.")
LEARNED_Q = ("연관 장기 반영 비율", "질환 자체의 장기 외에, 함께 나타나는 연관 장기를 얼마나 반영할지 정합니다.\n0 = 반영 안 함,  1 = 질환 자체의 장기와 같은 비중")
MONDO_Q = ("목록 외 질환의 장기 심각도", "목록에 없는 질환의 장기에 적용할 심각도입니다.  1 = 간경변 등 가장 심각한 질환 수준")
ORGANS_Q = ("약물별 표시 장기 수", "위험에 가장 크게 기여한 장기부터 표시합니다.")
SCALE_Q = ("Risk 눈금", "Relative: 이 환자에서 가장 낮은 약물 0, 가장 높은 약물 100으로 환산\nRaw: 가중 평균 원값 (보통 20~60)")
COLOUR_Q = ("색 표시", "Auto: 터미널에서만 색 사용")
COND_Q = ("기저질환 선택", "SPACE 선택(복수 가능)  ·  / 검색  ·  ENTER 확정")
COLOURS = [("On", True), ("Auto", None), ("Off", False)]

def _opts(table): return [(f"{n:<8} {m}", "") for n, _, m in table]

def _read_conditions_tui():
    import tui
    ids = list(_reg); items = [("✎ Other (type your own)", "")] + [(f"{i:<28} {_reg[i]['label']}", _reg[i]["organ_axes"]) for i in ids]
    pick = tui.checklist(COND_Q[0], items, checked=[], description=COND_Q[1], min_one=True)
    conds = ["interstitial_lung_disease"] if pick is None else [ids[i - 1] for i in pick if i > 0]
    if pick and 0 in pick:
        try: extra = input("\nType other conditions in English (comma separated, Enter to skip) > ").strip()
        except EOFError: extra = ""
        conds += [t.strip() for t in extra.split(",") if t.strip()]
    return conds or ["interstitial_lung_disease"]

def _summary(conds, raw):
    print("\n" + "\n".join(f"  {k:<22} {v}" for k, v in [("conditions", ", ".join(conds)), ("weak-organ multiplier", f"x{1 + LAMBDA:g}"), ("linked organs", LEARNED_FRACTION),
                                                           ("organs per ADC", N_ORGANS), ("Risk scale", "raw" if raw else "0-100 relative")]))

def wizard():
    """Arrow-key menus when the terminal allows it (ml/tui.py, modelled on `hermes setup`), numbered prompts otherwise."""
    global LAMBDA, LEARNED_FRACTION, MONDO_SEVERITY, N_ORGANS
    if not _tui_ok(): return _wizard_numbered()
    import tui
    conds = _read_conditions_tui()
    LAMBDA = EMPHASIS[tui.radiolist(EMPHASIS_Q[0], _opts(EMPHASIS), default=1, description=EMPHASIS_Q[1])][1]
    LEARNED_FRACTION = LEARNED[tui.radiolist(LEARNED_Q[0], _opts(LEARNED), default=2, description=LEARNED_Q[1])][1]
    if any(c not in _reg and c.lower() not in _by_label for c in conds): MONDO_SEVERITY = MONDO_OPTS[tui.radiolist(MONDO_Q[0], _opts(MONDO_OPTS), default=1, description=MONDO_Q[1])][1]
    N_ORGANS = [1, 2, 3][tui.radiolist(ORGANS_Q[0], [("1", ""), ("2", ""), ("3", "")], default=1, description=ORGANS_Q[1])]
    raw = tui.radiolist(SCALE_Q[0], [("Relative", ""), ("Raw", "")], default=0, description=SCALE_Q[1]) == 1
    col = COLOURS[tui.radiolist(COLOUR_Q[0], [(n, "") for n, _ in COLOURS], default=1, description=COLOUR_Q[1])][1]
    _summary(conds, raw); return conds, raw, col

def _wizard_numbered():
    global LAMBDA, LEARNED_FRACTION, MONDO_SEVERITY, N_ORGANS
    conds = _conditions()
    def ask(q, table, default):
        print(f"\n  {q[1]}"); k = _menu(q[0], [(i, f"{n:<8} {m}") for i, (n, _, m) in enumerate(table)], default + 1)
        return table[k][1] if isinstance(k, int) else float(k)           # '=7' typed by hand comes back as a float
    LAMBDA = ask(EMPHASIS_Q, EMPHASIS, 1); LEARNED_FRACTION = ask(LEARNED_Q, LEARNED, 2)
    if any(c not in _reg and c.lower() not in _by_label for c in conds): MONDO_SEVERITY = ask(MONDO_Q, MONDO_OPTS, 1)
    print(f"\n  {ORGANS_Q[1]}"); N_ORGANS = int(_menu(ORGANS_Q[0], [(1, "1"), (2, "2"), (3, "3")], 2))
    print(f"\n  {SCALE_Q[1]}"); raw = _menu(SCALE_Q[0], [(False, "Relative"), (True, "Raw")], 1)
    print(f"\n  {COLOUR_Q[1]}"); col = _menu(COLOUR_Q[0], [(v, n) for n, v in COLOURS], 2)
    _summary(conds, raw); return conds, raw, col

if __name__ == "__main__":
    if "--list" in sys.argv: list_conditions(); sys.exit(0)
    args = [a for a in sys.argv[1:] if a != "--raw"]
    if "--lambda" in args: k = args.index("--lambda"); LAMBDA = float(args[k + 1]); del args[k:k + 2]
    while True:
        if args: conds, raw, col = args, "--raw" in sys.argv, None                        # command-line mode: no questions
        elif sys.stdin.isatty(): conds, raw, col = wizard()
        else: conds, raw, col = ["interstitial_lung_disease"], False, None
        print()
        rows, w, notes = recommend(conds); render(rows, w, notes, show_raw=raw, color=col)
        if args or not sys.stdin.isatty(): break
        try: again = input("\nRun again with different answers? (y = yes, Enter = exit) > ").strip().lower()      # a plain line, so the table above stays visible
        except EOFError: break
        if again != "y": break
