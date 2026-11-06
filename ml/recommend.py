"""Patient comorbidities (and, optionally, lab values) in; every approved ADC out, ordered by what its label says about THIS patient.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/recommend.py         the input screens (conditions, lab values, ..., result)
    in code: rows, s, notes, checks = recommend(["ckd_stage_3", "heart_failure"], {"crcl": 45, "lvef": 48}, {"bilirubin": 2.0})
    (since 0.5.3 the command line takes no conditions or lab values; `--self-test` prints one fixed example)

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

Typed conditions are read by the organ judge (ml/scratch_runtime.py, models 0.7+) alone: it links a MONDO or HPO concept and
gives the organs; a concept that stands for a registry condition (conf/registry_concepts.json) adds that condition's severity
and restriction rules. A typed condition the judge maps to no organ is shown as not understood. The learned cross-organ
vulnerability (disease-pair model, ml/vulnerability_model.py) is a research model, not part of the app since 0.6.11: in the
only non-circular test it did not improve matching (+0.033 [-0.018, +0.087], ml/README.md).

This orders label evidence for one patient. It is not a probability of an adverse event and has not been validated against
patient outcomes (ml/docs/validation_plan.md).
"""
import csv, json, os, re, sys, unicodedata, warnings
for _k, _v in (("HF_HUB_DISABLE_PROGRESS_BARS", "1"), ("TRANSFORMERS_VERBOSITY", "error"), ("TQDM_DISABLE", "1"), ("HF_HUB_VERBOSITY", "error")):
    os.environ.setdefault(_k, _v)     # model loading bars and hub warnings are noise in a clinical table
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drug_evidence as DE, restrictions as RS
AXES = DE.AXES; R = RS.R
PRIORITY = {}               # condition text -> level the user set (1 = avoid its organs' toxicity first); default = severity order
FIRST = None                # the condition the doctor is most worried about (the priority step); None = automatic
CHOICE = {}                 # condition text -> MONDO id the user picked among its readings (None = 'not sure'); see mondo_index.readings
REG_NEAR = 0.80             # portable build: typed text is 'the same as' a registry condition at this spelling ratio -> its curated organs
MONDO_SEVERITY = 0.80       # organs read off the MONDO hierarchy have no curated severity; one fixed value, not fitted
MATCH_COS = 0.60            # portable build, last resort: borrow the organs of a loosely similar registry condition
LINK_THETA = 0.75           # = mondo_index.THETA: a MONDO match this close is 'understood' even when the concept has no organ axis
GATE_MONDO = True           # also require the validity gate for a MONDO link (chosen on the gold dev split, ml/docs/archive/model_review_2026-10-12.md)
CONTEXT = {"concomitant_bleomycin": "Concomitant bleomycin (co-medication, no organ)"}     # inputs that are not diseases but a label rule names
CONTEXT_ALIAS = {"bleomycin": "concomitant_bleomycin", "concomitant bleomycin": "concomitant_bleomycin", "블레오마이신": "concomitant_bleomycin", "블레오마이신 병용": "concomitant_bleomycin"}
EN = {"haematologic": "Haematologic", "hepatic": "Hepatic", "cardiovascular": "Cardiovascular", "pulmonary": "Pulmonary", "renal": "Renal",
      "gastrointestinal": "GI", "neurologic": "Neurologic", "ocular": "Ocular", "dermatologic": "Dermatologic", "metabolic_endocrine": "Metabolic",
      "musculoskeletal": "Musculoskeletal", "infectious_immune": "Immune", "otologic": "Otologic"}

_reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv", encoding="utf-8"))}
_by_label = {r["label"].lower(): r["id"] for r in _reg.values()}
_ALIASES = __import__("yaml").safe_load(open(R + "conf/registry_aliases.yaml", encoding="utf-8"))["aliases"]     # registry condition -> typed forms the judge misreads or misses (needs clinician review)
_by_label.update({unicodedata.normalize("NFC", form).lower(): cid for cid, forms in _ALIASES.items() for form in forms})
_by_concept = json.load(open(R + "conf/registry_concepts.json", encoding="utf-8"))["concepts"]   # ml/registry_concepts.py


class _Loading:
    """one-line spinner while the text encoders load (terminal only); replaces the libraries' progress bars."""
    def __init__(self, text, done, enabled=True): self.text, self.done, self.enabled = text, done, enabled
    def __enter__(self):
        import threading, time
        self.t0 = time.time(); self.on = self.enabled and sys.stderr.isatty(); self.stop = threading.Event()
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


def nfc(text):
    """composed Hangul: a macOS paste is decomposed, and no name or [가-힣] search would match it"""
    return unicodedata.normalize("NFC", text)


def _context(text):
    """the CONTEXT key a typed text stands for, or None"""
    t = " ".join(text.lower().split())
    return t if t in CONTEXT else CONTEXT_ALIAS.get(t)


def own_vec(cid):
    v = np.zeros(len(AXES))
    for a in _reg[cid]["organ_axes"].split(";"):
        if a in AXES: v[AXES.index(a)] = float(_reg[cid]["severity"])
    return v


_FREE = {}                  # free-text conditions -> the organ judge's links, per process
_ANALYSES = {}              # how each condition was read, shown in the input review
HAS_LEARNED = True          # the organ judge, the input review and the AI suggestions are available (not in the portable build)


def clear_model_cache():
    """A completed model update must invalidate both linking and inference results."""
    _FREE.clear(); _ANALYSES.clear(); _REG_P.clear(); _CHOSEN_NAME.clear()
    module = sys.modules.get("mondo_index")
    if module is not None:
        index = getattr(module, "_IDX", None)
        if index is not None and hasattr(index, "close"): index.close()
        module._IDX = None
    module = sys.modules.get("mondo_index")                    # the name index is per bundle too
    if module is not None and hasattr(module, "close"): module.close()


_EVIDENCE = []              # label evidence and rules parsed once per process: the label snapshot does not change while it runs


def _evidence():
    import copy
    if not _EVIDENCE: _EVIDENCE.extend([DE.evidence(), RS.load_rules()])
    return copy.deepcopy(_EVIDENCE[0]), _EVIDENCE[1]


def _free_info(free, progress=None):
    """per typed text: the organ judge's link (ml/scratch_runtime.py), or, when the judge is missing or fails, an empty link that
    says why (the input review shows it). The portable build replaces this function with string matching on MONDO names."""
    key = tuple(free)
    if key not in _FREE:
        text = english(free)                                   # Korean names go to the judge as their English KCD name
        try:
            import scratch_runtime as SR
            if not SR.available(): raise RuntimeError("the installed models have no organ judge; run adctox --update-models")
            if progress: progress("judging")
            with _Loading("Loading weights / 질환 판정 모델 (x2te)", "질환 판정 모델 준비 완료", enabled=progress is None):
                links = [_scratch_link(r, typed, read) for r, typed, read in zip(SR.judge(text), free, text)]
        except Exception as error:
            warnings.warn(f"organ judge unavailable: {error}")
            links = [dict(mondo=None, name="", sim=0.0, axes=[], gate=None, readings=[], ambiguous=False, fallback=f"{type(error).__name__}: {error}") for _ in free]
        _FREE[key] = links
    return _FREE[key]


TIE, CONFIRM, SHORT = 0.02, 0.8, 4    # candidates this close to the first are also readings of the text; a weaker match asks to confirm the read; letters in a short input (mondo_index.TIE)
DOUBT = {"confirm": "Confirm this read", "low": "Low confidence, check this"}


_GENERAL_ORGANS = {}


def _general_organs(general, own):
    """a general concept's organs, and those at least half of its labelled subtypes have: a label can be narrower than the disease
    (hereditary hemochromatosis: no hepatic, its types have it), and the read must not lose an organ by being general."""
    if general not in _GENERAL_ORGANS:
        import scratch_runtime as SR, subtypes as ST
        rows = [SR.concept(k) for k, v in ST.general_map().items() if v[1] == general]
        rows = [x[1] for x in rows if x and x[1]]; found = list(own)
        for organ in AXES:
            if organ not in found and len(rows) >= 2 and sum(organ in x for x in rows) * 2 >= len(rows): found.append(organ)
        _GENERAL_ORGANS[general] = found
    return list(_GENERAL_ORGANS[general])


def _candidates(r, typed):
    """the judge's candidates as the user reads them: a numbered subtype the text does not name becomes its general concept when the
    index has one, and a subtype without one is marked `numbered`. One row per concept, the first as the judge linked it."""
    import scratch_runtime as SR, subtypes as ST
    rows = r.get("candidates") or ([dict(concept=r["concept"], name=r["name"], organs=r["organs"], via=r["via"], sim=r["sim"])] if r["concept"] else [])
    out, seen = [], set()
    for x in rows:
        x = dict(x)
        if ST.is_subtype(x["concept"]) and not ST.keeps(typed, x["name"]):
            general = ST.general(x["concept"]); row = SR.concept(general) if general else None
            if row:
                organs = _general_organs(general, row[1])
                x.update(concept=general, name=row[0], organs=organs or list(r.get("judged") or []), via=row[2] if organs else "name")
            else: x["numbered"] = True
        if x["concept"] not in seen: seen.add(x["concept"]); out.append(x)
    if out and out[0].get("numbered"):                          # no general concept: the next close candidate that is no subtype, else this one
        plain = next((x for x in out[1:] if x["sim"] >= out[0]["sim"] - TIE and not x.get("numbered") and x["concept"].startswith("MONDO:")), None)
        if plain: out.remove(plain); out.insert(0, plain)
    return out


