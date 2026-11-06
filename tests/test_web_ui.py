"""Run the UI's axis-row logic under node.

The band basis decides which number a row leads with and what its bar is scaled to, so
the rendering is no longer cosmetic. Skipped where node is unavailable rather than made a
hard dependency: the Python suite is the gate, and this is a guard on one function.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "js" / "axis_row.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_axis_row_renders_both_bases_correctly():
    proc = subprocess.run(
        [shutil.which("node"), str(SCRIPT)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"axis_row.js reported failures:\n{proc.stdout}\n{proc.stderr}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_script_parses():
    """A syntax error in the page is invisible until someone opens it."""
    import re
    import tempfile

    page = Path(__file__).resolve().parents[1] / "web" / "index.html"
    js = re.search(
        r"<script[^>]*>(.*?)</script>", page.read_text(encoding="utf-8"), re.S
    ).group(1)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as fh:
        fh.write(js)
        tmp = fh.name
    proc = subprocess.run(
        [shutil.which("node"), "--check", tmp], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_the_ui_renders_the_live_api_response_not_only_a_fixture() -> None:
    """A field-name drift between the API and the UI passes every fixture test.

    `tests/js/axis_row.js` exercises `axisRow` against hand-built rows, which is the right
    place to pin the band-basis scaling and the driver colouring. It cannot catch the API
    renaming `organ_axis` or dropping `drivers`, because the fixture supplies both. This
    pushes the real response through the real function and fails on `undefined` or `NaN`
    reaching the markup.
    """
    import json
    import tempfile

    if not shutil.which("node"):
        pytest.skip("node not available")

    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    response = client.post("/api/v1/propose", json={
        "comorbidity_profile": {
            "conditions": ["interstitial_lung_disease", "ckd_stage_3"],
            "cohort": {"age_band": "65_74", "sex": "female"},
        },
        "target_antigen": "ERBB2", "top_k": 3,
    })
    assert response.status_code == 200, response.text[:300]
    risks = response.json()["candidates"][0]["organ_risks"]
    assert risks

    harness = r"""
const fs = require("fs"), vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8")
  .match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const ctx = { document: { getElementById: () => null, querySelectorAll: () => [],
  addEventListener() {} }, window: {},
  fetch: () => Promise.resolve({ json: () => ({}) }), console };
vm.createContext(ctx);
try { vm.runInContext(js, ctx); } catch (e) {}
const rows = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
let panels = 0;
for (const r of rows) {
  const html = ctx.axisRow(r);
  if (/undefined|NaN/.test(html)) {
    console.error("rendered undefined/NaN for " + r.organ_axis);
    process.exit(1);
  }
  if (html.includes("data-why")) panels++;
}
if (!panels) { console.error("no axis rendered a driver panel"); process.exit(1); }
console.log(panels + "/" + rows.length);
"""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "live.js"
        data = Path(tmp) / "risks.json"
        script.write_text(harness, encoding="utf-8")
        data.write_text(json.dumps(risks), encoding="utf-8")
        result = subprocess.run(
            ["node", str(script),
             str(Path(__file__).resolve().parents[1] / "web" / "index.html"),
             str(data)],
            capture_output=True, text=True,
        )
    assert result.returncode == 0, result.stderr[-800:]


def test_the_unranked_head_is_announced_and_not_whispered() -> None:
    """A tie group of 49 cannot be presented as six ranked cards.

    The interface used to print "Rank 1" on each of them with a small `tied` tag, and the
    tag's own wording -- "not distinguishable from its group" -- was false whenever the
    leader sat alone in its group. This pushes the live response through the real `headNote`
    and `card` functions and requires the set to be announced, the ordering criterion to be
    named, and no `undefined` or `NaN` to reach the markup.
    """
    import json
    import tempfile

    if not shutil.which("node"):
        pytest.skip("node not available")

    from fastapi.testclient import TestClient

    from adctox.api.main import app

    response = TestClient(app).post("/api/v1/propose", json={
        "comorbidity_profile": {
            "conditions": ["ckd_stage_4_5", "interstitial_lung_disease"],
        },
        "target_antigen": "HER2", "top_k": 6,
    })
    assert response.status_code == 200, response.text[:300]
    payload = response.json()
    head = payload["candidates"][0]
    if not (head.get("group_size") or 0) > 1:
        pytest.skip("this query no longer produces a tied head group")

    harness = r"""
