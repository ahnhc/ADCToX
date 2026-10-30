"""Prepare app and independent model assets locally; publishing is a separate command.

python -I scripts/build_ubuntu_release.py --models --model-version 0.0
python -I scripts/build_ubuntu_release.py              # app only, using tracked label evidence
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
from adc_version import APP_VERSION, RUNTIME_API, REPOSITORY
from adc_updates import AXES, validate_manifest

ENCODERS = [
    ("FremyCompany/BioLORD-2023", "167aab527b238a50ca65224e6319215d2ff4fc9f", "BioLORD-2023"),
    ("cambridgeltl/SapBERT-from-PubMedBERT-fulltext", "090663c3ae57bf35ffe4d0d468a2a88d03051a4d", "SapBERT"),
]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def model_assets(output, version, cache):
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    output.mkdir(parents=True, exist_ok=True)
    original = torch.load(cache / "vuln_biolord.pt", weights_only=False, map_location="cpu")
    meta = dict(original["meta"])
    for key in ("O", "base", "spread"): meta[key] = torch.from_numpy(np.asarray(meta[key]).copy())
    for key in ("out_axis", "out_dom"): meta[key] = [str(v) if v is not None else None for v in meta[key]]
    safe = {"format_version": 1, "ens": original["ens"], "meta": meta}
    if original.get("axis"): safe["axis"] = original["axis"]          # axis heads (model 0.1+); older apps ignore the key
    if original.get("axis_hidden"): safe["axis_hidden"] = [str(x) for x in original["axis_hidden"]]   # axes left blank (model 0.2+)
    if original.get("axis_models"):                                  # comparison heads and the agreement gate (model 0.2+)
        safe["axis_models"] = [{"name": str(x["name"]), "axis": x["axis"]} for x in original["axis_models"]]; safe["agree_min"] = int(original.get("agree_min", 1)); safe["axis_label"] = str(original.get("axis_label", "main"))
    torch.save(safe, output / "vuln_biolord.pt")
    torch.load(output / "vuln_biolord.pt", weights_only=True, map_location="cpu")
    with np.load(cache / "mondo_index.npz", allow_pickle=True) as source:
        extra = {k: source[k] for k in source.files if k not in ("E", "ids", "names", "axes")}   # v1+: validity gate; v2+: abbreviations, HPO
        np.savez_compressed(output / "mondo_index.npz", E=source["E"], ids=source["ids"].astype(str), names=source["names"].astype(str), axes=source["axes"], **extra)
    with np.load(output / "mondo_index.npz", allow_pickle=False) as safe_index:
        for key in safe_index.files: safe_index[key]
    files = []
    for name in ("vuln_biolord.pt", "mondo_index.npz"):
        path = output / name
        files.append({"path": name, "size": path.stat().st_size, "sha256": digest(path), "url": f"https://github.com/{REPOSITORY}/releases/download/models-{version}/{name}"})
    judge = cache / "GemmaJudge"                                     # model 0.5-0.6: the quantized Gemma organ judge (Apache-2.0)
    scratch = cache / "ScratchJudge"                                 # model 0.7+: the from-scratch organ judge (ml/scratch_export.py)
    for folder in (judge, scratch):
        if not folder.is_dir(): continue
        for path in sorted(folder.iterdir()):
            asset = f"{folder.name}-{path.name}"; (output / asset).write_bytes(path.read_bytes()) if not (output / asset).exists() or (output / asset).stat().st_size != path.stat().st_size else None
            files.append({"path": f"{folder.name}/{path.name}", "size": path.stat().st_size, "sha256": digest(path), "url": f"https://github.com/{REPOSITORY}/releases/download/models-{version}/{asset}"})
    for repo, revision, directory in ENCODERS:
        snapshot = Path(snapshot_download(repo, revision=revision, allow_patterns=["*.json", "1_Pooling/*", "model.safetensors", "vocab.txt"]))
        for path in sorted(snapshot.rglob("*")):
            if not path.is_file() or not (path.suffix == ".json" or path.name in ("model.safetensors", "vocab.txt")): continue
            relative = path.relative_to(snapshot).as_posix()
            files.append({"path": f"{directory}/{relative}", "size": path.stat().st_size, "sha256": digest(path), "url": f"https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(relative, safe='/')}"})
    manifest = {"schema_version": 1, "model_version": version, "runtime_api": RUNTIME_API, "architecture": "biolord-twotower-v1", "axes": AXES,
                "encoders": [{"repository": repo, "revision": revision, "directory": directory} for repo, revision, directory in ENCODERS],
                "score_definition": "clip(axis-standardized excess log-HR minus within-disease median, 0, 1)",
                "context": "legacy-lag-only", "files": files}
    validate_manifest(manifest)
    write(output / "models.json", manifest)
    if scratch.is_dir(): write(ROOT / "releases/models/stable3.json", manifest)  # read by app 0.5+; older apps reject ScratchJudge/
    else:
        write(ROOT / "releases/models/stable2.json", manifest)                   # read by app 0.3.8-0.4.x
        if not judge.is_dir(): write(ROOT / "releases/models/stable.json", manifest)  # apps up to 0.3.7 cannot take GemmaJudge/
    print(f"Model {version}: {len(files)} files, {sum(f['size'] for f in files) / 1024**2:.1f} MiB total; encoders use pinned Hugging Face URLs.")


def derived_models(output, version, base, add, drop):
    """a model release from a published manifest: its files stay where they are (same URLs and checksums, so an update downloads
    nothing again), the folders in `drop` are left out and each folder in `add` is uploaded with this release.
    Models 0.7 = models 0.6 without GemmaJudge/ plus ScratchJudge/."""
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(base.read_text()); manifest["model_version"] = version
    files = [f for f in manifest["files"] if f["path"].split("/")[0] not in drop]
    for folder in add:
        for path in sorted(folder.iterdir()):
            asset = f"{folder.name}-{path.name}"; (output / asset).write_bytes(path.read_bytes())
            files.append({"path": f"{folder.name}/{path.name}", "size": path.stat().st_size, "sha256": digest(path), "url": f"https://github.com/{REPOSITORY}/releases/download/models-{version}/{asset}"})
    manifest["files"] = files; validate_manifest(manifest)
    write(output / "models.json", manifest); write(ROOT / "releases/models/stable3.json", manifest)   # read by app 0.5+
    new = [f for f in files if f"/models-{version}/" in f["url"]]
    print(f"Model {version}: {len(files)} files, {sum(f['size'] for f in files) / 1024**2:.1f} MiB total; {len(new)} new files, {sum(f['size'] for f in new) / 1024**2:.1f} MiB.")


def release_tag():
    """v0.2 -> v0.2.0, v0.2.1 -> v0.2.1: the Git tag of the app release."""
    return "v" + APP_VERSION + (".0" if APP_VERSION.count(".") == 1 else "")


def app_assets(output):
    output.mkdir(parents=True, exist_ok=True)
    snapshot = ROOT / "ml/data/label_evidence.json"
    if not snapshot.exists():
        import drug_evidence
        evidence = json.loads(json.dumps(drug_evidence.evidence(), default=lambda x: x.item() if hasattr(x, "item") else list(x)))
        write(snapshot, {"source": "DailyMed label snapshot 2026-10-07; factual evidence derived by ml/drug_evidence.py", "evidence": evidence})
    app = output / "adc_recommender_full.py"
    subprocess.run([sys.executable, "-I", str(ROOT / "ml/build_portable.py"), "--full", str(app)], check=True,
                   env={**os.environ, "ADCTOX_EVIDENCE_SNAPSHOT": str(snapshot)})
    subprocess.run([sys.executable, "-m", "py_compile", str(app)], check=True)
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / "ml").glob("*.py")) if p.name in {"recommend.py", "restrictions.py", "labs.py", "form.py", "tui.py", "term.py", "adc_version.py", "adc_runtime.py", "adc_updates.py", "vulnerability_model.py", "mondo_index.py", "lab.py", "build_portable.py", "suggest.py", "gemma_runtime.py", "scratch_runtime.py", "motion.py", "webapp.py"}}
    source_hashes.update({str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / "ml/web").glob("*")) if p.is_file() and not p.name.startswith("mock")})   # the page adctox --web serves, embedded in the app
    info = {"app_version": APP_VERSION, "runtime_api": RUNTIME_API, "source_sha256": source_hashes}
    write(output / "bundle-info.json", info)
    archive = output / "adctox-ubuntu.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(app, arcname=app.name)
        tar.add(ROOT / "releases/requirements-cpu.txt", arcname="requirements-cpu.txt")
        tar.add(output / "bundle-info.json", arcname="bundle-info.json")
    manifest = {"schema_version": 1, "app_version": APP_VERSION, "runtime_api": RUNTIME_API,
                "url": f"https://github.com/{REPOSITORY}/releases/download/{release_tag()}/{archive.name}",
                "size": archive.stat().st_size, "sha256": digest(archive), "torch_version": "2.11.0"}
    write(output / "app.json", manifest)
    write(ROOT / "releases/app/stable.json", manifest)
    print(f"App {APP_VERSION}: {archive.stat().st_size / 1024:.1f} KiB. No model weights in the app archive.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", action="store_true")
    p.add_argument("--model-version", default="0.0")
    p.add_argument("--cache", type=Path, default=Path("/data/hyeongchanahn/adctox/ml_cache"))
    p.add_argument("--out", type=Path, default=ROOT / "dist/releases")
    p.add_argument("--base-manifest", type=Path, help="with --models: reuse this published manifest's files (derived_models)")
    p.add_argument("--add", type=Path, action="append", default=[], help="with --base-manifest: a bundle folder to upload")
    p.add_argument("--drop", action="append", default=[], help="with --base-manifest: a bundle folder to leave out")
    args = p.parse_args()
    if args.models and args.base_manifest: derived_models(args.out / "models", args.model_version, args.base_manifest, args.add, set(args.drop))
    elif args.models: model_assets(args.out / "models", args.model_version, args.cache)
    app_assets(args.out / "app")


if __name__ == "__main__": main()
