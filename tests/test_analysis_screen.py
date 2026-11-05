"""The AI 장기 분석 step: the line says what the model reports it is doing, the table follows the highlighted input, and a failed
organ judge is never shown as used."""
import sys, pathlib, types
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import term, tui


def _screen(monkeypatch, keys, size=(24, 80)):
    import form
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True); monkeypatch.setattr(term._Screen, "_size", lambda self: size)
    screen = term._Screen(console); frames = []
    it = iter([getattr(console, k) if k.startswith("KEY_") else k for k in keys])
    screen.refresh = lambda: frames.append(["".join(ch for ch, _ in line) for line in screen.buf])
    screen.get_wch = lambda: next(it)
    return screen, frames


def _rc():
    import recommend as RC
    return types.SimpleNamespace(_reg={}, CHOICE={}, AXES=list(tui.GLYPH), condition_name=lambda c: c,
                                 _indications=lambda: {})


def _report(i, **kw):
    return dict(condition=f"condition number {i}", source="MONDO", name=f"disease {i}", mondo=f"MONDO:{i}", organs=["hepatic"],
                judge_via="record", **kw)


def _review(monkeypatch, reports, keys, size=(24, 80)):
    import form, suggest as SG
    monkeypatch.setattr(SG, "index", lambda RC: types.SimpleNamespace(ko={}))
    screen, frames = _screen(monkeypatch, keys, size)
    F = form.Form(screen, _rc()); F.step = 2
    assert F._analysis_review(reports, 1.0) is None
    return frames


def test_the_table_follows_the_highlighted_input_at_80x24(monkeypatch):
    reports = [_report(i) for i in range(30)]
    frames = _review(monkeypatch, reports, ["KEY_DOWN"] * 29 + ["KEY_NPAGE"])
    last = frames[-1]
    assert any(ln.lstrip().startswith("› condition number 29") for ln in last)          # the last input, highlighted, in view
    assert any("Input" in ln and "Organs" in ln and "Read as" in ln for ln in last)      # the header stays
    assert all(len(ln) <= 80 for ln in last) and len(last) == 24
    assert not any("BioLORD" in ln or "Organ judge" in ln or "MLP" in ln for f in frames for ln in f)
    up = _review(monkeypatch, reports, ["KEY_DOWN"] * 29 + ["KEY_UP"] * 29 + ["KEY_NPAGE"])[-1]
    assert any(ln.lstrip().startswith("› condition number 0") for ln in up)


def test_a_failed_organ_judge_is_named(monkeypatch):
    reports = [dict(_report(i, fallback="RuntimeError: weights missing"), source="Unmapped", organs=[], judge_via=None) for i in (1, 2)]
    first = "\n".join(_review(monkeypatch, reports, ["KEY_NPAGE"])[0])
    assert "Organ judge 오류: RuntimeError: weights missing" in first and "linker" not in first
    ok = "\n".join(_review(monkeypatch, [_report(1)], ["KEY_NPAGE"])[0])
    assert "오류" not in ok and "linker" not in ok and "MONDO (record)" in ok


def _fake_models(monkeypatch, judge):
    """the analysis pipeline with a stand-in organ judge."""
    import recommend as RC, scratch_runtime as SR
    monkeypatch.setattr(SR, "available", lambda: True); monkeypatch.setattr(SR, "judge", judge)
    monkeypatch.setattr(RC, "english", lambda texts: list(texts))
    RC._FREE.clear(); RC._ANALYSES.clear()
    return RC


def test_judge_failure_reads_nothing_and_says_why(monkeypatch):
    def broken(texts): raise RuntimeError("weights missing")
    RC = _fake_models(monkeypatch, broken)
    events = []
    try:
        (r,) = RC.analyze_conditions(["pulmonary tb"], progress=events.append)
        assert events == ["judging", "done"]                                          # the events that happened, in order
        assert r["source"] == "Unmapped" and r["organs"] == [] and r["judge_via"] is None
        assert r["fallback"] == "RuntimeError: weights missing"
    finally: RC._FREE.clear(); RC._ANALYSES.clear()


def test_a_working_judge_leaves_no_fallback_mark(monkeypatch):
    RC = _fake_models(monkeypatch, lambda texts: [dict(concept="MONDO:0018076", name="tuberculosis", organs=["pulmonary"], via="record",
                                                         valid=0.99, ok=True, sim=0.97) for _ in texts])
    events = []
    try:
        (r,) = RC.analyze_conditions(["pulmonary tb"], progress=events.append)
        assert events == ["judging", "done"] and r["fallback"] is None and r["judge_via"] == "record"
        events.clear(); RC.analyze_conditions(["pulmonary tb"], progress=events.append)
        assert events == ["done"]                                                      # cached: no step is shown as running
    finally: RC._FREE.clear(); RC._ANALYSES.clear()


