"""What a typed or picked patient input turns into: the registry condition behind it, the lab value it means, the verdict it gets."""
import pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import form
import recommend as RC


def row_of(rows, adc): return next(r for r in rows if r["adc"] == adc)


@pytest.mark.parametrize("typed", ["bleomycin", "Bleomycin", "블레오마이신", "concomitant bleomycin", "Concomitant  Bleomycin", "concomitant_bleomycin"])
def test_typed_bleomycin_contraindicates_brentuximab(typed):
    rows, _, notes, _ = RC.recommend([typed])
    row = row_of(rows, "brentuximab-vedotin")
    assert row["verdict"].worst_known == RC.RS.TIER["contraindicated"] and row["restriction"].startswith("Contraindicated")
    assert notes == [(typed, RC.CONTEXT["concomitant_bleomycin"])] and RC.unresolved([typed]) == []
    assert RC.analyze_conditions([typed]) == [] and RC.ambiguous_conditions([typed]) == []


def test_the_bleomycin_suggestion_reads_back_as_the_rule_condition():
    import suggest as SG
    for typed in ("bleomycin", "블레오마이신"):
        kind, value, label, *_ = SG.names(RC, typed)[0]
        assert kind == "text" and "bleomycin" in label.lower()
        _, free, _ = form.Form._split(None, [(kind, value, label, "", [])])
        assert RC.resolve(form.split_free(free))[2] == {"concomitant_bleomycin"}


def _no_link(monkeypatch):
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: [dict(mondo=None, name="", sim=0.0, axes=[], gate=None, readings=[], ambiguous=False) for _ in free])


def _picked(monkeypatch, text, concept, name, organs):
    _no_link(monkeypatch)
    monkeypatch.setattr(RC, "_chosen", lambda mondo: (name, organs))
    monkeypatch.setitem(RC.CHOICE, text, concept)


def _typed(monkeypatch, concept, name, organs):
    link = dict(mondo=concept, name=name, sim=1.0, axes=organs, gate=True, valid=True, readings=[], ambiguous=False, judge=True, concept=concept, concept_name=name)
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: [dict(link) for _ in free])


@pytest.mark.parametrize("concept, name, organs, registry, adc, domain, category", [
    ("MONDO:0005252", "heart failure", ["cardiovascular"], "heart_failure", "trastuzumab-deruxtecan", "cardiac", "insufficient_data"),
    ("HP:0001657", "prolonged QT interval", ["cardiovascular"], "qt_prolongation", "inotuzumab-ozogamicin", "qt", "monitor"),
    ("MONDO:0019514", "hepatic veno-occlusive disease", ["hepatic"], "hepatic_vod_history", "gemtuzumab-ozogamicin", "hepatic", "monitor"),
])
def test_a_picked_reading_counts_like_the_same_concept_typed(monkeypatch, concept, name, organs, registry, adc, domain, category):
    _picked(monkeypatch, "pump trouble", concept, name, organs)
    s, _, ids, _, pc = RC.resolve(["pump trouble"])
    assert ids == {registry}
    verdict = row_of(RC.recommend(["pump trouble"])[0], adc)["verdict"]
    assert any(c == category and r["domain"] == domain and registry in r["when"].get("condition", []) for c, r in verdict.known)
    picked = s.tolist(), pc
    monkeypatch.delitem(RC.CHOICE, "pump trouble")
    _typed(monkeypatch, concept, name, organs)
    s, _, ids, _, pc = RC.resolve(["pump trouble"])
    assert ids == {registry} and (s.tolist(), pc) == picked


def test_a_picked_reading_outside_the_registry_keeps_the_fixed_severity(monkeypatch):
    _picked(monkeypatch, "asthma", "MONDO:0004979", "asthma", ["pulmonary"])
    s, _, ids, _, pc = RC.resolve(["asthma"])
    assert ids == set() and pc == [("asthma", {"pulmonary"}, RC.MONDO_SEVERITY)]

def test_every_rule_threshold_is_reached_when_the_value_is_not_entered():
    import numbers
    RS = RC.RS; rules = RS.load_rules(); organ = {"renal": "renal", "hepatic": "hepatic", "blood": "haematologic", "cardiac": "cardiovascular", "metabolic": "metabolic_endocrine"}
    for rule in rules:
        if rule["domain"] not in organ or not any(isinstance(v, numbers.Number) and not isinstance(v, bool) for v in rule["when"].values()): continue
        verdict = RS.judge(RS.Patient(organs={organ[rule["domain"]]}), [rule["adc"]], rules)[rule["adc"]]
        assert any(r is rule for _, r in verdict.possible), rule


