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


def test_interrupted_release_copy_is_not_taken_for_a_finished_one(tmp_path):
    lines = SCRIPT.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("task_release="))
    end = next(i for i in range(start, len(lines)) if lines[i] == "fi")
    fragment = "\n".join(lines[start:end + 1])
    prefix, work, shim = tmp_path / "prefix", tmp_path / "work", tmp_path / "shim"
    for folder in (prefix / "apps", work / "app", shim):
        folder.mkdir(parents=True)
    (work / "app" / "adc_recommender_full.py").write_text("print()\n")
    # the first mv into apps/ dies halfway, as a copy across file systems does on a full disk
    (shim / "mv").write_text(f'#!/bin/bash\nif [[ ! -e "{tmp_path}/died" ]]; then touch "{tmp_path}/died"; mkdir -p "$2"; touch "$2/partial"; exit 1; fi\nexec /bin/mv "$@"\n')
    (shim / "mv").chmod(0o755)
    script = f'set -e\ntask_prefix={prefix}; task_tmp={work}; task_version=1.0; task_fields=(x y 0123456789abcdef)\n{fragment}\n'
    env = {"PATH": f"{shim}:/usr/bin:/bin"}
    assert subprocess.run([bash, "-c", script], env=env, capture_output=True).returncode != 0
    assert not (prefix / "apps" / "1.0-0123456789ab").exists()
    assert subprocess.run([bash, "-c", script], env=env, capture_output=True).returncode == 0
    assert (prefix / "apps" / "1.0-0123456789ab" / "adc_recommender_full.py").is_file()
