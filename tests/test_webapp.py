"""adctox --web (0.6.3): the browser steps get from ml/webapp.py what the terminal screens show, as data, from a server that
answers 127.0.0.1 and same-origin requests only, runs analyses one at a time, and serves the page from memory in the one-file build."""
import http.client, json, re, signal, socket, subprocess, sys, pathlib, threading, time, types
from urllib.parse import quote
import pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import term, tui
import recommend as RC, webapp, suggest
LOAD_MONDO = suggest.Index.load_mondo           # the module's server patches it out; the index test needs the real one

plain = lambda t: re.sub(r"\x1b\[[\d;]*m", "", t)
HER2 = dict(conditions=["HER2 양성 유방암", "interstitial_lung_disease", "heart_failure"],
            raw={"bilirubin": 2.0, "creatinine": 1.4, "age": 68, "sex": "F", "weight": 55}, choice={}, first=None)


@pytest.fixture(scope="module")
def server():
    import suggest as SG
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ADCTOX_NO_BROWSER", "1")
        mp.setattr(SG.Index, "load_mondo", lambda self: None)              # registry and profile names: no model files read
        opened = []; mp.setattr("webbrowser.open", opened.append)
        box, up = [], threading.Event()
        t = threading.Thread(target=webapp.serve, args=(RC,), kwargs=dict(ready=lambda s: (box.append(s), up.set())), daemon=True); t.start()
        assert up.wait(10) and box[0].server_address[0] == "127.0.0.1"
        time.sleep(0.5); assert not opened
        yield box[0]
        port = box[0].server_port; box[0].shutdown(); t.join(10)
    assert not t.is_alive()
    with pytest.raises(ConnectionRefusedError): socket.create_connection(("127.0.0.1", port), timeout=2)


def request(server, method, path, body=None, headers=None):
    """-> (status, response headers, body bytes); a JSON body is sent as application/json unless headers say otherwise"""
    c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=60)
    data = body if isinstance(body, (bytes, str)) or body is None else json.dumps(body)
    c.request(method, path, body=data, headers={"Content-Type": "application/json"} | (headers or {}))
    r = c.getresponse(); out = r.read(); c.close()
    return r.status, dict(r.getheaders()), out


def call(server, method, path, body=None, host=None, headers=None):
    status, h, data = request(server, method, path, body, ({"Host": host} if host else {}) | (headers or {}))
    return status, json.loads(data) if h.get("Content-Type", "").startswith("application/json") else (h.get("Content-Type"), data.decode())


def finished(server, jid):
    """poll a job until it is done or failed; that answer is the last one the server gives for it"""
    for _ in range(600):
        status, job = call(server, "GET", f"/api/analyze/{jid}")
        assert status == 200, job
        if job["state"] not in ("queued", "running"): return job
        time.sleep(0.05)
    raise AssertionError("the analysis did not finish")


def _linked(monkeypatch, mondo, name, axes):
    link = dict(mondo=mondo, name=name, sim=1.0, judge=True, gate=True, axes=axes, readings=[], ambiguous=False)
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: ([("cirrhosis", 0.1)] * len(free), [dict(link) for _ in free], None))


def test_app_lists_the_axes_the_registry_and_the_lab_fields(server):
    from adc_version import APP_VERSION
    status, d = call(server, "GET", "/api/app")
    assert status == 200 and d["version"] == APP_VERSION and d["n_adcs"] == 15
    assert d["axes"] == RC.AXES and len(d["axes"]) == 13 and d["organ_short"]["pulmonary"] == "Lung" and d["organ_ko"]["hepatic"] == "간"
    reg = {r["id"]: r for r in d["registry"]}
    assert len(d["registry"]) == 41 and list(reg) == list(RC._reg)
    assert reg["chronic_liver_disease"] | {"label": None} == dict(id="chronic_liver_disease", label=None, name=RC.condition_name("chronic_liver_disease"),
                                                                  ko="만성 간질환", mondo="MONDO:0005154", organs=["hepatic"])
    assert d["labs"]["groups"] == ["Basic", "Kidney", "Liver", "Blood", "Glucose", "Pancreas", "Thyroid", "Cardio", "Genotype"]
    f = {x["key"]: x for x in d["labs"]["fields"]}
    assert f["creatinine"] == dict(key="creatinine", label="Creatinine", unit="mg/dL", group="Kidney", kind="number", range=[0.05, 30], uln=None)
    assert f["bilirubin"]["uln"] == 1.2 and (f["sex"]["kind"], f["child_pugh"]["kind"], f["ugt1a1"]["kind"]) == ("sex", "child_pugh", "yn")
    assert d["steps"] == ["질환", "검사 수치", "AI 장기 분석", "우선순위", "결과"] and d["first_text"] == RC.FIRST_TEXT