def test_belantamab_platelets_not_entered_may_be_avoid():
    rules = RC.RS.load_rules(); adc = "belantamab-mafodotin"
    open_ = RC.RS.judge(RC.RS.Patient(organs={"haematologic"}), [adc], rules)[adc]
    assert RC.RS.summary(open_) == "Avoid? (blood 2.3)" and open_.inputs == ["Platelets"]
    assert RC.RS.summary(RC.RS.judge(RC.RS.Patient(organs={"haematologic"}, platelets=20), [adc], rules)[adc]) == "Avoid (blood 2.3)"
    assert RC.RS.summary(RC.RS.judge(RC.RS.Patient(organs={"haematologic"}, platelets=25), [adc], rules)[adc]) == "-"

@pytest.mark.parametrize("typed", ["ESRD", "ESKD", "hemodialysis", "Haemodialysis", "peritoneal dialysis", "dialysis", "투석", "혈액투석", "복막투석"])
def test_typed_esrd_or_dialysis_counts_as_on_dialysis(typed):
    assert RC.resolve([typed])[2] == {"dialysis"} and RC.unresolved([typed]) == []
    verdict = row_of(RC.recommend([typed], None, {"egfr": 20})[0], "inotuzumab-ozogamicin")["verdict"]
    assert [c for c, r in verdict.known if r["domain"] == "renal"] == ["insufficient_data"]


@pytest.mark.parametrize("concept, name, organs", [("MONDO:0004375", "end stage renal failure", ["renal"]), ("MONDO:0975708", "dialysis disequilibrium syndrome", ["neurologic", "renal"])])
def test_the_esrd_and_dialysis_concepts_stand_for_dialysis_linked_or_picked(monkeypatch, concept, name, organs):
    _typed(monkeypatch, concept, name, organs)
    assert RC.resolve(["kidneys gone"])[2] == {"dialysis"}
    verdict = row_of(RC.recommend(["kidneys gone"], None, {"egfr": 20})[0], "inotuzumab-ozogamicin")["verdict"]
    assert [c for c, r in verdict.known if r["domain"] == "renal"] == ["insufficient_data"]
    _picked(monkeypatch, "kidneys gone", concept, name, organs)
    assert RC.resolve(["kidneys gone"])[2] == {"dialysis"}


def test_ckd_stage_5_is_not_read_as_dialysis(monkeypatch):
    _typed(monkeypatch, "HP:0003774", "Stage 5 chronic kidney disease", ["renal"])
    assert RC.resolve(["stage 5"])[2] == {"ckd_stage_4_5"}



@pytest.mark.parametrize("key, text", [("anc", "0,8"), ("creatinine", "1,2"), ("platelet", "12,34"), ("platelet", "1234,5"), ("platelet", ",123"), ("ast", "1,23,456")])
def test_a_decimal_comma_is_rejected_not_read_as_a_larger_number(key, text):
    import labs as LB
    with pytest.raises(ValueError, match="숫자를 입력하세요"): LB.parse(key, text)


@pytest.mark.parametrize("key, text, value", [("platelet", "1,234", 1234.0), ("ast", "2,500", 2500.0), ("ast", "12,5", None), ("glucose", "1,000", 1000.0)])
def test_only_thousands_grouping_is_stripped(key, text, value):
    import labs as LB
    if value is None:
        with pytest.raises(ValueError): LB.parse(key, text)
    else: assert LB.parse(key, text) == value



def test_the_lab_uln_replaces_the_default_for_the_rules_and_the_flags():
    import labs as LB
    assert LB.derive({"bilirubin": 1.7})[0]["bili"] == pytest.approx(1.7 / 1.2)
    lab, flags, notes = LB.derive({"bilirubin": 1.7, "uln_bilirubin": 1.0, "ast": 130, "uln_ast": 30, "alt": 50, "uln_alt": 25})
    assert lab["bili"] == 1.7 and lab["ast"] == pytest.approx(130 / 30) and lab["alt"] == 2
    assert ("hepatic", "bilirubin > 1.5 x ULN (CTCAE G2)") in flags and ("hepatic", "AST > 3 x ULN (CTCAE G2)") in flags
    assert "ULN used: bilirubin 1 (entered), ast 30 (entered), alt 25 (entered)" in notes
    assert "ULN used: bilirubin 1.2 (default), ast 40 (default)" in LB.derive({"bilirubin": 1.7, "ast": 20})[2]


