"""install.sh runs from whatever folder the user piped curl in: its Python must not import from that folder."""
from __future__ import annotations
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "install.sh"
bash = shutil.which("bash")
pytestmark = pytest.mark.skipif(not bash or sys.platform == "win32", reason="needs POSIX bash")


def test_every_python_invocation_is_isolated():
    calls = re.findall(r'(?:"\$1"|"\$task_python"|"\$task_env/bin/python")( +(?!\]\]|#)\S+)', SCRIPT.read_text())
    assert len(calls) >= 8 and all(flag == " -I" for flag in calls)


def test_python_ok_ignores_modules_in_the_current_folder(tmp_path):
    hostile = tmp_path / "cwd"; hostile.mkdir()
    for name in ("venv", "ensurepip", "sys"):
        (hostile / f"{name}.py").write_text(f"open({str(tmp_path / 'ran')!r}, 'w').close()\n")
    function = re.search(r"^python_ok\(\) \{.*?^\}", SCRIPT.read_text(), re.S | re.M).group(0)
    run = subprocess.run([bash, "-c", function + f'\npython_ok {sys.executable}'], cwd=hostile, capture_output=True, text=True)
    assert not (tmp_path / "ran").exists()
