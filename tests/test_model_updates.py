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
    assert (tmp_path / "current/vuln_biolord.pt").read_bytes() == b"head-2"
    assert updates.rollback(tmp_path, allow_local=True) == "0.0"
    assert (tmp_path / "current/vuln_biolord.pt").read_bytes() == b"head-1"


@pytest.mark.parametrize("failure", ["checksum", "missing", "size"])
def test_failed_download_preserves_all_active_files(server, tmp_path, failure):
    updates.install(make_manifest(server), tmp_path, allow_local=True)
    selected = (tmp_path / "current").resolve()
    second = make_manifest(server, "0.1", b"head-2")
    path = "/0.1/vuln_biolord.pt"
    if failure == "checksum": server[1][path] = b"wrong!"
    elif failure == "missing": del server[1][path]
    else: server[1][path] = b"too many bytes"
    with pytest.raises(updates.UpdateError): updates.install(second, tmp_path, allow_local=True)
    assert (tmp_path / "current").resolve() == selected
    assert (tmp_path / "current/vuln_biolord.pt").read_bytes() == b"head-1"
    assert not list(tmp_path.glob(".staging-*"))
    assert not list((tmp_path / "blobs").glob("*.partial"))


def test_cancel_before_activation_keeps_current_bundle(server, tmp_path):
    updates.install(make_manifest(server), tmp_path, allow_local=True)
    selected = (tmp_path / "current").resolve()
    manifest = make_manifest(server, "0.1", b"head-2")
    cancelled = threading.Event()
    with pytest.raises(updates.UpdateError, match="cancelled"):
        updates.install(manifest, tmp_path, allow_local=True, progress=lambda *args: cancelled.set(), cancelled=cancelled.is_set)
    assert (tmp_path / "current").resolve() == selected


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
    old = (tmp_path / "current").resolve()
    (old / "vuln_biolord.pt").write_bytes(b"broken")
    result = updates.install(manifest, tmp_path, allow_local=True)
    assert result["downloaded"] == ["vuln_biolord.pt"]
    assert (tmp_path / "current").resolve() != old
    assert (tmp_path / "current/vuln_biolord.pt").read_bytes() == b"head-1"


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
    previous = (tmp_path / "current").resolve()
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
