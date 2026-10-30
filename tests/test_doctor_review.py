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
    assert re.search(r"Lung\s+!!\s+Interstitial Lung Disease/Pneumonitis\s*$", text, re.M)
    assert not re.search(r"\b\d+\.\d+ [A-Z]|Boxed [A-Z]|\[\d+\.\d+\]", text)            # no section numbers
    assert RC.warning_names([("Boxed", "HEPATOTOXICITY"), ("5.1", "Hepatotoxicity")]) == "Hepatotoxicity"
    assert RC.warning_names([("5.2", "Neutropenia"), ("5.3", "Peripheral Neuropathy")]) == "Neutropenia; Peripheral Neuropathy"
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
    keys = ["KEY_DOWN"] * 11 + list("80") + ["KEY_DOWN"] * 5 + ["KEY_NPAGE"]          # Hb 80 (1-25), then try to go on
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


def test_the_first_screen_shows_no_organs(monkeypatch):
    """the organs are first shown by the analysis: neither the picked chips nor the suggestions carry them."""
    r, texts = _conditions(monkeypatch, list("glauc") + [None, None, "PGDN"], ["heart_failure", "cirrhosis"])
    assert r[0] == {"heart_failure", "cirrhosis"}
    last = texts[-1]
    assert "Heart failure" in last and "Glaucoma" in last
    assert not any(o in t for t in texts for o in ("Liver", "Cardio", "Eye", "분석 때 판정", "none of 13"))


def test_every_adc_has_a_cancer_and_every_cancer_an_adc():
    can = RC._cancers()
    assert set(a for v in can.values() for a in v) == set(RC._indications()) and all(can.values())


def _linked(monkeypatch, mondo, name, axes):
    """free text linked to one MONDO concept, without the encoder"""
    link = dict(mondo=mondo, name=name, sim=1.0, judge=True, gate=True, axes=axes, readings=[], ambiguous=False)
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: ([("cirrhosis", 0.1)] * len(free), [dict(link) for _ in free], None))


def test_a_cancer_among_the_diseases_puts_its_adcs_first(monkeypatch):
    """DLBCL typed with the diseases: the patient's cancer, not an organ; the ADCs approved for it first, the others under a rule."""
    _linked(monkeypatch, "MONDO:0018905", "diffuse large B-cell lymphoma", ["haematologic"])
    rows, s, notes, _ = RC.recommend(["cirrhosis", "DLBCL"], {}, {})
    approved = {"polatuzumab-vedotin", "loncastuximab-tesirine", "brentuximab-vedotin"}
    assert {r["adc"] for r in rows[:3]} == approved and not any(r["indicated"] for r in rows[3:])
    assert "haematologic" not in s and RC.patient_cancers(notes) == {"DLBCL": ("diffuse large B-cell lymphoma", ["Large B-cell lymphoma (DLBCL)"])}
    lines, at = RC._result_list(rows, 100)
    rule = next(i for i, ln in enumerate(lines) if "Other cancers" in ln)
    assert at[2] < rule < at[3]
    plain, _ = RC.recommend(["cirrhosis"], {}, {})[:2]
    assert all(r["indicated"] for r in plain) and not any("Other cancers" in ln for ln in RC._result_list(plain, 100)[0])


def test_two_cancers_take_the_adcs_of_both(monkeypatch):
    _linked(monkeypatch, "MONDO:0009693", "plasma cell myeloma", ["haematologic"])
    monkeypatch.setitem(RC.CHOICE, "AML", "MONDO:0018874")
    rows, *_ = RC.recommend(["myeloma", "AML"], {}, {})
    assert {r["adc"] for r in rows if r["indicated"]} == {"belantamab-mafodotin", "gemtuzumab-ozogamicin"}


def test_a_cancer_no_adc_is_approved_for_puts_the_rule_on_top(monkeypatch):
    _linked(monkeypatch, "MONDO:0005062", "lymphoma", ["haematologic"])
    rows, *_ = RC.recommend(["lymphoma"], {}, {})
    lines, at = RC._result_list(rows, 100)
    assert not any(r["indicated"] for r in rows) and "Other cancers" in lines[at[0] - 1]


def test_a_solid_cancer_takes_the_tumour_agnostic_her2_approval():
    terms = RC._cancer_map()["terms"]
    assert "HER2+ (IHC 3+) solid tumor" in terms["MONDO:0024331"][1]                   # colorectal carcinoma
    assert terms["MONDO:0006244"][1] == ["HER2+ (IHC 3+) solid tumor", "HER2+ breast cancer"]
    assert "HER2+ (IHC 3+) solid tumor" not in terms["MONDO:0018905"][1]               # DLBCL is not solid


