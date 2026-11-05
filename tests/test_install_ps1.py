"""install.ps1 on a Windows host, in temp folders only (LOCALAPPDATA is never read by the functions under test)."""
from __future__ import annotations
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "install.ps1"
powershell = shutil.which("powershell.exe") if sys.platform == "win32" else None
pytestmark = pytest.mark.skipif(not powershell, reason="needs Windows PowerShell")


def run_ps(code, cwd):
    return subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", code], cwd=cwd, capture_output=True, text=True, timeout=60)


def install_tree_source():
    return re.search(r"^function Install-Tree.*?^\}", SCRIPT.read_text(encoding="utf-8"), re.S | re.M).group(0)


def make_app(root, name, marker):
    folder = root / name
    (folder / "python").mkdir(parents=True)
    (folder / "marker.txt").write_text(marker)
    shutil.copy(Path(r"C:\Windows\System32\ping.exe"), folder / "python" / "python.exe")
    for i in range(30):
        (folder / f"a{i:02d}.txt").write_text("x")
    return folder


def test_reinstall_while_the_app_runs_changes_nothing(tmp_path):
    old = make_app(tmp_path, "app", "old")
    new = make_app(tmp_path, "new", "new")
    running = subprocess.Popen([str(old / "python" / "python.exe"), "-n", "30", "127.0.0.1"], stdout=subprocess.DEVNULL)
    try:
        run = run_ps(install_tree_source() + f"\n$ErrorActionPreference='Stop'; Install-Tree '{new}' '{old}'", tmp_path)
    finally:
        running.kill(); running.wait()
    assert run.returncode != 0
    assert (old / "marker.txt").read_text() == "old" and len(list(old.glob("a*.txt"))) == 30
    assert (new / "marker.txt").exists() and [p.name for p in tmp_path.iterdir() if ".old-" in p.name] == []


def test_reinstall_replaces_the_app_and_removes_the_old_copy(tmp_path):
    old = make_app(tmp_path, "app", "old")
    new = make_app(tmp_path, "new", "new")
    run = run_ps(install_tree_source() + f"\n$ErrorActionPreference='Stop'; Install-Tree '{new}' '{old}'", tmp_path)
    assert run.returncode == 0, run.stderr
    assert (old / "marker.txt").read_text() == "new" and not new.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["app"]


def test_launchers_work_from_a_non_ascii_account_folder(tmp_path):
    block = re.search(r"^foreach \(\$c in @\(@\('adctox'.*?^\}", SCRIPT.read_text(encoding="utf-8"), re.S | re.M).group(0)
    root = tmp_path / "한글계정" / "adctox"
    (root / "bin").mkdir(parents=True); (root / "app").mkdir()
    (root / "app" / "ADCTOX.bat").write_text("@echo off\r\necho got %*\r\n")
    script = tmp_path / "write.ps1"
    script.write_text(f"$Bin = '{root / 'bin'}'\n{block}\n", encoding="utf-8-sig")
    done = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-File", str(script)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    for name, flag in (("adctox", ""), ("adctox-web", "--web "), ("adctox-cli", "--cli ")):
        launcher = root / "bin" / f"{name}.cmd"
        launcher.read_bytes().decode("ascii")
        out = subprocess.run(["cmd.exe", "/c", str(launcher), "x"], capture_output=True, text=True, timeout=60)
        assert out.stdout.strip() == f"got {flag}x", out
