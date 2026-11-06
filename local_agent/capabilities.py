#!/usr/bin/env python3
"""Runtime capability registry for the offline agent. Never downloads anything.

The Qwen2.5-VL caption model is deliberately imported from two local GGUF
files: the language/vision weights and its matching multimodal projector.  A
model tag that advertises ``vision`` is necessary, but not sufficient evidence
that this import is complete; :func:`qwen25_vl_files` is the local-file check.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

import router
import llama_cpp_client

WHISPER_MODEL = Path(os.environ.get(
    "EQUAL_SHARES_WHISPER_MODEL",
    r"A:\Users\rhine\ComfyUI-Shared\models\sonicLipsyncFor_comfyui\sonic\whisper-tiny",
))
COMFY_PYTHON = Path(os.environ.get(
    "EQUAL_SHARES_COMFY_PYTHON",
    r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe",
))


@lru_cache(maxsize=1)
def comfy_whisper_available() -> bool:
    required = ("config.json", "preprocessor_config.json", "model.safetensors")
    if not COMFY_PYTHON.is_file() or any(not (WHISPER_MODEL / n).is_file() for n in required):
        return False
    try:
        import subprocess
        check = subprocess.run(
            [str(COMFY_PYTHON), "-c",
             "import torch,whisper,safetensors"],
            capture_output=True, text=True, timeout=75,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "-1",
                 "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        )
        return check.returncode == 0
    except Exception:
        return False


def _models(host: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"http://{host}/api/tags", timeout=5) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []


def _model_size(host: str, model: str) -> int | None:
    try:
        with urllib.request.urlopen(f"http://{host}/api/tags", timeout=5) as r:
            rows = json.loads(r.read()).get("models", [])
        row = next((m for m in rows if m.get("name") == model), None)
        return int(row["size"]) if row and row.get("size") is not None else None
    except Exception:
        return None


def _size_text(size: int | None) -> str:
    return f"{size / (1024 ** 3):.2f} GB installed" if size else "installed; exact size unavailable"


def _model_capabilities(host: str, model: str) -> list[str]:
    try:
        req = urllib.request.Request(
            f"http://{host}/api/show",
            data=json.dumps({"model": model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("capabilities", [])
    except Exception:
        return []


# ── vision tier definitions ───────────────────────────────────────────────────
# The operator selected one exact visual model pair.  It is deliberately not
# interchangeable with an Ollama model that happens to advertise `vision`:
# every image/video path must wait for this matched Qwen2.5-VL GGUF + mmproj.
# The tier is skipped if free VRAM < its need + safety.

VRAM_SAFETY_MB = 1024   # headroom beyond a model's peak VRAM need

# ── primary local visual model ───────────────────────────────────────────────
# Q4_K_M is 4.68 GB and the working matching Q8_0 projector is 0.70 GB. Eight
# GB of free VRAM plus one GB safety headroom leaves room for the image encoder and a
# practical context window on this 16 GB GPU, without CPU layer offload.
QWEN25_VL_MODEL = "qwen25-vl-nsfw-caption:v4-q4_k_m"
QWEN25_VL_REPOSITORY = "mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF"
QWEN25_VL_ROOT = Path(os.environ.get(
    "EQUAL_SHARES_QWEN25_VL_DIR",
    r"A:\Users\rhine\ComfyUI-Shared\models\LLM\GGUF\mradermacher\Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF",
))
# ``.local.gguf`` distinguishes verified local copies from any failed transfer
# left by a downloader.  llama.cpp accepts the standard GGUF extension.
QWEN25_VL_GGUF = QWEN25_VL_ROOT / "Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf"
QWEN25_VL_MMPROJ = QWEN25_VL_ROOT / "Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf"
# Hugging Face LFS SHA-256 for the exact V4 Q4_K_M + matching Q8_0 projector
# (mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF, tree fetched 2026-08-30).
# Size-only checks are not identity: a truncated or swapped GGUF of similar
# length must not start the watcher runtime.
QWEN25_VL_WEIGHTS_BYTES = 4_684_339_808
QWEN25_VL_WEIGHTS_SHA256 = "e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d"
QWEN25_VL_MMPROJ_BYTES = 732_298_784
QWEN25_VL_MMPROJ_SHA256 = "470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1"
QWEN25_VL_MMPROJ_MIN_BYTES = QWEN25_VL_MMPROJ_BYTES
QWEN25_VL_VRAM_MB = 8000
QWEN25_VL_RUNTIME_HOST = os.environ.get("EQUAL_SHARES_QWEN25_VL_HOST", "127.0.0.1:11436")
QWEN25_VL_LLAMA_SERVER = Path(os.environ.get(
    "EQUAL_SHARES_QWEN25_VL_SERVER",
    r"A:\Users\rhine\ComfyUI-Shared\runtimes\llama.cpp-cuda\llama-server.exe",
))
QWEN25_VL_RUNTIME_STATE = Path(__file__).resolve().parent / "runtime" / "qwen25_vl_runtime.json"
# Output of every production launch of that server (this module's watcher
# launch and dspy_optimizer's owned GVD-judge launch). It used to go to
# DEVNULL, so four mid-request crashes on 2026-09-24 left no trace.
QWEN25_VL_SERVER_LOG = Path(__file__).resolve().parent / "runtime" / "logs" / "qwen25_vl_llama_server.log"
QWEN25_VL_SERVER_LOG_MAX_BYTES = 20 * 1024 * 1024   # then rotated once to .prev

# Kept as compatibility aliases for callers written before the model switch.
# They now deliberately point at the 7B Qwen2.5-VL model rather than a 32B
# model that would spill layers to CPU.
MINICPM_V_MODEL = QWEN25_VL_MODEL
MINICPM_VRAM_MB = QWEN25_VL_VRAM_MB

# Qwen-Image is not part of sensory analysis.  It is an optional LoRA used only
# by a future, explicitly requested diffusion operation; importing this module
# must never load it or trigger a download.
QWEN_IMAGE_NSFW_REPOSITORY = "starsfriday/Qwen-Image-NSFW"
QWEN_IMAGE_NSFW_FILE = Path(os.environ.get(
    "EQUAL_SHARES_QWEN_IMAGE_NSFW_FILE",
    r"A:\Users\rhine\ComfyUI-Shared\models\diffusion_models\qwen_image_nsfw.safetensors",
))
# This is a Qwen-Image LoRA (base Qwen/Qwen-Image), not an SDXL checkpoint.
# work/image_render.py only builds CheckpointLoaderSimple graphs for RealVisXL,
# so this identity is recorded and never loaded by the storyboard planner.
QWEN_IMAGE_NSFW_BYTES = 188_807_872
QWEN_IMAGE_NSFW_SHA256 = "af10a4787691e56cd72803eeaed7f249c1b689583938147cd4ddb31e7d2e1350"

_SHA256_CACHE: dict[tuple[str, int, int], str] = {}


def _sha256_file(path: Path) -> str | None:
    """SHA-256 a local file. Cached on (path, size, mtime); never downloads."""
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), int(stat.st_size), int(stat.st_mtime))
    cached = _SHA256_CACHE.get(key)
    if cached:
        return cached
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    hexdigest = digest.hexdigest()
    _SHA256_CACHE[key] = hexdigest
    return hexdigest

_TIER_DEFS: list[dict] = [
    {
        "label": "primary",
        "vram_need_mb": QWEN25_VL_VRAM_MB,
        "task_strengths": "detailed captioning, image grounding, and frame-by-frame video action analysis",
        "models": [
            QWEN25_VL_MODEL,
        ],
    },
]

# The watcher's vision model, in priority order (used by vision_model() for
# single-model callers that predate the tier system):
VISION_MODEL_ENV = "EQUAL_SHARES_VISION_MODEL"
VISION_PREFERENCES = [QWEN25_VL_MODEL]


def qwen25_vl_files() -> dict:
    """Report the two immutable local files required for the visual import."""
    def describe(path: Path, expected_bytes: int, expected_sha256: str) -> dict:
        present = path.is_file()
        size = path.stat().st_size if present else 0
        return {
            "path": str(path), "present": present, "bytes": size,
            "expected_bytes": expected_bytes,
            "expected_sha256": expected_sha256,
            "size_ok": size == expected_bytes,
            "large_enough": size == expected_bytes,
        }
    return {
        "repository": QWEN25_VL_REPOSITORY,
        "weights": describe(QWEN25_VL_GGUF, QWEN25_VL_WEIGHTS_BYTES,
                            QWEN25_VL_WEIGHTS_SHA256),
        "mmproj": describe(QWEN25_VL_MMPROJ, QWEN25_VL_MMPROJ_BYTES,
                           QWEN25_VL_MMPROJ_SHA256),
    }


def qwen25_vl_files_ready() -> bool:
    """Whether the exact local base GGUF and matched projector have the right sizes.

    Checksums are verified separately at runtime start so a status poll never
    SHA-256s 5 GB. A size match with a hash mismatch still refuses to launch.
    """
    files = qwen25_vl_files()
    def _ok(part: dict) -> bool:
        if "size_ok" in part:
            return bool(part["size_ok"])
        return bool(part.get("large_enough"))
    return bool(_ok(files["weights"]) and _ok(files["mmproj"]))


def qwen25_vl_checksums_ok() -> bool:
    """True only when both local files match the pinned Hugging Face SHA-256."""
    if not qwen25_vl_files_ready():
        return False
    # Hashing the 5.4-GB pair on every media frame is needlessly expensive and
    # was causing the lazy runtime readiness window to expire.  Cache a verified
    # result keyed by size and mtime; any replacement invalidates the cache.
    cache_path = QWEN25_VL_RUNTIME_STATE.with_name("qwen25_vl_checksum_cache.json")
    stat_key = {
        "weights": [QWEN25_VL_GGUF.stat().st_size, QWEN25_VL_GGUF.stat().st_mtime_ns],
        "mmproj": [QWEN25_VL_MMPROJ.stat().st_size, QWEN25_VL_MMPROJ.stat().st_mtime_ns],
    }
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("stat_key") == stat_key:
            return bool(cached.get("ok"))
    except Exception:
        pass
    weights = _sha256_file(QWEN25_VL_GGUF)
    mmproj = _sha256_file(QWEN25_VL_MMPROJ)
    ok = (weights == QWEN25_VL_WEIGHTS_SHA256
          and mmproj == QWEN25_VL_MMPROJ_SHA256)
    try:
        cache_path.write_text(json.dumps({"stat_key": stat_key, "ok": ok}), encoding="utf-8")
    except Exception:
        pass
    return ok


def qwen25_vl_runtime_available() -> bool:
    """True only when the CUDA llama.cpp service is live on its loopback port."""
    return qwen25_vl_files_ready() and llama_cpp_client.up(QWEN25_VL_RUNTIME_HOST)


def _write_qwen25_vl_runtime_state(pid: int) -> None:
    """Atomically record ownership before treating a spawned VLM as usable."""
    QWEN25_VL_RUNTIME_STATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": int(pid),
        "started_at": time.time(),
        "server": str(QWEN25_VL_LLAMA_SERVER),
        "host": QWEN25_VL_RUNTIME_HOST,
    }
    temp = QWEN25_VL_RUNTIME_STATE.with_suffix(
        QWEN25_VL_RUNTIME_STATE.suffix + ".tmp")
    try:
        temp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temp, QWEN25_VL_RUNTIME_STATE)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _terminate_qwen25_vl_pid(pid: int) -> bool:
    """Terminate the exact PID returned by our own launcher and wait briefly."""
    try:
        if os.name == "nt":
            # On this Windows CUDA setup, taskkill can return access denied for
            # llama-server even though the same desktop session can manage it.
            # Use the local PowerShell process API after the ownership check;
            # PID is an int recorded only from our own Popen result.
            command = (
                "$ErrorActionPreference='Stop'; "
                f"Stop-Process -Id {pid} -Force -ErrorAction Stop"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=15)
            if result.returncode != 0 and _runtime_pid_alive(pid):
                return False
        else:
            os.kill(pid, 15)
    except Exception:
        return False
    deadline = time.monotonic() + 10
    while _runtime_pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    return not _runtime_pid_alive(pid)


def open_qwen25_vl_server_log(caller: str):
    """Append handle for one llama-server launch's stdout+stderr.

    Pass it as Popen stdout (stderr=STDOUT), then call
    close_qwen25_vl_server_log(handle, pid) so this process drops its copy;
    the server keeps the inherited handle. Returns subprocess.DEVNULL if the
    log cannot be opened: a logging failure must never block the runtime.
    """
    path = QWEN25_VL_SERVER_LOG
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size > QWEN25_VL_SERVER_LOG_MAX_BYTES:
            os.replace(path, path.with_name(path.name + ".prev"))
    except OSError:
        pass
    try:
        handle = path.open("ab")
        handle.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} "
                     f"llama-server launch by {caller} =====\n".encode("utf-8"))
        handle.flush()
        return handle
    except OSError:
        return subprocess.DEVNULL


def close_qwen25_vl_server_log(handle, pid: int | None = None) -> None:
    """Record the launched PID and close this process's copy of the log handle."""
    if handle is subprocess.DEVNULL or handle is None:
        return
    try:
        if pid:
            handle.write(f"===== pid {int(pid)} =====\n".encode("utf-8"))
            handle.flush()
    except (OSError, ValueError, TypeError):
        pass
    try:
        handle.close()
    except OSError:
        pass


