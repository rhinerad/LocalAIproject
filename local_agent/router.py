#!/usr/bin/env python3
"""Decide whether the agent runs on the GPU or the CPU, and switch automatically.

THE RULE
--------
    GPU idle    ->  big model on the GPU. Fast, better answers.
    GPU busy    ->  small model on CPU. Slower, but the render is untouched.

Checked **before every turn**, so a render that starts mid-conversation moves the
next reply to CPU without the operator doing anything.

WHY THIS IS NOT JUST "TRY THE GPU AND SEE"
------------------------------------------
A 14B model in VRAM is 9-10 GB. A MiniMax H3 render at 0.9 MP needs most of the
card. If the agent is holding that memory when the supervisor starts a clip, the
render OOMs — and this project's standing rule is that exactly one process owns
the GPU at a time.

So the agent does not merely avoid *starting* on GPU while busy. When it detects
a render it **actively unloads** its own GPU model (`keep_alive: 0`) before
answering on CPU. Yielding late is the same as not yielding.

THREE INDEPENDENT BUSY SIGNALS — ANY ONE IS ENOUGH
--------------------------------------------------
1. `runtime/render_queue_owner.json` names a live PID. This is the project's own
   lock, claimed by `render_audio_pass.py` and `render_voice_auditions.py`.
   Most authoritative: it means a render *intends* to use the card.
2. Port **8188** is listening — a ComfyUI backend is up.
3. `nvidia-smi` reports VRAM in use above `VRAM_BUSY_MB`, or any compute process
   that is not this agent's own Ollama.

Signal 1 catches the window between claiming the queue and the backend actually
loading, which is exactly when a naive VRAM check would say "idle" and let the
agent grab the card. Signals 2 and 3 catch a render started outside the project's
tooling — a manual ComfyUI session, which is how the good-audio takes were made.

**Failing safe:** if `nvidia-smi` cannot be run at all, the GPU is treated as
BUSY. An unknown GPU state must never be read as permission to use it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse

from atomic_io import atomic_write_text

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
OWNER = EQ / "runtime" / "render_queue_owner.json"
BATCH_RENDER_OWNER = ROOT / "batch_render_queue_owner.json"
IMAGE_RENDER_OWNER = ROOT / "work" / "runtime" / "image_render_owner.json"
RUNTIME = Path(__file__).resolve().parent / "runtime"
CHAT_BUSY_FILE = RUNTIME / "chat_busy.json"
GPU_OWNED_FILE = RUNTIME / "gpu_owned_residents.json"
MEDIA_PRESSURE_FILE = RUNTIME / "media_vram_pressure.json"
# Watcher sets this before the VLM is proven up. A failed start used to
# leave the file forever and silently demote every later pinned 14B chat
# (2026-09-05dw). Readers treat a stamp older than this as absent.
MEDIA_PRESSURE_TTL_S = 300
GPU_OWNED_SCHEMA = "gpu-owned-residents-v1"

CPU_HOST = os.environ.get("EQUAL_SHARES_CPU_HOST", "127.0.0.1:11435")
GPU_HOST = os.environ.get("EQUAL_SHARES_GPU_HOST", "127.0.0.1:11434")

# The GPU reasoning pair.  Both names are configurable so an operator can use
# the current Huihui v2 tags without changing code.  The fallback is still a
# GPU model: silently accepting CPU layer offload is precisely what this pair
# exists to prevent.
PRIMARY_REASONING_MODEL = os.environ.get(
    "EQUAL_SHARES_PRIMARY_REASONING_MODEL", "huihui_ai/qwen3-abliterated:14b")
FALLBACK_REASONING_MODEL = os.environ.get(
    "EQUAL_SHARES_FALLBACK_REASONING_MODEL", "huihui_ai/qwen3-abliterated:8b")
PRIMARY_SAFE_PROMPT_TOKENS = int(
    os.environ.get("EQUAL_SHARES_PRIMARY_SAFE_PROMPT_TOKENS", "16000"))
CODING_MODEL = os.environ.get(
    "EQUAL_SHARES_CODING_MODEL", "josiefied-qwen2.5-coder-14b:q4_k_m")
CODING_FALLBACK_MODEL = os.environ.get(
    "EQUAL_SHARES_CODING_FALLBACK_MODEL",
    "huihui_ai/qwen2.5-coder-abliterate:7b")

# Capability-based auto routing (TODO.md 2026-09-04). Tags are the ones
# smoke-tested in CHANGELOG/2026-09-04h. Qwythos lives on the Mac worker and
# is reached through farm_offload (Celery), not a second HTTP transport.
QWYTHOS_MODEL = os.environ.get(
    "EQUAL_SHARES_QWYTHOS_MODEL",
    "richardyoung/qwythos-9b-abliterated:latest")
DEEPSEEK_MODEL = os.environ.get(
    "EQUAL_SHARES_DEEPSEEK_MODEL",
    "huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M")
JOSIEFIED_CODER_MODEL = os.environ.get(
    "EQUAL_SHARES_JOSIEFIED_CODER_MODEL",
    "josiefied-qwen2.5-coder-14b:q4_k_m")
# Farm/Qwythos path only. GPU-resident ceilings live in GPU_VRAM_NUM_CTX
# (MODEL_VRAM_BUDGET.md 2026-09-05 addendum — 95% of this card's VRAM fit).
CAPABILITY_GPU_NUM_CTX = int(os.environ.get(
    "EQUAL_SHARES_CAPABILITY_GPU_NUM_CTX", "8192"))

CAP_TOOL = "tool"
CAP_LOGIC = "logic"
CAP_CODE = "code"
CAP_IMAGE = "image"
CAP_CREATIVE = "creative"  # large prompt/storyboard packs; not gpu_image

_CODE_SIGNAL = re.compile(
    r"\b(?:python|javascript|typescript|rust|golang|\bjava\b|c\+\+|csharp|"
    r"stack\s*trace|syntax\s+error|unit\s*tests?|pytest|"
    r"write\s+(?:a\s+|the\s+)?(?:function|class|module|script|code)|"
    r"debug\s+this|compile\s+error)\b",
    re.I,
)

# Still-frame / story-image generation. Checked before length-based
# needs_escalation so a long photoreal brief is not stamped CAP_LOGIC
# (DeepSeek) or CAP_TOOL (Mac Qwythos). "attached image" / see_image
# analysis is not generation and must not match.
_IMAGE_GEN_SIGNAL = re.compile(
    r"(?:"
    r"still[- ]frames?(?:\s+only)?"
    r"|start\s*\+\s*last"
    r"|start and last(?: still)? frames?"
    r"|(?:start|end)\s+frame"
    r"|plan_story_image|render_story_image"
    r"|(?:pre|clip)\d{1,2}_(?:start|last)\.png"
    r"|images?\s+only"
    r"|(?:generate|make|render|create)\b.{0,80}\b"
    r"(?:still frames?|pngs?|jpegs?|images?|photos?|stills?|photoreal)"
    r"|(?:photoreal|photorealistic).{0,80}\b(?:still|frame|png|image|photo)"
    r"|storyboard.{0,40}\b(?:frame|still|image|png|photo)"
    r"|no captions on the images"
    r"|(?:using|with|via)\s+flux\b"
    r"|\bflux\b.{0,40}\b(?:model|checkpoint|unet|photos?|images?|stills?)"
    r")",
    re.I | re.S,
)

# This is a deliberate, opt-in exception to the normal Huihui reasoning pair.
# It is exposed as a *new-chat* choice only, never selected automatically, and
# is GPU-only: the Q4_K_M blob already sits on the 1.25 GiB leftover, so a
# pinned chat waits for a free GPU rather than silently becoming an unrelated
# 8B conversation. num_ctx is GPU_VRAM_NUM_CTX, not a round 8k.
GPT_OSS_20B_HERETIC_MODEL = "gpt-oss-20b-heretic"
GPU_ONLY_OPT_IN_MODELS = (GPT_OSS_20B_HERETIC_MODEL,)

# Opt-in PowerInfer row in the same picker as Heretic. It is not an Ollama
# tag: decide() routes it to the loopback OpenAI proxy, never /api/chat.
POWERINFER_MODEL_ALIAS = os.environ.get("POWERINFER_MODEL_ALIAS", "powerinfer-local")
POWERINFER_PROXY_HOST = (
    f"{os.environ.get('POWERINFER_PROXY_BIND', '127.0.0.1')}:"
    f"{os.environ.get('POWERINFER_PROXY_PORT', '8091')}"
)
POWERINFER_BACKEND_URL = os.environ.get(
    "POWERINFER_BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
POWERINFER_SERVER_EXE = os.environ.get(
    "POWERINFER_SERVER_EXE", r"A:\PowerInferBuild\bin\server.exe")


def is_gpu_only_opt_in_model(model: str | None) -> bool:
    """Whether ``model`` is a deliberate GPU-only chat choice.

    Compare as an Ollama family+tag, not a raw string. ``chat_models()`` can
    emit ``gpt-oss-20b-heretic:latest`` when ``/api/tags`` lists that form
    (``ollama create gpt-oss-20b-heretic`` stores the default ``:latest`` tag,
    and ``_installed_variant`` returns the catalogue name as the picker
    ``name``). An exact-string pin would then miss and fall through to a CPU
    "cannot run now" refusal.
    """
    return any(_is_configured_variant(model, name) for name in GPU_ONLY_OPT_IN_MODELS)


def is_powerinfer_model(model: str | None) -> bool:
    """Whether ``model`` is the opt-in PowerInfer picker entry.

    The picker always stores ``POWERINFER_MODEL_ALIAS`` verbatim, but decide()
    still uses the same family+tag comparison as Heretic so a ``:latest``
    suffix cannot miss the GPU-only pin.
    """
    return _is_configured_variant(model, POWERINFER_MODEL_ALIAS)


def _family_tag(model: str) -> tuple[str, str]:
    """Split an Ollama model name without losing a v2-style tag suffix."""
    family, sep, tag = str(model).partition(":")
    return family, tag if sep else "latest"


def _installed_variant(have: list[str], configured: str) -> str | None:
    """Find the configured tag or its compatible ``-v2`` Ollama variant."""
    if configured in have:
        return configured
    family, tag = _family_tag(configured)
    for candidate in have:
        got_family, got_tag = _family_tag(candidate)
        if got_family == family and (got_tag == tag or got_tag.startswith(tag + "-")):
            return candidate
    return None


def _is_configured_variant(model: str | None, configured: str) -> bool:
    if not model:
        return False
    family, tag = _family_tag(configured)
    got_family, got_tag = _family_tag(model)
    return got_family == family and (got_tag == tag or got_tag.startswith(tag + "-"))


def is_coding_model(name: str | None) -> bool:
    """True for the configured coder tags or any installed *coder* chat model."""
    if not name:
        return False
    if _is_configured_variant(name, CODING_MODEL):
        return True
    if _is_configured_variant(name, CODING_FALLBACK_MODEL):
        return True
    return "coder" in str(name).lower()


def preferred_coding_model(have: list[str]) -> str | None:
    """Pick an installed coder, then any remaining preference-list match."""
    for candidate in (CODING_MODEL, CODING_FALLBACK_MODEL):
        found = _installed_variant(have, candidate)
        if found:
            return found
    for candidate in GPU_MODELS + CPU_MODELS:
        if "coder" in candidate.lower():
            found = _installed_variant(have, candidate)
            if found:
                return found
    return None


# 95% of max FP16-KV context that fits this RTX 5080 (16303 MiB) with the
# model alone on the GPU. Math: MODEL_VRAM_BUDGET.md 2026-09-05 addendum.
# Routing (which tag decide() picks) is independent of these ceilings.
GPU_VRAM_NUM_CTX = {
    PRIMARY_REASONING_MODEL: 33976,
    FALLBACK_REASONING_MODEL: 40960,
    DEEPSEEK_MODEL: 28371,
    JOSIEFIED_CODER_MODEL: 28371,
    GPT_OSS_20B_HERETIC_MODEL: 1742,
    # Same GGUF blobs as DeepSeek / Josiefied; template-only retags.
    "deepseek-r1-abliterated-14b:r1-tools": 28371,
    "josiefied-qwen2.5-coder-14b:official-tools": 28371,
}


def gpu_vram_num_ctx(model: str | None) -> int | None:
    """VRAM-derived GPU ``num_ctx`` for a routing tag, or None if unknown."""
    if not model:
        return None
    if is_gpu_only_opt_in_model(model):
        return GPU_VRAM_NUM_CTX[GPT_OSS_20B_HERETIC_MODEL]
    for tag, ctx in GPU_VRAM_NUM_CTX.items():
        if _is_configured_variant(model, tag):
            return ctx
    if is_coding_model(model):
        return GPU_VRAM_NUM_CTX[JOSIEFIED_CODER_MODEL]
    return None

# Preference order per tier. First one actually installed wins.
# The Huihui pair is the default conversation-model family. Do not expose stock
# Qwen, Dolphin, or a vision model as ordinary chat choices: visual/audio
# analysis is handled by dedicated sensory tools. ``GPU_ONLY_OPT_IN_MODELS`` is
# the narrow, operator-requested exception and is never selected automatically.
# CPU: prefer smaller models — on 4 threads, size is the main cost.
CPU_MODELS = [FALLBACK_REASONING_MODEL, "equal-shares-cpu", "equal-shares",
              "huihui_ai/qwen2.5-coder-abliterate:7b", "huihui_ai/qwen2.5-abliterate:7b",
              "huihui_ai/qwen2.5-coder-abliterate:14b"]
# GPU chat uses a general text/tool model.  Qwen3-VL variants are deliberately
# absent: they are selected by capabilities.py for vision/video, not conversation.
# Mixing those roles caused ordinary writing requests to be treated as sensory jobs.
GPU_MODELS = [PRIMARY_REASONING_MODEL, FALLBACK_REASONING_MODEL,
              DEEPSEEK_MODEL, JOSIEFIED_CODER_MODEL,
              "equal-shares-gpu", "equal-shares",
              "huihui_ai/qwen3.6-abliterated:27b",
              "huihui_ai/qwen2.5-coder-abliterate:32b", "huihui_ai/qwen2.5-abliterate:32b",
              "huihui_ai/qwen2.5-abliterate:14b", "huihui_ai/qwen2.5-coder-abliterate:14b"]

# The model picker describes *installed capability*, not the transient routing
# choice for this exact second. While ComfyUI owns the GPU, status polling
# deliberately avoids querying the GPU Ollama catalogue. Retain the most recent
# verified catalogue so a dual-tier Huihui model is not relabelled “CPU only”
# merely because a render is in progress.
_LAST_VERIFIED_GPU_MODELS: set[str] = set()


def chat_models(*, include_gpu: bool = True) -> list[dict]:
    """Chat-model picker entries and the tiers where each is available.

    Vision/audio models are intentionally absent because they are invoked by the
    sensory tools. The opt-in Heretic entry stays visible before installation so
    the operator can see how to enable it; it is marked unavailable until the
    exact local Ollama model exists on the GPU server.
    """
    global _LAST_VERIFIED_GPU_MODELS
    cpu = set(_tags(CPU_HOST)) if up(CPU_HOST) else set()
    # A render owns the GPU. The status badge and model picker can still show
    # CPU-capable models without waking or probing the GPU Ollama service.
    if include_gpu and up(GPU_HOST):
        gpu = set(_tags(GPU_HOST))
        if gpu:
            _LAST_VERIFIED_GPU_MODELS = set(gpu)
    else:
        # Display cache only. It never authorizes a GPU request: decide()
        # still performs a fresh routing check and yields to ComfyUI.
        gpu = set(_LAST_VERIFIED_GPU_MODELS)
    # The picker must only offer models that can genuinely be selected on the
    # currently available tier.  The primary 14B may be visible in a shared
    # CPU model store, but it is intentionally not a CPU chat choice: CPU
    # routing always uses the 8B resilience model to avoid slow/offloaded
    # execution.  Showing the 14B during a ComfyUI render would promise a
    # selection that is deliberately rerouted.
    # A verified display cache is enough to retain the GPU-capable options
    # during a busy poll; an empty cache still produces the conservative
    # CPU-only picker used at a brand-new busy startup.
    ordered = list(dict.fromkeys(
        (GPU_MODELS + CPU_MODELS) if (include_gpu or gpu) else CPU_MODELS
    ))
    # A busy-at-start server has no verified GPU catalogue yet. Keep the
    # primary 14B visible as a disabled GPU choice instead of making it appear
    # as though the operator's model vanished. It becomes selectable after a
    # fresh idle GPU inventory confirms its exact tag.
    if PRIMARY_REASONING_MODEL not in ordered:
        ordered.insert(0, PRIMARY_REASONING_MODEL)
    out: list[dict] = []
    seen: set[str] = set()
    for preferred in ordered:
        # Show an installed -v2 tag under its real name, not as the older tag.
        cpu_name = _installed_variant(list(cpu), preferred)
        gpu_name = _installed_variant(list(gpu), preferred)
        name = gpu_name or cpu_name
        if name and name not in seen:
            primary = _is_configured_variant(name, PRIMARY_REASONING_MODEL)
            gpu_available = bool(gpu_name)
            out.append({
                "name": name,
                # The 14B is never a CPU execution choice. A CPU-side copy is
                # used only to keep its picker entry visible while the GPU is
                # reserved; selecting it remains impossible until GPU presence
                # is freshly verified.
                "cpu": (name in cpu) and not primary,
                "gpu": gpu_available,
                "available": (gpu_available if primary else True),
                "gpu_only": primary,
                "kind": "coding" if is_coding_model(name) else "chat",
                **({"label": "huihui_ai/qwen3-abliterated:14b (GPU currently unavailable)",
                    "setup_hint": "The 14B model remains installed; release the GPU to select it.",
                    "unavailable_reason": "GPU currently unavailable"}
                   if primary and not gpu_available else {}),
            })
            seen.add(name)
    # At a fresh render-busy startup there may be no safe GPU catalogue cache.
    # Keep the operator's configured 14B choice in the picker nevertheless,
    # but make its unavailable state explicit. It must never appear CPU-capable
    # and cannot authorize a GPU request while the render owns the card.
    if PRIMARY_REASONING_MODEL not in seen:
        out.insert(0, {
            "name": PRIMARY_REASONING_MODEL,
            "cpu": False,
            "gpu": False,
            "available": False,
            "gpu_only": True,
            "kind": "chat",
            "label": "huihui_ai/qwen3-abliterated:14b (GPU currently unavailable)",
            "setup_hint": "The 14B model remains installed; release the GPU to select it.",
            "unavailable_reason": "GPU currently unavailable",
        })
        seen.add(PRIMARY_REASONING_MODEL)
    for name in GPU_ONLY_OPT_IN_MODELS:
        if name in seen:
            continue
        installed = _installed_variant(list(gpu), name)
        out.append({
            "name": installed or name,
            "cpu": False,
            "gpu": bool(installed),
            "available": bool(installed),
            "gpu_only": True,
            "kind": "chat",
            "label": "gpt-oss-20b-heretic (opt-in, GPU only)",
            "setup_hint": "Run setup_gpt_oss_20b_heretic.py --create first.",
        })
        seen.add(installed or name)
    if POWERINFER_MODEL_ALIAS not in seen:
        ready, ready_why = powerinfer_ready()
        out.append({
            "name": POWERINFER_MODEL_ALIAS,
            "cpu": False,
            "gpu": ready,
            "available": ready,
            "gpu_only": True,
            "kind": "base_completion",
            "backend": "powerinfer",
            "label": (f"{POWERINFER_MODEL_ALIAS} (opt-in, PowerInfer, GPU, text-only)"
                      if ready else
                      f"{POWERINFER_MODEL_ALIAS} (opt-in, PowerInfer — not running)"),
            "setup_hint": (
                "Start PowerInfer server.exe on "
                f"{POWERINFER_BACKEND_URL} and local_agent\\powerinfer_openai_proxy.py "
                f"on http://{POWERINFER_PROXY_HOST}. The router does not start them."
            ),
            **({} if ready else {"unavailable_reason": ready_why}),
        })
    return out

COMFY_PORT = 8188
VRAM_BUSY_MB = 2500        # anything above this and we assume a render owns it
# Post-/free verify only (2026-09-04: idle-open 345, post-generate resident 2459).
# Not an idle detector. VRAM_BUSY_MB would accept 2459 and stack a 14B.
TIMESHARE_VRAM_CLEAR_MAX_MIB = 800
STATUS_TIMESHARE_IDLE_REASON = "8188 up, idle, agent may claim"
_TIMESHARE_LOG = logging.getLogger("local_agent.router.timeshare")
# Last queue idle bool written by `_comfy_queue_idle` (the timeshare probe).
# status() reads this instead of urllib/MCP. None = unknown (best-effort).
_TIMESHARE_QUEUE_CACHE: dict = {"idle": None, "why": "", "at": 0.0}

# On Windows WDDM, nvidia-smi --query-compute-apps lists ALL GPU-context processes,
# including browsers, Electron desktop shells, and the idle Steam client using
# display acceleration. These do not conflict with renders. The Codex/ChatGPT
# desktop window and Steam's launcher shell are such contexts; treating their
# ~tens-of-MB display context as a render forced every local chat to the CPU
# even while the GPU was genuinely idle. A real game has its own executable and
# remains a foreign owner; the VRAM threshold below also remains authoritative.
# Port 8188 and queue_owner already catch active renders; this is belt-and-suspenders
# for manual ComfyUI sessions not started via the project's tooling.
_BROWSER_NAMES = frozenset(
    ["brave", "chrome", "firefox", "msedge", "edge", "opera", "safari",
     "iexplore", "microsoftedge", "vivaldi", "arc", "chatgpt", "codex",
     "steam"]
)

# Salad/XMRig and similar miners sit on the card but are not a ComfyUI render
# reservation. Treating them as "GPU busy" forced every chat onto the dedicated
# CPU Ollama (num_gpu=0, 4 threads), so no model had GPU layers. They must not
# steal the GPU chat path.
_BACKGROUND_GPU_COMPUTE = frozenset([
    "xmrig", "salad", "nicehash", "excavator", "phoenixminer", "t-rex",
    "nbminer", "gminer",
])


def _is_background_gpu_compute(path: str) -> bool:
    text = str(path or "").lower().replace("/", "\\")
    stem = Path(path).stem.lower() if path else ""
    if stem in _BACKGROUND_GPU_COMPUTE or "xmrig" in stem:
        return True
    return "\\salad\\" in text

# Native tool schemas plus the reviewed operating policy are a little under
# 10k tokens on their own.  An 8k CPU context therefore cannot even carry a
# normal tool-capable turn, let alone the operator's request and observations.
# 16k remains modest in host RAM, stays strictly CPU-only, and leaves useful
# room for the active request while ComfyUI owns VRAM.
# Single source of truth for the CPU thermal thread cap. Windows exposes no
# usable package-temperature sensor on this machine, so this cap (plus the
# ban on a second concurrent local model) is the CPU thermal safeguard.
# Every CPU-bound Ollama caller in this codebase must go through this
# constant rather than hardcoding its own "4" — see CHANGELOG for the
# 2026-08-31 consolidation that replaced five independent literals with it.
CPU_THREAD_CAP = 4
CPU_OPTIONS = {"num_gpu": 0, "num_thread": CPU_THREAD_CAP, "num_ctx": 16384,
               "temperature": 0.3, "top_p": 0.9, "repeat_penalty": 1.05}
GPU_OPTIONS = {"num_gpu": 99, "num_ctx": 16384,
               "temperature": 0.3, "top_p": 0.9, "repeat_penalty": 1.05}


@dataclass
class Decision:
    tier: str               # "gpu" | "cpu" | "farm"
    host: str
    model: str | None
    gpu_busy: bool
    reason: str
    detail: dict
    backend: str = "ollama"  # "ollama" | "powerinfer" | "farm"

    def options(self) -> dict:
        if self.backend == "powerinfer":
            return {"temperature": 0.3, "top_p": 0.9, "num_predict": 512}
        if self.backend == "farm" or self.tier == "farm":
            return {"num_gpu": 0, "num_thread": CPU_THREAD_CAP,
                    "num_ctx": CAPABILITY_GPU_NUM_CTX,
                    "temperature": 0.3, "top_p": 0.9, "repeat_penalty": 1.05}
        opts = dict(GPU_OPTIONS if self.tier == "gpu" else CPU_OPTIONS)
        if self.tier == "gpu":
            ctx = gpu_vram_num_ctx(self.model)
            if ctx is not None:
                opts["num_ctx"] = ctx
        return opts

    def as_dict(self) -> dict:
        return asdict(self)


# ── busy detection ────────────────────────────────────────────────────────────

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def queue_owner() -> tuple[bool, str]:
    """Does the project's own render lock name a live process?"""
    if not OWNER.is_file():
        return False, "no queue owner file"
    try:
        d = json.loads(OWNER.read_text(encoding="utf-8-sig"))
    except Exception:
        return False, "queue owner file unreadable"
    pid = int(d.get("pid", 0) or 0)
    if pid and _pid_alive(pid):
        return True, f"render queue claimed by live pid {pid} ({d.get('purpose', '?')})"
    return False, "queue owner released"


