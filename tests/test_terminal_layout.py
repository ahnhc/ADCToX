"""Keep terminal selection, warning colours and evidence readable across renderers and sizes."""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import term
import tui


def plain(text):
    return re.sub(r"\x1b\[[\d;]*m", "", text)


@pytest.mark.parametrize("width", [8, 35, 55, 75, 115])
def test_coloured_hangul_wrap_preserves_text_and_fits(width):
    text = "\x1b[33;1m자료 불충분 (cardiac)\x1b[0m  \x1b[36mMonitor (renal)\x1b[0m"
    lines = tui._wrap_ansi(text, width)
    assert "".join(map(plain, lines)) == plain(text)
    assert all(sum(tui._cw(c) for c in plain(line)) <= width for line in lines)


def test_selected_status_keeps_its_foreground_and_uses_a_neutral_background():
    console = term._Shim()
    console.init_pair(3, console.COLOR_RED, -1)
    sgr = console._sgr(console.color_pair(3) | console.A_REVERSE)
    assert "38;2;237;150;144" in sgr
    assert "48;2;44;46;38" in sgr
    assert ";7m" not in sgr


@pytest.mark.parametrize("shim", [False, True])
def test_selected_row_has_explicit_background_without_reversing_warning_colours(monkeypatch, shim):
    console = term._Shim()
    console.COLORS = 256
    monkeypatch.setattr(tui, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", shim)
    screen = term._Screen(console)
    painter = tui._Screen(screen)
    painter.row(5, "ADC  \x1b[31mAvoid\x1b[0m", selected=True)
    name_attr = screen.buf[5][2][1]
    warning_attr = screen.buf[5][7][1]
    assert not warning_attr & console.A_REVERSE
    assert console._pairs[(name_attr >> 8) & 0xFF] == (console.COLOR_WHITE, 236)
    assert console._pairs[(warning_attr >> 8) & 0xFF] == (console.COLOR_RED, 236)


def test_result_navigation_survives_resize_and_reaches_every_candidate(monkeypatch):
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True)
    size = [38, 120]
    monkeypatch.setattr(term._Screen, "_size", lambda self: tuple(size))
    screen = term._Screen(console)
    frames, selected = [], []
    keys = iter([console.KEY_DOWN, console.KEY_DOWN, console.KEY_DOWN, console.KEY_UP, console.KEY_PPAGE])

    def refresh():
        frames.append(["".join(ch for ch, _ in line) for line in screen.buf])

    def getch():
        key = next(keys)
        if len(frames) == 2: size[:] = [30, 65]
        return key

    screen.refresh = refresh
    screen.getch = getch
    monkeypatch.setattr(console, "wrapper", lambda app: app(screen))

    def listing(width):
        return ["ADC", "Candidate A", "Candidate B", "Candidate C"], [1, 2, 3]

    def detail(index, width):
        selected.append(index)
        return [f"Candidate {'ABC'[index]}", "\x1b[33mUnclear\x1b[0m: LVEF < 50%"]

    assert tui.browse("ADC 추천 결과", listing, [], detail, context=["환자: 심부전"]) == "back"
    assert selected == [0, 1, 2, 2, 1]
    assert len(screen.buf) == 30 and len(screen.buf[0]) == 65
    assert all("ADCTOX" in "\n".join(frame) and "LVEF < 50%" in "\n".join(frame) for frame in frames)


@pytest.mark.skipif(not pathlib.Path("/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07").exists(), reason="DailyMed snapshot absent")
def test_real_result_list_fits_and_keeps_warning_evidence():
    import recommend
    rows, _, _, checks = recommend.recommend(["ckd_stage_3", "heart_failure"], labs={"crcl": 45, "lvef": 48})
    for width in (35, 55, 64, 75, 95, 96, 97, 98, 100, 115):
        lines, at = recommend._result_list(rows, width)
        assert len(at) == len(rows)
        assert all(recommend._width(plain(line)) <= width for line in lines)
        for i, row in enumerate(rows):
            shown = " ".join("".join(plain(line) for line in lines[at[i]:at[i + 1] if i + 1 < len(at) else len(lines)]).split())
            for organ in recommend._organ_preview(row):
                assert plain(organ) in shown
            detail = "\n".join(map(plain, recommend._result_details(row, checks, width)))
            wrapped = [line for text in recommend._result_details(row, checks, width) for line in tui._wrap_ansi(text, width)]
            assert all(recommend._width(plain(line)) <= width for line in wrapped)
            assert "박스경고" not in detail and "🚨" not in detail and "?" not in detail
            assert "Label v" not in detail and "more restriction reasons" not in detail
            for test, names, _ in checks:
                if (not names or row["name"] in names) and not test.startswith("enter "):
                    assert test in detail
            if row["name"] == "Trastuzumab deruxtecan":
                assert "Not studied" in detail and "LVEF < 50%" in detail