def test_misread_cancer_names_are_read_as_cancers():
    """the linker reads 폐암 as pneumoconiosis and multiple myeloma as the animal term: the alias table names them"""
    assert RC.cancer_alias("폐암") == "MONDO:0008903" and RC.cancer_alias("다발성 골수종") == "MONDO:0009693"
    assert RC._cancer_map()["terms"]["MONDO:1013329"][1] == ["Multiple myeloma"]
    assert all(RC.is_cancer(m) for m in RC._cancer_map()["aliases"].values())


def test_the_cancer_map_is_built_from_the_csvs():
    import build_cancer_mondo as B
    named = {c for _, cs in RC._cancer_map()["terms"].values() for c in cs}
    assert named <= set(RC._cancers()) and "BPDCN" not in named                         # BPDCN has no MONDO term
    assert B.fold("HER2 양성 유방암") == "her2양성유방암"


def test_the_analysis_shows_a_cancer_as_cancer(monkeypatch):
    _linked(monkeypatch, "MONDO:0018905", "diffuse large B-cell lymphoma", ["haematologic"])
    monkeypatch.setattr(RC, "HAS_LEARNED", False)
    r = RC.analyze_conditions(["DLBCL"])[0]
    assert r["source"] == "Cancer" and r["organs"] == [] and r["cancers"] == ["Large B-cell lymphoma (DLBCL)"]


def test_trial_results_on_the_patients_organs(monkeypatch):
    rows = _rows(monkeypatch)
    tdxd = next(r for r in rows if r["name"] == "Trastuzumab deruxtecan")
    text = "\n".join(map(plain, RC._result_details(tdxd, [], 110)))
    assert "Trial results on the patient's organs" in text and re.search(r"^  DESTINY-Breast0\d, T-DXd 5.4 mg/kg q3w, n=\d+; vs ", text, re.M)
    assert re.search(r"^  Lung\s+(pneumonitis|interstitial lung disease) ", text, re.M)
    assert re.search(r"^  Cardio\s+\S", text, re.M)                                    # heart failure: the patient's organ, with or without a label warning
    gem = next(r for r in rows if r["name"] == "Gemtuzumab ozogamicin")
    assert "no results posted on ClinicalTrials.gov (ALFA-0701, NCT00927498)" in "\n".join(map(plain, RC._result_details(gem, [], 110)))
    assert RC._event_text(dict(term="pneumonitis", a=18, n=257, comp=[1, 261], sa=1, serious=False)) == "pneumonitis 18/257 (7.0%, vs 0.4%), serious 1/257"
    assert RC._event_text(dict(term="ild", a=5, n=257, comp=None, sa=5, serious=True)) == "ild serious 5/257 (1.9%)"
    organs = RC.patient_organs(tdxd)
    assert organs[:len(tdxd["boxed"])] == list(tdxd["boxed"]) and set(organs) >= {"pulmonary", "cardiovascular"}


def test_the_trial_table_is_built_from_the_csv():
    import build_trial_ae as B
    T = RC._trial_ae()["adcs"]
    assert set(T) == set(RC._indications()) and set(B.SIGNAL) == set(RC.AXES)
    for adc, v in T.items():
        assert v["trials"] or v["no_results"], adc
        assert [t["labelled"] for t in v["trials"]] == sorted((t["labelled"] for t in v["trials"]), reverse=True)
        for t in v["trials"]:
            for o in t["organs"].values():
                for e in [o.get("any"), o.get("serious"), *o.get("warned", [])]:
                    if e: assert 0 < e["a"] <= e["n"] and not re.search(B.EXCLUDE, e["term"])
    assert T["belantamab-mafodotin"]["trials"][0]["trial"] == "DREAMM-7" and T["trastuzumab-emtansine"]["trials"][0]["trial"] == "KATHERINE"
    assert {t["trial"] for t in T["polatuzumab-vedotin"]["no_results"]} == {"POLARIX"} and T["polatuzumab-vedotin"]["trials"][0]["trial"] == "GO29365"
    assert B.topics("pulmonary", ["Interstitial Lung Disease/Pneumonitis"]) and not B.topics("pulmonary", [])


def test_the_trial_of_the_patients_cancer_is_shown(monkeypatch):
    _linked(monkeypatch, "MONDO:0006244", "HER2 positive breast carcinoma", [])
    monkeypatch.setattr(RC, "FIRST", None); monkeypatch.setattr(RC, "PRIORITY", {})
    rows, *_ = RC.recommend(["HER2 양성 유방암", "interstitial_lung_disease"], {}, {})
    tdxd = next(r for r in rows if r["name"] == "Trastuzumab deruxtecan")
    assert "HER2+ breast cancer" in tdxd["cancers"]
    text = "\n".join(map(plain, RC._result_details(tdxd, [], 110)))
    assert "  DESTINY-Breast02, T-DXd 5.4 mg/kg q3w, n=404; vs treatment of physician's choice" in text     # the largest HER2+ trial, not DESTINY-Breast06
    assert re.search(r"^  Lung\s+(pneumonitis|interstitial lung disease) \d+/404 \(\d+\.\d%, vs \d+\.\d%\)", text, re.M)