def _timeshare_enabled() -> bool:
    return os.environ.get("EQUAL_SHARES_COMFY_TIMESHARE", "1").strip() != "0"


def _owner_file_idle(path: Path) -> tuple[bool, str]:
    """Idle iff missing or parsed JSON with no live PID. Unreadable is not idle."""
    if not path.is_file():
        return True, f"{path.name} missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        pid = int(data.get("pid", 0) or 0)
    except Exception:
        return False, f"{path.name} unreadable"
    if pid and _pid_alive(pid):
        return False, f"{path.name} live pid {pid}"
    return True, f"{path.name} released"


def _owner_lock_files() -> tuple[Path, Path, Path]:
    return (OWNER, BATCH_RENDER_OWNER, IMAGE_RENDER_OWNER)


def _owners_idle_for_timeshare() -> tuple[bool, str]:
    """True iff all three files missing or parsed with no live PID (_pid_alive)."""
    reasons = []
    for path in _owner_lock_files():
        idle, why = _owner_file_idle(path)
        reasons.append(why)
        if not idle:
            return False, why
    return True, "; ".join(reasons)


def _mcp_queue_int_counts(payload) -> tuple[int, int] | None:
    """MCP list idle proof is type-is-int running/pending only. Do not len(running_jobs)."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    running, pending = payload.get("running"), payload.get("pending")
    if type(running) is int and type(pending) is int:
        return running, pending
    return None


def _comfy_queue_via_urllib() -> tuple[bool, dict]:
    url = f"http://127.0.0.1:{COMFY_PORT}/queue"
    meta: dict = {"source": "urllib"}
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        meta["status"] = "unreadable"
        meta["error"] = str(exc)
        return False, meta
    if not isinstance(payload, dict):
        meta["status"] = "unreadable"
        return False, meta
    if "queue_running" not in payload or "queue_pending" not in payload:
        meta["status"] = "unreadable"
        return False, meta
    running, pending = payload["queue_running"], payload["queue_pending"]
    if not isinstance(running, list) or not isinstance(pending, list):
        meta["status"] = "unreadable"
        return False, meta
    meta["running"] = len(running)
    meta["pending"] = len(pending)
    if running or pending:
        return False, meta
    return True, meta


def _remember_queue_idle(idle: bool, why: str) -> tuple[bool, str]:
    _TIMESHARE_QUEUE_CACHE["idle"] = bool(idle)
    _TIMESHARE_QUEUE_CACHE["why"] = why
    _TIMESHARE_QUEUE_CACHE["at"] = time.time()
    return idle, why


def _comfy_queue_idle() -> tuple[bool, str]:
    """urllib /queue timeout=1 first; MCP list timeout=1 only if urllib is unreadable."""
    import mcp_client
    idle, meta = _comfy_queue_via_urllib()
    if not isinstance(meta, dict):
        meta = {"source": "urllib", "note": str(meta)}
    if meta.get("status") != "unreadable":
        return _remember_queue_idle(idle, json.dumps(meta, sort_keys=True))
    try:
        payload = mcp_client.call(
            "queue", {"action": "list"}, timeout=1,
            lock_timeout=0.2, spawn=False)
    except Exception as exc:
        meta["mcp_error"] = str(exc)
        return _remember_queue_idle(False, json.dumps(meta, sort_keys=True))
    counts = _mcp_queue_int_counts(payload)
    if counts is None:
        meta["mcp"] = "unreadable"
        return _remember_queue_idle(False, json.dumps(meta, sort_keys=True))
    running, pending = counts
    mcp_meta = {"running": running, "pending": pending, "source": "mcp",
                "urllib": meta}
    if running > 0 or pending > 0:
        return _remember_queue_idle(False, json.dumps(mcp_meta, sort_keys=True))
    return _remember_queue_idle(True, json.dumps(mcp_meta, sort_keys=True))


def _resident_is_ours(resident: list[str]) -> bool:
    """True only when live residents include a tag this agent loaded."""
    return bool(_owned_gpu_residents(resident))


def _timeshare_powerinfer_procs(procs: list[str]) -> list[str]:
    """Names-only server.exe is occupancy only with backend_up. TCP 8080 alone is not."""
    maybe = any(
        Path(p).stem.lower() == Path(POWERINFER_SERVER_EXE).stem.lower()
        or "powerinfer" in str(p).lower()
        for p in procs)
    backend_up = powerinfer_backend_listening() if maybe else False
    return [p for p in procs if _is_powerinfer_compute(p, backend_up=backend_up)]


def _already_claimed_for_timeshare(
        model: str | None, resident: list[str] | None, pi_compute: bool
        ) -> bool:
    if resident is None:
        return False
    if resident and _resident_is_ours(resident):
        return True
    return bool(is_powerinfer_model(model) and pi_compute)


def _parse_queue_meta(queue_why: str):
    try:
        return json.loads(queue_why)
    except json.JSONDecodeError:
        return queue_why


def _comfy_free_via_urllib() -> tuple[bool, str]:
    """POST ComfyUI /free (unload_models+free_memory). Used when MCP is not started."""
    url = f"http://127.0.0.1:{COMFY_PORT}/free"
    body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = getattr(resp, "status", None)
            if status is None:
                status = resp.getcode()
            if status is not None and not (200 <= int(status) < 300):
                return False, f"/free HTTP {status}"
            return True, "HTTP /free ok"
    except Exception as exc:
        return False, f"/free error: {exc}"


def _verify_vram_after_free(prefix: str) -> tuple[bool, str, int | None]:
    used, _procs = gpu_memory()
    if used is None:
        return False, "nvidia-smi unavailable after /free", None
    if used > TIMESHARE_VRAM_CLEAR_MAX_MIB:
        return False, f"after /free used={used} MiB > {TIMESHARE_VRAM_CLEAR_MAX_MIB}", used
    return True, f"{prefix}; used={used} MiB", used


def _clear_vram_for_timeshare() -> tuple[bool, str, int | None]:
    """MCP clear_vram (spawn=False) when ready; else HTTP POST /free; used <= 800."""
    import mcp_client
    mcp_not_started = False
    mcp_err = ""
    try:
        result = mcp_client.call(
            "clear_vram",
            {"unload_models": True, "free_memory": True},
            timeout=20, lock_timeout=0.2, spawn=False)
    except Exception as exc:
        mcp_err = str(exc)
        if "MCP client is not started" in mcp_err:
            mcp_not_started = True
        else:
            return False, f"clear_vram error: {exc}", None
    else:
        if isinstance(result, str) and result.startswith("VRAM cleared successfully"):
            return _verify_vram_after_free("cleared")
        text = result if isinstance(result, str) else repr(result)
        return False, f"clear_vram failed: {text[:200]}", None

    # MCP never started — same /free body ComfyUI accepts over HTTP.
    assert mcp_not_started
    ok, free_why = _comfy_free_via_urllib()
    if not ok:
        return False, f"clear_vram error: {mcp_err}; {free_why}", None
    return _verify_vram_after_free("cleared via HTTP /free")


def try_idle_comfy_timeshare(detail: dict, model: str | None = None) -> tuple[bool, str]:
    """Owners+queue idle, then already-claimed (needs model) or /free+verify."""
    ts: dict = {}
    detail["timeshare"] = ts
    owners_idle, owners_why = _owners_idle_for_timeshare()
    ts["owners"] = owners_why
    if not owners_idle:
        ts["path"] = "cpu_fallback"
        return False, owners_why

    queue_idle, queue_why = _comfy_queue_idle()
    ts["queue"] = _parse_queue_meta(queue_why)
    if not queue_idle:
        ts["path"] = "cpu_fallback"
        return False, queue_why

    used, procs = gpu_memory()
    procs = list(procs or [])
    pi_procs = _timeshare_powerinfer_procs(procs)
    pi_compute = bool(pi_procs)
    occ = {"used_mib": used, "powerinfer_compute": pi_procs}
    ts["occupancy"] = occ
    if used is None:
        ts["path"] = "cpu_fallback"
        return False, "nvidia-smi unavailable"

    if pi_compute and not is_powerinfer_model(model):
        ts["path"] = "cpu_fallback"
        return False, "PowerInfer compute present on a non-PowerInfer pin"

    resident = _running_models(GPU_HOST)
    occ["ollama_resident"] = resident
    already = _already_claimed_for_timeshare(model, resident, pi_compute)
    if already:
        ts["path"] = "already_claimed"
        owners_idle, owners_why = _owners_idle_for_timeshare()
        queue_idle, queue_why = _comfy_queue_idle()
        ts["recheck"] = {"owners": owners_why, "queue": _parse_queue_meta(queue_why)}
        if not owners_idle or not queue_idle:
            ts["path"] = "cpu_fallback"
            return False, "recheck claimed after already-resident"
        return True, "already claimed"

    used_before = used
    pack = _clear_vram_for_timeshare()
    if not isinstance(pack, tuple) or len(pack) < 2:
        cleared, clear_why, used_after = False, repr(pack), None
    else:
        cleared, clear_why = pack[0], pack[1]
        used_after = pack[2] if len(pack) > 2 else None
    ts["clear_vram"] = {
        "ok": cleared,
        "detail": clear_why,
        "used_before": used_before,
        "used_after": used_after,
    }
    if not cleared:
        ts["path"] = "cpu_fallback"
        return False, clear_why
    owners_idle, owners_why = _owners_idle_for_timeshare()
    queue_idle, queue_why = _comfy_queue_idle()
    ts["recheck"] = {"owners": owners_why, "queue": _parse_queue_meta(queue_why)}
    if not owners_idle or not queue_idle:
        ts["path"] = "cpu_fallback"
        return False, "recheck claimed after /free"
    ts["path"] = "clear_vram"
    return True, "cleared idle ComfyUI"


def _timeshare_would_load_host_gpu(prefer: str, model: str | None,
                                   capability: str | None) -> bool:
    if prefer == "cpu":
        return False
    if is_powerinfer_model(model) or is_gpu_only_opt_in_model(model):
        return True
    if capability in {CAP_CODE, CAP_LOGIC} and (
            model is None
            or _is_configured_variant(model, DEEPSEEK_MODEL)
            or _is_configured_variant(model, JOSIEFIED_CODER_MODEL)
            or is_coding_model(model)):
        return True
    if model is None:
        return True
    if _is_configured_variant(model, QWYTHOS_MODEL):
        return False
    if any(_is_configured_variant(model, tag) for tag in GPU_MODELS):
        return True
    if is_coding_model(model):
        return True
    return False


def _maybe_comfy_timeshare(prefer: str, model: str | None, prompt: str | None,
                           skip_farm: bool, ensure_gpu_evicted: bool,
                           busy: bool, why: str, detail: dict
                           ) -> tuple[bool, str, dict, str]:
    """Classify once, skip hook for farm, else idle-ComfyUI timeshare."""
    capability = classify_capability(prompt, model=model)
    if capability:
        detail["capability"] = capability
    farm_skip = (
        model is None and capability == CAP_TOOL and not skip_farm
        and prefer != "cpu" and _farm_reachable())
    if farm_skip:
        if (ensure_gpu_evicted and prefer != "cpu" and _timeshare_enabled()
                and busy and detail.get("comfy_port_8188") == "listening"):
            detail.setdefault("timeshare", {})["path"] = "farm_skip"
        return busy, why, detail, capability
    owned, _owned_why = queue_owner()
    if not (ensure_gpu_evicted and prefer != "cpu" and _timeshare_enabled()
            and busy and detail.get("comfy_port_8188") == "listening"
            and not owned
            and _timeshare_would_load_host_gpu(prefer, model, capability)):
        return busy, why, detail, capability
    claimed, claim_why = try_idle_comfy_timeshare(detail, model=model)
    if claimed:
        detail.setdefault("timeshare", {})["outcome"] = claim_why
        return False, claim_why, detail, capability
    detail.setdefault("timeshare", {})["outcome"] = claim_why
    return busy, why, detail, capability


def comfy_listening(port: int = COMFY_PORT) -> bool:
    with socket.socket() as s:
        # This is loopback-only status telemetry.  A local listener either
        # accepts immediately or is absent; waiting 400 ms for every agent
        # hop made ordinary read-only tool batches feel serial.  Keep a small
        # finite bound so a broken local TCP stack still fails closed rather
        # than delaying the chat path.
        s.settimeout(0.02)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _tcp_up(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _powerinfer_backend_host_port() -> tuple[str, int]:
    parsed = urlparse(POWERINFER_BACKEND_URL)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 8080)
    return host, port


def _powerinfer_proxy_host_port() -> tuple[str, int]:
    host, sep, port = POWERINFER_PROXY_HOST.rpartition(":")
    if not sep:
        return "127.0.0.1", 8091
    try:
        return host or "127.0.0.1", int(port)
    except ValueError:
        return "127.0.0.1", 8091


def powerinfer_proxy_listening() -> bool:
    host, port = _powerinfer_proxy_host_port()
    return _tcp_up(host, port)


def powerinfer_backend_listening() -> bool:
    host, port = _powerinfer_backend_host_port()
    return _tcp_up(host, port)


def powerinfer_ready() -> tuple[bool, str]:
    """Short loopback probes. Never starts a process and never waits on inference."""
    proxy_host, proxy_port = _powerinfer_proxy_host_port()
    backend_host, backend_port = _powerinfer_backend_host_port()
    if not powerinfer_proxy_listening():
        return False, (
            f"PowerInfer OpenAI proxy is not listening on {proxy_host}:{proxy_port}. "
            "Start local_agent\\powerinfer_openai_proxy.py after server.exe. "
            "The router does not start them."
        )
    if not powerinfer_backend_listening():
        return False, (
            f"PowerInfer server.exe is not listening on {backend_host}:{backend_port}. "
            "Start server.exe first, then the OpenAI proxy. "
            "The router does not start them."
        )
    return True, "PowerInfer proxy and backend are reachable"


def _is_powerinfer_compute(path: str, *, backend_up: bool = False) -> bool:
    """True when nvidia-smi named this agent's PowerInfer server, not a random server.exe."""
    text = str(path or "").lower().replace("/", "\\")
    if "powerinfer" in text:
        return True
    stem = Path(path).stem.lower() if path else ""
    configured = Path(POWERINFER_SERVER_EXE).stem.lower()
    if stem != configured:
        return False
    configured_path = str(Path(POWERINFER_SERVER_EXE)).lower().replace("/", "\\")
    if configured_path and configured_path in text:
        return True
    return bool(backend_up)


