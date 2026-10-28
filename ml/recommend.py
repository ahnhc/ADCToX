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

The learned cross-organ vulnerability (disease-pair model, ml/vulnerability_model.py; axis heads trained on the Danish DTB since model 0.2) is OFF by default: in the only non-circular
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drug_evidence as DE, restrictions as RS
AXES = DE.AXES; R = RS.R
LEARNED_FRACTION = 0.0      # off by default; see the module docstring
FALLBACK = {}               # condition text -> learned fraction, only for conditions that map to no organ (asked in the wizard)
PRIORITY = {}               # condition text -> level the user set (1 = avoid its organs' toxicity first); default = severity order
FIRST = None                # the condition the doctor is most worried about (the priority step); None = automatic
CANCER = None               # the patient's cancer (the first step); the ADCs approved for it come first. None = not given
CHOICE = {}                 # condition text -> MONDO id the user picked among its readings (None = 'not sure'); see mondo_index.readings
REG_NEAR = 0.80             # a free-text condition is 'the same as' a registry condition at this BioLORD cosine -> its curated organs
MONDO_SEVERITY = 0.80       # organs read off the MONDO hierarchy have no curated severity; one fixed value, not fitted
MATCH_COS = 0.60            # last resort: borrow the organs of a loosely similar registry condition
LINK_THETA = 0.75           # = mondo_index.THETA: a MONDO match this close is 'understood' even when the concept has no organ axis
AUTO_FALLBACK = 0.25        # the wizard's '자동': the learned estimate is used only when the validity gate says the text names a disease
GATE_MONDO = True           # also require the validity gate for a MONDO link / borrowed registry organs (chosen on the gold dev split,
GATE_BORROW = False         # ml/docs/archive/model_review_2026-10-12.md); an index without a gate (before v1) behaves as before
CONTEXT = {"concomitant_bleomycin": "Concomitant bleomycin (co-medication, no organ)"}     # inputs that are not diseases but a label rule names
EN = {"haematologic": "Haematologic", "hepatic": "Hepatic", "cardiovascular": "Cardiovascular", "pulmonary": "Pulmonary", "renal": "Renal",
      "gastrointestinal": "GI", "neurologic": "Neurologic", "ocular": "Ocular", "dermatologic": "Dermatologic", "metabolic_endocrine": "Metabolic",
      "musculoskeletal": "Musculoskeletal", "infectious_immune": "Immune", "otologic": "Otologic"}

_reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}
_by_label = {r["label"].lower(): r["id"] for r in _reg.values()}


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


def own_vec(cid):
    v = np.zeros(len(AXES))
    for a in _reg[cid]["organ_axes"].split(";"):
        if a in AXES: v[AXES.index(a)] = float(_reg[cid]["severity"])
    return v


_FREE = {}                  # free-text conditions -> (nearest registry condition per text, MONDO links), per process
_FREE_PREDICTIONS = {}       # actual saved disease-pair MLP predictions, cached per typed condition
_FREE_MODELS = {}            # typed condition -> (severity per model, agreement per axis, models needed for automatic use)
MODEL_NAMES = {"main": "Den", "combined": "Both", "previous": "Fin"}   # model 0.2 v1 names; later checkpoints store their own
_ANALYSES = {}              # mapping and model estimates shown in the input review
_REGISTRY_LEARNED = {}
HAS_LEARNED = True          # the learned estimate is available (not in the portable build)


def clear_model_cache():
    """A completed model update must invalidate both linking and inference results."""
    _FREE.clear(); _FREE_PREDICTIONS.clear(); _FREE_MODELS.clear(); _ANALYSES.clear(); _REG_P.clear(); _REGISTRY_LEARNED.clear()
    module = sys.modules.get("mondo_index")
    if module is not None:
        index = getattr(module, "_IDX", None)
        if index is not None and hasattr(index, "close"): index.close()
        module._IDX = None
    for name in ("mondo_index", "vulnerability_model"):          # loaded encoders, the index matrix and the ensemble are per bundle too
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "close"): module.close()


