"""Resolve independently installed model bundles; keep the research cache as a fallback."""
import os
from pathlib import Path


def model_home():
    return Path(os.environ.get("ADC_MODEL_HOME") or Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "adctox/models").expanduser()


def active_directory():
    if os.environ.get("ADC_RESEARCH_MODE") == "1":
        return None
    explicit = os.environ.get("ADC_MODEL_DIR")
    if explicit:
        return Path(explicit).expanduser()
    current = model_home() / "current"
    return current if current.is_dir() else None


def model_path(name, fallback):
    directory = active_directory()
    if directory is None:
        return str(fallback)
    path = directory / name
    if not path.exists():
        raise FileNotFoundError(f"Model file missing: {path}. Run adctox --update-models.")
    return str(path)


def encoder_path(name, fallback):
    return model_path(name, fallback)


def bundle_identity():
    directory = active_directory()
    if directory is None:
        return "research-cache"
    import json
    marker = directory / "bundle.json"
    if not marker.exists():
        return str(directory.resolve())
    return json.loads(marker.read_text())["bundle_id"]


def restricted_bundle():
    directory = active_directory()
    return directory is not None and (directory / "bundle.json").is_file()


def load_checkpoint(fallback, device):
    import torch
    path = model_path("vuln_biolord.pt", fallback)
    # Released bundles contain tensors and primitive metadata only. The legacy research
    # cache is a locally generated NumPy pickle, retained for reproducibility.
    checkpoint = torch.load(path, weights_only=restricted_bundle(), map_location=device)
    if checkpoint.get("format_version") == 1:
        for key in ("O", "base", "spread"):
            checkpoint["meta"][key] = checkpoint["meta"][key].cpu().numpy()
    return checkpoint