def gpu_memory() -> tuple[int | None, list[str]]:
    """(used MB, process names). (None, []) if nvidia-smi is unavailable."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None, []
    try:
        _cnw = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        used = subprocess.run(
            [exe, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=12, creationflags=_cnw)
        mb = max(int(x.strip()) for x in used.stdout.split("\n") if x.strip())
        procs = subprocess.run(
            [exe, "--query-compute-apps=process_name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=12, creationflags=_cnw)
        names = [p.strip() for p in procs.stdout.splitlines() if p.strip()]
        return mb, names
    except Exception:
        return None, []


def gpu_free_mb() -> int | None:
    """Free VRAM in MB from nvidia-smi, or None if unavailable (treat as 0)."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        values = [int(value.strip()) for value in result.stdout.splitlines()
                  if value.strip()]
        return max(values) if values else None
    except Exception:
        return None


def set_chat_busy(active: bool) -> None:
    """Cross-process signal used only to avoid evicting a streaming chat turn."""
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not active:
        # Windows can briefly hold this tiny status file open while another
        # local request reads it. Status cleanup must never turn that harmless
        # race into a failed chat response. Retry a few times, then leave the
        # short-lived marker to age out rather than raising.
        for attempt in range(3):
            try:
                CHAT_BUSY_FILE.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.05)
        return
    atomic_write_text(CHAT_BUSY_FILE, json.dumps({"pid": os.getpid()}))