def test_step_text_names_no_model():
    import form
    assert set(form.STEP_TEXT.values()) == {"장기 분석 중"}
    assert not hasattr(form, "STAGES_SCRATCH") and not hasattr(form, "pipeline")


def test_wrapped_rows_scroll_whole(monkeypatch):
    """at 80 columns a long reading wraps; scrolling shows whole inputs, never a wrapped tail under the header."""
    reports = [dict(_report(i), name=f"a rather long disease name number {i} that wraps") for i in range(12)]
    for k in range(12):
        last = _review(monkeypatch, reports, ["KEY_DOWN"] * k + ["KEY_NPAGE"])[-1]
        head = next(i for i, ln in enumerate(last) if "Read as" in ln)
        body = [ln for ln in last[head + 2:] if ln.strip()][:1]
        assert body and body[0].lstrip(" ›").startswith("condition number"), (k, body)
        assert any(ln.lstrip().startswith(f"› condition number {k}") for ln in last)


def test_priority_is_one_pick_that_stays_above_the_key_hint(monkeypatch):
    """the priority step asks for the one condition to weigh first; nine conditions at 80x24 scroll with the selection."""
    import form
    names = [f"condition number {i}" for i in range(9)]
    screen, frames = _screen(monkeypatch, ["KEY_DOWN"] * 9 + ["KEY_NPAGE"])
    F = form.Form(screen, _rc()); F.step = 3
    assert F.first(names, [["hepatic"]] * 9) == 9
    assert "가장 걱정되는 질환" in "\n".join(frames[0]) and "(●) Auto" in "\n".join(frames[0])
    for f in frames:
        assert "PgDn 다음" in f[-1] and "↑↓ 고르기" in f[-1] and not any("condition number" in ln for ln in f[-2:])
    assert any("(●) condition number 8" in ln for ln in frames[-1])
    text = "\n".join("\n".join(f) for f in frames)
    assert "먼저 피함" not in text and "[ − ]" not in text

def test_result_table_header_stays_while_rows_scroll(monkeypatch):
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(term, "USE_SHIM", True)
    monkeypatch.setattr(term._Screen, "_size", lambda self: (24, 80))
    screen = term._Screen(console); frames = []
    keys = iter([console.KEY_DOWN] * 13 + [console.KEY_NPAGE])
    screen.refresh = lambda: frames.append(["".join(ch for ch, _ in line) for line in screen.buf])
    screen.getch = lambda: next(keys)
    monkeypatch.setattr(console, "wrapper", lambda app: app(screen))
    table = ["  #   ADC   Label restriction", "  " + "─" * 70] + [f"  {i + 1}   ADC number {i}" for i in range(14)]
    assert tui.browse("t", table, list(range(2, 16)), [["reason"]] * 14, context=["Key values"]) == "next"
    for f in frames: assert any("Label restriction" in ln for ln in f)
    assert any("ADC number 13" in ln for ln in frames[-1]) and not any("ADC number 0" in ln for ln in frames[-1])


def test_an_analysis_that_cannot_go_on_shows_one_error_line(monkeypatch):
    import form
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True); monkeypatch.setattr(term._Screen, "_size", lambda self: (24, 80))
    screen = term._Screen(console); frames = []
    screen.refresh = lambda: frames.append(["".join(ch for ch, _ in line) for line in screen.buf])
    screen.get_wch = lambda: console.KEY_NPAGE                    # PgDn leaves the error screen
    def broken(conditions, progress=None):
        raise ValueError("This file contains pickled (object) data.\nsecond line of the message")
    RC = types.SimpleNamespace(**vars(_rc()), analyze_conditions=broken)
    F = form.Form(screen, RC); F.step = 2
    assert F.analyze(["pulmonary tb"]) == form.BACK
    shown = frames[-1]
    assert any("AI 분석을 완료하지 못했습니다" in ln for ln in shown)
    assert sum("ValueError" in ln for ln in shown) == 1 and not any("second line" in ln for ln in shown)
    assert not any("장기 분석 중" in ln for f in frames for ln in f)          # the judge step never started


