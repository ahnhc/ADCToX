"""The saved review must preserve unknown inputs and conditional restrictions."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node unavailable")
def test_review_states_and_export():
    script = Path(__file__).parent / "js" / "review.js"
    subprocess.run([shutil.which("node"), str(script)], check=True, timeout=30)
