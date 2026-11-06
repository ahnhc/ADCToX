"""A script that puts an absolute checkout path on sys.path makes every later import in the process read that checkout's code."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ABSOLUTE = re.compile(r"""sys\.path\b[^\n]*['"]/(home|data)/[^'"\n]*adctox""")


def test_no_script_puts_an_absolute_adctox_path_on_sys_path():
    bad = [str(p.relative_to(ROOT)) for folder in ("ml", "scripts", "src", "tests") for p in (ROOT / folder).rglob("*.py")
           if ABSOLUTE.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert not bad, bad
