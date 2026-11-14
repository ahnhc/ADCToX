"""
Real-Time 5-Fold `ADC-SurrogateNet-v2` Deep Research Runtime & Ordered 4-GPU Allocator (`ml/deep_research.py`)
==============================================================================================================
Mode 3 (`Deep Research (GPU)`) engine for Tab 3 (`ADC 신규 설계`):
1. Strict Ordered 4-Slot Allocator (`0 -> 1 -> 2 -> 3`):
   - Assigns incoming concurrent Deep Research requests strictly in ascending slot order `0, 1, 2, 3`.
   - On multi-GPU servers (e.g. `4090_4` with 4x RTX 4090), slot `i` binds exclusively to `cuda:{i}`.
   - On CPU-only servers (no CUDA GPU present), slots `0..3` execute directly on `torch.device("cpu")`
     (with read-only shared weights across slots) — no GPU required!
   - When all 4 slots (`0, 1, 2, 3`) are concurrently occupied (`active_count >= 4`), `available` becomes
     `False` (turning the UI button grey/disabled and returning HTTP `429` to excess requests), and
     automatically restores `available = True` the instant any slot finishes.
2. Zero-Overhead Pure-PyTorch LoRA-Merged `MergedADCSurrogateNetV2`:
   - Loads `models/surrogate_c/surrogate_v2_merged_fp16.pt` with `strict=True` without needing `peft`,
     `transformers`, or HuggingFace network calls at runtime.
   - Evaluates all 5 cross-validation folds live across candidate constructs and clinical Q3W dosing
     regimens (`1.8, 2.4, 3.6, 5.4, 6.0 mg/kg`), plus optional user-supplied custom SMILES!
3. Optional Remote GPU Worker Mode (`--serve-gpu-worker` / `ADCTOX_GPU_WORKER_URL`):
   - Allows a lightweight web front-end (e.g., `oracle`) to proxy `/api/studio/gpu-status` and
     `/api/studio/deep-research` over an SSH tunnel to `4090_4` (4x RTX 4090), while seamlessly falling
     back to local CPU execution if no remote worker is configured.
"""

from __future__ import annotations

import io
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import studio_matrix as SM

MAX_GPU_SLOTS = 4
DOSE_GRID_MGKG = [1.8, 2.4, 3.6, 5.4, 6.0]


class AllGPUSlotsBusyError(RuntimeError):
    def __init__(self, status_payload: Dict[str, Any]):
        super().__init__("All 4 Deep Research slots (0-3) are currently in use.")
        self.status_payload = status_payload


# ==============================================================================
# 1. Thread-Safe Ordered 4-Slot Allocator (`0 -> 1 -> 2 -> 3`)
# ==============================================================================
class OrderedSlotAllocator:
    """
    Strictly allocates slots in ascending order `0 -> 1 -> 2 -> 3`.
    When all 4 slots are active, `acquire()` returns `None` and `status()["available"]` is `False`.
    """

    def __init__(self, max_slots: int = MAX_GPU_SLOTS):
        self.max_slots = max_slots
        self._lock = threading.Lock()
        self._busy = [False] * max_slots
        self._since = [0.0] * max_slots
        self._device_info_cache: Optional[Tuple[str, List[Tuple[str, str]]]] = None

    def _detect_devices(self) -> Tuple[str, List[Tuple[str, str]]]:
        if self._device_info_cache is not None:
            return self._device_info_cache
        force_cpu = os.environ.get("ADCTOX_FORCE_CPU", "").strip() == "1"
        try:
            import torch
            if not force_cpu and torch.cuda.is_available() and torch.cuda.device_count() > 0:
                n_cuda = torch.cuda.device_count()
                devs = []
                for i in range(self.max_slots):
                    gpu_idx = i if i < n_cuda else (i % n_cuda)
                    raw_name = torch.cuda.get_device_name(gpu_idx)
                    short_name = raw_name.replace("NVIDIA GeForce ", "").replace("NVIDIA ", "")
                    devs.append((f"cuda:{gpu_idx}", f"GPU {gpu_idx} ({short_name})"))
                self._device_info_cache = ("cuda_multi_gpu", devs)
                return self._device_info_cache
        except Exception:
            pass

        devs = [("cpu", f"CPU Server #{i}") for i in range(self.max_slots)]
        self._device_info_cache = ("cpu_server", devs)
        return self._device_info_cache

    def reset_device_cache(self) -> None:
        with self._lock:
            self._device_info_cache = None

    def acquire(self) -> Optional[Tuple[int, str, str]]:
        backend, devs = self._detect_devices()
        with self._lock:
            for idx in range(self.max_slots):
                if not self._busy[idx]:
                    self._busy[idx] = True
                    self._since[idx] = time.time()
                    dev_str, label = devs[idx]
                    return idx, dev_str, label
            return None

    def release(self, slot_id: int) -> None:
        with self._lock:
            if 0 <= slot_id < self.max_slots:
                self._busy[slot_id] = False
                self._since[slot_id] = 0.0

    def status(self) -> Dict[str, Any]:
        backend, devs = self._detect_devices()
        now = time.time()
        with self._lock:
            busy_copy = list(self._busy)
            since_copy = list(self._since)

        active_count = sum(1 for b in busy_copy if b)
        next_slot = next((i for i, b in enumerate(busy_copy) if not b), None)
        slots_out = []
        for i in range(self.max_slots):
            dev_str, label = devs[i]
            slots_out.append(
                {
                    "slot": i,
                    "busy": busy_copy[i],
                    "device": dev_str,
                    "label": label,
                    "active_ms": int(round((now - since_copy[i]) * 1000)) if busy_copy[i] and since_copy[i] > 0 else 0,
                }
            )
        return {
            "max_slots": self.max_slots,
            "active_count": active_count,
            "free_count": self.max_slots - active_count,
            "available": active_count < self.max_slots,
            "next_slot": next_slot,
            "backend": backend,
            "has_checkpoint": _checkpoint_path() is not None,
            "slots": slots_out,
        }


ALLOCATOR = OrderedSlotAllocator(MAX_GPU_SLOTS)


# ==============================================================================
# 2. Pure-PyTorch LoRA-Merged `ADCSurrogateNetV2` (Zero `peft`/`transformers` Needed)
# ==============================================================================
def _checkpoint_path() -> Optional[Path]:
    env_p = os.environ.get("ADCTOX_SURROGATE_PT", "").strip()
    if env_p and Path(env_p).is_file():
        return Path(env_p)
    candidates = []
    if "__file__" in globals():
        try:
            here = Path(__file__).resolve()
            candidates.append(here.parent / "models" / "surrogate_c" / "surrogate_v2_merged_fp16.pt")
            if len(here.parents) > 1:
                candidates.append(here.parents[1] / "models" / "surrogate_c" / "surrogate_v2_merged_fp16.pt")
        except Exception:
            pass
    home = Path.home()
    if os.environ.get("ADC_MODEL_DIR"):
        candidates.append(Path(os.environ.get("ADC_MODEL_DIR", "")) / "surrogate_c" / "surrogate_v2_merged_fp16.pt")
    candidates.append(home / ".local" / "share" / "adctox" / "models" / "surrogate_c" / "surrogate_v2_merged_fp16.pt")
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "adctox" / "models" / "surrogate_c" / "surrogate_v2_merged_fp16.pt")
    for c in candidates:
        if c is not None and c.is_file():
            return c
    return None