def _readings(rows, typed, low=False):
    """-> (readings, whether the user chooses): a short input or a low-confidence read with candidates on different organs, or tied
    candidates on different organs. A concept without organs does not disagree with anything. Korean names are not short: 3 or 4
    letters are a whole word."""
    rows = [x for x in rows if x["concept"].startswith(("MONDO:", "HP:")) and not x.get("numbered")]
    if not rows: return [], False
    short = not re.search("[가-힣]", typed) and sum(ch.isalpha() for ch in typed) <= SHORT
    pool = rows if short or low else [x for x in rows if x["sim"] >= rows[0]["sim"] - TIE]
    if short: pool = pool[:1] + _abbreviations(typed) + pool[1:]
    named, seen = [], set()
    for x in pool:
        if x["name"].lower() not in seen: seen.add(x["name"].lower()); named.append(x)
    readings = [dict(mondo=x["concept"], name=x["name"], organs=list(x["organs"]), why=x.get("why") or ("closest name" if x is rows[0] else "similar name")) for x in named[:6]]
    return readings, len({frozenset(x["organs"]) for x in named if x["organs"]}) >= 2


_ABBR = {}


def _abbreviations(text):
    """what a short input may stand for, from the disease profiles the app carries: 'SCD' is sickle cell disease, which no name resembles."""
    import scratch_runtime as SR, suggest as SG
    key = text.strip().lower()
    if not _ABBR:
        for p in SG.profiles():
            for a in p.get("abbr", []): _ABBR.setdefault(a.lower(), []).append(p["id"])
    rows = [(t, SR.concept(t)) for t in _ABBR.get(key, [])]
    return [dict(concept=t, name=row[0], organs=row[1], why="abbreviation") for t, row in rows if row]


CANCER_WORD = re.compile(r"cancer|carcinoma|tumou?r|neoplasm|malignan|metasta|\bca\b|[a-z]oma\b|leuka?emia|암|종양|육종|백혈병|림프종", re.I)


def _names_cancer(concept, texts):
    """a text is this cancer's exact name or synonym: only then does a read make it the patient's cancer without asking. A short
    synonym does not count: MONDO lists 'LN' for lobular neoplasia, and an abbreviation has other meanings."""
    name, synonyms = _fold(_cancer_map()["terms"][concept][0]), _cancer_map().get("names", {}).get(concept, ())
    return any(f == name or (len(f) > SHORT and f in synonyms) for f in map(_fold, texts))


def _fold(text): return "".join(nfc(text).split()).replace("-", "").lower()


def reading_default(readings, applied=None):
    """the reading selected when the choice screen opens: a cancer the text calls a cancer, else the one the read applied, else the
    first that is no cancer (None = not sure): the patient's cancer reorders the ADCs, so a misread one must not pass on Next."""
    ids = [o["mondo"] for o in readings]
    return next((o["mondo"] for o in readings if o.get("says_cancer")), None) or (applied if applied in ids else next((o["mondo"] for o in readings if not is_cancer(o["mondo"])), None))


def _scratch_link(r, typed="", read=None):
    """one row of scratch_runtime.judge in the linker's format: a MONDO concept gives its organs (from its label, its MONDO record
    or, without either, the organ output on the text); any other result is an AI judgment of the text. `judge_via` says which.
    typed: the text as entered, read: what the judge read (a Korean name's English name). They decide whether a numbered subtype
    stands and whether a cancer is the patient's: a cancer they do not name is offered, and the read is what comes after it."""
    texts = [typed] if read in (None, typed) else [typed, read]
    rows = _candidates(r, " ".join(texts)) if r["ok"] and r["concept"] else []
    first = rows[0] if rows else None
    unnamed = bool(first) and is_cancer(first["concept"]) and not _names_cancer(first["concept"], texts)
    if unnamed: first = next((x for x in rows[1:] if x["sim"] >= first["sim"] - TIE and x["concept"].startswith("MONDO:") and not is_cancer(x["concept"]) and not x.get("numbered")), None)
    if rows and first is None: r = dict(r, concept=None, name="", organs=list(r.get("judged") or []), via="name")
    elif first and first["concept"] != r["concept"]:
        r = dict(r, concept=first["concept"], name=first["name"], organs=first["organs"] or list(r.get("judged") or []), via=first["via"] if first["organs"] else "name")
    lk = dict(mondo=None, name="", sim=r["sim"], axes=[], valid=r["valid"], gate=r["ok"], readings=[], ambiguous=False, doubt=None, judge_via=r["via"], judge=True, p=r.get("p"),
              concept=r["concept"], concept_name=r["name"])
    if not r["ok"]: return lk
    lk["readings"], lk["ambiguous"] = _readings(rows, typed, r.get("low"))
    if is_cancer(r["concept"]): lk["ambiguous"] = False                                # named: nothing to ask
    if unnamed:
        lk["ambiguous"] = True
        if CANCER_WORD.search(" ".join(texts)): lk["readings"][0]["says_cancer"] = True
    if r.get("low"): lk["doubt"] = "low"
    elif r["concept"] and r["sim"] < CONFIRM: lk["doubt"] = "confirm"
    if r["concept"] and r["concept"].startswith("MONDO:"): lk.update(mondo=r["concept"], name=r["name"], axes=list(r["organs"]))
    elif r["organs"]: lk.update(judged=list(r["organs"]), sim=0.0, judge_via="name")
    return lk


def english(texts):
    """typed texts with Korean disease names replaced by their English KCD name (index v3+); other texts unchanged."""
    texts = [nfc(t) for t in texts]
    if not any(re.search("[가-힣]", t) for t in texts): return list(texts)
    import mondo_index as MI
    return [(MI.korean(t) if hasattr(MI, "korean") else None) or t for t in texts]


def analyze_conditions(conditions, progress=None):
    """-> one report per condition for the input review: how it was read (registry, the judge's concept, its AI judgment, a
    chosen reading, the patient's cancer, or not understood), its organs and the judge's organ probabilities."""
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and not _context(c)]
    picked = [c for c in conditions if c not in free and not _context(c)]
    if not free and not picked: return []
    links = _free_info(free, progress) if free else []
    _, _, _, notes, pc = resolve(conditions)
    organs = {c: sorted(axes, key=AXES.index) for c, axes, _ in pc}
    reports = []
    labels = {c: _reg[c if c in _reg else _by_label[c.lower()]]["label"] for c in picked}
    probs = _registry_p(list(labels.values()), progress)
    for c in picked:                                            # a registry disease: its curated organs; the judge's organ output beside them
        report = dict(condition=c, source="Registry", name=labels[c], mondo=_reg[c if c in _reg else _by_label[c.lower()]].get("mondo_id"),
                      organs=organs.get(c, []), readings=[], ambiguous=False, fallback=None, judge_via=None, p=probs.get(labels[c]))
        _ANALYSES[c] = report; reports.append(report)
    for c, link in zip(free, links):
        how = dict(notes)[c]
        concept = " (registry '" in how                          # the judge's concept stands for a registry condition: still the judge's organs
        source = (("MONDO" if link["concept"].startswith("MONDO:") else "Phenotype (HPO)") if concept else "Chosen" if "chosen reading" in how else "AI judgment" if "AI judgment" in how else "MONDO (no organ axis)" if "no organ axis" in how else "MONDO" if "; MONDO '" in how else
                  "Registry match" if "same as registry" in how else "Similar condition" if "borrowed from registry" in how else "Unmapped")
        name = ("" if source == "AI judgment" else link["concept_name"] if concept else link["name"] if source.startswith("MONDO") else re.search(r"chosen reading (?:MONDO|HPO) '(.*?)'", how).group(1) if source == "Chosen" else
                _reg[link["registry"][0]]["label"] if source != "Unmapped" else "")
        report = dict(condition=c, source=source, name=name, mondo=link.get("concept") if concept else link.get("mondo") if source.startswith("MONDO") else None, organs=[] if source == "Unmapped" else organs.get(c, []),
                      readings=link.get("readings", []), ambiguous=bool(link.get("ambiguous")), doubt=None if c in CHOICE else link.get("doubt"), fallback=link.get("fallback"),
                      judge_via=link.get("judge_via") if source.startswith("MONDO") or source == "AI judgment" or concept else _chosen_via(c) if source == "Chosen" else None,
                      p=link.get("p"))
        _ANALYSES[c] = report; reports.append(report)
    for c, (name, cancers) in patient_cancers(notes).items():     # the patient's cancer: no organs, the ADCs approved for it come first
        _ANALYSES[c].update(source="Cancer", name=name, mondo=re.search(r"\((MONDO:\d+)\)$", dict(notes)[c]).group(1), organs=[], p=None,
                            cancers=cancers, ambiguous=False, doubt=None, readings=[], judge_via=None, fallback=None)
    if progress: progress("done")
    return sorted(reports, key=lambda r: conditions.index(r["condition"]))


_REG_P = {}                     # registry name -> the organ judge's organ probabilities on it


