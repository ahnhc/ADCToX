"""The AI 장기 분석 step: the line says what the model reports it is doing, the table follows the highlighted input, and a failed
organ judge is never shown as used."""
import sys, pathlib, types
import numpy as np
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
    return types.SimpleNamespace(_reg={}, CHOICE={}, AXES=list(tui.GLYPH), condition_name=lambda c: c, FIRST_TEXT=RC.FIRST_TEXT,
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


def test_a_failed_organ_judge_is_named_and_its_rows_read_as_linker(monkeypatch):
    reports = [_report(1, fallback="RuntimeError: weights missing"), dict(_report(2, fallback="RuntimeError: weights missing"), source="Unmapped", organs=[], judge_via=None)]
    reports[0]["judge_via"] = None
    first = "\n".join(_review(monkeypatch, reports, ["KEY_NPAGE"])[0])
    assert "Organ judge 오류 · MONDO linker로 대체" in first and "MONDO · linker" in first
    ok = "\n".join(_review(monkeypatch, [_report(1)], ["KEY_NPAGE"])[0])
    assert "오류" not in ok and "linker" not in ok and "MONDO · record" in ok


def _fake_models(monkeypatch, judge):
    """the analysis pipeline with stand-ins for the encoders, the older linker and the organ judge."""
    import recommend as RC, scratch_runtime as SR
    vm = types.ModuleType("vulnerability_model"); vm._st = lambda texts: np.zeros((len(texts), 4), np.float32)     # no registry name is near
    mi = types.ModuleType("mondo_index")
    mi.link = lambda texts: [dict(mondo="MONDO:0018076", name="tuberculosis", sim=0.9, axes=["pulmonary"], readings=[], ambiguous=False) for _ in texts]
    monkeypatch.setitem(sys.modules, "vulnerability_model", vm); monkeypatch.setitem(sys.modules, "mondo_index", mi)
    monkeypatch.setattr(SR, "available", lambda: True); monkeypatch.setattr(SR, "judge", judge)
    monkeypatch.setattr(RC, "HAS_LEARNED", False); monkeypatch.setattr(RC, "LEARNED_FRACTION", 0.0); monkeypatch.setattr(RC, "FALLBACK", {})
    monkeypatch.setattr(RC, "english", lambda texts: list(texts))
    RC._FREE.clear(); RC._ANALYSES.clear()
    return RC


def test_judge_failure_falls_back_to_the_linker_and_says_so(monkeypatch):
    def broken(texts): raise RuntimeError("weights missing")
    RC = _fake_models(monkeypatch, broken)
    events = []
    try:
        (r,) = RC.analyze_conditions(["pulmonary tb"], progress=events.append)
        assert events == ["embedding", "judging", "linking", "done"]                  # the events that happened, in order
        assert r["source"] == "MONDO" and r["organs"] == ["pulmonary"] and r["judge_via"] is None
        assert r["fallback"] == "RuntimeError: weights missing"
    finally: RC._FREE.clear(); RC._ANALYSES.clear()


def test_a_working_judge_leaves_no_fallback_mark(monkeypatch):
    RC = _fake_models(monkeypatch, lambda texts: [dict(concept="MONDO:0018076", name="tuberculosis", organs=["pulmonary"], via="record",
                                                         valid=0.99, ok=True, sim=0.97) for _ in texts])
    events = []
    try:
        (r,) = RC.analyze_conditions(["pulmonary tb"], progress=events.append)
        assert events == ["embedding", "judging", "done"] and r["fallback"] is None and r["judge_via"] == "record"
        events.clear(); RC.analyze_conditions(["pulmonary tb"], progress=events.append)
        assert events == ["done"]                                                      # cached: no step is shown as running
    finally: RC._FREE.clear(); RC._ANALYSES.clear()


def test_the_mlp_step_shows_only_when_the_mlp_runs(monkeypatch):
    import recommend as RC
    monkeypatch.setattr(RC, "english", lambda texts: list(texts))
    monkeypatch.setitem(RC._FREE_PREDICTIONS, "pulmonary tb", {"pulmonary": 0.9})
    events = []
    assert RC._predict_free(["pulmonary tb"], events.append) == [{"pulmonary": 0.9}] and events == []


def test_step_text_names_no_model():
    import form
    assert set(form.STEP_TEXT.values()) == {"질환 확인 중", "장기 분석 중"}
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
    assert "가장 걱정되는 질환" in "\n".join(frames[0]) and "(●) 자동 (질환 중증도 순)" in "\n".join(frames[0])
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
        progress("embedding"); raise ValueError("This file contains pickled (object) data.\nsecond line of the message")
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