def test_the_picked_condition_comes_first_and_the_rest_keep_their_order(monkeypatch):
    import builtins, recommend as RC
    pc = [("cirrhosis", {"hepatic"}, 1.0), ("heart_failure", {"cardiovascular"}, 1.0), ("glaucoma", {"ocular"}, 0.5), ("Lab: Hb < 10 g/dL", {"haematologic"}, 0.5)]
    monkeypatch.setattr(RC, "PRIORITY", {}); monkeypatch.setattr(RC, "FIRST", None); monkeypatch.setattr(builtins, "input", lambda prompt: "3")
    RC._ask_priority_pc(pc)
    assert RC.FIRST == "glaucoma" and RC.priority(pc) == {"glaucoma": 1, "cirrhosis": 2, "heart_failure": 2, "Lab: Hb < 10 g/dL": 3}
    monkeypatch.setattr(builtins, "input", lambda prompt: "4")                  # lab findings are not offered: 4 is out of range
    RC._ask_priority_pc(pc)
    assert RC.FIRST is None and RC.PRIORITY == {}
    monkeypatch.setattr(builtins, "input", lambda prompt: "")
    RC._ask_priority_pc(pc)
    assert RC.PRIORITY == {} and RC.priority(pc) == RC.default_levels(pc)


def test_the_analysis_shows_the_three_likeliest_organs_with_their_probability(monkeypatch):
    import form
    p = {a: 0.0 for a in tui.GLYPH}; p.update(neurologic=0.951, cardiovascular=0.68, metabolic_endocrine=0.22)
    plain = lambda t: __import__("re").sub(r"\x1b\[[\d;]*m", "", t)
    assert plain(form.likely(list(tui.GLYPH), ["neurologic"], p)) == "Neuro     ━━━━━  Cardio    ━━━──  Metabolic ━────"   # names padded: the bars line up
    assert "\033[32;1mNeuro" in form.likely(list(tui.GLYPH), ["neurologic"], p) and "\033[90mCardio" in form.likely(list(tui.GLYPH), ["neurologic"], p)
    assert plain(form.likely(list(tui.GLYPH), ["neurologic", "ocular"], p)).endswith("Eye       ━────")        # a used organ outside the three follows
    assert plain(form.likely(list(tui.GLYPH), ["hepatic"], None)) == "Liver"                           # no judge output: the used organs
    frames = _review(monkeypatch, [dict(_report(1), organs=["neurologic"], p=p)], ["KEY_NPAGE"])
    text = "\n".join(frames[0])
    assert "Neuro     ━━━━━  Cardio    ━━━──  Metabolic ━────" in text and "95%" not in text and "순위에 쓰는" not in text and all(len(ln) <= 80 for ln in frames[0])


def test_a_registry_disease_gets_an_analysis_row(monkeypatch):
    import recommend as RC, scratch_runtime as SR
    rid = next(iter(RC._reg)); label = RC._reg[rid]["label"]
    p = {a: 0.5 for a in RC.AXES}
    monkeypatch.setattr(SR, "available", lambda: True)
    monkeypatch.setattr(SR, "judge", lambda texts: [dict(p=p) for _ in texts])
    RC._ANALYSES.clear(); RC._REG_P.clear(); events = []
    try:
        (r,) = RC.analyze_conditions([rid], progress=events.append)
        assert r["source"] == "Registry" and r["name"] == label and r["p"] == p and r["organs"]
        assert events == ["judging", "done"]
    finally: RC._ANALYSES.clear(); RC._REG_P.clear()


def test_no_middle_dot_in_the_app_text():
    root = pathlib.Path(__file__).resolve().parents[1] / "ml"
    for name in ("form.py", "tui.py", "recommend.py", "restrictions.py", "labs.py", "term.py", "webapp.py", "web/index.html", "web/app.css", "web/app.js", "web/mock.js"):
        assert "·" not in (root / name).read_text(encoding="utf-8"), name


def test_the_app_runs_torch_on_at_most_four_threads(monkeypatch):
    import recommend as RC
    monkeypatch.setattr(RC.os, "cpu_count", lambda: 48)
    env = {}; RC.cap_threads(env); assert env == {"OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"}
    monkeypatch.setattr(RC.os, "cpu_count", lambda: 2)
    env = {}; RC.cap_threads(env); assert env["OMP_NUM_THREADS"] == "2"
    env = {"OMP_NUM_THREADS": "16"}; RC.cap_threads(env); assert env["OMP_NUM_THREADS"] == "16"        # the user's own setting stays
    env = {"ADCTOX_THREADS": "8"}; RC.cap_threads(env); assert env["MKL_NUM_THREADS"] == "8"
