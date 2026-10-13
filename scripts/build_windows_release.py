"""Windows package: unzip and double-click ADCTOX.bat. No installer, no admin rights, no Python on the PC.

    /data/hyeongchanahn/envs/adctox/bin/python -I scripts/build_windows_release.py      (after scripts/build_ubuntu_release.py)

Built on Linux from the same app archive the Ubuntu release uses, so app and model updates work the same way on both:
  ADCTOX/python/          official embeddable CPython 3.12.10 for Windows (pinned SHA256) with the app's packages for
                          win_amd64 unpacked into Lib/site-packages: torch (CPU) at the app manifest's torch_version and
                          releases/requirements-cpu.txt with their dependencies, as binary wheels only
  ADCTOX/apps/<release>/  the three files of adctox-ubuntu.tar.gz (adctox --update-app adds newer releases here)
  ADCTOX/app.txt          which release starts
  ADCTOX/launcher.py      starts that release; on the first start it downloads the models (about 1 GB) into
                          %LOCALAPPDATA%\\adctox\\models with the model updater
  ADCTOX/ADCTOX.bat       double-click entry point
Outputs dist/releases/windows/ADCTOX-windows.zip and windows.json (size, SHA256, release URL).
Downloads are cached in ADCTOX_WIN_CACHE (default /data/hyeongchanahn/adctox/raw/win_build on the lab server, else ~/.cache/adctox-win).
"""
import argparse, hashlib, io, json, os, shutil, subprocess, sys, tarfile, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from adc_version import APP_VERSION, REPOSITORY
CACHE = Path(os.environ.get("ADCTOX_WIN_CACHE") or ("/data/hyeongchanahn/adctox/raw/win_build" if Path("/data/hyeongchanahn").is_dir() else Path.home() / ".cache/adctox-win"))
EMBED = ("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3")

PTH = "python312.zip\r\n.\r\nLib\\site-packages\r\nimport site\r\n"
BAT = ('@echo off\r\n'
       'chcp 65001 >nul\r\n'
       'set PYTHONUTF8=1\r\n'
       'title ADCTOX\r\n'
       '"%~dp0python\\python.exe" -I "%~dp0launcher.py" %*\r\n'
       'if errorlevel 1 pause\r\n')