_EVIDENCE = []              # label evidence and rules parsed once per process: the label snapshot does not change while it runs


def _evidence():
    import copy
    if not _EVIDENCE: _EVIDENCE.extend([DE.evidence(), RS.load_rules()])
    return copy.deepcopy(_EVIDENCE[0]), _EVIDENCE[1]


def _learned_values():
    import adc_runtime
    if adc_runtime.active_directory() is not None:
        identity = adc_runtime.bundle_identity()
        if identity not in _REGISTRY_LEARNED:
            import vulnerability_model as VM
            _REGISTRY_LEARNED[identity] = dict(zip(_reg, VM.predict([r["label"] for r in _reg.values()])))
        return _REGISTRY_LEARNED[identity]
    return json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"]


def _free_info(free, progress=None):
    """per typed text: (nearest registry id, similarity), its MONDO link {name, sim, axes}, and the learned vector (or None).
    The portable build replaces this function with string matching on MONDO names and synonyms."""
    key = tuple(free)
    if key not in _FREE:
        if progress: progress("embedding")
        with _Loading("Loading weights / 질환 해석 모델 (BioLORD, MONDO)", "질환 해석 모델 준비 완료", enabled=progress is None):
            import vulnerability_model as VM, mondo_index as MI
            # typed text and registry labels in separate batches: the registry is embedded once per process, and the typed
            # text gets the same (fp16, unpadded-by-the-registry) embedding the MLP reuses below
            text = english(free)                                   # Korean names go to the models as their English KCD name
            Ef, Er = VM._st(text), VM._st([_reg[i]["label"] for i in _reg]); ids = list(_reg); best = []
            for i in range(len(free)):
                sims = Er @ Ef[i]; k = int(sims.argmax()); best.append((ids[k], float(sims[k])))
            links = None; failed = None
            try:
                import scratch_runtime as SR
                if SR.available():                             # model 0.7+: the from-scratch judge links and judges on its own
                    if progress: progress("judging")
                    links = [_scratch_link(r) for r in SR.judge(text)]
            except Exception as error:
                failed = f"{type(error).__name__}: {error}"; warnings.warn(f"organ judge unavailable: {error}")
            if links is None:
                if progress: progress("linking")
                links = MI.link(text)
                if failed:                                     # the bundle's older linker read these: the analysis screen says so
                    for lk in links: lk["fallback"] = failed
                try:
                    import gemma_runtime as GR
                    if GR.available():                         # model 0.5-0.6: the Gemma organ judge reads the typed text itself (Korean too)
                        if progress: progress("judging")
                        if GR.has_extra(): _judge_extra(free, links, GR, MI)
                        else:
                            for lk, organs in zip(links, GR.judge(list(free))): lk["judged"] = organs
                except Exception as error:
                    warnings.warn(f"Gemma organ judge unavailable: {error}")
            _FREE[key] = (best, links)
    best, links = _FREE[key]
    learned = None
    if LEARNED_FRACTION > 0 or FALLBACK:
        learned = _predict_free(free, progress)
    return best, links, learned


JUDGE_GATE = os.environ.get("ADC_JUDGE_GATE", "judge")   # models 0.6+: whose validity decision counts ("judge", "either", "linker")
KO_ALIGN = 0.6              # Korean text the linker could not place: the judge's SapBERT-space vector links it when this close (gold dev, Korean)


