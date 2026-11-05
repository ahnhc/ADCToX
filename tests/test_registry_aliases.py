"""conf/registry_aliases.yaml: typed forms that reach a registry condition before the organ judge reads them.

A wrong alias is silent: it attaches a patient to another condition's restriction rules. So the table is held to what a test
can show: every target exists, a form belongs to one condition, a form is not a cancer name (those read as the patient's cancer),
and the short forms with several meanings stay out. Whether each form means its condition is a clinician's call (see the file header).
"""
import collections
import csv
import hashlib
import json
import pathlib
import unicodedata

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
REG = {r["id"]: r for r in csv.DictReader((ROOT / "conf/comorbidity_registry.csv").open(encoding="utf-8"))}
ALIASES = yaml.safe_load((ROOT / "conf/registry_aliases.yaml").read_text(encoding="utf-8"))["aliases"]
CANCER = json.loads((ROOT / "data/curated/competition/cancer_mondo.json").read_text(encoding="utf-8"))
BENCH = [json.loads(line) for line in (ROOT / "data/curated/registry_linking/queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
fold = lambda text: "".join(unicodedata.normalize("NFC", text).split()).replace("-", "").lower()
form = lambda text: unicodedata.normalize("NFC", text).lower()
AMBIGUOUS = {"ms", "pe", "ra", "cad", "uc", "lc", "cld", "ded", "hd", "tcp", "cp", "pn", "dm", "ad", "mi", "ac", "ca"}


def test_every_alias_targets_a_registry_condition():
    assert set(ALIASES) <= set(REG), set(ALIASES) - set(REG)
    assert all(isinstance(f, str) and f.strip() and f == f.strip() for forms in ALIASES.values() for f in forms)


def test_no_form_is_claimed_by_two_conditions():
    owner = collections.defaultdict(set)
    for cid, forms in ALIASES.items():
        for f in forms: owner[form(f)].add(cid)
    assert {f: c for f, c in owner.items() if len(c) > 1} == {}
    for cid, forms in ALIASES.items():
        assert len({form(f) for f in forms}) == len(forms), f"{cid} lists a form twice"


def test_no_form_is_another_conditions_label_or_id():
    names = {form(r["label"]): cid for cid, r in REG.items()} | {form(cid): cid for cid in REG}
    clash = {f: (names[form(f)], cid) for cid, forms in ALIASES.items() for f in forms if form(f) in names and names[form(f)] != cid}
    assert clash == {}


def test_no_form_is_a_cancer_name_or_cancer_alias():
    cancer = set(CANCER["aliases"]) | {fold(name) for name, _ in CANCER["terms"].values()}
    assert sorted(f for forms in ALIASES.values() for f in forms if fold(f) in cancer) == []


def test_short_forms_with_several_meanings_stay_out():
    assert sorted(f for forms in ALIASES.values() for f in forms if form(f) in AMBIGUOUS) == []


def test_the_forms_that_were_pinned_in_the_code_are_here():
    old = {"dialysis": ["on dialysis", "dialysis", "esrd", "eskd", "hemodialysis", "haemodialysis", "peritoneal dialysis", "투석", "혈액투석", "복막투석"],
           "ckd_stage_3": [f"ckd{sep}{s}" for sep in (" stage ", " ", "") for s in ("3", "3a", "3b")],
           "ckd_stage_4_5": [f"ckd{sep}{s}" for sep in (" stage ", " ", "") for s in ("4", "5")]}
    for cid, forms in old.items():
        assert set(forms) <= {form(f) for f in ALIASES[cid]}, cid


def test_a_child_pugh_form_names_cirrhosis_only():
    assert {"cirrhosis child pugh b", "cirrhosis child-pugh c"} <= set(ALIASES["cirrhosis"])
    assert all("child" not in f for cid, forms in ALIASES.items() if cid != "cirrhosis" for f in forms)


def test_every_condition_has_two_benchmark_inputs():
    n = collections.Counter(r["condition"] for r in BENCH if r["condition"])
    assert {c: n[c] for c in REG if n[c] < 2} == {}
    assert set(n) <= set(REG)


def test_benchmark_is_marked_llm_written_and_split_by_condition_hash():
    assert {r["author"] for r in BENCH} == {"llm"}
    for r in BENCH:
        if r["condition"]:
            assert r["split"] == ("tune" if int(hashlib.sha1(r["condition"].encode()).hexdigest(), 16) % 2 == 0 else "holdout"), r
    halves = {s: {r["condition"] for r in BENCH if r["split"] == s} for s in ("tune", "holdout")}
    assert not halves["tune"] & halves["holdout"]
    assert len({r["query"] for r in BENCH}) == len(BENCH), "a query is listed twice"