def test_organ_preview_uses_patient_warnings_and_excludes_patient_organs_from_other():
    import recommend as R
    row = {"priority": [(1, "heart_failure", ["cardiovascular"]),
                        (2, "ckd_stage_3", ["renal"]), (2, "cirrhosis", ["hepatic"])],
           "boxed": ["hepatic"], "warn": ["cardiovascular", "renal"],
           "organs": {a: {"level": "none"} for a in R.AXES}}
    for organ in row["boxed"]: row["organs"][organ]["level"] = "boxed"
    for organ in row["warn"]: row["organs"][organ]["level"] = "W&P"
    row["organs"]["pulmonary"]["level"] = "boxed"
    row["organs"]["haematologic"]["level"] = "W&P"
    preview = list(map(plain, R._organ_preview(row)))
    assert preview == ["!! Liver", " ! Cardio+", "!! Lung+"]
    row["boxed"].clear()
    row["warn"].clear()
    for organ in R.AXES: row["organs"][organ]["level"] = "none"
    # Missing warning evidence is left blank rather than presented as a risk score or a safe organ.
    assert list(map(plain, R._organ_preview(row))) == ["-", "-", "-"]


@pytest.mark.parametrize("width", [35, 65, 75, 96, 115])
def test_header_bounds_values_and_priorities_without_repeating_diagnoses(width):
    import recommend as R
    rows = [{"priority": [(1, "heart_failure", ["cardiovascular"]), (2, "ckd_stage_3", ["renal"])],
             "verdict": R.RS.Verdict("sample", [], [], [], [])}]
    notes = [("ckd_stage_3", "registry"), ("heart_failure", "registry"),
             ("a long patient condition that needs wrapping across the available column width", "not understood")]
    values = {"crcl": 45.6, "lvef": 48, "bili": 1.2, "ast": 2, "alt": 3, "anc": 1.5, "platelets": 70}
    lines = list(map(plain, R._result_context(rows, notes, width, values)))
    assert all(R._width(line) <= width and "·" not in line for line in lines)
    assert len(lines) <= (6 if width >= 72 else 12)
    text = "\n".join(lines)
    for label in ("Key values", "Organ priority", "1. Cardio", "2. Kidney", "+ 4 more", "Unmapped:"):
        assert "".join(label.split()) in "".join(text.split())
    assert "심부전" not in text and "만성 콩팥병" not in text
    assert "Heart failure" not in text and "Chronic kidney disease" not in text
    assert any("│" in line for line in lines) == (width >= 72)


def test_selected_drug_values_come_first_and_egfr_approximation_remains_visible():
    import recommend as R
    row = {"priority": [], "verdict": R.RS.Verdict("sample", [
        ("insufficient_data", {"domain": "cardiac", "when": {"lvef_lt": 50}}),
        ("monitor", {"domain": "renal", "when": {"crcl_lt": 60}})], [], [], [])}
    notes = [("Lab", "CLcr ≈ eGFR 45 (approximation)")]
    lines = list(map(plain, R._result_context([row], notes, 115, {"crcl": 45, "bili": 2, "ast": 2, "alt": 2, "lvef": 48})))
    assert "LVEF 48%" in lines[1]
    assert "CLcr ≈ 45 mL/min (eGFR)" in "\n".join(lines)


@pytest.mark.parametrize("category, state", [("no_adjustment", "None"), ("monitor", "Monitor"),
    ("reduce_dose", "Monitor"), ("insufficient_data", "Not studied"), ("no_statement", "No data"),
    ("avoid", "Avoid"), ("contraindicated", "Avoid")])