def _judge_extra(free, links, GR, MI):
    """the four-output judge (models 0.6+): organs, validity, and for Korean text the linker missed, a MONDO link through the
    judge's SapBERT-space vector."""
    o = GR.outputs(list(free)); _, _, (_, _, _, thr, _) = GR.load()
    vecs = [k for k, (c, lk) in enumerate(zip(free, links)) if re.search("[가-힣]", c) and not lk["axes"] and o["valid_ok"][k]]
    near = MI.nearest(o["vec"])                                     # every text, for the analysis screen; applied only to `vecs`
    for k, lk in enumerate(links):
        lk["judged"] = [GR.AXES[a] for a in np.where(o["organ"][k] >= thr)[0]]; ok = bool(o["valid_ok"][k])
        if JUDGE_GATE == "judge": lk["gate"] = ok
        elif JUDGE_GATE == "either": lk["gate"] = ok or lk.get("gate") is not False
        top = np.argsort(-o["organ"][k])[:3]; s = int(np.argmax(o["sym"][k]))
        lk["gemma"] = dict(valid=float(o["valid"][k]), vthr=o["vthr"], ok=ok, organ=[(GR.AXES[a], float(o["organ"][k][a]), float(thr[a])) for a in top],
                           near=(near[k][0], MI.concept(near[k][0])[0] or "", float(near[k][1])), sym=(o["profiles"][s], float(o["sym"][k][s])))
        if k in vecs and near[k][1] >= KO_ALIGN:
            name, organs = MI.concept(near[k][0])
            if organs: lk.update(mondo=near[k][0], name=name, sim=near[k][1], axes=organs, via="judge vector")


def _scratch_link(r):
    """one row of scratch_runtime.judge in the linker's format: a MONDO concept gives its organs (from its label, its MONDO record
    or, without either, the organ output on the text); any other result is an AI judgment of the text. `judge_via` says which."""
    lk = dict(mondo=None, name="", sim=r["sim"], axes=[], valid=r["valid"], gate=r["ok"], readings=[], ambiguous=False, judge_via=r["via"], judge=True, p=r.get("p"))
    if not r["ok"]: return lk
    if r["concept"] and r["concept"].startswith("MONDO:"): lk.update(mondo=r["concept"], name=r["name"], axes=list(r["organs"]))
    elif r["organs"]: lk.update(judged=list(r["organs"]), sim=0.0, judge_via="name")
    return lk


def _judge_differs(lk, near):
    """the from-scratch judge linked a MONDO disease with organs that is not the registry condition's own concept: the judge's link
    stands over the looser name similarity ('Type 1 diabetes mellitus' is not the registry's 'Type 2 diabetes'). A registry
    condition the judge does not place in MONDO (prior exposures, procedures) still matches by name."""
    return bool(lk.get("judge") and lk.get("mondo") and lk["axes"] and _reg[near].get("mondo_id") != lk["mondo"])


def english(texts):
    """typed texts with Korean disease names replaced by their English KCD name (index v3+); other texts unchanged."""
    if not any(re.search("[가-힣]", t) for t in texts): return list(texts)
    import mondo_index as MI
    return [(MI.korean(t) if hasattr(MI, "korean") else None) or t for t in texts]


def _predict_free(free, progress=None):
    """Run our saved trained head, once per new text; these scores are not probabilities."""
    missing = list(dict.fromkeys(c for c in free if c not in _FREE_PREDICTIONS))
    if missing:
        if progress: progress("inference")                         # only when the MLP actually runs (not for cached texts)
        import vulnerability_model as VM
        if hasattr(VM, "predict_models"):                          # main estimate plus the comparison heads (model 0.2+)
            for c, by in zip(missing, VM.predict_models(english(missing))):
                _FREE_PREDICTIONS[c] = by["main"]
                if len(by) > 1:                                    # display names: the checkpoint's own (Both, Den, Fin)
                    label = VM._CK_OPT.get("label", "main"); by = {(label if k == "main" else k): v for k, v in by.items()}
                    _FREE_MODELS[c] = (by, VM.agreement(by), VM._CK_OPT["agree_min"])
        else: _FREE_PREDICTIONS.update(zip(missing, VM.predict(english(missing))))
    return [_FREE_PREDICTIONS[c] for c in free]


