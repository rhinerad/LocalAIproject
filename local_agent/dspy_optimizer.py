#!/usr/bin/env python3
"""Programmatic prompt optimization against the local visual QA gate.

The DSPy program writes only text (positive/negative still prompts). Sampler
hyperparameters are locked constants in the execution wrapper â€” they are never
OutputFields, because GEPA will emit strings like ``steps: "around 30"`` and
crash the compiler.

Metric stack (fail-closed, same production gate):

1. ``prompt_assertions`` â€” cheap, no GPU
2. ``comfy_api.generate_still`` â€” 60s wall-clock; ``TimeoutError`` on drop
3. ``check_still`` â€” mechanical; VLM is never loaded on failure
4. ``comfy_api.free_vram`` then exact Caption V4 llama.cpp
5. ``semantic_verdict_from_caption``
6. **always** offload llama-server VRAM before the next SDXL load

Compile requires ``dspy`` and ``XAI_API_KEY``. Metric helpers and unit tests
do not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from media_accuracy_gate import (
    check_still,
    check_video,
    prompt_assertions,
    semantic_verdict_from_caption,
    video_prompt_assertions,
)

EXACT_VLM_MODEL = "qwen25-vl-nsfw-caption:v4-q4_k_m"
EXACT_VLM_RUNTIME = "llama.cpp"
PHASE1_TASK_MODEL = "qwen2.5:1.5b"
PHASE1_PROMPT_MODEL = "llama3.1:8b"
OLLAMA_HOST = "http://127.0.0.1:11434"
VIDEO_RENDER_TIMEOUT_S = 3600
STILL_RENDER_TIMEOUT_S = 1800
REQUIRED_SEMANTIC_CHECKS = (
    "requested_subjects_present",
    "requested_pose_or_action_visible",
    "requested_composition_visible",
    "setting_matches",
    "identity_continuity",
    "no_forbidden_equipment",
    "blind_observation_consistent",
)
# Locked execution constants. Not DSPy outputs. Not parsed from LM text.
LOCKED_CFG = 7.0
LOCKED_STEPS = 30
LOCKED_SAMPLER = "euler"
LOCKED_SCHEDULER = "normal"
RENDER_TIMEOUT_S = 60
DEFAULT_TASK_MODEL = "grok-4.6"
DEFAULT_REFLECTION_MODEL = "grok-4.6"
XAI_BASE_URL = "https://api.x.ai/v1"
VLM_INSTRUCTION = (
    "Inspect the supplied still and compare it strictly with the requested prompt. "
    "The full expected generation prompt is supplied after this rubric. Read it before judging. "
    "Return one compact JSON object only, with this shape: "
    "{\"pass\":true|false,\"rationale\":\"short reason\","
    "\"observed\":{\"subjects\":[],\"setting\":\"\",\"camera_visible\":false,"
    "\"composition\":\"\",\"pose\":\"\",\"continuity\":\"\"},\"checks\":{"
    "\"requested_subjects_present\":true|false,"
    "\"requested_pose_or_action_visible\":true|false,"
    "\"requested_composition_visible\":true|false,"
    "\"setting_matches\":true|false,"
    "\"identity_continuity\":true|false,"
    "\"no_forbidden_equipment\":true|false,"
    "\"blind_observation_consistent\":true|false}}. "
    "Set pass=true only when every check is true. The camera, lens, tripod, "
    "recording equipment, and production crew are forbidden. Set "
    "camera_visible=true only for an unmistakable physical camera body, lens, "
    "or tripod. A dark corner or crop boundary is not camera evidence."
)
SIGNATURE_INSTRUCTIONS = (
    "Write a ComfyUI SDXL still prompt that will pass media_accuracy_gate "
    "prompt_assertions and then Qwen2.5-VL Caption V4 structured QA. "
    "Stills are static 4:3 scene plates. Never write motion verbs for the "
    "actor/entity (walks, runs, turns, waves, leans, approaches). Never mention "
    "MiniMax or a video prompt. Always include viewpoint control "
    "('camcorder' or 'viewer-perspective framing' or 'clean scene plate'). "
    "A camera noun inside a prohibitive clause is correct; a positive request "
    "to show a camera/lens/tripod is not. "
    "C001-C014 and C015-start must specify an apartment and must not name a "
    "Backrooms LoRA. C015-last and C016+ must include Backrooms / sickly yellow "
    "wallpaper / damp carpet cues. C016-C062 (Mode B) must include "
    "'do not depict the actor's face or torso' (or equivalent never-shown "
    "language) and must not draw a person except the tiny allowed fragments "
    "the scene spec names. Do not emit sampler hyperparameters; cfg, steps, "
    "and sampler are locked in the execution wrapper."
)
VIDEO_SIGNATURE_INSTRUCTIONS = (
    "Expand base_prompt into one dense paragraph for an 8-second Wan "
    "first-last-frame video. Style=backrooms. Keep the original request as "
    "the first sentence. When the camera is unlocked, copy these exact tokens "
    "into injected_prompt: first-person camcorder tracking, heavy VHS "
    "artifacting, handheld walking momentum, continuous unbroken shot, "
    "realistic camera shake, 1990s home video aesthetic. Never omit "
    "handheld walking momentum on an unlocked camera. If the base prompt "
    "already specifies a locked or authored camera (tripod, static shot, "
    "static camera, security camera, CCTV, dolly, pan, tilt), suppress "
    "handheld walking momentum, first-person camcorder tracking, and "
    "realistic camera shake; still keep heavy VHS artifacting, a continuous "
    "unbroken shot, and the 1990s home video aesthetic. Do not duplicate "
    "phrases already present. Do not mention MiniMax. Do not emit sampler "
    "hyperparameters."
)
VIDEO_VLM_INSTRUCTION = (
    "Inspect the supplied video frames in time order and compare them strictly "
    "with the requested motion prompt. The full expected generation prompt is "
    "supplied after this rubric. Return one compact JSON object only, with this "
    "shape: {\"pass\":true|false,\"rationale\":\"short reason\","
    "\"observed\":{\"subjects\":[],\"setting\":\"\",\"camera_visible\":false,"
    "\"composition\":\"\",\"pose\":\"\",\"continuity\":\"\",\"motion\":\"\"},"
    "\"checks\":{"
    "\"requested_subjects_present\":true|false,"
    "\"requested_pose_or_action_visible\":true|false,"
    "\"requested_composition_visible\":true|false,"
    "\"setting_matches\":true|false,"
    "\"identity_continuity\":true|false,"
    "\"no_forbidden_equipment\":true|false,"
    "\"blind_observation_consistent\":true|false}}. "
    "Set pass=true only when every check is true. Handheld camcorder motion "
    "must look like walking momentum, not a locked tripod or a still image. "
    "The camera body, lens, tripod, recording equipment, and production crew "
    "are forbidden. A dark corner is not camera evidence."
)
_VIDEO_RENDER_CACHE: dict[str, dict] = {}

_RENDER_CACHE: dict[str, dict] = {}
_QWEN25_VL_PROC: subprocess.Popen | None = None


class HandoffError(RuntimeError):
    """Hardware ownership is uncertain; block subsequent GPU work."""


@dataclass(frozen=True)
class MemorySample:
    total: int
    used: int
    free: int


class HandoffLatch:
    """Poison the run after one uncertain GPU handoff."""

    def __init__(self):
        self.failed = False

    def require_healthy(self):
        if self.failed:
            raise HandoffError("GPU handoff previously failed; recovery required")

    def perform(self, operation: Callable[[], object]):
        self.require_healthy()
        try:
            return operation()
        except Exception as exc:
            self.failed = True
            raise HandoffError("GPU handoff failed; subsequent GPU work blocked") from exc


_GPU_HANDOFF_LATCH = HandoffLatch()
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


def _wait_for_stage_memory(stage: str) -> MemorySample:
    if stage == "sdxl":
        required_free = _env_mib("DSPY_OPT_SDXL_REQUIRED_FREE_MB", 12288)
        max_used = _env_mib("DSPY_OPT_SDXL_MAX_RELEASED_USED_MB", 4096)
    elif stage == "qwen":
        required_free = _env_mib("DSPY_OPT_QWEN_REQUIRED_FREE_MB", 10240)
        max_used = _env_mib("DSPY_OPT_QWEN_MAX_RELEASED_USED_MB", 6144)
    else:
        raise ValueError(f"unknown GPU memory stage: {stage}")
    return wait_for_memory(
        required_free=required_free,
        max_released_used=max_used,
        timeout=float(os.environ.get("DSPY_OPT_HANDOFF_TIMEOUT_S", "180")),
        stable_for=float(os.environ.get("DSPY_OPT_HANDOFF_STABLE_S", "0.75")),
        interval=float(os.environ.get("DSPY_OPT_HANDOFF_INTERVAL_S", "0.25")),
    )


def stop_owned_server(proc: subprocess.Popen, *, timeout: float = 15.0) -> None:
    """Terminate only a retained direct Popen handle and confirm process exit."""
    if proc.poll() is not None:
        proc.wait(timeout=0)
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
    except Exception as exc:
        raise HandoffError("Owned llama-server exit could not be confirmed") from exc


def _transient_hardware_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "timeout", "timed out", "connection", "refused", "reset",
        "unavailable", "oom", "out of memory", "cuda", "vram",
        "winerror 10061",
    )
    return any(marker in text for marker in markers)


class _FallbackPrediction:
    """Stand-in when dspy is not installed. Same fields GEPA reads."""

    def __init__(self, score: float, feedback: str):
        self.score = float(score)
        self.feedback = str(feedback)


def _prediction(score: float, feedback: str):
    try:
        import dspy
        return dspy.Prediction(score=float(score), feedback=str(feedback))
    except ImportError:
        return _FallbackPrediction(score, feedback)


def _dspy():
    try:
        import dspy
        return dspy
    except ImportError as exc:
        raise RuntimeError(
            "dspy is not installed. Metric helpers work without it; compile "
            "needs `pip install dspy` in the Python that will run overnight."
        ) from exc


def _field(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _positive_prompt(pred: Any) -> str:
    return str(_field(pred, "positive_prompt") or _field(pred, "prompt") or "").strip()


def _negative_prompt(pred: Any) -> str:
    return str(_field(pred, "negative_prompt") or _field(pred, "negative") or "").strip()


def _example_seed(example: Any) -> int:
    seed = _field(example, "seed")
    if seed is not None:
        return int(seed)
    clip_id = str(_field(example, "clip_id") or "clip")
    frame = str(_field(example, "frame") or "start")
    digest = hashlib.sha256(f"{clip_id}:{frame}".encode()).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def cache_key(example: Any, prompt: str, negative: str) -> str:
    raw = json.dumps({
        "clip_id": _field(example, "clip_id"),
        "frame": _field(example, "frame"),
        "prompt": prompt,
        "negative": negative,
        "cfg": LOCKED_CFG,
        "steps": LOCKED_STEPS,
        "sampler": LOCKED_SAMPLER,
        "seed": _example_seed(example),
    }, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _port_from_host(host: str) -> int:
    try:
        return int(str(host).rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 11436


def _pid_listening_on_port(port: int) -> int | None:
    """Return the local listener PID on ``port``, or None. Windows PowerShell."""
    if os.name != "nt":
        return None
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if ($c) { $c.OwningProcess } else { '' }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    text = (result.stdout or "").strip()
    if not text.isdigit():
        return None
    pid = int(text)
    return pid if pid > 0 else None


def offload_vlm_vram() -> None:
    """Release the retained Caption V4 llama-server before SDXL admission."""
    _stop_owned_qwen25_vl_runtime()


def _stop_owned_qwen25_vl_runtime() -> None:
    """Stop only the llama-server process launched by this optimizer run."""
    global _QWEN25_VL_PROC
    import capabilities
    import llama_cpp_client

    if _QWEN25_VL_PROC is None:
        if llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST):
            raise HandoffError("Qwen runtime is live without a retained process handle")
        return
    proc = _QWEN25_VL_PROC
    try:
        stop_owned_server(proc)
        deadline = time.monotonic() + 5
        while llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST) and time.monotonic() < deadline:
            time.sleep(0.2)
        if llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST):
            raise HandoffError("Qwen runtime health endpoint remained live after owned process exit")
    finally:
        _QWEN25_VL_PROC = None
        try:
            capabilities.QWEN25_VL_RUNTIME_STATE.unlink()
        except FileNotFoundError:
            pass


def _ensure_owned_qwen25_vl_runtime(timeout_seconds: int = 420) -> bool:
    """Start Qwen through a retained Popen handle so teardown is verifiable."""
    global _QWEN25_VL_PROC
    import capabilities
    import llama_cpp_client

    if _QWEN25_VL_PROC is not None and _QWEN25_VL_PROC.poll() is None:
        if llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST):
            return True
        raise HandoffError("Owned Qwen runtime process is alive but not healthy")
    _QWEN25_VL_PROC = None
    if llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST):
        raise HandoffError("Qwen runtime is already live without a retained process handle")
    if not (capabilities.qwen25_vl_files_ready()
            and capabilities.QWEN25_VL_LLAMA_SERVER.is_file()
            and capabilities.qwen25_vl_checksums_ok()):
        return False
    host = capabilities.QWEN25_VL_RUNTIME_HOST
    bind_host = str(host).rsplit(":", 1)[0] or "127.0.0.1"
    port = str(_port_from_host(host))
    args = [
        str(capabilities.QWEN25_VL_LLAMA_SERVER),
        "--model", str(capabilities.QWEN25_VL_GGUF),
        "--mmproj", str(capabilities.QWEN25_VL_MMPROJ),
        "--host", bind_host,
        "--port", port,
        "--ctx-size", "32768",
        "--n-gpu-layers", "99",
        "--image-min-tokens", "1024",
        "--flash-attn", "auto",
        "--no-webui",
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    # Server output goes to capabilities.QWEN25_VL_SERVER_LOG (was DEVNULL) so
    # a crash mid-judge leaves the llama.cpp reason on disk.
    log = capabilities.open_qwen25_vl_server_log("dspy_optimizer._ensure_owned_qwen25_vl_runtime")
    try:
        proc = subprocess.Popen(
            args,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    except Exception as exc:
        capabilities.close_qwen25_vl_server_log(log)
        raise HandoffError("Could not launch owned Qwen llama-server") from exc
    capabilities.close_qwen25_vl_server_log(log, proc.pid)
    _QWEN25_VL_PROC = proc
    try:
        capabilities._write_qwen25_vl_runtime_state(proc.pid)
    except Exception as exc:
        _stop_owned_qwen25_vl_runtime()
        raise HandoffError("Could not record owned Qwen runtime state") from exc
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _QWEN25_VL_PROC = None
            try:
                capabilities.QWEN25_VL_RUNTIME_STATE.unlink()
            except FileNotFoundError:
                pass
            raise HandoffError("Owned Qwen llama-server exited before becoming healthy; "
                               f"see {capabilities.QWEN25_VL_SERVER_LOG}")
        if llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST):
            return True
        time.sleep(1)
    _stop_owned_qwen25_vl_runtime()
    raise HandoffError("Owned Qwen llama-server did not become healthy before deadline")


def run_vlm_verdict(image_path: Path, prompt: str) -> dict:
    """Call the exact Caption V4 llama.cpp runtime and parse with the gate."""
    import capabilities
    import media_tools

    if not capabilities.qwen25_vl_runtime_available():
        _ensure_owned_qwen25_vl_runtime()
    if not capabilities.qwen25_vl_runtime_available():
        return {
            "status": "fail",
            "reasons": [
                "semantic verdict is not from the exact Qwen2.5-VL Caption V4 llama.cpp runtime"
            ],
            "verdict": None,
            "model": None,
            "runtime": None,
        }
    raw_envelope = media_tools._run_vision_gpu(
        [image_path],
        prompt,
        capabilities.QWEN25_VL_MODEL,
        capabilities.QWEN25_VL_RUNTIME_HOST,
        instruction=VLM_INSTRUCTION,
        num_ctx=16384,
        num_predict=512,
        # Structured JSON verdict, validated with the penalty effectively off
        # (llama_cpp_client dropped it until 2026-09-24ae); keep it off.
        repeat_penalty=1.0,
    )
    envelope = json.loads(raw_envelope)
    analysis = str(envelope.get("analysis") or "")
    verdict = semantic_verdict_from_caption(
        analysis, prompt,
        model=envelope.get("model"),
        runtime=envelope.get("runtime"),
    )
    if "VLM did not return structured JSON" in (verdict.get("reasons") or []):
        retry_envelope = json.loads(media_tools._run_vision_gpu(
            [image_path],
            prompt,
            capabilities.QWEN25_VL_MODEL,
            capabilities.QWEN25_VL_RUNTIME_HOST,
            instruction=VLM_INSTRUCTION + (
                "\nFORMAT RETRY: Return exactly one compact JSON object matching "
                "the requested schema. No markdown or prose."
            ),
            num_ctx=16384,
            num_predict=512,
            repeat_penalty=1.0,  # structured verdict; see the first call above
        ))
        verdict = semantic_verdict_from_caption(
            str(retry_envelope.get("analysis") or ""), prompt,
            model=retry_envelope.get("model"),
            runtime=retry_envelope.get("runtime"),
        )
    return verdict


def evaluate_candidate(
    example: Any,
    pred: Any,
    dry_run: bool = False,
    *,
    render_fn: Callable[..., Path] | None = None,
    vlm_fn: Callable[[Path, str], dict] | None = None,
    free_vram_fn: Callable[[], None] | None = None,
    offload_vlm_fn: Callable[[], None] | None = None,
) -> dict:
    """Audit-refactored metric body.

    Hyperparameters are the locked constants, never parsed from ``pred``.
    Mechanical failure returns before the VLM is loaded. ComfyUI poll timeout
    is 60s. llama-server is offloaded after every VLM call.
    """
    clip_id = str(_field(example, "clip_id") or "")
    frame = str(_field(example, "frame") or "start")
    prompt = _positive_prompt(pred)
    negative = _negative_prompt(pred)
    # Gate key is ``pass``, not ``passed``.
    p_assert = prompt_assertions(prompt, clip_id, frame)
    if not p_assert.get("pass", False):
        return {
            "gepa": 0.0,
            "mipro": 0.0,
            "feedback": f"Prompt Assertion Failed: {p_assert.get('reasons')}",
            "prompt_ok": False,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": True,
            "checks": {},
        }
    if dry_run:
        return {
            "gepa": 0.5,
            "mipro": 0.2,
            "feedback": "Dry run passed assertions.",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": True,
            "checks": {},
        }

    key = cache_key(example, prompt, negative)
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        return cached

    live = render_fn is None
    if live:
        _GPU_HANDOFF_LATCH.require_healthy()
    if live:
        import comfy_api
        if offload_vlm_fn is None:
            offload_vlm_fn = offload_vlm_vram
        if free_vram_fn is None:
            free_vram_fn = comfy_api.free_vram
        lora_name = os.environ.get("DSPY_OPT_LORA") or None
        try:
            lora_strength = float(os.environ.get("DSPY_OPT_LORA_STRENGTH") or 0.8)
        except ValueError:
            lora_strength = 0.8

        def render_fn(prompt: str, negative: str, example: Any) -> Path:
            stem = f"{_field(example, 'clip_id')}_{_field(example, 'frame')}_{key[:10]}"
            if offload_vlm_fn is not None:
                _GPU_HANDOFF_LATCH.perform(offload_vlm_fn)
            _GPU_HANDOFF_LATCH.perform(lambda: _wait_for_stage_memory("sdxl"))
            return comfy_api.generate_still(
                positive=prompt,
                negative=negative,
                cfg=LOCKED_CFG,
                steps=LOCKED_STEPS,
                sampler=LOCKED_SAMPLER,
                scheduler=LOCKED_SCHEDULER,
                timeout=RENDER_TIMEOUT_S,
                stem=stem,
                seed=_example_seed(example),
                lora_name=lora_name,
                lora_strength=lora_strength,
            )

    vlm = vlm_fn or run_vlm_verdict

    try:
        image_path = render_fn(prompt, negative, example)
    except HandoffError:
        raise
    except TimeoutError:
        if live:
            _GPU_HANDOFF_LATCH.failed = True
            raise HandoffError("ComfyUI render timed out during live GPU evaluation")
        return {
            "gepa": 0.0,
            "mipro": 0.0,
            "feedback": "ComfyUI Render Timed Out. Possible syntax or node error.",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": False,
            "checks": {},
        }
    except Exception as exc:
        if live and _transient_hardware_error(exc):
            _GPU_HANDOFF_LATCH.failed = True
            raise HandoffError("Transient ComfyUI/GPU failure during live evaluation") from exc
        return {
            "gepa": 0.0,
            "mipro": 0.0,
            "feedback": f"ComfyUI render failed: {exc}",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": False,
            "checks": {},
        }

    mech_check = check_still(image_path, prompt, clip_id, frame)
    if mech_check.get("status") != "pass":
        # Short-circuit: never load Caption V4 for a mechanically illegal still.
        result = {
            "gepa": 0.0,
            "mipro": 0.1,
            "feedback": f"Mechanical check failed: {mech_check.get('reasons')}",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": False,
            "image_path": str(image_path),
            "checks": {},
        }
        _RENDER_CACHE[key] = result
        return result

    if free_vram_fn is not None:
        if live:
            _GPU_HANDOFF_LATCH.perform(free_vram_fn)
        else:
            free_vram_fn()
    if live:
        _GPU_HANDOFF_LATCH.perform(lambda: _wait_for_stage_memory("qwen"))

    try:
        try:
            semantic = vlm(Path(image_path), prompt)
        except Exception as exc:
            if live and _transient_hardware_error(exc):
                _GPU_HANDOFF_LATCH.failed = True
                raise HandoffError("Transient VLM/GPU failure during live evaluation") from exc
            raise
    finally:
        if offload_vlm_fn is not None:
            if live:
                _GPU_HANDOFF_LATCH.perform(offload_vlm_fn)
            else:
                offload_vlm_fn()

    verdict = semantic.get("verdict") if isinstance(semantic.get("verdict"), dict) else {}
    checks = dict(verdict["checks"]) if isinstance(verdict.get("checks"), dict) else {}
    if semantic.get("status") == "pass":
        result = {
            "gepa": 1.0,
            "mipro": 1.0,
            "feedback": "Perfect score. All checks passed.",
            "prompt_ok": True,
            "mechanical_ok": True,
            "semantic_ok": True,
            "skipped_gpu": False,
            "image_path": str(image_path),
            "checks": checks,
        }
        _RENDER_CACHE[key] = result
        return result

    checks_passed = sum(1 for name in REQUIRED_SEMANTIC_CHECKS if checks.get(name) is True)
    rationale = verdict.get("rationale") or ""
    result = {
        "gepa": 0.0,
        "mipro": 0.4 + (0.6 * (checks_passed / 7.0)),
        "feedback": (
            f"VLM Failed: {semantic.get('reasons')}. Rationale: {rationale}"
        ),
        "prompt_ok": True,
        "mechanical_ok": True,
        "semantic_ok": False,
        "skipped_gpu": False,
        "image_path": str(image_path),
        "checks": checks,
    }
    _RENDER_CACHE[key] = result
    return result


def _injected_prompt(pred: Any) -> str:
    return str(
        _field(pred, "injected_prompt")
        or _field(pred, "positive_prompt")
        or _field(pred, "prompt")
        or ""
    ).strip()


def _camera_locked(example: Any, prompt: str) -> bool:
    flagged = _field(example, "camera_locked")
    if flagged is not None:
        return bool(flagged)
    try:
        import temporal_physics as tp
        return tp.camera_is_locked(prompt) or tp.has_specified_motion(prompt)
    except Exception:
        return False


def video_cache_key(example: Any, injected: str) -> str:
    raw = json.dumps({
        "clip_id": _field(example, "clip_id"),
        "injected": injected,
        "start": _field(example, "start_prompt"),
        "end": _field(example, "end_prompt"),
        "seed": _example_seed(example),
    }, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def extract_eval_frames(video_path: Path, count: int = 10) -> list[Path]:
    """Uniformly sample 8-12 PNG frames for the VLM.

    MiniMax I2V emits ~192 frames (8s @ 24fps). Feeding the full clip to
    Qwen-VL OOMs an RTX 5080, so we always cap to [8, 12] frames.
    """
    import subprocess

    # NEVER send the full 192-frame MiniMax clip to Qwen-VL.
    try:
        _requested = int(count)
    except Exception:
        _requested = 10
    count = int(max(8, min(12, _requested)))

    out_dir = HERE / "runtime" / "dspy_opt" / "eval_frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(video_path).encode()).hexdigest()[:10]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    duration = 2.0
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            text=True,
            encoding="utf-8",
            timeout=15,
            creationflags=flags,
        )
        duration = max(0.5, float(raw.strip() or 2.0))
    except Exception:
        pass

    # Uniform sample across the full duration (inclusive endpoints inset slightly).
    if count == 1:
        fracs = (0.5,)
    else:
        fracs = tuple(i / (count - 1) for i in range(count))
        # inset endpoints a hair so we avoid black first/last frames
        fracs = tuple(0.02 + 0.96 * f for f in fracs)

    frames: list[Path] = []
    for i, frac in enumerate(fracs):
        sec = max(0.0, min(duration - 0.05, duration * frac))
        target = out_dir / f"{video_path.stem}_{digest}_{i:02d}_{sec:.3f}s.png"
        if not target.exists():
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(video_path),
                    "-ss",
                    f"{sec:.3f}",
                    "-frames:v",
                    "1",
                    "-c:v",
                    "png",
                    "-y",
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=60,
                creationflags=flags,
            )
        frames.append(target)
    return frames


def run_vlm_verdict_video(video_path: Path, prompt: str) -> dict:
    """Caption V4 over sampled frames; same JSON schema as stills."""
    import capabilities
    import media_tools

    frames = extract_eval_frames(video_path)
    if not capabilities.qwen25_vl_runtime_available():
        _ensure_owned_qwen25_vl_runtime()
    if not capabilities.qwen25_vl_runtime_available():
        return {
            "status": "fail",
            "reasons": [
                "semantic verdict is not from the exact Qwen2.5-VL Caption V4 llama.cpp runtime"
            ],
            "verdict": None,
            "model": None,
            "runtime": None,
        }
    raw_envelope = media_tools._run_vision_gpu(
        frames,
        prompt,
        capabilities.QWEN25_VL_MODEL,
        capabilities.QWEN25_VL_RUNTIME_HOST,
        instruction=VIDEO_VLM_INSTRUCTION,
        num_ctx=32768,
        num_predict=512,
        repeat_penalty=1.0,  # structured verdict; see the still call above
    )
    envelope = json.loads(raw_envelope)
    analysis = str(envelope.get("analysis") or "")
    return semantic_verdict_from_caption(
        analysis, prompt,
        model=envelope.get("model"),
        runtime=envelope.get("runtime"),
    )


def render_phases_2_3(example: Any, injected: str) -> Path:
    """SDXL start/end stills then Wan first-last-frame. No Phase 4. No physics rewrite."""
    root = HERE.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import comfy_api
    from dispatcher import DEFAULT_COMFY_URL, PipelineOrchestrator
    from live_vram_test import (
        JOB_TIMEOUT_S,
        VIDEO_TIMEOUT_S,
        _upload_png,
        build_fl2va_graph,
        wait_for_video,
    )

    if not comfy_api.ping(DEFAULT_COMFY_URL):
        raise HandoffError("ComfyUI is not listening on 127.0.0.1:8188")

    clip_id = str(_field(example, "clip_id") or "opt")
    key = video_cache_key(example, injected)[:10]
    start_prompt = str(_field(example, "start_prompt") or injected)
    end_prompt = str(_field(example, "end_prompt") or injected)
    orch = PipelineOrchestrator(comfy_url=DEFAULT_COMFY_URL)

    def _still(prompt: str, tag: str) -> Path:
        # style=default: Phase 1 already produced the prompt. Do not re-inject.
        graph = orch.build_and_dispatch_payload(prompt, "16:9", "sdxl", "default")
        save = graph.get("7") or {}
        if isinstance(save.get("inputs"), dict):
            save["inputs"]["filename_prefix"] = comfy_api.save_prefix(f"dspy_opt/opt_{clip_id}_{tag}_{key}")
            if save.get("class_type") == "SaveImageWebsocket":
                save["class_type"] = "SaveImage"
                save["inputs"].setdefault(
                    "filename_prefix",
                    comfy_api.save_prefix(f"dspy_opt/opt_{clip_id}_{tag}_{key}"),
                )
        queued = orch.submit_prompt(graph)
        pid = queued["prompt_id"]
        tracked = orch.track_prompt_id(pid, timeout_s=JOB_TIMEOUT_S)
        if tracked.get("state") != "complete":
            raise RuntimeError(f"still {tag} failed: {tracked}")
        return comfy_api.wait_for_image(pid, url=orch.comfy_url, timeout_s=30)

    start_png = _still(start_prompt, "start")
    end_png = _still(end_prompt, "end")

    _GPU_HANDOFF_LATCH.perform(comfy_api.free_vram)
    start_name = _upload_png(Path(start_png), orch.comfy_url)
    end_name = _upload_png(Path(end_png), orch.comfy_url)
    graph = build_fl2va_graph(start_name, end_name, injected, f"dspy_opt/opt_{clip_id}_{key}")
    pid = orch.submit_prompt(graph)["prompt_id"]
    tracked = orch.track_prompt_id(pid, timeout_s=VIDEO_TIMEOUT_S)
    if tracked.get("state") != "complete":
        raise RuntimeError(f"Phase 3 failed: {tracked}")
    mp4 = wait_for_video(pid, orch.comfy_url, timeout_s=60)
    _GPU_HANDOFF_LATCH.perform(comfy_api.free_vram)
    return Path(mp4)


def evaluate_video_candidate(
    example: Any,
    pred: Any,
    dry_run: bool = False,
    *,
    render_fn: Callable[..., Path] | None = None,
    vlm_fn: Callable[[Path, str], dict] | None = None,
    check_video_fn: Callable[..., dict] | None = None,
    free_vram_fn: Callable[[], None] | None = None,
    offload_vlm_fn: Callable[[], None] | None = None,
) -> dict:
    """Score a Phase-1 injected prompt against Phase 2+3 MP4 + Qwen2.5-VL.

    Does not call ``enforce_physics_terms``. Missing physics tokens fail
    ``video_prompt_assertions`` so the optimizer has to learn them.
    """
    clip_id = str(_field(example, "clip_id") or "")
    injected = _injected_prompt(pred)
    scene_spec = str(_field(example, "scene_spec") or "")
    locked = _camera_locked(example, injected or str(_field(example, "base_prompt") or ""))
    p_assert = video_prompt_assertions(
        injected, camera_locked=locked, scene_spec=scene_spec,
    )
    if not p_assert.get("pass", False):
        return {
            "gepa": 0.0,
            "mipro": 0.0,
            "feedback": f"Video Prompt Assertion Failed: {p_assert.get('reasons')}",
            "prompt_ok": False,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": True,
            "checks": {},
        }
    if dry_run:
        return {
            "gepa": 0.5,
            "mipro": 0.2,
            "feedback": "Dry run passed video prompt assertions.",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": True,
            "checks": {},
        }

    key = video_cache_key(example, injected)
    cached = _VIDEO_RENDER_CACHE.get(key)
    if cached is not None:
        return cached

    live = render_fn is None
    if live:
        _GPU_HANDOFF_LATCH.require_healthy()
        if offload_vlm_fn is None:
            offload_vlm_fn = offload_vlm_vram
        render_fn = lambda _prompt, _example: render_phases_2_3(_example, _prompt)

    vlm = vlm_fn or run_vlm_verdict_video
    checker = check_video_fn or check_video

    try:
        if live and offload_vlm_fn is not None:
            _GPU_HANDOFF_LATCH.perform(offload_vlm_fn)
            _GPU_HANDOFF_LATCH.perform(lambda: _wait_for_stage_memory("sdxl"))
        video_path = render_fn(injected, example)
    except HandoffError:
        raise
    except TimeoutError:
        if live:
            _GPU_HANDOFF_LATCH.failed = True
            raise HandoffError("ComfyUI Phase 2/3 timed out during live GPU evaluation")
        return {
            "gepa": 0.0,
            "mipro": 0.0,
            "feedback": "ComfyUI Phase 2/3 Timed Out. Possible syntax or node error.",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": False,
            "checks": {},
        }
    except Exception as exc:
        if live and _transient_hardware_error(exc):
            _GPU_HANDOFF_LATCH.failed = True
            raise HandoffError("Transient ComfyUI/GPU failure during live video evaluation") from exc
        return {
            "gepa": 0.0,
            "mipro": 0.0,
            "feedback": f"ComfyUI Phase 2/3 failed: {exc}",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": False,
            "checks": {},
        }

    mech = checker(video_path, injected, clip_id)
    if mech.get("status") != "pass":
        result = {
            "gepa": 0.0,
            "mipro": 0.1,
            "feedback": f"Mechanical video check failed: {mech.get('reasons')}",
            "prompt_ok": True,
            "mechanical_ok": False,
            "semantic_ok": False,
            "skipped_gpu": False,
            "video_path": str(video_path),
            "checks": {},
        }
        _VIDEO_RENDER_CACHE[key] = result
        return result

    if free_vram_fn is not None:
        if live:
            _GPU_HANDOFF_LATCH.perform(free_vram_fn)
        else:
            free_vram_fn()
    if live:
        _GPU_HANDOFF_LATCH.perform(lambda: _wait_for_stage_memory("qwen"))

    try:
        try:
            semantic = vlm(Path(video_path), injected)
        except Exception as exc:
            if live and _transient_hardware_error(exc):
                _GPU_HANDOFF_LATCH.failed = True
                raise HandoffError("Transient VLM/GPU failure during live video evaluation") from exc
            raise
    finally:
        if offload_vlm_fn is not None:
            if live:
                _GPU_HANDOFF_LATCH.perform(offload_vlm_fn)
            else:
                offload_vlm_fn()

    verdict = semantic.get("verdict") if isinstance(semantic.get("verdict"), dict) else {}
    checks = dict(verdict["checks"]) if isinstance(verdict.get("checks"), dict) else {}
    if semantic.get("status") == "pass":
        result = {
            "gepa": 1.0,
            "mipro": 1.0,
            "feedback": "Perfect score. Video checks passed.",
            "prompt_ok": True,
            "mechanical_ok": True,
            "semantic_ok": True,
            "skipped_gpu": False,
            "video_path": str(video_path),
            "checks": checks,
        }
        _VIDEO_RENDER_CACHE[key] = result
        return result

    checks_passed = sum(1 for name in REQUIRED_SEMANTIC_CHECKS if checks.get(name) is True)
    rationale = verdict.get("rationale") or ""
    result = {
        "gepa": 0.0,
        "mipro": 0.4 + (0.6 * (checks_passed / 7.0)),
        "feedback": (
            f"VLM Failed: {semantic.get('reasons')}. Rationale: {rationale}"
        ),
        "prompt_ok": True,
        "mechanical_ok": True,
        "semantic_ok": False,
        "skipped_gpu": False,
        "video_path": str(video_path),
        "checks": checks,
    }
    _VIDEO_RENDER_CACHE[key] = result
    return result


def _target_is_video() -> bool:
    return os.environ.get("DSPY_OPT_TARGET", "still").strip().lower() == "video"


def gepa_metric(example, pred, trace=None, pred_name=None, pred_trace=None, **_kwargs):
    """GEPA contract: ``dspy.Prediction(score, feedback)``."""
    dry = os.environ.get("DSPY_OPT_DRY_RUN", "").strip() in {"1", "true", "yes"}
    if _target_is_video():
        result = evaluate_video_candidate(example, pred, dry_run=dry)
    else:
        result = evaluate_candidate(example, pred, dry_run=dry)
    return _prediction(result["gepa"], result["feedback"])


def mipro_metric(example, pred, trace=None, pred_name=None, pred_trace=None, **_kwargs):
    """MIPROv2 contract: scalar in [0, 1]."""
    dry = os.environ.get("DSPY_OPT_DRY_RUN", "").strip() in {"1", "true", "yes"}
    if _target_is_video():
        return evaluate_video_candidate(example, pred, dry_run=dry)["mipro"]
    return evaluate_candidate(example, pred, dry_run=dry)["mipro"]


def build_program():
    dspy = _dspy()

    class ComfyStillSignature(dspy.Signature):
        """Write a ComfyUI SDXL still prompt that will pass media_accuracy_gate prompt_assertions and then Qwen2.5-VL Caption V4 structured QA."""
        scene_spec: str = dspy.InputField(desc="The semantic target and setting")
        clip_id: str = dspy.InputField(desc="The unique ID for the cut")
        frame: str = dspy.InputField(desc="The specific frame index")
        constraints: str = dspy.InputField(desc="Hard rejection clauses to avoid")
        positive_prompt: str = dspy.OutputField(desc="Dense visual description for SDXL")
        negative_prompt: str = dspy.OutputField(desc="Specific negative prompt terms")

    ComfyStillSignature.instructions = SIGNATURE_INSTRUCTIONS

    class ComfyStillProgram(dspy.Module):
        def __init__(self):
            super().__init__()
            self.writer = dspy.ChainOfThought(ComfyStillSignature)

        def forward(self, scene_spec, clip_id, frame, constraints=""):
            return self.writer(
                scene_spec=scene_spec,
                clip_id=clip_id,
                frame=frame,
                constraints=constraints or "",
            )

    return ComfyStillProgram()


def build_video_program():
    """Phase-1 injector compiled against qwen2.5:1.5b. Same fields as temporal_physics_v1."""
    dspy = _dspy()

    class TemporalPhysicsSignature(dspy.Signature):
        """Expand a Backrooms request into a dense Wan FLF motion paragraph."""
        base_prompt: str = dspy.InputField(desc="The raw scene or motion request")
        style: str = dspy.InputField(desc="Must be backrooms")
        injected_prompt: str = dspy.OutputField(
            desc="Dense video paragraph including required physics tokens"
        )

    TemporalPhysicsSignature.instructions = VIDEO_SIGNATURE_INSTRUCTIONS

    class TemporalPhysicsInjector(dspy.Module):
        def __init__(self):
            super().__init__()
            self.prog = dspy.ChainOfThought(TemporalPhysicsSignature)

        def forward(self, base_prompt, style="backrooms"):
            return self.prog(base_prompt=base_prompt, style=style or "backrooms")

    return TemporalPhysicsInjector()


def configure_lms(*, task_model: str = DEFAULT_TASK_MODEL,
                  reflection_model: str = DEFAULT_REFLECTION_MODEL):
    """SpaceXAI / xAI OpenAI-compatible endpoint. Key from XAI_API_KEY only."""
    dspy = _dspy()
    api_key = os.environ.get("XAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set; compile will not run.")
    task_lm = dspy.LM(
        f"openai/{task_model}",
        api_key=api_key,
        api_base=XAI_BASE_URL,
        temperature=0.7,
        max_tokens=2048,
    )
    reflection_lm = dspy.LM(
        f"openai/{reflection_model}",
        api_key=api_key,
        api_base=XAI_BASE_URL,
        temperature=1.0,
        max_tokens=8000,
    )
    dspy.configure(lm=task_lm)
    return task_lm, reflection_lm


def configure_video_lms(*, task_model: str = PHASE1_TASK_MODEL,
                        prompt_model: str | None = None):
    """Phase-1 student is local Ollama ``qwen2.5:1.5b``.

    MIPROv2's prompt proposer uses SpaceXAI/xAI when ``XAI_API_KEY`` is set,
    otherwise local ``llama3.1:8b``.
    """
    dspy = _dspy()
    import temporal_physics as tp

    if not tp.configure_local_dspy_lm(host=OLLAMA_HOST, model=task_model):
        raise RuntimeError(
            f"Ollama at {OLLAMA_HOST} does not have {task_model}. "
            "Install it or start Ollama before compiling."
        )
    from dspy.dsp.utils.settings import settings
    task_lm = settings.lm
    api_key = os.environ.get("XAI_API_KEY", "").strip()
    if api_key:
        reflection_lm = dspy.LM(
            f"openai/{DEFAULT_REFLECTION_MODEL}",
            api_key=api_key,
            api_base=XAI_BASE_URL,
            temperature=1.0,
            max_tokens=8000,
        )
    else:
        chosen = prompt_model or PHASE1_PROMPT_MODEL
        reflection_lm = dspy.LM(
            f"ollama_chat/{chosen}",
            api_base=OLLAMA_HOST,
            cache=False,
            temperature=1.0,
            max_tokens=8192,
            keep_alive=0,
            extra_body={"keep_alive": 0},
        )
    dspy.configure(lm=task_lm)
    return task_lm, reflection_lm


def _video_example_from_row(dspy, row: dict):
    return dspy.Example(
        base_prompt=str(row.get("base_prompt") or row.get("motion") or ""),
        style=str(row.get("style") or "backrooms"),
        scene_spec=str(row.get("scene_spec") or ""),
        clip_id=str(row.get("clip_id") or ""),
        start_prompt=str(row.get("start_prompt") or row.get("start") or ""),
        end_prompt=str(row.get("end_prompt") or row.get("end") or ""),
        camera_locked=bool(row.get("camera_locked") or False),
        constraints=str(row.get("constraints") or ""),
        seed=row.get("seed"),
    ).with_inputs("base_prompt", "style")


def load_trainset(path: Path):
    dspy = _dspy()
    examples = []
    video = _target_is_video()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        if video or row.get("base_prompt") or row.get("motion"):
            examples.append(_video_example_from_row(dspy, row))
        else:
            ex = dspy.Example(
                scene_spec=str(row["scene_spec"]),
                clip_id=str(row["clip_id"]),
                frame=str(row.get("frame") or "start"),
                constraints=str(row.get("constraints") or ""),
                seed=row.get("seed"),
            ).with_inputs("scene_spec", "clip_id", "frame", "constraints")
            examples.append(ex)
    if not examples:
        raise RuntimeError(f"no examples in {path}")
    return examples


def default_trainset():
    dspy = _dspy()
    rows = [
        {
            "clip_id": "C001",
            "frame": "start",
            "scene_spec": (
                "Static 4:3 viewer-perspective reference still of one fictional "
                "adult man standing in a modest ordinary apartment living room "
                "with a visible sofa."
            ),
            "constraints": (
                "Must specify apartment. No Backrooms LoRA. Clean scene plate: "
                "no visible recording camera, camcorder body, lens, tripod, "
                "operator, crew. No motion verbs."
            ),
            "seed": 1001,
        },
        {
            "clip_id": "C016",
            "frame": "last",
            "scene_spec": (
                "Static low, slightly tilted 4:3 consumer-camcorder POV lying on "
                "the floor of an empty Level 0 Backrooms interior. Damp "
                "brown-beige carpet, sickly yellow patterned wallpaper."
            ),
            "constraints": (
                "Mode B: do not depict the actor's face or torso. Actor entirely "
                "outside the frame. No visible camera body, lens, tripod. "
                "Absence of a person is correct."
            ),
            "seed": 1016,
        },
        {
            "clip_id": "C017",
            "frame": "last",
            "scene_spec": (
                "Static low 4:3 consumer-camcorder POV turned toward a nearby "
                "Level 0 Backrooms wall. Sickly yellow patterned wallpaper fills "
                "most of the frame; a strip of damp brown-beige carpet along the bottom."
            ),
            "constraints": (
                "Mode B: do not depict the actor's face or torso. No person, "
                "hand, sleeve, or body. No camera equipment."
            ),
            "seed": 1017,
        },
    ]
    return [
        dspy.Example(**row).with_inputs(
            "scene_spec", "clip_id", "frame", "constraints"
        )
        for row in rows
    ]


def default_video_trainset():
    """3â€“5 baseline Backrooms scenarios for Phase-1 MIPRO."""
    dspy = _dspy()
    rows = [
        {
            "clip_id": "OPT01",
            "scene_spec": "damp yellow carpet hallway, Level 0 Backrooms",
            "base_prompt": (
                "[Handheld POV] Camera settles on damp brown-beige carpet then "
                "lifts toward a sickly yellow Level 0 hallway."
            ),
            "start_prompt": (
                "Static low tilted 4:3 consumer-camcorder POV on empty Level 0 "
                "floor. Damp brown-beige carpet, sickly yellow wallpaper."
            ),
            "end_prompt": (
                "Same floor plate, slightly more of the yellow wall entering frame."
            ),
            "style": "backrooms",
            "camera_locked": False,
            "seed": 1601,
        },
        {
            "clip_id": "OPT02",
            "scene_spec": "abandoned indoor pool room, empty tiled basin, yellowed lighting",
            "base_prompt": (
                "[Handheld POV] Walk along the edge of an abandoned indoor pool; "
                "stale water, tiled basin, echoing empty room."
            ),
            "start_prompt": (
                "Static 4:3 camcorder POV of an abandoned indoor pool: empty tiled "
                "basin, milky water, yellowed overhead lights."
            ),
            "end_prompt": (
                "Closer to the pool edge; tiles and stagnant water fill more of frame."
            ),
            "style": "backrooms",
            "camera_locked": False,
            "seed": 1602,
        },
        {
            "clip_id": "OPT03",
            "scene_spec": "fluorescent office corridor, repeating yellow wallpaper",
            "base_prompt": (
                "[Low handheld walk] Bounce forward through a narrow yellow "
                "corridor under repeating fluorescent rectangles."
            ),
            "start_prompt": (
                "Low shaky 4:3 view down a narrow yellow corridor, damp carpet "
                "and wallpaper filling the frame."
            ),
            "end_prompt": (
                "Far fluorescent fixture growing larger; corridor still empty."
            ),
            "style": "backrooms",
            "camera_locked": False,
            "seed": 1603,
        },
        {
            "clip_id": "OPT04",
            "scene_spec": "empty yellow room with a single doorway opening",
            "base_prompt": (
                "[Shaky tracking] Slow walk across an empty yellow room toward "
                "the nearest doorway."
            ),
            "start_prompt": (
                "Chest-height forward view into an empty yellow room; doorway "
                "visible ahead."
            ),
            "end_prompt": (
                "The same room, the doorway larger in frame."
            ),
            "style": "backrooms",
            "camera_locked": False,
            "seed": 1604,
        },
        {
            "clip_id": "OPT05",
            "scene_spec": "dead-end yellow wall, Level 0 Backrooms",
            "base_prompt": (
                "[Shaky tracking] Walk until a dead-end yellow wall fills the frame."
            ),
            "start_prompt": (
                "Original narrow yellow hall, slightly scuffed carpet, wall distant."
            ),
            "end_prompt": (
                "Dead-end wall ahead, yellow and close, filling the frame."
            ),
            "style": "backrooms",
            "camera_locked": False,
            "seed": 1605,
        },
    ]
    return [_video_example_from_row(dspy, row) for row in rows]


def compile_program(
    *,
    optimizer: str = "gepa",
    auto: str = "light",
    trainset=None,
    valset=None,
    log_dir: Path | None = None,
    save_path: Path | None = None,
    target: str = "still",
):
    dspy = _dspy()
    if auto not in {"light", "medium", "heavy"}:
        raise ValueError("auto must be light, medium, or heavy")
    os.environ["DSPY_OPT_TARGET"] = target
    video = target == "video"
    if video:
        task_lm, reflection_lm = configure_video_lms()
        student = build_video_program()
        trainset = list(trainset or default_video_trainset())
        default_save = (
            HERE.parent / "models" / "dspy_compiled" / "temporal_physics_mipro.json"
        )
    else:
        task_lm, reflection_lm = configure_lms()
        student = build_program()
        trainset = list(trainset or default_trainset())
        default_save = HERE / "runtime" / "dspy_opt" / "optimized.json"
    valset = list(valset or trainset)
    log_dir = log_dir or (HERE / "runtime" / "dspy_opt" / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_path or default_save
    save_path.parent.mkdir(parents=True, exist_ok=True)

    if optimizer == "gepa":
        teleprompter = dspy.GEPA(
            metric=gepa_metric,
            auto=auto,
            reflection_lm=reflection_lm,
            num_threads=1,
            track_stats=True,
            log_dir=str(log_dir),
            skip_perfect_score=True,
            perfect_score=1.0,
            failure_score=0.0,
            add_format_failure_as_feedback=True,
        )
        compiled = teleprompter.compile(student, trainset=trainset, valset=valset)
    elif optimizer == "mipro":
        teleprompter = dspy.MIPROv2(
            metric=mipro_metric,
            auto=auto,
            prompt_model=reflection_lm,
            task_model=task_lm,
            num_threads=1,
            max_bootstrapped_demos=2,
            max_labeled_demos=2,
            track_stats=True,
            log_dir=str(log_dir),
        )
        compiled = teleprompter.compile(
            student, trainset=trainset, valset=valset, minibatch=False,
        )
    elif optimizer == "bootstrap":
        teleprompter = dspy.BootstrapFewShotWithRandomSearch(
            metric=mipro_metric,
            max_bootstrapped_demos=2,
            max_labeled_demos=4,
            num_candidate_programs=6,
            num_threads=1,
        )
        compiled = teleprompter.compile(student, trainset=trainset, valset=valset)
    else:
        raise ValueError("optimizer must be gepa, mipro, or bootstrap")

    compiled.save(str(save_path))
    return compiled, save_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Optimize Phase-1 Backrooms prompts (qwen2.5:1.5b) against "
            "media_accuracy_gate + Qwen2.5-VL, using ComfyUI Phases 2 and 3."
        ),
    )
    parser.add_argument(
        "--target", choices=("video", "still"), default="video",
        help="video = Phase 1 injector + Wan FLF MP4 metric (default).",
    )
    parser.add_argument(
        "--optimizer", choices=("gepa", "mipro", "bootstrap"), default="mipro",
    )
    parser.add_argument("--auto", choices=("light", "medium", "heavy"), default="light")
    parser.add_argument("--trainset", type=Path, help="JSONL of examples")
    parser.add_argument("--save", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Score prompt assertions only. No ComfyUI, no VLM. Cannot reach score 1.0.",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Run the optimizer. Video target needs Ollama qwen2.5:1.5b and live ComfyUI unless --dry-run.",
    )
    parser.add_argument(
        "--boot-comfy",
        action="store_true",
        help="If :8188 is down, start the owned Backrooms ComfyUI backend for the compile.",
    )
    args = parser.parse_args(argv)
    if not args.compile:
        parser.print_help()
        print(
            "\nRefusing to start GPU work without --compile.\n"
            "Phase-1 video MIPRO:\n"
            "  python local_agent/dspy_optimizer.py --compile --target video "
            "--optimizer mipro --auto light\n"
            "Dry assertions only:\n"
            "  python local_agent/dspy_optimizer.py --compile --target video "
            "--optimizer mipro --dry-run"
        )
        return 2
    os.environ["DSPY_OPT_TARGET"] = args.target
    if args.dry_run:
        os.environ["DSPY_OPT_DRY_RUN"] = "1"
    trainset = load_trainset(args.trainset) if args.trainset else None
    watch = None
    compiled = None
    path = None
    if args.target == "video" and not args.dry_run:
        root = HERE.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import comfy_api
        from dispatcher import DEFAULT_COMFY_URL
        if not comfy_api.ping(DEFAULT_COMFY_URL):
            if not args.boot_comfy:
                print("ComfyUI is not on 127.0.0.1:8188. Re-run with --boot-comfy or start the backend.")
                return 3
            from backrooms_watch import BackroomsWatch
            watch = BackroomsWatch()
            watch.acquire()
            watch.restart("dspy_opt:compile")
    try:
        compiled, path = compile_program(
            optimizer=args.optimizer,
            auto=args.auto,
            trainset=trainset,
            save_path=args.save,
            target=args.target,
        )
    finally:
        if watch is not None:
            watch.close()
    if compiled is None or path is None:
        return 1
    print(json.dumps({
        "saved": str(path),
        "optimizer": args.optimizer,
        "auto": args.auto,
        "target": args.target,
        "task_model": PHASE1_TASK_MODEL if args.target == "video" else DEFAULT_TASK_MODEL,
    }, indent=2))
    module = getattr(compiled, "prog", None) or getattr(compiled, "writer", None)
    instructions = getattr(getattr(module, "signature", None), "instructions", None)
    if instructions:
        print("--- compiled instructions ---")
        print(instructions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