def ensure_qwen25_vl_runtime(timeout_seconds: int = 150) -> bool:
    """Start the configured local VLM only for an approved media batch.

    No download occurs here.  The caller must already have checked render
    ownership and VRAM through ``router.plan_vision_vram``.  The PID file lets
    this module later release only the runtime it started itself.
    """
    if not (qwen25_vl_files_ready() and QWEN25_VL_LLAMA_SERVER.is_file()):
        return False
    if not qwen25_vl_checksums_ok():
        return False
    if llama_cpp_client.up(QWEN25_VL_RUNTIME_HOST):
        return True
    args = [str(QWEN25_VL_LLAMA_SERVER), "--model", str(QWEN25_VL_GGUF),
            "--mmproj", str(QWEN25_VL_MMPROJ), "--host", "127.0.0.1", "--port", "11436",
            # `extract_video_actions` batches up to 20 one-second frames. Its
            # detailed action prompt is ~21K visual/text tokens, so 16K rejects
            # a valid video before inference. This runtime is temporary and is
            # released immediately after the media batch.
            "--ctx-size", "32768", "--n-gpu-layers", "99", "--image-min-tokens", "1024",
            "--flash-attn", "auto", "--no-webui"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    log = open_qwen25_vl_server_log("capabilities.ensure_qwen25_vl_runtime")
    try:
        try:
            proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=flags)
        except Exception:
            close_qwen25_vl_server_log(log)
            raise
        close_qwen25_vl_server_log(log, proc.pid)
        # If recording ownership fails, immediately terminate only the process
        # returned by this Popen call. Leaving it alive would create an orphan
        # that no later watcher can safely release.
        try:
            _write_qwen25_vl_runtime_state(proc.pid)
        except Exception:
            _terminate_qwen25_vl_pid(proc.pid)
            return False
    except Exception:
        return False
    # After an owned ComfyUI still render, the driver can take tens of seconds
    # to return VRAM even though port 8188 has already closed.  The exact VLM
    # itself needs roughly a minute to initialise.  90 seconds therefore
    # turned a healthy handoff into a false semantic failure; 150 seconds is
    # still bounded and remains below the media-request timeout.
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if llama_cpp_client.up(QWEN25_VL_RUNTIME_HOST):
            return True
        time.sleep(1)
    # A failed readiness probe is not a reason to keep a 10+ GB server alive.
    # The state was recorded above, so cleanup remains ownership-safe.
    release_qwen25_vl_runtime()
    return False