def _registry_p(labels, progress=None):
    """{registry name: {axis: probability}} from the organ judge's organ output on the name, or None per name without the judge
    (models before 0.7, or the judge failed). The registry's own organs are what the recommendation uses."""
    need = [l for l in labels if l not in _REG_P]
    if need:
        try:
            import scratch_runtime as SR
            if SR.available():
                if progress: progress("judging")
                for l, r in zip(need, SR.judge(need)): _REG_P[l] = r.get("p")
        except Exception as error:
            warnings.warn(f"organ judge unavailable: {error}")
    return {l: _REG_P.get(l) for l in labels}


def resolve(conditions):
    """-> (s over AXES, own-organ set, registry ids present, [(input, how it was read)], [(input, its organs, its value)])"""
    ws, notes, ids, own_axes, pc = [np.zeros(len(AXES))], [], set(), set(), []
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and not _context(c)]
    if free: links = _free_info(free)
    fi = 0
    for c in conditions:
        if _context(c): ids.add(_context(c)); notes.append((c, CONTEXT[_context(c)])); continue
        cid = c if c in _reg else _by_label.get(c.lower())
        if not cid: lk = links[fi]; fi += 1
        mondo = _reg[cid].get("mondo_id") if cid else CHOICE.get(c) if c in CHOICE else cancer_alias(c) or (lk.get("mondo") if lk.get("gate") is not False and (lk.get("judge") or lk.get("sim", 0) >= LINK_THETA) else None)
        if is_cancer(mondo):                                    # the patient's cancer: the ADCs approved for it come first; not an organ
            notes.append((c, f"cancer; MONDO '{_cancer_map()['terms'][mondo][0]}' ({mondo})")); ws.append(np.zeros(len(AXES))); continue
        if cid:
            own, how = own_vec(cid), f"registry: {_reg[cid]['label']}"; ids.add(cid)
        else:
            near, sim = lk.get("registry") or (None, 0.0)            # portable build: the registry condition spelled most like the text
            rejected = lk.get("gate") is False; picked = CHOICE.get(c, "-")
            chosen = _chosen(picked) if c in CHOICE and picked else None
            if chosen:
                near = _by_concept.get(picked); own = np.zeros(len(AXES)); ids.update([near] if near else [])
                [own.__setitem__(AXES.index(a), float(_reg[near]["severity"]) if near else MONDO_SEVERITY) for a in chosen[1]]
                how = f"free text; chosen reading {'HPO' if picked.startswith('HP:') else 'MONDO'} '{chosen[0]}' -> organs: {', '.join(chosen[1]) or 'none'}"
            elif c in CHOICE and picked is None: own, how = np.zeros(len(AXES)), "free text; not understood (no organ); reading left open by the user"
            elif lk.get("judge") and (lk["axes"] or lk.get("judged")) and not rejected and lk.get("concept") in _by_concept:
                near = _by_concept[lk["concept"]]; organs = lk["axes"] or lk["judged"]; own = np.zeros(len(AXES)); ids.add(near)
                [own.__setitem__(AXES.index(a), float(_reg[near]["severity"])) for a in organs]
                how = f"free text; {lk['concept']} '{lk['concept_name']}' (registry '{_reg[near]['label']}') -> organs: {', '.join(organs)}"
            elif near and sim >= REG_NEAR: own, how = own_vec(near), f"free text; same as registry '{_reg[near]['label']}' (cos {sim:.2f})"; ids.add(near)
            elif lk["axes"] and not (GATE_MONDO and rejected):
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in lk["axes"]]
                how = f"free text; MONDO '{lk['name']}' (sim {lk['sim']:.2f}) -> organs: {', '.join(lk['axes'])}"
            elif lk.get("judged") and not rejected:                 # no concept with organs: the judge's organ output on the text
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in lk["judged"]]
                how = f"free text; AI judgment -> organs: {', '.join(lk['judged'])}"
            elif lk["axes"] == [] and (lk.get("mondo") if lk.get("judge") else lk.get("sim", 0) >= LINK_THETA) and not rejected and not lk.get("ambiguous"):
                own, how = np.zeros(len(AXES)), f"free text; MONDO '{lk['name']}' (sim {lk['sim']:.2f}) -> no organ axis"
            elif near and sim >= MATCH_COS: own, how = own_vec(near), f"free text; organs borrowed from registry '{_reg[near]['label']}' (cos {sim:.2f})"
            else: own, how = np.zeros(len(AXES)), "free text; not understood (no organ)"
        own_axes |= {AXES[k] for k in np.where(own > 0)[0]}
        if own.max() > 0: pc.append((c, {AXES[k] for k in np.where(own > 0)[0]}, float(own.max())))
        ws.append(own); notes.append((c, how))
    return np.maximum.reduce(ws), own_axes, ids, notes, pc


def _chosen(mondo):
    import mondo_index as MI
    if MI._IDX is None: MI._IDX = MI._load()                    # the names of the active bundle's index
    name, organs = MI.concept(mondo)
    if name and not organs and mondo.startswith("MONDO:"):
        try:
            import scratch_runtime as SR
            if SR.available() and not SR.concept_via(mondo):         # models 0.7+: as when its name is typed, the judge reads the name
                if mondo not in _CHOSEN_NAME:
                    r = SR.judge([name])[0]; _CHOSEN_NAME[mondo] = list(r["organs"]) if r["ok"] else []
                organs = _CHOSEN_NAME[mondo]
        except Exception as error:
            warnings.warn(f"organ judge unavailable: {error}")
    return (name, organs) if name else None


_CHOSEN_NAME = {}           # MONDO id -> the judge's organs for its name (a concept without label or record)


def _chosen_via(condition):
    """models 0.7+: label or record, for a reading picked from the list (the same organs the judge gives that concept)."""
    try:
        import scratch_runtime as SR
        picked = CHOICE.get(condition) or ""
        return SR.concept_via(picked) or ("name" if _CHOSEN_NAME.get(picked) else None)
    except Exception:
        return None


def ambiguous_conditions(conditions):
    """[(typed text, readings)] for free text whose readings point at different organs and that the user has not settled."""
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and not _context(c)]
    if not free: return []
    links = _free_info(free)
    return [(c, lk["readings"]) for c, lk in zip(free, links) if lk.get("ambiguous") and lk.get("gate") is not False and not cancer_alias(c)]   # not a disease name, or a named cancer: nothing to choose


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
    """typed conditions that map to no organ (the review lists them as unmapped)."""
    return [c for c, how in resolve(conditions)[3] if how.startswith("free text; not understood")]


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
    labs = dict(labs or {}); s, own_axes, ids, notes, pc = resolve(conditions); E, rules = _evidence(); adcs = sorted(E)
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
    p = RS.Patient(conditions=ids, organs=own_axes, **labs); V = RS.judge(p, adcs, rules); rows = []
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
    cancers = patient_cancers(notes)                   # a cancer among the conditions: the patient has that cancer only
    approved = {a for _, cs in cancers.values() for c in cs for a in _cancers().get(c, [])}
    for r in rows: r["cancers"] = sorted({c for _, cs in cancers.values() for c in cs})       # trial_lines() picks the cancer's trial
    for r in rows: r["indicated"] = not cancers or r["adc"] in approved
    first = next((set(o) for c, o, _ in pc if c == FIRST), None)
    hit = lambda r, k: sum(a in first for a in r[k]) if first else 0
    # a cancer: the ADCs approved for it first. A picked condition: its organs' boxed warnings, then warnings, come before
    # Monitor / Not studied; Avoid stays last
    order = lambda r: ((not r["indicated"],) if cancers else ()) + ((r["tier"] >= RS.TIER["avoid"], hit(r, "boxed"), hit(r, "warn")) if first else ()) + (r["tier"], r["verdict"].worst_known, r["Bl"], r["Wl"])
    rows.sort(key=lambda r: (order(r), r["name"]))
    prev = None
    for r in rows:
        k = order(r); r["tie"] = bool(prev and k == prev["key"]); r["rank"] = prev["rank"] if r["tie"] else (prev["rank"] + 1 if prev else 1)
        r["key"] = k; prev = r
    for i in range(len(rows) - 1):
        if rows[i + 1]["tie"]: rows[i]["tie"] = True
    return rows, {a: round(float(s[k]), 2) for k, a in enumerate(AXES) if s[k] > 0}, notes, checks(ids, E, V)


def checks(ids, E, V):
    """patient checklist: guideline / label tests the conditions call for, and the lab values that would settle a '?' restriction."""
    import yaml
    out = []
    for c in yaml.safe_load(open(R + "conf/patient_checks.yaml", encoding="utf-8"))["checks"]:
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
    """-> (plain text, painted text). Conditional rules name their missing input explicitly."""
    parts = RS.summary_parts(v)
    if not parts: return "-", "-"
    plain, out = [], []
    for c, ds, sure in parts:
        txt = f"{RS.TABLE[c]} ({', '.join(ds)})" + (" / Needs input" if not sure else "")
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


RANGE_TXT = [("crcl_ge", "crcl_lt", "CLcr {} to <{}"), ("bili_gt", "bili_le", "bilirubin >{} to {}×ULN"),
             ("ast_gt", "ast_le", "AST >{} to {}×ULN"), ("alt_gt", "alt_le", "ALT >{} to {}×ULN")]