const fs = require("fs"), vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8")
  .match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const ctx = { document: { getElementById: () => null, querySelectorAll: () => [],
  addEventListener() {} }, window: {},
  fetch: () => Promise.resolve({ json: () => ({}) }), console };
vm.createContext(ctx);
try { vm.runInContext(js, ctx); } catch (e) {}
const d = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const note = ctx.headNote(d);
const inSet = ctx.headSetSize(d);
const opts0 = { oneSet: inSet > 0, total: inSet };
if (!note) { console.error("no head note for a tied head group"); process.exit(1); }
if (!/unranked set/.test(ctx.card(d.candidates[0], 0, opts0))) {
  console.error("a card in a one-set head still prints a rank");
  process.exit(1);
}
// Whitespace-normalised: the markup wraps and indents, so a literal newline in a phrase
// makes the assertion about the template's line breaks rather than about its words.
const flat = note.replace(/\s+/g, " ");
for (const want of ["not ranked", "as a set", String(d.candidates[0].group_size)]) {
  if (!flat.includes(want)) {
    console.error("head note omits " + JSON.stringify(want) + ": " + note);
    process.exit(1);
  }
}
const all = note + d.candidates.map((c, i) =>
  ctx.card(c, i, { oneSet: i < inSet, total: inSet })).join("");
if (/undefined|NaN/.test(all)) { console.error("undefined/NaN in markup"); process.exit(1); }
// The false sentence: a singleton group told it is indistinguishable from its group.
for (const c of d.candidates) {
  const html = ctx.card(c, 0, { oneSet: false });
  if (c.group_size === 1 && /not distinguishable from its group/.test(html)) {
    console.error("a group of one is told it is indistinguishable from its group");
    process.exit(1);
  }
}
console.log("ok");
"""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "head.js"
        data = Path(tmp) / "payload.json"
        script.write_text(harness, encoding="utf-8")
        data.write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run(
            ["node", str(script),
             str(Path(__file__).resolve().parents[1] / "web" / "index.html"),
             str(data)],
            capture_output=True, text=True,
        )
    assert result.returncode == 0, result.stderr[-800:] + result.stdout[-400:]


def test_the_whole_result_block_renders_a_live_response() -> None:
    """The assembly, not just its pieces.

    `axisRow` and `card` were the only testable units, because the rest of the result block
    was a template literal inside the submit handler. So the assembly, the ranking-evidence
    rows and the why-not block were covered by nothing, and a renamed field in any of them
    would have reached the page as `undefined`. `renderResult` is extracted for this.

    Run over several profiles, because the blocks are conditional: a profile with no
    comorbidity produces no at-risk axis, a dermatologic one against a skin-expressed target
    is the only case that fires the target-expression flag, and the why-not block exists only
    when a constraint actually excluded the lowest-risk candidate.
    """
    import json
    import tempfile

    if not shutil.which("node"):
        pytest.skip("node not available")

    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    queries = [
        ({"conditions": []}, "TACSTD2"),
        ({"conditions": ["ckd_stage_4_5", "interstitial_lung_disease"]}, "ERBB2"),
        ({"conditions": ["severe_psoriasis", "prior_sjs_ten"]}, "NECTIN4"),
        ({"conditions": ["cirrhosis", "ckd_stage_4_5", "heart_failure", "dry_eye"]},
         "CD33"),
    ]
    payloads = []
    for profile, target in queries:
        r = client.post("/api/v1/propose", json={
            "comorbidity_profile": profile, "target_antigen": target, "top_k": 4,
        })
        if r.status_code == 503:
            pytest.skip("posterior artefact absent")
        assert r.status_code == 200, r.text[:300]
        payloads.append(r.json())

    harness = r"""
const fs = require("fs"), vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8")
  .match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const ctx = { document: { getElementById: () => null, querySelectorAll: () => [],
  addEventListener() {} }, window: {},
  fetch: () => Promise.resolve({ json: () => ({}) }), console };