def test_suggestions_are_the_first_screens_names_and_symptom_diseases(server, monkeypatch):
    import suggest as SG
    status, d = call(server, "GET", "/api/suggest?q=cirr")
    assert status == 200 and d["symptoms"] == [] and d["parts"] == []
    found = [s[1] for s in SG.names(RC, "cirr")]; mondo = RC._reg["cirrhosis"]["mondo_id"]
    assert mondo in found and [x["pick"]["choice"] or x["pick"]["condition"] for x in d["names"]] == [v for v in found if v != mondo]   # suggest's order, a disease once
    cirr = next(x for x in d["names"] if x["id"] == "cirrhosis")
    assert cirr == dict(text="Cirrhosis", sub="간경변", id="cirrhosis", mondo=RC._reg["cirrhosis"]["mondo_id"], ko="간경변", organs=["hepatic"],
                        kind="registry", cancer=False, why=None, pick=dict(condition="cirrhosis", choice=None))
    assert "cirrhosis" not in [x["id"] for x in call(server, "GET", "/api/suggest?q=cirr&picked=cirrhosis")[1]["names"]]    # picked: not offered again
    ko = call(server, "GET", "/api/suggest?q=" + quote("간경"))[1]["names"]
    assert ko[0]["text"] == "간경변" and ko[0]["sub"] == "Cirrhosis"                                                       # Korean typed: Korean first
    monkeypatch.setattr(RC, "HAS_LEARNED", False)                                                                        # n-grams only: no model
    q = "숨이 차고 다리가 부어요"
    d = call(server, "GET", "/api/suggest?q=" + quote(q))[1]
    assert d["names"] == [] and d["symptoms"] and all(x["kind"] == "symptom" and x["why"] for x in d["symptoms"])
    assert [x["pick"]["choice"] or x["pick"]["condition"] for x in d["symptoms"]] == [s[1] for s, _ in SG.symptoms(RC, q, semantic=False)]
    assert "심부전" in [x["text"] for x in d["symptoms"]]
    her2 = call(server, "GET", "/api/suggest?q=" + quote("HER2 양성 유방암"))[1]["names"][0]                               # the cancer alias row first
    assert her2["pick"] == dict(condition="HER2 양성 유방암", choice="MONDO:0006244") and her2["cancer"]


def test_the_search_reads_the_old_index_or_the_new_one_never_half(tmp_path, monkeypatch):
    """the MONDO names arrive in the background (about 6 s): a search meanwhile reads the registry and profile names whole"""
    import numpy as np, adc_runtime, scratch_runtime as SR
    n = 20000                                                    # a stand-in index, large enough to read the rows while it loads
    np.savez(tmp_path / "mondo_index.npz", ids=np.array([f"MONDO:9{k:06d}" for k in range(n)]), names=np.array([f"stand-in disease {k}" for k in range(n)]),
             axes=np.eye(13)[np.arange(n) % 13])
    monkeypatch.setitem(sys.modules, "mondo_index", types.SimpleNamespace(C=f"{tmp_path}/", AXES=list(RC.AXES)))
    monkeypatch.setattr(adc_runtime, "model_path", lambda name, fallback: str(fallback)); monkeypatch.setattr(SR, "available", lambda: False)
    I = suggest.Index(RC); before = len(I.rows); seen = set()
    loader = threading.Thread(target=LOAD_MONDO, args=(I,)); loader.start()
    while loader.is_alive(): seen.add(len(I.rows)); time.sleep(0.0005)
    loader.join(); after = len(I.rows)
    assert after == before + n and seen <= {before, after} and I.organs["MONDO:9000001"] == [RC.AXES[1]] and I.mondo_loaded


