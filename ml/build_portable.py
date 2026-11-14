"""Build dist/adc_recommender.py: the recommender as ONE file that runs off this server (Python >= 3.10 + numpy).

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_portable.py            -> dist/adc_recommender.py (light)
    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_portable.py --full     -> dist/adc_recommender_full.py

--full is the installed app: free text goes through the organ judge (ml/scratch_runtime.py) exactly as ml/recommend.py does
here. It needs torch and transformers, and the model bundle (ScratchJudge/, mondo_index.npz for MONDO names and Korean KCD
names) that adctox --update-models installs, or a models folder in ADC_MODEL_DIR. The name-index code is the server's own
(ml/mondo_index.py), copied function by function; only file locations change. GPU when torch sees one, else CPU.

What goes in:
  * the program modules as they are here (recommend, restrictions, labs, form, tui, webapp), served from the file by an importer,
    and the page of adctox --web (ml/web/, data["web"]: webapp serves it from memory);
  * the label evidence (ml/drug_evidence.evidence(), computed now from the DailyMed snapshot), the 97 label rules, the
    condition registry and the checks, as compressed JSON;
  * MONDO disease names and exact synonyms that map to an organ (the same ancestor -> organ crosswalk as ml/mondo_index.py).
What changes, and only this:
  * free text is matched by string (exact name / synonym, then close spelling) instead of the organ judge, so it understands
    fewer phrasings;
  * data come from the file, not from server paths.
Every substitution is asserted, so a change in the source that breaks one stops the build instead of shipping it.
"""
import base64, csv, json, os, pathlib, re, sys, zlib
import yaml

R = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(R / "ml"), str(R / "src")]
OBO = R / "data/raw_big/mondo/2026-10-07/mondo.obo"
FULL = "--full" in sys.argv
_pos = [a for a in sys.argv[1:] if a != "--full"]
OUT = pathlib.Path(_pos[0]) if _pos else R / ("dist/adc_recommender_full.py" if FULL else "dist/adc_recommender.py")


def mondo_terms():
    """{lowercase name or exact synonym: [canonical name, [organ axes]]} for diseases with at least one organ."""
    from drug_evidence import AXES
    T = {}; cur = None; term = False
    for line in open(OBO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": term, cur = True, None; continue
        if line.startswith("["): term = False; continue
        if not term or not line: continue
        if line.startswith("id: "): cur = line[4:].strip(); T[cur] = dict(name="", syn=[], parents=set(), obs=False)
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:].strip()
        elif line.startswith("is_obsolete: true"): T[cur]["obs"] = True
        elif line.startswith("synonym: ") and " EXACT " in line:
            q = re.match(r'synonym: "(.*)" EXACT', line)
            if q: T[cur]["syn"].append(q.group(1))
        elif line.startswith("is_a: "):
            p = line[6:].split()[0]
            if p.startswith(("MONDO:", "HP:")): T[cur]["parents"].add(p)
    memo = {}
    def anc(t):
        if t in memo: return memo[t]
        seen, st = set(), list(T[t]["parents"]) if t in T else []
        while st:
            n = st.pop()
            if n in seen: continue
            seen.add(n); st.extend(T[n]["parents"] if n in T else ())
        memo[t] = seen; return seen
    cross = {k.lower(): v for k, v in yaml.safe_load(open(R / "conf/ontology/mondo_organ_axis.yaml", encoding="utf-8"))["ancestor_to_axis"].items()}
    out = {}
    for t, d in T.items():
        if not t.startswith("MONDO:") or d["obs"] or not d["name"] or not (t == "MONDO:0000001" or "MONDO:0000001" in anc(t)): continue
        axes = sorted({cross[T[a]["name"].lower()] for a in anc(t) | {t} if a in T and T[a]["name"].lower() in cross} & set(AXES), key=AXES.index)
        if not axes: continue
        for s in [d["name"]] + d["syn"]: out.setdefault(s.lower(), [d["name"], axes])
    return out