def test_restriction_column_is_one_word_with_exact_action_in_the_details(category, state):
    import recommend as R
    row = {"name": "Sample ADC", "rank": 1, "priority": [], "boxed": [], "warn": [], "version": 1, "date": "2026-01-01",
           "organs": {a: {"level": "none"} for a in R.AXES},
           "verdict": R.RS.Verdict("sample", [(category, {"domain": "renal", "when": {"crcl_lt": 30}})], [], [], [])}
    lines, starts = R._result_list([row], 115)
    assert plain(lines[starts[0]]).split() == ["1", "Sample", "ADC", *state.split(), "-", "-", "-"]
    assert R.RS.TABLE[category] in "\n".join(map(plain, R._result_details(row, [], 115)))


def test_condition_names_are_shortened_only_for_display_and_priorities_group_ties():
    import recommend as R
    assert R.condition_name("reduced_lvef") == "Reduced ejection fraction"
    assert R.KO["reduced_lvef"] == "좌심실 박출률 저하"
    assert "LVEF < 50%" in R._reg["reduced_lvef"]["label"]
    assert R.priority_lines([("heart_failure", {"cardiovascular"}, 1.0),
                             ("interstitial_lung_disease", {"pulmonary"}, 1.0),
                             ("ckd_stage_3", {"renal"}, 0.7)]) == [
        "  1. Heart failure, Interstitial lung disease", "  2. Chronic kidney disease stage 3"]


@pytest.mark.parametrize("columns", [40, 70, 100, 120])
def test_final_output_fits_terminal_and_preserves_dose_actions_and_check_names(monkeypatch, capsys, columns):
    import json
    import os
    import shutil
    import recommend as R
    evidence = json.loads((pathlib.Path(__file__).resolve().parents[1] / "ml/data/label_evidence.json").read_text())["evidence"]
    monkeypatch.setattr(R.DE, "evidence", lambda: evidence)
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback: os.terminal_size((columns, 36)))
    monkeypatch.setattr(R, "_ANALYSES", {})
    rows, s, notes, checks = R.recommend(["heart_failure", "interstitial_lung_disease", "ckd_stage_3"],
                                         raw={"lvef": 48, "egfr": 45, "child_pugh": "A"})
    R.render(rows, s, notes, checks, color=False, raw={"lvef": 48, "egfr": 45, "child_pugh": "A"})
    output = capsys.readouterr().out
    assert all(R._width(line) < columns for line in output.splitlines())
    assert "\x1b" not in output
    assert "Label actions" in output and R.RS.TABLE["reduce_dose"] in output
    assert "Pre-treatment checks" in output
    normalized = " ".join(output.split())
    assert "CLcr ≈ 45 mL/min (eGFR)" in normalized
    for row in rows:
        assert row["name"] in normalized
    for _, names, _ in checks:
        assert all(name in normalized for name in names)


def test_typed_disease_runs_trained_head_and_keeps_estimates_separate_from_mapped_organs(monkeypatch):
    import types
    import recommend as R
    calls = []
    def predict(texts):
        calls.append(list(texts))
        return [{"renal": 0.9, "pulmonary": 0.2} for _ in texts]
    monkeypatch.setitem(sys.modules, "vulnerability_model", types.SimpleNamespace(predict=predict))
    monkeypatch.setattr(R, "_FREE_PREDICTIONS", {})
    monkeypatch.setattr(R, "_ANALYSES", {})
    monkeypatch.setattr(R, "LEARNED_FRACTION", 0.0)
    monkeypatch.setattr(R, "FALLBACK", {})
    def linked(free, progress=None):
        return ([("copd", 0.4), ("copd", 0.1)],
                [{"name": "asthma", "sim": 1.0, "axes": ["pulmonary"]},
                 {"name": "disease", "sim": 0.1, "axes": []}], None)
    monkeypatch.setattr(R, "_free_info", linked)
    events = []
    reports = R.analyze_conditions(["asthma", "banana spaceship"], progress=events.append)
    assert calls == [["asthma", "banana spaceship"]]
    assert "inference" in events and events[-1] == "done"
    assert reports[0]["organs"] == ["pulmonary"] and reports[0]["estimates"][0] == ("renal", 0.9)
    assert reports[1]["source"] == "Unmapped" and reports[1]["organs"] == []
    assert R.LEARNED_FRACTION == 0.0 and R.FALLBACK == {}
    s = R.resolve(["asthma", "banana spaceship"])[0]
    assert s[R.AXES.index("renal")] == 0 and s[R.AXES.index("pulmonary")] > 0
    R.analyze_conditions(["asthma", "banana spaceship"])
    assert len(calls) == 1  # Reviewing or revisiting input reuses the real prediction instead of loading weights again.


