"""Label use restrictions (conf/label_restrictions.yaml), judged for one patient, kept apart from the risk score.

A restriction answers "does the label limit use in a patient like this?", which no organ score can answer:
"avoid when CLcr < 60" is not 0.6 of a warning, and a low burden elsewhere must not average it away.

Patient values are intervals. A value the user did not enter spans its whole plausible range, and the
verdict is then the SET of categories the label allows over that range (shown as "Avoid?" plus the test
that would decide it), never a value guessed from a diagnosis: CKD stage 3 is defined on eGFR, the labels
on Cockcroft-Gault CLcr, and the two are not interchangeable.

Domains are judged only when the patient makes them relevant: renal / hepatic / cardiac / ocular when a
condition's own organ is that organ or the matching lab value was entered; qt / other by the conditions a
rule names; genotype when it was entered. Renal and hepatic questions that no rule answers come back as
"no label statement" (section 8.6/8.7 is where a label addresses them; silence is not evidence of safety).
"""
import re, os, json
from dataclasses import dataclass, field
import yaml

R = "/home/hyeongchanahn/CONI/adctox/"
DM = "/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07/"
CATS = ["no_adjustment", "monitor", "reduce_dose", "no_statement", "insufficient_data", "avoid", "contraindicated"]
# reduce_dose ranks with monitor (usable, with an action) but is shown as what the label requires, not as monitoring
TIER = {"no_adjustment": 0, "monitor": 1, "reduce_dose": 1, "no_statement": 2, "insufficient_data": 2, "avoid": 3, "contraindicated": 4}
SHORT = {"no_adjustment": "No adjustment", "monitor": "Monitor", "reduce_dose": "Dose reduction required", "no_statement": "No label statement",
         "insufficient_data": "Insufficient data", "avoid": "Avoid", "contraindicated": "Contraindicated"}
COVERED = ("renal", "hepatic")                       # domains where silence is reported as "no label statement"
DOMAIN_AXIS = {"renal": "renal", "hepatic": "hepatic", "cardiac": "cardiovascular", "ocular": "ocular"}
NEEDS = {"renal": "CLcr (Cockcroft-Gault), dialysis/ESRD status if CLcr < 15", "hepatic": "total bilirubin / AST / ALT (x ULN), Child-Pugh", "cardiac": "baseline LVEF"}
INF = float("inf")
KO = {"no_adjustment": "조정 불필요", "monitor": "모니터링", "reduce_dose": "감량 필요", "no_statement": "언급 없음",
      "insufficient_data": "자료 부족", "avoid": "회피", "contraindicated": "금기"}
DOMAIN_KO = {"renal": "신장", "hepatic": "간", "cardiac": "심장", "ocular": "눈", "qt": "QT", "genotype": "유전형", "other": "병용"}


def load_rules():
    return yaml.safe_load(open(R + "conf/label_restrictions.yaml"))["rules"]


def label_text(adc):
    """whitespace-collapsed text of the latest label version for an ADC id like 'pivekimab-sunirine'."""
    from lxml import html
    d = DM + adc.replace("-", "_"); v = max(int(m.group(1)) for f in os.listdir(d) if (m := re.match(r"v(\d+)\.html$", f)))
    return re.sub(r"\s+", " ", html.parse(f"{d}/v{v}.html").getroot().text_content()), v


@dataclass
class Patient:
    conditions: set = field(default_factory=set)
    organs: set = field(default_factory=set)          # own organ axes of the conditions (registry / MONDO), not learned ones
    crcl: float | None = None
    esrd: bool | None = None
    bili: float | None = None
    ast: float | None = None
    alt: float | None = None
    child_pugh: str | None = None
    lvef: float | None = None
    ugt1a1_28_homozygous: bool | None = None

    def __post_init__(self):
        if "dialysis" in self.conditions: self.esrd = True
        if self.esrd is None and self.crcl is not None and self.crcl >= 15: self.esrd = False      # below 15 it may or may not be ESRD