def test_lab_values_are_parsed_flagged_and_derived_as_the_lab_screen_does(server):
    import labs as LB
    raw = {"hb": "8", "platelet": "abc", "anc": "0", "bilirubin": 2.0, "age": 68, "sex": "여", "weight": 55, "creatinine": "1.4", "ugt1a1": True}
    status, d = call(server, "POST", "/api/labs", {"raw": raw})
    assert status == 200 and d["raw"] == {"hb": 8.0, "bilirubin": 2.0, "age": 68.0, "sex": "F", "weight": 55.0, "creatinine": 1.4, "ugt1a1": True}
    assert d["errors"] == {"platelet": "Platelet: 숫자를 입력하세요", "anc": "ANC: 0.01–100 x10³/µL 사이로 입력하세요"}
    assert d["flags"] == [{"key": "hb", "organ": "haematologic", "why": "Hb < 10 g/dL (CTCAE anaemia G2)"},
                          {"key": "bilirubin", "organ": "hepatic", "why": "bilirubin > 1.5 x ULN (CTCAE G2)"}]
    assert d["derived"] | {"shown": None} == dict(crcl=LB.cockcroft_gault(68, 55, 1.4, "F"), crcl_source="Cockcroft-Gault", bili_xuln=LB.derive(d["raw"])[0]["bili"],
                                                  ast_xuln=None, alt_xuln=None, ggt_xuln=None, amylase_xuln=None, lipase_xuln=None, shown=None)
    assert d["derived"]["shown"] == {"crcl": "33.4", "bili": "1.67"} and d["notes"][0] == "CLcr 33.4 mL/min (Cockcroft-Gault)"
    assert call(server, "POST", "/api/labs", {"raw": {"egfr": 40}})[1]["derived"]["crcl_source"] == "eGFR"
    d = call(server, "POST", "/api/labs", {"raw": {"ggt": 150, "amylase": "200", "lipase": 100, "ast": 50}})[1]["derived"]      # x ULN under every field that has one
    assert d["shown"] == {"ast": "1.25", "ggt": "2.5", "amylase": "2", "lipase": "1.67"} and d["ggt_xuln"] == 2.5 and d["bili_xuln"] is None
    status, d = call(server, "POST", "/api/labs", {"raw": {"cholesterol": 200}})
    assert status == 400 and "cholesterol" in d["error"]


def test_the_analysis_runs_in_a_job_and_reports_what_the_analysis_screen_shows(server, monkeypatch):
    import scratch_runtime as SR
    p = {a: 0.01 for a in RC.AXES}; p.update(hepatic=0.97, gastrointestinal=0.41, renal=0.002)
    monkeypatch.setattr(SR, "available", lambda: True)
    monkeypatch.setattr(SR, "judge", lambda texts: [dict(p=p) for _ in texts])
    RC._ANALYSES.clear(); RC._REG_P.clear()
    try:
        status, d = call(server, "POST", "/api/analyze", {"conditions": ["cirrhosis"]})
        assert status == 200
        job = finished(server, d["job"])
    finally: RC._ANALYSES.clear(); RC._REG_P.clear()
    assert job["state"] == "done" and job["step"] == "done" and job["step_text"] == "장기 분석 중" and job["error"] is None
    assert job["elapsed"] >= 0 and job["usage"].startswith("AI process   CPU ") and job["ambiguous"] == [] and job["unresolved"] == []
    (r,) = job["reports"]
    assert r["source"] == "Registry" and r["shown"] == "Cirrhosis" and r["organs"] == ["hepatic"] and r["p"] == p and r["how"] == "Registry"
    assert [(c["organ"], c["used"], c["text"]) for c in r["likely"]] == [("hepatic", True, "97%"), ("gastrointestinal", False, "41%"), ("haematologic", False, "1%")]
    assert plain(__import__("form").likely(RC.AXES, ["hepatic"], p)) == "  ".join(f"{tui.GLYPH[c['organ']]} {c['text']}" for c in r["likely"])
    assert call(server, "GET", f"/api/analyze/{d['job']}")[0] == 404                                # handed out once, then forgotten
    assert call(server, "GET", "/api/analyze/nosuchjob")[0] == 404


def test_a_second_analysis_waits_its_turn(server, monkeypatch):
    gate, calls = threading.Event(), []
    def slow(conds, progress=None):
        calls.append(list(conds)); progress("judging"); gate.wait(20); return []
    monkeypatch.setattr(RC, "analyze_conditions", slow)
    a = call(server, "POST", "/api/analyze", {"conditions": ["cirrhosis"]})[1]["job"]
    for _ in range(200):
        if call(server, "GET", f"/api/analyze/{a}")[1]["state"] == "running": break
        time.sleep(0.02)
    status, b = call(server, "POST", "/api/analyze", {"conditions": ["copd"]})
    assert status == 200
    jb = call(server, "GET", f"/api/analyze/{b['job']}")[1]
    assert (jb["state"], jb["step"], jb["step_text"], jb["elapsed"], jb["conditions"]) == ("queued", "", "", 0.0, ["copd"])
    ja = call(server, "GET", f"/api/analyze/{a}")[1]
    assert (ja["state"], ja["step"], ja["step_text"]) == ("running", "judging", "장기 분석 중")
    gate.set()
    assert finished(server, a)["state"] == finished(server, b["job"])["state"] == "done" and calls == [["cirrhosis"], ["copd"]]


