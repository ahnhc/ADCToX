"""Exercise real downloads, delta updates, failed activation, repair, and rollback."""
from __future__ import annotations
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))
import adc_updates as updates
import adc_runtime


def selected_bundle(root):
    """the selected bundle in either switch mode (current symlink on Linux, current.txt on Windows)."""
    return adc_runtime.current_directory(root).resolve()


@pytest.fixture
def server():
    bodies, requests = {}, []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            body = bodies.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            if body is not None: self.wfile.write(body)
        def log_message(self, *args): pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    yield f"http://127.0.0.1:{http.server_port}", bodies, requests
    http.shutdown(); http.server_close(); thread.join()


def make_manifest(server, version="0.0", weight=b"head-1"):
    base, bodies, _ = server
    content = {"vuln_biolord.pt": weight, "mondo_index.npz": b"index", "BioLORD-2023/config.json": b"biolord-config",
               "SapBERT/config.json": b"sapbert-config", "BioLORD-2023/model.safetensors": b"biolord", "SapBERT/model.safetensors": b"sapbert"}
    files = []
    for path, body in content.items():
        urlpath = "/" + version + "/" + path
        bodies[urlpath] = body
        files.append({"path": path, "url": base + urlpath, "size": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    return {"schema_version": 1, "model_version": version, "runtime_api": 1, "architecture": "biolord-twotower-v1", "axes": updates.AXES, "files": files}


def test_only_changed_head_is_downloaded_and_rollback_restores_it(server, tmp_path):
    first = make_manifest(server)
    result = updates.install(first, tmp_path, allow_local=True)
    assert len(result["downloaded"]) == 6
    second = make_manifest(server, "0.1", b"head-2")
    server[2].clear()
    result = updates.install(second, tmp_path, allow_local=True)
    assert result["downloaded"] == ["vuln_biolord.pt"]
    assert len(result["reused"]) == 5
    assert server[2] == ["/0.1/vuln_biolord.pt"]
    assert (selected_bundle(tmp_path) / "vuln_biolord.pt").read_bytes() == b"head-2"
    assert updates.rollback(tmp_path, allow_local=True) == "0.0"
    assert (selected_bundle(tmp_path) / "vuln_biolord.pt").read_bytes() == b"head-1"


@pytest.mark.parametrize("failure", ["checksum", "missing", "size"])
def test_failed_download_preserves_all_active_files(server, tmp_path, failure):
    updates.install(make_manifest(server), tmp_path, allow_local=True)
    selected = selected_bundle(tmp_path)
    second = make_manifest(server, "0.1", b"head-2")
    path = "/0.1/vuln_biolord.pt"
    if failure == "checksum": server[1][path] = b"wrong!"
    elif failure == "missing": del server[1][path]
    else: server[1][path] = b"too many bytes"
    with pytest.raises(updates.UpdateError): updates.install(second, tmp_path, allow_local=True)
    assert selected_bundle(tmp_path) == selected
    assert (selected_bundle(tmp_path) / "vuln_biolord.pt").read_bytes() == b"head-1"
    assert not list(tmp_path.glob(".staging-*"))
    assert not list((tmp_path / "blobs").glob("*.partial"))


def test_cancel_before_activation_keeps_current_bundle(server, tmp_path):
    updates.install(make_manifest(server), tmp_path, allow_local=True)
    selected = selected_bundle(tmp_path)
    manifest = make_manifest(server, "0.1", b"head-2")
    cancelled = threading.Event()
    with pytest.raises(updates.UpdateError, match="cancelled"):
        updates.install(manifest, tmp_path, allow_local=True, progress=lambda *args: cancelled.set(), cancelled=cancelled.is_set)
    assert selected_bundle(tmp_path) == selected


def test_repeat_install_has_no_network_downloads(server, tmp_path):
    manifest = make_manifest(server)
    updates.install(manifest, tmp_path, allow_local=True)
    server[2].clear()
    result = updates.install(manifest, tmp_path, allow_local=True)
    assert result["downloaded"] == []
    assert server[2] == []


def test_corrupted_local_model_is_repaired_in_a_new_directory(server, tmp_path):
    manifest = make_manifest(server)
    updates.install(manifest, tmp_path, allow_local=True)
    old = selected_bundle(tmp_path)
    (old / "vuln_biolord.pt").write_bytes(b"broken")
    result = updates.install(manifest, tmp_path, allow_local=True)
    assert result["downloaded"] == ["vuln_biolord.pt"]
    assert selected_bundle(tmp_path) != old
    assert (selected_bundle(tmp_path) / "vuln_biolord.pt").read_bytes() == b"head-1"


@pytest.mark.parametrize("change", ["schema", "runtime", "axes", "architecture", "missing", "duplicate", "traversal", "absolute", "backslash", "http", "size"])
def test_incompatible_or_invalid_manifest_is_rejected(server, change):
    m = copy.deepcopy(make_manifest(server))
    if change == "schema": m["schema_version"] = 2
    elif change == "runtime": m["runtime_api"] = 2
    elif change == "axes": m["axes"] = list(reversed(m["axes"]))
    elif change == "architecture": m["architecture"] = "other"
    elif change == "missing": m["files"].pop()
    elif change == "duplicate": m["files"].append(m["files"][0])
    elif change == "traversal": m["files"][0]["path"] = "../outside"
    elif change == "absolute": m["files"][0]["path"] = "/outside"
    elif change == "backslash": m["files"][0]["path"] = "BioLORD-2023\\outside"
    elif change == "http": m["files"][0]["url"] = "http://example.com/model"
    elif change == "size": m["files"][0]["size"] = -1
    with pytest.raises(updates.UpdateError): updates.validate_manifest(m, allow_local=True)


def test_fetch_parses_real_http_manifest_and_errors_leave_local_state(server, tmp_path):
    manifest = make_manifest(server)
    server[1]["/models.json"] = json.dumps(manifest).encode()
    fetched = updates.fetch_manifest(server[0] + "/models.json", allow_local=True)
    assert fetched == manifest
    updates.install(fetched, tmp_path, allow_local=True)
    server[1]["/models.json"] = b"invalid json"
    with pytest.raises(updates.UpdateError): updates.fetch_manifest(server[0] + "/models.json", allow_local=True)
    assert updates.current_info(tmp_path)["model_version"] == "0.0"


def test_another_update_cannot_activate_while_lock_is_held(server, tmp_path):
    with updates._locked(tmp_path):
        with pytest.raises(updates.UpdateError, match="already running"):
            updates.install(make_manifest(server), tmp_path, allow_local=True)


def test_rollback_rejects_modified_previous_weights(server, tmp_path):
    updates.install(make_manifest(server), tmp_path, allow_local=True)
    previous = selected_bundle(tmp_path)
    updates.install(make_manifest(server, "0.1", b"head-2"), tmp_path, allow_local=True)
    (previous / "vuln_biolord.pt").write_bytes(b"broken")
    with pytest.raises(updates.UpdateError, match="corrupted"):
        updates.rollback(tmp_path, allow_local=True)
    assert updates.current_info(tmp_path)["model_version"] == "0.1"


def test_successful_update_invalidates_linking_and_inference_caches(monkeypatch):
    import recommend as rc
    class Index:
        closed = False
        def close(self): self.closed = True
    index = Index()
    from types import SimpleNamespace
    module = SimpleNamespace(_IDX=index)
    monkeypatch.setitem(sys.modules, "mondo_index", module)
    for cache in (rc._FREE, rc._FREE_PREDICTIONS, rc._ANALYSES, rc._REGISTRY_LEARNED): cache["test"] = 1
    rc.clear_model_cache()
    assert all(not c for c in (rc._FREE, rc._FREE_PREDICTIONS, rc._ANALYSES, rc._REGISTRY_LEARNED))
    assert index.closed and module._IDX is None


def test_update_button_returns_to_condition_selection_without_losing_input(monkeypatch):
    import form, term, tui
    from types import SimpleNamespace
    console = term._Shim()
    monkeypatch.setattr(tui, "curses", console)
    monkeypatch.setattr(form, "curses", console)
    monkeypatch.setattr(term, "USE_SHIM", True)
    screen = term._Screen(console)
    keys = iter([" ", "U", "PGDN"])
    monkeypatch.setattr(form, "_key", lambda scr: next(keys))
    opened = []
    monkeypatch.setattr(form.Form, "model_updates", lambda self: opened.append(True))
    rc = SimpleNamespace(_reg={"cirrhosis": {"organ_axes": "hepatic"}}, AXES=["hepatic"], EN={"hepatic": "Hepatic"},
                         KO={"cirrhosis": "간경변"}, condition_name=lambda c: "Cirrhosis", HAS_LEARNED=True)
    selected, free = form.Form(screen, rc).conditions(set(), "asthma")
    assert opened == [True] and selected == {"cirrhosis"} and free == "asthma"


def test_managed_runtime_does_not_mix_missing_files_with_research_cache(monkeypatch, tmp_path):
    import adc_runtime
    monkeypatch.setenv("ADC_MODEL_DIR", str(tmp_path))
    monkeypatch.delenv("ADC_RESEARCH_MODE", raising=False)
    with pytest.raises(FileNotFoundError, match="--update-models"):
        adc_runtime.model_path("missing", "research-cache-file")
    monkeypatch.setenv("ADC_RESEARCH_MODE", "1")
    assert adc_runtime.model_path("missing", "research-cache-file") == "research-cache-file"


def test_unchanged_bundle_is_not_rehashed_or_reinstalled(server, tmp_path, monkeypatch):
    manifest = make_manifest(server)
    updates.install(manifest, tmp_path, allow_local=True)
    active = selected_bundle(tmp_path)
    hashed = []
    monkeypatch.setattr(updates, "digest", lambda path: hashed.append(path) or "x")
    assert updates.plan(manifest, tmp_path)["up_to_date"]
    result = updates.install(manifest, tmp_path, allow_local=True)
    assert result["up_to_date"] and result["downloaded"] == [] and hashed == []
    assert selected_bundle(tmp_path) == active


def test_plan_lists_only_changed_files_and_verify_finds_corruption(server, tmp_path):
    manifest = make_manifest(server)
    updates.install(manifest, tmp_path, allow_local=True)
    (selected_bundle(tmp_path) / "vuln_biolord.pt").write_bytes(b"broken")
    todo = updates.plan(manifest, tmp_path)
    assert todo["download"] == ["vuln_biolord.pt"] and not todo["up_to_date"]
    assert updates.verify(tmp_path) == ["vuln_biolord.pt"]


def test_windows_pointer_mode_installs_switches_and_rolls_back_without_symlinks(server, tmp_path, monkeypatch):
    """Windows records the active bundle in current.txt and copies blobs where hard links fail (FAT, other volume)."""
    import adc_runtime
    monkeypatch.setenv("ADC_POINTER_SWITCH", "1")
    monkeypatch.setenv("ADC_MODEL_HOME", str(tmp_path))
    monkeypatch.delenv("ADC_RESEARCH_MODE", raising=False); monkeypatch.delenv("ADC_MODEL_DIR", raising=False)
    monkeypatch.setattr(updates.os, "link", lambda *a: (_ for _ in ()).throw(OSError("no hard links")))
    first = updates.install(make_manifest(server), tmp_path, allow_local=True)
    second = updates.install(make_manifest(server, "0.1", b"head-2"), tmp_path, allow_local=True)
    assert not (tmp_path / "current").exists() and (tmp_path / "current.txt").read_text().strip() == second["bundle_id"]
    assert adc_runtime.active_directory() == tmp_path / "versions" / second["bundle_id"]
    assert (adc_runtime.active_directory() / "vuln_biolord.pt").read_bytes() == b"head-2"
    assert updates.current_info(tmp_path)["model_version"] == "0.1"
    assert updates.rollback(tmp_path, allow_local=True) == "0.0"
    assert (tmp_path / "current.txt").read_text().strip() == first["bundle_id"]
    (tmp_path / "current.txt").write_text("../escape\n")
    assert adc_runtime.active_directory() is None and updates.current_info(tmp_path) is None


def _app_release(server, version, requirements=b"numpy==2.5.3\n", tamper=False):
    import io, tarfile
    base, bodies, _ = server
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, body in {"adc_recommender_full.py": f"print('app {version}')\n".encode(), "requirements-cpu.txt": requirements, "bundle-info.json": b"{}"}.items():
            info = tarfile.TarInfo(name); info.size = len(body); archive.addfile(info, io.BytesIO(body))
    body = buffer.getvalue(); bodies[f"/app/{version}.tar.gz"] = body + (b"x" if tamper else b"")
    manifest = {"schema_version": 1, "app_version": version, "runtime_api": 1, "url": f"{base}/app/{version}.tar.gz",
                "size": len(body), "sha256": hashlib.sha256(body).hexdigest(), "torch_version": "2.11.0"}
    bodies["/app/stable.json"] = json.dumps(manifest).encode()
    return manifest


def _installed_app(prefix, pointer):
    release = prefix / "apps" / "0.2.1-aaaaaaaaaaaa"; release.mkdir(parents=True)
    (release / "adc_recommender_full.py").write_text("print('old')\n"); (release / "requirements-cpu.txt").write_bytes(b"numpy==2.5.3\n")
    if pointer: (prefix / "app.txt").write_text(release.name + "\n")
    else: (prefix / "current").symlink_to(release.relative_to(prefix), target_is_directory=True)
    return release / "adc_recommender_full.py"


@pytest.mark.parametrize("pointer", [pytest.param(False, marks=pytest.mark.skipif(sys.platform == "win32", reason="Windows uses app.txt")), True])
def test_app_update_unpacks_the_new_release_and_switches_only_when_packages_match(server, tmp_path, monkeypatch, pointer):
    if pointer: monkeypatch.setenv("ADC_POINTER_SWITCH", "1")
    else: monkeypatch.delenv("ADC_POINTER_SWITCH", raising=False)
    program = _installed_app(tmp_path, pointer)
    message = updates.update_app(_app_release(server, "90.1"), program=program, allow_local=True, torch_version="2.11.0")
    assert "90.1 installed" in message
    active = (tmp_path / "apps" / (tmp_path / "app.txt").read_text().strip()) if pointer else (tmp_path / "current").resolve()
    assert (active / "adc_recommender_full.py").read_text() == "print('app 90.1')\n"
    # a release that needs other Python packages is refused and the running release stays selected
    before = (tmp_path / "app.txt").read_text() if pointer else (tmp_path / "current").resolve()
    with pytest.raises(updates.UpdateError, match="installer"):
        updates.update_app(_app_release(server, "90.2", requirements=b"numpy==3.0\n"), program=active / "adc_recommender_full.py", allow_local=True, torch_version="2.11.0")
    with pytest.raises(updates.UpdateError, match="verification"):
        updates.update_app(_app_release(server, "90.3", tamper=True), program=active / "adc_recommender_full.py", allow_local=True, torch_version="2.11.0")
    assert before == ((tmp_path / "app.txt").read_text() if pointer else (tmp_path / "current").resolve())


def test_app_check_is_cached_and_a_repository_copy_is_not_self_updated(server, tmp_path, monkeypatch):
    base, _, requests = server
    _app_release(server, "9.0")
    monkeypatch.setenv("ADCTOX_APP_MANIFEST", base + "/app/stable.json")
    first = updates.check_app(home=tmp_path / "models", allow_local=True)
    assert first["newer"] and first["latest"] == "9.0"
    count = len(requests)
    assert updates.check_app(home=tmp_path / "models", allow_local=True)["latest"] == "9.0" and len(requests) == count
    with pytest.raises(updates.UpdateError, match="not an installed app"):
        updates.update_app(program=tmp_path / "adc_recommender_full.py", allow_local=True)