vm.createContext(ctx);
try { vm.runInContext(js, ctx); } catch (e) {}
const payloads = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
let rendered = 0;
for (const d of payloads) {
  const html = ctx.renderResult(d);
  if (!html || html.length < 400) {
    console.error("result block is empty or trivial"); process.exit(1);
  }
  // `undefined` and `NaN` reaching the markup is a renamed or absent field.
  const bad = html.match(/undefined|NaN/g);
  if (bad) { console.error("markup contains " + bad.join(", ")); process.exit(1); }
  // The blocks that must always be there.
  for (const want of ["passed the constraints", "organ_axis" in d ? "" : "axis",
                      "Pareto front"]) {
    if (want && !html.includes(want)) {
      console.error("missing " + JSON.stringify(want)); process.exit(1);
    }
  }
  rendered++;
}
if (rendered !== payloads.length) { console.error("not all rendered"); process.exit(1); }
console.log("rendered " + rendered);
"""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "whole.js"
        data = Path(tmp) / "payloads.json"
        script.write_text(harness, encoding="utf-8")
        data.write_text(json.dumps(payloads), encoding="utf-8")
        result = subprocess.run(
            ["node", str(script),
             str(Path(__file__).resolve().parents[1] / "web" / "index.html"),
             str(data)],
            capture_output=True, text=True,
        )
    assert result.returncode == 0, result.stderr[-900:] + result.stdout[-300:]


def test_a_laboratory_dominated_axis_says_so_on_the_row() -> None:
    """The hepatic axis is mostly laboratory abnormalities, and the number means something
    different because of it.

    MedDRA files laboratory findings under `Investigations` rather than under the organ, so
    the taxonomy redistributes them -- "alanine aminotransferase increased" to hepatic. The
    hepatic axis comes out **64% laboratory rows in the registry and 84% in the literature**,
    against 0-8% for most axes. So "hepatic risk 0.18" is largely transaminase elevation
    rather than hepatotoxicity as a clinical event, and a patient who declares cirrhosis is
    up-weighting a laboratory finding.

    That changes what the figure means rather than whether it is right, which is why it is a
    label on the axis rather than a limitation in a document. The axis has to carry it even
    when the composition artefact is absent, in which case no claim is made at all --
    "we have not measured this" and "this axis is not laboratory-dominated" must not render
    the same way.
    """
    import json
    import tempfile

    if not shutil.which("node"):
        pytest.skip("node not available")

    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    ont = client.get("/api/v1/ontology").json()
    hepatic = next(a for a in ont["organ_axes"] if a["id"] == "hepatic")
    if "mostly_laboratory" not in hepatic:
        pytest.skip("run `make axis-composition`")
    assert hepatic["mostly_laboratory"] is True, hepatic
    assert hepatic["lab_share_registry"] > 0.5, hepatic
    # And it is the exception, not the rule.
    dominated = [a["id"] for a in ont["organ_axes"] if a.get("mostly_laboratory")]
    assert dominated == ["hepatic"], dominated

    r = client.post("/api/v1/assess", json={
        "design": {
            "target_antigen": "ERBB2", "payload": "DXd", "linker": "GGFG",
            "conjugation": "interchain_cysteine", "dar": 8.0,
            "isotype": "IgG1", "masking": "none",
        },
        "comorbidity_profile": {"conditions": ["cirrhosis"]},
    })
    assert r.status_code == 200, r.text[:200]
    rows = r.json()["organ_risks"]

    harness = r"""
const fs = require("fs"), vm = require("vm");
const js = fs.readFileSync(process.argv[2], "utf8")
  .match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const ctx = { document: { getElementById: () => null, querySelectorAll: () => [],
  addEventListener() {} }, window: {},
  fetch: () => Promise.resolve({ json: () => ({}) }), console };
