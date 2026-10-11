"""Run by build_full.bat inside its private venv: makes the ADC_Recommender folder.

    ADC_Recommender\
        ADC Recommender.exe        double-click this: opens the program in Windows Terminal (windowless launcher)
        app\ADC_Recommender.exe    the program (PyInstaller one-folder build) and its libraries
        app\models\                BioLORD-2023, SapBERT (from Hugging Face, pinned revisions), mondo_index.npz, vuln_biolord.pt

The folder needs no Python and no internet; copy or zip it whole.
"""
import os, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "ADC_Recommender"
MODELS = [("FremyCompany/BioLORD-2023", "167aab527b238a50ca65224e6319215d2ff4fc9f", "BioLORD-2023",
           ["*.json", "1_Pooling/*", "model.safetensors", "vocab.txt"]),
          ("cambridgeltl/SapBERT-from-PubMedBERT-fulltext", "090663c3ae57bf35ffe4d0d468a2a88d03051a4d", "SapBERT",
           ["*.json", "model.safetensors", "vocab.txt"])]
# transformers / sentence-transformers load parts of themselves by name, which PyInstaller cannot see
COLLECT = ["--collect-submodules", "sentence_transformers", "--collect-data", "sentence_transformers",
           "--collect-submodules", "transformers.models.bert", "--hidden-import", "transformers.models.bert.modeling_bert",
           "--recursive-copy-metadata", "sentence-transformers"]      # transformers checks its dependencies' versions at import


def pyinstaller(*args):
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                    "--distpath", str(HERE / "build_out"), "--workpath", str(HERE / "build_tmp"), "--specpath", str(HERE / "build_tmp"), *args], check=True)


def main():
    from huggingface_hub import snapshot_download
    shutil.rmtree(OUT, ignore_errors=True)
    print("[1/3] program ...", flush=True)
    pyinstaller("--onedir", "--console", "--name", "ADC_Recommender", *COLLECT, str(HERE / "adc_recommender_full.py"))
    shutil.copytree(HERE / "build_out" / "ADC_Recommender", OUT / "app")
    if os.name == "nt":
        print("[2/3] launcher ...", flush=True)
        pyinstaller("--onefile", "--noconsole", "--name", "ADC Recommender", str(HERE / "launcher.py"))
        shutil.copy2(HERE / "build_out" / "ADC Recommender.exe", OUT / "ADC Recommender.exe")
    print("[3/3] models (about 850 MB download) ...", flush=True)
    m = OUT / "app" / "models"; m.mkdir(parents=True, exist_ok=True)
    for repo, rev, name, allow in MODELS:
        snapshot_download(repo, revision=rev, local_dir=m / name, allow_patterns=allow)
        shutil.rmtree(m / name / ".cache", ignore_errors=True)
    for f in ("mondo_index.npz", "vuln_biolord.pt"): shutil.copy2(HERE / "models_data" / f, m / f)
    shutil.copy2(HERE / "README.txt", OUT / "README.txt")
    print(f"\nDone: {OUT}\n  double-click 'ADC Recommender.exe'. Copy or zip the whole folder to use it on another PC.")


if __name__ == "__main__":
    main()
