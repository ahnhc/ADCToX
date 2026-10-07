"""Every artefact must record what produced it.

None of them did. The plan's reproducibility section claims the lineage is a hash chain,
and the artefacts were bare results: no revision, no snapshot date, no input hashes. The
cost was paid repeatedly while fixing this project -- after changing the dataset builder
mid-session, deciding whether a running fit's output was still valid meant reasoning about
which modules a process had already imported, when the file should simply have said.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adctox.provenance import stamp, write_json

ART = Path(__file__).resolve().parents[1] / "artifacts"

# Exemptions for artefacts predating provenance. Now empty: every artefact in the tree has
# been regenerated through the helper. It is kept as an explicit empty set rather than
# deleted, because the test below asserts the list only shrinks, and an empty list makes
# "every artefact carries provenance" an unconditional invariant.
PRE_STAMP: set[str] = set()   # all artefacts are stamped; keep it that way


def test_stamp_reports_revision_and_dirtiness():
    s = stamp()
    assert s["revision"] and len(s["revision"]) == 40, s["revision"]
    assert s["dirty"] in (True, False)
    assert s["written_utc"].endswith("+00:00")


def test_stamp_hashes_the_inputs_it_is_given(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hello")
    s = stamp({"thing": f})
    assert s["inputs"]["thing"].startswith("sha256:")
    f.write_text("goodbye")
    assert stamp({"thing": f})["inputs"]["thing"] != s["inputs"]["thing"], (
        "the hash did not change when the input did"
    )


def test_a_missing_input_is_recorded_as_null_not_omitted(tmp_path):
    """Silence and absence must be distinguishable, as everywhere else here."""
    s = stamp({"gone": tmp_path / "nope"})
    assert "gone" in s["inputs"] and s["inputs"]["gone"] is None


def test_write_json_embeds_rather_than_sidecars(tmp_path):
    out = tmp_path / "a.json"
    write_json(out, {"value": 1}, {"self": out.parent})
    doc = json.loads(out.read_text())
    assert doc["value"] == 1
    assert doc["provenance"]["revision"]
    assert not list(tmp_path.glob("*.prov*")), "a sidecar was written"


@pytest.mark.skipif(not ART.exists(), reason="no artefacts built")
def test_artefacts_carry_provenance_and_the_exemption_list_only_shrinks():
    missing = set()
    for path in sorted(ART.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "provenance" not in doc:
            missing.add(path.name)
    unexpected = missing - PRE_STAMP
    assert not unexpected, (
        f"artefacts written without provenance: {sorted(unexpected)}. Route the write "
        "through adctox.provenance.write_json."
    )
    stale = PRE_STAMP - missing
    assert not stale, (
        f"these are now stamped and should be removed from PRE_STAMP: {sorted(stale)}"
    )
