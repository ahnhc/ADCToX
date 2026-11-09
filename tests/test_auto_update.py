import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import adc_updates as U


def test_auto_update_switches_only_when_a_newer_release_is_installed(monkeypatch):
    monkeypatch.delenv("ADCTOX_NO_AUTO_UPDATE", raising=False); monkeypatch.delenv("ADCTOX_AUTO_UPDATED", raising=False)
    monkeypatch.setattr(U, "app_layout", lambda program=None: (pathlib.Path("/p"), pathlib.Path("/p/apps/x")))
    monkeypatch.setattr(U, "check_app", lambda **k: {"latest": "9.9.9", "newer": True})
    monkeypatch.setattr(U, "update_app", lambda **k: "App switched to 9.9.9.")
    assert U.auto_update_app() is True
    monkeypatch.setattr(U, "check_app", lambda **k: {"latest": U.APP_VERSION, "newer": False})
    assert U.auto_update_app() is False
    monkeypatch.setattr(U, "check_app", lambda **k: None)                      # offline
    assert U.auto_update_app() is False


def test_auto_update_never_raises_and_can_be_switched_off(monkeypatch):
    monkeypatch.delenv("ADCTOX_NO_AUTO_UPDATE", raising=False); monkeypatch.delenv("ADCTOX_AUTO_UPDATED", raising=False)
    monkeypatch.setattr(U, "app_layout", lambda program=None: (pathlib.Path("/p"), pathlib.Path("/p/apps/x")))
    monkeypatch.setattr(U, "check_app", lambda **k: {"latest": "9.9.9", "newer": True})
    def boom(**k): raise U.UpdateError("needs different packages")
    monkeypatch.setattr(U, "update_app", boom)
    assert U.auto_update_app() is False
    monkeypatch.setattr(U, "update_app", lambda **k: "App switched to 9.9.9.")
    monkeypatch.setenv("ADCTOX_NO_AUTO_UPDATE", "1")
    assert U.auto_update_app() is False
    monkeypatch.delenv("ADCTOX_NO_AUTO_UPDATE"); monkeypatch.setenv("ADCTOX_AUTO_UPDATED", "1")
    assert U.auto_update_app() is False


def test_a_repository_checkout_is_never_auto_updated(monkeypatch):
    monkeypatch.delenv("ADCTOX_NO_AUTO_UPDATE", raising=False); monkeypatch.delenv("ADCTOX_AUTO_UPDATED", raising=False)
    monkeypatch.setattr(U, "app_layout", lambda program=None: None)
    assert U.auto_update_app() is False


def test_a_running_app_checks_again_and_restarts_only_when_asked(monkeypatch):
    monkeypatch.delenv("ADCTOX_NO_AUTO_UPDATE", raising=False); monkeypatch.setenv("ADCTOX_AUTO_UPDATED", "1")   # set by a restart: only the startup check is skipped
    monkeypatch.setattr(U, "app_layout", lambda program=None: (pathlib.Path("/p"), pathlib.Path("/p/apps/x")))
    monkeypatch.setattr(U, "check_app", lambda **k: {"latest": "9.9.9", "newer": True})
    monkeypatch.setattr(U, "update_app", lambda **k: "App switched to 9.9.9.")
    assert U.auto_update_app() is False and U.auto_update_app(startup=False) is True
