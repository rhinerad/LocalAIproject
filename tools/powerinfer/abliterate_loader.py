"""Streaming TurboSparse loader that never materializes a full safetensors shard.

Transformers 4.41.2 loads each shard with ``safetensors.torch.load_file`` (the
whole 4.5 GiB mapping) and then copies/quantizes every tensor while that mapping
is still live. On this 32 GiB Windows host that collides with CUDA host pins and
looks like a hang at ``Loading checkpoint shards 2/4``.

This module:

- refuses Hub downloads
- streams one tensor at a time via ``safe_open``
- quantizes ``nn.Linear`` weights to NF4 on CUDA without passing Params4bit
  ``__dict__`` into the constructor (transformers 4.41 + bitsandbytes 0.50)
- enforces a wall-clock deadline so a load cannot run indefinitely
"""

from __future__ import annotations

import gc
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable, Iterable

_CACHE_ROOT = Path(__file__).resolve().parent / ".hf_cache"
os.environ.setdefault("HF_HOME", str(_CACHE_ROOT))
os.environ.setdefault("HF_MODULES_CACHE", str(_CACHE_ROOT / "modules"))
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import torch
import torch.nn as nn
from safetensors import safe_open
from safetensors.torch import save_file
from transformers import dynamic_module_utils

# Bamboo's modeling file imports flash-attn behind a runtime guard, but older
# Transformers still statically rejects the file when flash-attn is missing.
dynamic_module_utils.check_imports = lambda _filename: []

DEFAULT_LOCAL_TURBOSPARSE = Path(
    r"A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-instruct-source-20260830"
)
HUB_ID = "Tiiny/TurboSparse-Mistral-Instruct"
SHARD_RE = re.compile(r"^model-\d+-of-\d+\.safetensors$")
SKIP_QUANT_SUFFIXES = ("lm_head",)


class Deadline:
    def __init__(self, seconds: float) -> None:
        if seconds <= 0:
            raise ValueError("deadline must be positive")
        self.seconds = float(seconds)
        self.end = time.monotonic() + self.seconds

    def remaining(self) -> float:
        return self.end - time.monotonic()

    def check(self, where: str) -> None:
        left = self.remaining()
        if left <= 0:
            raise TimeoutError(f"timed out after {self.seconds:.0f}s at {where}")


def resolve_local_model(model: str | Path) -> Path:
    raw = str(model).strip().replace("\\", "/")
    path = Path(model)
    if path.is_dir() and (path / "config.json").is_file():
        return path.resolve()
    if raw in {HUB_ID, HUB_ID.replace("/", "-")}:
        if DEFAULT_LOCAL_TURBOSPARSE.is_dir() and (DEFAULT_LOCAL_TURBOSPARSE / "config.json").is_file():
            return DEFAULT_LOCAL_TURBOSPARSE
    raise SystemExit(
        f"refusing to download {model!r}; pass the local snapshot directory "
        f"(expected {DEFAULT_LOCAL_TURBOSPARSE})"
    )


def shard_paths(root: Path) -> list[Path]:
    files = sorted(p for p in root.iterdir() if p.is_file() and SHARD_RE.match(p.name))
    if not files:
        raise FileNotFoundError(f"no model-*-of-*.safetensors shards in {root}")
    return files


def _walk(model: nn.Module, name: str) -> tuple[nn.Module, str]:
    obj: nn.Module = model
    parts = name.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    return obj, parts[-1]


def replace_linears_with_4bit(model: nn.Module, compute_dtype: torch.dtype = torch.bfloat16) -> int:
    import bitsandbytes as bnb

    replaced = 0

    def recurse(module: nn.Module, prefix: str) -> None:
        nonlocal replaced
        for child_name, child in list(module.named_children()):
            full = f"{prefix}.{child_name}" if prefix else child_name
            if child_name in SKIP_QUANT_SUFFIXES or full in SKIP_QUANT_SUFFIXES:
                recurse(child, full)
                continue
            if isinstance(child, nn.Linear) and type(child) is nn.Linear:
                quant = bnb.nn.Linear4bit(
                    child.in_features,
                    child.out_features,
                    bias=child.bias is not None,
                    compute_dtype=compute_dtype,
                    compress_statistics=False,
                    quant_type="nf4",
                    device="meta",
                )
                quant.source_cls = type(child)
                quant.requires_grad_(False)
                module._modules[child_name] = quant
                replaced += 1
            else:
                recurse(child, full)

    recurse(model, "")
    return replaced