def analyze_conditions(conditions, progress=None):
    """Review typed conditions using both disease linking and our trained disease-pair MLP.

    A model's natural-disease vulnerability estimate is displayed separately from the linked disease's organs.
    Running inference does not silently turn on cross-organ weighting or invent a label diagnosis.
    """
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and c not in CONTEXT]
    picked = [c for c in conditions if c not in free and c not in CONTEXT]
    if not free and not picked: return []
    best, links, _ = _free_info(free, progress) if free else ([], [], None)
    learned = (_predict_free(free, progress) if HAS_LEARNED else [None] * len(free)) if free else []
    _, _, _, notes, pc = resolve(conditions)
    organs = {c: sorted(axes, key=AXES.index) for c, axes, _ in pc}
    reports = []
    labels = {c: _reg[c if c in _reg else _by_label[c.lower()]]["label"] for c in picked}
    probs = _registry_p(list(labels.values()), progress)
    for c in picked:                                            # a registry disease: its curated organs; the judge's organ output beside them
        report = dict(condition=c, source="Registry", name=labels[c], mondo=_reg[c if c in _reg else _by_label[c.lower()]].get("mondo_id"),
                      organs=organs.get(c, []), estimates=[], model=None, readings=[], ambiguous=False, models=[], by_model={}, agree={},
                      gemma=None, via=None, fallback=None, judge_via=None, p=probs.get(labels[c]))
        _ANALYSES[c] = report; reports.append(report)
    for c, (near, sim), link, prediction in zip(free, best, links, learned):
        how = dict(notes)[c]
        source = ("Chosen" if "chosen reading" in how else "AI judgment" if "AI judgment" in how else "MONDO (no organ axis)" if "no organ axis" in how else "MONDO" if "; MONDO '" in how else "Phenotype (HPO)" if "phenotype HPO" in how else
                  "Registry match" if "same as registry" in how else "Similar condition" if "borrowed from registry" in how else "Unmapped")
        name = ("" if source == "AI judgment" else link["name"] if source.startswith("MONDO") else re.search(r"chosen reading (?:MONDO|HPO) '(.*?)'", how).group(1) if source == "Chosen" else
                link["hpo"]["name"] if source == "Phenotype (HPO)" else _reg[near]["label"] if source != "Unmapped" else "")
        estimates = sorted(((a, float(v)) for a, v in (prediction or {}).items() if v > 0), key=lambda x: (-x[1], AXES.index(x[0])))[:3]
        models, by_model, agree = [], {}, {}
        if c in _FREE_MODELS:                                       # most agreed organs first, then the main score
            by, agree, _ = _FREE_MODELS[c]; models = [MODEL_NAMES.get(k, k) for k in by]
            estimates.sort(key=lambda x: (-agree.get(x[0], 0), -x[1], AXES.index(x[0])))
            by_model = {a: [float(by[k][a]) for k in by] for a, _ in estimates}
        report = dict(condition=c, source=source, name=name, mondo=link.get("mondo") if source.startswith("MONDO") else None, organs=[] if source == "Unmapped" else organs.get(c, []), estimates=estimates,
                      model="BioLORD + disease-pair MLP" if prediction is not None else None,
                      readings=link.get("readings", []), ambiguous=bool(link.get("ambiguous")),
                      models=models, by_model=by_model, agree={a: agree.get(a, 0) for a, _ in estimates}, gemma=link.get("gemma"), via=link.get("via"), fallback=link.get("fallback"),
                      judge_via=link.get("judge_via") if source.startswith("MONDO") or source == "AI judgment" else _chosen_via(c) if source == "Chosen" else None,
                      p=link.get("p"))
        _ANALYSES[c] = report; reports.append(report)
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
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and c not in CONTEXT]
    if free: best, links, learned_free = _free_info(free)
    L = _learned_values() if LEARNED_FRACTION > 0 else None
    fi = 0
    for c in conditions:
        if c in CONTEXT: ids.add(c); notes.append((c, CONTEXT[c])); continue
        cid = c if c in _reg else _by_label.get(c.lower())
        if cid:
            own, how = own_vec(cid), f"registry: {_reg[cid]['label']}"; ids.add(cid); lv = np.array([L[cid][a] for a in AXES]) if L else None
        else:
            near, sim = best[fi]; lk = links[fi]; rl = _reg[near]["label"]
            lv = np.array([learned_free[fi][a] for a in AXES]) if learned_free else None
            rejected = lk.get("gate") is False; hp = lk.get("hpo"); picked = CHOICE.get(c, "-")
            chosen = _chosen(picked) if c in CHOICE and picked else None
            if chosen:
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in chosen[1]]
                how = f"free text; chosen reading {'HPO' if picked.startswith('HP:') else 'MONDO'} '{chosen[0]}' -> organs: {', '.join(chosen[1]) or 'none'}"
            elif c in CHOICE and picked is None: own, how = np.zeros(len(AXES)), "free text; not understood (no organ); reading left open by the user"
            elif sim >= REG_NEAR and not _judge_differs(lk, near): own, how = own_vec(near), f"free text; same as registry '{rl}' (cos {sim:.2f})"; ids.add(near)
            elif lk["axes"] and not (GATE_MONDO and rejected):
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in lk["axes"]]
                how = f"free text; MONDO '{lk['name']}' (sim {lk['sim']:.2f}) -> organs: {', '.join(lk['axes'])}"
            elif lk.get("judged") and not rejected:                 # index v5+: no linked organ, the fast organ judgment of the text
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in lk["judged"]]
                how = f"free text; AI judgment -> organs: {', '.join(lk['judged'])}"
            elif lk["axes"] == [] and (lk.get("mondo") if lk.get("judge") else lk.get("sim", 0) >= LINK_THETA) and not rejected and not lk.get("ambiguous"):
                own, how = np.zeros(len(AXES)), f"free text; MONDO '{lk['name']}' (sim {lk['sim']:.2f}) -> no organ axis"
            elif hp:
                own = np.zeros(len(AXES)); [own.__setitem__(AXES.index(a), MONDO_SEVERITY) for a in hp["organs"]]
                how = f"free text; phenotype HPO '{hp['name']}' (sim {hp['sim']:.2f}) -> organs: {', '.join(hp['organs'])}"
            elif sim >= MATCH_COS and not lk.get("judge") and not (GATE_BORROW and rejected): own, how = own_vec(near), f"free text; organs borrowed from registry '{rl}' (cos {sim:.2f})"
            else:
                own, how = np.zeros(len(AXES)), "free text; not understood (no organ)"
                if FALLBACK.get(c) == AUTO_FALLBACK and rejected:
                    how += "; validity gate: not read as a disease, learned estimate not used"
                elif FALLBACK.get(c) and lv is not None:
                    f = max(FALLBACK[c], LEARNED_FRACTION); top = [AXES[k] for k in np.argsort(-lv)[:3] if f * lv[k] >= 0.01]
                    if c in _FREE_MODELS:                           # organs too few models agree on are shown, not applied
                        _, agree, need = _FREE_MODELS[c]; top = [a for a in top if agree.get(a, 0) >= need]
                    estimate = np.zeros_like(lv)
                    for a in top: estimate[AXES.index(a)] = f * lv[AXES.index(a)]
                    ws.append(estimate); how += f"; learned estimate x{f:g} used (not validated): {', '.join(EN[a] for a in top) or 'no organ'}"
                    if top: pc.append((c, set(top), float(f * lv.max())))
            if lk.get("ambiguous") and c not in CHOICE:
                applied = hp["name"] if hp and "phenotype HPO" in how else lk.get("name")
                how += "; other readings: " + "; ".join(f"{r['name']} ({', '.join(EN[a] for a in r['organs']) or 'no organ'})" for r in lk["readings"] if r["name"] != applied)
            fi += 1
        own_axes |= {AXES[k] for k in np.where(own > 0)[0]}
        if own.max() > 0: pc.append((c, {AXES[k] for k in np.where(own > 0)[0]}, float(own.max())))
        ws.append(np.maximum(own, LEARNED_FRACTION * lv) if lv is not None and LEARNED_FRACTION > 0 else own); notes.append((c, how))
    return np.maximum.reduce(ws), own_axes, ids, notes, pc