def test_a_job_without_a_worker_ends_as_an_error(monkeypatch):
    class NoThread(threading.Thread):
        def start(self): raise RuntimeError("can't start new thread")
    app = webapp.App(RC); monkeypatch.setattr(webapp.threading, "Thread", NoThread)
    job = app.job(app.analyze({"conditions": ["cirrhosis"]})["job"])
    assert (job["state"], job["error"]) == ("error", "RuntimeError: can't start new thread")


def test_the_browser_opens_once_the_server_answers(monkeypatch):
    import urllib.request
    monkeypatch.delenv("ADCTOX_NO_BROWSER", raising=False); monkeypatch.setattr(suggest.Index, "load_mondo", lambda self: None)
    got, box, up = [], [], threading.Event()
    def browser(url):                                            # a console browser holds on until it has the page (w3m, a BROWSER script)
        got.append(urllib.request.urlopen(url + "api/app", timeout=5).status); up.set()
    monkeypatch.setattr("webbrowser.open", browser)
    t = threading.Thread(target=webapp.serve, args=(RC,), kwargs=dict(ready=box.append), daemon=True); t.start()
    try: assert up.wait(15) and got == [200]
    finally:
        if box: box[0].shutdown()
        t.join(10)


def test_a_finished_job_expires(server, monkeypatch):
    monkeypatch.setattr(RC, "analyze_conditions", lambda conds, progress=None: [])
    monkeypatch.setattr(webapp, "KEEP", 0.0)
    jid = call(server, "POST", "/api/analyze", {"conditions": ["cirrhosis"]})[1]["job"]
    for _ in range(200):
        if server.app.jobs.get(jid, {}).get("state") == "done": break
        time.sleep(0.02)
    time.sleep(0.01)
    assert call(server, "GET", f"/api/analyze/{jid}")[0] == 404


def _review_frame(monkeypatch, reports, ko):
    """the analysis table as the terminal draws it"""
    import form, suggest as SG
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True); monkeypatch.setattr(term._Screen, "_size", lambda self: (40, 160))
    monkeypatch.setattr(SG, "index", lambda RC: types.SimpleNamespace(ko=ko))
    screen = term._Screen(console); frames = []
    keys = iter([console.KEY_NPAGE])
    screen.refresh = lambda: frames.append(["".join(ch for ch, _ in line) for line in screen.buf]); screen.get_wch = lambda: next(keys)
    monkeypatch.setitem(form.APP_CHECK, "started", True)                       # no app update check from the test
    F = form.Form(screen, RC); F.step = 2
    assert F._analysis_review(reports, 1.0) is None
    return "\n".join(frames[-1])


def test_read_as_and_how_are_the_analysis_screens(monkeypatch):
    monkeypatch.setitem(RC.CHOICE, "short breath", "HP:0002094")
    base = dict(estimates=[], readings=[], ambiguous=False, p=None, judge_via=None, fallback=None, gemma=None)
    reports = [dict(base, condition="cirrhosis", source="Registry", name="Cirrhosis", mondo="MONDO:0005155", organs=["hepatic"]),
               dict(base, condition="치매", source="MONDO", name="dementia", mondo="MONDO:0001627", organs=["neurologic"], judge_via="record"),
               dict(base, condition="adhd", source="MONDO (no organ axis)", name="attention deficit hyperactivity disorder", mondo="MONDO:0007743", organs=[], judge_via="label"),
               dict(base, condition="short breath", source="Chosen", name="Dyspnea", mondo=None, organs=["pulmonary"]),
               dict(base, condition="asdfgh", source="Unmapped", name="", mondo=None, organs=[], fallback="RuntimeError: x"),
               dict(base, condition="glaucoma ms", source="Similar condition", name="Glaucoma", mondo=None, organs=["ocular"], fallback="RuntimeError: x",
                    ambiguous=True, readings=[dict(mondo="MONDO:1", name="a", organs=[]), dict(mondo="MONDO:2", name="b", organs=["ocular"])])]
    ko = {"MONDO:0001627": "치매"}
    text = _review_frame(monkeypatch, reports, ko)
    out = [webapp._report(RC, r, ko) for r in reports]
    assert [(x["read_as"], x["how"]) for x in out] == [("", "Registry"), ("", "MONDO (record)"), ("attention deficit hyperactivity disorder", "MONDO (label)"),
                                                       ("Dyspnea", "Chosen"), ("", "Not understood"), ("Glaucoma", "Similar registry condition (linker)")]
    for x in out:                                                                   # each row of the terminal table, word for word
        row = next(ln for ln in text.splitlines() if ln.strip().lstrip("› ").startswith(x["shown"][:20]))
        assert re.search(re.escape(((x["read_as"] + "  ") if x["read_as"] else "") + x["how"]) + r"(\s|$)", row), (x, row)
        if x["tag"]: assert x["tag"] in text
    assert out[2]["no_organs"] == "none of 13" and out[4]["no_organs"] == "-" and out[5]["tag"] == "2 meanings: pick on the next screen"