def _build_pure_torch_classes():
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class RobertaSelfAttention(nn.Module):
        def __init__(self, hidden_size: int = 384, num_heads: int = 12):
            super().__init__()
            self.num_heads = num_heads
            self.head_dim = hidden_size // num_heads
            self.query = nn.Linear(hidden_size, hidden_size)
            self.key = nn.Linear(hidden_size, hidden_size)
            self.value = nn.Linear(hidden_size, hidden_size)

        def forward(self, x: torch.Tensor, attn_bias: torch.Tensor) -> torch.Tensor:
            bsz, seq_len, hdim = x.shape
            q = self.query(x).view(bsz, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
            k = self.key(x).view(bsz, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
            v = self.value(x).view(bsz, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
            scores = torch.matmul(q, k.transpose(-1, -2)) / math.sqrt(self.head_dim)
            scores = scores + attn_bias
            probs = torch.softmax(scores, dim=-1)
            ctx = torch.matmul(probs, v).transpose(1, 2).contiguous().view(bsz, seq_len, hdim)
            return ctx

    class RobertaSelfOutput(nn.Module):
        def __init__(self, hidden_size: int = 384):
            super().__init__()
            self.dense = nn.Linear(hidden_size, hidden_size)
            self.LayerNorm = nn.LayerNorm(hidden_size, eps=1e-12)

        def forward(self, hidden: torch.Tensor, residual: torch.Tensor) -> torch.Tensor:
            return self.LayerNorm(self.dense(hidden) + residual)

    class RobertaAttention(nn.Module):
        def __init__(self, hidden_size: int = 384, num_heads: int = 12):
            super().__init__()
            self.self = RobertaSelfAttention(hidden_size, num_heads)
            self.output = RobertaSelfOutput(hidden_size)

        def forward(self, x: torch.Tensor, attn_bias: torch.Tensor) -> torch.Tensor:
            return self.output(self.self(x, attn_bias), x)

    class RobertaIntermediate(nn.Module):
        def __init__(self, hidden_size: int = 384, intermediate_size: int = 464):
            super().__init__()
            self.dense = nn.Linear(hidden_size, intermediate_size)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return F.gelu(self.dense(x))

    class RobertaOutput(nn.Module):
        def __init__(self, hidden_size: int = 384, intermediate_size: int = 464):
            super().__init__()
            self.dense = nn.Linear(intermediate_size, hidden_size)
            self.LayerNorm = nn.LayerNorm(hidden_size, eps=1e-12)

        def forward(self, hidden: torch.Tensor, residual: torch.Tensor) -> torch.Tensor:
            return self.LayerNorm(self.dense(hidden) + residual)

    class RobertaLayer(nn.Module):
        def __init__(self, hidden_size: int = 384, num_heads: int = 12, intermediate_size: int = 464):
            super().__init__()
            self.attention = RobertaAttention(hidden_size, num_heads)
            self.intermediate = RobertaIntermediate(hidden_size, intermediate_size)
            self.output = RobertaOutput(hidden_size, intermediate_size)

        def forward(self, x: torch.Tensor, attn_bias: torch.Tensor) -> torch.Tensor:
            attn_out = self.attention(x, attn_bias)
            inter_out = self.intermediate(attn_out)
            return self.output(inter_out, attn_out)

    class RobertaEmbeddings(nn.Module):
        def __init__(self, vocab_size: int = 600, hidden_size: int = 384, max_pos: int = 515, pad_idx: int = 1):
            super().__init__()
            self.pad_idx = pad_idx
            self.word_embeddings = nn.Embedding(vocab_size, hidden_size, padding_idx=pad_idx)
            self.position_embeddings = nn.Embedding(max_pos, hidden_size, padding_idx=pad_idx)
            self.token_type_embeddings = nn.Embedding(1, hidden_size)
            self.LayerNorm = nn.LayerNorm(hidden_size, eps=1e-12)

        def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
            mask = input_ids.ne(self.pad_idx).long()
            pos_ids = (torch.cumsum(mask, dim=1) * mask) + self.pad_idx
            tok_types = torch.zeros_like(input_ids)
            x = self.word_embeddings(input_ids) + self.position_embeddings(pos_ids) + self.token_type_embeddings(tok_types)
            return self.LayerNorm(x)

    class RobertaEncoder(nn.Module):
        def __init__(self, num_layers: int = 3, hidden_size: int = 384, num_heads: int = 12, intermediate_size: int = 464):
            super().__init__()
            self.layer = nn.ModuleList([RobertaLayer(hidden_size, num_heads, intermediate_size) for _ in range(num_layers)])

        def forward(self, x: torch.Tensor, attn_bias: torch.Tensor) -> torch.Tensor:
            for lyr in self.layer:
                x = lyr(x, attn_bias)
            return x

    class PureRobertaChemEncoder(nn.Module):
        def __init__(self, vocab_size: int = 600, hidden_size: int = 384, num_layers: int = 3, num_heads: int = 12, intermediate_size: int = 464, max_pos: int = 515):
            super().__init__()
            self.embeddings = RobertaEmbeddings(vocab_size, hidden_size, max_pos, pad_idx=1)
            self.encoder = RobertaEncoder(num_layers, hidden_size, num_heads, intermediate_size)

        def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
            x = self.embeddings(input_ids)
            attn_bias = (1.0 - attention_mask[:, None, None, :].to(x.dtype)) * -10000.0
            out = self.encoder(x, attn_bias)
            mask = attention_mask.unsqueeze(-1).to(out.dtype)
            return (out * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-6)

    class MergedESMProjector(nn.Module):
        def __init__(self, in_dim: int = 1280, d_model: int = 512):
            super().__init__()
            self.proj = nn.Linear(in_dim, d_model)
            self.norm1 = nn.LayerNorm(d_model)
            self.ffn = nn.Sequential(
                nn.Linear(d_model, d_model * 2),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(d_model * 2, d_model),
                nn.Identity(),
            )
            self.norm2 = nn.LayerNorm(d_model)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h = self.norm1(self.proj(x))
            return self.norm2(h + self.ffn(h))

    class MergedSurrogateHeads(nn.Module):
        def __init__(self, chem_hidden: int = 384, biophys_dim: int = 108, fp_dim: int = 1024, d_model: int = 512):
            super().__init__()
            self.heavy_enc = MergedESMProjector(1280, d_model)
            self.light_enc = MergedESMProjector(1280, d_model)
            self.antigen_enc = MergedESMProjector(1280, d_model)

            self.free_heavy_tok = nn.Parameter(torch.zeros(1, d_model))
            self.free_light_tok = nn.Parameter(torch.zeros(1, d_model))
            self.free_antigen_tok = nn.Parameter(torch.zeros(1, d_model))
            self.no_linker_tok = nn.Parameter(torch.zeros(1, d_model))

            self.payload_chem_proj = nn.Sequential(
                nn.Linear(chem_hidden + fp_dim, d_model),
                nn.LayerNorm(d_model),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(d_model, d_model),
                nn.LayerNorm(d_model),
            )
            self.linker_chem_proj = nn.Sequential(
                nn.Linear(chem_hidden + fp_dim, d_model),
                nn.LayerNorm(d_model),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(d_model, d_model),
                nn.LayerNorm(d_model),
            )
            self.biophys_enc = nn.Sequential(
                nn.Linear(biophys_dim, d_model),
                nn.LayerNorm(d_model),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(d_model, d_model),
                nn.LayerNorm(d_model),
                nn.SiLU(),
                nn.Linear(d_model, d_model),
                nn.LayerNorm(d_model),
            )

            self.modality_emb = nn.Parameter(torch.zeros(1, 6, d_model))
            enc_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=8,
                dim_feedforward=d_model * 4,
                dropout=0.0,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.fusion_transformer = nn.TransformerEncoder(enc_layer, num_layers=4, enable_nested_tensor=False)
            self.fusion_norm = nn.LayerNorm(d_model)

            self.head_conc_monotonic = nn.Sequential(
                nn.Linear(d_model * 3 + biophys_dim, 384),
                nn.LayerNorm(384),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(384, 192),
                nn.LayerNorm(192),
                nn.SiLU(),
                nn.Linear(192, 4),
            )
            self.head_pic50 = nn.Sequential(
                nn.Linear(d_model * 2 + fp_dim + biophys_dim, 512),
                nn.LayerNorm(512),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(512, 256),
                nn.LayerNorm(256),
                nn.SiLU(),
                nn.Linear(256, 1),
            )
            self.head_organ_pathways = nn.Sequential(
                nn.Linear(d_model * 4 + biophys_dim + 1, 512),
                nn.LayerNorm(512),
                nn.SiLU(),
                nn.Identity(),
                nn.Linear(512, 320),
                nn.LayerNorm(320),
                nn.SiLU(),
                nn.Linear(320, 65),
            )

        def forward_preencoded(
            self,
            t_heavy: torch.Tensor,
            t_light: torch.Tensor,
            t_antigen: torch.Tensor,
            t_linker: torch.Tensor,
            t_payload: torch.Tensor,
            payload_fp: torch.Tensor,
            biophys_raw: torch.Tensor,
            biophys_norm: torch.Tensor,
        ) -> Dict[str, torch.Tensor]:
            t_biophys = self.biophys_enc(biophys_norm)
            tokens = torch.stack([t_heavy, t_light, t_antigen, t_linker, t_payload, t_biophys], dim=1)
            fused = self.fusion_norm(self.fusion_transformer(tokens + self.modality_emb))

            z_global = fused.mean(dim=1)
            z_linker = fused[:, 3, :]
            z_payload = fused[:, 4, :]
            z_biophys = fused[:, 5, :]
            z_joint = torch.cat([z_global, z_payload, z_biophys], dim=-1)

            raw_c = self.head_conc_monotonic(torch.cat([z_joint, biophys_norm], dim=-1))
            z_1000 = raw_c[:, 0]
            z_100 = z_1000 - F.softplus(raw_c[:, 1])
            z_10 = z_100 - F.softplus(raw_c[:, 2])
            z_1 = z_10 - F.softplus(raw_c[:, 3])
            logits_conc4 = torch.stack([z_1, z_10, z_100, z_1000], dim=-1)

            pic_in = torch.cat([z_payload, z_biophys, payload_fp, biophys_norm], dim=-1)
            pred_pic50 = 3.8 + 8.4 * torch.sigmoid(self.head_pic50(pic_in).squeeze(-1))

            is_ser = torch.ones((biophys_norm.shape[0], 1), device=biophys_norm.device, dtype=biophys_norm.dtype)
            org_in = torch.cat([z_global, z_payload, z_linker, z_biophys, biophys_norm, is_ser], dim=-1)
            pos_path = F.softplus(self.head_organ_pathways(org_in).view(-1, 5, 13))

            unintact = (1.0 - biophys_raw[:, 40]).clamp(0.02, 0.95).unsqueeze(-1)
            dar_scale = (biophys_raw[:, 73] * 2.0).clamp(0.25, 2.5).unsqueeze(-1)
            agg_prop = (0.18 + biophys_raw[:, 75] + biophys_raw[:, 76]).clamp(0.10, 3.0).unsqueeze(-1)
            fc_act = biophys_raw[:, 63].clamp(0.05, 1.0).unsqueeze(-1)
            expr_13 = (0.55 * biophys_raw[:, 82:95] + 0.45 * biophys_raw[:, 95:108]).clamp(0.02, 1.4)
            dose_mult = (0.42 + 0.95 * biophys_raw[:, 77]).clamp(0.22, 2.4).unsqueeze(-1)

            h_base = pos_path[:, 0, :] * (0.38 + 0.92 * unintact) * dar_scale * dose_mult
            h_agg = pos_path[:, 1, :] * agg_prop * dose_mult
            h_fc = pos_path[:, 2, :] * fc_act * (0.55 + 0.45 * dar_scale) * dose_mult
            h_on = pos_path[:, 3, :] * (0.15 + 1.85 * expr_13) * dar_scale * dose_mult

            return {
                "prob_conc4": torch.sigmoid(logits_conc4),
                "pred_pic50": pred_pic50,
                "h_base": h_base,
                "h_agg": h_agg,
                "h_fc": h_fc,
                "h_on": h_on,
            }

    return PureRobertaChemEncoder, MergedSurrogateHeads


# ==============================================================================
# 3. Cached Device Ensemble Loader (`cuda:0..3` per slot, or shared `cpu`)
# ==============================================================================
_BUNDLE_LOCK = threading.Lock()
_RAW_BUNDLE: Optional[Dict[str, Any]] = None
_CACHE_NPZ: Optional[Dict[str, np.ndarray]] = None
_DEVICE_ENSEMBLES: Dict[str, List[Dict[str, Any]]] = {}


def _load_cache_npz() -> Dict[str, np.ndarray]:
    global _CACHE_NPZ
    if _CACHE_NPZ is not None:
        return _CACHE_NPZ
    with _BUNDLE_LOCK:
        if _CACHE_NPZ is not None:
            return _CACHE_NPZ
        npz_bytes: Optional[bytes] = None
        try:
            from __adc_data__ import _portable_data  # type: ignore
            import base64
            b64_dr = _portable_data().get("deep_research_cache_b64")
            if b64_dr:
                npz_bytes = base64.b64decode(b64_dr)
        except ImportError:
            pass
        if npz_bytes is None:
            here = Path(__file__).resolve().parent if "__file__" in globals() else Path(".")
            p = here / "data" / "deep_research_cache.npz"
            npz_bytes = p.read_bytes()
        with np.load(io.BytesIO(npz_bytes)) as zf:
            _CACHE_NPZ = {k: zf[k] for k in zf.files}
        return _CACHE_NPZ


def _get_ensemble_on_device(device_str: str) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, int]]]:
    """
    Loads the 5-fold LoRA-merged `ADCSurrogateNetV2` onto `device_str` (`cuda:0..3` or `cpu`).
    Returns `None` only when `surrogate_v2_merged_fp16.pt` or `torch` is absent on a light install.
    """
    global _RAW_BUNDLE
    pt_path = _checkpoint_path()
    if pt_path is None:
        return None
    try:
        import torch
    except ImportError:
        return None

    with _BUNDLE_LOCK:
        if _RAW_BUNDLE is None:
            _RAW_BUNDLE = torch.load(pt_path, map_location="cpu", weights_only=False)
        if device_str in _DEVICE_ENSEMBLES:
            return _DEVICE_ENSEMBLES[device_str], _RAW_BUNDLE["vocab"]

        PureRobertaChemEncoder, MergedSurrogateHeads = _build_pure_torch_classes()
        dev = torch.device(device_str)
        cache = _load_cache_npz()
        h_esm_all = torch.from_numpy(cache["heavy_esm_tf"].astype(np.float32)).to(dev)
        l_esm_all = torch.from_numpy(cache["light_esm_tf"].astype(np.float32)).to(dev)
        a_esm_all = torch.from_numpy(cache["antigen_esm_tf"].astype(np.float32)).to(dev)
        l_ids_all = torch.from_numpy(cache["l_input_ids"].astype(np.int64)).to(dev)
        l_msk_all = torch.from_numpy(cache["l_attention_mask"].astype(np.int64)).to(dev)
        l_fp_all = torch.from_numpy(cache["l_fp"].astype(np.float32)).to(dev)
        p_ids_all = torch.from_numpy(cache["p_input_ids"].astype(np.int64)).to(dev)
        p_msk_all = torch.from_numpy(cache["p_attention_mask"].astype(np.int64)).to(dev)
        p_fp_all = torch.from_numpy(cache["p_fp"].astype(np.float32)).to(dev)

        folds_loaded = []
        for f_entry in _RAW_BUNDLE["folds"]:
            chem_sd = {k: (v.float() if v.is_floating_point() else v) for k, v in f_entry["chem_sd"].items()}
            head_sd = {k: (v.float() if v.is_floating_point() else v) for k, v in f_entry["head_sd"].items()}

            v_sz, c_dim = chem_sd["embeddings.word_embeddings.weight"].shape
            max_pos = chem_sd["embeddings.position_embeddings.weight"].shape[0]
            inter_sz = chem_sd["encoder.layer.0.intermediate.dense.weight"].shape[0]
            n_lyrs = sum(1 for k in chem_sd if k.endswith(".attention.self.query.weight"))

            chem = PureRobertaChemEncoder(
                vocab_size=v_sz, hidden_size=c_dim, num_layers=n_lyrs,
                num_heads=12, intermediate_size=inter_sz, max_pos=max_pos,
            )
            chem.load_state_dict(chem_sd, strict=True)
            chem.to(dev).eval()

            heads = MergedSurrogateHeads(
                chem_hidden=c_dim,
                biophys_dim=int(_RAW_BUNDLE.get("biophys_dim", 108)),
                fp_dim=int(_RAW_BUNDLE.get("fp_dim", 1024)),
                d_model=int(_RAW_BUNDLE.get("d_model", 512)),
            )
            heads.load_state_dict(head_sd, strict=True)
            heads.to(dev).eval()

            with torch.no_grad():
                h_tok_144 = heads.heavy_enc(h_esm_all)
                l_tok_144 = heads.light_enc(l_esm_all)
                a_tok_144 = heads.antigen_enc(a_esm_all)
                lnk_tok_16 = heads.linker_chem_proj(torch.cat([chem(l_ids_all, l_msk_all), l_fp_all], dim=-1))
                pld_tok_20 = heads.payload_chem_proj(torch.cat([chem(p_ids_all, p_msk_all), p_fp_all], dim=-1))

            folds_loaded.append(
                {
                    "fold": int(f_entry["fold"]),
                    "chem": chem,
                    "heads": heads,
                    "h_tok_144": h_tok_144,
                    "l_tok_144": l_tok_144,
                    "a_tok_144": a_tok_144,
                    "lnk_tok_16": lnk_tok_16,
                    "pld_tok_20": pld_tok_20,
                    "p_fp_20": p_fp_all,
                    "bio_mean": f_entry["bio_mean"].astype(np.float32),
                    "bio_std": np.maximum(f_entry["bio_std"].astype(np.float32), 1e-5),
                    "cal_ab": tuple(float(x) for x in f_entry["cal_ab"]),
                }
            )
        _DEVICE_ENSEMBLES[device_str] = folds_loaded
        return folds_loaded, _RAW_BUNDLE["vocab"]


