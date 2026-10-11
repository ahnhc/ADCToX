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
CATS = ["no_adjustment", "monitor", "no_statement", "insufficient_data", "avoid", "contraindicated"]
TIER = {"no_adjustment": 0, "monitor": 1, "no_statement": 2, "insufficient_data": 2, "avoid": 3, "contraindicated": 4}
SHORT = {"no_adjustment": "No adjustment", "monitor": "Monitor", "no_statement": "No label statement",
         "insufficient_data": "Insufficient data", "avoid": "Avoid", "contraindicated": "Contraindicated"}
COVERED = ("renal", "hepatic")                       # domains where silence is reported as "no label statement"
DOMAIN_AXIS = {"renal": "renal", "hepatic": "hepatic", "cardiac": "cardiovascular", "ocular": "ocular"}
NEEDS = {"renal": "CLcr (Cockcroft-Gault)", "hepatic": "total bilirubin / AST (x ULN), Child-Pugh", "cardiac": "baseline LVEF"}
INF = float("inf")


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
    if p.bili is not None or p.ast is not None or p.child_pugh: on.add("hepatic")
    if p.lvef is not None: on.add("cardiac")
    if p.ugt1a1_28_homozygous is not None: on.add("genotype")
    for r in rules:
        if set(r["when"].get("condition", [])) & p.conditions: on.add(r["domain"])
    return on


def _grid(p, domain):
    """plausible patient states for the values this domain reads; a given value is a single point."""
    if domain == "renal":
        if p.esrd: return [dict(crcl=10, esrd=True)]
        if p.crcl is not None: return [dict(crcl=p.crcl, esrd=False if p.crcl >= 15 else None)]
        return [dict(crcl=10, esrd=True), dict(crcl=10, esrd=False), dict(crcl=20, esrd=False), dict(crcl=45, esrd=False),
                dict(crcl=55, esrd=False), dict(crcl=75, esrd=False), dict(crcl=100, esrd=False)]
    if domain == "hepatic":
        bs = [p.bili] if p.bili is not None else [0.8, 1.2, 2.0, 4.0]
        as_ = [p.ast] if p.ast is not None else [0.8, 2.0, 2.8, 4.0]
        cs = [p.child_pugh] if p.child_pugh else ["A", "B", "C"]
        return [dict(bili=b, ast=a, child_pugh=c) for b in bs for a in as_ for c in cs]
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
        key = {"crcl_lt": "crcl", "crcl_ge": "crcl", "bili_gt": "bili", "bili_le": "bili", "ast_gt": "ast", "ast_le": "ast",
               "lvef_lt": "lvef", "lvef_ge": "lvef", "child_pugh": "child_pugh", "esrd": "esrd"}[k]
        x = st.get(key)
        if x is None: return None
        ok = {"crcl_lt": lambda: x < v, "crcl_ge": lambda: x >= v, "bili_gt": lambda: x > v, "bili_le": lambda: x <= v,
              "ast_gt": lambda: x > v, "ast_le": lambda: x <= v, "lvef_lt": lambda: x < v, "lvef_ge": lambda: x >= v,
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
                hits = [r for r in drs if _holds(r["when"], st, p)]; hit_sets.append(hits)
            for r in drs:
                n = sum(any(h is r for h in hs) for hs in hit_sets)
                if n == len(states) and n: known.append((r["category"], r))
                elif n: possible.append((r["category"], r)); missing.add(NEEDS.get(dom, dom))
            if dom in COVERED:
                empty = [not [h for h in hs if "always" not in h["when"]] for hs in hit_sets]
                if any(empty): silent.append((dom, all(empty)));  missing.update([NEEDS[dom]] if not all(empty) else [])
        out[adc] = Verdict(adc, known, possible, silent, sorted(missing))
    return out


def summary(v):
    """short cell text: the most restrictive known verdict, then what a missing test could still make it."""
    def best(items): return max(items, key=lambda cr: TIER[cr[0]]) if items else None
    k = best(v.known); parts = []
    sure_silent = [d for d, sure in v.silent if sure]
    if k and (not sure_silent or TIER[k[0]] >= TIER["no_statement"]):
        parts.append(f"{SHORT[k[0]]} ({k[1]['domain']} {k[1]['section']})")
    elif sure_silent:
        parts.append(f"No label statement ({'/'.join(sure_silent)})")
    pw = best([cr for cr in v.possible if TIER[cr[0]] > v.worst_known]); unsure_silent = [d for d, s in v.silent if not s]
    silent_wins = unsure_silent and v.worst_known < TIER["no_statement"] and (not pw or TIER[pw[0]] < TIER["no_statement"])
    if silent_wins: parts.append(f"No statement? ({'/'.join(unsure_silent)})")
    elif pw: parts.append(f"{SHORT[pw[0]]}? ({pw[1]['domain']} {pw[1]['section']})")
    return "; ".join(parts) if parts else "-"


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
