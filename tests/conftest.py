"""What every test run shares: subprocesses find src/, and a run leaves the tracked files as it found them."""
import os, pathlib, subprocess
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")]))


def _changed():
    try: return subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    except (OSError, subprocess.SubprocessError): return None


@pytest.fixture(scope="session", autouse=True)
def tracked_files_stay_as_they_were():
    before = _changed()
    yield
    after = _changed()
    assert before is None or after is None or after == before, f"the tests changed tracked files:\n{after}"


@pytest.fixture
def restored():
    """restored(path): put this file back after the test, for a test that runs a script writing a tracked artefact"""
    saved = {}
    yield lambda path: saved.setdefault(path, path.read_bytes())
    for path, data in saved.items(): path.write_bytes(data)