def test_opt_in_model_fallback_applies_only_the_three_organs_shown_in_priority(monkeypatch):
    import recommend as R
    monkeypatch.setattr(R, "FALLBACK", {"unmapped condition": 0.25})
    monkeypatch.setattr(R, "LEARNED_FRACTION", 0.0)
    predictions = {a: (i + 1) / len(R.AXES) for i, a in enumerate(R.AXES)}
    monkeypatch.setattr(R, "_free_info", lambda free: (
        [("copd", 0.1)], [{"name": "disease", "sim": 0.1, "axes": []}], [predictions]))
    s, own_axes, ids, notes, pc = R.resolve(["unmapped condition"])
    applied = {a for a, value in zip(R.AXES, s) if value > 0}
    assert len(applied) == 3 and applied == pc[0][1]
    assert own_axes == set() and ids == set()  # An estimate never invents a confirmed diagnosis or organ-based label restriction.
    assert "not validated" in notes[0][1]


def test_detail_scroll_reaches_every_reason_and_check_without_changing_candidate(monkeypatch):
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True)
    size = [30, 90]
    monkeypatch.setattr(term._Screen, "_size", lambda self: tuple(size))
    screen = term._Screen(console)
    frames, selected = [], []
    keys = iter([9] + [console.KEY_DOWN] * 45 + [console.KEY_HOME, console.KEY_END,
                9, console.KEY_DOWN, console.KEY_NPAGE])
    screen.refresh = lambda: frames.append("\n".join("".join(ch for ch, _ in line) for line in screen.buf))
    def getch():
        if len(frames) == 12: size[:] = [26, 65]
        return next(keys)
    screen.getch = getch
    monkeypatch.setattr(console, "wrapper", lambda app: app(screen))
    def detail(index, width):
        selected.append(index)
        return [f"Candidate {index}"] + [f"Restriction reason {i:02}" for i in range(20)] + [
            "─" * width, "Missing inputs", "LVEF", "─" * width, "Pre-treatment checks",
            "First full check", "Last full check"]
    assert tui.browse("unused", ["ADC", "Candidate 0", "Candidate 1"], [1, 2], detail) == "next"
    for text in [f"Restriction reason {i:02}" for i in range(20)] + ["Missing inputs", "First full check", "Last full check"]:
        assert any(text in frame for frame in frames)
    assert selected[:-1] == [0] * (len(selected) - 1) and selected[-1] == 1
    assert "↑↓ 이유 스크롤" in frames[1]
    assert "Candidate 1" in frames[-1] and "Restriction reason 00" in frames[-1]
    assert all("ADCTOX" in frame and tui.UI_VERSION in frame for frame in frames)


def test_missing_inputs_are_separate_and_all_restriction_reasons_are_available(monkeypatch):
    import recommend as R
    evidence = [("renal", "Avoid", f"Reason {i}", "avoid", False) for i in range(7)]
    monkeypatch.setattr(R, "reason_rows", lambda row: list(evidence))
    verdict = R.RS.Verdict("sample", [], [], [], [R.RS.NEEDS["renal"]])
    row = {"name": "Sample ADC", "verdict": verdict}
    details = list(map(plain, R._result_details(row, [("A full check", ["Sample ADC"], None)], 75)))
    assert all(f"Reason {i}" in "\n".join(details) for i in range(7))
    missing_at = details.index("Missing inputs")
    assert details[missing_at - 1] == "─" * 75
    assert details[missing_at + 1] == "  CLcr / dialysis status"
    assert "A full check" in "\n".join(details)
    assert "?" not in "\n".join(details) and "Label v" not in "\n".join(details)


