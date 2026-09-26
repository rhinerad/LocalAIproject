#!/usr/bin/env python3
"""Isolated ComfyUI HTTP wrapper for the DSPy still-optimization loop.

``tools.comfy_generate`` cannot be used here: comfyui-mcp's generate_image
action hardcodes SaveImage ``filename_prefix`` to ``ComfyUI``, so optimizer
stills would land in the operator output stream. This module posts a graph
directly to ``POST /prompt`` with prefix ``dspy_opt/<stem>``, polls
``/history/{prompt_id}``, and resolves the PNG.

It does not start, restart, or kill ComfyUI. It does not hold the MCP lock.
The live backend is the Rockernow listener on ``mcp_client.COMFYUI_URL``
(default http://127.0.0.1:8188). Sampler fields are locked by the DSPy
harness (cfg=7, steps=30, euler). Default size is 1024x768 so
``media_accuracy_gate.check_still`` sees a 4:3 frame. History polling is
capped at 60 wall-clock seconds and raises ``TimeoutError`` if ComfyUI
never writes ``/history`` (dropped node-validation jobs hang otherwise).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import mcp_client

OUTPUT_SUBDIR = "dspy_opt"
DEFAULT_URL = mcp_client.COMFYUI_URL
DEFAULT_CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 768
# Locked by the DSPy execution wrapper. Not proposed by the language model.
DEFAULT_STEPS = 30
DEFAULT_CFG = 7.0
DEFAULT_SAMPLER = "euler"
DEFAULT_SCHEDULER = "normal"
RENDER_TIMEOUT_S = 60.0
DEFAULT_NEGATIVE = (
    "visible camera body, camcorder, lens, tripod, operator, crew, "
    "production equipment, text, watermark, logo, blood, gore, "
    "deformed hands, extra fingers"
)
CLIENT_ID = "local_agent-dspy-opt"
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")
_PROMPT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
_HISTORY_MEDIA_KEYS = ("images", "gifs", "videos", "files")


class ComfyAPIError(RuntimeError):
    """ComfyUI HTTP, graph, or output-resolution failure."""


class HandoffError(RuntimeError):
    """Hardware ownership is uncertain; block subsequent GPU work."""


@dataclass(frozen=True)
class MemorySample:
    total: int
    used: int
    free: int


_NVML = None
_NVML_HANDLE = None


def _env_mib(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return int(default) * 1024 * 1024
    return int(float(raw) * 1024 * 1024)


def _read_gpu_memory(device_index: int | None = None) -> MemorySample:
    """Read total-device VRAM without creating a CUDA context."""
    global _NVML, _NVML_HANDLE
    if device_index is None:
        device_index = int(os.environ.get("DSPY_OPT_GPU_DEVICE", "0"))
    if _NVML is None or _NVML_HANDLE is None:
        try:
            import pynvml

            pynvml.nvmlInit()
            _NVML = pynvml
            _NVML_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(device_index)
        except Exception:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "-i", str(device_index),
                    "--query-gpu=memory.total,memory.used,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise HandoffError((result.stderr or "nvidia-smi memory query failed").strip())
            total_mib, used_mib, free_mib = [
                int(part.strip()) for part in result.stdout.strip().splitlines()[0].split(",")
            ]
            mib = 1024 * 1024
            return MemorySample(total=total_mib * mib, used=used_mib * mib, free=free_mib * mib)
    info = _NVML.nvmlDeviceGetMemoryInfo(_NVML_HANDLE)
    return MemorySample(total=int(info.total), used=int(info.used), free=int(info.free))


def wait_for_memory(
    read: Callable[[], MemorySample] = _read_gpu_memory, *,
    required_free: int,
    max_released_used: int,
    timeout: float = 45.0,
    stable_for: float = 0.75,
    interval: float = 0.25,
) -> MemorySample:
    """Wait until VRAM shows both headroom and a released-model baseline."""
    if min(timeout, stable_for, interval) <= 0 or required_free <= 0 or max_released_used < 0:
        raise ValueError("Invalid memory thresholds or timing parameters")
    deadline = time.monotonic() + timeout
    stable_since = None
    last = None
    while time.monotonic() < deadline:
        try:
            last = read()
        except Exception as exc:
            raise HandoffError("GPU memory telemetry unavailable") from exc
        if not (0 < last.total and 0 <= last.used <= last.total
                and 0 <= last.free <= last.total):
            raise HandoffError(f"Invalid GPU memory telemetry: {last}")
        if required_free > last.total:
            raise HandoffError("Required headroom exceeds total device memory")
        now = time.monotonic()
        if last.free >= required_free and last.used <= max_released_used:
            if stable_since is None:
                stable_since = now
            if now - stable_since >= stable_for:
                return last
        else:
            stable_since = None
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    raise HandoffError(f"VRAM release/headroom deadline exceeded; last={last}")


def save_prefix(stem: str) -> str:
    """Return a SaveImage prefix that lands under ``output/dspy_opt/``."""
    cleaned = _SAFE_STEM.sub("_", str(stem).strip()).strip("._-") or "still"
    return f"{OUTPUT_SUBDIR}/{cleaned}"


def comfy_output_root() -> Path:
    return Path(mcp_client.COMFYUI_PATH) / "output"


def ping(url: str = DEFAULT_URL, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/system_stats", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def build_txt2img_graph(
    *,
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    checkpoint: str = DEFAULT_CHECKPOINT,
    filename_prefix: str = "still",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    seed: int = 42,
    sampler: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    denoise: float = 1.0,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
) -> dict[str, Any]:
    """Minimal SDXL txt2img graph. Optional LoRA is inserted only when named.

    LoRA filename is never invented here. Pass the on-disk ComfyUI LoRA name
    (for post-fall Backrooms stills) via ``lora_name`` or DSPY_OPT_LORA.
    """
    if width < 512 or height < 384 or width % 8 or height % 8:
        raise ComfyAPIError(
            f"width/height must be multiples of 8 and at least 512x384, got {width}x{height}"
        )
    prefix = save_prefix(filename_prefix)
    clip_src: Any = ["1", 1]
    model_src: Any = ["1", 0]
    graph: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
    }
    if lora_name:
        graph["8"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "lora_name": lora_name,
                "strength_model": float(lora_strength),
                "strength_clip": float(lora_strength),
            },
        }
        clip_src = ["8", 1]
        model_src = ["8", 0]
    graph.update({
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": clip_src},
            "_meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": clip_src},
            "_meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": model_src,
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": float(denoise),
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": prefix},
        },
    })
    return graph


def enqueue_graph(graph: dict[str, Any], *, url: str = DEFAULT_URL,
                  timeout: int = 30) -> dict[str, Any]:
    body = json.dumps({"prompt": graph, "client_id": CLIENT_ID}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/prompt",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            queued = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ComfyAPIError(f"ComfyUI /prompt HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ComfyAPIError(f"ComfyUI /prompt failed: {exc}") from exc
    if not queued.get("prompt_id"):
        raise ComfyAPIError(f"ComfyUI /prompt returned no prompt_id: {queued!r}")
    queued["filename_prefix"] = graph["7"]["inputs"]["filename_prefix"]
    return queued


def _fetch_history(prompt_id: str, *, url: str, timeout: float = 30.0) -> dict:
    if not _PROMPT_ID_RE.fullmatch(prompt_id):
        raise ComfyAPIError(f"invalid prompt_id: {prompt_id!r}")
    hist_url = f"{url.rstrip('/')}/history/{urllib.parse.quote(prompt_id, safe='')}"
    try:
        with urllib.request.urlopen(hist_url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise ComfyAPIError(f"ComfyUI /history HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ComfyAPIError(f"ComfyUI /history unreadable: {exc}") from exc


def _history_entry(payload: object, prompt_id: str) -> dict | None:
    if not isinstance(payload, dict) or not payload:
        return None
    entry = payload.get(prompt_id)
    if isinstance(entry, dict):
        return entry
    if "outputs" in payload or "status" in payload:
        return payload
    if len(payload) == 1:
        only = next(iter(payload.values()))
        if isinstance(only, dict):
            return only
    return None


def _history_output_items(entry: dict) -> list[dict]:
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return []
    items: list[dict] = []
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for key in _HISTORY_MEDIA_KEYS:
            block = node_out.get(key)
            if not isinstance(block, list):
                continue
            for item in block:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                kind = str(item.get("type") or "output").lower()
                if kind != "output":
                    continue
                items.append({
                    "filename": Path(str(item["filename"])).name,
                    "subfolder": str(item.get("subfolder") or "").replace("\\", "/"),
                    "type": "output",
                    "media_key": key,
                })
    return items


def parse_history(payload: object, prompt_id: str) -> dict:
    entry = _history_entry(payload, prompt_id)
    if entry is None:
        return {"state": "pending", "prompt_id": prompt_id, "outputs": []}
    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    status_str = str(status.get("status_str") or "")
    completed = bool(status.get("completed"))
    items = _history_output_items(entry)
    if status_str.lower() in {"error", "failed"} or (
            completed and status_str.lower() not in {"success", ""} and not items):
        return {
            "state": "error",
            "prompt_id": prompt_id,
            "status_str": status_str,
            "outputs": items,
        }
    if completed or items:
        return {
            "state": "complete",
            "prompt_id": prompt_id,
            "status_str": status_str or "success",
            "outputs": items,
        }
    return {"state": "pending", "prompt_id": prompt_id, "outputs": items}


def _download_view(item: dict, dest: Path, *, url: str) -> Path:
    query = urllib.parse.urlencode({
        "filename": item["filename"],
        "subfolder": item.get("subfolder") or "",
        "type": "output",
    })
    req = urllib.request.Request(f"{url.rstrip('/')}/view?{query}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
    except Exception as exc:
        raise ComfyAPIError(f"ComfyUI /view failed for {item['filename']}: {exc}") from exc
    return dest


def resolve_output_path(item: dict, *, url: str = DEFAULT_URL) -> Path:
    """Prefer the on-disk ComfyUI output file; otherwise pull /view into runtime."""
    sub = str(item.get("subfolder") or "").replace("\\", "/").strip("/")
    name = Path(str(item["filename"])).name
    local = comfy_output_root() / sub / name if sub else comfy_output_root() / name
    if local.is_file():
        return local
    fallback = Path(__file__).resolve().parent / "runtime" / OUTPUT_SUBDIR / name
    return _download_view(item, fallback, url=url)


def wait_for_image(prompt_id: str, *, url: str = DEFAULT_URL,
                   timeout_s: float = RENDER_TIMEOUT_S) -> Path:
    """Poll /history until one output image exists.

    Strict wall-clock cap (default 60s). A dropped prompt never appears in
    ``/history``; that path raises ``TimeoutError`` so the DSPy compiler
    cannot hang overnight.
    """
    timeout_s = float(timeout_s)
    if timeout_s <= 0:
        raise TimeoutError("ComfyUI render timeout must be positive")
    deadline = time.monotonic() + timeout_s
    delay = 0.5
    last = {"state": "pending", "prompt_id": prompt_id, "outputs": []}
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"ComfyUI job {prompt_id} did not appear in /history within "
                f"{timeout_s:.0f}s (state={last.get('state')}). Possible "
                "syntax or node validation error; dropped prompts never complete."
            )
        last = parse_history(_fetch_history(prompt_id, url=url), prompt_id)
        if last["state"] == "error":
            raise ComfyAPIError(
                f"ComfyUI job {prompt_id} failed: {last.get('status_str') or 'error'}"
            )
        if last["state"] == "complete":
            images = [item for item in last["outputs"] if item.get("media_key") == "images"]
            chosen = images[0] if images else (last["outputs"][0] if last["outputs"] else None)
            if chosen is None:
                raise ComfyAPIError(f"ComfyUI job {prompt_id} completed with no output files")
            return resolve_output_path(chosen, url=url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            continue
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 5.0)


def free_vram(url: str = DEFAULT_URL) -> None:
    """Ask ComfyUI to unload models so the Qwen2.5-VL llama.cpp runtime can load.

    16 GB cannot hold RealVisXL and Qwen2.5-VL Caption V4 at once. This is a
    request to the already-running backend, not a process kill. The HTTP
    response only confirms that ComfyUI accepted the request; NVML confirms
    that device memory reached a released baseline before callers continue.
    """
    body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/free",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        raise ComfyAPIError(f"ComfyUI /free failed: {exc}") from exc
    wait_for_memory(
        required_free=_env_mib("DSPY_OPT_QWEN_REQUIRED_FREE_MB", 10240),
        max_released_used=_env_mib("DSPY_OPT_QWEN_MAX_RELEASED_USED_MB", 6144),
        timeout=float(os.environ.get("DSPY_OPT_HANDOFF_TIMEOUT_S", "180")),
        stable_for=float(os.environ.get("DSPY_OPT_HANDOFF_STABLE_S", "0.75")),
        interval=float(os.environ.get("DSPY_OPT_HANDOFF_INTERVAL_S", "0.25")),
    )


def generate_still(
    *,
    prompt: str | None = None,
    positive: str | None = None,
    negative_prompt: str = DEFAULT_NEGATIVE,
    negative: str | None = None,
    stem: str = "still",
    seed: int = 42,
    cfg: float = DEFAULT_CFG,
    steps: int = DEFAULT_STEPS,
    sampler: str = DEFAULT_SAMPLER,
    scheduler: str = DEFAULT_SCHEDULER,
    checkpoint: str = DEFAULT_CHECKPOINT,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    lora_name: str | None = None,
    lora_strength: float = 0.8,
    url: str = DEFAULT_URL,
    timeout_s: float = RENDER_TIMEOUT_S,
    timeout: float | None = None,
) -> Path:
    """Enqueue one isolated still and block until the PNG is on disk.

    ``positive`` / ``negative`` / ``timeout`` are aliases used by the DSPy
    harness. Sampler defaults are the locked constants (cfg=7, steps=30,
    euler). ``timeout`` defaults to 60s and raises ``TimeoutError``.
    """
    prompt = (prompt or positive or "").strip()
    if not prompt:
        raise ComfyAPIError("prompt/positive is required")
    if negative is not None:
        negative_prompt = negative
    if timeout is not None:
        timeout_s = float(timeout)
    if not ping(url):
        raise ComfyAPIError(
            f"ComfyUI is not listening at {url}. Start the Rockernow backend "
            "before a live DSPy compile; this wrapper will not launch it."
        )
    graph = build_txt2img_graph(
        prompt=prompt,
        negative_prompt=negative_prompt or DEFAULT_NEGATIVE,
        checkpoint=checkpoint,
        filename_prefix=stem,
        width=width,
        height=height,
        steps=int(steps),
        cfg=float(cfg),
        seed=int(seed),
        sampler=sampler,
        scheduler=scheduler,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    queued = enqueue_graph(graph, url=url)
    return wait_for_image(str(queued["prompt_id"]), url=url, timeout_s=timeout_s)