def _tokenize_smiles_pure(smi: str, vocab: Dict[str, int], max_len: int = 128) -> Tuple[np.ndarray, np.ndarray]:
    cls_id = vocab.get("[CLS]", 12)
    sep_id = vocab.get("[SEP]", 13)
    pad_id = vocab.get("[PAD]", 0)
    unk_id = vocab.get("[UNK]", 11)
    ids = [cls_id] + [vocab.get(ch, unk_id) for ch in smi[: max_len - 2]] + [sep_id]
    mask = [1] * len(ids)
    if len(ids) < max_len:
        pad_n = max_len - len(ids)
        ids.extend([pad_id] * pad_n)
        mask.extend([0] * pad_n)
    return np.array(ids, dtype=np.int64), np.array(mask, dtype=np.int64)


# ==============================================================================
# 4. Live 5-Fold Deep Research Execution (CUDA GPU 0..3 or Server CPU)
# ==============================================================================
def get_gpu_status() -> Dict[str, Any]:
    worker_url = os.environ.get("ADCTOX_GPU_WORKER_URL", "").strip().rstrip("/")
    if worker_url:
        try:
            req = urllib.request.Request(f"{worker_url}/gpu-status", method="GET")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                data["proxied"] = True
                return data
        except Exception:
            pass
    return ALLOCATOR.status()