def test_automatic_fallback_uses_the_low_weight_and_opt_out_stays_available(monkeypatch):
    import recommend as R
    assert R.FALLBACK_OPTS == [("자동", 0.25), ("반영", 0.5), ("반영 안함", 0.0)]
    monkeypatch.setattr(R, "unresolved", lambda conditions: ["lung hole"])
    monkeypatch.setattr(R, "FALLBACK", {})
    R._ask_fallback(["lung hole"], radio=lambda *args, **kwargs: kwargs["default"])
    assert R.FALLBACK == {"lung hole": 0.25}
    R._ask_fallback(["lung hole"], radio=lambda *args, **kwargs: 2)
    assert R.FALLBACK == {}


def test_meaning_choice_is_one_screen_starts_on_the_applied_reading_and_returns_every_pick(monkeypatch):
    import types
    import form
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console)
    monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True)
    monkeypatch.setattr(term._Screen, "_size", lambda self: (40, 100))
    screen = term._Screen(console)
    frames = []
    keys = iter([console.KEY_DOWN, console.KEY_DOWN, "\n", "\n", console.KEY_NPAGE])
    screen.refresh = lambda: frames.append("\n".join("".join(ch for ch, _ in line) for line in screen.buf))
    screen.get_wch = lambda: next(keys)
    RC = types.SimpleNamespace(ORGAN_SHORT={"cardiovascular": "Cardio", "neurologic": "Neuro"}, AXES=list(form.GLYPH))
    groups = [("asd", [dict(mondo="M:1", name="atrial septal defect", organs=["cardiovascular"]),
                       dict(mondo="M:2", name="Alzheimer disease", organs=["neurologic"]),
                       dict(mondo="M:3", name="autism spectrum disorder", organs=["neurologic"])]),
              ("amnesia", [dict(mondo="M:4", name="dissociative amnesia", organs=[]),
                           dict(mondo="HP:0002354", name="Memory impairment", organs=["neurologic"])])]
    pick = form.Form(screen, RC).meanings(groups, {"amnesia": "HP:0002354"})
    # ENTER on autism moves to amnesia's current pick (the applied phenotype); ENTER there keeps it; PgDn finishes
    assert pick == {"asd": "M:3", "amnesia": "HP:0002354"}
    first = frames[0]
    assert "Atrial septal defect" in first and "13개 장기 밖" in first and "증상" in first and "모름" in first
    assert "●" in next(l for l in first.splitlines() if "Memory impairment" in l)
    assert all(len(line) <= 100 for frame in frames for line in frame.splitlines())


def test_every_model_is_shown_and_only_agreed_organs_are_applied_automatically(monkeypatch):
    import types
    import recommend as R
    zero = {a: 0.0 for a in R.AXES}
    by = {"main": {**zero, "pulmonary": 0.8, "hepatic": 0.4, "renal": 0.3},
          "combined": {**zero, "pulmonary": 0.9, "renal": 0.2, "ocular": 0.1},
          "previous": {**zero, "pulmonary": 0.7, "renal": 0.5, "otologic": 0.2}}
    def agreement(models):
        n = {}
        for s in models.values():
            for a, v in sorted(s.items(), key=lambda x: -x[1])[:3]:
                if v > 0: n[a] = n.get(a, 0) + 1
        return n
    VM = types.SimpleNamespace(predict_models=lambda texts: [by for _ in texts], agreement=agreement, _CK_OPT={"agree_min": 2})
    monkeypatch.setitem(sys.modules, "vulnerability_model", VM)
    for name in ("_FREE_PREDICTIONS", "_FREE_MODELS", "_ANALYSES"): monkeypatch.setattr(R, name, {})
    monkeypatch.setattr(R, "LEARNED_FRACTION", 0.0)
    monkeypatch.setattr(R, "FALLBACK", {})
    linked = lambda free, progress=None: ([("copd", 0.1)], [{"name": "disease", "sim": 0.1, "axes": []}],
                                         R._predict_free(free) if R.FALLBACK else None)
    monkeypatch.setattr(R, "_free_info", linked)
    report = R.analyze_conditions(["lung hole"])[0]
    assert report["models"] == ["Den", "Both", "Fin"]
    assert [a for a, _ in report["estimates"]] == ["pulmonary", "renal", "hepatic"]      # most agreed first
    assert report["agree"] == {"pulmonary": 3, "renal": 3, "hepatic": 1} and report["by_model"]["hepatic"] == [0.4, 0.0, 0.0]
    monkeypatch.setattr(R, "FALLBACK", {"lung hole": 0.25})
    s = R.resolve(["lung hole"])[0]
    applied = {a for a, v in zip(R.AXES, s) if v > 0}
    assert applied == {"pulmonary", "renal"}                                            # hepatic: one model only