def _direct(monkeypatch, first=None):
    """the result rows as form.run computes them for the same patient"""
    conds = [i for i in RC._reg if i in HER2["conditions"]] + ["HER2 양성 유방암"]           # registry order, then typed text (form.run)
    raw = {k: float(v) if not isinstance(v, str) else v for k, v in HER2["raw"].items()}
    monkeypatch.setattr(RC, "FIRST", None); monkeypatch.setattr(RC, "PRIORITY", {}); monkeypatch.setattr(RC, "FALLBACK", {}); monkeypatch.setattr(RC, "CHOICE", {})
    pc = RC.patient_conditions(conds, raw)
    if first:
        d = RC.default_levels(pc); monkeypatch.setattr(RC, "PRIORITY", {c: 0 if c == first else d[c] for c, _, _ in pc}); monkeypatch.setattr(RC, "FIRST", first)
    return RC.recommend(conds, {}, raw), raw


def _event_line(e):
    """one event as the page writes it from its fields (term, a, n, comp, sa, serious)"""
    pct = lambda a, n: f"{100 * a / n:.1f}%"
    return (f"{e['term']} {'serious ' if e['serious'] else ''}{e['a']}/{e['n']} ({pct(e['a'], e['n'])}" + (f", vs {pct(*e['comp'])}" if e["comp"] else "") + ")"
            + (f", serious {e['sa']}/{e['n']}" if e["sa"] and not e["serious"] else ""))