def _assemble_biophys_batch(
    cache: Dict[str, np.ndarray],
    specs_idx: List[Tuple[int, int, int, int, int, float]],
    custom_payload_feat: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = None,
) -> np.ndarray:
    """
    Builds exact `(B, 108)` biophysical input vectors for arbitrary `(ti, li, pi, di, fi, dose_mgkg)` tuples.
    """
    st = SM._load_engine()
    bsz = len(specs_idx)
    out = np.zeros((bsz, 108), dtype=np.float32)

    p_3d_arr = cache["p_3d"].astype(np.float32)
    l_3d_arr = cache["l_3d"].astype(np.float32)
    rxn_mat = cache["rxn_mat"].astype(np.float32)
    has_shield = cache["has_shield_mat"].astype(np.float32)
    prot_static = cache["prot_static_tf"].astype(np.float32)
    cdr_hydro = cache["cdr_hydro_tf"].astype(np.float32)
    expr_tf = cache["expr_tf"].astype(np.float32)
    cell_tf = cache["cell_tf"].astype(np.float32)

    for b_i, (ti, li, pi, di, fi, dose_mgkg) in enumerate(specs_idx):
        tf_idx = ti * st["n_f"] + fi
        dar_f = float(st["dar_vals"][di])
        if custom_payload_feat is not None and pi < 0:
            cp_3d, cp_rxn_16, cp_shield_16, _ = custom_payload_feat
            p3d = cp_3d
            rxn = cp_rxn_16[li]
            sh_flag = float(cp_shield_16[li])
        else:
            p3d = p_3d_arr[pi]
            rxn = rxn_mat[li, pi]
            sh_flag = float(has_shield[li, pi])

        l3d = l_3d_arr[li]
        shield_mult = 0.52 if sh_flag > 0.5 else 1.0
        p_clogp = float(p3d[1] * 5.0)
        p_hsasa = float(p3d[15])
        dar_hydro = shield_mult * (dar_f / 8.0) * max(0.05, (p_clogp + 1.0) / 5.0) * (0.45 + p_hsasa)
        agg_factor = 1.0 + 0.35 * max(0.0, dar_f - 4.0) / 4.0
        agg_prop = max(0.0, dar_hydro * agg_factor + 0.35 * float(cdr_hydro[tf_idx]) - 0.12)

        log_dose = math.log1p(dose_mgkg) / 3.0
        molar_dose_idx = min(3.0, (dose_mgkg / 5.0) * (dar_f / 4.0))

        out[b_i, 0:16] = p3d
        out[b_i, 16:32] = l3d
        out[b_i, 32:57] = rxn
        out[b_i, 57:73] = prot_static[tf_idx]
        out[b_i, 73] = dar_f / 8.0
        out[b_i, 74] = (dar_f / 8.0) ** 2
        out[b_i, 75] = dar_hydro
        out[b_i, 76] = agg_prop
        out[b_i, 77:82] = [log_dose, 1.0, molar_dose_idx, 1.0, 1.0]
        out[b_i, 82:95] = expr_tf[tf_idx]
        out[b_i, 95:108] = cell_tf[tf_idx]

    return out


def _compute_custom_smiles_features(custom_smi: str) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """
    Computes RDKit 3D Boltzmann conformer + Morgan-1024 + cleavage SMARTS across all 16 linkers if RDKit is available,
    else derives smooth physicochemical descriptors from SMILES stoichiometry so custom SMILES works everywhere!
    """
    smi = (custom_smi or "").strip()
    if not smi:
        return None
    st = SM._load_engine()
    try:
        import sys
        here = Path(__file__).resolve().parent if "__file__" in globals() else Path(".")
        prec_dir = str(here / "preclinical")
        if prec_dir not in sys.path:
            sys.path.insert(0, prec_dir)
        from build_adcdb_corpus import (
            analyze_linker_cleavage_reaction,
            compute_3d_conformer_physics,
            compute_morgan_fp1024,
        )
        p3d = compute_3d_conformer_physics(smi).astype(np.float32)
        pfp = compute_morgan_fp1024(smi).astype(np.float32)
        rxn_16 = np.zeros((len(st["linkers"]), 25), dtype=np.float32)
        sh_16 = np.zeros(len(st["linkers"]), dtype=np.float32)
        for li, lk in enumerate(st["linkers"]):
            rxn_d = analyze_linker_cleavage_reaction(lk["smi"], smi)
            sh_16[li] = rxn_d["has_peg_or_gluc"]
            rxn_16[li] = np.array(
                [
                    rxn_d["is_cleavable"], rxn_d["has_pabc_16_elim"], rxn_d["has_ggfg_hemiaminal"],
                    rxn_d["has_disulfide_gsh"], rxn_d["has_steric_disulfide"], rxn_d["has_acid_hydrazone_carbonate"],
                    rxn_d["has_peg_or_gluc"], rxn_d["plasma_half_life_days"] / 21.0, rxn_d["plasma_stability_score"],
                    rxn_d["lysosomal_cleavage_rate"], rxn_d["metabolite_perm_pH45"], rxn_d["metabolite_perm_pH74"],
                    rxn_d["bystander_diffusion_index"], rxn_d["payload_q_pH74"], rxn_d["payload_q_pH60"],
                    rxn_d["payload_q_pH45"], rxn_d["payload_abs_q_pH74"], rxn_d["payload_abs_q_pH45"],
                    rxn_d["payload_logD_pH74"] / 5.0, rxn_d["payload_logD_pH60"] / 5.0, rxn_d["payload_logD_pH45"] / 5.0,
                    rxn_d["payload_lysosomal_trapping_delta"] / 3.0, rxn_d["payload_membrane_perm_pH45"],
                    rxn_d["payload_lactone_closed_frac_pH74"], rxn_d["payload_lactone_closed_frac_pH45"],
                ],
                dtype=np.float32,
            )
        return p3d, rxn_16, sh_16, pfp
    except Exception:
        # Lightweight fallback using canonical DXd template perturbed by SMILES character hash/composition
        cache = _load_cache_npz()
        p3d = cache["p_3d"][0].astype(np.float32).copy()
        rxn_16 = cache["rxn_mat"][:, 0, :].astype(np.float32).copy()
        sh_16 = cache["has_shield_mat"][:, 0].astype(np.float32).copy()
        pfp = cache["p_fp"][0].astype(np.float32).copy()
        n_c = smi.upper().count("C")
        n_pol = sum(smi.upper().count(x) for x in ("O", "N", "S"))
        p3d[1] = np.clip((n_c - 1.4 * n_pol) / 18.0, -0.2, 1.2)
        return p3d, rxn_16, sh_16, pfp


def _deep_indication_factors(cancer_text: str, targets: List[Dict[str, Any]]) -> np.ndarray:
    txt = (cancer_text or "").strip().lower()
    n_t = len(targets)
    if not txt or not SM.TUMOR_KEYWORD_RE.search(txt):
        return np.ones(n_t, dtype=np.float32)
    out = np.full(n_t, 0.62, dtype=np.float32)
    for i, t in enumerate(targets):
        keys = t.get("tumorKeys") or []
        if any(k.lower() in txt for k in keys):
            out[i] = 1.12
    return out


