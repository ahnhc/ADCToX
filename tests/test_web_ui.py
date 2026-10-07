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