vm.createContext(ctx);
try { vm.runInContext(js, ctx); } catch (e) {}
const payload = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
// Before boot, ONT is null: the row must still render rather than throw.
const before = ctx.axisRow(payload.rows.find(r => r.organ_axis === "hepatic"));
if (/undefined|NaN/.test(before)) { console.error("pre-boot row is broken"); process.exit(1); }
if (/mostly laboratory/.test(before)) {
  console.error("claimed a composition the page had not been given"); process.exit(1);
}
ctx.ONT = payload.ont;
const hep = ctx.axisRow(payload.rows.find(r => r.organ_axis === "hepatic"));
if (!/mostly laboratory/.test(hep)) { console.error("hepatic row omits the label"); process.exit(1); }
const gi = ctx.axisRow(payload.rows.find(r => r.organ_axis === "gastrointestinal"));
if (/mostly laboratory/.test(gi)) { console.error("labelled an axis that is 2% laboratory"); process.exit(1); }
console.log("ok");
"""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "lab.js"
        data = Path(tmp) / "payload.json"
        script.write_text(harness, encoding="utf-8")
        data.write_text(json.dumps({"ont": ont, "rows": rows}), encoding="utf-8")
        result = subprocess.run(
            ["node", str(script),
             str(Path(__file__).resolve().parents[1] / "web" / "index.html"),
             str(data)],
            capture_output=True, text=True,
        )
    assert result.returncode == 0, result.stderr[-900:] + result.stdout[-300:]


PAGE = Path(__file__).resolve().parents[1] / "web" / "index.html"
BOOT_FAILURE = Path(__file__).resolve().parent / "js" / "boot_failure.js"


def _page_css() -> str:
    import re

    css = re.search(r"<style>(.*?)</style>", PAGE.read_text(encoding="utf-8"), re.S).group(1)
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _css_vars(block: str) -> dict[str, str]:
    import re

    found = re.findall(r"(--[\w-]+)\s*:\s*#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", block)
    return {k: "#" + (v if len(v) == 6 else "".join(c * 2 for c in v)) for k, v in found}


def _luminance(hexcolour: str) -> float:
    channels = [int(hexcolour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_page_css_has_no_declarations_outside_a_rule_and_no_undefined_variables() -> None:
    """A bare `--x:` between rules swallows the next rule, and `var(--muted)` resolves to nothing."""
    import re

    css = _page_css()
    depth, top = 0, []
    for ch in css:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            top.append(ch)
    assert not re.search(r"--[\w-]+\s*:", "".join(top)), "custom property declared outside a rule"
    defined = set(re.findall(r"(--[\w-]+)\s*:", css))
    used = set(re.findall(r"var\((--[\w-]+)", css))
    assert not used - defined, f"undefined custom properties: {sorted(used - defined)}"
    root = re.search(r":root\{(.*?)\}", css, re.S).group(1)
    for name in ("--src-model", "--src-rule", "--src-elicited_prior"):
        assert name in root


def test_band_text_colours_meet_aa_contrast_at_11px() -> None:
    import re

    css = _page_css()
    light = _css_vars(re.search(r":root\{(.*?)\}", css, re.S).group(1))
    dark = {**light, **_css_vars(re.search(
        r"prefers-color-scheme:dark\)\{\s*:root:not\(\[data-theme=light\]\)\{(.*?)\}", css, re.S
    ).group(1))}
    for theme in (light, dark):
        for name in ("--moderate", "--none", "--ink-dim", "--low", "--high"):
            for surface in ("--bg", "--panel"):
                ratio = _contrast(theme[name], theme[surface])
                assert ratio >= 4.5, f"{name} on {surface} is {ratio:.2f}:1"


def test_page_accessibility_hooks_are_present() -> None:
    html = PAGE.read_text(encoding="utf-8")
    assert 'id="status" role="status" aria-live="polite"' in html
    assert 'role="group" aria-labelledby="chips-label"' in html
    assert 'aria-expanded="false"' in html and "aria-controls=" in html
    assert 'setAttribute("aria-expanded"' in html
    assert "@media(max-width:600px)" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_failed_boot_says_so_instead_of_loading_forever() -> None:
    result = subprocess.run(
        [shutil.which("node"), str(BOOT_FAILURE), str(PAGE)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-600:]


ADCTOX_CSS = Path(__file__).resolve().parents[1] / "ml" / "web" / "app.css"


def test_lab_groups_go_to_one_column_when_the_step_is_narrow() -> None:
    """Between 900 and 1280 px two columns leave a lab name 29 px: the container rule must come after the two-column one."""
    css = ADCTOX_CSS.read_text(encoding="utf-8")
    assert css.index(".groups { columns: 2;") < css.index("@container (max-width: 760px) { .groups { columns: 1; } }")