def _when(w):
    parts = []; w = dict(w)
    for lo, hi, text in RANGE_TXT:                     # a band reads as the label writes it: 'bilirubin >1.5 to 3×ULN', 'CLcr 30 to <90'
        if lo in w and hi in w: parts.append(text.format(w.pop(lo), w.pop(hi)))
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
        if d in silent and not silent[d] and all(RS.TIER[c] < RS.TIER["no_statement"] for c, _ in po): po = []     # as summary(): the unstated state outranks what is below it
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


ORGAN_SHORT = {"haematologic": "Blood", "hepatic": "Liver", "cardiovascular": "Cardio", "pulmonary": "Lung", "renal": "Kidney",
               "gastrointestinal": "GI", "neurologic": "Neuro", "ocular": "Eye", "dermatologic": "Skin", "metabolic_endocrine": "Metabolic",
               "musculoskeletal": "MSK", "infectious_immune": "Immune", "otologic": "Ear"}


def _organ_preview(row):
    """Display up to two patient warning organs and one other warning organ. Does not affect ADC ordering.

    Boxed warnings precede section-5 warnings. Within a warning tier, use the patient's existing organ priority;
    equal-priority organs retain the axis order. '+' means additional organs have a label warning.
    """
    priorities = {}
    for level, _, organs in row["priority"]:
        for organ in organs: priorities[organ] = min(level, priorities.get(organ, level))
    patient = set(priorities) | set(row["boxed"]) | set(row["warn"])
    strength = {"boxed": 0, "W&P": 1}
    key = lambda organ: (strength[row["organs"][organ]["level"]], priorities.get(organ, 999), AXES.index(organ))
    own = sorted(set(row["boxed"]) | set(row["warn"]), key=key)
    other = sorted((organ for organ in AXES if organ not in patient and row["organs"][organ]["level"] in strength),
                   key=lambda organ: (strength[row["organs"][organ]["level"]], AXES.index(organ)))
    def cell(organ, more=False, blank=False):
        if not organ: return "" if blank else "\033[90m-\033[0m"
        boxed = row["organs"][organ]["level"] == "boxed"
        marker = "!!" if boxed else "!"
        return f"\033[{31 if boxed else 33}m{marker:>2} {ORGAN_SHORT[organ]}{'+' if more else ''}\033[0m"
    return [cell(own[0] if own else None), cell(own[1] if len(own) > 1 else None, len(own) > 2, blank=bool(own)),
            cell(other[0] if other else None, len(other) > 1)]


def _ljust(text, size): return text + " " * max(0, size - _width(text))


def _result_list(rows, width):
    """Responsive result list with the warning organs visible alongside each ADC's restriction."""
    import tui
    paint = lambda t, c: f"\033[{c}m{t}\033[0m" if c else t
    strip = lambda text: re.sub(r"\x1b\[[\d;]*m", "", text)
    name_w = max([_width(r["name"]) for r in rows] + [3])
    wide = width >= 90
    stacked = width < 64
    name_w = min(name_w, 28 if wide else max(12, width // 2))
    organ_w = 12
    if wide: name_w = min(name_w, width - 9 - 3 * (organ_w + 3) - len("Label restriction"))
    status_w = max(2, width - name_w - 9 - (3 * (organ_w + 3) if wide else 0))
    widths = [name_w, status_w] + ([organ_w] * 3 if wide else [])
    def line(rank, cells):
        return rank + "   " + "   ".join(text + " " * max(0, size - _width(strip(text))) for text, size in zip(cells, widths))
    if wide:
        out = [line("  #", ["ADC", "Label restriction"]) + "   " + _ljust("Patient organs", 2 * organ_w + 3) + "   " + "Other"]
    else:
        out = ["  #   ADC"] if stacked else [line("  #", ["ADC", "Label restriction"])]
    out.append("\033[90m" + "─" * width + "\033[0m")
    at = []; previous_rank = None
    for row in rows:
        if not row.get("indicated", True) and (not at or rows[len(at) - 1].get("indicated", True)):    # the ADCs for other cancers (all of them: none is approved for the patient's)
            out.append("\033[90m── Other cancers " + "─" * max(0, width - 17) + "\033[0m")
        at.append(len(out))
        rank_text = f"{row['rank']:>3}" if row["rank"] != previous_rank else "   "
        previous_rank = row["rank"]
        verdict = row["verdict"]
        # Four display groups only. Exact label actions (including dose reduction / contraindication)
        # and whether a rule is still conditional remain explicit in the selected row's reasons.
        tier = verdict.worst_possible
        state, tone = {0: ("None", "32"), 1: ("Monitor", "36"), 2: ("No data", "33"),
                       3: ("Avoid", "31"), 4: ("Avoid", "31")}.get(tier, ("None", "90"))
        if tier == 2 and any(c == "insufficient_data" for c, _ in verdict.known + verdict.possible): state = "Not studied"
        sure = verdict.worst_known == tier
        status = paint(state + ("" if sure else "?"), tone + (";1" if sure else ""))   # ?: it depends on a value not entered
        organs = _organ_preview(row)
        if stacked:
            names = tui._wrap(row["name"], max(2, width - 6), "")
            out.append(rank_text + "   " + names[0])
            out.extend("      " + ln for ln in names[1:])
            out.extend("      " + ln for ln in tui._wrap_ansi(status, max(2, width - 6)))
        else:
            names = tui._wrap(row["name"], name_w, "")
            columns = [names, tui._wrap_ansi(status, status_w)]
            if wide: columns += [tui._wrap_ansi(organ, organ_w) for organ in organs]
            for i in range(max(map(len, columns))):
                rank = rank_text if i == 0 else "   "
                out.append(line(rank, [column[i] if i < len(column) else "" for column in columns]))
        if not wide:
            mine = [o for o in organs[:2] if strip(o) not in ("", "-")]
            summary = "Patient: " + (" ".join(mine) or "-") + "   Other: " + organs[2]
            out.extend("      " + ln for ln in tui._wrap_ansi(summary, max(2, width - 6)))
    return out, at


def _compact_line(text, width):
    """Keep a summary on one terminal line; an ellipsis explicitly marks shortened text."""
    import tui
    if _width(re.sub(r"\x1b\[[\d;]*m", "", text)) <= width: return text
    return tui._wrap_ansi(text, max(2, width - 1))[0] + "\033[90m…\033[0m"


def _missing_inputs(verdict):
    """the values not entered that could still change this ADC's restriction (only those: an entered bilirubin is not listed)."""
    if getattr(verdict, "inputs", None): return list(verdict.inputs)
    short = {"renal": "CLcr / dialysis status", "hepatic": "Bilirubin / AST / ALT / Child-Pugh", "cardiac": "LVEF",
             "blood": "Platelets / ANC", "metabolic": "HbA1c"}
    return [short.get(next((d for d, text in RS.NEEDS.items() if text == need), ""), need) for need in verdict.missing]


_MECH = None


def _mechanisms():
    """adc -> payload, family, mechanism, linker and the teammates' mechanism note (data/curated/competition/
    adc_mechanism_draft.csv, ml/competition_tables.py); the app build embeds it (ml/build_portable.py)."""
    global _MECH
    if _MECH is None:
        try:
            from __adc_data__ import _portable_data                                   # the app build carries the table
            _MECH = _portable_data().get("mechanisms", {})
        except ImportError:
            _MECH = read_mechanisms(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "competition", "adc_mechanism_draft.csv"))
    return _MECH


_IND = None


def _indications():
    """adc -> the label's section 1 indications, short (data/curated/competition/adc_indications.csv); the app build embeds it."""
    global _IND
    if _IND is None:
        try:
            from __adc_data__ import _portable_data
            _IND = _portable_data().get("indications", {})
        except ImportError:
            _IND = read_mechanisms(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "competition", "adc_indications.csv"))
    return _IND


# payload / linker codes of the mechanism table, as a reader writes them
MECH_TXT = {"tubulin": "microtubule inhibitor", "topo1": "topoisomerase I inhibitor", "dna_cleave": "DNA strand breaks",
            "dna_crosslink": "DNA crosslinking", "ign": "indolinobenzodiazepine", "pbd": "pyrrolobenzodiazepine",
            "hydrazone_AcBut_disulfide": "AcBut hydrazone", "IGN_peptide": "peptide", "sulfo_SPDB": "sulfo-SPDB",
            "val_ala_PABC_PEG8": "Val-Ala PABC (PEG8)", "vc_PABC": "Val-Cit PABC", "mc": "maleimidocaproyl (mc)"}


def payload_line(mech):
    """'MMAE (auristatin), microtubule inhibitor; Val-Cit PABC linker, cleavable; bystander effect; target CD30'"""
    t = lambda x: MECH_TXT.get(x, x)
    return (f"{mech['payload']} ({t(mech['payload_family'])}), {t(mech['mechanism'])}; {t(mech['linker'])} linker, "
            + ("cleavable" if mech["linker_cleavable"] == "True" else "non-cleavable") + ("; bystander effect" if mech["bystander"] == "True" else "")
            + (f"; target {mech['target']}" if mech.get("target") else ""))


