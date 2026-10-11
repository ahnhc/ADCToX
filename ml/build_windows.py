"""Build dist/ADC_Recommender_Windows.zip: unzip on any 64-bit Windows 10/11 PC and double-click; no Python install.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/build_windows.py

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
    (OUT / "README_사용법.txt").write_bytes(README.replace("\n", "\r\n").encode("utf-8-sig"))
    z = R / "dist/ADC_Recommender_Windows.zip"; z.unlink(missing_ok=True)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as f:
        for p in sorted(OUT.rglob("*")): f.write(p, pathlib.Path("ADC_Recommender") / p.relative_to(OUT))
    print(f"wrote {z} ({z.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