def test_mirvetuximab_at_bilirubin_1_7_depends_on_the_lab_uln():
    assert row_of(RC.recommend([], None, {"bilirubin": 1.7})[0], "mirvetuximab-soravtansine")["restriction"].startswith("No adjustment")
    assert row_of(RC.recommend([], None, {"bilirubin": 1.7, "uln_bilirubin": 1.0})[0], "mirvetuximab-soravtansine")["restriction"].startswith("Avoid")


@pytest.mark.parametrize("key", ["uln_bilirubin", "uln_ast", "uln_alt"])
@pytest.mark.parametrize("text", ["0", "-1", "abc", "1,2"])
def test_a_uln_that_is_not_a_positive_number_is_refused(key, text):
    import labs as LB
    with pytest.raises(ValueError): LB.parse(key, text)
    fields = {f[0]: f for f in LB.FIELDS}
    assert fields[key][1].endswith(" ULN") and fields[key][3] == "Liver"


def test_the_uln_used_is_shown_beside_the_x_uln_value():
    raw = {"bilirubin": 1.7, "uln_bilirubin": 1.0, "ast": 50}
    rows, _, notes, _ = RC.recommend([], None, raw)
    values = __import__("labs").derive(raw)[0]
    text = "\n".join(RC._result_context(rows, notes, 120, values, raw=raw))
    assert "Bilirubin 1.7×ULN (ULN 1)" in text and "AST 1.25×ULN (ULN 40)" in text
    gauges = RC._value_gauges(["Bilirubin 1.7×ULN (ULN 1)", "ALT 0.5×ULN (ULN 40)"])
    assert all("━" in line for line in gauges)
    assert "1 mg/dL" not in text                                              # the ULN is on the value's line, not listed again


def test_the_terminal_lab_screen_takes_a_uln_and_reads_the_value_with_it(monkeypatch):
    import term, tui, types
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console); monkeypatch.setattr(term, "USE_SHIM", True)
    monkeypatch.setattr(term._Screen, "_size", lambda self: (30, 100))
    screen = term._Screen(console); frames = []
    screen.refresh = lambda: frames.append("\n".join("".join(ch for ch, _ in line) for line in screen.buf))
    F = form.Form(screen, types.SimpleNamespace(_reg={}, CHOICE={}, AXES=list(tui.GLYPH), condition_name=lambda c: c, _indications=lambda: {}))
    F.step = 1; F.done = []
    import labs as LB
    keys = [k[0] for k in LB.FIELDS]
    moves = lambda key: [console.KEY_DOWN] * keys.index(key)
    it = iter(moves("bilirubin") + list("1.7") + [console.KEY_DOWN] * (keys.index("uln_bilirubin") - keys.index("bilirubin")) + list("1") + [console.KEY_UP] * (keys.index("uln_bilirubin") - keys.index("bilirubin")) + [console.KEY_NPAGE])
    screen.get_wch = lambda: next(it)
    assert F.labs({}) == {"bilirubin": 1.7, "uln_bilirubin": 1.0}
    assert any("Bilirubin 1.7×ULN" in f and "ULN 1 " in f for f in frames) and any("default 1.2" in f for f in frames)



def test_a_picked_name_with_a_comma_stays_one_condition_and_keeps_its_reading():
    name = "Diabetes mellitus, type 2"
    sel = [("mondo", "MONDO:0005148", name, "", []), ("text", "asthma", "asthma", "", [])]
    _, free, choice = form.Form._split(None, sel)
    assert isinstance(free, str) and form.split_free(free) == [name, "asthma"] and choice == {name: "MONDO:0005148"}
    assert [("mondo" if f in choice else "text", choice.get(f, f), f) for f in form.split_free(free)] == [x[:3] for x in sel]


def test_a_saved_free_text_from_an_older_run_still_reads_as_before(monkeypatch, tmp_path):
    import json
    saved = tmp_path / "last_input.json"; saved.write_text(json.dumps(dict(picked=[], free="copd ,   asthma,heart  stop", raw={}, choice={})), encoding="utf-8")
    monkeypatch.setattr(form, "SAVE", str(saved))
    assert form.split_free(form.load()["free"]) == ["copd", "asthma", "heart stop"]


def test_a_comma_in_text_typed_as_is_still_separates():
    _, free, _ = form.Form._split(None, [("text", "copd, asthma", "copd, asthma", "", [])])
    assert form.split_free(free) == ["copd", "asthma"]



