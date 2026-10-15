"""Build dist/adc_recommender.py: the recommender as ONE file that runs off this server (Python >= 3.10 + numpy).

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_portable.py            -> dist/adc_recommender.py (light)
    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_portable.py --full     -> dist/adc_recommender_full.py

--full keeps the server's language models: free text goes through BioLORD / SapBERT to MONDO and the FinnGen-trained head
is offered when MONDO finds no organ, exactly as ml/recommend.py does here. It needs torch, transformers and
sentence-transformers, and a models folder (BioLORD-2023, SapBERT, mondo_index.npz, vuln_biolord.pt) next to the program or
in ADC_MODEL_DIR. The model code is the server's own (ml/vulnerability_model.py, ml/mondo_index.py, ml/lab.py), copied
function by function; only file locations change. GPU when torch sees one, else CPU.

What goes in:
  * the program modules as they are here (recommend, restrictions, labs, form, tui), served from the file by an importer;
  * the label evidence (ml/drug_evidence.evidence(), computed now from the DailyMed snapshot), the 97 label rules, the
    condition registry and the checks, as compressed JSON;
  * MONDO disease names and exact synonyms that map to an organ (the same ancestor -> organ crosswalk as ml/mondo_index.py).
What changes, and only this:
  * free text is matched by string (exact name / synonym, then close spelling) instead of BioLORD / SapBERT embeddings,
    so it understands fewer phrasings; the FinnGen estimate is not offered (it is off by default on the server too);
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
    cross = {k.lower(): v for k, v in yaml.safe_load(open(R / "conf/ontology/mondo_organ_axis.yaml"))["ancestor_to_axis"].items()}
    out = {}
    for t, d in T.items():
        if not t.startswith("MONDO:") or d["obs"] or not d["name"] or not (t == "MONDO:0000001" or "MONDO:0000001" in anc(t)): continue
        axes = sorted({cross[T[a]["name"].lower()] for a in anc(t) | {t} if a in T and T[a]["name"].lower() in cross} & set(AXES), key=AXES.index)
        if not axes: continue
        for s in [d["name"]] + d["syn"]: out.setdefault(s.lower(), [d["name"], axes])
    return out


PORTABLE_FREE = '''
def _free_info(free, progress=None):
    """portable: string matching. Registry: exact label / id, else close spelling (ratio >= 0.9). MONDO: exact name or
    exact synonym, else the closest spelling among names and synonyms (ratio >= 0.88). No embeddings, no learned vector."""
    import difflib
    D = _portable_data(); terms = D["mondo"]; keys = D["_mondo_keys"]
    reg = {**{r["label"].lower(): i for i, r in _reg.items()}, **{i.replace("_", " "): i for i in _reg}}
    best, links = [], []
    for text in free:
        q = " ".join(text.lower().replace("_", " ").split())
        m = difflib.get_close_matches(q, list(reg), n=1, cutoff=0.9)
        best.append((reg[m[0]], 1.0 if m and m[0] == q else (difflib.SequenceMatcher(None, q, m[0]).ratio() if m else 0.0)) if m else (next(iter(_reg)), 0.0))
        if q in terms: name, axes = terms[q]; links.append(dict(name=name, sim=1.0, axes=axes)); continue
        m = difflib.get_close_matches(q, keys, n=1, cutoff=0.88)
        if m: name, axes = terms[m[0]]; links.append(dict(name=name, sim=difflib.SequenceMatcher(None, q, m[0]).ratio(), axes=axes))
        else: links.append(dict(name="", sim=0.0, axes=[]))
    return best, links, None
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
    """vulnerability_model and mondo_index for the full build: server functions, local file locations."""
    vm = extract(R / "ml/lab.py", ["TwoTower"]) + "\n" + extract(R / "ml/vulnerability_model.py", ["close", "_encoder", "_st", "_ensemble", "axis_net", "predict", "predict_models", "agreement"])
    vm = sub(vm, '"FremyCompany/BioLORD-2023"', 'os.path.join(_BASE, "BioLORD-2023")', "vulnerability_model")
    vm = vm.replace("lab.TwoTower", "TwoTower"); assert not re.search(r"\blab\.(?!py)", vm)
    vm = RT_HEAD + 'DEV = "cuda:0" if torch.cuda.is_available() else "cpu"; PT = os.path.join(_BASE, "vuln_biolord.pt")\n_ST, _EMB, _CK, _EMB_MAX, _CK_AXIS, _CK_HIDDEN, _CK_ALT, _CK_OPT = {}, {}, {}, 4096, [], set(), [], {"agree_min": 1}\n\n' + vm
    mi = extract(R / "ml/mondo_index.py", ["_encoder", "_embed", "close", "_char_feats", "gate_inputs", "link", "concept", "readings", "abbreviations", "concept_candidates", "_tri", "rr_features", "rerank_scores", "phenotype", "_ko_norm", "korean"])
    mi = RT_HEAD + 'THETA = 0.75; NAME = os.path.join(_BASE, "SapBERT"); C = _BASE + os.sep\n_ENC = {}; _IDX = None; _IDX_E = None; TIE = 0.02; HPO_THETA = 0.85; RR_K = 10; import re; ABBREV = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,5}$"); HANGUL = re.compile("[가-힣]")\n\n' + mi
    src = (R / "ml/mondo_index.py").read_text()
    assert "THETA = 0.75;" in src and "_IDX = None" in src and 'C + "mondo_index.npz"' in mi       # constants above match the server
    return vm, mi


def sub(src, old, new, name):
    assert old in src, f"{name}: expected text not found: {old[:70]!r}"
    return src.replace(old, new, 1)


def main():
    if snapshot := os.environ.get("ADCTOX_EVIDENCE_SNAPSHOT"):
        E = json.loads(pathlib.Path(snapshot).read_text())["evidence"]
    else:
        import drug_evidence as DE
        E = json.loads(json.dumps(DE.evidence(), default=lambda x: x.item() if hasattr(x, "item") else list(x) if isinstance(x, (set, tuple)) else str(x)))
    data = dict(evidence=E, rules=yaml.safe_load(open(R / "conf/label_restrictions.yaml"))["rules"],
                registry=list(csv.DictReader(open(R / "conf/comorbidity_registry.csv"))),
                checks=yaml.safe_load(open(R / "conf/patient_checks.yaml"))["checks"], mondo={} if FULL else mondo_terms(),
                profiles=__import__("suggest").read_profiles(R / "data/curated/disease_profiles"))
    if FULL: data["learned"] = json.load(open(R / "ml/results/learned_vulnerability.json"))["severity"]
    blob = base64.b64encode(zlib.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), 9)).decode()
    src = {m: (R / "ml" / f"{m}.py").read_text() for m in ("recommend", "restrictions", "labs", "form", "tui", "term", "suggest", "adc_version", "adc_runtime", "adc_updates")}

    rc = src["recommend"]
    rc = sub(rc, 'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n', "", "recommend")
    rc = sub(rc, '_reg = {r["id"]: r for r in csv.DictReader(open(R + "conf/comorbidity_registry.csv"))}',
             '_reg = {r["id"]: r for r in _portable_data()["registry"]}', "recommend")
    if not FULL:
        rc = sub(rc, 'HAS_LEARNED = True ', 'HAS_LEARNED = False', "recommend")
        i = rc.index("def _free_info("); j = rc.index("\ndef ", i + 10)
        rc = rc[:i] + PORTABLE_FREE.strip() + "\n\n" + rc[j:]
    rc = sub(rc, '    import yaml\n    out = []\n', '    out = []\n', "recommend")
    rc = sub(rc, 'for c in yaml.safe_load(open(R + "conf/patient_checks.yaml"))["checks"]:', 'for c in _portable_data()["checks"]:', "recommend")
    rc = sub(rc, 'return json.load(open(R + "ml/results/learned_vulnerability.json"))["severity"]',
             'return _portable_data()["learned"]' if FULL else 'return {}', "recommend")
    if not FULL:
        rc = sub(rc, 'MATCH_COS = 0.60 ', 'MATCH_COS = 9.99 ', "recommend")          # no loose 'borrowing' of organs by spelling
        rc = sub(rc, 'REG_NEAR = 0.80 ', 'REG_NEAR = 0.90 ', "recommend")
    rc = rc.replace("import drug_evidence as DE, restrictions as RS", "import drug_evidence as DE, restrictions as RS\nfrom __adc_data__ import _portable_data")
    rs = src["restrictions"]
    rs = sub(rs, 'R = str(Path(__file__).resolve().parents[1]) + os.sep', 'R = ""', "restrictions")
    rs = sub(rs, "import yaml\n", "", "restrictions")
    rs = sub(rs, '    return yaml.safe_load(open(R + "conf/label_restrictions.yaml"))["rules"]',
             '    from __adc_data__ import _portable_data\n    return _portable_data()["rules"]', "restrictions")
    src["recommend"], src["restrictions"], src["drug_evidence"] = rc, rs, DE_STUB
    if FULL: src["vulnerability_model"], src["mondo_index"] = runtime_modules()
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
if False:   # never runs: platform-specific imports, listed for the bundler
    import ctypes, curses, msvcrt, select, termios, tty
    import numpy{{TORCH}}

_SRC = json.loads({mods!r})


class _Here(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        return importlib.util.spec_from_loader(name, self) if name in _SRC else None
    def create_module(self, spec): return None
    def exec_module(self, module):
        exec(compile(_SRC[module.__name__], f"<adc_recommender:{{module.__name__}}>", "exec"), module.__dict__)


sys.meta_path.insert(0, _Here())

if __name__ == "__main__":
    import recommend
    recommend.main()
''')
    text = OUT.read_text()
    if FULL:
        text = text.replace("{HEAD}", '"""ADC label-based recommender, full version: the server program with its language models.', 1)
        text = text.replace("{FREE}", "Free text goes through BioLORD / SapBERT to MONDO (GPU if available, else CPU); needs the models folder.", 1)
        text = text.replace("{DATA}", "\nThe models folder holds BioLORD-2023, SapBERT, a MONDO name index and a head trained on FinnGen summary\nstatistics and published Danish disease trajectories (Siggaard et al. 2020); the program prints no FinnGen numbers.", 1)
        text = text.replace("{TORCH}", "\n    import torch, transformers, sentence_transformers", 1)
    else:
        text = text.replace("{HEAD}", '"""ADC label-based recommender: one file, runs anywhere with Python >= 3.10 and numpy.', 1)
        text = text.replace("{FREE}", "Free text is matched by spelling against MONDO names and synonyms (the server version uses a language model).", 1)
        text = text.replace("{DATA}", " No patient-level or FinnGen data are included.", 1)
        text = text.replace("{TORCH}", "", 1)
    OUT.write_text(text)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB; {len(data['mondo'])} MONDO strings)")


if __name__ == "__main__":
    main()