def _domains(p, rules):
    on = set()
    for d, ax in DOMAIN_AXIS.items():
        if ax in p.organs: on.add(d)
    if p.crcl is not None or p.esrd: on.add("renal")
    if p.bili is not None or p.ast is not None or p.alt is not None or p.child_pugh: on.add("hepatic")
    if p.lvef is not None: on.add("cardiac")
    if p.ugt1a1_28_homozygous is not None: on.add("genotype")
    for r in rules:
        if set(r["when"].get("condition", [])) & p.conditions: on.add(r["domain"])
    return on


def _grid(p, domain):
    """plausible patient states for the values this domain reads; a given value is a single point."""
    if domain == "renal":
        if p.esrd: return [dict(crcl=10, esrd=True)]
        if p.crcl is not None:                     # below 15 without a dialysis answer it may or may not be ESRD: both states
            return [dict(crcl=p.crcl, esrd=False)] if p.crcl >= 15 or p.esrd is False else [dict(crcl=p.crcl, esrd=True), dict(crcl=p.crcl, esrd=False)]
        return [dict(crcl=10, esrd=True), dict(crcl=10, esrd=False), dict(crcl=20, esrd=False), dict(crcl=45, esrd=False),
                dict(crcl=55, esrd=False), dict(crcl=75, esrd=False), dict(crcl=100, esrd=False)]
    if domain == "hepatic":
        bs = [p.bili] if p.bili is not None else [0.8, 1.2, 2.0, 4.0]
        as_ = [p.ast] if p.ast is not None else [0.8, 2.0, 2.8, 4.0]
        ls = [p.alt] if p.alt is not None else [0.8, 2.0, 2.8, 4.0]
        cs = [p.child_pugh] if p.child_pugh else ["A", "B", "C"]
        return [dict(bili=b, ast=a, alt=l, child_pugh=c) for b in bs for a in as_ for l in ls for c in cs]
    if domain == "cardiac":
        return [dict(lvef=v) for v in ([p.lvef] if p.lvef is not None else [35, 45, 55])]
    return [dict()]


def _holds(when, st, p):
    """True / False for one plausible state; a value the state does not fix is unknown -> None."""
    for k, v in when.items():
        if k == "always": continue
        if k == "condition":
            if not (set(v) & p.conditions): return False
            continue
        if k == "ugt1a1_28_homozygous":
            if p.ugt1a1_28_homozygous is None: return None
            if p.ugt1a1_28_homozygous != v: return False
            continue
        key = {"crcl_lt": "crcl", "crcl_ge": "crcl", "bili_gt": "bili", "bili_le": "bili", "ast_gt": "ast", "ast_le": "ast", "alt_gt": "alt", "alt_le": "alt",
               "lvef_lt": "lvef", "lvef_ge": "lvef", "child_pugh": "child_pugh", "esrd": "esrd"}[k]
        x = st.get(key)
        if x is None: return None
        ok = {"crcl_lt": lambda: x < v, "crcl_ge": lambda: x >= v, "bili_gt": lambda: x > v, "bili_le": lambda: x <= v,
              "ast_gt": lambda: x > v, "ast_le": lambda: x <= v, "alt_gt": lambda: x > v, "alt_le": lambda: x <= v, "lvef_lt": lambda: x < v, "lvef_ge": lambda: x >= v,
              "child_pugh": lambda: x in v, "esrd": lambda: x == v}[k]()
        if not ok: return False
    return True


@dataclass
class Verdict:
    adc: str
    known: list            # [(category, rule)] that hold for this patient whatever the missing values are
    possible: list         # [(category, rule)] that hold for SOME plausible value of a missing input
    silent: list           # covered domains where some plausible state has no rule ("no label statement")
    missing: list          # tests that would settle a 'possible' verdict

    @property
    def worst_known(self): return max([TIER[c] for c, _ in self.known] + [TIER["no_statement"] for d, sure in self.silent if sure] + [-1])

    @property
    def worst_possible(self): return max([TIER[c] for c, _ in self.known + self.possible] + [TIER["no_statement"] for _ in self.silent] + [-1])