def test_mouse_reports_become_clicks_and_wheel_scrolls():
    console = term._Shim(); screen = term._Screen(console)
    assert screen._escape("[<0;12;5M") == console.KEY_MOUSE and console.getmouse()[1:3] == (11, 4)
    assert screen._escape("[<0;12;5m") == -1                                         # the release is ignored
    assert screen._escape("[<64;1;1M") == console.KEY_UP and screen._escape("[<65;1;1M") == console.KEY_DOWN
    assert screen._escape("[A") == console.KEY_UP and screen._escape("[6~") == console.KEY_NPAGE


def test_a_click_presses_the_row_or_button_under_it(monkeypatch):
    import types, form
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console); monkeypatch.setattr(term, "USE_SHIM", True)
    monkeypatch.setattr(term._Screen, "_size", lambda self: (30, 100))
    screen = term._Screen(console); screen.refresh = lambda: None
    F = form.Form(screen, types.SimpleNamespace(HAS_LEARNED=False))
    F.frame("t", ""); F.row(10, "a row", False, 3)
    clicks = iter([("CLICK", 10, 40), ("CLICK", 2, 97 - 3), ("CLICK", 25, 5)])
    monkeypatch.setattr(form, "_key", lambda scr, tab=False: next(clicks))
    assert F.key() == ("ROW", 3) and F.key() == "NOOP" and F.key() == "NOOP"           # row; the top right has no buttons any more


def test_organ_strip_marks_linked_and_estimated_organs():
    import form
    s = form.strip(list(form.GLYPH), on=["hepatic"], maybe=["renal"])
    assert plain(s) == "Liver Kidney?" and "\x1b[32;1mLiver" in s and "\x1b[33mKidney?" in s
    assert plain(form.strip(list(form.GLYPH))) == "-"


def test_logo_lines_and_colours_line_up():
    import tui
    assert len(tui.logo()) == 5 and max(len(plain(l)) for l in tui.logo()) <= tui.logo_width()
    for chars, cols in tui.LOGO:
        assert len(chars) == len(cols) and all((c == " ") == (k == " ") for c, k in zip(chars, cols)) and set(cols) <= {" ", "c", "y", "r"}


def test_a_long_highlighted_name_scrolls_after_a_pause():
    import form
    t = "Familial juvenile hyperuricemic nephropathy type 1"
    assert form.marquee(t, 26, 0.5) == t and form.marquee("Asthma", 26, 9) == "Asthma"
    shown = {form._clip(form.marquee(t, 26, r / 10), 26) for r in range(0, 200)}
    assert any(x.endswith("type 1") for x in shown) and form._clip(t, 26) in shown


