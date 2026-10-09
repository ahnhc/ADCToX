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
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
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
const opts0 = { oneSet: ctx.headIsOneSet(d), total: d.candidates.length };
if (!note) { console.error("no head note for a tied head group"); process.exit(1); }
if (!/unranked set/.test(ctx.card(d.candidates[0], 0, opts0))) {
  console.error("a card in a one-set head still prints a rank");
  process.exit(1);
}
for (const want of ["are not ranked", "as a set", String(d.candidates[0].group_size)]) {
  if (!note.includes(want)) {
    console.error("head note omits " + JSON.stringify(want) + ": " + note);
    process.exit(1);
  }
}
const opts = { oneSet: ctx.headIsOneSet(d), total: d.candidates.length };
const all = note + d.candidates.map((c, i) => ctx.card(c, i, opts)).join("");
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