def judge(p, adcs, rules=None):
    rules = load_rules() if rules is None else rules
    out = {}
    for adc in adcs:
        rs = [r for r in rules if r["adc"] == adc]; on = _domains(p, rs); known, possible, silent, missing = [], [], [], set()
        for dom in sorted(on):
            drs = [r for r in rs if r["domain"] == dom]; states = _grid(p, dom); hit_sets = []
            for st in states:
                res = [(r, _holds(r["when"], st, p)) for r in drs]
                hit_sets.append([r for r, h in res if h is not False])        # None = a value this state leaves open: may hold
            for r in drs:
                n_true = sum(_holds(r["when"], st, p) is True for st in states); n_any = sum(any(h is r for h in hs) for hs in hit_sets)
                if n_true == len(states) and n_true: known.append((r["category"], r))
                elif n_any: possible.append((r["category"], r))
            if dom in COVERED:
                empty = [not [h for h in hs if "always" not in h["when"]] for hs in hit_sets]
                if any(empty): silent.append((dom, all(empty)))
        v = Verdict(adc, known, possible, silent, [])
        # ask only for tests that could still change the answer: a possible verdict above what is already certain
        w = v.worst_known
        need = {r["domain"] for c, r in possible if TIER[c] > w} | {d for d, sure in silent if not sure and TIER["no_statement"] > w}
        v.missing = sorted({NEEDS.get(d, d) for d in need}); out[adc] = v
    return out


def _top(entries, ko=False):
    """entries [(category, domain, section)] -> 'Cat (dom s, dom s); Cat2 (...)' for every domain at the highest tier, worst per domain."""
    if not entries: return None
    per = {}
    for c, d, s in entries:
        if d not in per or TIER[c] > TIER[per[d][0]] or (TIER[c] == TIER[per[d][0]] and CATS.index(c) > CATS.index(per[d][0])): per[d] = (c, s)
    top = max(TIER[c] for c, _ in per.values()); groups = {}
    for d, (c, s) in sorted(per.items()):
        if TIER[c] == top: groups.setdefault(c, []).append(DOMAIN_KO.get(d, d) if ko else f"{d} {s}".strip())
    return "; ".join(f"{(KO if ko else SHORT)[c]} ({', '.join(ds)})" for c, ds in sorted(groups.items(), key=lambda kv: -CATS.index(kv[0])))


def summary(v, ko=False):
    """short cell text: the most restrictive known verdict for EVERY domain that reaches it, then what a missing test could
    still make it (again every domain at that tier). A domain the label is silent on counts as 'No label statement'."""
    known = [(c, r["domain"], r["section"]) for c, r in v.known] + [("no_statement", d, "") for d, sure in v.silent if sure]
    possible = [(c, r["domain"], r["section"]) for c, r in v.possible if TIER[c] > v.worst_known] + \
               [("no_statement", d, "") for d, sure in v.silent if not sure and TIER["no_statement"] > v.worst_known]
    k, p = _top(known, ko), _top(possible, ko)
    if p: p = "; ".join(x.replace(" (", "? (", 1) for x in p.split("; "))
    return ("  " if ko else "; ").join(x for x in (k, p) if x) or "-"


def verify_quotes(rules=None):
    """every rule's quote must occur verbatim in its label; returns the rules that do not."""
    rules = load_rules() if rules is None else rules; texts = {}; bad = []
    for r in rules:
        if r["adc"] not in texts: texts[r["adc"]] = label_text(r["adc"])[0]
        if re.sub(r"\s+", " ", r["quote"]).strip() not in texts[r["adc"]]: bad.append(r)
    return bad


if __name__ == "__main__":
    bad = verify_quotes(); print(f"{len(load_rules())} rules, {len(bad)} quotes not found verbatim")
    for r in bad: print("  NOT FOUND:", r["adc"], r["section"], r["quote"][:90])