PORTABLE_FREE = '''
def _free_info(free, progress=None):
    """portable: string matching. Registry: exact label / id, else close spelling (ratio >= 0.9), as link["registry"]. MONDO:
    exact name or exact synonym, else the closest spelling among names and synonyms (ratio >= 0.88). No model."""
    import difflib
    import subtypes as ST
    D = _portable_data(); terms = D["mondo"]; keys = D["_mondo_keys"]
    general = {v[0].lower(): v[2] for v in ST.general_map().values() if v[2]}
    def read(q, key):
        """a numbered subtype the text does not name reads as its general concept, as with the organ judge (recommend._candidates)"""
        g = general.get(terms[key][0].lower())
        return terms.get(g.lower(), terms[key]) if g and not ST.keeps(q, terms[key][0]) else terms[key]
    reg = {**{r["label"].lower(): i for i, r in _reg.items()}, **{i.replace("_", " "): i for i in _reg}}
    links = []
    for text in free:
        q = " ".join(text.lower().replace("_", " ").split())
        m = difflib.get_close_matches(q, list(reg), n=1, cutoff=0.9)
        near = (reg[m[0]], 1.0 if m[0] == q else difflib.SequenceMatcher(None, q, m[0]).ratio()) if m else None
        if q in terms: name, axes = read(q, q); links.append(dict(name=name, sim=1.0, axes=axes, registry=near)); continue
        m = difflib.get_close_matches(q, keys, n=1, cutoff=0.88)
        if m: name, axes = read(q, m[0]); links.append(dict(name=name, sim=difflib.SequenceMatcher(None, q, m[0]).ratio(), axes=axes, registry=near))
        else: links.append(dict(name="", sim=0.0, axes=[], registry=near))
    return links
'''

DE_STUB = '''"""portable: label evidence computed on the server from the DailyMed snapshot, carried in this file."""
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]


def evidence():
    import recommend
    E = recommend._portable_data()["evidence"]
    for e in E.values():
        for o in e["organs"].values(): o["headings"] = [tuple(h) for h in o["headings"]]
    return E
'''


RT_HEAD = '''"""full build: the server's model code, reading its files from the models folder."""
import os, sys, time, warnings
import numpy as np, torch, torch.nn as nn
import adc_runtime
warnings.filterwarnings("ignore")
for _k, _v in (("HF_HUB_OFFLINE", "1"), ("TRANSFORMERS_OFFLINE", "1"), ("TOKENIZERS_PARALLELISM", "false"), ("TRANSFORMERS_VERBOSITY", "error")):
    os.environ.setdefault(_k, _v)
_HERE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0]))
_BASE = os.environ.get("ADC_MODEL_DIR") or os.path.join(_HERE, "models")
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
'''


def extract(path, names):
    """verbatim source of these top-level functions / classes (with decorators), in file order."""
    import ast
    text = path.read_text(); lines = text.splitlines(keepends=True); out, seen = [], set()
    for n in ast.parse(text).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names:
            start = min([d.lineno for d in n.decorator_list] + [n.lineno]) - 1
            out.append("".join(lines[start:n.end_lineno])); seen.add(n.name)
    assert seen == set(names), f"{path.name}: missing {set(names) - seen}"
    return "\n\n".join(out) + "\n"


def runtime_modules():
    """mondo_index for the full build (names, organs and Korean KCD names of the bundle's index): server functions, local file locations."""
    mi = extract(R / "ml/mondo_index.py", ["close", "_load", "concept", "_ko_norm", "korean"])
    mi = RT_HEAD + 'C = _BASE + os.sep\n_ENC = {}; _IDX = None; _IDX_E = None; import re; HANGUL = re.compile("[가-힣]")\n\n' + mi
    src = (R / "ml/mondo_index.py").read_text()
    assert "_IDX = None" in src and 'C + "mondo_index.npz"' in mi       # constants above match the server
    used = set(re.findall(r"\bMI\.(\w+)", "".join((R / "ml" / f).read_text() for f in ("recommend.py", "suggest.py"))))
    gone = sorted(n for n in used if not re.search(rf"^(def {n}\(|{n} = |.*\b{n} = )", mi, re.M) and n not in ("AXES",))
    assert not gone, f"mondo_index functions the app uses but the full build leaves out: {gone}"
    return mi


def sub(src, old, new, name):
    assert old in src, f"{name}: expected text not found: {old[:70]!r}"
    return src.replace(old, new, 1)


