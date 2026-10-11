"""Build dist/ADC_Recommender_Windows.zip: unzip on any 64-bit Windows 10/11 PC and double-click; no Python install.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_windows.py           light version (spelling match, no models)
    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_windows.py --full    dist/ADC_full_build_on_windows.zip

--full: the server version with its language models, as a folder. Unzip on Windows and run build_full.bat once (needs
Python 3.10-3.14 and internet): it installs CPU PyTorch, transformers, sentence-transformers and PyInstaller in a private
venv, builds the program as a one-folder app, adds a windowless launcher that opens it in Windows Terminal, and downloads
BioLORD-2023 and SapBERT at pinned revisions (ml/win/make_folder.py). The result folder runs without Python or internet.

Inside: the official embeddable CPython 3.12.10 for Windows (python.org; runs from its folder, writes nothing to the
system), the Windows wheel of numpy unpacked into it, dist/adc_recommender.py (ml/build_portable.py; its menus are drawn by
ml/term.py with ANSI codes, so no curses is needed), and a launcher. Downloads are cached in /data/hyeongchanahn/adctox/raw/win_build and checked against the hashes below.
"""
import hashlib, pathlib, shutil, subprocess, sys, urllib.request, zipfile

R = pathlib.Path("/home/hyeongchanahn/CONI/adctox"); C = pathlib.Path("/data/hyeongchanahn/adctox/raw/win_build")
EMBED = ("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3")
WHEELS = ["numpy-2.5.4-cp312-cp312-win_amd64.whl"]          # menus are drawn by ml/term.py on Windows; no curses needed
OUT = R / "dist/ADC_Recommender_Windows"

BAT = '@echo off\r\nchcp 65001 >nul\r\nset PYTHONUTF8=1\r\nset PYTHONIOENCODING=utf-8\r\ncd /d "%~dp0"\r\n"%~dp0python\\python.exe" "%~dp0adc_recommender.py" {args}\r\npause\r\n'
# Run once on a Windows PC that has Python 3.10+: makes dist\ADC_Recommender.exe, which then runs on any 64-bit Windows
# without Python. A private venv keeps the PC's own Python untouched.
EXE_BAT = (
    '@echo off\r\n'
    'cd /d "%~dp0"\r\n'
    'echo Building ADC_Recommender.exe (needs internet once for PyInstaller and numpy) ...\r\n'
    'py -3 -m venv .buildenv 2>nul || python -m venv .buildenv\r\n'
    'if errorlevel 1 (echo Python 3.10+ is needed to build. & pause & exit /b 1)\r\n'
    '".buildenv\\Scripts\\python.exe" -m pip install --quiet --upgrade pip pyinstaller numpy\r\n'
    '".buildenv\\Scripts\\pyinstaller.exe" --onefile --console --name ADC_Recommender --noconfirm --clean adc_recommender.py\r\n'
    'if errorlevel 1 (echo Build failed. & pause & exit /b 1)\r\n'
    'echo.\r\n'
    'echo Done: %~dp0dist\\ADC_Recommender.exe  (copy this one file to any Windows PC)\r\n'
    'pause\r\n')

README = """ADC 추천 프로그램 (Windows)

실행
  1. 이 폴더를 압축 해제합니다 (압축 파일 안에서 바로 실행하지 마세요).
  2. "ADC Recommender.bat" 을 더블클릭합니다.
     ↑↓ 이동, SPACE 선택, PgDn 다음 단계, PgUp 이전 단계. 결과 표에서 ↑↓로 고르면 아래에 이유가 나옵니다.
  3. 표가 잘리면 창을 최대화하세요. Windows Terminal(Windows 11 기본)에서 가장 잘 보입니다.

  Python 설치가 필요 없습니다. python 폴더에 들어 있는 휴대용 Python(python.org 공식 배포)으로 실행되며
  시스템에 아무것도 설치하거나 바꾸지 않습니다.

이 프로그램은 FDA 허가사항(라벨)이 이 환자에 대해 말하는 내용을 정리해 ADC를 정렬합니다.
독성 발생 확률이 아니며, 실제 환자 결과로 검증되지 않았습니다. 처방 결정은 의료진이 합니다.

데이터: FDA 라벨(DailyMed, public domain), MONDO Disease Ontology (CC BY 4.0).
포함된 소프트웨어: CPython 3.12.10 (PSF License), numpy (BSD) - 각 라이선스 파일 포함.
"""


FULL_BAT = (
    '@echo off\r\n'
    'chcp 65001 >nul\r\n'
    'cd /d "%~dp0"\r\n'
    'echo Building the ADC_Recommender folder. Needs internet once (about 1.5 GB: PyTorch, libraries, models).\r\n'
    'set "PY="\r\n'
    'py -3.12 -c "1" >nul 2>nul && set "PY=py -3.12"\r\n'
    'if not defined PY (py -3 -c "1" >nul 2>nul && set "PY=py -3")\r\n'
    'if not defined PY set "PY=python"\r\n'
    '%PY% -m venv .buildenv\r\n'
    'if errorlevel 1 (echo Python 3.10-3.14 is needed to build. & pause & exit /b 1)\r\n'
    'set "VP=%~dp0.buildenv\\Scripts\\python.exe"\r\n'
    '"%VP%" -m pip install --upgrade pip\r\n'
    '"%VP%" -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu\r\n'
    'if errorlevel 1 (echo PyTorch install failed. & pause & exit /b 1)\r\n'
    '"%VP%" -m pip install transformers==5.19.0 sentence-transformers==6.1.0 numpy pyinstaller\r\n'
    'if errorlevel 1 (echo Library install failed. & pause & exit /b 1)\r\n'
    '"%VP%" make_folder.py\r\n'
    'if errorlevel 1 (echo Build failed. & pause & exit /b 1)\r\n'
    'pause\r\n')

