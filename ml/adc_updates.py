"""Verified, transactional model-bundle updates. No third-party runtime dependencies."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from adc_version import APP_MANIFEST_URL, APP_VERSION, MODEL_MANIFEST_URL, RUNTIME_API
from adc_runtime import model_home, current_directory, pointer_mode

AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class UpdateError(Exception):
    pass


def manifest_url():
    return os.environ.get("ADCTOX_MODEL_MANIFEST", MODEL_MANIFEST_URL)


def _url(url, allow_local=False):
    if not isinstance(url, str):
        raise UpdateError("Invalid download URL.")
    parsed = urllib.parse.urlsplit(url)
    local = allow_local and parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not (parsed.scheme == "https" or local) or not parsed.hostname or parsed.username or parsed.password:
        raise UpdateError("Model downloads require an HTTPS URL.")
    return url


def _open(url, allow_local=False):
    request = urllib.request.Request(_url(url, allow_local), headers={"User-Agent": "ADCTOX-updater/1", "Accept": "application/octet-stream"})
    response = urllib.request.urlopen(request, timeout=30)
    try:
        _url(response.geturl(), allow_local)
    except Exception:
        response.close()
        raise
    return response


def validate_manifest(data, allow_local=False):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise UpdateError("Unsupported model manifest.")
    if data.get("runtime_api") != RUNTIME_API or data.get("architecture") != "biolord-twotower-v1" or data.get("axes") != AXES:
        raise UpdateError("This model requires a different app runtime. Update the app first.")
    if not isinstance(data.get("model_version"), str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", data["model_version"]):
        raise UpdateError("Invalid model version.")
    files = data.get("files")
    if not isinstance(files, list) or not 2 <= len(files) <= 200:
        raise UpdateError("Invalid model file list.")
    seen = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise UpdateError("Invalid model file entry.")
        path = PurePosixPath(item["path"])
        if (path.is_absolute() or ".." in path.parts or "\\" in item["path"] or str(path) != item["path"]
                or not path.parts or path.parts[0] not in ("BioLORD-2023", "SapBERT", "vuln_biolord.pt", "mondo_index.npz")
                or item["path"] in seen or any(ord(c) < 32 for c in item["path"])):
            raise UpdateError("Invalid or duplicate model path.")
        if path.parts[0] in ("vuln_biolord.pt", "mondo_index.npz") and len(path.parts) != 1:
            raise UpdateError("Invalid model path.")
        seen.add(item["path"])
        if not re.fullmatch(r"[a-f0-9]{64}", str(item.get("sha256", ""))):
            raise UpdateError("Invalid file checksum.")
        if type(item.get("size")) is not int or not 0 < item["size"] < 2 * 1024**3:
            raise UpdateError("Invalid file size.")
        _url(item.get("url", ""), allow_local)
    required = {"vuln_biolord.pt", "mondo_index.npz", "BioLORD-2023/config.json", "SapBERT/config.json", "BioLORD-2023/model.safetensors", "SapBERT/model.safetensors"}
    if not required <= seen:
        raise UpdateError("The model bundle is incomplete.")
    return data


def fetch_manifest(url=None, allow_local=False):
    try:
        with _open(url or manifest_url(), allow_local) as stream:
            body = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(body) > MAX_MANIFEST_BYTES:
            raise UpdateError("Model manifest is too large.")
        return validate_manifest(json.loads(body), allow_local)
    except (OSError, ValueError, TypeError) as error:
        raise UpdateError(f"Could not check model updates: {error}") from error


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _valid(path, item):
    return path.is_file() and path.stat().st_size == item["size"] and digest(path) == item["sha256"]


# Blobs are content-addressed and every one was hashed when it was downloaded. Re-hashing ~1 GB on each update only to learn
# that nothing changed is wasted work, so a verified blob is remembered by (size, mtime) and trusted while both are unchanged.
# `adctox --verify-models` still re-hashes everything.
def _verified_path(root):
    return Path(root) / "blobs" / "verified.json"


def _load_verified(root):
    try:
        data = json.loads(_verified_path(root).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember(root, verified, sha, path):
    stat = path.stat(); verified[sha] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    tmp = _verified_path(root).with_suffix(".tmp"); tmp.write_text(json.dumps(verified)); os.replace(tmp, _verified_path(root))


def _trusted(root, verified, item):
    blob = Path(root) / "blobs" / item["sha256"]
    try: stat = blob.stat()
    except OSError: return False
    seen = verified.get(item["sha256"])
    return stat.st_size == item["size"] and bool(seen) and seen.get("size") == stat.st_size and seen.get("mtime_ns") == stat.st_mtime_ns


def plan(manifest, home=None):
    """-> dict(up_to_date, download=[paths], reuse=[paths], download_bytes): what an update would fetch, without hashing.
    A blob of the installed bundle that predates the verified list is adopted once by size (it was hashed when downloaded)."""
    root = Path(home) if home else model_home(); verified = _load_verified(root); current = current_info(root)
    installed = {f["sha256"] for f in (current or {}).get("manifest", {}).get("files", [])}
    download, reuse = [], []
    for item in manifest["files"]:
        blob = root / "blobs" / item["sha256"]
        legacy = item["sha256"] not in verified                              # installed before the verified list existed
        if legacy and item["sha256"] in installed and blob.is_file() and blob.stat().st_size == item["size"]:
            _verified_path(root).parent.mkdir(parents=True, exist_ok=True); _remember(root, verified, item["sha256"], blob)
        (reuse if _trusted(root, verified, item) else download).append(item)
    return dict(up_to_date=bool(current) and current.get("bundle_id") == bundle_id(manifest) and not download,
                download=[i["path"] for i in download], reuse=[i["path"] for i in reuse], download_bytes=sum(i["size"] for i in download))


def verify(home=None):
    """re-hash every file of the active bundle; -> list of corrupted paths (their blobs are forgotten, so the next update refetches)."""
    root = Path(home) if home else model_home(); current = current_info(root)
    if not current: raise UpdateError("No installed model bundle.")
    verified = _load_verified(root); bad = []
    for item in current["manifest"]["files"]:
        blob = root / "blobs" / item["sha256"]
        if _valid(blob, item): _remember(root, verified, item["sha256"], blob)
        else: bad.append(item["path"]); verified.pop(item["sha256"], None)
    tmp = _verified_path(root).with_suffix(".tmp"); tmp.write_text(json.dumps(verified)); os.replace(tmp, _verified_path(root))
    return bad


def current_info(home=None):
    root = Path(home) if home else model_home()
    directory = current_directory(root)
    try:
        return json.loads((directory / "bundle.json").read_text()) if directory else None
    except (OSError, ValueError):
        return None


def bundle_id(manifest):
    # Includes model URLs and contract as well as weights; unchanged bytes still reuse blobs.
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _download(item, target, progress, allow_local):
    received = 0
    hasher = hashlib.sha256()
    temporary = target.with_suffix(".partial")
    try:
        with _open(item["url"], allow_local) as source, temporary.open("wb") as output:
            while block := source.read(1024 * 1024):
                received += len(block)
                if received > item["size"]:
                    raise UpdateError(f"Unexpected file size: {item['path']}")
                output.write(block)
                hasher.update(block)
                progress(item["path"], received, item["size"])
            output.flush()
            os.fsync(output.fileno())
        if received != item["size"] or hasher.hexdigest() != item["sha256"]:
            raise UpdateError(f"Checksum verification failed: {item['path']}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def _locked(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".update.lock").open("a+") as stream:
        if os.name == "nt":
            import msvcrt
            try:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise UpdateError("Another model update is already running.") from error
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UpdateError("Another model update is already running.") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _switch(root, destination):
    if pointer_mode():                                       # Windows: replace a small file, never a directory link
        temporary = root / ".current-next.txt"
        temporary.write_text(destination.name + "\n")
        os.replace(temporary, root / "current.txt")
        return
    temporary = root / ".current-next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(destination.relative_to(root), target_is_directory=True)
    os.replace(temporary, root / "current")


def _place(blob, path):
    """hard link the verified blob into the bundle; copy where the file system has no hard links (FAT, other volume)."""
    try:
        os.link(blob, path)
    except OSError:
        shutil.copy2(blob, path)


def install(manifest, home=None, progress=None, allow_local=False, cancelled=None):
    """Fetch changed files only; activate the complete verified bundle with one atomic rename."""
    validate_manifest(manifest, allow_local)
    root = Path(home) if home else model_home()
    progress = progress or (lambda *args: None)
    cancelled = cancelled or (lambda: False)
    def check_cancelled():
        if cancelled():
            raise UpdateError("Model update cancelled. Existing models remain selected.")
    identity = bundle_id(manifest)
    downloaded, reused = [], []
    try:
        with _locked(root):
            versions, blobs = root / "versions", root / "blobs"
            versions.mkdir(exist_ok=True)
            blobs.mkdir(exist_ok=True)
            previous = current_info(root)
            todo = plan(manifest, root)
            if todo["up_to_date"]:
                return {"model_version": manifest["model_version"], "downloaded": [], "reused": todo["reuse"], "bundle_id": identity, "up_to_date": True}
            verified = _load_verified(root)
            with tempfile.TemporaryDirectory(prefix=".staging-", dir=root) as temporary:
                staged = Path(temporary) / "bundle"
                staged.mkdir()
                for item in manifest["files"]:
                    check_cancelled()
                    blob = blobs / item["sha256"]
                    if _trusted(root, verified, item):
                        reused.append(item["path"])
                    else:
                        _download(item, blob, progress, allow_local)
                        _remember(root, verified, item["sha256"], blob)
                        downloaded.append(item["path"])
                    path = staged / item["path"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    _place(blob, path)
                destination = versions / identity
                if destination.exists():
                    # Never mutate a directory another running process may be using.
                    destination = versions / (identity + "-" + __import__("uuid").uuid4().hex[:12])
                marker = {"bundle_id": identity, "directory": destination.name, "model_version": manifest["model_version"], "manifest": manifest}
                (staged / "bundle.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n")
                os.replace(staged, destination)
                if previous and previous["bundle_id"] != identity:
                    (root / "previous.json").write_text(json.dumps(previous) + "\n")
                check_cancelled()
                _switch(root, destination)
            return {"model_version": manifest["model_version"], "downloaded": downloaded, "reused": reused, "bundle_id": identity, "up_to_date": False}
    except (OSError, ValueError) as error:
        raise UpdateError(f"Model update failed. Existing models remain selected: {error}") from error


def rollback(home=None, allow_local=False):
    root = Path(home) if home else model_home()
    try:
        with _locked(root):
            previous = json.loads((root / "previous.json").read_text())
            directory = previous.get("directory", previous["bundle_id"])
            if not re.fullmatch(r"[a-f0-9]{64}(?:-[a-f0-9]{12})?", directory):
                raise UpdateError("Invalid previous model bundle.")
            destination = root / "versions" / directory
            manifest = validate_manifest(previous["manifest"], allow_local)
            if not all(_valid(destination / item["path"], item) for item in manifest["files"]):
                raise UpdateError("Previous model files are incomplete or corrupted.")
            current = current_info(root)
            _switch(root, destination)
            if current:
                (root / "previous.json").write_text(json.dumps(current) + "\n")
            return previous["model_version"]
    except (OSError, ValueError, KeyError) as error:
        raise UpdateError("No verified previous model bundle is available.") from error


# ------------------------------------------------------------------ the app itself (models above)
def _version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def app_manifest_url():
    return os.environ.get("ADCTOX_APP_MANIFEST", APP_MANIFEST_URL)


def fetch_app_manifest(url=None, allow_local=False):
    try:
        with _open(url or app_manifest_url(), allow_local) as stream:
            data = json.loads(stream.read(MAX_MANIFEST_BYTES + 1))
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise UpdateError(f"Could not read the app release manifest: {error}") from error
    if data.get("schema_version") != 1 or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(data.get("app_version", ""))) \
            or not re.fullmatch(r"[0-9a-f]{64}", str(data.get("sha256", ""))) or not isinstance(data.get("size"), int) or not 0 < data["size"] < 50 * 1024**2:
        raise UpdateError("Invalid app release manifest.")
    _url(data.get("url", ""), allow_local)
    return data


def check_app(max_age_hours=24, home=None, allow_local=False):
    """-> {latest, newer} from the published app manifest, read at most once a day (cached next to the models); None offline."""
    import time
    cache = (Path(home) if home else model_home()).parent / "app_check.json"
    try:
        c = json.loads(cache.read_text())
        if time.time() - c["checked"] < max_age_hours * 3600 and c.get("current") == APP_VERSION: return c
    except (OSError, ValueError, KeyError):
        pass
    try:
        latest = fetch_app_manifest(allow_local=allow_local)["app_version"]
    except UpdateError:
        return None
    c = {"checked": time.time(), "current": APP_VERSION, "latest": latest, "newer": _version(latest) > _version(APP_VERSION)}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True); cache.write_text(json.dumps(c))
    except OSError:
        pass
    return c


def app_layout(program=None):
    """(install prefix, the running app directory) when this app runs from an installed layout (prefix/apps/<release>/),
    else None (a repository checkout or a copied file)."""
    import sys
    path = Path(program or sys.argv[0]).resolve()
    if path.parent.parent.name == "apps": return path.parent.parent.parent, path.parent
    return None


def update_app(manifest=None, program=None, allow_local=False, torch_version=None):
    """Download the newer app archive, verify it, unpack it beside the current release and switch to it (prefix/current link
    on Linux, prefix/app.txt on Windows). The runtime (Python packages) is not changed: when the release needs other packages,
    nothing is switched and the installer has to be run again. -> message."""
    import io, sys, tarfile
    layout = app_layout(program)
    if layout is None:
        raise UpdateError("This copy is not an installed app (run from a repository or a copied file); update it with git pull or the installer.")
    prefix, running = layout
    manifest = manifest or fetch_app_manifest(allow_local=allow_local)
    if _version(manifest["app_version"]) <= _version(APP_VERSION):
        return f"App {APP_VERSION} is up to date."
    body = b""
    with _open(manifest["url"], allow_local) as stream:
        body = stream.read(manifest["size"] + 1)
    if len(body) != manifest["size"] or hashlib.sha256(body).hexdigest() != manifest["sha256"]:
        raise UpdateError("App download failed verification; nothing was changed.")
    names = {"adc_recommender_full.py", "requirements-cpu.txt", "bundle-info.json"}
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        members = archive.getmembers()
        if {m.name for m in members} != names or not all(m.isfile() for m in members):
            raise UpdateError("Unexpected app archive contents; nothing was changed.")
        new_req = archive.extractfile("requirements-cpu.txt").read()
        try: old_req = (running / "requirements-cpu.txt").read_bytes()
        except OSError: old_req = None
        if torch_version is None:
            try: torch_version = __import__("torch").__version__.split("+")[0]
            except ImportError: torch_version = None
        if new_req != old_req or (manifest.get("torch_version") and torch_version and manifest["torch_version"] != torch_version):
            raise UpdateError(f"App {manifest['app_version']} needs different Python packages; run the installer again (see the release notes).")
        release = prefix / "apps" / f"{manifest['app_version']}-{manifest['sha256'][:12]}"
        if not release.exists():
            staged = Path(tempfile.mkdtemp(prefix=".app-", dir=prefix / "apps"))
            try:
                archive.extractall(staged, filter="data")
                os.replace(staged, release)
            finally:
                shutil.rmtree(staged, ignore_errors=True)
    if pointer_mode():
        temporary = prefix / ".app-next.txt"; temporary.write_text(release.name + "\n"); os.replace(temporary, prefix / "app.txt")
    else:
        temporary = prefix / ".app-next"; temporary.unlink(missing_ok=True)
        temporary.symlink_to(release.relative_to(prefix), target_is_directory=True); os.replace(temporary, prefix / "current")
    return f"App {manifest['app_version']} installed; it starts next time you open ADCTOX."


def app_cli(action):
    try:
        if action == "check":
            m = fetch_app_manifest()
            print(f"App {APP_VERSION} -> {m['app_version']}: " + ("update available (adctox --update-app)" if _version(m["app_version"]) > _version(APP_VERSION) else "up to date"))
        else:
            print(update_app())
        return 0
    except UpdateError as error:
        print(str(error), file=__import__("sys").stderr)
        return 1


def cli(action="update"):
    try:
        if action == "rollback":
            print(f"Model restored: {rollback()}")
            return 0
        info = current_info()
        if action == "version":
            print(info["model_version"] if info else "research-cache / not installed")
            return 0
        if action == "verify":
            bad = verify()
            print("All model files verified." if not bad else "Corrupted (will be downloaded again on update): " + ", ".join(bad))
            return 0 if not bad else 1
        manifest = fetch_manifest()
        print(f"Model {info['model_version'] if info else 'not installed'} -> {manifest['model_version']}")
        todo = plan(manifest)
        if action == "check":
            print("Up to date" if todo["up_to_date"] else f"Update available: {len(todo['download'])} files to download ({todo['download_bytes'] / 1024**2:.1f} MiB), {len(todo['reuse'])} unchanged")
            return 0
        if todo["up_to_date"]:
            print("Up to date; nothing downloaded.")
            return 0
        last = {}
        def progress(name, done, total):
            percent = int(done * 100 / total)
            if percent // 10 != last.get(name):
                print(f"  {name}  {percent}%", flush=True)
                last[name] = percent // 10
        result = install(manifest, progress=progress)
        print(f"Model {result['model_version']} ready: {len(result['downloaded'])} downloaded, {len(result['reused'])} unchanged.")
        return 0
    except UpdateError as error:
        print(str(error), file=__import__("sys").stderr)
        return 1