def test_recommend_carries_every_number_the_result_screen_prints(server, monkeypatch):
    _linked(monkeypatch, "MONDO:0006244", "HER2 positive breast carcinoma", [])
    status, d = call(server, "POST", "/api/recommend", HER2)
    assert status == 200 and d["conditions"] == [i for i in RC._reg if i in HER2["conditions"]] + ["HER2 양성 유방암"] and d["first"] is None
    assert sorted(o["condition"] for o in d["first_options"]) == ["heart_failure", "interstitial_lung_disease"]   # lab findings and the cancer are not offered
    assert RC.FIRST is None and RC.PRIORITY == {} and RC.CHOICE == {} and RC.FALLBACK == {}                    # put back after the request
    tdxd = next(r for r in d["rows"] if r["adc"] == "trastuzumab-deruxtecan")
    trial = tdxd["detail"]["trial"]
    assert trial["trial"] == "DESTINY-Breast02" and trial["n"] == 404 and trial["comparator"]["n"] == 195
    lung = next(o for o in trial["organs"] if o["organ"] == "pulmonary")
    ev = lung["events"][0]
    assert (ev["term"], ev["a"], ev["n"], ev["comp"], ev["sa"], ev["serious"]) == ("pneumonitis", 25, 404, [0, 195], 10, False)
    assert ev["text"] == "pneumonitis 25/404 (6.2%, vs 0.0%), serious 10/404" and lung["warned"] and lung["none"] is None
    assert {"organ": "pulmonary", "mark": "!!", "text": "Interstitial Lung Disease/Pneumonitis"} in tdxd["detail"]["warnings"]
    assert "HER2+ breast cancer" in tdxd["cancers"] and tdxd["indicated"] and not tdxd["detail"]["missing"]
    assert d["patient"]["cancers"] == [dict(condition="HER2 양성 유방암", name=RC._cancer_map()["terms"]["MONDO:0006244"][0], cancers=RC._cancer_map()["terms"]["MONDO:0006244"][1])]
    (rows, s, notes, ck), raw = _direct(monkeypatch)
    assert [r["adc"] for r in d["rows"]] == [r["adc"] for r in rows] and d["s"] == s and d["notes"] == [list(n) for n in notes]
    values = __import__("labs").derive(raw)[0]; n_events = 0
    for i, (mine, row) in enumerate(zip(d["rows"], rows)):
        text = "\n".join(map(plain, RC._result_details(row, ck, 200)))
        detail = json.dumps(mine["detail"], ensure_ascii=False)
        for n in re.findall(r"\d+(?:\.\d+)?%?", text): assert n in detail, (row["name"], n)
        trial, lines = mine["detail"]["trial"], [ln.strip() for ln in RC.trial_lines(row)]
        if trial and "no_results" in trial: assert lines == [trial["no_results"]]
        elif trial:                                                  # the TUI's trial lines, rebuilt from the numbers alone
            head = f"{trial['trial']}, {trial['regimen']}, n={trial['n']}" + (f"; vs {trial['comparator']['regimen']}, n={trial['comparator']['n']}" if trial["comparator"] else "")
            assert lines == [head] + [f"{RC.ORGAN_SHORT[o['organ']]:<9} " + ("; ".join(map(_event_line, o["events"])) or o["none"]) for o in trial["organs"]]
            t = next(x for x in RC._trial_ae()["adcs"][row["adc"]]["trials"] if x["trial"] == trial["trial"])
            for o in trial["organs"]:
                src = t["organs"].get(o["organ"], {}); evs = src.get("warned") or [e for e in (src.get("any"), src.get("serious")) if e]
                if len(evs) == 2 and evs[0]["term"] == evs[1]["term"]: evs = evs[:1]
                assert len(evs) == len(o["events"])
                for e, mine_e in zip(evs, o["events"]):              # the trial table's numbers, unchanged, and the TUI's text of them
                    assert {k: mine_e[k] for k in e} == e and mine_e["text"] == RC._event_text(e) and mine_e["pct"] == f"{100 * e['a'] / e['n']:.1f}%"
                    assert mine_e["comp_pct"] == (f"{100 * e['comp'][0] / e['comp'][1]:.1f}%" if e.get("comp") else None); n_events += 1
        else: assert lines == []
        assert [ln.strip() for ln in RC.organ_warning_lines(row)] == [f"{RC.ORGAN_SHORT[w['organ']]:<9} {w['mark']:<2}  {w['text']}".strip() for w in mine["detail"]["warnings"]]
        context = "\n".join(map(plain, RC._result_context(rows, notes, 400, values, i, raw=raw)))
        assert all(v in context for v in mine["detail"]["values"][:3])                                             # the Key values the screen lists
        lines, at = RC._result_list([row], 140)
        assert (mine["status"] + ("" if mine["sure"] else "?")) in re.split(r"\s{3,}", plain(lines[at[0]]).strip())    # the list's cell, exactly
    assert n_events > 10 and d["patient"]["values"] == d["rows"][0]["detail"]["values"]
    gem = next(r for r in d["rows"] if r["adc"] == "gemtuzumab-ozogamicin")
    assert gem["detail"]["trial"]["no_results"] == "no results posted on ClinicalTrials.gov (ALFA-0701, NCT00927498)"


def test_first_reorders_the_rows_as_the_priority_step_does(server, monkeypatch):
    _linked(monkeypatch, "MONDO:0006244", "HER2 positive breast carcinoma", [])
    auto = call(server, "POST", "/api/recommend", HER2)[1]
    status, picked = call(server, "POST", "/api/recommend", HER2 | {"first": "interstitial_lung_disease"})
    assert status == 200 and picked["first"] == "interstitial_lung_disease"
    (rows, *_), _ = _direct(monkeypatch, "interstitial_lung_disease")
    assert [r["adc"] for r in picked["rows"]] == [r["adc"] for r in rows] != [r["adc"] for r in auto["rows"]]
    assert [(r["rank"], r["tie"]) for r in picked["rows"]] == [(r["rank"], r["tie"]) for r in rows]
    for first in ("HER2 양성 유방암", ["interstitial_lung_disease"], 3):
        status, bad = call(server, "POST", "/api/recommend", HER2 | {"first": first})
        assert status == 400 and bad["error"], first
    status, bad = call(server, "POST", "/api/recommend", HER2 | {"raw": {"hb": "80"}})
    assert status == 400 and bad["errors"] == {"hb": "Hb: 1–25 g/dL 사이로 입력하세요"}