def _chosen(mondo):
    import mondo_index as MI
    if MI._IDX is None: MI.link(["x"])                          # loads the index of the active bundle
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
    free = [c for c in conditions if c not in _reg and c.lower() not in _by_label and c not in CONTEXT]
    if not free: return []
    _, links, _ = _free_info(free)
    return [(c, lk["readings"]) for c, lk in zip(free, links) if lk.get("ambiguous") and lk.get("gate") is not False]   # not a disease name: nothing to choose


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
    approved = set(_cancers().get(CANCER, [])) if CANCER else set()
    for r in rows: r["indicated"] = not approved or r["adc"] in approved
    first = next((set(o) for c, o, _ in pc if c == FIRST), None)
    hit = lambda r, k: sum(a in first for a in r[k]) if first else 0
    # a cancer: the ADCs approved for it first. A picked condition: its organs' boxed warnings, then warnings, come before
    # Monitor / Not studied; Avoid stays last
    order = lambda r: ((not r["indicated"],) if approved else ()) + ((r["tier"] >= RS.TIER["avoid"], hit(r, "boxed"), hit(r, "warn")) if first else ()) + (r["tier"], r["verdict"].worst_known, r["Bl"], r["Wl"])
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
        if not row.get("indicated", True) and at and rows[len(at) - 1].get("indicated", True):    # the ADCs for other cancers
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