def _assign_linear4bit_weight(module: nn.Module, tensor: torch.Tensor, device: torch.device) -> None:
    import bitsandbytes as bnb

    payload = tensor.detach().to("cpu", dtype=torch.float16).contiguous()
    del tensor
    param = bnb.nn.Params4bit(
        payload,
        requires_grad=False,
        compress_statistics=False,
        quant_type="nf4",
        module=module,
    )
    param = param.to(device)
    module._parameters["weight"] = param
    module.quant_state = param.quant_state


def _assign_plain(module: nn.Module, leaf: str, tensor: torch.Tensor, device: torch.device) -> None:
    value = tensor.detach()
    if value.is_floating_point():
        value = value.to(dtype=torch.bfloat16)
    value = value.to(device)
    current = getattr(module, leaf, None)
    if leaf in getattr(module, "_parameters", {}) or isinstance(current, nn.Parameter):
        module._parameters[leaf] = nn.Parameter(value, requires_grad=False)
    elif leaf in getattr(module, "_buffers", {}):
        module._buffers[leaf] = value
    else:
        setattr(module, leaf, value)


def materialize_rotary_caches(model: nn.Module, device: torch.device, dtype: torch.dtype) -> int:
    rebuilt = 0
    for module in model.modules():
        setter = getattr(module, "_set_cos_sin_cache", None)
        if setter is None or not hasattr(module, "inv_freq"):
            continue
        inv = module.inv_freq
        if inv is None:
            continue
        module.inv_freq = inv.to(device=device, dtype=torch.float32)
        seq = int(getattr(module, "max_position_embeddings", getattr(module, "max_seq_len_cached", 2048)))
        setter(seq_len=seq, device=device, dtype=dtype)
        rebuilt += 1
    return rebuilt