def test_page_files_are_served_to_this_computer_only(server, monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "_page", lambda: {"index.html": "<p>ADCTOX</p>", "app.js": "go()"})
    assert call(server, "GET", "/") == (200, ("text/html; charset=utf-8", "<p>ADCTOX</p>"))
    assert call(server, "GET", "/static/app.js") == call(server, "GET", "/app.js") == (200, ("text/javascript; charset=utf-8", "go()"))
    assert call(server, "GET", "/static/../recommend.py")[0] == 404 and call(server, "GET", "/static/webapp.py")[0] == 404
    status, d = call(server, "GET", "/api/app", host="attacker.example:80")
    assert status == 403 and d["error"]
    assert call(server, "GET", "/api/app", host=f"localhost:{server.server_port}")[0] == 200
    (tmp_path / "index.html").write_text("<p>한</p>", encoding="utf-8"); (tmp_path / "app.css").write_text("a{}"); (tmp_path / "mock.js").write_text("fixtures")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG"); (tmp_path / "sub").mkdir(); (tmp_path / ".app.js.swp").write_text("x")
    assert webapp.web_files(tmp_path) == {"app.css": "a{}", "index.html": "<p>한</p>"}
    assert webapp.web_files(tmp_path / "missing") == {}


def test_other_sites_pages_cannot_drive_the_api(server, monkeypatch):
    """a page of another site can send 'simple' requests to 127.0.0.1 without a preflight: they are refused"""
    me = f"http://127.0.0.1:{server.server_port}"
    assert call(server, "POST", "/api/labs", {"raw": {}}, headers={"Origin": me, "Sec-Fetch-Site": "same-origin"})[0] == 200
    status, d = call(server, "POST", "/api/labs", json.dumps({"raw": {}}), headers={"Content-Type": "text/plain"})
    assert status == 415 and d["error"]
    for h in ({"Origin": "https://attacker.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
        assert call(server, "POST", "/api/analyze", {"conditions": ["cirrhosis"]}, headers=h)[0] == 403, h
        assert call(server, "GET", "/api/suggest?q=cirr", headers=h)[0] == 403, h
    monkeypatch.setattr(webapp, "_page", lambda: {"index.html": "<p>ADCTOX</p>"})
    assert call(server, "GET", "/", headers={"Sec-Fetch-Site": "cross-site"})[0] == 200                  # a link to the page itself still opens it


def test_malformed_requests_get_a_one_line_answer(server, capsys):
    for length in ("abc", "-5"):
        status, h, data = request(server, "POST", "/api/labs", b"{}", {"Content-Length": length})
        assert status == 400 and json.loads(data)["error"], length
    status, h, data = request(server, "HEAD", "/")
    assert (status, h["Allow"], data) == (405, "GET, POST", b"") and h["Server"] == "ADCTOX"
    for method in ("OPTIONS", "PUT", "DELETE"):
        status, h, data = request(server, method, "/api/app")
        assert status == 405 and json.loads(data) == {"error": "method not allowed"}, method
    assert request(server, "OPTIONS", "/api/app", headers={"Host": "attacker.example"})[0] == 403             # the host gate comes first
    try: raise BrokenPipeError(32, "Broken pipe")                                                      # the tab closed mid-answer: nothing
    except BrokenPipeError: server.handle_error(None, ("127.0.0.1", 1))
    try: raise ValueError("bad value\nsecond line")
    except ValueError: server.handle_error(None, ("127.0.0.1", 1))
    assert capsys.readouterr().err == "adctox --web: ValueError: bad value\n"


def test_ctrl_c_during_an_analysis_lets_it_finish_and_exits_cleanly(tmp_path):
    code = ("import sys, time; sys.path.insert(0, sys.argv[1]); import recommend as RC, webapp, suggest as SG\n"
            "SG.Index.load_mondo = lambda self: None\n"
            "def slow(conds, progress=None): progress('judging'); time.sleep(1.5); print('analysis finished', flush=True); return []\n"
            "RC.analyze_conditions = slow\n"
            "webapp.serve(RC, open_browser=False, ready=lambda s: print('port', s.server_port, flush=True))\n"
            "print('serve returned', flush=True)\n")
    p = subprocess.Popen([sys.executable, "-I", "-c", code, str(ROOT / "ml")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                         env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CUDA_VISIBLE_DEVICES": ""})
    try:
        port = next(int(ln.split()[1]) for ln in p.stdout if ln.startswith("port "))
        server = types.SimpleNamespace(server_port=port)
        jid = call(server, "POST", "/api/analyze", {"conditions": ["cirrhosis"]})[1]["job"]
        for _ in range(200):
            if call(server, "GET", f"/api/analyze/{jid}")[1]["state"] == "running": break
            time.sleep(0.02)
        p.send_signal(signal.SIGINT)
        out, err = p.communicate(timeout=60)
    finally:
        if p.poll() is None: p.kill()
    assert p.returncode == 0 and "analysis finished" in out and "serve returned" in out, (p.returncode, out, err[-800:])
    assert "분석을 마치는 중" in err and "Traceback" not in err


def test_the_one_file_build_serves_the_page_from_memory(tmp_path):
    out = tmp_path / "adc_recommender.py"
    build = subprocess.run([sys.executable, "-I", str(ROOT / "ml/build_portable.py"), str(out)], capture_output=True, text=True)
    assert build.returncode == 0, build.stderr[-1500:]
    assert "page: " in build.stdout and "index.html" in build.stdout
    code = ("import runpy, sys, http.client, threading; runpy.run_path(sys.argv[1], run_name='app')\n"
            "import recommend as RC, webapp; from __adc_data__ import _portable_data\n"
            "web = _portable_data()['web']; assert {'index.html', 'app.css', 'app.js'} <= set(web) and 'mock.js' not in web, sorted(web)\n"
            "assert web == webapp.web_files(sys.argv[2]) and webapp._page() is web\n"
            "s = webapp.make_server(RC); assert s.server_address[0] == '127.0.0.1'; threading.Thread(target=s.serve_forever, daemon=True).start()\n"
            "c = http.client.HTTPConnection('127.0.0.1', s.server_port); c.request('GET', '/'); r = c.getresponse()\n"
            "got = (r.status, r.getheader('Content-Type'), r.read().decode()); assert got == (200, 'text/html; charset=utf-8', web['index.html']), got[:2]\n"
            "c.request('GET', '/static/mock.js'); r = c.getresponse(); r.read(); assert r.status == 404\n"
            "c.request('GET', '/api/app'); r = c.getresponse(); assert r.status == 200 and len(__import__('json').loads(r.read())['registry']) == 41\n")
    run = subprocess.run([sys.executable, "-I", "-c", code, str(out), str(ROOT / "ml/web")], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CUDA_VISIBLE_DEVICES": ""}, cwd=tmp_path)
    assert run.returncode == 0, run.stderr[-1500:]


def test_help_names_the_web_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["adctox", "--help"])
    RC.main(); out = capsys.readouterr().out
    assert "adctox --web" in out and "ADCTOX_NO_BROWSER=1" in out


def test_web_flag_starts_the_server_without_a_terminal(monkeypatch, capsys):
    served = []
    monkeypatch.setattr(sys, "argv", ["adctox", "--web"]); monkeypatch.setattr(RC, "cap_threads", lambda: None)
    monkeypatch.setattr(RC, "preload", lambda: served.append("preload")); monkeypatch.setattr(webapp, "serve", lambda rc: served.append(rc))
    RC.main()
    assert served == ["preload", RC]


def test_adctox_web_launcher_is_written_beside_adctox(tmp_path, monkeypatch):
    import shutil, adc_updates as AU
    launcher = tmp_path / "adctox"; launcher.write_text('#!/usr/bin/env bash\nset -e\nexec /x/python -I /x/current/adc_recommender_full.py "$@"\n'); launcher.chmod(0o755)
    monkeypatch.setattr(AU, "pointer_mode", lambda: False); monkeypatch.setattr(shutil, "which", lambda name: str(launcher) if name == "adctox" else None)
    web = AU.ensure_web_launcher()
    assert web == tmp_path / "adctox-web" and web.read_text().endswith('adc_recommender_full.py --web "$@"\n') and web.stat().st_mode & 0o111
    web.write_text("mine"); assert AU.ensure_web_launcher() == web and web.read_text() == "mine"        # never overwritten
    cmd = tmp_path / "adctox.cmd"; cmd.write_text('@echo off\r\ncall "C:\\ADCTOX\\ADCTOX.bat" %*')
    monkeypatch.setattr(AU, "pointer_mode", lambda: True); monkeypatch.setattr(shutil, "which", lambda name: str(cmd) if name == "adctox.cmd" else None)
    assert AU.ensure_web_launcher() == tmp_path / "adctox-web.cmd" and (tmp_path / "adctox-web.cmd").read_text().endswith('ADCTOX.bat" --web %*')
    other = tmp_path / "bin"; other.mkdir(); (other / "adctox").write_text("#!/bin/sh\necho not ours \"$@\"\n")
    monkeypatch.setattr(AU, "pointer_mode", lambda: False); monkeypatch.setattr(shutil, "which", lambda name: str(other / "adctox"))
    assert AU.ensure_web_launcher() is None and not (other / "adctox-web").exists()