def organ_warning_lines(row):
    """the label warnings on this patient's organs, the boxed one first: '  Lung      !!  Boxed INTERSTITIAL LUNG DISEASE; 5.1 ...'"""
    out = []
    for marks, organs in (("!!", row.get("boxed", [])), ("! ", row.get("warn", []))):
        for a in organs:
            heads = "; ".join(f"{sec} {head}" for sec, head in row["organs"][a].get("headings", []))
            out.append(f"  {ORGAN_SHORT[a]:<9} {marks}  {heads}")
    return out


_CAN = None


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


def preload():
    """load the encoder and the organ judge in the background while the doctor types: the first analysis waited for them."""
    import threading
    def work():
        try:
            import vulnerability_model as VM
            VM._st([_reg[i]["label"] for i in _reg])           # the registry names the analysis compares typed text with
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
        if keep: out.append("  " + " ".join(keep) + (f" [{mech['reference']}]" if mech.get("reference") else ""))
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
             "child_pugh": "child_pugh", "ugt1a1": "ugt1a1_28_homozygous", "age": "crcl", "sex": "crcl", "weight": "crcl", "creatinine": "crcl", "egfr": "crcl"}


def _raw_values(raw, values):
    """entered lab values that no restriction input shows, each with the organ it marked (ml/labs.py FLAGS): 'Hb 8 g/dL → Blood'."""
    import labs as LB
    out = []
    for k, label, unit, _ in LB.FIELDS:
        v = (raw or {}).get(k)
        if v is None or values.get(_SHOWN_AS.get(k, "")) is not None: continue
        text = ("yes" if v else "no") if isinstance(v, bool) else f"{v:g}" if isinstance(v, (int, float)) else str(v)
        organs = [o for key, test, o, _ in LB.FLAGS if key == k and isinstance(v, (int, float)) and test(v, LB.ULN.get(k))]
        out.append((bool(organs), f"{label} {text} {unit}" + (" → " + ", ".join(ORGAN_SHORT[o] for o in dict.fromkeys(organs)) if organs else "")))
    return [t for _, t in sorted(out, key=lambda x: not x[0])]           # the ones that marked an organ first


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
        else: inputs.append(f"{label} {text}{unit}")
    inputs += _raw_values(raw, values)
    organ_levels = {}
    for level, _, organs in prio:
        for organ in organs: organ_levels[organ] = min(level, organ_levels.get(organ, level))
    grouped = {}
    for organ, level in sorted(organ_levels.items(), key=lambda item: (item[1], AXES.index(item[0]))):
        grouped.setdefault(level, []).append(organ)
    if graphic:                                                # the result screen: one organ strip per level (green = that level's organs)
        import tui
        priorities = [f"{level}  {tui.strip(AXES, organs)}" for level, organs in grouped.items()]
    else: priorities = [f"{level}. {', '.join(ORGAN_SHORT[o] for o in organs)}" for level, organs in grouped.items()]
    def block(title, items, empty):
        body = items[:3] + ([f"+ {len(items) - 3} more"] if len(items) > 3 else [])
        return [f"\033[33;1m{title}\033[0m"] + ["  " + text for text in body or [empty]]
    left = block("Key values", inputs, "Not entered")
    right = block("Organ priority", priorities, "None specified")
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
                      footer="!! Boxed warning   ! Warning   + more organs   ? needs a value not entered",
                      context=lambda i, w: _result_context(rows, notes, w, values, i, graphic=True, raw=raw), scr=scr, crumbs=crumbs)