def test_a_cancer_with_two_lab_flags_has_no_priority_screen_and_does_not_crash(monkeypatch):
    import term, tui
    console = term._Shim(); screen = term._Screen(console); browsed = []
    monkeypatch.setattr(tui, "curses", console); monkeypatch.setattr(form, "curses", console); monkeypatch.setattr(term, "USE_SHIM", True)
    monkeypatch.setattr(console, "wrapper", lambda app: app(screen))
    monkeypatch.setattr(form, "load", lambda: dict(picked=set(), free="폐암", raw={"hb": 8.0, "alt": 300.0}, choice={})); monkeypatch.setattr(form, "save", lambda st: None)
    for name, stub in dict(resume=lambda self, st: True, conditions=lambda self, picked, free, choice: (picked, free, choice), labs=lambda self, raw: raw,
                           analyze=lambda self, conds: ([], 0.0)).items(): monkeypatch.setattr(form.Form, name, stub)
    monkeypatch.setattr(RC, "browse", lambda rows, *a, **k: browsed.append(rows) or "done")
    _no_link(monkeypatch)
    conds, raw, (rows, _, notes, _) = form.run(RC)
    assert conds == ["폐암"] and raw == {"hb": 8.0, "alt": 300.0} and browsed == [rows] and RC.FIRST is None
    assert [c for c, _ in notes if c.startswith("Lab: ")] == ["Lab: Hb < 10 g/dL", "Lab: ALT > 3 x ULN"]



@pytest.mark.parametrize("patient", [dict(organs={"renal"}), dict(crcl=10), dict(organs={"renal"}, crcl=10)])
def test_enfortumab_reasons_say_what_the_summary_says_when_dialysis_is_open(patient):
    RS = RC.RS; adc = "enfortumab-vedotin"
    verdict = RS.judge(RS.Patient(**patient), [adc])[adc]
    assert RS.summary(verdict) == "No label statement? (renal)"
    assert [x[:2] + x[3:] for x in RC.reason_rows(dict(verdict=verdict))] == [("renal", "No data", "no_statement", False)]


@pytest.mark.parametrize("patient", [dict(organs={"renal"}), dict(organs={"hepatic"}), dict(crcl=10), dict(crcl=45), dict(bili=2.0), dict(organs={"haematologic"}), dict(organs={"renal", "hepatic", "cardiovascular"})])
def test_every_open_verdict_in_the_summary_has_its_reason_row(patient):
    RS = RC.RS; rules = RS.load_rules()
    for adc, verdict in RS.judge(RS.Patient(**patient), sorted({r["adc"] for r in rules}), rules).items():
        reasons = [(x[0], x[3]) for x in RC.reason_rows(dict(verdict=verdict)) if not x[4]]
        for category, domains, settled in RS.summary_parts(verdict):
            if not settled: assert {(d, category) for d in domains} <= set(reasons), (adc, patient)



NFD = __import__("unicodedata").normalize("NFD", "폐암")


def test_a_decomposed_hangul_paste_reads_like_the_typed_name(monkeypatch):
    import types
    assert NFD != "폐암" and RC.cancer_alias(NFD) == RC.cancer_alias("폐암") is not None
    monkeypatch.setitem(sys.modules, "mondo_index", types.SimpleNamespace(korean=lambda t: {"치매": "dementia"}.get(t)))
    assert RC.english([__import__("unicodedata").normalize("NFD", "치매")]) == ["dementia"]
    assert form.split_free(f"{NFD}, asthma") == ["폐암", "asthma"]


def test_the_plain_prompts_normalize_what_they_read(monkeypatch):
    answers = iter([f"{NFD}, " + __import__("unicodedata").normalize("NFD", "블레오마이신"), ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers)); monkeypatch.setattr(RC, "HAS_LEARNED", False); _no_link(monkeypatch)
    conds, *_ = RC.wizard()
    assert conds == ["폐암", "블레오마이신"] and RC.resolve(conds)[2] == {"concomitant_bleomycin"}


@pytest.mark.parametrize("typed, condition", [("CKD stage 3", "ckd_stage_3"), ("ckd 3b", "ckd_stage_3"), ("CKD3", "ckd_stage_3"), ("CKD stage 4", "ckd_stage_4_5"), ("ckd 5", "ckd_stage_4_5")])
def test_a_staged_ckd_is_that_stage_and_not_esrd(typed, condition):
    """the judge links 'CKD stage 3' to end stage renal failure, and that concept counts as ESRD in the label rules"""
    _, _, ids, _, _ = RC.resolve([typed])
    assert ids == {condition} and "dialysis" not in ids