def stream_load_quantized(
    model: nn.Module,
    source: Path,
    device: torch.device,
    deadline: Deadline,
    *,
    allowed_prefixes: Iterable[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Fill ``model`` from local shards, one tensor at a time."""
    import bitsandbytes as bnb

    allowed = tuple(allowed_prefixes) if allowed_prefixes is not None else None
    stats = {"tensors": 0, "quantized": 0, "skipped": 0, "shards": 0}
    emit = log or (lambda _msg: None)
    expected = {name for name, _ in model.named_parameters()} | {name for name, _ in model.named_buffers()}

    def _wanted(key: str) -> bool:
        if key in expected:
            return True
        if allowed is None:
            return key in expected
        parts = key.split(".")
        if len(parts) >= 3 and parts[0] == "model" and parts[1] == "layers" and parts[2].isdigit():
            prefix = f"model.layers.{parts[2]}."
            return prefix in allowed
        return key.startswith(("model.embed_tokens", "model.norm", "lm_head"))

    for shard in shard_paths(source):
        deadline.check(f"open {shard.name}")
        stats["shards"] += 1
        emit(f"stream {shard.name}")
        with safe_open(str(shard), framework="pt") as handle:
            for key in handle.keys():
                deadline.check(f"{shard.name}:{key}")
                if not _wanted(key):
                    stats["skipped"] += 1
                    continue
                if key not in expected:
                    stats["skipped"] += 1
                    continue
                tensor = handle.get_tensor(key)
                module, leaf = _walk(model, key)
                if leaf == "weight" and isinstance(module, bnb.nn.Linear4bit):
                    _assign_linear4bit_weight(module, tensor, device)
                    stats["quantized"] += 1
                else:
                    _assign_plain(module, leaf, tensor, device)
                    del tensor
                stats["tensors"] += 1
                if stats["tensors"] % 25 == 0:
                    emit(f"  tensors={stats['tensors']} quantized={stats['quantized']} remaining={deadline.remaining():.0f}s")
                    gc.collect()
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()
    still_meta = [
        name
        for name, param in model.named_parameters()
        if param.device.type == "meta"
    ]
    if still_meta:
        preview = ", ".join(still_meta[:8])
        raise RuntimeError(f"{len(still_meta)} parameters still on meta after stream load: {preview}")
    materialize_rotary_caches(model, device, torch.bfloat16)
    model.eval()
    return stats


def build_empty_causal_lm(source: Path, *, num_hidden_layers: int | None, trust_remote_code: bool):
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoModelForCausalLM

    cfg = AutoConfig.from_pretrained(
        str(source),
        local_files_only=True,
        trust_remote_code=trust_remote_code,
    )
    cfg._attn_implementation = "eager"
    if num_hidden_layers is not None:
        cfg.num_hidden_layers = int(num_hidden_layers)
    with init_empty_weights():
        model = AutoModelForCausalLM.from_config(cfg, trust_remote_code=trust_remote_code)
    replaced = replace_linears_with_4bit(model)
    return cfg, model, replaced


def load_measurement_model(
    source: Path,
    *,
    trust_remote_code: bool,
    deadline: Deadline,
    num_hidden_layers: int | None = None,
    log: Callable[[str], None] | None = None,
):
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the 4-bit measurement copy")
    device = torch.device("cuda:0")
    cfg, model, replaced = build_empty_causal_lm(
        source, num_hidden_layers=num_hidden_layers, trust_remote_code=trust_remote_code
    )
    emit = log or (lambda _msg: None)
    emit(f"replaced {replaced} Linear modules with Linear4bit")
    allowed = None
    if num_hidden_layers is not None:
        allowed = tuple(f"model.layers.{i}." for i in range(num_hidden_layers))
    stats = stream_load_quantized(
        model,
        source,
        device,
        deadline,
        allowed_prefixes=allowed,
        log=log,
    )
    emit(json.dumps({"load_stats": stats}, sort_keys=True))
    return cfg, model, stats


def edit_tensor_norm_preserving(
    name: str,
    weight: torch.Tensor,
    direction: torch.Tensor,
    strength: float,
    target_re: re.Pattern[str],
) -> torch.Tensor:
    """Same Projected Abliteration writer as the original script, with float32 rescale.

    r-space projection: W <- (I - strength * d d^T) W, then restore Frobenius
    norm. Compute the update in float32 so bf16 storage does not drop the scale
    factor (observed 0.7% drift on some o_proj matrices).
    """
    if not target_re.search(name):
        return weight
    if not name.endswith("o_proj.weight"):
        return weight
    d = direction.detach().to(dtype=torch.float32, device="cpu").flatten()
    if weight.shape[0] != d.numel():
        raise ValueError(f"unexpected o_proj shape for {name}: {tuple(weight.shape)}")
    original = weight.detach().to(dtype=torch.float32, device="cpu")
    edited = original - strength * torch.outer(d, d @ original)
    before = original.norm()
    after = edited.norm()
    if after > 0:
        edited = edited * (before / after)
    return edited.to(dtype=weight.dtype)


def edit_shards_cpu(
    source: Path,
    output: Path,
    direction: torch.Tensor,
    strength: float,
    target_re: re.Pattern[str],
    deadline: Deadline,
    log: Callable[[str], None] | None = None,
) -> list[str]:
    """Edit full-precision o_proj writers one shard at a time. Source is never written."""
    emit = log or (lambda _msg: None)
    index_path = source / "model.safetensors.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    weight_map: dict[str, str] = index["weight_map"]
    changed: list[str] = []
    output.mkdir(parents=True, exist_ok=False)
    copied = {
        "config.json",
        "configuration_bamboo.py",
        "modeling_bamboo.py",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer.model",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "model.safetensors.index.json",
    }
    for name in copied:
        src = source / name
        if src.is_file():
            shutil.copy2(src, output / name)

    for shard_name in sorted(set(weight_map.values())):
        deadline.check(f"edit {shard_name}")
        emit(f"edit {shard_name}")
        tensors: dict[str, torch.Tensor] = {}
        with safe_open(str(source / shard_name), framework="pt") as handle:
            for key in handle.keys():
                deadline.check(f"edit {shard_name}:{key}")
                tensor = handle.get_tensor(key)
                if target_re.search(key):
                    tensors[key] = edit_tensor_norm_preserving(
                        key, tensor, direction, strength, target_re
                    ).contiguous()
                    changed.append(key)
                else:
                    tensors[key] = tensor
        save_file(tensors, str(output / shard_name), metadata={"format": "pt"})
        del tensors
        gc.collect()
    if not changed:
        raise RuntimeError("no allowlisted o_proj weights found; output directory was created but is incomplete")
    return changed


def host_ram_mb() -> dict[str, float]:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return {
        "total_mb": stat.ullTotalPhys / (1024 * 1024),
        "avail_mb": stat.ullAvailPhys / (1024 * 1024),
        "pagefile_total_mb": stat.ullTotalPageFile / (1024 * 1024),
        "pagefile_avail_mb": stat.ullAvailPageFile / (1024 * 1024),
    }