def patient_lines(notes):
    """[(English name, Korean name or how it was read, or None for a plain note line)] for the Patient block."""
    def names(c, how):
        cid = c if c in _reg else _by_label.get(c.lower())
        if cid: return _reg[cid]["label"], KO.get(cid, "")
        if c in CONTEXT: return CONTEXT[c], ""
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
    emit(paint("!! Boxed warning   ! Warning   + more organs   ? needs a value not entered", "90"))
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
            organs = ", ".join(ORGAN_SHORT[a] for a in report["organs"]) or no_organ_text(report)
            src = "MONDO" if report["source"].startswith("MONDO") else report["source"] if report["source"] != "Unmapped" else ""
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
                    o = r["organs"][a]; hd = "; ".join(f"{sec} {h}" for sec, h in o["headings"]) or "no warning"
                    emit(f"  {EN[a]} / {o['level']} / {hd} / {_inc_text(o)}")


# ------------------------------------------------------------------------------------------------ input
ORGAN_KO = {"haematologic": "혈액", "hepatic": "간", "cardiovascular": "심혈관", "pulmonary": "폐", "renal": "신장", "gastrointestinal": "위장관",
            "neurologic": "신경", "ocular": "눈", "dermatologic": "피부", "metabolic_endocrine": "대사/내분비", "musculoskeletal": "근골격",
            "infectious_immune": "감염/면역", "otologic": "귀"}
