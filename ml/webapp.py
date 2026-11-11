"""adctox --web: the five input steps and the result screen in the default browser, served on this computer only.

A stdlib HTTP server bound to 127.0.0.1 on a free port; the page is ml/web/ (the one-file build carries it, ml/build_portable.py
data["web"]). The endpoints return, as data, what the terminal screens (ml/form.py, ml/recommend.py) show: the same names, the
same Read as and how texts, the same numbers. Nothing is kept on the server; the page keeps its own state.
recommend's per-process state (CHOICE, PRIORITY, FIRST) is set from each request under one lock and put back after it.
Analyses run one at a time in one worker thread, in the order they were asked for (a later one waits as "queued").
"""
import base64, gzip, json, os, queue, re, secrets, sys, threading, time, traceback
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HANGUL = re.compile("[가-힣]")
# the page is English only (Korean input is still read): its step names and the analysis progress line
STEPS = ["Conditions", "Labs", "Organs", "Priority", "Results"]
STEP_TEXT = {"judging": "Analysing organs"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml; charset=utf-8", ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json; charset=utf-8",
         ".txt": "text/plain; charset=utf-8", ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf"}
BINARY = {".woff2", ".ttf", ".otf"}     # kept base64 in the page dict (the one-file build stores it as JSON), sent as bytes
JSON = "application/json; charset=utf-8"
# form.Form._analysis_review: the source words of the analysis table
SOURCE = {"AI judgment": "AI judgment", "Registry match": "Registry", "Registry": "Registry", "Similar condition": "Similar registry condition",
          "Phenotype (HPO)": "HPO phenotype", "Chosen": "Chosen", "Unmapped": "Not understood"}
STATUS = {0: "None", 1: "Monitor", 2: "No data", 3: "Avoid", 4: "Avoid"}       # recommend._result_list: the four display groups
JOBS = 8                    # analyses kept for the page to fetch; a finished one goes once fetched, or after KEEP seconds
KEEP = 300
GZIP_FROM = 32768               # one large response stalls at about 64 KB through a loopback filter (AdGuard on Windows), and the page never loads
SENTENCE_MAX = 400             # characters of a described case the symptom search reads: it costs about 6 ms a character, a pasted note took minutes


def web_files(folder):
    """{name: text} of the page files in a folder (binary ones as base64), {} when it is missing; the one-file build embeds this
    dict. The page's fixtures (mock*) stay out: the app serves only what the page runs on."""
    folder = Path(folder)
    if not folder.is_dir(): return {}
    return {p.name: base64.b64encode(p.read_bytes()).decode() if p.suffix in BINARY else p.read_text(encoding="utf-8") for p in sorted(folder.iterdir())
            if p.is_file() and p.suffix in TYPES and not p.name.startswith((".", "mock", "AnthropicSans"))}


def _page():
    """the page files: the embedded ones in the one-file build (never from disk there), else ml/web/ as it is now"""
    try: from __adc_data__ import _portable_data
    except ImportError: return web_files(Path(__file__).resolve().parent / "web")
    return _portable_data().get("web", {})


class _Error(Exception):
    def __init__(self, status, message, **extra): super().__init__(message); self.status, self.extra = status, extra


def _plain(x):
    if hasattr(x, "item"): return x.item()                          # numpy numbers
    if isinstance(x, (set, frozenset)): return sorted(x)
    return str(x)


def _one_line(error): return f"{type(error).__name__}: {error}".splitlines()[0]


def _log(error):
    """one line on stderr; the traceback with ADCTOX_WEB_DEBUG=1"""
    if os.environ.get("ADCTOX_WEB_DEBUG") == "1": traceback.print_exception(type(error), error, error.__traceback__)
    else: print(f"adctox --web: {_one_line(error)}", file=sys.stderr, flush=True)


def _parse_raw(raw):
    """{lab key: typed text or value} -> ({key: value}, {key: the lab screen's error line})"""
    import form, labs as LB
    if raw is None: raw = {}
    if not isinstance(raw, dict): raise _Error(400, "raw: an object of lab values is expected")
    fields = {f[0]: f for f in LB.FIELDS}; out, errors = {}, {}
    for k, v in raw.items():
        if k not in fields: raise _Error(400, f"unknown lab field: {k}")
        if v is None: continue
        try:
            x = LB.parse(k, ("y" if v else "n") if isinstance(v, bool) else str(v))
            if x is not None: out[k] = x
        except ValueError as e: errors[k] = _lab_error(fields[k], e)
    return out, errors


def _likely(axes, used, p):
    """form.likely as data: the judge's three most probable organs, then a used organ outside them; without p, the used organs."""
    if not p: return [dict(organ=a, used=True, p=None, text=None) for a in axes if a in used]
    top = sorted(axes, key=lambda a: -p.get(a, 0))[:3]
    top += [a for a in axes if a in used and a not in top]
    pct = lambda x: ">99%" if x >= 0.995 else "<1%" if x < 0.005 else f"{round(x * 100)}%"
    return [dict(organ=a, used=a in used, p=p.get(a, 0), text=pct(p.get(a, 0))) for a in top]


def _lab_error(field, error):
    """form._lab_error in English: 'Hb: enter 1–25 g/dL', 'Hb: enter a number'"""
    _, label, unit, _ = field
    if re.fullmatch(r"[\d.]+–[\d.]+", str(error)): return f"{label}: enter {error} {unit}".rstrip()
    return f"{label}: enter a number" if HANGUL.search(str(error)) else f"{label}: enter {error}"


def _report(RC, r, ko):
    """one row of the analysis table (form.Form._analysis_review): the input as shown, Read as, how, and the organ cells"""
    shown = RC.condition_name(r["condition"]) if r["source"] == "Registry" else r["condition"]
    picked = RC.CHOICE.get(r["condition"]) or ""
    kr = False                                                  # Read as: the English name, whatever language was typed
    linked = r["source"].startswith("MONDO") or r["source"] == "Cancer"
    read = ((ko.get(r.get("mondo") or "") if kr else "") or r["name"]) if linked else ((ko.get(picked) if kr else "") or r["name"] or "")
    how = "MONDO" if linked else SOURCE.get(r["source"], r["source"])
    if r.get("judge_via"): how += f" ({r['judge_via']})"
    if read.lower() in (r["condition"].lower(), shown.lower()): read = ""
    empty = None if r["organs"] else "Cancer" if r["source"] == "Cancer" else "none of 13" if r["source"].startswith("MONDO") else "-"
    tag = f"{len(r['readings'])} meanings: pick on the next screen" if r.get("ambiguous") and r["condition"] not in RC.CHOICE else None
    return dict(condition=r["condition"], shown=shown, source=r["source"], name=r["name"], read_as=read, how=how, mondo=r.get("mondo"),
                organs=list(r["organs"]), p=r.get("p"), likely=_likely(RC.AXES, r["organs"], r.get("p")) if r["organs"] else [], no_organs=empty,
                readings=[dict(mondo=o["mondo"], name=o["name"], organs=list(o.get("organs") or [])) for o in r.get("readings") or []],
                ambiguous=bool(r.get("ambiguous")), tag=tag, check=RC.DOUBT.get(r.get("doubt")), judge_via=r.get("judge_via"), fallback=bool(r.get("fallback")), cancers=r.get("cancers"))


def _preview(RC, row):
    """recommend._organ_preview as data: the warned patient organs (the list shows two, + for more) and the other warned organs
    (one, + for more), boxed first"""
    prio = {}
    for level, _, organs in row["priority"]:
        for o in organs: prio[o] = min(level, prio.get(o, level))
    strength = {"boxed": 0, "W&P": 1}; level = lambda o: row["organs"][o]["level"]
    patient = set(prio) | set(row["boxed"]) | set(row["warn"])
    own = sorted(set(row["boxed"]) | set(row["warn"]), key=lambda o: (strength[level(o)], prio.get(o, 999), RC.AXES.index(o)))
    other = sorted((o for o in RC.AXES if o not in patient and level(o) in strength), key=lambda o: (strength[level(o)], RC.AXES.index(o)))
    cell = lambda o: dict(organ=o, mark="!!" if level(o) == "boxed" else "!")
    return dict(patient=[cell(o) for o in own], other=[cell(o) for o in other])


def _event(RC, e):
    pct = lambda a, n: f"{100 * a / n:.1f}%"                         # recommend._event_text
    return dict(e, pct=pct(e["a"], e["n"]), comp_pct=pct(*e["comp"]) if e.get("comp") else None, text=RC._event_text(e))


def _trial(RC, row):
    """recommend.trial_lines as data: the trial (the patient's cancer's when known), its comparator, and per patient organ the
    events the label warning is about, or the most frequent and the most frequent serious event"""
    T = RC._trial_ae().get("adcs", {}).get(row.get("adc"))
    if not T: return None
    if not T["trials"]:
        t = T["no_results"][0]
        return dict(no_results=f"no results posted on ClinicalTrials.gov ({t['trial']}, {t['nct']})", trial=t["trial"], nct=t["nct"])
    t = next((t for t in T["trials"] if set(t["cancers"]) & set(row.get("cancers", []))), T["trials"][0])
    none = "none reported" if not t["threshold"] else f"none at or above {t['threshold']:g}%, none serious"
    organs = []
    for a in (RC.patient_organs(row) or list(dict.fromkeys((row.get('boxed') or []) + (row.get('warn') or []))) or RC.AXES):
        o = t["organs"].get(a, {})
        evs = o.get("warned") or [e for e in (o.get("any"), o.get("serious")) if e]
        if len(evs) == 2 and evs[0]["term"] == evs[1]["term"]: evs = evs[:1]
        events = [_event(RC, e) for e in evs]
        organs.append(dict(organ=a, warned=bool(o.get("warned")), events=events, none=None if events else none, text="; ".join(e["text"] for e in events) or none))
    return dict(trial=t["trial"], nct=t["nct"], phase=t.get("phase"), population=t.get("population"), regimen=t["regimen"], n=t["n"],
                comparator=t.get("comparator"), threshold=t["threshold"], line=RC.trial_lines(row)[0].strip(), organs=organs,
                scale=(sc := RC.trial_scale([e for o in organs for e in o["events"]])), scale_text=f"0 to {sc}%",
                source=RC._trial_ae().get("snapshot"))


def _key_values(RC, row, notes, values, raw):
    """recommend._result_context's Key values for the selected row (its restriction's values first), plain text"""
    import labs as LB
    reasons = sorted(RC.reason_rows(row), key=lambda x: (-RC.RS.TIER[x[3]], not x[4]))
    relevant = list(dict.fromkeys(key for domain, *_ in reasons for key in RC.DOMAIN_VALUES.get(domain, ())))
    ordered = sorted((k for k in RC.VALUE_LABELS if values.get(k) is not None), key=lambda k: relevant.index(k) if k in relevant else len(relevant))
    out = []
    for k in ordered:
        label, unit = RC.VALUE_LABELS[k]; v = values[k]
        text = ("yes" if v else "no") if isinstance(v, bool) else (LB.shown(k, v) if isinstance(v, (int, float)) else str(v))
        out.append(f"CLcr ≈ {text} mL/min (eGFR)" if k == "crcl" and any(a == "Lab" and "CLcr ≈ eGFR" in b for a, b in notes) else f"{label} {text}{unit}" + LB.uln_text(k, raw))
    return out + RC._raw_values(raw, values)


def _patient_side(RC, row, domain, code, sure, values, conds, raw=None):
    """what of this patient meets the label rule behind one restriction row: the entered conditions it names and the values it
    reads ('Heart failure', 'Bilirubin 1.67×ULN'); a value the rule needs but nobody entered reads 'LVEF not entered'"""
    import labs as LB
    rrs = [rr for c, rr in (row["verdict"].known if sure else row["verdict"].possible) if rr["domain"] == domain and c == code]
    if not rrs: return ""
    w = rrs[0]["when"]; out = [RC.condition_name(c) for c in w.get("condition", []) if c in conds]
    keys = dict.fromkeys(k.rsplit("_", 1)[0] if k.rsplit("_", 1)[-1] in ("gt", "ge", "lt", "le") else k for k in w if k not in ("condition", "always"))
    for k in keys:
        if k not in RC.VALUE_LABELS: continue
        label, unit = RC.VALUE_LABELS[k]; v = values.get(k)
        if v is None: out.append(f"{label} not entered"); continue
        out.append(f"{label} " + (("yes" if v else "no") if isinstance(v, bool) else (LB.shown(k, v) if isinstance(v, (int, float)) else str(v))) + unit + LB.uln_text(k, raw))
    return ", ".join(out)


def _detail(RC, row, checks_, notes, values, raw, conds=()):
    """the result screen's panel for one ADC (recommend._result_details), with every number it prints"""
    ind = RC._indications().get(row.get("adc"))
    evidence = RC.reason_rows(row)
    evidence = [x for x in evidence if x[3] != "no_adjustment"] or evidence
    evidence.sort(key=lambda x: (-RC.RS.TIER[x[3]], not x[4], x[0]))
    mech = RC._mechanisms().get(row.get("adc")); payload = None
    if mech:
        note = mech.get("mechanism_note", "")
        keep = [x for x in re.split(r"(?<=\.)\s+(?=[A-Z])", note) if re.search(re.escape(mech["payload"]) + r"|microtubul|topoisomerase|DNA", x)][:2]
        t = lambda x: RC.MECH_TXT.get(x, x)
        rows = [["Payload", f"{mech['payload']} ({t(mech['payload_family'])})"], ["Action", t(mech["mechanism"])],
                ["Linker", f"{t(mech['linker'])}, " + ("cleavable" if mech["linker_cleavable"] == "True" else "non-cleavable")],
                ["Bystander effect", "yes" if mech["bystander"] == "True" else "no"]] + ([["Target", mech["target"]]] if mech.get("target") else [])
        payload = dict(line=RC.payload_line(mech), rows=rows, note=" ".join(keep) or None)
    return dict(indication=ind["indication"] if ind else None,
                reasons=[dict(organ=RC.ORGAN_SHORT[RC.RS.DOMAIN_AXIS[o]] if o in RC.RS.DOMAIN_AXIS else o.capitalize(), domain=o, status=st, basis=b, code=c, sure=sure,
                              patient=_patient_side(RC, row, o, c, sure, values, conds, raw)) for o, st, b, c, sure in evidence],
                warnings=[dict(organ=a, mark=mark, text=RC.warning_names(row["organs"][a].get("headings", [])))
                          for mark, organs in (("!!", row.get("boxed", [])), ("!", row.get("warn", []))) for a in organs],
                other_warnings=[dict(organ=c["organ"], mark=c["mark"], text=RC.warning_names(row["organs"][c["organ"]].get("headings", [])))
                                for c in _preview(RC, row)["other"]],
                trial=_trial(RC, row), missing=RC._missing_inputs(row["verdict"]) if row["verdict"].missing else [], payload=payload,
                checks=[test for test, names, _ in checks_ if (not names or row["name"] in names) and not test.startswith("enter ")],
                values=_key_values(RC, row, notes, values, raw))


def _row(RC, row, checks_, notes, values, raw, conds=()):
    v = row["verdict"]; tier = v.worst_possible; status = STATUS.get(tier, "None")
    if tier == 2 and any(c == "insufficient_data" for c, _ in v.known + v.possible): status = "Not studied"
    name = lambda d: RC.ORGAN_SHORT[RC.RS.DOMAIN_AXIS[d]] if d in RC.RS.DOMAIN_AXIS else d.capitalize()     # the organ names the other columns use
    cause = list(dict.fromkeys(name(d) for d, _, _, c, _ in RC.reason_rows(row) if RC.RS.TIER[c] == tier)) if tier > 0 else []   # what sets the level
    return dict(rank=row["rank"], tie=row["tie"], adc=row["adc"], name=row["name"], status=status, sure=v.worst_known == tier, cause=cause,
                known=max(0, v.worst_known),
                restriction=row["restriction"], restriction_ko=row["restriction_ko"], tier=tier, indicated=row["indicated"],
                boxed=row["boxed"], warn=row["warn"], elsewhere=row["elsewhere"], levels={a: row["organs"][a]["level"] for a in RC.AXES},
                preview=_preview(RC, row), cancers=row["cancers"], detail=_detail(RC, row, checks_, notes, values, raw, conds))


class App:
    def __init__(self, RC):
        self.RC, self.lock, self.jobs, self.jobs_lock, self.hosts = RC, threading.Lock(), {}, threading.Lock(), set()
        self.queue, self.worker, self.current, self.stopping = queue.SimpleQueue(), None, None, False

    @contextmanager
    def state(self, choice):
        """recommend's per-process state for one request: CHOICE from the request, the rest empty; put back afterwards"""
        RC = self.RC
        with self.lock:
            keep = RC.CHOICE, RC.PRIORITY, RC.FIRST
            RC.CHOICE, RC.PRIORITY, RC.FIRST = dict(choice), {}, None
            try: yield RC
            finally: RC.CHOICE, RC.PRIORITY, RC.FIRST = keep

    def conditions(self, body, allow_empty=False):
        """registry ids in registry order, then typed texts in the order given: the order form.run hands to recommend"""
        conds = body.get("conditions")
        if not isinstance(conds, list) or not all(isinstance(c, str) for c in conds): raise _Error(400, "conditions: a list of registry ids and typed texts is expected")
        texts = list(dict.fromkeys(" ".join(self.RC.nfc(c).split()) for c in conds if c.strip()))
        if not texts and not allow_empty: raise _Error(400, "Add at least one condition")
        return [i for i in self.RC._reg if i in texts] + [c for c in texts if c not in self.RC._reg]

    def choice(self, body, conds):
        choice = body.get("choice") or {}
        if not isinstance(choice, dict) or not all(v is None or (isinstance(v, str) and re.fullmatch(r"(MONDO|HP):\d+", v)) for v in choice.values()):
            raise _Error(400, "choice: {typed text: MONDO or HP id, or null} is expected")
        return {c: v for c, v in ((self.RC.nfc(k), x) for k, x in choice.items()) if c in conds}

    # ------------------------------------------------------------------ GET
    def app(self):
        import form, labs as LB
        from adc_version import APP_VERSION
        RC = self.RC
        try:
            import adc_updates
            info = adc_updates.current_info(); models = info.get("model_version") if info else None
        except Exception:
            models = None
        kind = {"sex": "sex", "child_pugh": "child_pugh", "ugt1a1": "yn", "esrd": "yn"}
        rule = {}                                   # the organ flag a value is checked against (labs.FLAGS): the page marks ✓ when it is not met
        for k, _, _, why in LB.FLAGS: rule.setdefault(k, why)
        fields = [dict(key=k, label=label, unit=unit, group=g, kind=kind.get(k, "number"), range=list(LB.RANGE[k]) if k in LB.RANGE else None, uln=LB.ULN.get(k),
                       rule=rule.get(k)) for k, label, unit, g in LB.FIELDS]
        return dict(version=APP_VERSION, models=models, n_adcs=len(RC._indications()) or 15, has_learned=bool(RC.HAS_LEARNED), axes=list(RC.AXES),
                    organ_short=RC.ORGAN_SHORT, organ_en=RC.EN, organ_ko=RC.ORGAN_KO,
                    mechanisms=list(RC._mechanisms().values()),
                    registry=[dict(id=i, label=r["label"], name=RC.condition_name(i), ko=RC.KO.get(i), mondo=r.get("mondo_id") or None,
                                   organs=[a for a in r["organ_axes"].split(";") if a]) for i, r in RC._reg.items()],
                    labs=dict(groups=list(dict.fromkeys(f["group"] for f in fields)), fields=fields), steps=STEPS)

    def suggest(self, q, picked=(), ai=False):
        """form.Form.conditions' lists: names (a cancer alias first), the words that are each a name, AI names on request, and
        diseases from symptoms when the text reads as a sentence. A disease is listed once, and not when it is already picked."""
        import suggest as SG
        RC = self.RC; text = RC.nfc(q).strip(); have = set()
        def names_of(s):                                       # the English name, and no Korean second line (the page is English)
            a, b = s[2], (s[3] if s[3] and s[3] != s[2] else "")
            if HANGUL.search(a) and b and not HANGUL.search(b): a, b = b, a
            return a, ("" if HANGUL.search(b) else b)
        def keys(x):                                           # id, MONDO id, either name
            mondo = RC._reg[x[1]].get("mondo_id") if x[0] == "reg" and x[1] in RC._reg else x[1] if str(x[1]).startswith("MONDO:") else None
            k = {(x[0], str(x[1]))} | {("name", n) for n in (re.sub(r"\W", "", str(x[2]).lower()),) if n}
            if mondo: k.add(("mondo", mondo))
            if x[3] and HANGUL.search(str(x[3])): k.add(("name", re.sub(r"\W", "", str(x[3]))))
            return k
        def fresh(x):
            k = keys(x)
            if k & have: return False
            have.update(k); return True
        def item(s, why=None):
            kind, val, label, detail, org = s
            if str(val).startswith("HP:"): detail = ""         # the semantic search puts its tag (증상) where a Korean name goes
            main, sub = names_of((kind, val, label, detail))
            mondo = (RC._reg[val].get("mondo_id") or None) if kind == "reg" else val if kind == "mondo" else None
            return dict(text=main, sub=sub, id=val if kind == "reg" else None, mondo=mondo, ko=next((x for x in (label, detail) if x and HANGUL.search(x)), None),
                        organs=list(org or []), kind="symptom" if why is not None else "registry" if kind == "reg" else "hpo" if str(val).startswith("HP:") else "mondo" if kind == "mondo" else "kcd",
                        cancer=RC.is_cancer(mondo), why="typed name" if why == "입력한 이름" else why,      # suggest's tag is for the Korean screens
                        pick=dict(condition=val if kind == "reg" else main if kind == "mondo" else label, choice=val if kind == "mondo" else None))
        for p in picked:
            have.update(keys(("reg", p, RC.condition_name(p), "") if p in RC._reg else ("mondo", p, "", "") if re.match(r"(MONDO|HP):", p) else ("text", p, p, "")))
        head = text if len(text) <= SENTENCE_MAX else text[:SENTENCE_MAX].rsplit(None, 1)[0]      # a pasted note: its first words are searched
        out = dict(q=q, names=[], parts=SG.parts(RC, q if head == text else head) if text else [], ai=[], symptoms=[], symptoms_error=None, already=None)
        if not text: return out
        alias = RC.cancer_alias(text)                          # a cancer name the search reads badly (HER2 양성 유방암: 양성 = benign)
        found = ([("mondo", alias, RC._cancer_map()["terms"][alias][0], text, [])] if alias else []) + SG.names(RC, q if head == text else head)
        if found and keys(found[0]) & have: out["already"] = item(found[0])["text"]      # the text's best name is picked: Enter must not take the next best
        out["names"] = [item(s) for s in found if fresh(s)]
        sentence = len(text) >= 4 and len(text.split()) >= 2 and not SG.parts(RC, head) and not SG.numbered_name(RC, head)
        if ai and RC.HAS_LEARNED and len(text) >= 2 and not sentence:
            try: res = SG.semantic(RC, head)
            except Exception: res = []
            out["ai"] = [item(s) for s in res if fresh(s)]
        if sentence:
            try: res = SG.symptoms(RC, head)
            except Exception as e: res = []; out["symptoms_error"] = f"{type(e).__name__}: {str(e)[:80]}"
            out["symptoms"] = [item(s, why) for s, why in res if fresh(s)]
        return out

    def _prune(self):
        """under jobs_lock: finished jobs older than KEEP go, then the oldest beyond JOBS (a queued one dropped here never runs)"""
        now = time.monotonic()
        for k, j in list(self.jobs.items()):
            if j["ended"] is not None and now - j["ended"] > KEEP: del self.jobs[k]
        while len(self.jobs) > JOBS:
            j = self.jobs.pop(next(iter(self.jobs)))
            if j["state"] == "queued": j.update(state="error", error="dropped", ended=now)

    def job(self, jid):
        """the job's state; a finished job is handed out once and then forgotten, with the patient's conditions and reports"""
        with self.jobs_lock:
            self._prune()
            job = self.jobs.get(jid)
            if job is None: raise _Error(404, "unknown analysis job")
            out = {k: v for k, v in job.items() if k not in ("started", "ended", "usage")}
            if out["state"] in ("done", "error"): del self.jobs[jid]
        elapsed = out["elapsed"] if out["elapsed"] is not None else time.monotonic() - job["started"] if job["started"] is not None else 0.0
        return dict(out, elapsed=round(elapsed, 1), usage="AI process   " + job["usage"].line())

    # ------------------------------------------------------------------ POST
    def labs(self, body):
        """the lab screen: parsed values, its error lines, x ULN for every field with a ULN (as the screen shows it under the
        field), CLcr, and the organs abnormal values mark"""
        import labs as LB
        raw, errors = _parse_raw(body.get("raw"))
        lab, _, notes = LB.derive(raw); uln = LB.uln_of(raw)
        flags = [dict(key=k, organ=organ, why=why) for k, test, organ, why in LB.FLAGS if raw.get(k) is not None and test(raw[k], uln.get(k))]
        source = None if "crcl" not in lab else "entered" if raw.get("crcl") is not None else "eGFR" if any(n.startswith("CLcr ≈ eGFR") for n in notes) else "Cockcroft-Gault"
        short = lambda k: "bili" if k == "bilirubin" else k                       # bili / ast / alt: the names the label rules read
        derived = dict(crcl=lab.get("crcl"), crcl_source=source, **{f"{short(k)}_xuln": float(LB._xuln(raw[k], u)) if k in raw else None for k, u in uln.items()},
                       shown=dict({"crcl": LB.shown("crcl", lab["crcl"])} if "crcl" in lab else {},
                                  **{short(k): LB.shown("bili", float(LB._xuln(raw[k], u))) for k, u in uln.items() if k in raw}))     # form.Form.labs: Bilirubin 1.67×ULN
        return dict(raw=raw, errors=errors, flags=flags, derived=derived, notes=notes, uln=uln)

    def analyze(self, body):
        """queue an analysis; it runs when the ones before it have finished"""
        import form
        conds = self.conditions(body); choice = self.choice(body, conds)
        with self.jobs_lock:
            jid = secrets.token_hex(8)
            self.jobs[jid] = job = dict(state="queued", step="", step_text="", started=None, ended=None, elapsed=None, error=None, conditions=conds,
                                        reports=[], ambiguous=[], unresolved=[], usage=form._ProcessUsage())
            self._prune()
            self.queue.put((job, conds, choice))
            if self.worker is None or not self.worker.is_alive():
                try:
                    self.worker = threading.Thread(target=self._work, daemon=True); self.worker.start()
                except RuntimeError as error:                                   # no thread: the job ends here, not as 'queued' forever
                    job.update(state="error", error=_one_line(error), ended=time.monotonic(), elapsed=0.0)
        return dict(job=jid)

    def _work(self):
        while True:
            item = self.queue.get()
            if item is None or self.stopping: return
            if item[0]["state"] == "queued": self._analyze(*item)

    def stop(self, wait=120):
        """at exit: no further analysis starts; the one running finishes (its thread is inside the models, and a process that
        exits around it aborts)"""
        self.stopping = True; self.queue.put(None)
        worker = self.worker
        if worker is None or not worker.is_alive(): return
        if self.current is not None: print("finishing the analysis", file=sys.stderr, flush=True)
        worker.join(wait)
        return worker.is_alive()

    def _analyze(self, job, conds, choice):
        """form.run step 2 in the worker: the analysis with its progress line, then the inputs that read as several diseases and
        those with no organ"""
        import form, suggest as SG
        def progress(event): job.update(step=event, step_text=STEP_TEXT.get(event, job["step_text"]))
        self.current = job; job.update(started=time.monotonic(), usage=form._ProcessUsage()); job["state"] = "running"
        try:
            with self.state(choice) as RC:
                reports = RC.analyze_conditions(conds, progress=progress)
                ko = SG.index(RC).ko; free = [c for c in conds if c not in RC._reg]
                out = [_report(RC, r, ko) for r in reports]
                applied = {r["condition"]: o["mondo"] for r in reports for o in r.get("readings", []) if o["name"] == r["name"]}
                groups = [g for g in RC.ambiguous_conditions(conds) if g[0] not in choice] if free else []
                ambiguous = []
                for text, readings in groups:
                    ambiguous.append(dict(text=text, default=RC.reading_default(readings, applied.get(text)),
                                          readings=[dict(mondo=o["mondo"], name=o["name"][:1].upper() + o["name"][1:], organs=list(o["organs"]), hpo=str(o["mondo"]).startswith("HP:")) for o in readings]))
                miss = RC.unresolved(conds) if free else []
            job.update(reports=out, ambiguous=ambiguous, unresolved=miss, step="done", elapsed=time.monotonic() - job["started"], ended=time.monotonic())
            job["state"] = "done"
        except Exception as error:
            _log(error)
            job.update(error=_one_line(error), elapsed=time.monotonic() - job["started"], ended=time.monotonic()); job["state"] = "error"
        finally:
            self.current = None

    def recommend(self, body):
        """form.run steps 3 and 4: the condition weighed first, then the result screen's rows and their panels"""
        import labs as LB
        conds = self.conditions(body, allow_empty=True); choice = self.choice(body, conds)
        raw, errors = _parse_raw(body.get("raw"))
        if errors: raise _Error(400, next(iter(errors.values())), errors=errors)
        first = body.get("first")
        if first is not None and not isinstance(first, str): raise _Error(400, "first: a condition or null is expected")
        first = first and self.RC.nfc(first)
        with self.state(choice) as RC:
            pc = RC.patient_conditions(conds, raw)
            picks = [(c, o) for c, o, _ in pc if not c.startswith("Lab: ")] if len(pc) >= 2 and len({frozenset(o) for _, o, _ in pc}) >= 2 else []
            if first is not None:
                if first not in dict(picks): raise _Error(400, "first: not a condition the Priority step offers")
                d = RC.default_levels(pc); RC.PRIORITY = {c: 0 if c == first else d[c] for c, _, _ in pc}; RC.FIRST = first
            rows, s, notes, ck = RC.recommend(conds, {}, raw)
            values = LB.derive(raw)[0] if raw else {}
            prio = rows[0]["priority"] if rows else []
            organ_levels = {}
            for level, _, organs in prio:
                for o in organs: organ_levels[o] = min(level, organ_levels.get(o, level))
            grouped = {}
            for o, level in sorted(organ_levels.items(), key=lambda x: (x[1], RC.AXES.index(x[0]))): grouped.setdefault(level, []).append(o)
            return dict(conditions=conds, first=RC.FIRST,
                        first_options=[dict(condition=c, name=RC.condition_name(c), organs=sorted(o, key=RC.AXES.index)) for c, o in picks],
                        rows=[_row(RC, r, ck, notes, values, raw, conds) for r in rows], s=s, priority=[list(p) for p in prio],
                        notes=[list(n) for n in notes], checks=[[test, names] for test, names, _ in ck],
                        patient=dict(values=_key_values(RC, rows[0], notes, values, raw) if rows else [], organ_levels=organ_levels,
                                     organ_priority=[[level, organs] for level, organs in grouped.items()],
                                     unmapped=[c for c, how in notes if "not understood" in how],
                                     cancers=[dict(condition=c, name=n, cancers=list(cs)) for c, (n, cs) in RC.patient_cancers(notes).items()]))

    # ------------------------------------------------------------------ routes
    def get(self, path, query):
        if path == "/api/app": return self.app()
        if path == "/api/suggest": return self.suggest(query.get("q", [""])[0], query.get("picked", []), query.get("ai", ["0"])[0] == "1")
        m = re.fullmatch(r"/api/analyze/(\w+)", path)
        if m: return self.job(m.group(1))
        m = re.fullmatch(r"/(?:static/)?([\w.-]+)", path)          # a page file, at /static/<name> or /<name>
        name = "index.html" if path == "/" else m.group(1) if m else None
        files = _page()
        if name not in files: raise _Error(404, "not found")
        suffix = Path(name).suffix
        return TYPES[suffix], base64.b64decode(files[name]) if suffix in BINARY else files[name]

    def post(self, path, body):
        routes = {"/api/labs": self.labs, "/api/analyze": self.analyze, "/api/recommend": self.recommend}
        if path not in routes: raise _Error(404, "not found")
        return routes[path](body)


GONE = (BrokenPipeError, ConnectionResetError)              # the tab was closed or reloaded mid-answer: nothing to report


def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version, sys_version = "ADCTOX", ""
        timeout = 30                                            # a client that sends less than it announced does not hold a thread

        def version_string(self): return self.server_version

        def log_message(self, *args): pass                     # no access log in the terminal

        def send(self, status, data, ctype=JSON, headers=()):
            if isinstance(data, str): data = data.encode("utf-8")
            try:
                if len(data) > GZIP_FROM and "gzip" in self.headers.get("Accept-Encoding", ""):
                    data = gzip.compress(data, 6); headers = [*headers, ("Content-Encoding", "gzip")]
                self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
                for k, v in headers: self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD": self.wfile.write(data)
            except GONE:
                self.close_connection = True

        def gate(self, path):
            """another site's page can reach 127.0.0.1 too: by DNS rebinding (Host), or with a no-cors 'simple' request that
            needs no preflight (Origin, Sec-Fetch-Site, a JSON content type)"""
            host = self.headers.get("Host") or ""
            if not _loopback(host): raise _Error(403, "this server answers 127.0.0.1 only")
            if self.command != "GET" or path.startswith("/api/"):
                origin, site = self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site")
                allowed_origins = (f"http://{host}", f"https://{host}") if _remote_enabled() else (f"http://{host}",)
                if origin is not None and origin not in allowed_origins: raise _Error(403, "cross-origin request refused")
                if site is not None and site not in ("same-origin", "none"): raise _Error(403, "cross-site request refused")
            if self.command == "POST" and (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                raise _Error(415, "Content-Type: application/json is expected")

        def body(self):
            try: n = int(self.headers.get("Content-Length") or 0)
            except ValueError: raise _Error(400, "Content-Length is not a number") from None
            if n < 0: raise _Error(400, "Content-Length is negative")
            if n > 1 << 20: raise _Error(413, "request too large")
            try: body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: raise _Error(400, "invalid JSON") from None
            if not isinstance(body, dict): raise _Error(400, "a JSON object is expected")
            return body

        def route(self):
            url = urlsplit(self.path)
            try:
                self.gate(url.path)
                if self.command == "GET": out = app.get(url.path, parse_qs(url.query))
                elif self.command == "POST": out = app.post(url.path, self.body())
                else: raise _Error(405, "method not allowed")
            except _Error as e:
                return self.send(e.status, json.dumps(dict(error=str(e), **e.extra), ensure_ascii=False), headers=[("Allow", "GET, POST")] if e.status == 405 else ())
            except GONE:
                self.close_connection = True; return
            except Exception as e:
                _log(e)
                return self.send(500, json.dumps(dict(error=_one_line(e)), ensure_ascii=False))
            if isinstance(out, tuple): self.send(200, out[1], out[0])
            else: self.send(200, json.dumps(out, ensure_ascii=False, default=_plain))

        do_GET = do_POST = do_HEAD = do_OPTIONS = do_PUT = do_DELETE = do_PATCH = route
    return Handler


class _Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"          # on Windows SO_REUSEADDR lets a second process bind a port that is in use
    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if not isinstance(error, GONE): _log(error)


def _remote_enabled():
    bind = os.environ.get("ADCTOX_HOST", "").strip()
    allow = os.environ.get("ADCTOX_ALLOWED_HOSTS", "").strip()
    return bool(allow) or (bool(bind) and bind.lower() not in ("127.0.0.1", "localhost", "::1"))


def _loopback(host):
    """a Host header naming this computer, on any port: the port differs behind an SSH tunnel (ssh -L 8080:127.0.0.1:<port>),
    while a DNS-rebinding page carries its own domain name. When ADCTOX_HOST / ADCTOX_ALLOWED_HOSTS is set for server hosting,
    configured hosts are permitted too."""
    name = (host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]").lower()
    if name in ("127.0.0.1", "localhost", "[::1]"): return True
    if not _remote_enabled(): return False
    allow = [x.strip().lower() for x in os.environ.get("ADCTOX_ALLOWED_HOSTS", "").split(",") if x.strip()]
    bind = os.environ.get("ADCTOX_HOST", "").strip().lower()
    if "*" in allow or (bind == "0.0.0.0" and not allow): return bool(name)
    return name in allow or name == bind


def _host():
    return os.environ.get("ADCTOX_HOST", "").strip() or "127.0.0.1"


def make_server(RC, port=0):
    app = App(RC); bind = _host()
    try: server = _Server((bind, port), _handler(app))
    except OSError as e:
        if not port: raise
        raise SystemExit(f"adctox --web: port {port} is in use (another ADCTOX web?). Close it or set another ADCTOX_PORT.") from e
    server.app = app; app.hosts = {f"127.0.0.1:{server.server_port}", f"localhost:{server.server_port}"}
    return server


def _port():
    """ADCTOX_PORT: a fixed port, so an SSH tunnel command can stay the same between starts; unset or empty, a free one"""
    raw = os.environ.get("ADCTOX_PORT", "").strip()
    if not raw: return 0
    if not raw.isdigit() or not 1 <= int(raw) <= 65535: raise SystemExit(f"adctox --web: ADCTOX_PORT must be a port number (1 to 65535), not {raw!r}")
    return int(raw)


def serve(RC, open_browser=True, ready=None):
    """serve until Ctrl-C (or server.shutdown(); `ready` gets the server once it listens)"""
    import webbrowser, suggest as SG
    from adc_version import APP_VERSION
    server = make_server(RC, _port()); url = f"http://127.0.0.1:{server.server_port}/"
    threading.Thread(target=SG.index(RC).load_mondo, daemon=True).start()       # MONDO and KCD names for the search, as the first screen loads them
    print(f"ADCTOX {APP_VERSION}   {url}\nOpening it in the browser. Ctrl-C to quit", flush=True)
    if open_browser and os.environ.get("ADCTOX_NO_BROWSER") != "1":      # once serving: a browser that holds on until it exits (w3m, a BROWSER script) gets answers
        timer = threading.Timer(0.3, webbrowser.open, args=(url,)); timer.daemon = True; timer.start()
    if ready: ready(server)
    try: server.serve_forever()
    except KeyboardInterrupt: print(file=sys.stderr)
    finally:
        server.server_close()
        try: stuck = server.app.stop()
        except KeyboardInterrupt: _leave(130)                                  # Ctrl-C again while the analysis finishes: leave now
        if stuck: _leave(0)                             # still inside the models after the wait: a normal exit would abort around it


def _leave(code):
    """exit without the interpreter's shutdown, which aborts while another thread is inside torch"""
    sys.stdout.flush(); sys.stderr.flush(); os._exit(code)
