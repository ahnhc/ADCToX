from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent
DATA_ROOT = _PACKAGE / "_data"
if not DATA_ROOT.is_dir():
    DATA_ROOT = _PACKAGE.parents[1]