LAUNCHER = '''"""Starts the ADCTOX release named in app.txt with this folder's Python; downloads the models on the first start."""
import os, runpy, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def vc_runtime_missing():
    """torch needs the Microsoft Visual C++ runtime (msvcp140.dll); found in System32 when installed, or next to python.exe."""
    import ctypes
    try:
        ctypes.WinDLL("msvcp140.dll"); return False
    except OSError:
        return True


def main():
    if os.name == "nt" and vc_runtime_missing():
        print("ADCTOX needs the Microsoft Visual C++ Redistributable (x64), which this PC does not have yet.")
        print("Install it from https://aka.ms/vs/17/release/vc_redist.x64.exe and start ADCTOX again.")
        return 1
    app = HERE / "apps" / (HERE / "app.txt").read_text().strip() / "adc_recommender_full.py"
    home = Path(os.environ.get("ADC_MODEL_HOME") or Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "adctox" / "models")
    if not (home / "current.txt").exists() and len(sys.argv) == 1:
        print("ADCTOX: first start. Downloading the models (about 1 GB, once) ...", flush=True)
        if subprocess.call([sys.executable, "-I", str(app), "--update-models"]):
            print("The model download did not finish. Check the internet connection and start ADCTOX again.")
            return 1
    sys.argv[0] = str(app)
    runpy.run_path(str(app), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
README = """ADCTOX {version} (Windows)

실행
  압축을 푼 ADCTOX 폴더의 ADCTOX.bat를 더블클릭합니다.
  처음 실행할 때 모델 파일(약 1 GB)을 한 번 내려받습니다. 저장 위치: %LOCALAPPDATA%\\adctox\\models
  Windows Terminal이 있으면 그 창에서 열립니다.

업데이트
  모델: 질환 선택 화면에서 U
  앱: 새 버전이 있으면 질환 선택 화면 아래에 표시됩니다. 명령 프롬프트에서
      ADCTOX.bat --update-app
  패키지 구성이 바뀌는 버전은 새 zip을 받아 다시 풀어야 합니다(안내가 나옵니다).

요구 사항
  64비트 Windows 10 또는 11, 인터넷(첫 실행과 업데이트 때만)
  torch를 불러오지 못한다는 오류가 나오면 Microsoft Visual C++ 재배포 가능 패키지(x64)를 설치합니다:
  https://aka.ms/vs/17/release/vc_redist.x64.exe

이 폴더는 어디에 두어도 되며, 시스템에 아무것도 설치하지 않습니다. 지우려면 폴더와 %LOCALAPPDATA%\\adctox를 삭제합니다.
"""


def fetch(url, sha, name):
    CACHE.mkdir(parents=True, exist_ok=True); path = CACHE / name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        with urllib.request.urlopen(url) as r: path.write_bytes(r.read())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, f"checksum mismatch: {name}"
    return path


def wheels(torch_version, requirements):
    """binary win_amd64 wheels for torch and the requirements with their dependencies. uv resolves for Windows (pip download
    applies the build machine's platform markers and would pull Linux-only CUDA packages); pip then fetches each pinned wheel."""
    out = CACHE / f"wheels-{torch_version}"; out.mkdir(parents=True, exist_ok=True)
    req = out / "resolve-in.txt"; req.write_text(f"torch=={torch_version}\n" + requirements.read_text())
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    pins = subprocess.run([uv, "pip", "compile", "--quiet", "--python-platform", "x86_64-pc-windows-msvc", "--python-version", "3.12",
                           "--no-header", "--no-annotate", str(req)], check=True, capture_output=True, text=True).stdout.split()
    (out / "windows-lock.txt").write_text("\n".join(pins) + "\n")
    pip = [sys.executable, "-m", "pip"] if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode == 0 else [shutil.which("python3") or "python3", "-m", "pip"]
    subprocess.run([*pip, "download", "--quiet", "--disable-pip-version-check", "--no-deps", "--only-binary=:all:", "--platform", "win_amd64",
                    "--python-version", "3.12", "--implementation", "cp", "-d", str(out), *pins], check=True)
    names = {p.split("==")[0].lower().replace("-", "_") for p in pins}
    return sorted(w for w in out.glob("*.whl") if w.name.split("-")[0].lower() in names)


def unpack_wheel(wheel, site, prefix=None):
    with zipfile.ZipFile(wheel) as z:
        for info in z.infolist():
            parts = info.filename.split("/")
            if parts[0].endswith(".data"):                       # name-x.data/{purelib,platlib}/... go to site-packages; data/ to the Python folder
                if len(parts) >= 3 and parts[1] == "data" and prefix is not None and parts[2] != "Scripts": target = prefix.joinpath(*parts[2:])
                elif len(parts) < 3 or parts[1] not in ("purelib", "platlib"): continue
                else: target = site.joinpath(*parts[2:])
            else:
                target = site.joinpath(*parts)
            if info.is_dir(): continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst: shutil.copyfileobj(src, dst)


BUILD_PS1 = r"""# ADCTOX Windows package, built on Windows. Run build.bat (or: powershell -ExecutionPolicy Bypass -File build_windows.ps1).
# Needs internet. Writes ADCTOX\ next to this script and ADCTOX-windows.zip. Nothing is installed on the PC itself.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Embed = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$EmbedSha = "{embed_sha}"
$Release = "{release}"
$Torch = "{torch}"

if (Test-Path ADCTOX) {{ Write-Host "ADCTOX folder already exists; delete it first to rebuild."; exit 1 }}
New-Item -ItemType Directory ADCTOX\python | Out-Null

Write-Host "1/5 Python 3.12.10 (embeddable, from python.org)"
Invoke-WebRequest $Embed -OutFile python-embed.zip -UseBasicParsing
if ((Get-FileHash python-embed.zip -Algorithm SHA256).Hash.ToLower() -ne $EmbedSha) {{ throw "python-embed.zip checksum mismatch" }}
Expand-Archive python-embed.zip -DestinationPath ADCTOX\python
Set-Content ADCTOX\python\python312._pth "python312.zip`r`n.`r`nLib\site-packages`r`nimport site" -Encoding ascii -NoNewline

Write-Host "2/5 pip"
Invoke-WebRequest https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py -UseBasicParsing
& ADCTOX\python\python.exe get-pip.py --no-warn-script-location --quiet
if ($LASTEXITCODE -ne 0) {{ throw "pip setup failed" }}

Write-Host "3/5 PyTorch $Torch (CPU) and the app's packages (several minutes)"
& ADCTOX\python\python.exe -m pip install --no-warn-script-location --disable-pip-version-check "torch==$Torch" --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) {{ throw "torch install failed" }}
& ADCTOX\python\python.exe -m pip install --no-warn-script-location --disable-pip-version-check -r app\requirements-cpu.txt
if ($LASTEXITCODE -ne 0) {{ throw "package install failed" }}

Write-Host "4/5 App files"
New-Item -ItemType Directory "ADCTOX\apps\$Release" | Out-Null
Copy-Item app\* "ADCTOX\apps\$Release\"
Set-Content ADCTOX\app.txt $Release -Encoding ascii
Copy-Item launcher.py, ADCTOX.bat, README.txt ADCTOX\

Write-Host "5/5 Check and zip"
& ADCTOX\python\python.exe -I ADCTOX\launcher.py --version
if ($LASTEXITCODE -ne 0) {{ throw "the packaged app does not start" }}
& ADCTOX\python\python.exe -c "import torch, transformers, sentence_transformers; print('torch', torch.__version__)"
if ($LASTEXITCODE -ne 0) {{ throw "packages do not import (install the Microsoft Visual C++ Redistributable x64 and run again)" }}
Remove-Item python-embed.zip, get-pip.py
if (Test-Path ADCTOX-windows.zip) {{ Remove-Item ADCTOX-windows.zip }}
Compress-Archive ADCTOX ADCTOX-windows.zip
Write-Host "Done: ADCTOX\ADCTOX.bat (run it) and ADCTOX-windows.zip (to share)."
"""
BUILD_BAT = '@echo off\r\ncd /d "%~dp0"\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"\r\npause\r\n'
KIT_README = r"""ADCTOX {version} Windows 빌드 키트

준비: 64비트 Windows 10/11, 인터넷. Python을 미리 설치할 필요는 없습니다.

1. 이 폴더를 압축 해제한 위치에 둡니다(경로에 한글이 없으면 더 안전합니다).
2. build.bat를 더블클릭합니다. 5단계로 진행되며 수 분 걸립니다.
   1/5 python.org의 Python 3.12.10 embeddable (SHA256 확인)
   2/5 pip
   3/5 PyTorch {torch} CPU와 앱 패키지(transformers, sentence-transformers 등)
   4/5 앱 파일 배치
   5/5 실행 확인과 ADCTOX-windows.zip 생성
3. 끝나면 ADCTOX\ADCTOX.bat로 실행합니다. 첫 실행 때 모델(약 1 GB)을 받습니다.
   다른 PC에는 ADCTOX-windows.zip만 주면 됩니다.

다시 빌드하려면 ADCTOX 폴더를 지우고 build.bat를 다시 실행합니다.
5/5에서 패키지를 불러오지 못하면 Microsoft Visual C++ 재배포 가능 패키지(x64)를 설치한 뒤 다시 실행합니다:
https://aka.ms/vs/17/release/vc_redist.x64.exe

파일
  build.bat, build_windows.ps1  빌드
  app\                          앱 파일(Ubuntu 릴리스와 같은 3개 파일)
  launcher.py, ADCTOX.bat, README.txt  패키지에 들어갈 실행 파일과 안내
"""


def kit(a, manifest, archive):
    """a folder (and zip) to build the same package on a Windows PC with pip, for when the Linux-built one does not run."""
    out = a.out.parent / "windows-build-kit"; shutil.rmtree(out, ignore_errors=True); (out / "app").mkdir(parents=True)
    with tarfile.open(archive) as t: t.extractall(out / "app", filter="data")
    release = f"{APP_VERSION}-{manifest['sha256'][:12]}"
    (out / "build_windows.ps1").write_text(BUILD_PS1.format(embed_sha=EMBED[1], release=release, torch=manifest["torch_version"]).replace("\n", "\r\n"), encoding="utf-8-sig")
    (out / "build.bat").write_bytes(BUILD_BAT.encode())
    (out / "launcher.py").write_text(LAUNCHER); (out / "ADCTOX.bat").write_bytes(BAT.encode())
    (out / "README.txt").write_text(README.format(version=APP_VERSION).replace("\n", "\r\n"), encoding="utf-8-sig")
    (out / "BUILD_README.txt").write_text(KIT_README.format(version=APP_VERSION, torch=manifest["torch_version"]).replace("\n", "\r\n"), encoding="utf-8-sig")
    z = out.parent / "ADCTOX-windows-build-kit.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.rglob("*")):
            if p.is_file(): zf.write(p, ("ADCTOX-windows-build-kit/" + p.relative_to(out).as_posix()))
    print(f"Windows build kit: {z} ({z.stat().st_size / 1024:.0f} KiB)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app", type=Path, default=ROOT / "dist/releases/app"); ap.add_argument("--out", type=Path, default=ROOT / "dist/releases/windows")
    # Microsoft's terms let holders of a Visual Studio licence (Community included) ship these DLLs with their program; off by
    # default, then the launcher points to the official installer when the PC lacks the runtime.
    ap.add_argument("--bundle-vc-runtime", action="store_true")
    ap.add_argument("--kit-only", action="store_true", help="only write the Windows build kit (build on a Windows PC)")
    a = ap.parse_args()
    manifest = json.loads((a.app / "app.json").read_text()); archive = a.app / "adctox-ubuntu.tar.gz"
    assert manifest["app_version"] == APP_VERSION and hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["sha256"], "build the app first (scripts/build_ubuntu_release.py)"
    kit(a, manifest, archive)
    if a.kit_only: return
    stage = a.out / "ADCTOX"; shutil.rmtree(a.out, ignore_errors=True); stage.mkdir(parents=True)
    with zipfile.ZipFile(fetch(EMBED[0], EMBED[1], "python-3.12.10-embed-amd64.zip")) as z: z.extractall(stage / "python")
    (stage / "python/python312._pth").write_text(PTH)
    site = stage / "python/Lib/site-packages"; site.mkdir(parents=True)
    with tarfile.open(archive) as t:
        req = t.extractfile("requirements-cpu.txt").read(); release = stage / "apps" / f"{APP_VERSION}-{manifest['sha256'][:12]}"
        release.mkdir(parents=True); t.extractall(release, filter="data")
    (CACHE / "requirements-cpu.txt").write_bytes(req)
    found = wheels(manifest["torch_version"], CACHE / "requirements-cpu.txt")
    for w in found: unpack_wheel(w, site)
    if a.bundle_vc_runtime:
        subprocess.run([shutil.which("python3") or "python3", "-m", "pip", "download", "--quiet", "--no-deps", "--only-binary=:all:", "--platform", "win_amd64",
                        "--python-version", "3.12", "--implementation", "cp", "-d", str(CACHE / "msvc"), "msvc-runtime==14.44.35112"], check=True)
        for w in (CACHE / "msvc").glob("msvc_runtime-14.44.35112-*.whl"): unpack_wheel(w, site, prefix=stage / "python"); found.append(w)
    (stage / "app.txt").write_text(release.name + "\n"); (stage / "launcher.py").write_text(LAUNCHER)
    (stage / "ADCTOX.bat").write_bytes(BAT.encode()); (stage / "README.txt").write_text(README.format(version=APP_VERSION).replace("\n", "\r\n"), encoding="utf-8-sig")
    out = a.out / "ADCTOX-windows.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts: z.write(p, p.relative_to(a.out).as_posix())
    tag = "v" + APP_VERSION + (".0" if APP_VERSION.count(".") == 1 else "")
    info = {"schema_version": 1, "app_version": APP_VERSION, "url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{out.name}",
            "size": out.stat().st_size, "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "python": "3.12.10 embeddable",
            "torch_version": manifest["torch_version"], "wheels": [w.name for w in found]}
    (a.out / "windows.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"Windows {APP_VERSION}: {out.stat().st_size / 1024**2:.0f} MiB, {len(found)} wheels; models download on first start.")


if __name__ == "__main__":
    main()
