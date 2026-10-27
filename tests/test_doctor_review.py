"""Fixes from going through the app as a doctor would (2026-10-28): the picked condition reorders the ADCs, the result words say
what they mean, Missing inputs lists only what is missing, and the input screens explain themselves."""
import re, sys, pathlib, types
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import term, tui
import recommend as RC

plain = lambda t: re.sub(r"\x1b\[[\d;]*m", "", t)
PATIENT = (["interstitial_lung_disease", "heart_failure"], {"bilirubin": 2.0, "age": 68, "sex": "F", "weight": 55, "creatinine": 1.4, "lvef": 40})


def _rows(monkeypatch, first=None):
    monkeypatch.setattr(RC, "FIRST", first); monkeypatch.setattr(RC, "PRIORITY", {})
    rows, *_ = RC.recommend(PATIENT[0], {}, PATIENT[1])
    return rows


def test_the_picked_condition_moves_its_organ_warnings_down_but_not_above_avoid(monkeypatch):
    auto = _rows(monkeypatch)
    picked = _rows(monkeypatch, "interstitial_lung_disease")
    lung = lambda r: "pulmonary" in r["boxed"] + r["warn"]
    usable = [r for r in picked if r["tier"] < RC.RS.TIER["avoid"]]
    first_lung = next(i for i, r in enumerate(usable) if lung(r))
    assert all(lung(r) for r in usable[first_lung:])                          # no lung-free ADC below one with a lung warning
    assert all(r["tier"] >= RC.RS.TIER["avoid"] for r in picked[len(usable):])  # Avoid stays at the bottom
    assert [r["name"] for r in auto] != [r["name"] for r in picked]
    assert sorted(r["name"] for r in auto) == sorted(r["name"] for r in picked)
    ranks = [r["rank"] for r in picked]
    assert ranks == sorted(ranks) and ranks[0] == 1


def test_automatic_order_is_unchanged_without_a_pick(monkeypatch):
    rows = _rows(monkeypatch)
    key = [(r["tier"], r["verdict"].worst_known, r["Bl"], r["Wl"], r["name"]) for r in rows]
    assert key == sorted(key)


def test_result_words_say_not_studied_no_data_and_question_mark():
    assert RC.RS.TABLE["insufficient_data"] == "Not studied" and RC.RS.TABLE["no_statement"] == "No data"
    row = {"name": "Sample ADC", "rank": 1, "priority": [], "boxed": [], "warn": [], "organs": {a: {"level": "none"} for a in RC.AXES},
           "verdict": RC.RS.Verdict("sample", [], [("avoid", {"domain": "renal", "when": {"crcl_lt": 30}})], [], [RC.RS.NEEDS["renal"]])}
    lines, starts = RC._result_list([row], 115)
    assert "Avoid?" in plain(lines[starts[0]])                                 # it depends on a value not entered
    assert "Unclear" not in "\n".join(map(plain, lines))


def test_label_bands_read_like_the_label():
    assert RC._when({"crcl_ge": 30, "crcl_lt": 90}) == "CLcr 30 to <90"
    assert RC._when({"bili_gt": 1.5, "bili_le": 3}) == "bilirubin >1.5 to 3×ULN"
    assert RC._when({"crcl_lt": 30}) == "CLcr < 30"


def test_missing_inputs_list_only_values_not_entered(monkeypatch):
    rows = _rows(monkeypatch)
    listed = {m for r in rows for m in RC._missing_inputs(r["verdict"])}
    assert listed and not listed & {"Bilirubin", "LVEF"} and not any("/" in m for m in listed)
    assert all(m in set(RC.RS.INPUT.values()) for m in listed)


def test_details_show_indication_organ_warnings_and_readable_payload(monkeypatch):
    rows = _rows(monkeypatch)
    tdxd = next(r for r in rows if r["name"] == "Trastuzumab deruxtecan")
    text = "\n".join(map(plain, RC._result_details(tdxd, [], 110)))
    assert "HER2+ breast cancer" in text and "Warnings on the patient's organs" in text
    assert re.search(r"Lung\s+!!\s+Boxed INTERSTITIAL LUNG DISEASE; 5.1 Interstitial Lung Disease/Pneumonitis", text)
    assert "topoisomerase I inhibitor" in text and "topo1" not in text
    for r in rows:
        t = "\n".join(map(plain, RC._result_details(r, [], 110)))
        assert not re.search(r"\b(dna_cleave|dna_crosslink|vc_PABC|hydrazone_AcBut_disulfide|IGN_peptide)\b", t), r["name"]
        assert RC._indications()[r["adc"]]["indication"] in t


def _screen(monkeypatch, keys, size=(24, 80)):
    import form
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True); monkeypatch.setattr(term._Screen, "_size", lambda self: size)
    screen = term._Screen(console); frames = []
    it = iter([getattr(console, k) if k.startswith("KEY_") else k for k in keys])
    screen.refresh = lambda: frames.append(["".join(ch for ch, _ in line) for line in screen.buf])
    def get():
        try: return next(it)
        except StopIteration: raise AssertionError("screen did not finish")
    screen.get_wch = get
    return screen, frames


def test_lab_error_names_the_field_and_moves_there(monkeypatch):
    import form
    keys = ["KEY_DOWN"] * 10 + list("80") + ["KEY_DOWN"] * 5 + ["KEY_NPAGE"]          # Hb 80 (1-25), then try to go on
    screen, frames = _screen(monkeypatch, keys + ["KEY_NPAGE"])
    F = form.Form(screen, RC); F.step = 1
    with pytest.raises(AssertionError): F.labs({})
    last = "\n".join(frames[-1])
    assert "Hb: 1–25 g/dL 사이로 입력하세요" in last and re.search(r"→ Hb\s+80", last)
    assert any("ULN 1.2" in ln and "Bilirubin" in ln for f in frames for ln in f)


def _conditions(monkeypatch, keys, picked):
    import form
    screen, frames = _screen(monkeypatch, [], (30, 100))
    it = iter(keys); monkeypatch.setattr(form, "_key", lambda scr, tab=False: next(it))
    def none(): raise form.curses.error                                         # nothing after a bare Esc
    screen.get_wch = none
    F = form.Form(screen, RC); F.step = 0
    return F.conditions(set(picked), ""), ["\n".join(f) for f in frames]


def test_backspace_on_an_empty_box_takes_two_presses(monkeypatch):
    import form
    r, texts = _conditions(monkeypatch, ["BS", "BS", "PGDN"], ["heart_failure", "cirrhosis"])
    assert r[0] == {"cirrhosis"}                                                # one disease out after two presses, not two
    assert any("한 번 더 누르면 뺌: Heart failure" in t for t in texts) and any("뺌: Heart failure" in t and "한 번 더" not in t for t in texts)
    r, _ = _conditions(monkeypatch, ["BS", "UP", "BS", "PGDN"], ["heart_failure", "cirrhosis"])
    assert r[0] == {"heart_failure", "cirrhosis"}                               # another key in between: nothing taken off


def test_the_start_screen_says_what_the_app_does(monkeypatch):
    import form
    r, texts = _conditions(monkeypatch, ["ESC"], [])
    assert r == form.QUIT and "FDA 승인 ADC 15개를 경고가 적은 순서로 보여 줍니다" in texts[0]