def _runtime_pid_alive(pid: int) -> bool:
    """Return whether the owned runtime PID still exists.

    ``os.kill(pid, 0)`` is not a sufficient Windows probe: its Windows error
    mapping cannot distinguish this CUDA child reliably. `tasklist` can also
    return an access-denied pseudo-result even for a server the current desktop
    session can see. PowerShell's `Get-Process` is the reliable local probe on
    this workstation; a numeric PID is the only interpolated value.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            command = (
                "$ErrorActionPreference='SilentlyContinue'; "
                f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} "
                "else { exit 1 }"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            # A failed probe must not authorize deletion of the ownership
            # record. Treat unknown state as still live so release fails safe.
            return True
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def release_qwen25_vl_runtime() -> bool:
    """Release the VLM after its batch, without touching a manually started one."""
    try:
        state = json.loads(QWEN25_VL_RUNTIME_STATE.read_text(encoding="utf-8"))
        pid = int(state.get("pid", 0))
    except Exception:
        return False
    # Do not discard the ownership record if Windows refuses to terminate a
    # still-live runtime. Keeping it makes a later safe retry possible and
    # prevents an orphaned VLM from silently occupying the GPU forever.
    if not _terminate_qwen25_vl_pid(pid):
        return False
    try:
        QWEN25_VL_RUNTIME_STATE.unlink()
    except FileNotFoundError:
        pass
    return True


def _is_vision(host: str, model: str) -> bool:
    return "vision" in _model_capabilities(host, model)


def vision_model(host: str | None = None) -> str | None:
    """Return only the operator-selected Qwen2.5-VL import.

    ``host`` remains in this compatibility signature for older callers, but it
    is intentionally irrelevant: this GGUF is served through the private
    llama.cpp runtime, never substituted with an arbitrary Ollama VLM.
    """
    del host
    return QWEN25_VL_MODEL if qwen25_vl_files_ready() else None


def capability(name: str) -> dict:
    if name == "vision":
        direct_ready = qwen25_vl_runtime_available()
        files_ready = qwen25_vl_files_ready()
        gpu_model = QWEN25_VL_MODEL if files_ready else None
        model = gpu_model
        return {
            "available": bool(model),
            "model": model,
            "models": {"gpu": gpu_model, "cpu": None},
            "reason": ("exact Qwen2.5-VL Caption V4 GGUF and matched projector are ready; "
                       "the lazy llama.cpp runtime starts only for a queued media batch" if model else
                       "the exact Qwen2.5-VL Caption V4 GGUF and matched projector are not both present"),
            "install": (None if model else
                        "Run local_agent\\setup_qwen25_vl_caption.ps1 to fetch the "
                        "Qwen2.5-VL GGUF and matching mmproj, then import it as "
                        f"`{QWEN25_VL_MODEL}`."),
            "size": "5.33 GB local GGUF pair" if model else
                    "approximately 5.33 GB download for Q4_K_M GGUF plus matching Q8_0 mmproj",
            "qwen25_vl_files": qwen25_vl_files(),
            "runtime": ("llama.cpp CUDA" if direct_ready else "lazy llama.cpp; not loaded"),
            "runtime_host": QWEN25_VL_RUNTIME_HOST if direct_ready else None,
        }
    if name == "video_frames":
        ok = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        return {
            "available": ok,
            "reason": "ffmpeg and ffprobe installed" if ok else "ffmpeg or ffprobe missing",
            "install": "Install FFmpeg.", "size": "varies",
        }
    if name == "transcription":
        faster = importlib.util.find_spec("faster_whisper") is not None
        comfy = comfy_whisper_available()
        engine = "faster_whisper" if faster else "comfy_whisper_tiny" if comfy else None
        return {
            "available": bool(engine),
            "engine": engine,
            "model": ("large-v3" if faster else str(WHISPER_MODEL) if comfy else None),
            "python": str(COMFY_PYTHON) if comfy and not faster else None,
            "gpu_required": False,
            "reason": ("faster_whisper importable" if faster else
                       "existing ComfyUI Whisper tiny checkpoint is usable offline on four CPU threads" if comfy else
                       "no complete local transcription runtime/model found"),
            "install": (None if engine else
                        "Install faster-whisper and a Whisper model only when downloads are authorised."),
            "size": ("already on disk" if engine else
                     "approximately 1.5 GB for large-v3 plus the Python package"),
        }
    if name == "voice_compare":
        return {
            "available": False,
            "reason": "no local speaker-embedding model is installed",
            "install": "Install a local speaker-embedding model only when downloads are authorised.",
            "size": "model-dependent",
        }
    if name == "audio_measure":
        ok = bool(shutil.which("ffmpeg") and importlib.util.find_spec("numpy"))
        return {
            "available": ok,
            "reason": "FFmpeg and NumPy installed" if ok else "FFmpeg or NumPy missing",
            "install": "Install the missing local dependency.", "size": "varies",
        }
    if name == "exemplar_retrieval":
        available = importlib.util.find_spec("chromadb") is not None
        return {
            "available": available,
            "reason": ("chromadb installed; semantic exemplar retrieval and deduplication are active"
                       if available else "chromadb is not installed"),
            "install": None if available else "pip install chromadb",
            "feature": "approved local exemplar retrieval and semantic deduplication",
        }
    if name == "feedback_encryption":
        available = importlib.util.find_spec("cryptography") is not None
        return {
            "available": available,
            "reason": ("cryptography installed; feedback records are encrypted at rest"
                       if available else "cryptography is not installed"),
            "install": None if available else "pip install cryptography",
            "feature": "AES-256-GCM idle-only encryption for local feedback records",
        }
    if name == "qwen_image_diffusion":
        present = QWEN_IMAGE_NSFW_FILE.is_file()
        size = QWEN_IMAGE_NSFW_FILE.stat().st_size if present else 0
        return {
            "available": present and size == QWEN_IMAGE_NSFW_BYTES,
            "loaded": False,
            "load_policy": ("identity only; work/image_render.py has no Qwen-Image LoRA "
                            "graph (it is RealVisXL CheckpointLoaderSimple). Do not load "
                            "this adapter from sensory analysis or import."),
            "repository": QWEN_IMAGE_NSFW_REPOSITORY,
            "base_model": "Qwen/Qwen-Image",
            "kind": "lora",
            "checkpoint": str(QWEN_IMAGE_NSFW_FILE),
            "expected_bytes": QWEN_IMAGE_NSFW_BYTES,
            "expected_sha256": QWEN_IMAGE_NSFW_SHA256,
            "reason": ("Qwen-Image-NSFW LoRA file is present; UPGRADE 13 cannot load it "
                       "because its planner only builds SDXL CheckpointLoaderSimple graphs"
                       if present else
                       "Qwen-Image-NSFW LoRA is not on disk; UPGRADE 13 has no loader for it"),
        }
    raise KeyError(f"unknown capability {name!r}")


def vision_tiers(host: str | None = None, *, include_unloaded: bool = False) -> list[dict]:
    """Installed, vision-capable model tiers in preference order (largest first).

    Each entry: {"label", "model", "vram_need_mb", "task_strengths"}.
    Only tiers with at least one installed + vision-capable model are returned.
    """
    del host, include_unloaded
    result = []
    for td in _TIER_DEFS:
        if td["label"] == "primary" and qwen25_vl_files_ready():
            result.append({
                "label": td["label"], "model": QWEN25_VL_MODEL,
                "vram_need_mb": td["vram_need_mb"], "task_strengths": td["task_strengths"],
                "runtime": "llama.cpp",
            })
    return result


def action_model(host: str | None = None) -> tuple[str, int]:
    """Return (model_name, vram_need_mb) for the video action extractor.

    Qwen2.5-VL caption is deliberately reused for action extraction.  It is the
    configured vision model and fits a 16 GB GPU without CPU layer offload.
    Raises RuntimeError with an install command if the model is not installed or
    does not advertise the vision capability.  Callers must handle RuntimeError
    and surface the message to the operator rather than crashing.
    """
    host = host or router.GPU_HOST
    del host
    # The VLM is deliberately lazy. A complete local GGUF/mmproj pair is enough
    # for the watcher to service a queued job; requiring an already-running
    # runtime here falsely reports the configured model as "not installed".
    if qwen25_vl_files_ready() or qwen25_vl_runtime_available():
        return QWEN25_VL_MODEL, QWEN25_VL_VRAM_MB
    raise RuntimeError(
        f"{QWEN25_VL_MODEL!r} is not installed or does not have the vision capability. "
        "Run local_agent\\setup_qwen25_vl_caption.ps1."
    )


def all_capabilities() -> dict:
    result = {name: capability(name) for name in
              ("vision", "video_frames", "audio_measure", "transcription", "voice_compare",
               "qwen_image_diffusion", "exemplar_retrieval", "feedback_encryption")}
    # The same Qwen2.5-VL import is used for dense chronological action logs.
    try:
        model, vram_mb = action_model()
        result["action_extraction"] = {
            "available": True,
            "model": model,
            "reason": "exact local Qwen2.5-VL Caption V4 GGUF plus matched projector are ready",
            "vram_need_mb": vram_mb,
            "tool": "extract_video_actions",
            "use_for": "dense second-by-second action log, H3 prompt shot beats",
        }
    except RuntimeError as exc:
        result["action_extraction"] = {
            "available": False,
            "model": QWEN25_VL_MODEL,
            "reason": str(exc),
            "install": "Run local_agent\\setup_qwen25_vl_caption.ps1.",
            "tool": "extract_video_actions",
        }
    return result


if __name__ == "__main__":
    print(json.dumps(all_capabilities(), indent=2))