def main():
    if snapshot := os.environ.get("ADCTOX_EVIDENCE_SNAPSHOT"):
        E = json.loads(pathlib.Path(snapshot).read_text(encoding="utf-8"))["evidence"]
    else:
        import drug_evidence as DE
        E = json.loads(json.dumps(DE.evidence(), default=lambda x: x.item() if hasattr(x, "item") else list(x) if isinstance(x, (set, tuple)) else str(x)))
    data = dict(evidence=E, rules=yaml.safe_load(open(R / "conf/label_restrictions.yaml", encoding="utf-8"))["rules"],
                registry=list(csv.DictReader(open(R / "conf/comorbidity_registry.csv", encoding="utf-8"))),
                registry_concepts=json.load(open(R / "conf/registry_concepts.json", encoding="utf-8"))["concepts"],
                registry_aliases=yaml.safe_load(open(R / "conf/registry_aliases.yaml", encoding="utf-8"))["aliases"],
                checks=yaml.safe_load(open(R / "conf/patient_checks.yaml", encoding="utf-8"))["checks"], mondo={} if FULL else mondo_terms(),
                profiles=__import__("suggest").read_profiles(R / "data/curated/disease_profiles"), nonhuman=sorted(__import__("suggest").nonhuman_ids(OBO)),
                mondo_ko={t: [k, en] + list(alt) for t, (k, alt, en) in __import__("suggest").read_mondo_ko(R / "data/curated/korean/mondo_ko.jsonl").items()},
                mechanisms={r["adc"]: r for r in csv.DictReader(open(R / "data/curated/competition/adc_mechanism_draft.csv", encoding="utf-8"))},
                indications={r["adc"]: r for r in csv.DictReader(open(R / "data/curated/competition/adc_indications.csv", encoding="utf-8"))},
                cancers={r["cancer"]: r["adcs"].split(";") for r in csv.DictReader(open(R / "data/curated/competition/adc_cancers.csv", encoding="utf-8"))},
                cancer_mondo=json.load(open(R / "data/curated/competition/cancer_mondo.json", encoding="utf-8")),
                subtypes=json.load(open(R / "data/curated/disease_linking/subtype_general.json", encoding="utf-8")),
                trial_ae=json.load(open(R / "data/curated/competition/trial_ae.json", encoding="utf-8")),
                studio_catalog_368k=json.load(open(R / "ml/data/studio_catalog_368k.json", encoding="utf-8")),
                studio_368k_svd_b64=base64.b64encode((R / "ml/data/studio_368k_svd.npz").read_bytes()).decode(),
                deep_research_cache_b64=base64.b64encode((R / "ml/data/deep_research_cache.npz").read_bytes()).decode(),
                web=__import__("webapp").web_files(R / "ml/web"))
    assert {"index.html", "app.js", "app.css"} <= set(data["web"]), f"adctox --web needs its page in ml/web/: found {sorted(data['web'])}"
    print("page: " + ", ".join(f"{name} {(len(base64.b64decode(text)) if name.endswith(('.woff2', '.ttf', '.otf', '.png', '.ico')) else len(text.encode())) / 1024:.1f} KB" for name, text in data["web"].items()))
    blob = base64.b64encode(zlib.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), 9)).decode()
    src = {m: (R / "ml" / f"{m}.py").read_text(encoding="utf-8") for m in ("recommend", "restrictions", "labs", "form", "tui", "term", "suggest", "subtypes", "scratch_runtime", "adc_version", "adc_runtime", "adc_updates", "motion", "studio_matrix", "deep_research", "webapp")}
    local = {q.stem for q in (R / "ml").glob("*.py")}                      # the screen modules import only embedded modules (0.4.0: motion)
    for m in ("form", "tui", "term", "motion", "studio_matrix", "deep_research", "webapp"):
        for name in set(re.findall(r"^\s*(?:import|from)\s+(\w+)", src[m], re.M)):
            assert name not in local or name in src, f"{m} imports ml/{name}.py, which the portable build does not embed"

    rc = src["recommend"]
    rc = sub(rc, 'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n', "", "recommend")
    rc = sub(rc, '_reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv", encoding="utf-8"))}',
             '_reg = {r["id"]: r for r in _portable_data()["registry"]}', "recommend")
    rc = sub(rc, '_by_concept = json.load(open(R + "conf/registry_concepts.json", encoding="utf-8"))["concepts"]',
             '_by_concept = _portable_data()["registry_concepts"]', "recommend")
    rc = sub(rc, '_ALIASES = __import__("yaml").safe_load(open(R + "conf/registry_aliases.yaml", encoding="utf-8"))["aliases"]',
             '_ALIASES = _portable_data()["registry_aliases"]', "recommend")
    if not FULL:
        rc = sub(rc, 'HAS_LEARNED = True ', 'HAS_LEARNED = False', "recommend")
        i = rc.index("def _free_info("); j = rc.index("\nTIE, CONFIRM", i) + 1
        rc = rc[:i] + PORTABLE_FREE.strip() + "\n\n\n" + rc[j:]
    rc = sub(rc, '    import yaml\n    out = []\n', '    out = []\n', "recommend")
    rc = sub(rc, 'for c in yaml.safe_load(open(R + "conf/patient_checks.yaml", encoding="utf-8"))["checks"]:', 'for c in _portable_data()["checks"]:', "recommend")
    if not FULL:
        rc = sub(rc, 'MATCH_COS = 0.60 ', 'MATCH_COS = 9.99 ', "recommend")          # no loose 'borrowing' of organs by spelling
        rc = sub(rc, 'REG_NEAR = 0.80 ', 'REG_NEAR = 0.90 ', "recommend")
    rc = rc.replace("import drug_evidence as DE, restrictions as RS", "import drug_evidence as DE, restrictions as RS\nfrom __adc_data__ import _portable_data")
    rs = src["restrictions"]
    rs = sub(rs, 'R = str(Path(__file__).resolve().parents[1]) + os.sep', 'R = ""', "restrictions")
    rs = sub(rs, "import yaml\n", "", "restrictions")
    rs = sub(rs, '    return yaml.safe_load(open(R + "conf/label_restrictions.yaml", encoding="utf-8"))["rules"]',
             '    from __adc_data__ import _portable_data\n    return _portable_data()["rules"]', "restrictions")
    src["recommend"], src["restrictions"], src["drug_evidence"] = rc, rs, DE_STUB
    if FULL: src["mondo_index"] = runtime_modules()
    src["__adc_data__"] = f'''import base64, json, zlib
_D = None
def _portable_data():
    global _D
    if _D is None:
        _D = json.loads(zlib.decompress(base64.b64decode(BLOB)).decode()); _D["_mondo_keys"] = list(_D["mondo"])
    return _D
BLOB = "{blob}"
'''
    mods = json.dumps({k: v for k, v in src.items()}, ensure_ascii=False)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(f'''#!/usr/bin/env python3
{{HEAD}}

    python adc_recommender.py                       interactive menus (arrow keys; work in Windows Terminal without extra packages)
    python adc_recommender.py cirrhosis glaucoma --lab bilirubin=2.0 --lab ast=50
    python adc_recommender.py --list                condition ids

Built from the project repository on {__import__("datetime").date.today()} (DailyMed label snapshot 2026-10-07, {len(data["rules"])} label rules).
{{FREE}}
This orders label evidence for one patient; it is not a probability of an adverse event.

Data carried in this file: FDA labels via DailyMed (U.S. NLM; public domain); MONDO Disease Ontology names and synonyms
(Monarch Initiative, CC BY 4.0, https://mondo.monarchinitiative.org); disease profiles for the search (names, everyday words,
symptoms, treatments in English and Korean) written for this project by Claude and not yet reviewed by clinicians.{{DATA}}
"""
import importlib.abc, importlib.util, json, sys

# what the embedded modules import, loaded now (a bundler sees them, and nothing is read from the unpack folder later)
import base64, csv, dataclasses, difflib, itertools, locale, os, re, shutil, textwrap, threading, time, unicodedata, warnings, zlib
if False:   # never runs: platform-specific imports and those of adctox --web, listed for the bundler
    import ctypes, curses, msvcrt, select, termios, tty
    import contextlib, http.server, secrets, traceback, urllib.parse, webbrowser
    import numpy{{TORCH}}

_SRC = json.loads({mods!r})


class _Here(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        return importlib.util.spec_from_loader(name, self) if name in _SRC else None
    def create_module(self, spec): return None
    def exec_module(self, module):
        module.__file__ = os.path.abspath(__file__) if "__file__" in globals() else os.path.abspath(sys.argv[0])
        exec(compile(_SRC[module.__name__], f"<adc_recommender:{{module.__name__}}>", "exec"), module.__dict__)


sys.meta_path.insert(0, _Here())

if __name__ == "__main__":
    import recommend
    recommend.main()
''')
    text = OUT.read_text()
    if FULL:
        text = text.replace("{HEAD}", '"""ADC label-based recommender, full version: the server program with its organ judge.', 1)
        text = text.replace("{FREE}", "Free text goes through the organ judge (x2te) to MONDO (GPU if available, else CPU); needs the model bundle.", 1)
        text = text.replace("{DATA}", "\nThe model bundle holds the organ judge, trained from random weights (no pretrained model), and a MONDO name index.", 1)
        text = text.replace("{TORCH}", "\n    import torch, transformers", 1)
    else:
        text = text.replace("{HEAD}", '"""ADC label-based recommender: one file, runs anywhere with Python >= 3.10 and numpy.', 1)
        text = text.replace("{FREE}", "Free text is matched by spelling against MONDO names and synonyms (the server version uses a language model).", 1)
        text = text.replace("{DATA}", " No patient-level or FinnGen data are included.", 1)
        text = text.replace("{TORCH}", "", 1)
    OUT.write_text(text)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB; {len(data['mondo'])} MONDO strings)")


if __name__ == "__main__":
    main()