def warning_names(headings):
    """the label's warning names on one organ, without section numbers; a name inside another (the boxed warning's capitals
    within its section 5 heading) is shown once, as the longer: [("Boxed", "INTERSTITIAL LUNG DISEASE"), ("5.1", "Interstitial
    Lung Disease/Pneumonitis")] -> 'Interstitial Lung Disease/Pneumonitis'"""
    heads = list(dict.fromkeys(head for _, head in headings))
    keep = [h for i, h in enumerate(heads) if not any(h.lower() in o.lower() and (h.lower() != o.lower() or (h.isupper() and not o.isupper()) or (h == o and j < i))
                                                    for j, o in enumerate(heads) if j != i)]
    return "; ".join(keep)


def organ_warning_lines(row):
    """the label warnings on this patient's organs, the boxed one first: '  Lung      !!  Interstitial Lung Disease/Pneumonitis'"""
    return [f"  {ORGAN_SHORT[a]:<9} {marks}  {warning_names(row['organs'][a].get('headings', []))}"
            for marks, organs in (("!!", row.get("boxed", [])), ("! ", row.get("warn", []))) for a in organs]


def patient_organs(row):
    """the organs the patient's conditions marked: those with a boxed warning on this label first, then a W&P warning, then the rest in axis order"""
    mine = {o for _, _, organs in row.get("priority", []) for o in organs}
    warned = list(row.get("boxed", [])) + list(row.get("warn", []))
    return warned + sorted(mine - set(warned), key=AXES.index)


def _event_text(e):
    """'pneumonitis 18/257 (7.0%, vs 0.4%), serious 1/257'; an event reported only as serious: 'interstitial lung disease serious 5/257 (1.9%)'"""
    pct = lambda a, n: f"{100 * a / n:.1f}%"
    text = f"{e['term']} {'serious ' if e['serious'] else ''}{e['a']}/{e['n']} ({pct(e['a'], e['n'])}" + (f", vs {pct(*e['comp'])}" if e.get("comp") else "") + ")"
    return text + (f", serious {e['sa']}/{e['n']}" if e.get("sa") and not e["serious"] else "")


def trial_lines(row):
    """ClinicalTrials.gov results of the ADC's main trial on the patient's organs (data/curated/competition/trial_ae.json,
    ml/build_trial_ae.py): the trial and its comparator, then one line per organ with the events the label warning on that organ
    is about, or, where the label has no warning, the organ's most frequent event and its most frequent serious event."""
    T = _trial_ae().get("adcs", {}).get(row.get("adc"))
    if not T: return []
    if not T["trials"]:
        t = T["no_results"][0]; return [f"  no results posted on ClinicalTrials.gov ({t['trial']}, {t['nct']})"]
    t = next((t for t in T["trials"] if set(t["cancers"]) & set(row.get("cancers", []))), T["trials"][0])      # the patient's cancer's trial when known
    out = [f"  {t['trial']}, {t['regimen']}, n={t['n']}" + (f"; vs {t['comparator']['regimen']}, n={t['comparator']['n']}" if t.get("comparator") else "")]
    none = "none reported" if not t["threshold"] else f"none at or above {t['threshold']:g}%, none serious"
    for a in patient_organs(row):
        o = t["organs"].get(a, {})
        evs = o.get("warned") or [e for e in (o.get("any"), o.get("serious")) if e]
        if len(evs) == 2 and evs[0]["term"] == evs[1]["term"]: evs = evs[:1]
        out.append(f"  {ORGAN_SHORT[a]:<9} " + ("; ".join(_event_text(e) for e in evs) or none))
    return out


def trial_scale(events):
    """the bars' full length in %: the smallest of 5, 10, 20, 30, 50, 100 that holds every ADC and comparator rate"""
    top = max([100 * e["a"] / e["n"] for e in events] + [100 * e["comp"][0] / e["comp"][1] for e in events if e.get("comp")] + [1])
    return next((v for v in (5, 10, 20, 30, 50, 100) if v >= top), 100)


def trial_bars(row, cells=20):
    """trial_lines for the detail panel: the trial line, a legend with the scale, then per organ each event's name and two bars
    on one scale, the ADC's (amber, its serious part red) and the comparator's (grey), each with its rate; the counts stay in
    trial_lines (the report)."""
    T = _trial_ae().get("adcs", {}).get(row.get("adc"))
    if not T or not T["trials"]: return trial_lines(row)
    t = next((t for t in T["trials"] if set(t["cancers"]) & set(row.get("cancers", []))), T["trials"][0])
    head = trial_lines(row)[0]; none = "none reported" if not t["threshold"] else f"none at or above {t['threshold']:g}%, none serious"
    rows_ = []
    for a in patient_organs(row):
        o = t["organs"].get(a, {})
        evs = o.get("warned") or [e for e in (o.get("any"), o.get("serious")) if e]
        if len(evs) == 2 and evs[0]["term"] == evs[1]["term"]: evs = evs[:1]
        rows_.append((a, evs))
    scale = trial_scale([e for _, evs in rows_ for e in evs])
    def bar(f, ser, color):
        n = min(cells, round(100 * f / scale * cells)); k = min(n, round(100 * ser / scale * cells))
        n = max(n, 1) if f > 0 else 0
        return (f"\033[31m{'━' * k}\033[0m" if k else "") + f"\033[{color}m{'━' * (n - k)}\033[0m\033[90m{'─' * (cells - n)}\033[0m"
    pct = lambda a, n: f"{100 * a / n:.1f}%"
    out = [head, "  \033[33m━\033[0m ADC  \033[31m━\033[0m Serious  \033[90m━ Comparator   0 to " + f"{scale}%\033[0m"]
    pad = " " * 12
    for a, evs in rows_:
        if not evs: out.append(f"  {ORGAN_SHORT[a]:<9} \033[90m{none}\033[0m"); continue
        for i, e in enumerate(evs):
            out.append(f"  {ORGAN_SHORT[a] if i == 0 else '':<9} {e['term']}" + (" (serious)" if e["serious"] else ""))
            ser = e["a"] / e["n"] if e["serious"] else (e.get("sa") or 0) / e["n"]
            out.append(pad + bar(e["a"] / e["n"], ser, "33") + f" {pct(e['a'], e['n'])}")
            if e.get("comp"): out.append(pad + bar(e["comp"][0] / e["comp"][1], 0, "90") + f" \033[90m{pct(*e['comp'])}\033[0m")
    return out


_CAN = _CM = _TA = None


def _trial_ae():
    """{"snapshot", "adcs": {adc: {"trials": [...], "no_results": [...]}}} (data/curated/competition/trial_ae.json, ml/build_trial_ae.py);
    the app build embeds it."""
    global _TA
    if _TA is None:
        try:
            from __adc_data__ import _portable_data
            _TA = _portable_data().get("trial_ae", {})
        except ImportError:
            try: _TA = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "competition", "trial_ae.json"), encoding="utf-8"))
            except OSError: _TA = {}
    return _TA


def _cancers():
    """cancer -> the ADCs approved for it, from the labels' section 1 (data/curated/competition/adc_cancers.csv); the app build embeds it."""
    global _CAN
    if _CAN is None:
        try:
            from __adc_data__ import _portable_data
            _CAN = _portable_data().get("cancers", {})
        except ImportError:
            import csv
            try: _CAN = {r["cancer"]: r["adcs"].split(";") for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "competition", "adc_cancers.csv"), encoding="utf-8"))}
            except OSError: _CAN = {}
    return _CAN


def _cancer_map():
    """{"terms": {MONDO id: [name, [cancers]]}, "aliases": {folded name: MONDO id}} (data/curated/competition/cancer_mondo.json,
    ml/build_cancer_mondo.py); the app build embeds it."""
    global _CM
    if _CM is None:
        try:
            from __adc_data__ import _portable_data
            _CM = _portable_data().get("cancer_mondo", {})
        except ImportError:
            import json
            try: _CM = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "competition", "cancer_mondo.json"), encoding="utf-8"))
            except OSError: _CM = {}
    return _CM


def cancer_alias(text):
    """the MONDO cancer a typed name stands for when the disease linker misreads it (폐암 -> pneumoconiosis), else None"""
    return _cancer_map().get("aliases", {}).get("".join(nfc(text).split()).replace("-", "").lower())


def is_cancer(mondo):
    return bool(mondo) and mondo in _cancer_map().get("terms", {})


def patient_cancers(notes):
    """{condition: (MONDO name, [cancers from adc_cancers.csv])} for the conditions read as the patient's cancer"""
    terms = _cancer_map().get("terms", {}); out = {}
    for c, how in notes:
        m = re.match(r"cancer; MONDO '.*' \((MONDO:\d+)\)$", how)
        if m and m.group(1) in terms: out[c] = tuple(terms[m.group(1)])
    return out


def preload():
    """load the organ judge in the background while the doctor types: the first analysis waited for it."""
    import threading
    def work():
        try:
            import scratch_runtime as SR
            if SR.available(): SR.load()
        except Exception as error:
            warnings.warn(f"preload: {error}")
    threading.Thread(target=work, daemon=True).start()