KO = {"chronic_liver_disease": "만성 간질환", "cirrhosis": "간경변", "hepatitis_b_chronic": "만성 B형 간염", "hepatitis_c_chronic": "만성 C형 간염",
      "hepatic_vod_history": "간정맥폐쇄병 병력", "nafld": "비알코올성 지방간", "ckd_stage_3": "만성 콩팥병 3기", "ckd_stage_4_5": "만성 콩팥병 4–5기",
      "dialysis": "투석 중", "heart_failure": "심부전", "reduced_lvef": "좌심실 박출률 저하", "prior_anthracycline": "안트라사이클린 치료 경험",
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
FALLBACK_Q = ("추정 장기 반영: {conds}", "질환명과 추정 장기를 확인해 주세요. 자동은 질환으로 인식된 입력에만 반영합니다.")
FALLBACK_OPTS = [("자동", 0.25), ("반영", 0.5), ("반영 안함", 0.0)]
def _tui_ok():
    if "--plain" in sys.argv: return False          # plain prompts and a printed table, no full-screen menus
    try: import term                                 # real curses, or the ANSI stand-in on Windows (ml/term.py)
    except ImportError: return False
    return sys.stdin.isatty() and sys.stdout.isatty() and (os.name == "nt" or os.environ.get("TERM", "dumb") != "dumb")   # Windows sets no TERM


FIRST_TEXT = "고른 질환의 장기에 경고가 있는 ADC를 아래로 내립니다. Avoid는 그대로 맨 아래입니다."


def _ask_priority_pc(pc):
    """the one condition to weigh first (form.Form.first in the terminal screens); Enter = automatic, the severity order."""
    global PRIORITY, FIRST
    names = [c for c, _, _ in pc]; d = default_levels(pc); picks = [(c, o) for c, o, _ in pc if not c.startswith("Lab: ")]
    print(f"\n가장 걱정되는 질환\n  {FIRST_TEXT}\n  0) 자동 (질환 중증도 순)")
    for k, (c, organs) in enumerate(picks, 1): print(f"  {k}) {condition_name(c)}   {', '.join(ORGAN_SHORT[a] for a in sorted(organs, key=AXES.index))}")
    try: raw = input("  번호 (Enter = 0) > ").strip()
    except EOFError: raw = ""
    k = int(raw) if raw.isdigit() and int(raw) <= len(picks) else 0
    FIRST = picks[k - 1][0] if k else None
    PRIORITY = {c: 0 if c == FIRST else d[c] for c in names} if k else {}


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
    """plain prompts (--plain, or no full-screen terminal) -> (conditions, labs (x ULN form; empty), colour, raw lab values), or
    None when no condition is given.
    The terminal session is form.run."""
    import labs as LB
    global CANCER
    ids = list(_reg); cancers = list(_cancers())
    print("암종")
    for k, c in enumerate(cancers, 1): print(f"  {k:>2}) {c}")
    try: text = input("번호 (Enter = 모름) > ").strip()
    except EOFError: text = ""
    CANCER = cancers[int(text) - 1] if text.isdigit() and 1 <= int(text) <= len(cancers) else None
    split = []
    while not split:                                   # no condition, no analysis: ask again (Enter on an empty line = exit)
        try: text = input("기저질환 (번호/ID/영어, 쉼표 구분; ? = 목록, Enter = 종료) > ")
        except EOFError: return None
        if text.strip() == "?":
            for k, i in enumerate(ids, 1): print(f"  {k:>2}) {i:<28} {_reg[i]['label']}")
            continue
        if not text.strip(): return None
        split = [" ".join(x.split()) for x in text.split(",") if x.strip()]
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
        _ask_fallback(conds)
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
  adctox                         입력 화면으로 시작 (질환 → 검사 수치 → AI 장기 분석 → 우선순위 → 결과)
  adctox --plain                 전체 화면 없이 질문에 답하는 방식으로 입력
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
    if "--no-wt" in sys.argv: sys.argv.remove("--no-wt")
    else: term.into_windows_terminal()                 # double-clicked on Windows: reopen in Windows Terminal when there is one
    term.windows_console()                              # UTF-8 and ANSI colours in a Windows console
    if arguments == ["--self-test"]:                    # installed-app check (CI): one fixed example patient, the printed table
        conds = list(SELF_TEST)
        if HAS_LEARNED: analyze_conditions(conds)
        rows, s, notes, ck = recommend(conds); render(rows, s, notes, ck); return
    other = [a for a in arguments if a != "--plain"]
    if other:                                          # 0.5.3: conditions and lab values are entered on the screens only
        print(f"adctox: 알 수 없는 인자입니다: {' '.join(other)}\n질환과 검사 수치는 입력 화면에서 넣습니다. adctox 만 실행하세요 (옵션: adctox --help).", file=sys.stderr)
        sys.exit(2)
    if not sys.stdin.isatty():
        print("adctox: 입력 화면이 필요합니다. 터미널에서 실행하세요 (설치 확인은 adctox --self-test).", file=sys.stderr); sys.exit(2)
    if _tui_ok():                                      # the terminal session: six steps and the result screen
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