FULL_README = """ADC 추천 프로그램 (Windows, 전체 버전)

실행
  "ADC Recommender.exe" 를 더블클릭합니다. Windows Terminal이 있으면 그 창으로만 열립니다 (없으면 일반 콘솔 창).
  ↑↓ 이동, SPACE 선택, PgDn 다음 단계, PgUp 이전 단계. 결과 표에서 ↑↓로 고르면 아래에 이유가 나옵니다.
  목록에 없는 질환은 맨 아래 Other에 영어로 입력합니다. 언어 모델(BioLORD, SapBERT)이 MONDO 질환에 연결합니다.
  NVIDIA GPU용 PyTorch가 아니므로 CPU로 실행됩니다 (질환 몇 개는 CPU로 몇 초).

이 폴더 전체를 복사하거나 압축해서 옮기면 다른 PC에서도 그대로 실행됩니다. Python과 인터넷이 필요 없습니다.
app 폴더 안의 파일은 지우거나 옮기지 마세요.

이 프로그램은 FDA 허가사항(라벨)이 이 환자에 대해 말하는 내용을 정리해 ADC를 정렬합니다.
독성 발생 확률이 아니며, 실제 환자 결과로 검증되지 않았습니다. 처방 결정은 의료진이 합니다.

데이터와 모델: FDA 라벨(DailyMed, public domain); MONDO Disease Ontology (CC BY 4.0);
BioLORD-2023 (FremyCompany; 모델 카드의 라이선스 조건 적용); SapBERT (Cambridge LTL);
FinnGen 요약 통계로 학습한 장기 추정 모델 (수치는 출력하지 않음).
"""


def full():
    """dist/ADC_full_build_on_windows.zip: the full program, the folder builder and the two project-made model files."""
    subprocess.run([sys.executable, "-I", str(R / "ml/build_portable.py"), "--full"], check=True)
    d = R / "dist/ADC_full_build"; shutil.rmtree(d, ignore_errors=True); (d / "models_data").mkdir(parents=True)
    shutil.copy(R / "dist/adc_recommender_full.py", d)
    for p in ("launcher.py", "make_folder.py"): shutil.copy(R / "ml/win" / p, d)
    for p in ("mondo_index.npz", "vuln_biolord.pt"): shutil.copy(pathlib.Path("/data/hyeongchanahn/adctox/ml_cache") / p, d / "models_data")
    (d / "build_full.bat").write_bytes(FULL_BAT.encode("ascii"))
    (d / "README.txt").write_bytes(FULL_README.replace("\n", "\r\n").encode("utf-8-sig"))
    z = R / "dist/ADC_full_build_on_windows.zip"; z.unlink(missing_ok=True)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as f:
        for p in sorted(d.rglob("*")): f.write(p, pathlib.Path("ADC_full_build") / p.relative_to(d))
    print(f"wrote {z} ({z.stat().st_size / 1e6:.1f} MB)")


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    C.mkdir(parents=True, exist_ok=True); emb = C / EMBED[0].rsplit("/", 1)[1]
    if not emb.exists(): urllib.request.urlretrieve(EMBED[0], emb)
    assert sha(emb) == EMBED[1], "embeddable Python hash mismatch"
    for w in WHEELS:
        if not (C / "wheels" / w).exists():
            subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.12",
                            "--implementation", "cp", "--no-deps", w.split("-")[0].replace("_", "-") + "==" + w.split("-")[1], "-d", str(C / "wheels")], check=True)
    subprocess.run([sys.executable, "-I", str(R / "ml/build_portable.py")], check=True)
    shutil.rmtree(OUT, ignore_errors=True); py = OUT / "python"; py.mkdir(parents=True)
    zipfile.ZipFile(emb).extractall(py)
    site = py / "Lib/site-packages"; site.mkdir(parents=True)
    for w in WHEELS: zipfile.ZipFile(C / "wheels" / w).extractall(site)
    (py / "python312._pth").write_text("python312.zip\r\n.\r\nLib\\site-packages\r\n")
    shutil.copy(R / "dist/adc_recommender.py", OUT / "adc_recommender.py")
    (OUT / "ADC Recommender.bat").write_bytes(BAT.format(args="").encode("ascii"))
    exe = R / "dist/build_exe_on_windows"; shutil.rmtree(exe, ignore_errors=True); exe.mkdir()
    shutil.copy(R / "dist/adc_recommender.py", exe / "adc_recommender.py")
    (exe / "build_exe.bat").write_bytes(EXE_BAT.encode("ascii"))
    z2 = R / "dist/ADC_build_exe_on_windows.zip"; z2.unlink(missing_ok=True)
    with zipfile.ZipFile(z2, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as f:
        for p in sorted(exe.iterdir()): f.write(p, pathlib.Path("ADC_build_exe") / p.name)
    print(f"wrote {z2}")
    (OUT / "README_사용법.txt").write_bytes(README.replace("\n", "\r\n").encode("utf-8-sig"))
    z = R / "dist/ADC_Recommender_Windows.zip"; z.unlink(missing_ok=True)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as f:
        for p in sorted(OUT.rglob("*")): f.write(p, pathlib.Path("ADC_Recommender") / p.relative_to(OUT))
    print(f"wrote {z} ({z.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    full() if "--full" in sys.argv else main()