def test_only_page_keys_leave_a_screen(monkeypatch):
    import form
    F = form.Form.__new__(form.Form)
    keys = iter(["ENTER", "ESC", " ", "PGDN"])
    monkeypatch.setattr(F, "frame", lambda *a, **k: 2, raising=False)
    monkeypatch.setattr(F, "row", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(F, "key", lambda *a, **k: next(keys), raising=False)
    F.scr = type("S", (), {"getmaxyx": lambda self: (30, 100), "refresh": lambda self: None})()
    F.S = type("P", (), {"put": lambda *a, **k: None, "put_ansi": lambda *a, **k: None, "dim": 0})()
    assert F.choose("t", "", ["a", "b"]) == 0                   # Enter, Esc and Space stay; PgDn goes on


def test_gemma_panel_marks_the_step_that_set_the_organs():
    import types, form
    RC = types.SimpleNamespace(AXES=list(tui.GLYPH))
    g = dict(valid=0.999, vthr=0.995, ok=True, organ=[("neurologic", 0.9, 0.5), ("ocular", 0.1, 0.5)], near=("MONDO:0007739", "Huntington disease", 0.81),
             sym=("MONDO:0005154", 0.2))
    r = dict(condition="헌팅톤무도병", source="MONDO", name="Huntington disease", mondo="MONDO:0007739", organs=["neurologic"], gemma=g, via="judge vector")
    lines = [re.sub(r"\x1b\[[\d;]*m", "", ln) for ln in form.gemma_panel(r, RC, {"MONDO:0007739": "헌팅턴병"}, 120)]
    assert lines[0].startswith("┌─ Gemma judge") and lines[-1].startswith("└") and any("헌팅톤무도병" in ln for ln in lines)
    assert any("├─ align  헌팅턴병" in ln for ln in lines) and any("└─ sym" in ln for ln in lines)
    assert any("→ Neuro" in ln and "Gemma align" in ln for ln in lines)
    assert not any(c in "".join(lines) for c in "●○█░▶·")              # glyphs whose width differs between fonts
    assert len({form._w(ln) for ln in lines}) == 1                  # the right border lines up


def test_the_app_sets_the_validity_threshold_over_the_models(monkeypatch):
    import gemma_runtime as GR
    monkeypatch.delenv("ADC_VALID_THR", raising=False)
    assert GR.valid_threshold(0.995) == 0.95
    monkeypatch.setenv("ADC_VALID_THR", "model"); assert GR.valid_threshold(0.995) == 0.995


def test_motion_replays_the_frame_and_lands_on_the_drawn_screen(monkeypatch):
    """a transition plays the recorded frame in intermediate frames and then shows exactly what the screen drew."""
    import motion
    monkeypatch.setattr(motion, "enabled", lambda: True)
    monkeypatch.setattr(motion.time, "sleep", lambda s: None)
    class Fake:
        def __init__(self): self.rows = {}; self.frames = []
        def getmaxyx(self): return (20, 60)
        def erase(self): self.rows = {}
        def addstr(self, y, x, s, attr=0): self.rows.setdefault(y, []).append((x, s))
        def refresh(self): self.frames.append({y: "".join(s for _, s in sorted(v)) for y, v in self.rows.items()})
    fake = Fake(); win = motion.Win(fake)
    win.erase(); win.addstr(1, 2, "ADCTOX", 1); win.addstr(5, 2, "Heart failure  Cardio  심부전"); win.addstr(6, 2, "Cirrhosis")
    win.transition("slide", dir=1); win.refresh()
    assert len(fake.frames) > 2 and fake.frames[-1] == {1: "ADCTOX", 5: "Heart failure  Cardio  심부전", 6: "Cirrhosis"}
    assert all(f.get(1) == "ADCTOX" for f in fake.frames)                                       # the brand row never moves
    assert any(f.get(5) != "Heart failure  Cardio  심부전" for f in fake.frames[:-1])         # on the way in, the row is still cut
    n = len(fake.frames); win.erase(); win.addstr(4, 2, "a"); win.addstr(5, 2, "b"); win.addstr(6, 2, "c"); win.transition("cascade"); win.refresh()
    assert fake.frames[-1] == {4: "a", 5: "b", 6: "c"} and any(len(f) < 3 for f in fake.frames[n:-1])   # rows arrive one by one
    monkeypatch.setattr(motion, "enabled", lambda: False)
    before = len(fake.frames); win.erase(); win.addstr(4, 2, "x"); win.transition("wipe"); win.refresh()
    assert len(fake.frames) == before + 1                                                        # off: one frame, no replay


@pytest.mark.parametrize("keys, goes_on", [(["\n"], True), (["KEY_DOWN", "\n"], False)])
def test_saved_patient_is_offered_to_go_on_or_start_new(monkeypatch, keys, goes_on):
    """0.5.3: a saved run in progress is not loaded silently; the first screen names what is saved and where."""
    import types
    import form
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console)
    monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True)
    monkeypatch.setattr(term._Screen, "_size", lambda self: (30, 100))
    screen = term._Screen(console)
    frames = []
    it = iter([getattr(console, k) if k.startswith("KEY_") else k for k in keys])
    screen.refresh = lambda: frames.append("\n".join("".join(ch for ch, _ in line) for line in screen.buf))
    screen.get_wch = lambda: next(it)
    RC = types.SimpleNamespace(_reg={}, condition_name=lambda c: c)
    st = dict(picked=set(), free="pulmonary TB, Hemophilia A", raw={"hb": 8.0}, choice={})
    assert form.Form(screen, RC).resume(st) is goes_on
    first = frames[0]
    assert "질환 2개 (pulmonary TB, Hemophilia A), 검사 수치 1개" in first and "last_input.json" in first and "새 환자로 시작" in first
