"""Where the research scripts find the repository and the model cache. Defaults are the lab server's; on another machine set
ADCTOX_REPO (a checkout of this repository) and ADCTOX_CACHE (an unpacked adctox-team-cache, i.e. the ml_cache folder)."""
import os
from pathlib import Path

REPO = os.environ.get("ADCTOX_REPO", str(Path(__file__).resolve().parents[1])).rstrip("/\\") + "/"
CACHE = os.environ.get("ADCTOX_CACHE", "/data/hyeongchanahn/adctox/ml_cache").rstrip("/\\") + "/"