def read_mechanisms(path):
    import csv
    try: return {r["adc"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}
    except OSError: return {}


def _result_details(row, checks_, width):
    """Complete restriction reasons and checks; the viewer wraps and scrolls this panel."""
    paint = lambda t, c: f"\033[{c}m{t}\033[0m" if c else t
    out = [paint(row["name"], "33;1")]
    ind = _indications().get(row.get("adc"))
    if row.get("cancers"):                                                      # the entered cancer: ✓ approved for it, ✕ not
        out.append(paint(("✓ " if row.get("indicated", True) else "✕ ") + ", ".join(row["cancers"]), "32;1" if row.get("indicated", True) else "33;1"))
    if ind: out.append(paint("  " + ind["indication"], "90"))                     # what it is approved for (label section 1)
    evidence = reason_rows(row)
    evidence = [reason for reason in evidence if reason[3] != "no_adjustment"] or evidence
    evidence.sort(key=lambda reason: (-RS.TIER[reason[3]], not reason[4], reason[0]))
    for organ, status, basis, code, sure in evidence:
        out.append(f"  {organ.capitalize():<9} " + paint(status, TONE[code] + (";1" if sure else "")) + f"   {basis}")
    if not evidence: out.append("  No applicable label restriction")
    warned = organ_warning_lines(row)
    if warned:
        out.append(paint("─" * width, "90"))
        out.append(paint("Warnings on the patient's organs", "33;1"))
        out.extend(warned)
    trial = trial_bars(row)
    if trial:
        out.append(paint("─" * width, "90"))
        out.append(paint("Trial results on the patient's organs", "33;1"))
        out.extend(trial)
    if row["verdict"].missing:
        out.append(paint("─" * width, "90"))
        out.append(paint("Missing inputs", "33;1"))
        out.extend("  " + need for need in _missing_inputs(row["verdict"]))
    mech = _mechanisms().get(row.get("adc"))
    if mech:
        out.append(paint("─" * width, "90"))
        out.append(paint("Payload and linker", "33;1"))
        out.append("  " + payload_line(mech))
        note = mech.get("mechanism_note", "")                                          # the label's own 12.1 text, verbatim
        keep = [x for x in re.split(r"(?<=\.)\s+(?=[A-Z])", note) if re.search(re.escape(mech["payload"]) + r"|microtubul|topoisomerase|DNA", x)][:2]
        if keep: out.append("  " + " ".join(keep))
    mine = [test for test, names, _ in checks_ if (not names or row["name"] in names) and not test.startswith("enter ")]
    if mine:
        out.append(paint("─" * width, "90"))
        out.append(paint("Pre-treatment checks", "33;1"))
        out.extend("  - " + test for test in mine)
    return out


VALUE_LABELS = {"crcl": ("CLcr", " mL/min"), "bili": ("Bilirubin", "×ULN"), "ast": ("AST", "×ULN"), "alt": ("ALT", "×ULN"),
                "lvef": ("LVEF", "%"), "platelets": ("Platelets", " ×10³/µL"), "anc": ("ANC", " ×10³/µL"), "hba1c": ("HbA1c", "%"),
                "child_pugh": ("Child-Pugh", ""), "esrd": ("Dialysis/ESRD", ""), "ugt1a1_28_homozygous": ("UGT1A1*28 hom.", "")}
DOMAIN_VALUES = {"renal": ("crcl", "esrd"), "hepatic": ("bili", "ast", "alt", "child_pugh"), "cardiac": ("lvef",),
                 "blood": ("platelets", "anc"), "metabolic": ("hba1c",), "genotype": ("ugt1a1_28_homozygous",)}


# lab-report values already shown through a restriction input (CLcr, x ULN, ...), so not listed again
_SHOWN_AS = {"bilirubin": "bili", "ast": "ast", "alt": "alt", "platelet": "platelets", "anc": "anc", "hba1c": "hba1c", "lvef": "lvef",
             "child_pugh": "child_pugh", "ugt1a1": "ugt1a1_28_homozygous", "age": "crcl", "sex": "crcl", "weight": "crcl", "creatinine": "crcl", "egfr": "crcl",
             "uln_bilirubin": "bili", "uln_ast": "ast", "uln_alt": "alt"}


def _raw_values(raw, values):
    """entered lab values that no restriction input shows, each with the organ it marked (ml/labs.py FLAGS): 'Hb 8 g/dL → Blood'."""
    import labs as LB
    out = []
    for k, label, unit, _ in LB.FIELDS:
        v = (raw or {}).get(k)
        if v is None or values.get(_SHOWN_AS.get(k, "")) is not None: continue
        text = ("yes" if v else "no") if isinstance(v, bool) else f"{v:g}" if isinstance(v, (int, float)) else str(v)
        organs = [o for key, test, o, _ in LB.FLAGS if key == k and isinstance(v, (int, float)) and test(v, LB.uln_of(raw).get(k))]
        text += f" {unit}" if isinstance(v, (int, float)) and not isinstance(v, bool) else ""       # 'Sex F', not 'Sex F M/F'
        out.append((bool(organs), f"{label} {text}" + (" → " + ", ".join(ORGAN_SHORT[o] for o in dict.fromkeys(organs)) if organs else "")))
    return [t for _, t in sorted(out, key=lambda x: not x[0])]           # the ones that marked an organ first


def _value_gauges(items, cells=10):
    """Key values as name | value | gauge, the gauges starting in one column: x ULN on 0 to 3 (ticks at 1 and 1.5), CLcr on
    0 to 120 mL/min (ticks at 30, 60, 90); amber past a tick that matters, red past the last; other values keep their → organ."""
    parsed = []
    for text in items:
        m = re.match(r"^(.*?)\s((?:≈\s)?[\d.]+.*?)(?:\s→\s(.+))?$", text)
        parsed.append(m.groups() if m else (text, "", None))
    wn = max((len(n) for n, _, _ in parsed), default=0); wv = max((len(v) for _, v, _ in parsed), default=0); out = []
    for name, val, organ in parsed:
        g = ""
        uln = re.match(r"^([\d.]+)×ULN\b", val); cl = name.startswith("CLcr") and re.search(r"([\d.]+)", val)
        if uln: x = float(uln.group(1)); f, ticks, tone = x / 3, (1 / 3, .5), "31" if x > 3 else "33" if x > 1 else "90;1"
        elif cl: x = float(cl.group(1)); f, ticks, tone = x / 120, (.25, .5, .75), "31" if x < 30 else "33" if x < 60 else "90;1"
        if uln or cl:
            n = max(1, min(cells, round(f * cells))); tk = {round(t * cells) for t in ticks}
            g = "".join(f"\033[{tone}m━\033[0m" if i < n else ("\033[90m┼\033[0m" if i in tk else "\033[90m─\033[0m") for i in range(cells))
        tail = f"\033[33m→ {organ}\033[0m" if organ else ""
        out.append(f"{name:<{wn}}  {val:>{wv}}  " + (g + (" " + tail if tail else "") if g else (" " * cells + "  " + tail if tail else "")).rstrip())
    return out


def _result_context(rows, notes, width, values=None, selected=0, graphic=False, raw=None):
    """Bounded key values and organ priority, without repeating diagnoses from the input screen."""
    import labs as LB
    values = values or {}
    prio = rows[0]["priority"] if rows else []
    reasons_ = sorted(reason_rows(rows[selected]), key=lambda reason: (-RS.TIER[reason[3]], not reason[4])) if rows else []
    relevant = list(dict.fromkeys(key for domain, *_ in reasons_ for key in DOMAIN_VALUES.get(domain, ())))
    ordered = sorted((key for key in VALUE_LABELS if values.get(key) is not None),
                     key=lambda key: relevant.index(key) if key in relevant else len(relevant))
    inputs = []
    for key in ordered:
        label, unit = VALUE_LABELS[key]; value = values[key]
        text = ("yes" if value else "no") if isinstance(value, bool) else (LB.shown(key, value) if isinstance(value, (int, float)) else str(value))
        if key == "crcl" and any(a == "Lab" and "CLcr ≈ eGFR" in b for a, b in notes):
            inputs.append(f"CLcr ≈ {text} mL/min (eGFR)")
        else: inputs.append(f"{label} {text}{unit}" + LB.uln_text(key, raw))
    inputs += _raw_values(raw, values)
    if graphic: inputs = _value_gauges(inputs)
    organ_levels = {}
    for level, _, organs in prio:
        for organ in organs: organ_levels[organ] = min(level, organ_levels.get(organ, level))
    grouped = {}
    for organ, level in sorted(organ_levels.items(), key=lambda item: (item[1], AXES.index(item[0]))):
        grouped.setdefault(level, []).append(organ)
    if graphic:                                                # the result screen: one organ strip per level (green = that level's organs)
        import tui
        tiers = [tui.strip(AXES, organs) if k == 0 else "\033[32m" + " ".join(ORGAN_SHORT[o] for o in organs) + "\033[0m" for k, organs in enumerate(grouped.values())]
        priorities = ["  \033[90m→\033[0m  ".join(tiers)] if tiers else []         # first tier bright, the later ones plain, in order
    else: priorities = [" → ".join(", ".join(ORGAN_SHORT[o] for o in organs) for organs in grouped.values())] if grouped else []
    def block(title, items, empty):
        body = items[:3] + ([f"+ {len(items) - 3} more"] if len(items) > 3 else [])
        return [f"\033[33;1m{title}\033[0m"] + ["  " + text for text in body or [empty]]
    left = block("Key values", inputs, "Not entered")
    right = block("Review order", priorities, "None specified")
    if width < 72:
        out = [_compact_line(text, width) for text in left + [""] + right]
    else:
        half = (width - 3) // 2
        left = [_compact_line(text, half) for text in left]
        right = [_compact_line(text, width - half - 3) for text in right]
        out = []
        for i in range(max(len(left), len(right))):
            a = left[i] if i < len(left) else ""; b = right[i] if i < len(right) else ""
            padding = half - _width(re.sub(r"\x1b\[[\d;]*m", "", a))
            out.append(a + " " * padding + "\033[90m │ \033[0m" + b)
    unmapped = [c for c, how in notes if "not understood" in how]
    if unmapped:
        estimated = any("learned estimate x" in how for _, how in notes)
        out.append(_compact_line(("Unvalidated estimate: " if estimated else "Unmapped: ") + ", ".join(unmapped), width))
    return out


def browse(rows, checks_=(), notes=(), labs=None, raw=None, scr=None, crumbs=None):
    """interactive view of the result table (terminal only): pick a row to read why it has its restriction.
    scr / crumbs: draw inside the wizard's session (form.run) instead of a session of its own."""
    import tui, labs as LB
    values = {**(LB.derive(raw)[0] if raw else {}), **(labs or {})}
    return tui.browse("ADC 추천 결과", lambda w: _result_list(rows, w), [],
                      lambda i, w: _result_details(rows[i], checks_, w),
                      footer="!! Boxed warning   ! Warning",
                      context=lambda i, w: _result_context(rows, notes, w, values, i, graphic=True, raw=raw), scr=scr, crumbs=crumbs)


def patient_lines(notes):
    """[(English name, Korean name or how it was read, or None for a plain note line)] for the Patient block."""
    def names(c, how):
        cid = c if c in _reg else _by_label.get(c.lower())
        if cid: return _reg[cid]["label"], KO.get(cid, "")
        if _context(c): return CONTEXT[_context(c)], ""
        if c == "Lab": return how, None
        if c.startswith("Lab: "): return c[5:], "(" + EN[how.rsplit(": ", 1)[-1]] + ")"
        m = re.search(r"(?:MONDO|registry) '([^']+)'", how)
        if "not understood" in how: return c, "(장기 미확인)" + ("  learned estimate, not validated" if "learned estimate" in how else "")
        return c, f"({m.group(1)})" if m else ""
    return [names(a, b) for a, b in notes]


def render(rows, s, notes, checks_, detail=False, color=None, labs=None, raw=None):
    """Print the same responsive list as the interactive view, followed by bounded-width checks."""
    import shutil, tui, labs as LB
    color = (sys.stdout.isatty() or bool(os.environ.get("FORCE_COLOR"))) and not os.environ.get("NO_COLOR") if color is None else color
    paint = lambda t, c: f"\033[{c}m{t}\033[0m" if color and c else t
    width = max(10, shutil.get_terminal_size((110, 24)).columns - 5)
    strip = lambda text: re.sub(r"\x1b\[[\d;]*m", "", text)
    def emit(text=""):
        for line in tui._wrap_ansi(text, width): print("  " + (line if color else strip(line)).rstrip())
    def heading(text):
        emit(); emit(paint(text, "33;1"))
    emit(paint("ADCTOX", "33;1") + " " * max(1, width - 6 - len(tui.UI_VERSION)) + paint(tui.UI_VERSION, "90"))
    emit(paint("─" * width, "90")); emit()
    values = {**(LB.derive(raw)[0] if raw else {}), **(labs or {})}
    for line in _result_context(rows, notes, width, values, raw=raw): emit(line)
    emit()
    for line in _result_list(rows, width)[0]: emit(line)
    emit(paint("!! Boxed warning   ! Warning", "90"))
    actions = [(r, reason) for r in rows for reason in reason_rows(r) if reason[3] in ("reduce_dose", "contraindicated")]
    if actions:
        heading("Label actions")
        for row, (organ, status, basis, code, certain) in actions:
            emit(f"{row['name']} / {organ.capitalize()}")
            emit("  " + paint(status, TONE[code]) + f"   {basis}")
    analyses = [_ANALYSES[c] for c, _ in notes if c in _ANALYSES and _ANALYSES[c]["source"] != "Registry"]     # typed text only
    if analyses:
        heading("AI organ analysis")
        for report in analyses:
            organs = "Cancer" if report["source"] == "Cancer" else ", ".join(ORGAN_SHORT[a] for a in report["organs"]) or no_organ_text(report)
            src = "MONDO" if report["source"].startswith("MONDO") or report["source"] == "Cancer" else report["source"] if report["source"] != "Unmapped" else ""
            if src and report.get("judge_via"): src += f" ({report['judge_via']})"      # label, record or name: what set the organs
            read = f"   ({src}: {report['name']})" if report["name"] else (f"   ({src})" if src else "")
            emit(f"{report['condition']} → {organs}" + paint(read, "90"))
    missing = list(dict.fromkeys(need for row in rows for need in _missing_inputs(row["verdict"])))
    if missing:
        emit(); emit(paint("─" * width, "90")); emit(paint("Missing inputs", "33;1"))
        for need in missing: emit("  " + need)
    clinical_checks = [(test, names, src) for test, names, src in checks_ if not test.startswith("enter ")]
    if clinical_checks:
        heading("Pre-treatment checks")
        for test, names, src in clinical_checks:
            emit(f"- {test}")
            if names: emit(paint("  ADCs: " + ", ".join(names), "90"))
    if detail:
        heading("Label evidence on your organs")
        for r in rows:
            emit(r["name"])
            for a in AXES:
                if a in s:
                    o = r["organs"][a]; hd = warning_names(o["headings"]) or "no warning"
                    emit(f"  {EN[a]} / {o['level']} / {hd} / {_inc_text(o)}")
        heading("Trial results on your organs")
        for r in rows:
            emit(r["name"])
            for line in trial_lines(r): emit(line)


# ------------------------------------------------------------------------------------------------ input
ORGAN_KO = {"haematologic": "혈액", "hepatic": "간", "cardiovascular": "심혈관", "pulmonary": "폐", "renal": "신장", "gastrointestinal": "위장관",
            "neurologic": "신경", "ocular": "눈", "dermatologic": "피부", "metabolic_endocrine": "대사/내분비", "musculoskeletal": "근골격",
            "infectious_immune": "감염/면역", "otologic": "귀"}
KO = {"chronic_liver_disease": "만성 간질환", "cirrhosis": "간경변", "hepatitis_b_chronic": "만성 B형 간염", "hepatitis_c_chronic": "만성 C형 간염",
      "hepatic_vod_history": "간정맥폐쇄병 병력", "nafld": "비알코올성 지방간", "ckd_stage_3": "만성 콩팥병 3기", "ckd_stage_4_5": "만성 콩팥병 4–5기",
      "dialysis": "말기 신부전 또는 투석", "heart_failure": "심부전", "reduced_lvef": "좌심실 박출률 저하", "prior_anthracycline": "안트라사이클린 치료 경험",
      "coronary_artery_disease": "관상동맥질환", "qt_prolongation": "QT 연장", "interstitial_lung_disease": "간질성 폐질환", "pulmonary_fibrosis": "폐섬유증",
      "copd": "만성 폐쇄성 폐질환", "prior_chest_radiation": "흉부 방사선 치료 경험", "peripheral_neuropathy": "말초신경병증",
      "diabetic_neuropathy": "당뇨병성 말초신경병증", "multiple_sclerosis": "다발성 경화증", "keratopathy_history": "각막병증 병력", "dry_eye": "안구건조증",
      "glaucoma": "녹내장", "prior_corneal_surgery": "각막 수술 경험", "thrombocytopenia": "혈소판감소증", "itp": "면역 혈소판감소증",
      "neutropenia_chronic": "만성 호중구감소증", "anaemia_chronic": "만성 빈혈", "mds": "골수형성이상증후군", "prior_hsct": "조혈모세포이식 경험",
      "inflammatory_bowel_disease": "염증성 장질환", "prior_bowel_resection": "장 절제술 경험", "chronic_pancreatitis": "만성 췌장염",
      "severe_psoriasis": "중증 건선", "prior_sjs_ten": "스티븐스-존슨 증후군/TEN 병력", "type_2_diabetes": "제2형 당뇨병", "hypothyroidism": "갑상선기능저하증",
      "hiv_controlled": "치료 중인 HIV 감염", "active_autoimmune": "활동성 자가면역질환", "hearing_loss": "감각신경성 난청"}


def no_organ_text(report):
    """what an empty organ list means: a recognised disease outside the 13 organs, or text that was not understood."""
    if report.get("source") in ("MONDO (no organ axis)", "Chosen") and report.get("name"):
        return "None of the 13 organs (e.g. psychiatric, developmental, reproductive)"
    return "Unmapped"


def condition_name(condition):
    """Short UI label only; model inputs and clinical rules retain the complete registry label."""
    return re.sub(r"\s*\([^)]*\)", "", _reg[condition]["label"]) if condition in _reg else condition


def priority_lines(pc):
    levels = default_levels(pc); groups = {}
    for c, _, _ in sorted(pc, key=lambda item: levels[item[0]]): groups.setdefault(levels[c], []).append(condition_name(c))
    return [f"  {level}. {', '.join(names)}" for level, names in groups.items()]
COND_Q = ("기저질환 선택", "SPACE 선택(복수 가능)    / 검색    ENTER 확정")
def _tui_ok():
    if "--plain" in sys.argv: return False          # plain prompts and a printed table, no full-screen menus
    try: import term                                 # real curses, or the ANSI stand-in on Windows (ml/term.py)
    except ImportError: return False
    return sys.stdin.isatty() and sys.stdout.isatty() and (os.name == "nt" or os.environ.get("TERM", "dumb") != "dumb")   # Windows sets no TERM


def _ask_priority_pc(pc):
    """the one condition to weigh first (form.Form.first in the terminal screens); Enter = automatic, the severity order."""
    global PRIORITY, FIRST
    names = [c for c, _, _ in pc]; d = default_levels(pc); picks = [(c, o) for c, o, _ in pc if not c.startswith("Lab: ")]
    print("\n가장 걱정되는 질환\n  0) Auto")
    for k, (c, organs) in enumerate(picks, 1): print(f"  {k}) {condition_name(c)}   {', '.join(ORGAN_SHORT[a] for a in sorted(organs, key=AXES.index))}")
    try: raw = input("  번호 (Enter = 0) > ").strip()
    except EOFError: raw = ""
    k = int(raw) if raw.isdigit() and int(raw) <= len(picks) else 0
    FIRST = picks[k - 1][0] if k else None
    PRIORITY = {c: 0 if c == FIRST else d[c] for c in names} if k else {}


def wizard(back=False):
    """plain prompts (--plain, or no full-screen terminal) -> (conditions, labs (x ULN form; empty), colour, raw lab values), or
    None when no condition is given.
    The terminal session is form.run."""
    import labs as LB
    ids = list(_reg)
    split = []
    while not split:                                   # no condition, no analysis: ask again (Enter on an empty line = exit)
        try: text = input("기저질환 (번호/ID/영어, 쉼표 구분; ? = 목록, Enter = 종료) > ")
        except EOFError: return None
        if text.strip() == "?":
            for k, i in enumerate(ids, 1): print(f"  {k:>2}) {i:<28} {_reg[i]['label']}")
            continue
        if not text.strip(): return None
        split = [" ".join(nfc(x).split()) for x in text.split(",") if x.strip()]
    conds = [ids[int(x) - 1] if x.isdigit() and 1 <= int(x) <= len(ids) else x for x in split]
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
    if HAS_LEARNED:
        analyze_conditions(conds)
    pc = patient_conditions(conds, raw)
    if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2: _ask_priority_pc(pc)
    return conds, {}, None, raw


SELF_TEST = ("alzheimer", "cirrhosis", "치매")


HELP = """ADCTOX {version}

기저질환(과 검사 수치)을 넣으면 미국 FDA 라벨이 있는 ADC {n}개를 이 환자에게 맞는 순서로 보여 줍니다.
순서 기준: 라벨의 사용 제한(Contraindicated, Avoid, Not studied) > 환자 장기에 걸린 boxed 경고 > 그 밖의 경고.
가장 걱정되는 질환을 고르면, Avoid가 아닌 ADC 중에서 그 질환의 장기 경고가 적은 ADC가 위로 갑니다.
질환은 AI 판정 모델이 MONDO 질환과 장기에 연결하고, 분석은 이 컴퓨터 안에서만 합니다.
연구용 도구입니다. 독성 발생 확률이 아니며 처방 결정을 대신하지 않습니다.

사용
  adctox                         브라우저에서 시작 (질환 → 검사 수치 → AI 장기 분석 → 우선순위 → 결과). 이 컴퓨터 안에서만 실행.
                                 ADCTOX_NO_BROWSER=1이면 주소만 표시, ADCTOX_PORT=8765면 그 포트
  adctox-cli                     같은 다섯 단계를 터미널 화면에서 (adctox --cli와 같음)
  adctox --plain                 터미널에서 전체 화면 없이 질문에 답하는 방식으로 입력
  질환과 검사 수치는 입력 화면에서만 넣습니다. 명령줄 인자로는 받지 않습니다.

입력 화면 키
  글자 입력       질환명 추천 (한국어, 영어, 약어, 초성, 오타); 두 단어 이상이면 증상으로 찾은 질환도
  ↑↓ ENTER        추천 고르기 (클릭도 됨)
  Backspace       빈 칸에서 두 번 누르면 마지막에 고른 질환 빼기 (질환 칩의 ×를 눌러도 됨)
  PgDn / PgUp     다음 단계 / 이전 단계
  ESC             입력 지우기, 빈 칸에서 누르면 종료

업데이트와 관리
  adctox --update-app            새 앱 설치
  adctox --check-app             새 앱이 있는지 확인
  adctox --update-models         바뀐 모델 파일만 받기
  adctox --check-models          모델 업데이트 확인
  adctox --model-version         설치된 모델 버전
  adctox --rollback-models       이전 모델로 되돌리기
  adctox --verify-models         모델 파일 무결성 검사
  adctox --self-test             예시 환자 한 명(alzheimer, cirrhosis, 치매)으로 분석이 끝까지 되는지 확인
  adctox --version               앱 버전
  adctox --help                  이 설명

자세히: https://github.com/ahnhc/ADCToX"""


def cap_threads(environ=os.environ):
    """before torch loads: at most 4 CPU threads (ADCTOX_THREADS or OMP_NUM_THREADS set by the user win). A few diseases at a time
    run fastest on a few busy threads; torch's default, one per core, leaves most of them waiting (24-core Xeon, 4 diseases:
    analysis 1.1 s on 4 threads, 14 to 19 s on 24, on a shared server)."""
    threads = environ.get("ADCTOX_THREADS") or str(min(4, os.cpu_count() or 1))
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"): environ.setdefault(name, threads)


def main():
    from adc_version import APP_VERSION
    arguments = sys.argv[1:]
    import adc_updates
    if adc_updates.app_layout():                      # an app updated in place: adctox-web and adctox-cli appear beside adctox at its first start, --version included
        try: adc_updates.ensure_launchers()
        except OSError: pass
    if arguments == ["--version"]:
        print(APP_VERSION); return
    actions = {"--update-models": "update", "--check-models": "check", "--model-version": "version", "--rollback-models": "rollback", "--verify-models": "verify"}
    if len(arguments) == 1 and arguments[0] in actions:
        import adc_updates
        raise SystemExit(adc_updates.cli(actions[arguments[0]]))
    if len(arguments) == 1 and arguments[0] in ("--update-app", "--check-app"):
        import adc_updates
        raise SystemExit(adc_updates.app_cli("update" if arguments[0] == "--update-app" else "check"))
    if arguments in (["--help"], ["-h"], ["help"]):
        print(HELP.format(version=APP_VERSION, n=len(_evidence()[0]))); return
    cap_threads()
    import term
    if "--no-wt" in sys.argv: sys.argv.remove("--no-wt"); arguments = sys.argv[1:]
    elif arguments == ["--cli"]: term.into_windows_terminal()   # on Windows: reopen the terminal screens in Windows Terminal when there is one
    term.windows_console()                              # UTF-8 and ANSI colours in a Windows console
    if arguments == ["--self-test"]:                    # installed-app check (CI): one fixed example patient, the printed table
        conds = list(SELF_TEST)
        if HAS_LEARNED: analyze_conditions(conds)
        rows, s, notes, ck = recommend(conds); render(rows, s, notes, ck); return
    if arguments in ([], ["--web"]):                   # 0.6.12: the browser is the default (ml/webapp.py, served on this computer only); --cli for the terminal
        import webapp
        preload(); webapp.serve(sys.modules[__name__]); return
    if "--web" in arguments:                           # --web takes no other argument
        print("adctox: --web는 단독으로 씁니다 (adctox --web).", file=sys.stderr); sys.exit(2)
    other = [a for a in arguments if a not in ("--cli", "--plain")]
    if other:                                          # 0.5.3: conditions and lab values are entered on the screens only
        print(f"adctox: 알 수 없는 인자입니다: {' '.join(other)}\n질환과 검사 수치는 입력 화면에서 넣습니다. 브라우저는 adctox, 터미널은 adctox-cli (옵션: adctox --help).", file=sys.stderr)
        sys.exit(2)
    if not sys.stdin.isatty():
        print("adctox-cli: 입력 화면이 필요합니다. 터미널에서 실행하세요 (브라우저는 adctox, 설치 확인은 adctox --self-test).", file=sys.stderr); sys.exit(2)
    if _tui_ok():                                      # the terminal session: five steps and the result screen
        import form
        preload()
        r = form.run(sys.modules[__name__])
        if r is None: sys.exit(0)
        conds, raw, (rows, s, notes, ck) = r
        print(); render(rows, s, notes, ck, labs={}, raw=raw); form.clear(); return
    while True:                                        # --plain, or a terminal without full-screen support
        answers = wizard()
        if answers is None: return
        conds, labs, col, raw = answers
        print()
        rows, s, notes, ck = recommend(conds, labs, raw)
        render(rows, s, notes, ck, color=col, labs=labs, raw=raw)
        try: again = input("\nRun again with different answers? (y = yes, Enter = exit) > ").strip().lower()
        except EOFError: break
        if again != "y": break

if __name__ == "__main__":
    main()