def chat_busy() -> bool:
    try:
        age = max(0.0, __import__("time").time() - CHAT_BUSY_FILE.stat().st_mtime)
        data = json.loads(CHAT_BUSY_FILE.read_text(encoding="utf-8"))
        return age < 600 and _pid_alive(int(data.get("pid", 0) or 0))
    except Exception:
        return False


def _name_matches_owned(name: str, configured: str) -> bool:
    return _is_configured_variant(name, configured) or _is_configured_variant(
        configured, name)


def _load_gpu_owned() -> list[str]:
    try:
        data = json.loads(GPU_OWNED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict) or data.get("schema") != GPU_OWNED_SCHEMA:
        return []
    names = data.get("models")
    if not isinstance(names, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _save_gpu_owned(models: list[str]) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    atomic_write_text(GPU_OWNED_FILE, json.dumps({
        "schema": GPU_OWNED_SCHEMA,
        "models": models,
        "updated_at": time.time(),
    }))


def note_gpu_owned(model: str | None) -> None:
    """Record that this agent selected/loaded ``model`` on GPU Ollama."""
    name = str(model or "").strip()
    if not name:
        return
    owned = _load_gpu_owned()
    if any(_name_matches_owned(name, tag) for tag in owned):
        return
    _save_gpu_owned([*owned, name])


def forget_gpu_owned(*models: str) -> None:
    """Drop ownership of tags this agent unloaded or never kept resident."""
    if not models:
        if GPU_OWNED_FILE.is_file():
            _save_gpu_owned([])
        return
    owned = _load_gpu_owned()
    kept = [tag for tag in owned
            if not any(_name_matches_owned(tag, str(m or "")) for m in models)]
    if kept != owned:
        _save_gpu_owned(kept)


def _owned_gpu_residents(resident: list[str] | None) -> list[str]:
    """Live ``/api/ps`` names this agent loaded, not merely GPU_MODELS tags.

    Tags that disappeared from ``/api/ps`` are dropped (a later third-party
    reload of the same tag is not ours). Do not prune during ``chat_busy``:
    the selected model may not have appeared in ``/api/ps`` yet.
    """
    owned = _load_gpu_owned()
    if resident is not None and not chat_busy():
        kept = [tag for tag in owned
                if any(_name_matches_owned(name, tag) for name in resident if name)]
        if kept != owned:
            _save_gpu_owned(kept)
            owned = kept
    if not resident or not owned:
        return []
    return [name for name in resident
            if name and any(_name_matches_owned(name, tag) for tag in owned)]


def set_media_pressure(active: bool) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if active:
        MEDIA_PRESSURE_FILE.write_text(
            json.dumps({"at": time.time(), "ttl_s": MEDIA_PRESSURE_TTL_S}),
            encoding="utf-8")
    else:
        try:
            MEDIA_PRESSURE_FILE.unlink()
        except FileNotFoundError:
            pass


def refresh_media_pressure() -> bool:
    """Rewrite ``at`` if the flag file is still on disk.

    In-flight vision jobs call this so a batch longer than
    ``MEDIA_PRESSURE_TTL_S`` does not lose the demotion. Unlike
    ``media_pressure()``, this does not unlink an aged stamp — the watcher
    still owns the file until ``_release_vision_batch``.
    """
    if not MEDIA_PRESSURE_FILE.is_file():
        return False
    set_media_pressure(True)
    return True


def media_pressure() -> bool:
    """True while a vision reclaim is genuinely in flight.

    The file is a leaky latch: ``_prepare_vision_batch`` writes it before
    the VLM is up, and a failed start never reached ``_release_vision_batch``.
    Expire (and unlink) a stamp older than ``MEDIA_PRESSURE_TTL_S`` so a
    leftover file cannot demote 14B chats indefinitely.
    """
    if not MEDIA_PRESSURE_FILE.is_file():
        return False
    at = None
    try:
        data = json.loads(MEDIA_PRESSURE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            at = float(data.get("at") or 0)
    except Exception:
        at = None
    if at is None or at <= 0:
        try:
            at = MEDIA_PRESSURE_FILE.stat().st_mtime
        except OSError:
            return False
    if time.time() - at > MEDIA_PRESSURE_TTL_S:
        try:
            MEDIA_PRESSURE_FILE.unlink()
        except (FileNotFoundError, OSError):
            pass
        return False
    return True


def plan_vision_vram(tiers: list[dict]) -> tuple[dict | None, str]:
    """Pick a media tier and the sole allowed chat action.

    Returns ``(tier, action)`` where action is ``none``, ``downgrade`` or
    ``evict``.  ``tier is None`` means wait: a render owns the GPU, a chat is
    streaming, telemetry is unknown, or no tier can fit even after eviction.
    """
    owned, _ = queue_owner()
    if owned or comfy_listening() or chat_busy() or not tiers:
        return None, "none"
    free = gpu_free_mb()
    if free is None:
        return None, "none"
    for tier in tiers:
        if free >= int(tier["vram_need_mb"]) + 1024:
            return tier, "none"
    resident = _running_models(GPU_HOST)
    if resident is None:
        return None, "none"
    if any(_is_configured_variant(m, PRIMARY_REASONING_MODEL) for m in resident):
        return tiers[0], "downgrade"
    if resident:
        return tiers[0], "evict"
    return None, "none"


def gpu_busy() -> tuple[bool, str, dict]:
    """Any one signal is enough. Unknown GPU state counts as busy."""
    detail: dict = {}

    owned, why = queue_owner()
    detail["queue_owner"] = why
    if owned:
        return True, why, detail

    listening = comfy_listening()
    detail["comfy_port_8188"] = "listening" if listening else "closed"
    if listening:
        return True, "a ComfyUI backend is listening on port 8188", detail

    mb, procs = gpu_memory()
    detail["vram_used_mb"] = mb
    detail["compute_processes"] = procs
    if mb is None:
        return True, ("nvidia-smi unavailable — GPU state unknown, so treating it as "
                      "busy. An unknown GPU is never permission to use it."), detail
    # Probe 8080 only when nvidia-smi already named a server.exe-class process.
    # A status poll must not stall on that port, and an idle GPU with no such
    # process must keep the existing Ollama idle path.
    maybe_powerinfer = any(
        Path(p).stem.lower() == Path(POWERINFER_SERVER_EXE).stem.lower()
        or "powerinfer" in str(p).lower()
        for p in procs)
    backend_up = powerinfer_backend_listening() if maybe_powerinfer else False
    if backend_up:
        detail["powerinfer_backend"] = "listening"
    powerinfer_procs = [p for p in procs if _is_powerinfer_compute(p, backend_up=backend_up)]
    if powerinfer_procs:
        detail["powerinfer_compute"] = powerinfer_procs
    foreign = [p for p in procs
               if "ollama" not in p.lower()
               and "insufficient permissions" not in p.lower()
               and not any(b in Path(p).stem.lower() for b in _BROWSER_NAMES)
               and not _is_background_gpu_compute(p)
               and not _is_powerinfer_compute(p, backend_up=backend_up)]
    background = [p for p in procs if _is_background_gpu_compute(p)]
    if background:
        detail["background_gpu_compute"] = background
    if foreign:
        return True, f"another compute process is on the GPU: {', '.join(foreign)}", detail

    # A long agent conversation may already have its own 14B Ollama model
    # resident.  That is not an external GPU job and must not make the next
    # hop fall to CPU before the adaptive router can evict/switch it.  Queue
    # ownership, Comfy's port, and known foreign compute processes above still
    # win.  `/api/ps` is the local proof of *what* is loaded; ownership is
    # only this agent's when note_gpu_owned recorded the tag (or chat_busy
    # plus a selected tag while the load is in flight). A third party on the
    # same GPU_HOST (comfy-pilot, 2026-09-05df) must not inherit that waiver.
    resident = _running_models(GPU_HOST)
    detail["gpu_resident_ollama_models"] = resident
    ours = _owned_gpu_residents(resident)
    detail["gpu_owned_ollama_models"] = ours
    unexplained = [name for name in (resident or [])
                   if name and name not in ours]
    if unexplained:
        detail["gpu_unexplained_ollama_models"] = unexplained
    powerinfer_owns = bool(powerinfer_procs) or detail.get("powerinfer_backend") == "listening"
    if mb > VRAM_BUSY_MB:
        if ours and not unexplained:
            return False, (f"GPU has {mb} MB in use by this agent's resident "
                           f"Ollama model(s): {', '.join(ours)}"), detail
        if unexplained:
            return True, (
                f"{mb} MB of VRAM already in use (threshold {VRAM_BUSY_MB} MB); "
                f"GPU Ollama residents were not loaded by this agent: "
                f"{', '.join(unexplained)}"), detail
        selected = _load_gpu_owned()
        if chat_busy() and selected:
            return False, (f"GPU has {mb} MB in use while this agent is loading "
                           f"its selected GPU model(s): {', '.join(selected)}"), detail
        if powerinfer_owns:
            return True, "PowerInfer is using the GPU", detail
        return True, f"{mb} MB of VRAM already in use (threshold {VRAM_BUSY_MB} MB)", detail

    if powerinfer_owns:
        return True, "PowerInfer is using the GPU", detail

    return False, f"GPU idle ({mb} MB used, no foreign compute process)", detail


# ── model discovery ───────────────────────────────────────────────────────────

def _tags(host: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"http://{host}/api/tags", timeout=4) as r:
            return [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:
        return []


def _running_models(host: str) -> list[str] | None:
    """Models actually resident on one Ollama server.

    ``/api/tags`` lists everything installed and cannot tell us what owns VRAM.
    ``/api/ps`` is the authoritative resident-model list. ``None`` means the
    endpoint could not be read; an empty list means the server is up but has
    nothing loaded.
    """
    try:
        with urllib.request.urlopen(f"http://{host}/api/ps", timeout=4) as r:
            data = json.loads(r.read().decode())
        return [str(m.get("name") or m.get("model") or "")
                for m in data.get("models", [])
                if m.get("name") or m.get("model")]
    except Exception:
        return None


def up(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _pick(have: list[str], prefer: list[str]) -> str | None:
    """First installed model from the preference list.

    TWO PASSES, and the order matters. A single pass that fell back to a
    base-name match inside the loop picked `qwen2.5-coder:14b` for the CPU tier
    when `qwen2.5:7b` was also installed — because `qwen2.5-coder:7b` sits
    earlier in the list and matched the 14B on base name alone, ignoring the size
    that is the entire point of the CPU tier.

    So: exact names first, across the whole list. Only if nothing matches exactly
    do we fall back to base-name matching.
    """
    if not have:
        return None
    for want in prefer:                   # pass 1 — exact/compatible tag, size included
        compatible = _installed_variant(have, want)
        if compatible:
            return compatible
    for want in prefer:                   # pass 2 — same family, any tag
        for h in have:
            if h.split(":")[0] == want.split(":")[0]:
                return h
    return have[0]


def unload(host: str, model: str) -> bool:
    """Evict a model from VRAM immediately. Called before yielding to a render."""
    # Callers use the stable configured tag (for example ``:14b``), while a
    # machine may have the compatible ``:14b-v2`` tag resident.  Resolve that
    # alias against `/api/ps` before asking Ollama to unload it.
    resident = _running_models(host) or []
    actual = _installed_variant(resident, model) or model
    try:
        req = urllib.request.Request(
            f"http://{host}/api/generate",
            data=json.dumps({"model": actual, "keep_alive": 0}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        if host == GPU_HOST:
            forget_gpu_owned(actual, model)
        return True
    except Exception:
        return False


def prompt_pack_intent(text: str | None) -> bool:
    """True for large multi-clip creative/storyboard prompt packs.

    Distinct from short still-frame CAP_IMAGE sheets: a 102-clip Backrooms
    pack must not collapse into render_story_image_batch with invented
    placeholders. Detection lives in managed_prompt_pack so tools/tests share
    one definition.
    """
    try:
        import managed_prompt_pack
        return managed_prompt_pack.is_prompt_pack(text)
    except Exception:
        return False


def image_generation_intent(text: str | None) -> bool:
    """True when the operator asked to produce stills / story images.

    Length-based ``needs_escalation`` must not win over this: a 5k-char
    START/LAST brief is image work, not DeepSeek logic. Returning
    ``CAP_IMAGE`` (not ``CAP_TOOL``) also keeps unpinned chats off Mac
    Qwythos — a 16-still Comfy job is not a farm tool turn.
    """
    return bool(_IMAGE_GEN_SIGNAL.search(str(text or "")))


def classify_capability(text: str | None, *, model: str | None = None) -> str:
    """Map a turn to tool / logic / code / image. Empty string means no override.

    An explicit pin of one of the three capability models wins. A coding-model
    pin wins. Otherwise the prompt is classified. No prompt -> no override, so
    existing CPU/GPU auto behaviour (and its tests) stay intact.
    """
    if model:
        if _is_configured_variant(model, QWYTHOS_MODEL):
            return CAP_TOOL
        if _is_configured_variant(model, DEEPSEEK_MODEL):
            return CAP_LOGIC
        if (_is_configured_variant(model, JOSIEFIED_CODER_MODEL)
                or is_coding_model(model)):
            return CAP_CODE
    text = str(text or "").strip()
    if not text:
        return ""
    if _CODE_SIGNAL.search(text):
        return CAP_CODE
    if prompt_pack_intent(text):
        return CAP_CREATIVE
    if image_generation_intent(text):
        return CAP_IMAGE
    try:
        import difficulty
        if difficulty.needs_escalation(text):
            return CAP_LOGIC
    except Exception:
        pass
    return CAP_TOOL


def thermal_blocks_gpu() -> str | None:
    """Refuse GPU capability models when thermal_guard says the card is hot.

    Unknown telemetry fails closed, matching tools._thermal_blocks_comfy_process
    and gpu_busy(). START_MAX_C is the start ceiling (70 C).
    """
    work = str(ROOT / "work")
    if work not in sys.path:
        sys.path.insert(0, work)
    import thermal_guard
    try:
        sample = thermal_guard.sample_gpu()
    except thermal_guard.ThermalTelemetryError as exc:
        return (f"thermal telemetry unavailable ({exc}); unknown GPU heat is "
                "never permission to swap a 14B model")
    if sample.temperature_c >= thermal_guard.EMERGENCY_C:
        return (f"GPU {sample.temperature_c} C reached thermal_guard emergency "
                f"ceiling {thermal_guard.EMERGENCY_C} C")
    if sample.temperature_c > thermal_guard.START_MAX_C:
        return (f"GPU {sample.temperature_c} C exceeds thermal_guard start "
                f"ceiling {thermal_guard.START_MAX_C} C")
    return None


def prepare_gpu_model(target: str, *, timeout_seconds: float = 15.0,
                      poll_seconds: float = 0.25) -> dict:
    """Flush every resident GPU Ollama model that is not ``target``.

    Sends the same ``keep_alive: 0`` generate used by ``unload`` /
    ``context_compactor`` / ``evict_gpu_residents``, then waits on ``/api/ps``
    until those names disappear. The RTX 5080 holds one 14B; overlapping two
    during a swap exceeds MODEL_VRAM_BUDGET.md immediately.
    """
    if not target:
        return {"attempted": [], "keep_alive_sent": [], "remaining": [],
                "verified": False, "reason": "no target model"}
    if not up(GPU_HOST):
        return {"attempted": [], "keep_alive_sent": [], "remaining": [],
                "verified": False, "reason": "GPU Ollama server is offline"}
    before = _running_models(GPU_HOST)
    if before is None:
        return {"attempted": [], "keep_alive_sent": [], "remaining": None,
                "verified": False,
                "reason": "could not read GPU Ollama /api/ps before swap"}
    to_flush = [name for name in before
                if not _is_configured_variant(name, target)]
    if not to_flush:
        note_gpu_owned(target)
        return {"attempted": [], "keep_alive_sent": [], "remaining": [],
                "verified": True,
                "reason": "target already resident or GPU empty"}
    sent = [name for name in to_flush if unload(GPU_HOST, name)]
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        current = _running_models(GPU_HOST)
        if current is None:
            return {"attempted": to_flush, "keep_alive_sent": sent,
                    "remaining": None, "verified": False,
                    "reason": "could not read GPU Ollama /api/ps after keep_alive:0"}
        remaining = [name for name in current if name in to_flush]
        if not remaining:
            note_gpu_owned(target)
            return {"attempted": to_flush, "keep_alive_sent": sent,
                    "remaining": [], "verified": True,
                    "reason": "flushed via keep_alive:0 and verified via /api/ps"}
        if time.monotonic() >= deadline:
            return {"attempted": to_flush, "keep_alive_sent": sent,
                    "remaining": remaining, "verified": False,
                    "reason": "keep_alive:0 swap timed out"}
        time.sleep(max(0.05, float(poll_seconds)))


def _farm_reachable() -> bool:
    try:
        import farm_offload
        return bool(farm_offload.farm_reachable())
    except Exception:
        return False


def evict_gpu_residents(*, timeout_seconds: float = 15.0,
                        poll_seconds: float = 0.25) -> dict:
    """Unload and *verify* every Ollama model resident on the GPU service.

    ``/api/tags`` only tells us what could load; it cannot establish that a
    model has released VRAM.  This lock uses `/api/ps` before and after the
    unload requests.  A failed or unreadable verification is intentionally a
    failure, not an assumption that the GPU is clear.
    """
    if not up(GPU_HOST):
        return {"attempted": [], "remaining": [], "verified": True,
                "reason": "GPU Ollama server is offline; no local Ollama model can remain resident"}
    before = _running_models(GPU_HOST)
    if before is None:
        return {"attempted": [], "remaining": None, "verified": False,
                "reason": "could not read GPU Ollama /api/ps before eviction"}
    if not before:
        return {"attempted": [], "remaining": [], "verified": True,
                "reason": "GPU Ollama has no resident models"}
    requested = {name: unload(GPU_HOST, name) for name in before}
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    current: list[str] | None = before
    while True:
        current = _running_models(GPU_HOST)
        if current is None:
            return {"attempted": before, "requested": requested, "remaining": None,
                    "verified": False, "reason": "could not read GPU Ollama /api/ps after eviction"}
        # All initially resident names must disappear. Do not require a blank
        # list: a different short-lived local request may have started after the
        # lock was claimed, and it is not evidence that the unload failed.
        remaining = [name for name in current if name in before]
        if not remaining:
            forget_gpu_owned(*before)
            return {"attempted": before, "requested": requested, "remaining": [],
                    "verified": True, "reason": "GPU Ollama residency cleared and verified via /api/ps"}
        if time.monotonic() >= deadline:
            return {"attempted": before, "requested": requested, "remaining": remaining,
                    "verified": False, "reason": "GPU Ollama model eviction timed out"}
        time.sleep(max(0.05, float(poll_seconds)))


# Live Qwen3 14B/8B, 2026-09-05bc: 68 GPU schemas + short user message
# produced prompt_eval_count=4098. The old len(json)/3.4 estimate of the
# same wire was 11940 — schema JSON is much denser than English. Using that
# inflate falsely demoted Huihui-14B → 8B (threshold PRIMARY_SAFE_PROMPT_TOKENS).
# Per-schema ≈ (4098 − short-user) / 68 ≈ 60. Heretic/harmony is higher
# (~104/schema) but this constant is for the Huihui pair's 16k gate.
MEASURED_SCHEMA_TOKENS = 60
_MESSAGE_CHARS_PER_TOKEN = 3.4


def estimate_context_tokens(messages: list[dict], tool_schemas: list[dict] | None = None) -> int:
    """Conservative, dependency-free context estimate for pre-flight routing.

    Message text still uses a JSON-wire character heuristic. Tool schemas use
    a measured per-schema constant from live ``prompt_eval_count`` (2026-09-05bc)
    instead of ``len(json.dumps(tools))/3.4``, which 2–3× over-counted Qwen.
    """
    msg_wire = json.dumps(
        {"messages": messages or []}, ensure_ascii=False, separators=(",", ":"))
    msg_tokens = max(0, int(len(msg_wire) / _MESSAGE_CHARS_PER_TOKEN))
    schema_tokens = len(tool_schemas or []) * MEASURED_SCHEMA_TOKENS
    return max(1, msg_tokens + schema_tokens)


def _adaptive_gpu_model(selected: str | None, prompt_tokens: int | None,
                        gpu_have: list[str], detail: dict) -> tuple[str | None, str | None]:
    """Route a long primary-model context to the 8B GPU fallback.

    A pinned primary chat is allowed to use its paired fallback internally.  It
    is not a model substitution for a different chat: the model pair is one
    resilience policy selected by the operator.
    """
    if (_is_configured_variant(selected, PRIMARY_REASONING_MODEL) and prompt_tokens is not None and
            prompt_tokens > PRIMARY_SAFE_PROMPT_TOKENS):
        fallback = _installed_variant(gpu_have, FALLBACK_REASONING_MODEL)
        if fallback:
            detail["adaptive_fallback"] = {
                "from": PRIMARY_REASONING_MODEL,
                "to": FALLBACK_REASONING_MODEL,
                "estimated_prompt_tokens": prompt_tokens,
                "threshold": PRIMARY_SAFE_PROMPT_TOKENS,
                "reason": "predictive context-length protection",
            }
            return fallback, "predictive context-length protection"
        detail["adaptive_fallback_unavailable"] = (
            f"{FALLBACK_REASONING_MODEL} is not installed on the GPU tier")
    return selected, None


def _paired_cpu_fallback(model: str | None, primary_model: str,
                         fallback_model: str, cpu_have: list[str],
                         gpu_have: list[str]) -> tuple[str | None, str, dict]:
    """Resolve a configured pair's safe 8B-style CPU hand-off once.

    The caller owns the user-facing sentence, but both primary-reasoning and
    coding fallbacks need the identical store selection: prefer the dedicated
    CPU model store, then reuse a GPU-store copy *only* with ``num_gpu=0``.
    Keeping this choice here avoids the two branches drifting into different
    offload behaviour.
    """
    del model, primary_model  # retained in the interface to describe the pair.
    dedicated = _installed_variant(cpu_have, fallback_model)
    if dedicated:
        return dedicated, "dedicated_cpu", {}
    reuse = _installed_variant(gpu_have, fallback_model)
    if reuse:
        return reuse, "gpu_store_cpu_only", {
            "host": GPU_HOST,
            "model": reuse,
            "num_gpu": 0,
            "num_thread": CPU_OPTIONS["num_thread"],
            "reason": "reuse already-downloaded model; CPU-only request",
        }
    return None, "unavailable", {}


def _powerinfer_owns_gpu(why: str, detail: dict) -> bool:
    """True only when gpu_busy() classified PowerInfer itself as the occupant."""
    del detail  # occupancy is already encoded in the gpu_busy reason string.
    return str(why or "").startswith("PowerInfer is using the GPU")


def _decide_powerinfer(prefer: str, busy: bool, why: str, detail: dict) -> Decision:
    ready, ready_why = powerinfer_ready()
    detail = dict(detail)
    detail["powerinfer"] = {
        "ready": ready,
        "reason": ready_why,
        "proxy": powerinfer_proxy_listening(),
        "backend": powerinfer_backend_listening(),
    }
    owned_by_powerinfer = _powerinfer_owns_gpu(why, detail)
    blocking = busy and not owned_by_powerinfer
    if blocking:
        return Decision(
            "gpu", POWERINFER_PROXY_HOST, None, True,
            f"Selected PowerInfer model {POWERINFER_MODEL_ALIAS} cannot run while "
            f"the GPU is busy: {why}. It will not fall back to Ollama or CPU.",
            detail, "powerinfer")
    if prefer == "cpu":
        return Decision(
            "gpu", POWERINFER_PROXY_HOST, None, busy,
            f"Selected PowerInfer model {POWERINFER_MODEL_ALIAS} needs GPU permission "
            "before it can run. It will not fall back to CPU.",
            detail, "powerinfer")
    if not ready:
        return Decision(
            "gpu", POWERINFER_PROXY_HOST, None, busy, ready_why, detail, "powerinfer")
    return Decision(
        "gpu", POWERINFER_PROXY_HOST, POWERINFER_MODEL_ALIAS, busy,
        "PowerInfer proxy is reachable — selected opt-in PowerInfer backend",
        detail, "powerinfer")


def _finish_gpu_ollama(decision: Decision, *, ensure_gpu_evicted: bool) -> Decision:
    """Record a real GPU Ollama load. Status polls must not claim ownership."""
    if (ensure_gpu_evicted and decision.backend == "ollama"
            and decision.tier == "gpu" and decision.model
            and not decision.gpu_busy):
        note_gpu_owned(decision.model)
    return decision


def decide(prefer: str = "auto", model: str | None = None,
           prompt_tokens: int | None = None, *, ensure_gpu_evicted: bool = True,
           prompt: str | None = None, skip_farm: bool = False) -> Decision:
    """Which tier answers the next turn.

    `prefer` is "auto", "gpu" or "cpu". A manual "gpu" is still refused while a
    render is running — the operator can force CPU, never force a conflict.
    ``prompt`` enables capability-based auto routing (tool/logic/code). With no
    prompt and no pin, behaviour matches the historical CPU/GPU auto path.
    """
    busy, why, detail = gpu_busy()
    busy, why, detail, capability = _maybe_comfy_timeshare(
        prefer, model, prompt, skip_farm, ensure_gpu_evicted, busy, why, detail)
    cpu_have = _tags(CPU_HOST) if up(CPU_HOST) else []
    # When the dedicated CPU 8B fallback is available, a busy GPU must not be
    # probed just to populate an inventory. It is both unnecessary and can
    # accumulate failed loopback requests while ComfyUI owns the card.
    skip_gpu_inventory = busy and bool(_installed_variant(cpu_have, FALLBACK_REASONING_MODEL))
    if skip_gpu_inventory:
        gpu_have = []
        detail["gpu_inventory_skipped"] = "render busy; dedicated CPU 8B is available"
    else:
        gpu_have = _tags(GPU_HOST) if up(GPU_HOST) else []

    # Opt-in PowerInfer and other GPU-only pins never CPU-offload and must not
    # become Huihui 8B. These checks run *before* the eviction-verification
    # early-return: that return is a CPU Decision, which is exactly the silent
    # downgrade these models forbid — including when /api/ps cannot confirm
    # that Ollama VRAM was released. They were never going to use the CPU tier.
    if is_powerinfer_model(model):
        return _decide_powerinfer(prefer, busy, why, detail)

    # The optional 20B Heretic model is not part of the automatic reasoning
    # hierarchy. It needs the GPU and must never partially offload or silently
    # become the Huihui 8B fallback. Return a precise non-runnable Decision so
    # the chat remains pinned and the UI/agent can explain what is needed.
    if is_gpu_only_opt_in_model(model):
        if busy:
            return Decision(
                "gpu", GPU_HOST, None, True,
                f"Selected GPU-only model {model} cannot run while the GPU is busy: {why}. "
                "It will not fall back to CPU.", detail)
        if prefer == "cpu":
            return Decision(
                "gpu", GPU_HOST, None, False,
                f"Selected GPU-only model {model} needs GPU permission before it can load. "
                "Approve its pending GPU request in the sidebar.", detail)
        if not up(GPU_HOST):
            return Decision(
                "gpu", GPU_HOST, None, False,
                f"Selected GPU-only model {model} cannot run because the GPU Ollama server is offline.",
                detail)
        selected = _installed_variant(gpu_have, model)
        if not selected:
            return Decision(
                "gpu", GPU_HOST, None, False,
                f"Selected GPU-only model {model} is not installed. "
                "Run local_agent\\setup_gpt_oss_20b_heretic.py --create, then start a new chat.",
                detail)
        return _finish_gpu_ollama(
            Decision("gpu", GPU_HOST, selected, False,
                     "GPU free — selected opt-in GPU-only model", detail),
            ensure_gpu_evicted=ensure_gpu_evicted)

    if capability:
        detail["capability"] = capability

    # Unpinned lightweight turns go to Mac Qwythos through farm_offload
    # (same Celery/farm_status.json path as summarize/embed). Do not evict
    # host GPU models for this — Qwythos does not use the RTX 5080.
    if (model is None and capability == CAP_TOOL and not skip_farm
            and prefer != "cpu" and _farm_reachable()):
        detail["farm"] = {"reachable": True, "model": QWYTHOS_MODEL}
        return Decision(
            "farm", "farm", QWYTHOS_MODEL, busy,
            "farm reachable — lightweight tool-calling on Mac "
            f"{QWYTHOS_MODEL} via farm_offload",
            detail, "farm")

    # Unpinned tool turn that would have gone to Qwythos, but the farm is
    # down or skip_farm=True. Local GPU auto (Huihui 14B/8B) must not get
    # the drowning 68-tool catalog. Pinned Huihui conversation hops and
    # CAP_CODE/CAP_LOGIC specialists keep the full GPU schema.
    if model is None and capability == CAP_TOOL:
        detail["gpu_tool_fallback"] = True

    # Unpinned (or explicitly pinned) coding / deep-logic turns use the
    # exclusive 14B pair on the host GPU. One resident 14B at a time:
    # keep_alive:0 flush of the other, then load. queue_owner / gpu_busy /
    # thermal_guard all refuse rather than overlapping a render.
    capability_block_gpu = False
    want_capability_gpu = (
        prefer != "cpu"
        and capability in {CAP_CODE, CAP_LOGIC}
        and (model is None
             or _is_configured_variant(model, DEEPSEEK_MODEL)
             or _is_configured_variant(model, JOSIEFIED_CODER_MODEL)
             or is_coding_model(model))
    )
    if want_capability_gpu:
        target_cfg = (
            JOSIEFIED_CODER_MODEL if capability == CAP_CODE else DEEPSEEK_MODEL
        )
        owned, owned_why = queue_owner()
        refuse_why = None
        if owned:
            refuse_why = owned_why
        elif busy:
            refuse_why = why
        else:
            refuse_why = thermal_blocks_gpu()
        if refuse_why:
            capability_block_gpu = True
            detail["capability_gpu_refused"] = {
                "capability": capability,
                "target": target_cfg,
                "reason": refuse_why,
            }
            if prefer == "gpu":
                return Decision(
                    "gpu", GPU_HOST, None, True,
                    f"capability {capability} refused: {refuse_why}",
                    detail)
            # auto: fall through to the CPU path after eviction below
        elif not up(GPU_HOST):
            detail["capability_gpu_refused"] = {
                "capability": capability, "target": target_cfg,
                "reason": "GPU Ollama server is offline",
            }
        else:
            live_gpu = _tags(GPU_HOST) if not skip_gpu_inventory else gpu_have
            if not live_gpu:
                live_gpu = _tags(GPU_HOST) if up(GPU_HOST) else []
            selected_cap = _installed_variant(live_gpu, target_cfg)
            if not selected_cap:
                detail["capability_gpu_refused"] = {
                    "capability": capability, "target": target_cfg,
                    "reason": f"{target_cfg} is not installed on the GPU tier",
                }
            elif ensure_gpu_evicted:
                swap = prepare_gpu_model(selected_cap)
                detail["host_model_swap"] = swap
                if not swap.get("verified"):
                    return Decision(
                        "gpu", GPU_HOST, None, busy,
                        "capability model swap could not verify keep_alive:0 "
                        "flush: " + str(swap.get("reason")),
                        detail)
                return _finish_gpu_ollama(
                    Decision(
                        "gpu", GPU_HOST, selected_cap, False,
                        f"GPU free — capability {capability} on {selected_cap}",
                        detail),
                    ensure_gpu_evicted=True)
            else:
                return Decision(
                    "gpu", GPU_HOST, selected_cap, False,
                    f"GPU free — capability {capability} on {selected_cap} "
                    "(status; no swap)",
                    detail)

    # A dedicated CPU fallback does not make it safe to skip GPU eviction. The
    # previous shortcut did exactly that: it avoided a GPU inventory while a
    # render was busy, but also left any resident 14B model consuming VRAM.
    # Before a real turn is allowed to choose CPU, release local Ollama weights
    # and confirm their disappearance through /api/ps. Status polling passes
    # ``ensure_gpu_evicted=False`` and remains read-only.
    if busy and ensure_gpu_evicted:
        eviction = evict_gpu_residents()
        detail["gpu_eviction"] = eviction
        if not eviction.get("verified"):
            return Decision(
                "cpu", CPU_HOST, None, True,
                "GPU is reserved and local Ollama model eviction could not be verified; "
                "refusing the CPU hand-off until /api/ps confirms VRAM is released. "
                + str(eviction.get("reason", "unknown eviction failure")),
                detail,
            )

    if model:
        allowed = {m["name"] for m in chat_models(include_gpu=not skip_gpu_inventory)}
        if skip_gpu_inventory:
            # Do not lie that a pinned GPU-only model is "unknown" merely
            # because its server was intentionally not contacted.  It reaches
            # the normal CPU hand-off/refusal branch below instead.
            allowed.add(model)
            if model not in cpu_have and _is_configured_variant(model, PRIMARY_REASONING_MODEL):
                detail["unavailable_primary_chat"] = {
                    "requested": model,
                    "fallback": FALLBACK_REASONING_MODEL,
                    "reason": "primary model is not installed on the CPU tier; GPU inventory intentionally skipped",
                }
            # Retain the configured primary as a valid pinned chat so the
            # normal paired-8B handoff can occur without checking GPU state.
            allowed.add(PRIMARY_REASONING_MODEL)
        if model not in allowed:
            # Existing chats can legitimately be pinned to a compatible 14B-v2
            # primary tag while that optional model is being replaced or is not
            # currently loaded on either service.  Its documented resilience
            # pair is the Huihui 8B model, so continue on that CPU-safe member
            # instead of returning a blank model.  Other unavailable pins still
            # refuse; this is not general silent model substitution.
            if _is_configured_variant(model, PRIMARY_REASONING_MODEL):
                detail["unavailable_primary_chat"] = {
                    "requested": model,
                    "fallback": FALLBACK_REASONING_MODEL,
                    "reason": "primary model is not installed on either active tier",
                }
            elif is_coding_model(model):
                fallback = preferred_coding_model(list(dict.fromkeys(gpu_have + cpu_have)))
                if not fallback:
                    fallback = (
                        _installed_variant(gpu_have, PRIMARY_REASONING_MODEL)
                        or _installed_variant(cpu_have, FALLBACK_REASONING_MODEL)
                        or _pick(gpu_have, GPU_MODELS)
                        or _pick(cpu_have, CPU_MODELS)
                    )
                if fallback:
                    detail["unavailable_coding_model"] = {
                        "requested": model,
                        "fallback": fallback,
                        "reason": "configured coding model is not installed on either active tier",
                    }
                    model = fallback
                    on_cpu, on_gpu = model in cpu_have, model in gpu_have
                else:
                    return Decision("cpu", CPU_HOST, None, busy,
                                    f"Selected chat model is unavailable: {model}", detail)
            else:
                return Decision("cpu", CPU_HOST, None, busy,
                                f"Selected chat model is unavailable: {model}", detail)
        on_cpu, on_gpu = model in cpu_have, model in gpu_have
    else:
        on_cpu = on_gpu = False

    want_gpu = (prefer == "gpu") or (prefer == "auto" and not busy)
    if prefer == "gpu" and busy:
        why = f"GPU requested but unavailable: {why}"
        want_gpu = False
    if capability_block_gpu:
        want_gpu = False
        refused = detail.get("capability_gpu_refused")
        if isinstance(refused, dict) and refused.get("reason"):
            why = refused["reason"]

    if want_gpu and up(GPU_HOST):
        selected = (model if on_gpu else None) if model else _pick(gpu_have, GPU_MODELS)
        adaptive_reason = None
        # Predictive 14B→8B is a real token-estimate gate (not a leaked
        # flag). 8B then degenerates on long still-frame scripts
        # (2026-09-05 live hops). Image intent keeps the primary; 14B
        # GPU_VRAM_NUM_CTX already covers the 16k–34k window.
        if capability in {CAP_IMAGE, CAP_CREATIVE}:
            if (prompt_tokens is not None
                    and prompt_tokens > PRIMARY_SAFE_PROMPT_TOKENS
                    and _is_configured_variant(selected, PRIMARY_REASONING_MODEL)):
                detail["adaptive_fallback_skipped"] = {
                    "reason": (
                        "image-generation intent keeps primary"
                        if capability == CAP_IMAGE
                        else "creative prompt-pack keeps primary"
                    ),
                    "estimated_prompt_tokens": prompt_tokens,
                    "threshold": PRIMARY_SAFE_PROMPT_TOKENS,
                }
        else:
            selected, adaptive_reason = _adaptive_gpu_model(
                selected, prompt_tokens, gpu_have, detail)
        if (media_pressure() and _is_configured_variant(selected, PRIMARY_REASONING_MODEL)):
            fallback = _installed_variant(gpu_have, FALLBACK_REASONING_MODEL)
            if fallback:
                selected, adaptive_reason = fallback, "media VRAM pressure"
        if selected:
            return _finish_gpu_ollama(
                Decision("gpu", GPU_HOST, selected, busy,
                         (adaptive_reason or why) if prefer == "gpu" else
                         (f"GPU free — {adaptive_reason or why}"), detail),
                ensure_gpu_evicted=ensure_gpu_evicted)
        if model and not on_gpu:
            why = f"{model} is not installed on the GPU tier; {why}"
        else:
            why = f"GPU server has no models; {why}"

    selected = (model if on_cpu else None) if model else _pick(cpu_have, CPU_MODELS)
    cpu_host = CPU_HOST

    # This workstation's GPU Ollama service owns the already-downloaded Huihui
    # tags while the dedicated CPU service has a separate local model store.
    # Calling that same service with CPU_OPTIONS (num_gpu=0, four threads) is
    # still CPU-only inference; it avoids both a duplicate pull and GPU layer
    # offload when a render has reserved the card.
    cpu_store_fallback, cpu_fallback_source, cpu_fallback_detail = _paired_cpu_fallback(
        model, PRIMARY_REASONING_MODEL, FALLBACK_REASONING_MODEL, cpu_have, gpu_have
    )
    gpu_store_cpu_fallback = (
        cpu_store_fallback if cpu_fallback_source == "gpu_store_cpu_only" else None
    )
    cpu_transition = "GPU reserved" if busy else "CPU requested"
    if cpu_store_fallback and cpu_fallback_source == "dedicated_cpu":
        selected = cpu_store_fallback
        why = (f"{cpu_transition}; using Huihui 8B on the dedicated CPU server "
               f"(num_gpu=0, {CPU_OPTIONS['num_thread']} threads). {why}")
    elif gpu_store_cpu_fallback:
        selected = gpu_store_cpu_fallback
        cpu_host = str(cpu_fallback_detail["host"])
        detail["cpu_huihui_fallback"] = dict(cpu_fallback_detail)
        why = (f"{cpu_transition}; using Huihui 8B on CPU (num_gpu=0, "
               f"{CPU_OPTIONS['num_thread']} threads). {why}")

    # A primary-Huihui chat is a deliberate pair: when a render reserves the
    # GPU, continue it on the paired 8B model on the CPU rather than dropping
    # to Dolphin or trying to retain/partially offload the 14B weights.
    paired_cpu_fallback = None
    if model and not on_cpu and _is_configured_variant(model, PRIMARY_REASONING_MODEL):
        paired_cpu_fallback = cpu_store_fallback
        if paired_cpu_fallback and cpu_fallback_source == "gpu_store_cpu_only":
            cpu_host = str(cpu_fallback_detail["host"])
        if paired_cpu_fallback:
            selected = paired_cpu_fallback
            why = (f"{cpu_transition}; continuing primary-Huihui chat on paired CPU "
                   f"fallback {paired_cpu_fallback}. {why}")
    if model and not on_cpu and is_coding_model(model) and not paired_cpu_fallback:
        coding_cpu = (
            _installed_variant(cpu_have, CODING_FALLBACK_MODEL)
            or _installed_variant(cpu_have, CODING_MODEL)
            or cpu_store_fallback
        )
        if not coding_cpu:
            coding_cpu = gpu_store_cpu_fallback
            if coding_cpu:
                cpu_host = str(cpu_fallback_detail["host"])
        if coding_cpu:
            paired_cpu_fallback = coding_cpu
            selected = coding_cpu
            why = (f"{cpu_transition}; coding mode on CPU ({coding_cpu}). "
                   "A 14B coder on CPU is slow — free the GPU for heavy coding. "
                   f"{why}")
            detail["coding_cpu_fallback"] = {
                "requested": model,
                "using": coding_cpu,
            }
    if model and not on_cpu:
        # `paired_cpu_fallback` is only set by the primary-14B-pairing and
        # coding-model branches above -- that is the actual authorization
        # gate for silently substituting the 8B fallback in for a *different*
        # pinned model (e.g. a GPU-only pin must still be refused here, not
        # silently become Huihui 8B; see
        # `test_gpu_only_pin_refuses_instead_of_substituting_when_busy`).
        #
        # But `cpu_store_fallback`/`gpu_store_cpu_fallback` a few lines up
        # resolve unconditionally against `FALLBACK_REASONING_MODEL`,
        # independent of what `model` actually is (`_paired_cpu_fallback`
        # ignores its own `model` argument). So when the *pinned* model IS
        # itself the fallback model, that resolution already found and
        # assigned the exact model that was asked for -- not a substitution
        # at all, just the GPU-store copy run with CPU flags. Refusing that
        # here used to discard the already-correct `selected` and emit a
        # self-contradictory message ("cannot run ... GPU tier is
        # unavailable" immediately followed by "using Huihui 8B on CPU ...
        # GPU idle") for exactly that case. Live bug, 2026-09-06.
        if not paired_cpu_fallback and not _is_configured_variant(model, FALLBACK_REASONING_MODEL):
            selected = None
            why = (f"Selected model {model} cannot run now: it is not installed on "
                   f"the CPU tier and the GPU tier is unavailable or not selected. {why}")
    return Decision("cpu", cpu_host, selected, busy, why, detail)


def fallback_after_primary_failure(previous: Decision, error: BaseException) -> Decision | None:
    """Unload a failed 14B request and retry exactly once on paired 8B GPU.

    This deliberately returns ``None`` instead of falling through to CPU.  A
    partial CPU offload is slow and unpredictable; while a render is active the
    existing normal routing path owns the decision and the agent must not add a
    second GPU workload.
    """
    if previous.tier != "gpu" or not _is_configured_variant(previous.model, PRIMARY_REASONING_MODEL):
        return None
    busy, why, detail = gpu_busy()
    if busy or not up(GPU_HOST):
        detail["reactive_fallback_unavailable"] = (
            "GPU became busy" if busy else "GPU Ollama server is unavailable")
        return None
    gpu_have = _tags(GPU_HOST)
    fallback_model = _installed_variant(gpu_have, FALLBACK_REASONING_MODEL)
    if not fallback_model:
        detail["reactive_fallback_unavailable"] = (
            f"{FALLBACK_REASONING_MODEL} is not installed on the GPU tier")
        return None
    # An OOM may leave the primary resident despite the failed request.
    unload(GPU_HOST, PRIMARY_REASONING_MODEL)
    detail["adaptive_fallback"] = {
        "from": PRIMARY_REASONING_MODEL,
        "to": FALLBACK_REASONING_MODEL,
        "reason": "reactive primary-model failure",
        "error": str(error)[:500],
    }
    return Decision("gpu", GPU_HOST, fallback_model, False,
                    "reactive 14B failure — retrying once on 8B GPU fallback", detail)


def _status_timeshare_idle(busy: bool, detail: dict) -> bool:
    """Owner files + last-known queue. No urllib/MCP. Best-effort if cache empty."""
    if not (busy and (detail or {}).get("comfy_port_8188") == "listening"):
        return False
    if not _timeshare_enabled():
        return False
    owners_idle, _ = _owners_idle_for_timeshare()
    if not owners_idle:
        return False
    cached = _TIMESHARE_QUEUE_CACHE.get("idle")
    if cached is False:
        return False
    return True


def status() -> dict:
    busy, why, detail = gpu_busy()
    d = decide(ensure_gpu_evicted=False)
    # Status is observational. During an *active* render it must not query the
    # GPU model catalogue; the next agent turn still makes its own authoritative
    # routing decision and will use the CPU fallback.
    # Idle-8188 timeshare is different: gpu_busy() still short-circuits on the
    # listener, but owners+queue are idle and a granted turn may claim. Skipping
    # the catalogue then leaves _LAST_VERIFIED_GPU_MODELS empty after restart
    # and wrongly disables GPU-only picker entries ("GPU currently unavailable").
    timeshare_idle = _status_timeshare_idle(busy, detail)
    include_gpu = (not busy) or timeshare_idle
    cpu_up = up(CPU_HOST)
    gpu_up = up(GPU_HOST)
    cpu_models = _tags(CPU_HOST) if cpu_up else []
    gpu_models = _tags(GPU_HOST) if include_gpu and gpu_up else []
    reason = STATUS_TIMESHARE_IDLE_REASON if timeshare_idle else why
    return {
        "gpu_busy": busy,
        "timeshare_idle": timeshare_idle,
        "reason": reason,
        "routing_reason": d.reason,
        "detail": detail,
        "tier": d.tier,
        "model": d.model,
        "host": d.host,
        "cpu_server_up": cpu_up,
        "gpu_server_up": gpu_up,
        "cpu_models": cpu_models,
        "gpu_models": gpu_models,
        "chat_models": chat_models(include_gpu=include_gpu),
        "coding_model": CODING_MODEL,
    }


if __name__ == "__main__":
    s = status()
    print(f"GPU busy      : {s['gpu_busy']}  — {s['reason']}")
    print(f"routing to    : {s['tier'].upper()}  {s['model']}  @ {s['host']}")
    print(f"routing reason: {s['routing_reason']}")
    print(f"cpu server    : {'up' if s['cpu_server_up'] else 'down'}  {s['cpu_models']}")
    print(f"gpu server    : {'up' if s['gpu_server_up'] else 'down'}  {s['gpu_models']}")
    print(json.dumps(s["detail"], indent=2))
    sys.exit(0)