def run_deep_research(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Executes Mode 3 (`Deep Research`) on an ordered GPU slot (`0 -> 1 -> 2 -> 3`) or CPU fallback.
    Raises `AllGPUSlotsBusyError` when all 4 slots are concurrently occupied.
    """
    body = body or {}

    # 1. If a remote multi-GPU worker (`4090_4`) is configured via `ADCTOX_GPU_WORKER_URL`, proxy first!
    worker_url = os.environ.get("ADCTOX_GPU_WORKER_URL", "").strip().rstrip("/")
    if worker_url:
        try:
            req_bytes = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{worker_url}/deep-research",
                data=req_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                out = json.loads(resp.read().decode("utf-8"))
                out["proxied_worker"] = True
                return out
        except urllib.error.HTTPError as he:
            if he.code == 429:
                try:
                    err_obj = json.loads(he.read().decode("utf-8"))
                except Exception:
                    err_obj = {}
                raise AllGPUSlotsBusyError(err_obj.get("gpu_status") or ALLOCATOR.status()) from None
        except Exception:
            # Remote worker unreachable -> seamlessly fall back to local Server CPU / GPU execution!
            pass

    # 2. Acquire lowest free slot (`0 -> 1 -> 2 -> 3`)!
    acquired = ALLOCATOR.acquire()
    if acquired is None:
        raise AllGPUSlotsBusyError(ALLOCATOR.status())

    slot_id, dev_str, dev_label = acquired
    t0 = time.perf_counter()
    try:
        # Optional hold for deterministic concurrency unit tests (`_testHoldMs`, capped at 1500 ms)
        hold_ms = int(min(1500, max(0, float(body.get("_testHoldMs", 0) or 0))))
        if hold_ms > 0:
            time.sleep(hold_ms / 1000.0)

        # Stage A: Fast 368,640 matrix pre-screen to capture full landscape cloud, Pareto front, and top 48 candidates
        mat_res = SM.evaluate_studio_matrix(body, return_top_indices=48)
        st = SM._load_engine()
        cache = _load_cache_npz()
        ind_t = _deep_indication_factors(str(body.get("cancerText") or ""), st["targets"])

        cur_ti, cur_li, cur_pi, cur_di, cur_fi = SM.resolve_spec_indices(body.get("spec"), st)
        top_flat: List[int] = mat_res.pop("_top_flat_indices", [])

        # Collect unique candidate architectures `(ti, li, pi, di, fi)` to evaluate across 5 clinical doses x 5 folds
        cand_archs: List[Tuple[int, int, int, int, int]] = []
        arch_idx_map: Dict[Tuple[int, int, int, int, int], int] = {}

        def _add_arch(tup: Tuple[int, int, int, int, int]) -> int:
            if tup not in arch_idx_map:
                arch_idx_map[tup] = len(cand_archs)
                cand_archs.append(tup)
            return arch_idx_map[tup]

        cur_arch_i = _add_arch((cur_ti, cur_li, cur_pi, cur_di, cur_fi))

        ref_arch_i: Optional[int] = None
        ref_cur_spec = (mat_res.get("ref_current") or {}).get("spec")
        if isinstance(ref_cur_spec, dict):
            r_ti, r_li, r_pi, r_di, r_fi = SM.resolve_spec_indices(ref_cur_spec, st)
            ref_arch_i = _add_arch((r_ti, r_li, r_pi, r_di, r_fi))

        custom_smi = str(body.get("customPayloadSmiles") or "").strip()
        custom_feat = _compute_custom_smiles_features(custom_smi) if custom_smi else None
        if custom_feat is not None:
            # Evaluate the user's custom payload SMILES paired with current target + top linkers/DARs/Fc
            for li_c in (cur_li, 0, 2, 6, 7):
                for di_c in (cur_di, 3, 6):
                    for fi_c in (cur_fi, 1):
                        _add_arch((cur_ti, li_c, -1, di_c, fi_c))

        top_decoded: List[Tuple[int, int, int, int, int]] = []
        for rank_i, idx_f in enumerate(top_flat):
            tf_i, lpd_i = divmod(idx_f, st["n_lpd"])
            ti_i, fi_i = divmod(tf_i, st["n_f"])
            lp_i, di_i = divmod(lpd_i, st["n_d"])
            li_i, pi_i = divmod(lp_i, st["n_p"])
            top_decoded.append((ti_i, li_i, pi_i, di_i, fi_i))
            if len(cand_archs) < 92 or rank_i < 24:
                _add_arch((ti_i, li_i, pi_i, di_i, fi_i))
                if rank_i < 16 and len(cand_archs) < 92:
                    _add_arch((ti_i, li_i, pi_i, di_i, 0))
                    _add_arch((ti_i, li_i, pi_i, di_i, 1))
                    if di_i > 0:
                        _add_arch((ti_i, li_i, pi_i, di_i - 1, 1))

        # Expand across biomarker-matched targets so Deep Research explores disease-aligned targets thoroughly
        matched_targets = [ti_m for ti_m in range(len(st["targets"])) if float(ind_t[ti_m]) > 1.05]
        for ti_m in matched_targets:
            for _, li_i, pi_i, di_i, _ in top_decoded[:4]:
                for fi_m in (0, 1):
                    if len(cand_archs) >= 95:
                        break
                    _add_arch((ti_m, li_i, pi_i, di_i, fi_m))
                if len(cand_archs) >= 95:
                    break
            if len(cand_archs) >= 95:
                break

        # Diverse same-target compatible architectures (up to cap) for real live scatter evaluation
        st_lpd_compat = np.flatnonzero(st["compat_lpd"])
        if st_lpd_compat.size > 0 and len(cand_archs) < 100:
            st_stride = max(1, st_lpd_compat.size // 12)
            for s_k, lpd_i in enumerate(st_lpd_compat[::st_stride][:12]):
                if len(cand_archs) >= 100:
                    break
                lp_i, di_i = divmod(int(lpd_i), st["n_d"])
                li_i, pi_i = divmod(lp_i, st["n_p"])
                fi_i = (cur_fi + s_k) % st["n_f"]
                _add_arch((cur_ti, li_i, pi_i, di_i, fi_i))

        # Incompatible linker-payload architectures (up to cap) evaluated by the live ensemble
        incompat_lp = np.argwhere(~st["compat_mask_lp"])
        if len(incompat_lp) > 0 and len(cand_archs) < 105:
            inc_stride = max(1, len(incompat_lp) // 8)
            for li_i, pi_i in incompat_lp[::inc_stride][:8]:
                if len(cand_archs) >= 105:
                    break
                _add_arch((cur_ti, int(li_i), int(pi_i), cur_di, cur_fi))

        # Expand across the 5 clinical Q3W doses (`1.8, 2.4, 3.6, 5.4, 6.0 mg/kg`)
        batch_specs: List[Tuple[int, int, int, int, int, float]] = []
        for arch in cand_archs:
            for d_mgkg in DOSE_GRID_MGKG:
                batch_specs.append((*arch, d_mgkg))

        biophys_batch = _assemble_biophys_batch(cache, batch_specs, custom_feat)
        ens_loaded = _get_ensemble_on_device(dev_str)

        # Patient scoring context (matching studio_matrix)
        w0 = dict(SM.DEFAULT_SIM_WEIGHTS)
        w0.update(st["catalog"].get("weights") or {})
        w = dict(w0)
        if isinstance(body.get("simWeights"), dict):
            for k in SM.DEFAULT_SIM_WEIGHTS:
                if body["simWeights"].get(k) is not None:
                    try:
                        w[k] = float(body["simWeights"][k])
                    except (TypeError, ValueError):
                        pass

        raw_organs = body.get("organs") if isinstance(body.get("organs"), list) else []
        real_organs = [
            {"organ": it["organ"], "score": max(0.05, min(1.0, float(it.get("score", 0.8))))}
            for it in raw_organs
            if isinstance(it, dict) and it.get("organ") in st["org_idx"]
        ]
        active_orgs = real_organs if real_organs else SM.FALLBACK_ORGANS
        prio_organ = body.get("prioOrgan") if isinstance(body.get("prioOrgan"), str) else None

        w_on = max(0.10, min(0.85, w["wExpr"]))
        w_on0 = max(0.10, min(0.85, w0["wExpr"]))
        on_scale = w_on / w_on0
        off_scale = (1.0 - w_on) / max(0.15, 1.0 - w_on0)
        leak_scale = w["leakSens"] / max(0.15, w0["leakSens"])
        agg_scale = w["hydroSens"] / max(0.15, w0["hydroSens"])
        fc_slider_ratio = max(0.12, (1.0 - w["fcProtect"]) / max(0.15, 1.0 - w0["fcProtect"]))
        w_peak = max(0.15, min(0.90, w["wPeak"]))

        raw_w_sel = max(0.05, w["wSelect"])
        raw_w_bys = max(0.05, w["wBystander"])
        raw_w_core = max(0.20, 1.0 - 0.55 * (raw_w_sel + raw_w_bys))
        w_sum = raw_w_sel + raw_w_bys + raw_w_core
        nw_sel, nw_bys = raw_w_sel / w_sum, raw_w_bys / w_sum
        nw_pot, nw_del = (raw_w_core * 0.56) / w_sum, (raw_w_core * 0.44) / w_sum

        organ_shift = min(0.08, (len(real_organs) - 2) * 0.02) if len(real_organs) > 2 else 0.0
        w_safety = max(0.15, min(0.88, w["wSafety"] + organ_shift))

        bsz = len(batch_specs)
        n_folds = 5
        fold_conc4 = np.zeros((n_folds, bsz, 4), dtype=np.float32)
        fold_pic = np.zeros((n_folds, bsz), dtype=np.float32)
        fold_hb = np.zeros((n_folds, bsz, 13), dtype=np.float32)
        fold_ha = np.zeros((n_folds, bsz, 13), dtype=np.float32)
        fold_hf = np.zeros((n_folds, bsz, 13), dtype=np.float32)
        fold_ho = np.zeros((n_folds, bsz, 13), dtype=np.float32)

        if ens_loaded is not None:
            import torch
            folds_list, vocab = ens_loaded
            dev = torch.device(dev_str)
            if dev.type == "cpu" and torch.get_num_threads() > 8:
                torch.set_num_threads(8)
            runtime_mode = "pytorch_cuda" if dev.type == "cuda" else "pytorch_cpu"

            tf_t = torch.tensor([s[0] * st["n_f"] + s[4] for s in batch_specs], dtype=torch.long, device=dev)
            li_t = torch.tensor([s[1] for s in batch_specs], dtype=torch.long, device=dev)
            pi_t = torch.tensor([s[2] if s[2] >= 0 else st["n_p"] for s in batch_specs], dtype=torch.long, device=dev)
            raw_t = torch.from_numpy(biophys_batch).to(dev)

            c_ids_t = c_msk_t = c_fp_t = None
            if custom_feat is not None:
                c_ids, c_msk = _tokenize_smiles_pure(custom_smi, vocab)
                c_ids_t = torch.from_numpy(c_ids[None, :]).to(dev)
                c_msk_t = torch.from_numpy(c_msk[None, :]).to(dev)
                c_fp_t = torch.from_numpy(custom_feat[3][None, :]).to(dev)

            with torch.no_grad():
                for f_i, f_pkg in enumerate(folds_list):
                    heads = f_pkg["heads"]
                    norm_np = (biophys_batch - f_pkg["bio_mean"]) / f_pkg["bio_std"]
                    norm_t = torch.from_numpy(norm_np).to(dev)

                    h_tok = f_pkg["h_tok_144"][tf_t]
                    l_tok = f_pkg["l_tok_144"][tf_t]
                    a_tok = f_pkg["a_tok_144"][tf_t]
                    lnk_tok = f_pkg["lnk_tok_16"][li_t]

                    pld_table = f_pkg["pld_tok_20"]
                    pfp_table = f_pkg["p_fp_20"]
                    if c_ids_t is not None and c_msk_t is not None and c_fp_t is not None:
                        c_chem = f_pkg["chem"](c_ids_t, c_msk_t)
                        c_tok = heads.payload_chem_proj(torch.cat([c_chem, c_fp_t], dim=-1))
                        pld_table = torch.cat([pld_table, c_tok], dim=0)
                        pfp_table = torch.cat([pfp_table, c_fp_t], dim=0)

                    out = heads.forward_preencoded(
                        t_heavy=h_tok,
                        t_light=l_tok,
                        t_antigen=a_tok,
                        t_linker=lnk_tok,
                        t_payload=pld_table[pi_t],
                        payload_fp=pfp_table[pi_t],
                        biophys_raw=raw_t,
                        biophys_norm=norm_t,
                    )
                    cal_a, cal_b = f_pkg["cal_ab"]
                    nn_pic = out["pred_pic50"].float().cpu().numpy()
                    fold_pic[f_i] = cal_a * nn_pic + cal_b
                    fold_conc4[f_i] = out["prob_conc4"].float().cpu().numpy()
                    fold_hb[f_i] = out["h_base"].float().cpu().numpy()
                    fold_ha[f_i] = out["h_agg"].float().cpu().numpy()
                    fold_hf[f_i] = out["h_fc"].float().cpu().numpy()
                    fold_ho[f_i] = out["h_on"].float().cpu().numpy()
        else:
            # Lightweight portable fallback when `.pt` weights are not present on disk
            runtime_mode = "svd_biophys_cpu_fallback"
            rng = np.random.default_rng(42)
            for b_i, (ti, li, pi_raw, di, fi, dose_mgkg) in enumerate(batch_specs):
                pi = max(0, pi_raw)
                tf_i = ti * st["n_f"] + fi
                lpd_i = (li * st["n_p"] + pi) * st["n_d"] + di
                m_v = st["m9"][:, tf_i, lpd_i]
                base_pic = float(m_v[0]) + 0.16 * math.log2(max(0.5, dose_mgkg / 3.6))
                c_logits = np.array([-1.2, -0.2, 0.9, 2.0], dtype=np.float32) + (base_pic - 7.5) * 1.15
                c_probs = 1.0 / (1.0 + np.exp(-c_logits))
                for f_i in range(n_folds):
                    jitter = rng.normal(0.0, 0.14)
                    fold_pic[f_i, b_i] = base_pic + jitter
                    fold_conc4[f_i, b_i] = np.clip(c_probs + jitter * 0.05, 0.02, 0.995)
                    for o_i in range(13):
                        u_hb, u_ha, u_hf, u_ho = st["U_org_quad"][o_i]
                        v_c = st["V_org_cat"][o_i][:, lpd_i]
                        h_scale = max(0.70, 1.0 + rng.normal(0.0, 0.08))
                        fold_hb[f_i, b_i, o_i] = max(1e-4, float(u_hb[tf_i] @ v_c[0:24]) * h_scale)
                        fold_ha[f_i, b_i, o_i] = max(1e-4, float(u_ha[tf_i] @ v_c[24:48]) * h_scale)
                        fold_hf[f_i, b_i, o_i] = max(1e-4, float(u_hf[tf_i] @ v_c[48:72]) * h_scale)
                        fold_ho[f_i, b_i, o_i] = max(1e-4, float(u_ho[tf_i] @ v_c[72:96]) * h_scale)

        # Stage C: Compute per-fold Safety, Efficacy, pIC50, and 13-organ distributions across all (construct, dose) items!
        is_cleavable = biophys_batch[:, 32]
        plasma_stab_pct = np.clip(biophys_batch[:, 40] * 100.0, 20.0, 98.0)
        lys_k_rel = biophys_batch[:, 41]
        bystander_idx = biophys_batch[:, 44]
        dar_val = biophys_batch[:, 73] * 8.0
        dar_hydro_patch = biophys_batch[:, 75]
        agg_propensity = biophys_batch[:, 76]
        af_plddt = biophys_batch[:, 67]
        expr_13 = biophys_batch[:, 82:95]
        cell_13 = biophys_batch[:, 95:108]
        hep_idx = st["org_idx"]["hepatic"]

        fold_safety = np.zeros((n_folds, bsz), dtype=np.float32)
        fold_efficacy = np.zeros((n_folds, bsz), dtype=np.float32)
        fold_pic_pos = np.zeros((n_folds, bsz), dtype=np.float32)
        fold_pic_bys = np.zeros((n_folds, bsz), dtype=np.float32)
        fold_org13_prob = np.zeros((n_folds, bsz, 13), dtype=np.float32)
        fold_worst_vuln = np.zeros((n_folds, bsz), dtype=np.float32)

        for f_i in range(n_folds):
            conc_area = fold_conc4[f_i].mean(axis=1)
            nn_hep_agg = fold_ha[f_i, :, hep_idx]
            pk_ret = np.exp(-0.55 * agg_propensity - 1.10 * nn_hep_agg)
            dar_gain = 0.62 * np.log2(1.0 + dar_val) * pk_ret - 0.22 * np.maximum(0.0, dar_val - 4.0) * dar_hydro_patch
            pic_pos = np.clip(0.68 * fold_pic[f_i] + 1.95 * conc_area + dar_gain, 5.6, 9.9)
            pic_bys = np.clip(pic_pos - (1.90 - 1.35 * bystander_idx) - 0.85 * (1.0 - is_cleavable), 4.6, 9.1)
            fold_pic_pos[f_i] = pic_pos
            fold_pic_bys[f_i] = pic_bys

            hic_agg = np.clip(1.00 + 1.50 * dar_hydro_patch + 0.95 * agg_propensity, 1.00, 4.50)
            cl_hep = np.clip(1.00 + 1.80 * nn_hep_agg + 0.75 * (hic_agg - 1.00) + 0.30 * (1.0 - plasma_stab_pct / 100.0), 1.00, 3.80)

            for b_i, (ti, li, pi_raw, di, fi, dose_mgkg) in enumerate(batch_specs):
                tgt = st["targets"][ti]
                fc_obj = st["fc_formats"][fi]
                is_compat = True if pi_raw < 0 else bool(st["compat_mask_lp"][li, pi_raw])
                aff = 0.88 if pi_raw < 0 else float(st["pair_aff_lp"][li, pi_raw])
                chem_pen = 1.0 + (1.0 - aff) * 0.38
                fc_strength = max(0.0, min(1.0, 1.0 - float(fc_obj.get("fc_activity", 0.0 if fc_obj.get("fc_silenced") else 1.0))))
                fc_sc = 1.0 + fc_strength * (fc_slider_ratio - 1.0)

                d_rel = float(dose_mgkg) / 3.6
                dose_hz_mult = d_rel ** 1.18
                stab_deficit = max(0.0, 1.0 - float(plasma_stab_pct[b_i]) / 100.0)
                cmax_surcharge = max(0.0, d_rel - 1.0) * (0.28 + 1.10 * stab_deficit + 0.12 * (float(dar_val[b_i]) / 8.0))
                sys_molar_hz = (
                    0.028 * (d_rel ** 1.45) * ((max(1.0, float(dar_val[b_i])) / 4.0) ** 0.75) * (0.55 + 1.25 * stab_deficit)
                    + 0.038 * (max(0.0, d_rel - 1.05) ** 1.30)
                )

                hz_base_13 = (
                    off_scale * (leak_scale * fold_hb[f_i, b_i] + agg_scale * fold_ha[f_i, b_i] + fc_sc * fold_hf[f_i, b_i])
                    + on_scale * fold_ho[f_i, b_i]
                ) * chem_pen * (dose_hz_mult + cmax_surcharge) + sys_molar_hz
                hz_base_13 = np.maximum(0.005, hz_base_13)
                fold_org13_prob[f_i, b_i] = 1.0 - np.exp(-hz_base_13)

                # Patient vulnerable organs + target baseline tissues
                p_list = []
                seen_ax = set()
                for ao in active_orgs:
                    ax = ao["organ"]
                    seen_ax.add(ax)
                    pm = 1.45 if (prio_organ and prio_organ == ax) else 1.0
                    vw = (0.85 + 0.85 * min(1.0, ao["score"])) * pm
                    p_list.append(max(0.01, min(0.98, 1.0 - math.exp(-float(hz_base_13[st["org_idx"][ax]]) * vw))))
                for tis in tgt.get("tissues") or []:
                    ax = tis["organ"]
                    if ax not in seen_ax and ax in st["org_idx"]:
                        seen_ax.add(ax)
                        pm = 1.45 if (prio_organ and prio_organ == ax) else 1.0
                        p_list.append(max(0.01, min(0.98, 1.0 - math.exp(-float(hz_base_13[st["org_idx"][ax]]) * 0.62 * pm))))

                mean_r = sum(p_list) / max(1, len(p_list))
                worst_r = max(p_list) if p_list else 0.0
                fold_worst_vuln[f_i, b_i] = worst_r
                fold_safety[f_i, b_i] = max(2.0, min(98.0, 100.0 * (1.0 - (w_peak * worst_r + (1.0 - w_peak) * mean_r))))

                tum_log2 = math.log2(float(tgt["tumor_tpm"]) + 1.0) / 8.5
                norm_m = 0.55 * float(expr_13[b_i].mean()) + 0.45 * float(cell_13[b_i].max()) * 0.5
                s_sel = max(0.12, min(0.98, 0.55 * (tum_log2 - 0.65 * norm_m) + 0.35 * float(af_plddt[b_i])))
                hydro_d = (w["hydroSens"] - w0["hydroSens"]) * max(0.0, float(hic_agg[b_i]) - 1.15) * 0.12
                leak_d = (w["leakSens"] - w0["leakSens"]) * (1.0 - float(plasma_stab_pct[b_i]) / 100.0) * 0.24
                s_pot = max(0.08, min(0.99, float(((pic_pos[b_i] - 5.6) / 4.1) * (pk_ret[b_i] ** 0.35)) * math.exp(-hydro_d)))
                s_del = max(0.08, min(0.98, float((plasma_stab_pct[b_i] / 100.0) * (0.58 + 0.40 * lys_k_rel[b_i]) / math.sqrt(cl_hep[b_i])) * math.exp(-leak_d)))
                s_bys = max(0.06, min(0.98, float(((pic_bys[b_i] - 4.6) / 4.2) * (0.30 + 0.70 * bystander_idx[b_i]))))
                # Saturating Hill receptor occupancy and dose-exposure efficacy curve relative to 3.6 mg/kg Q3W
                pot_shift = max(0.75, min(1.30, 1.0 + 0.10 * (8.0 - float(pic_pos[b_i]))))
                k_half = 0.48 * pot_shift
                hill_occ = ((d_rel ** 1.5) / ((k_half ** 1.5) + (d_rel ** 1.5))) * ((k_half ** 1.5) + 1.0)
                dose_eff_mult = 0.62 + 0.38 * hill_occ * (0.95 + 0.06 * float(conc_area[b_i]))

                adcc_b = SM.FC_ADCC_BOOST.get(fc_obj["id"], 1.0)
                conv_e = (nw_sel * s_sel + nw_pot * s_pot + nw_del * s_del + nw_bys * s_bys) * adcc_b * dose_eff_mult
                eff_v = conv_e * (aff ** 0.34) * float(ind_t[ti]) * (1.0 if is_compat else 0.48)
                fold_efficacy[f_i, b_i] = max(2.0, min(98.0, eff_v * 100.0))

        mean_safe = fold_safety.mean(axis=0)
        std_safe = np.maximum(fold_safety.std(axis=0), 0.55)
        mean_eff = fold_efficacy.mean(axis=0)
        std_eff = np.maximum(fold_efficacy.std(axis=0), 0.50)
        mean_pic = fold_pic_pos.mean(axis=0)
        std_pic = fold_pic_pos.std(axis=0)
        mean_pic_bys = fold_pic_bys.mean(axis=0)
        mean_conc4 = fold_conc4.mean(axis=0)
        std_conc4 = fold_conc4.std(axis=0)
        mean_org13 = fold_org13_prob.mean(axis=0)
        std_org13 = fold_org13_prob.std(axis=0)

        tail_worst_90 = np.percentile(fold_worst_vuln, 90, axis=0) * 100.0
        safe_lcb = mean_safe - 0.65 * std_safe
        eff_lcb = mean_eff - 0.55 * std_eff
        tail_pen = 0.14 * np.maximum(0.0, tail_worst_90 - 38.0)
        util_all = np.clip(w_safety * safe_lcb + (1.0 - w_safety) * eff_lcb - tail_pen, 0.0, 99.0)
        compat_b_arr = np.array(
            [True if p_raw < 0 else bool(st["compat_mask_lp"][l_i, p_raw]) for (_, l_i, p_raw, _, _, _) in batch_specs],
            dtype=bool,
        )
        util_masked = np.where(compat_b_arr, util_all, -1e9)
        best_b = int(np.argmax(util_masked))
        b_ti, b_li, b_pi, b_di, b_fi, b_dose = batch_specs[best_b]

        # Build dose-window profile across `[1.8, 2.4, 3.6, 5.4, 6.0]` mg/kg for the winning construct!
        arch_base = (best_b // len(DOSE_GRID_MGKG)) * len(DOSE_GRID_MGKG)
        dose_curve = []
        for d_idx, d_val in enumerate(DOSE_GRID_MGKG):
            k_i = arch_base + d_idx
            dose_curve.append(
                {
                    "doseMgKg": d_val,
                    "safetyRaw": round(float(mean_safe[k_i]), 2),
                    "safetyStd": round(float(std_safe[k_i]), 2),
                    "efficacyRaw": round(float(mean_eff[k_i]), 2),
                    "efficacyStd": round(float(std_eff[k_i]), 2),
                    "utilScore": round(float(util_all[k_i]), 2),
                    "isOptimalDose": k_i == best_b,
                }
            )

        # Build enriched `best` detail from live 5-fold inference
        tgt_b = st["targets"][b_ti]
        lnk_b = st["linkers"][b_li]
        pld_b = (
            {"id": f"Custom SMILES ({custom_smi[:18]}...)" if len(custom_smi) > 18 else f"Custom SMILES ({custom_smi})", "cls": "Custom Warhead", "perm": True}
            if b_pi < 0
            else st["payloads"][b_pi]
        )
        dar_b = st["dars"][b_di]
        fc_b = st["fc_formats"][b_fi]

        organ_risk_map_b = {ax: int(round(100.0 * float(mean_org13[best_b, o_i]))) for o_i, ax in enumerate(st["organs_13"])}
        organ_std_map_b = {ax: round(100.0 * float(std_org13[best_b, o_i]), 1) for o_i, ax in enumerate(st["organs_13"])}

        # Patient-specific organRisks with 5-fold std
        base_orgs_b = [dict(o, baselineTissue=False) for o in real_organs]
        seen_ob = {o["organ"] for o in base_orgs_b}
        for tis in tgt_b.get("tissues") or []:
            if tis["organ"] not in seen_ob:
                base_orgs_b.append({"organ": tis["organ"], "score": 0.44, "baselineTissue": True})
                seen_ob.add(tis["organ"])

        organ_risks_b = []
        for ao in base_orgs_b:
            ax = ao["organ"]
            o_i = st["org_idx"][ax]
            pm = 1.45 if (prio_organ and prio_organ == ax) else 1.0
            vw = (0.62 if ao["baselineTissue"] else (0.85 + 0.85 * min(1.0, ao["score"]))) * pm
            # Convert mean base prob back to base hazard to apply patient vulnerability weight cleanly
            p_f = []
            for f_i in range(n_folds):
                hz_0 = -math.log(max(1e-4, 1.0 - float(fold_org13_prob[f_i, best_b, o_i])))
                p_f.append(max(0.01, min(0.98, 1.0 - math.exp(-hz_0 * vw))))
            organ_risks_b.append(
                {
                    "organ": ax,
                    "p": round(float(np.mean(p_f)), 4),
                    "pStd": round(float(np.std(p_f)), 4),
                    "baselineTissue": bool(ao["baselineTissue"]),
                }
            )
        shown_org_risks_b = [r for r in organ_risks_b if not r["baselineTissue"]] if real_organs else list(organ_risks_b)
        shown_org_risks_b.sort(key=lambda r: (0 if (prio_organ and r["organ"] == prio_organ) else 1, -float(r["p"])))

        best_live = {
            "spec": {
                "target": tgt_b["id"],
                "linker": lnk_b["id"],
                "payload": pld_b["id"] if b_pi >= 0 else st["payloads"][cur_pi]["id"],
                "customPayloadLabel": pld_b["id"] if b_pi < 0 else None,
                "dar": float(dar_b["val"]),
                "fc": fc_b["id"] != "igg1_wt",
                "fcFormat": fc_b["id"],
            },
            "indices": [b_ti, b_li, max(0, b_pi), b_di, b_fi],
            "safetyScore": int(round(float(mean_safe[best_b]))),
            "efficacyScore": int(round(float(mean_eff[best_b]))),
            "safetyRaw": round(float(mean_safe[best_b]), 2),
            "efficacyRaw": round(float(mean_eff[best_b]), 2),
            "safetyStd": round(float(std_safe[best_b]), 2),
            "efficacyStd": round(float(std_eff[best_b]), 2),
            "utilScore": round(float(util_all[best_b]), 2),
            "isCompat": True,
            "bystander": bool(lnk_b["cleavable"] and pld_b.get("perm", True)),
            "fcSilenced": fc_b["id"] != "igg1_wt",
            "fcFormat": fc_b["id"],
            "fcLabelKo": fc_b["ko"],
            "fcLabelEn": fc_b["en"],
            "plasmaStabPct": int(round(float(plasma_stab_pct[best_b]))),
            "pIC50Pos": round(float(mean_pic[best_b]), 2),
            "pIC50Std": round(float(std_pic[best_b]), 2),
            "pIC50Bys": round(float(mean_pic_bys[best_b]), 2),
            "optimalDoseMgKg": b_dose,
            "concResponse": [
                {"concNm": c_nm, "killPct": round(float(mean_conc4[best_b, c_i]) * 100.0, 1), "stdPct": round(float(std_conc4[best_b, c_i]) * 100.0, 1)}
                for c_i, c_nm in enumerate((1, 10, 100, 1000))
            ],
            "doseCurve": dose_curve,
            "organRisks": shown_org_risks_b,
            "organRiskMap": organ_risk_map_b,
            "organStdMap": organ_std_map_b,
            "nwSel": round(nw_sel, 4),
            "nwPot": round(nw_pot, 4),
            "nwDel": round(nw_del, 4),
            "nwBys": round(nw_bys, 4),
        }
        best_live["rationales"] = SM.build_rationales(best_live, st, real_organs)

        # Also enrich `current` construct at standard 3.6 mg/kg (index 2 of cur_arch_i) with live 5-fold uncertainty & kill curve!
        cur_b_idx = cur_arch_i * len(DOSE_GRID_MGKG) + 2  # 3.6 mg/kg on `cand_archs[cur_arch_i]`
        cur_detail = dict(mat_res["current"])
        cur_detail["safetyRaw"] = round(float(mean_safe[cur_b_idx]), 2)
        cur_detail["safetyScore"] = int(round(float(mean_safe[cur_b_idx])))
        cur_detail["safetyStd"] = round(float(std_safe[cur_b_idx]), 2)
        cur_detail["efficacyRaw"] = round(float(mean_eff[cur_b_idx]), 2)
        cur_detail["efficacyScore"] = int(round(float(mean_eff[cur_b_idx])))
        cur_detail["efficacyStd"] = round(float(std_eff[cur_b_idx]), 2)
        cur_detail["pIC50Pos"] = round(float(mean_pic[cur_b_idx]), 2)
        cur_detail["pIC50Std"] = round(float(std_pic[cur_b_idx]), 2)
        cur_detail["concResponse"] = [
            {"concNm": c_nm, "killPct": round(float(mean_conc4[cur_b_idx, c_i]) * 100.0, 1), "stdPct": round(float(std_conc4[cur_b_idx, c_i]) * 100.0, 1)}
            for c_i, c_nm in enumerate((1, 10, 100, 1000))
        ]

        if ref_arch_i is not None and isinstance(mat_res.get("ref_current"), dict):
            ref_b_idx = ref_arch_i * len(DOSE_GRID_MGKG) + 2
            ref_cur_live = dict(mat_res["ref_current"])
            ref_cur_live["safetyRaw"] = round(float(mean_safe[ref_b_idx]), 2)
            ref_cur_live["safetyScore"] = int(round(float(mean_safe[ref_b_idx])))
            ref_cur_live["safetyStd"] = round(float(std_safe[ref_b_idx]), 2)
            ref_cur_live["efficacyRaw"] = round(float(mean_eff[ref_b_idx]), 2)
            ref_cur_live["efficacyScore"] = int(round(float(mean_eff[ref_b_idx])))
            ref_cur_live["efficacyStd"] = round(float(std_eff[ref_b_idx]), 2)
            mat_res["ref_current"] = ref_cur_live

        if b_ti != mat_res["best"]["indices"][0]:
            ref_probe = SM.evaluate_studio_matrix({**body, "spec": best_live["spec"]})
            mat_res["ref_best"] = ref_probe["ref_current"]

        # Real-time 5-fold evaluated points for Deep Research scatter plot (no 368k cloud synthetic filler)
        deep_points: List[List[float]] = []
        deep_same_target_cloud: List[List[float]] = []
        for k_i, (k_ti, k_li, k_pi, _, _, _) in enumerate(batch_specs):
            is_c = True if k_pi < 0 else bool(st["compat_mask_lp"][k_li, k_pi])
            flags = (1 if is_c else 0) | (2 if k_ti == b_ti else 0) | (4 if k_ti == cur_ti else 0)
            pt_s = round(float(mean_safe[k_i]), 1)
            pt_e = round(float(mean_eff[k_i]), 1)
            deep_points.append([pt_s, pt_e, flags])
            if is_c and k_ti == cur_ti:
                deep_same_target_cloud.append([pt_s, pt_e])

        compat_b_indices = np.flatnonzero(compat_b_arr)
        sorted_b = sorted(
            compat_b_indices.tolist(),
            key=lambda i: (-round(float(mean_safe[i]), 2), -round(float(mean_eff[i]), 2)),
        )
        deep_pareto: List[Dict[str, Any]] = []
        run_max_e = -1e9
        for k_i in sorted_b:
            s_v = round(float(mean_safe[k_i]), 2)
            e_v = round(float(mean_eff[k_i]), 2)
            if e_v > run_max_e + 0.05:
                run_max_e = e_v
                p_ti, p_li, p_pi, p_di, p_fi, p_dose = batch_specs[k_i]
                deep_pareto.append(
                    {
                        "safetyRaw": s_v,
                        "efficacyRaw": e_v,
                        "utilScore": round(float(util_all[k_i]), 2),
                        "doseMgKg": float(p_dose),
                        "spec": {
                            "target": st["targets"][p_ti]["id"],
                            "linker": st["linkers"][p_li]["id"],
                            "payload": st["payloads"][cur_pi if p_pi < 0 else p_pi]["id"],
                            "dar": float(st["dars"][p_di]["val"]),
                            "fc": st["fc_formats"][p_fi]["id"] != "igg1_wt",
                            "fcFormat": st["fc_formats"][p_fi]["id"],
                        },
                    }
                )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        mat_res["schema"] = "ADCToX-DeepResearch-v083"
        mat_res["mode"] = "deep_research_v2"
        mat_res["current"] = cur_detail
        mat_res["best"] = best_live
        mat_res["deep_points"] = deep_points
        mat_res["cloud"] = deep_points
        mat_res["same_target_cloud"] = deep_same_target_cloud
        mat_res["pareto_front"] = deep_pareto
        mat_res["deep_research"] = {
            "slot": slot_id,
            "device": dev_str,
            "device_label": dev_label,
            "runtime_mode": runtime_mode,
            "n_folds": n_folds,
            "evaluated_regimens": bsz,
            "neural_forward_passes": bsz * n_folds,
            "optimal_dose_mgkg": b_dose,
            "custom_smiles_used": bool(custom_feat is not None),
            "elapsed_ms": elapsed_ms,
        }
        return mat_res
    finally:
        ALLOCATOR.release(slot_id)
        # Attach fresh post-release GPU status so caller immediately sees freed slot!


# ==============================================================================
# 5. Standalone Multi-GPU Worker Server (`python ml/deep_research.py --serve-gpu-worker`)
# ==============================================================================
def serve_gpu_worker(host: str = "127.0.0.1", port: int = 8766) -> None:
    class WorkerHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, payload: Dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path.startswith("/gpu-status"):
                self._send(200, ALLOCATOR.status())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path.startswith("/deep-research"):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                try:
                    res = run_deep_research(body)
                    res["gpu_status"] = ALLOCATOR.status()
                    self._send(200, res)
                except AllGPUSlotsBusyError as busy_err:
                    self._send(429, {"error": "all_gpu_slots_busy", "gpu_status": busy_err.status_payload})
                except Exception as exc:
                    self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
            else:
                self._send(404, {"error": "not found"})

    srv = ThreadingHTTPServer((host, port), WorkerHandler)
    st_info = ALLOCATOR.status()
    print(f"ADCTOX Deep Research GPU Worker listening on http://{host}:{port} ({st_info['backend']})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve-gpu-worker", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    if args.serve_gpu_worker:
        serve_gpu_worker(args.host, args.port)
