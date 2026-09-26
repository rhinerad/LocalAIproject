#!/usr/bin/env python3
"""Phase 3 live Generalized Video Director: Wan 2.1 + Qwen2.5-VL with VRAM flip-flop.

16 GB cannot hold Wan and Caption V4 at once. Every metric eval:

1. ``vram_controller.prepare_for_comfyui(reason="Wan 2.1 generation")``
2. ComfyUI Wan first-last-frame with clamped cfg / denoise / steps
3. ``vram_controller.release_after_comfyui(reason="Wan 2.1 complete")``
   (always, including TimeoutError / failure)
4. Frame extract + Qwen2.5-VL Caption V4 on :11436
5. ``vram_controller.release_after_vlm`` so llama.cpp leaves the card

Timeouts return MIPRO 0.0 with JSON feedback. This module does not start
ComfyUI and does not compile unless ``--compile`` is passed.
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import logging
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("dspy_orchestrator")


def _atexit_release_vlm() -> None:
    try:
        vram_controller.release_after_vlm(reason="orchestrator exit")
    except Exception:
        pass


atexit.register(_atexit_release_vlm)

# --- P1-D lease / admission helpers (Comfy client may be stubbed offline) ---
class VramAdmissionError(RuntimeError):
    """VRAM prepare/admission failed; must not continue to submit."""


def prepare_comfy_or_raise(prepare_fn, *, reason: str) -> None:
    """Admission failure is blocking — never swallow and continue."""
    try:
        prepare_fn(reason=reason)
    except VramAdmissionError:
        raise
    except Exception as exc:
        raise VramAdmissionError(f"VRAM admission failed ({reason}): {exc}") from exc


def cancel_reconcile_before_lease_release(
    client,
    *,
    prompt_id: str | None = None,
    attempt_id: str | None = None,
    reason: str = "attempt finally",
) -> dict:
    """On owned attempt finally: cancel/reconcile prompt BEFORE releasing GPU lease."""
    try:
        from production_store import release_gpu_lease
        return release_gpu_lease(
            client, prompt_id=prompt_id, attempt_id=attempt_id, reason=reason
        )
    except Exception:
        trace = {"attempt_id": attempt_id, "prompt_id": prompt_id, "reason": reason}
        if prompt_id and hasattr(client, "cancel_prompt"):
            client.cancel_prompt(prompt_id)
            trace["cancelled"] = True
        if hasattr(client, "reconcile"):
            client.reconcile(prompt_id=prompt_id)
            trace["reconciled"] = True
        if hasattr(client, "release_after_comfyui"):
            client.release_after_comfyui(reason=reason)
            trace["lease_released"] = True
        return trace



HERE = Path(__file__).resolve().parent
import dynamic_voice
extract_raw_dialogue = dynamic_voice.extract_raw_dialogue
extract_dialogue_array = dynamic_voice.extract_dialogue_array
normalize_dialogue_array = dynamic_voice.normalize_dialogue_array
dialogue_to_speech_text = dynamic_voice.dialogue_to_speech_text
is_c001 = dynamic_voice.is_c001
lock_c001_master_voice = dynamic_voice.lock_c001_master_voice
apply_dynamic_voice_routing = dynamic_voice.apply_dynamic_voice_routing
VoiceAudioGateError = dynamic_voice.VoiceAudioGateError
classify_voice_submit_error = dynamic_voice.classify_voice_submit_error
assert_audio_gate = dynamic_voice.assert_audio_gate
from minimax_ref2vid import (
    wants_minimax_ref2vid,
    apply_minimax_ref2vid,
    attach_minimax_native_audio_mux,
)
strip_f5_voice_nodes = dynamic_voice.strip_f5_voice_nodes

# Pure H3 timing (editorial_frames vs generation_frames).
try:
    import importlib.util as _ilu
    _gvd_core_path = Path(__file__).resolve().parent.parent / "gvd_core.py"
    _spec = _ilu.spec_from_file_location("_gvd_core_timing", _gvd_core_path)
    _gvd_mod = _ilu.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_gvd_mod)
    h3_generation_frames = _gvd_mod.h3_generation_frames
    editorial_vs_generation_frames = _gvd_mod.editorial_vs_generation_frames
except Exception:
    def h3_generation_frames(required_frames: int) -> int:
        if isinstance(required_frames, bool) or not isinstance(required_frames, int) or required_frames < 1:
            raise ValueError("positive integer frame count required")
        n = max(124, required_frames)
        n += (5 - n % 17) % 17
        if n > 362:
            raise ValueError("Split into multiple render segments")
        return n

    def editorial_vs_generation_frames(editorial_frames: int) -> tuple[int, int]:
        editorial = int(editorial_frames)
        if editorial < 1:
            raise ValueError("editorial_frames must be >= 1")
        return editorial, h3_generation_frames(editorial)

ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from local_agent import vram_controller
except ImportError:
    import vram_controller

import generalized_video_director as gvd
from media_accuracy_gate import (
    VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT,
    parse_video_director_scores,
    video_director_passes_curriculum,
)

# Coherent Wan defaults if the student truncates before emitting numbers.
# Old 8.0 / 0.35 / 40 sat on the clamp edges and rendered abstract noise.
# denoise stays for the hparams dict shape; the current signature omits it.
HPARAM_FALLBACKS = {
    "cfg_scale": 5.5,
    "denoise": 0.90,
    "step_count": 28.0,
}
STUDENT_MAX_TOKENS = 8192
_CAMERA_KEYWORDS = (
    "handheld",
    "camcorder",
    "first-person",
    "first person",
    "fpv",
    "pov",
    "point-of-view",
)
_MOTION_KEYWORDS = (
    "walk",
    "walking",
    "momentum",
    "push in",
    "push-in",
    "tracking forward",
    "track forward",
    "dolly",
    "glide",
    "advance",
    "move forward",
    # Relaxed 2026-09-26e (operator decision, CHANGELOG 2026-09-26d): history
    # row 265 (B01 644b, "gradually moves ... panning") rendered a clip the
    # review calls good and the judge scores 0.80 offline, but the table above
    # rejected it. Plain motion verbs and camera pans/tilts/turns now count.
    "move",
    "moves",
    "moving",
    "movement",
    "pan",
    "pans",
    "panning",
    "tracking",
    "tracks",
    "drift",
    "drifts",
    "drifting",
    "creep",
    "creeps",
    "creeping",
    "step forward",
    "steps forward",
    "stepping forward",
    "approach",
    "approaches",
    "approaching",
    "travel",
    "travels",
    "traveling",
    "travelling",
    "wander",
    "wanders",
    "wandering",
    "tilt",
    "tilts",
    "tilting",
    "turn",
    "turns",
    "turning",
    "sway",
    "sways",
    "swaying",
)
# Word-bounded, not substring: "remove" / "improvement" must not read as
# motion, and a hyphen or spaces may join a two-word entry ("push-in").
_MOTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k).replace(r"\ ", r"[\s-]+") for k in _MOTION_KEYWORDS) + r")\b"
)
# The floor: a negated motion phrase ("the camera does not move", "no
# panning", "without any camera movement") is blanked before matching, so
# echoing motion vocabulary while describing a static shot still fails.
_MOTION_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|zero|doesn'?t|does not|isn'?t|is not|don'?t|do not)"
    r"\s+(?:\w+\s+){0,2}(?:camera\s+)?"
    r"(?:mov\w*|pan\w*|walk\w*|track\w*|dolly\w*|drift\w*|tilt\w*|turn\w*|motion)\b"
)


def has_motion_keyword(text: str) -> bool:
    """Backrooms motion check: a word-bounded motion term outside a negation."""
    lowered = _MOTION_NEGATION_RE.sub(" ", str(text or "").lower())
    return bool(_MOTION_RE.search(lowered))
_DRONE_OR_CINEMATIC_CATEGORIES = frozenset(
    {
        "drone",
        "drone_high_kinematics",
        "cinematic",
        "cinematic_drone",
    }
)
# MiniMax I2V defaults: editorial target 8s @ 24fps.
# generation_frames are computed via h3_generation_frames(editorial_frames).
MINIMAX_FPS = 24
DEFAULT_EDITORIAL_FRAMES = 192  # 8s @ 24fps editorial span
MINIMAX_NUM_FRAMES = DEFAULT_EDITORIAL_FRAMES  # back-compat alias (editorial, not forced gen)
MINIMAX_GRAPH_TEMPLATE = Path(__file__).resolve().parent / "graphs" / "flux_minimax_i2v_api.json"
# MiniMax H3 sampler steps: fixed at 20 by CLAUDE.md ("Model and settings") and
# backend_profiles.H3_DISTILLED. Independent of the FLUX-still step_count.
try:
    from backend_profiles import H3_DISTILLED as _H3_PROFILE
    MINIMAX_H3_STEPS = int(_H3_PROFILE["steps"])
except Exception:
    MINIMAX_H3_STEPS = 20

EXACT_VLM_MODEL = "qwen25-vl-nsfw-caption:v4-q4_k_m"
EXACT_VLM_RUNTIME = "llama.cpp"
DEFAULT_COMFY_URL = os.environ.get("EQUAL_SHARES_COMFYUI_URL", "http://127.0.0.1:8188")
WAN_TIMEOUT_S = float(os.environ.get("GVD_WAN_TIMEOUT_S", "3600"))
STILL_TIMEOUT_S = float(os.environ.get("GVD_STILL_TIMEOUT_S", "1800"))
VLM_TIMEOUT_S = float(os.environ.get("GVD_VLM_TIMEOUT_S", "1800"))
DEFAULT_SAVE = ROOT / "models" / "dspy_compiled" / "generalized_video_director_mipro.json"

LAST_METRIC_RESULT: dict[str, Any] = {}
LAST_RENDER_TELEMETRY: dict[str, Any] = {}

# Comfy node-id sets for phase-tagged VRAM telemetry (flux_minimax_i2v_api.json).
FLUX_PHASE_NODES = frozenset({"3", "5", "6", "7", "8", "10", "11", "12", "14", "41"})
MINIMAX_PHASE_NODES = frozenset(
    {"20", "25", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40"}
)

METRIC_HISTORY: list[dict[str, Any]] = []


def trim_graph_to_stills_only(graph: dict, *, filename_prefix: str) -> dict:
    """Keep FLUX T2I -> VAEDecode IMAGE; drop MiniMax I2V / video decode / SaveVideo.

    Live stack is FLUX.1 + MiniMax (Wan retired). ``--stills-only`` previews the
    FLUX start frame via SaveImage before I2V.
    """
    import copy

    if not isinstance(graph, dict):
        raise TypeError("graph must be a dict")
    g = copy.deepcopy(graph)
    g.pop("_meta", None)

    drop: set[str] = {str(x) for x in MINIMAX_PHASE_NODES}
    for nid, node in list(g.items()):
        if not isinstance(node, dict):
            continue
        ct = str(node.get("class_type") or "")
        low = ct.lower()
        if (
            ct in {"SaveVideo", "CreateVideo", "MiniMaxH3ImageToVideo", "MiniMaxImageToVideo"}
            or "minimax" in low
        ):
            drop.add(str(nid))
    for nid in list(drop):
        g.pop(str(nid), None)

    decode_id = None
    if "8" in g and str((g.get("8") or {}).get("class_type") or "") == "VAEDecode":
        decode_id = "8"
    else:
        for nid, node in g.items():
            if isinstance(node, dict) and str(node.get("class_type") or "") == "VAEDecode":
                if str(nid) in FLUX_PHASE_NODES or decode_id is None:
                    decode_id = str(nid)
    if not decode_id:
        raise RuntimeError("stills-only trim failed: no VAEDecode left in FLUX subgraph")
    if str((g.get("1006") or {}).get("class_type") or "") == "ImageSharpen":
        decode_id = "1006"  # refine checkpoint's sharpened output is what I2V would get

    for nid, node in list(g.items()):
        if isinstance(node, dict) and str(node.get("class_type") or "") == "SaveImage":
            g.pop(nid, None)

    save_id = "90"
    while save_id in g:
        save_id = str(int(save_id) + 1)
    try:
        import comfy_api
        prefix = comfy_api.save_prefix(filename_prefix)
    except Exception:
        prefix = filename_prefix
    g[save_id] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": [decode_id, 0],
            "filename_prefix": prefix,
        },
    }
    return g



def _vram_snapshot(label: str) -> dict[str, Any]:
    """nvidia-smi sample for flip-flop evidence. Never throws into the metric."""
    import subprocess
    import time as _time

    row: dict[str, Any] = {"label": label, "ts": _time.time()}
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        used, free, total = [int(float(p.strip())) for p in raw.strip().splitlines()[0].split(",")]
        row.update({"used_mib": used, "free_mib": free, "total_mib": total})
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    try:
        row["owner"] = vram_controller.get_vram_owner()
    except Exception:
        pass
    return row



def _nvidia_used_mib() -> int | None:
    """Fast single-field nvidia-smi used-MiB sample."""
    import subprocess

    try:
        raw = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        return int(float(raw.strip().splitlines()[0].split(",")[0]))
    except Exception:
        return None


class _PhaseVRAMMonitor:
    """Background nvidia-smi sampler with FLUX / MiniMax phase tags.

    Phase flips when Comfy reports an executing node id in the corresponding set.
    """

    def __init__(self) -> None:
        import threading

        self._phase = "pre_submit"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.samples: list[dict[str, Any]] = []
        self.flux_peak_mib = 0
        self.minimax_peak_mib = 0
        self.post_flux_idle_mib: int | None = None
        self.minimax_started_ts: float | None = None
        self.minimax_finished_ts: float | None = None
        self._thread = threading.Thread(target=self._loop, name="phase-vram", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def set_phase(self, phase: str) -> None:
        import time as _time

        with self._lock:
            if phase == self._phase:
                return
            prev = self._phase
            self._phase = phase
            used = _nvidia_used_mib()
            self.samples.append(
                {
                    "label": f"phase_transition_{prev}_to_{phase}",
                    "phase": phase,
                    "ts": _time.time(),
                    "used_mib": used,
                }
            )
            if phase == "minimax" and self.minimax_started_ts is None:
                self.minimax_started_ts = _time.time()
                # First sample entering MiniMax ≈ post-FLUX handoff VRAM.
                if used is not None:
                    self.post_flux_idle_mib = int(used)
            if phase == "post_minimax" and self.minimax_started_ts is not None:
                self.minimax_finished_ts = _time.time()

    def note_executing_node(self, node_id: Any) -> None:
        if node_id is None:
            return
        nid = str(node_id)
        if nid in FLUX_PHASE_NODES:
            self.set_phase("flux")
        elif nid in MINIMAX_PHASE_NODES:
            self.set_phase("minimax")

    def mark_post_flux_idle(self) -> None:
        """Explicit mid-pipeline /free idle sample (two-phase render)."""
        import time as _time

        used = _nvidia_used_mib()
        with self._lock:
            self.post_flux_idle_mib = used
            self.samples.append(
                {
                    "label": "post_flux_idle_after_free",
                    "phase": "post_flux_idle",
                    "ts": _time.time(),
                    "used_mib": used,
                }
            )
        self.set_phase("post_flux_idle")

    def _loop(self) -> None:
        import time as _time

        while not self._stop.wait(0.5):
            used = _nvidia_used_mib()
            with self._lock:
                phase = self._phase
                self.samples.append(
                    {"label": "sample", "phase": phase, "ts": _time.time(), "used_mib": used}
                )
                if used is None:
                    continue
                if phase == "flux":
                    self.flux_peak_mib = max(self.flux_peak_mib, int(used))
                elif phase == "minimax":
                    self.minimax_peak_mib = max(self.minimax_peak_mib, int(used))

    def summary(self) -> dict[str, Any]:
        import time as _time

        with self._lock:
            started = self.minimax_started_ts
            finished = self.minimax_finished_ts or _time.time()
            duration = None
            if started is not None:
                duration = float(finished - started)
            return {
                "flux_vram_peak_mib": self.flux_peak_mib or None,
                "post_flux_idle_vram_mib": self.post_flux_idle_mib,
                "minimax_vram_peak_mib": self.minimax_peak_mib or None,
                "minimax_generation_seconds": duration,
                "samples_n": len(self.samples),
                "final_phase": self._phase,
            }


def _track_prompt_with_phase(
    orch: Any,
    prompt_id: str,
    monitor: _PhaseVRAMMonitor,
    *,
    timeout_s: float,
) -> dict[str, Any]:
    """Like PipelineOrchestrator.track_prompt_id but tags FLUX vs MiniMax phases."""
    import json
    import time as _time

    prompt_id = str(prompt_id)
    deadline = _time.monotonic() + max(1.0, float(timeout_s))
    try:
        from dispatcher import _connect_comfy_websocket
    except Exception:
        # Fallback: no WS phase tags; still track completion.
        return orch.track_prompt_id(prompt_id, timeout_s=timeout_s)

    session = _connect_comfy_websocket(orch.websocket_url(), timeout=min(10.0, timeout_s))
    try:
        while _time.monotonic() < deadline:
            remaining = deadline - _time.monotonic()
            raw = session.recv_text(timeout=min(5.0, remaining))
            if raw is None:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = str(message.get("type") or "")
            data = message.get("data") if isinstance(message.get("data"), dict) else {}
            msg_prompt = str(data.get("prompt_id") or "")
            if msg_prompt and msg_prompt != prompt_id:
                continue
            if kind == "executing":
                monitor.note_executing_node(data.get("node"))
            if kind == "executed":
                monitor.note_executing_node(data.get("node"))
            node = data.get("node")
            job_done = kind == "execution_success" or (
                kind == "executing" and node is None and msg_prompt == prompt_id
            )
            if job_done:
                return {
                    "state": "complete",
                    "prompt_id": prompt_id,
                    "source": "websocket",
                    "type": kind,
                }
            if kind in {"execution_error", "execution_interrupted"}:
                return {
                    "state": "error",
                    "prompt_id": prompt_id,
                    "source": "websocket",
                    "type": kind,
                    "data": data,
                }
    finally:
        try:
            session.close()
        except Exception:
            pass
    return {"state": "timeout", "prompt_id": prompt_id}


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def is_backrooms_example(example: Any) -> bool:
    category = str(_field(example, "category") or "").strip().lower()
    clip_id = str(_field(example, "id") or _field(example, "clip_id") or "").upper()
    return category == "backrooms" or clip_id.startswith("GVD-B")


def _try_parse_float(value: Any) -> float | None:
    """Coerce LM hparam quirks (range strings / min-max dicts) to a single float."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if number != number else number
    if isinstance(value, dict):
        lo = value.get("min", value.get("low", value.get("lo", value.get("start"))) )
        hi = value.get("max", value.get("high", value.get("hi", value.get("end"))) )
        lo_n = _try_parse_float(lo)
        hi_n = _try_parse_float(hi)
        if lo_n is not None and hi_n is not None:
            number = (lo_n + hi_n) / 2.0
            return None if number != number else number
        for key in ("value", "cfg", "cfg_scale", "denoise", "step_count", "steps"):
            if key in value:
                return _try_parse_float(value.get(key))
        return None
    text = str(value).strip()
    if not text:
        return None
    range_match = re.search(
        r"(-?\d+(?:\.\d+)?)\s*(?:-|to|\.\.)\s*(-?\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if range_match:
        lo_n = float(range_match.group(1))
        hi_n = float(range_match.group(2))
        number = (lo_n + hi_n) / 2.0
        return None if number != number else number
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    return None if number != number else number


_SIGNATURE_OUTPUT_FIELDS: frozenset[str] | None = None


def _director_output_fields() -> frozenset[str] | None:
    """Output fields of the current director signature, or None without dspy."""
    global _SIGNATURE_OUTPUT_FIELDS
    if _SIGNATURE_OUTPUT_FIELDS is None:
        try:
            _SIGNATURE_OUTPUT_FIELDS = frozenset(gvd.director_signature_class().output_fields)
        except Exception:  # dspy missing: treat every hparam as emitted
            return None
    return _SIGNATURE_OUTPUT_FIELDS


def parse_director_hparams(pred: Any) -> tuple[dict[str, float], list[str]]:
    """Parse cfg/denoise/steps; missing or garbage fields get safe fallbacks, then clamp.

    An hparam the current signature does not emit (denoise since 2026-09-16)
    silently takes its clamped fallback when absent; the dict shape is kept.
    """
    parsed: dict[str, float] = {}
    notes: list[str] = []
    ranges = {
        "cfg_scale": gvd.CFG_SCALE_RANGE,
        "denoise": gvd.DENOISE_RANGE,
        "step_count": gvd.STEP_COUNT_RANGE,
    }
    emitted = _director_output_fields()
    for name, fallback in HPARAM_FALLBACKS.items():
        raw = _field(pred, name)
        number = _try_parse_float(raw)
        absent = raw is None or (isinstance(raw, str) and not raw.strip())
        if number is None and absent and emitted is not None and name not in emitted:
            number = fallback
        elif number is None:
            msg = (
                f"hparam {name}={raw!r} missing or unparseable; "
                f"using fallback {fallback}"
            )
            notes.append(msg)
            log.warning(msg)
            warnings.warn(msg, stacklevel=2)
            number = fallback
        lo, hi = ranges[name]
        parsed[name] = max(lo, min(hi, number))
    return parsed, notes


def _example_category(example: Any) -> str:
    return str(_field(example, "category") or "").strip().lower()


def _is_drone_or_cinematic(example: Any) -> bool:
    cat = _example_category(example)
    if cat in _DRONE_OR_CINEMATIC_CATEGORIES:
        return True
    if "drone" in cat or "cinematic" in cat:
        return True
    return False


def mechanical_director_gate(example: Any, pred: Any, video_path: Path | None = None) -> dict:
    """Category-aware mechanical check. Does not load the VLM.

    drone / cinematic: only require non-empty prompts + positive duration
    (skip VHS / liminal / handheld checks).
    backrooms: any camera noun AND any motion verb (no exact-phrase lock).

    Reads only ``example`` and ``pred``; ``video_path`` is accepted for
    compatibility and not used. evaluate_live_candidate therefore runs it
    before the render (2026-09-25j), not after.
    """
    start_prompt = _director_start_prompt(example, pred)
    motion_prompt = _director_motion_prompt(pred)
    # Combined text for keyword scans; prefer motion prompt for camera/motion.
    prompt = motion_prompt or start_prompt
    reasons: list[str] = []
    if not start_prompt:
        reasons.append("start_prompt is empty")
    if not motion_prompt:
        reasons.append("video_prompt is empty")
    for name, text in (("start_prompt", start_prompt), ("video_prompt", motion_prompt)):
        if text and instruction_echo(text):
            reasons.append(f"{name} repeats the director instructions")
    duration_raw = _field(example, "duration_seconds")
    if duration_raw is None or duration_raw == "":
        duration = 8.0
    else:
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError):
            duration = 0.0
            reasons.append("duration_seconds is not a number")
    if duration <= 0:
        reasons.append("duration_seconds must be positive")

    if _is_drone_or_cinematic(example):
        # Bypass VHS / liminal / handheld requirements entirely.
        return {"status": "pass" if not reasons else "fail", "reasons": reasons}

    if is_backrooms_example(example):
        lowered = (motion_prompt or prompt).lower()
        if not any(token in lowered for token in _CAMERA_KEYWORDS):
            reasons.append(
                "backrooms clip missing a camera keyword "
                "(handheld, camcorder, first-person, fpv, pov)"
            )
        if not has_motion_keyword(lowered):
            reasons.append(
                "backrooms clip missing a motion keyword "
                "(walk, push in, tracking, dolly, pan, moves, ...; a negated "
                "motion phrase does not count)"
            )
    return {"status": "pass" if not reasons else "fail", "reasons": reasons}


def passes_curriculum(
    example: Any,
    pred: Any,
    parsed: dict | None = None,
    iteration: int = 0,
    *,
    video_path: Path | None = None,
) -> dict:
    """Category-aware curriculum entrypoint used by live eval.

    Mechanical gate first (drone/cinematic bypass of VHS checks); then the
    progressive VLM score bar when ``parsed`` is provided.
    """
    mech = mechanical_director_gate(example, pred, video_path)
    if mech.get("status") != "pass":
        return {
            "pass": False,
            "threshold": None,
            "iteration": int(iteration or 0),
            "compared": None,
            "reasons": list(mech.get("reasons") or []),
            "mechanical": mech,
        }
    if parsed is None:
        return {
            "pass": True,
            "threshold": None,
            "iteration": int(iteration or 0),
            "compared": None,
            "reasons": [],
            "mechanical": mech,
        }
    scored = video_director_passes_curriculum(parsed, iteration, use_minimum=True)
    scored["mechanical"] = mech
    return scored


def _unwrap_text_object(value: dict) -> str:
    """Text of an object-valued prompt field: a known text key, else the string values."""
    for key in ("description", "text", "prompt", "value", "content"):
        if isinstance(value.get(key), str) and value[key].strip():
            return value[key].strip()
    return " ".join(str(v).strip() for v in value.values()
                    if isinstance(v, str) and v.strip())


def director_json_adapter():
    """JSONAdapter that fills missing cfg/denoise/step_count instead of aborting the eval."""
    dspy = gvd._dspy()
    from dspy.adapters.json_adapter import apply_output_field_defaults, json_repair, parse_value
    from dspy.utils.exceptions import AdapterParseError

    class DirectorJSONAdapter(dspy.JSONAdapter):
        def parse(self, signature, completion: str):
            fields = json_repair.loads(completion)
            if not isinstance(fields, dict):
                match = re.search(r"\{.*\}", str(completion), re.DOTALL)
                if match:
                    fields = json_repair.loads(match.group(0))
            if not isinstance(fields, dict):
                raise AdapterParseError(
                    adapter_name="DirectorJSONAdapter",
                    signature=signature,
                    lm_response=completion,
                    message="LM response cannot be serialized to a JSON object.",
                )
            allowed = set(signature.output_fields)
            fields = {key: value for key, value in fields.items() if key in allowed}
            for name, fallback in HPARAM_FALLBACKS.items():
                if name not in allowed:
                    continue
                number = _try_parse_float(fields.get(name)) if name in fields else None
                if number is None:
                    msg = (
                        f"JSONAdapter missing {name}={fields.get(name)!r}; "
                        f"using fallback {fallback}"
                    )
                    log.warning(msg)
                    warnings.warn(msg, stacklevel=2)
                    fields[name] = fallback
                else:
                    # Store the coerced float: parse_value(float) rejects the raw
                    # {"value": "4.0"} / "4.0-5.5" forms the student emits.
                    fields[name] = number
            for key, value in list(fields.items()):
                if isinstance(value, dict) and signature.output_fields[key].annotation is str:
                    # {"start_prompt": {"description": "..."}} would otherwise
                    # reach CLIP/MiniMax as the text "{'description': '...'}".
                    value = _unwrap_text_object(value)
                fields[key] = parse_value(value, signature.output_fields[key].annotation)
            fields = apply_output_field_defaults(signature, fields)
            for key in signature.output_fields:
                if key in fields:
                    continue
                if key in HPARAM_FALLBACKS:
                    fields[key] = HPARAM_FALLBACKS[key]
                elif key in {
                    "reasoning", "positive_prompt", "start_prompt",
                    "video_prompt", "negative_prompt",
                }:
                    # Empty text reaches the mechanical gate, which names the field.
                    fields[key] = ""
                else:
                    raise AdapterParseError(
                        adapter_name="DirectorJSONAdapter",
                        signature=signature,
                        lm_response=completion,
                        parsed_result=fields,
                    )
            return fields

    return DirectorJSONAdapter()


def harden_student_lm(task_lm: Any) -> Any:
    """Raise qwen2.5:1.5b completion budget (8192) and curb repetition loops."""
    stop = ["```\n", "<|im_end|>", "}\n}"]
    ollama_opts = {
        "num_predict": STUDENT_MAX_TOKENS,
        "repeat_penalty": 1.2,
        "stop": list(stop),
    }
    extra_body = {
        "keep_alive": 0,
        "num_predict": STUDENT_MAX_TOKENS,
        "repeat_penalty": 1.2,
        "stop": list(stop),
        "options": ollama_opts,
    }
    try:
        copied = task_lm.copy(
            max_tokens=STUDENT_MAX_TOKENS,
            temperature=0.4,
            extra_body=extra_body,
        )
        task_lm = copied
    except Exception:
        kwargs = getattr(task_lm, "kwargs", None)
        if isinstance(kwargs, dict):
            kwargs["max_tokens"] = STUDENT_MAX_TOKENS
            kwargs["temperature"] = 0.4
            extra = dict(kwargs.get("extra_body") or {})
            extra.update(extra_body)
            kwargs["extra_body"] = extra
    try:
        gvd._dspy().configure(lm=task_lm, adapter=director_json_adapter())
    except Exception:
        pass
    return task_lm


def _fail_penalty(error: str) -> float:
    """Small distinct scalars so MIPRO can tell failure modes apart."""
    text = str(error or "").lower()
    if "timeout" in text:
        return 0.05
    if (
        "json" in text
        or "mechanical" in text
        # positive_prompt (legacy) or start_prompt/video_prompt (FLUX+MiniMax).
        or "prompt is empty" in text
        or "hparam" in text
        or "adapter" in text
        or "unparseable" in text
    ):
        return 0.02
    if (
        "pipeline" in text
        or "dispatch" in text
        or "comfy" in text
        or "wan" in text
        or "vram" in text
    ):
        return 0.01
    return 0.01


# A rendered and judged clip must outrank every _fail_penalty above, however
# bad its scores: a real render gives MIPRO information, a timeout gives none.
# Before 2026-09-24 an all-zero verdict scored 0.0 and e.g. 0.0/0.0/0.15 scored
# 0.045, both below a render timeout (0.05), so the optimizer could prefer a
# program that never renders. The fixed judge (video_judge.py, CHANGELOG
# 2026-09-24q) returns all-zero far more often, which is why this matters now.
# 0.10 is twice the largest penalty. Clips at or above 0.10 are unchanged.
JUDGED_SCORE_FLOOR = 0.10


def _judged_scalar(minimum: float, mean: float) -> float:
    """MIPRO scalar for a judged clip: 0.7*min + 0.3*mean, never below JUDGED_SCORE_FLOOR."""
    return max(JUDGED_SCORE_FLOOR, (0.7 * float(minimum)) + (0.3 * float(mean)))


def _fail_result(
    *,
    hparams: dict[str, float],
    example: Any,
    pred: Any,
    error: str,
    video_path: str | None = None,
    vram_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    clip_id = str(_field(example, "id") or _field(example, "clip_id") or "")
    mipro = _fail_penalty(error)
    feedback = {
        "mock": False,
        "clip_id": clip_id,
        "category": str(_field(example, "category") or ""),
        "hparams": hparams,
        "step_count_int": int(round(hparams["step_count"])),
        "scores": None,
        "mean": None,
        "minimum": None,
        "threshold": None,
        "passes_curriculum": False,
        "mipro": mipro,
        "error": error,
        "video_path": video_path,
        # Resolved FLUX still / MiniMax motion text; the resolvers fall back to
        # legacy positive_prompt for pre-2026-09-16 Wan predictions.
        "start_prompt": _director_start_prompt(example, pred)[:500],
        "video_prompt": _director_motion_prompt(pred)[:500],
        "vram_trace": vram_trace or [],
    }
    return {
        "mipro": mipro,
        "passes_curriculum": False,
        "hparams": hparams,
        "scores": None,
        "feedback": json.dumps(feedback, ensure_ascii=True),
        "feedback_obj": feedback,
        "error": error,
        "video_path": video_path,
    }


def _store(result: dict[str, Any]) -> float:
    global LAST_METRIC_RESULT
    LAST_METRIC_RESULT = result
    METRIC_HISTORY.append(result)
    generalized_video_metric.last_feedback = result["feedback"]
    generalized_video_metric.last_result = result
    history_path = HERE / "runtime" / "dspy_opt" / "gvd_live_metric_history.jsonl"
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result.get("feedback_obj") or json.loads(result["feedback"]), ensure_ascii=True) + "\n")
    except Exception:
        pass
    return float(result["mipro"])



def _force_frame_length(graph: dict, num_frames: int = MINIMAX_NUM_FRAMES) -> dict:
    """Hard-set MiniMax / I2V length fields to 192 frames (8s @ 24fps).

    Only touch explicit length scalars. NEVER overwrite image-link inputs such as
    ``first_frame`` / ``image`` / ``images`` (Comfy links like ``["8", 0]``).
    """
    length_keys = {
        "num_frames",
        "frame_count",
        "frames",
        "length",
        "video_length",
        "num_frames_total",
        "total_frames",
        "duration_frames",
    }
    protected = {
        "first_frame",
        "last_frame",
        "image",
        "images",
        "start_image",
        "end_image",
        "init_image",
        "pixels",
    }
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key in list(inputs.keys()):
            lk = str(key).lower()
            if lk in protected:
                continue
            if lk not in length_keys:
                continue
            val = inputs[key]
            if isinstance(val, (list, tuple, dict)):
                continue
            inputs[key] = int(num_frames)
    return graph




def _comfy_input_name(image: str) -> str:
    """Comfy input-relative name for LoadImage: basename for absolute/Windows paths."""
    image_s = str(image).strip()
    p = Path(image_s)
    if p.is_absolute() or "\\" in image_s or (len(image_s) > 2 and image_s[1] == ":"):
        return p.name
    if ".." in Path(image_s).parts:
        raise ValueError("unsafe frame path")
    return image_s.replace("\\", "/")


def bind_h3_image_frames(
    graph: dict,
    *,
    first_frame_path: str | None = None,
    last_frame_path: str | None = None,
) -> dict:
    """Bind uploaded images to MiniMaxH3ImageToVideo.first_frame / .last_frame.

    Matches h3_i2v_reference.api.json: LoadImage node -> first_frame link.
    ``first_frame_path`` / ``last_frame_path`` are Comfy input-relative names
    (already uploaded) or absolute paths whose basename is used as the upload name.
    """
    if not isinstance(graph, dict):
        return graph
    # Locate MiniMaxH3ImageToVideo node (prefer known id "20")
    target_id = None
    if isinstance(graph.get("20"), dict) and str(graph["20"].get("class_type") or "") == "MiniMaxH3ImageToVideo":
        target_id = "20"
    else:
        for nid, node in graph.items():
            if isinstance(node, dict) and str(node.get("class_type") or "") == "MiniMaxH3ImageToVideo":
                target_id = str(nid)
                break
    if target_id is None:
        return graph
    node = graph[target_id]
    inputs = dict(node.get("inputs") or {})
    for nid, field, image in (("1001", "first_frame", first_frame_path), ("1002", "last_frame", last_frame_path)):
        if not image:
            continue
        graph[nid] = {"class_type": "LoadImage", "inputs": {"image": _comfy_input_name(image)}}
        inputs[field] = [nid, 0]
    graph[target_id] = {**node, "inputs": inputs}
    meta = graph.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["h3_frame_binding"] = {
            "first_frame": first_frame_path,
            "last_frame": last_frame_path,
            "bound_fields": [k for k in ("first_frame", "last_frame") if k in inputs and isinstance(inputs.get(k), list)],
        }
    return graph


def prune_unreferenced_flux_nodes(graph: dict) -> dict:
    """Remove FLUX_PHASE_NODES that no remaining node consumes (fixpoint).

    Only ever touches the FLUX still subgraph ids; MiniMax/voice/save nodes
    are never pruned here. Records what was dropped in ``_meta``.
    """
    if not isinstance(graph, dict):
        return graph

    def _referenced() -> set[str]:
        refs: set[str] = set()
        for nid, node in graph.items():
            if nid == "_meta" or not isinstance(node, dict):
                continue
            for value in (node.get("inputs") or {}).values():
                if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                    refs.add(str(value[0]))
        return refs

    pruned: list[str] = []
    while True:
        refs = _referenced()
        drop = [
            nid for nid in list(graph)
            if nid in FLUX_PHASE_NODES and isinstance(graph.get(nid), dict) and nid not in refs
        ]
        if not drop:
            break
        for nid in drop:
            graph.pop(nid, None)
            pruned.append(nid)
    meta = graph.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["flux_still_skipped"] = bool(pruned)
        meta["pruned_flux_nodes"] = sorted(pruned, key=lambda s: (len(s), s))
    return graph


# Refine checkpoint (clip-to-clip chaining quality reset): the FLUX branch runs
# as low-denoise img2img on an uploaded frame instead of T2I from an empty latent.
REFINE_LOAD_NODE, REFINE_SCALE_NODE, REFINE_ENCODE_NODE, REFINE_SHARPEN_NODE = (
    "1003", "1004", "1005", "1006",
)


def bind_refine_checkpoint(
    graph: dict,
    *,
    frame_path: str,
    denoise: float,
    sharpen_alpha: float = 0.0,
) -> dict:
    """Rewire the FLUX still branch to img2img-refine ``frame_path``.

    LoadImage(1003) -> ImageScale(1004, to node 5's size) -> VAEEncode(1005, FLUX
    VAE 10) -> KSampler 3 at ``denoise`` -> VAEDecode 8 [-> ImageSharpen 1006].
    Node 3 keeps its start_prompt/negative conditioning (6/7/12) and model (41),
    so the refinement is steered by the same text + model as a fresh still, but
    starts from the frame's pose/composition. EmptyFlux2LatentImage 5 is removed.
    Whatever consumed the FLUX decode (MiniMax first_frame) now gets the refined
    image. Raises if the graph lacks the expected FLUX nodes: a silently
    unrefined T2I still would defeat the checkpoint.
    """
    d = float(denoise)
    if not 0.0 < d < 1.0:
        raise ValueError(f"refine denoise must be in (0, 1), got {denoise!r}")
    expected = {"3": "KSampler", "5": "EmptyFlux2LatentImage", "8": "VAEDecode", "10": "VAELoader"}
    for nid, ctype in expected.items():
        if str((graph.get(nid) or {}).get("class_type") or "") != ctype:
            raise RuntimeError(f"refine checkpoint needs node {nid} {ctype} in the FLUX+MiniMax graph")
    size = graph["5"]["inputs"]
    graph[REFINE_LOAD_NODE] = {"class_type": "LoadImage", "inputs": {"image": _comfy_input_name(frame_path)}}
    graph[REFINE_SCALE_NODE] = {
        "class_type": "ImageScale",
        "inputs": {
            "image": [REFINE_LOAD_NODE, 0],
            "upscale_method": "lanczos",
            "width": int(size["width"]),
            "height": int(size["height"]),
            "crop": "center",
        },
    }
    graph[REFINE_ENCODE_NODE] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": [REFINE_SCALE_NODE, 0], "vae": ["10", 0]},
    }
    graph["3"]["inputs"]["latent_image"] = [REFINE_ENCODE_NODE, 0]
    graph["3"]["inputs"]["denoise"] = d
    graph.pop("5", None)
    if float(sharpen_alpha) > 0:
        graph[REFINE_SHARPEN_NODE] = {
            "class_type": "ImageSharpen",
            "inputs": {"image": ["8", 0], "sharpen_radius": 1, "sigma": 1.0, "alpha": float(sharpen_alpha)},
        }
        for nid, node in graph.items():
            if nid in ("_meta", REFINE_SHARPEN_NODE) or not isinstance(node, dict):
                continue
            for key, value in (node.get("inputs") or {}).items():
                if value == ["8", 0]:
                    node["inputs"][key] = [REFINE_SHARPEN_NODE, 0]
    meta = graph.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["flux_still_skipped"] = False
        meta["refine_checkpoint"] = {
            "frame": str(frame_path),
            "denoise": d,
            "sharpen_alpha": float(sharpen_alpha),
            "latent_from": REFINE_ENCODE_NODE,
        }
    return graph


def resolve_generation_frames(
    *,
    editorial_frames: int | None = None,
    generation_frames: int | None = None,
    duration_seconds: float | None = None,
) -> tuple[int, int]:
    """Return (editorial_frames, generation_frames) using H3 alignment."""
    if generation_frames is not None and editorial_frames is None:
        gen = int(generation_frames)
        return gen, h3_generation_frames(gen)
    if editorial_frames is not None:
        ed = int(editorial_frames)
    elif duration_seconds is not None:
        ed = max(1, int(round(float(duration_seconds) * MINIMAX_FPS)))
    else:
        ed = int(DEFAULT_EDITORIAL_FRAMES)
    return editorial_vs_generation_frames(ed)

def _inject_prompt_fields(
    graph: dict,
    *,
    start_prompt: str,
    video_prompt: str,
    negative: str,
    hparams: dict[str, float],
) -> dict:
    """Fill placeholder / known text+hparam slots in a FLUX+MiniMax API graph."""
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        if str(node_id).startswith("_"):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        ctype = str(node.get("class_type") or "")
        # Heuristic text injection until the real template maps exact node IDs.
        if "text" in inputs and isinstance(inputs["text"], str):
            marker = inputs["text"].strip().upper()
            if marker in {"{{START_PROMPT}}", "{{FLUX_PROMPT}}", "START_PROMPT"}:
                inputs["text"] = start_prompt
            elif marker in {"{{VIDEO_PROMPT}}", "{{MOTION_PROMPT}}", "VIDEO_PROMPT"}:
                inputs["text"] = video_prompt
            elif marker in {"{{NEGATIVE}}", "NEGATIVE_PROMPT"}:
                inputs["text"] = negative
        # cfg/steps/denoise are FLUX-still hparams. They must not reach the
        # MiniMax sampler (node 35 BasicScheduler): that silently ran MiniMax
        # at the FLUX step count (12-40) on 143 of 144 renders through
        # 2026-09-23. MiniMax steps are set in _apply_flux_minimax_node_map.
        if str(node_id) not in MINIMAX_PHASE_NODES:
            for cfg_key in ("cfg", "cfg_scale", "guidance"):
                if cfg_key in inputs:
                    inputs[cfg_key] = float(hparams.get("cfg_scale", inputs[cfg_key]))
            for step_key in ("steps", "step_count", "num_inference_steps"):
                if step_key in inputs:
                    inputs[step_key] = int(round(hparams.get("step_count", inputs[step_key])))
            if "denoise" in inputs:
                inputs["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise
        # MiniMax-style prompt fields
        for pk in ("prompt", "positive", "motion_prompt", "video_prompt"):
            if pk in inputs and isinstance(inputs[pk], str):
                marker = inputs[pk].strip().upper()
                if marker in {"{{VIDEO_PROMPT}}", "{{MOTION_PROMPT}}", "VIDEO_PROMPT", ""}:
                    inputs[pk] = video_prompt
        if ctype.lower().startswith("minimax") or "minimax" in ctype.lower():
            for pk in ("prompt", "text", "positive"):
                if pk in inputs:
                    inputs[pk] = video_prompt
    return graph






def _comfy_prompt_graph(graph: dict) -> dict:
    """Drop non-node bookkeeping keys (e.g. _meta) before Comfy /prompt."""
    if not isinstance(graph, dict):
        raise TypeError("graph must be a dict")
    return {
        key: value
        for key, value in graph.items()
        if not str(key).startswith("_") and isinstance(value, dict) and "class_type" in value
    }



def _apply_flux_minimax_node_map(
    graph: dict,
    *,
    start_prompt: str,
    video_prompt: str,
    hparams: dict[str, float],
    negative: str = "",
    prefix: str | None = None,
    generation_frames: int | None = None,
    editorial_frames: int | None = None,
) -> dict:
    """Wire DSPy fields onto flux_minimax_i2v_api.json.

    Contract:
    - "6" CLIPTextEncode.text <- start_prompt  ({{START_PROMPT}})
    - "7" CLIPTextEncode.text <- negative_prompt ({{NEGATIVE_PROMPT}})
    - "20" MiniMaxH3ImageToVideo.prompt <- video_motion_prompt ({{VIDEO_PROMPT}})
    - "20" length forced to 192 (8s @ 24fps; valid 17k+5 grid)
    - "3" KSampler cfg/steps/denoise <- hparams (FLUX still)
    - "35" MiniMax BasicScheduler.steps <- hparams["minimax_step_count"], else
      MINIMAX_H3_STEPS (20). Never the FLUX step_count.
    """
    def _fill(value: str, token: str, replacement: str) -> str:
        text = str(value or "")
        if token in text:
            return text.replace(token, str(replacement or ""))
        return str(replacement or "")

    node6 = graph.get("6")
    if isinstance(node6, dict) and isinstance(node6.get("inputs"), dict):
        node6["inputs"]["text"] = _fill(
            node6["inputs"].get("text", "{{START_PROMPT}}"),
            "{{START_PROMPT}}",
            start_prompt,
        )

    node7 = graph.get("7")
    if isinstance(node7, dict) and isinstance(node7.get("inputs"), dict):
        node7["inputs"]["text"] = _fill(
            node7["inputs"].get("text", "{{NEGATIVE_PROMPT}}"),
            "{{NEGATIVE_PROMPT}}",
            negative,
        )

    node20 = graph.get("20")
    if isinstance(node20, dict) and isinstance(node20.get("inputs"), dict):
        raw = str(node20["inputs"].get("prompt", "{{VIDEO_PROMPT}}"))
        raw = raw.replace("{{VIDEO_MOTION_PROMPT}}", "{{VIDEO_PROMPT}}")
        filled = _fill(raw, "{{VIDEO_PROMPT}}", video_prompt)
        # Do NOT append negatives into MiniMax prompt text — FLUX/MiniMax treat
        # named concepts as attractors (concept bleed). CLIP negative stays on node 7 only.
        node20["inputs"]["prompt"] = filled
        # Real MiniMaxH3 schema uses length, not duration_frames.
        _ed, _gen = resolve_generation_frames(
            editorial_frames=editorial_frames,
            generation_frames=generation_frames,
        )
        node20["inputs"]["length"] = int(_gen)
        if "duration_frames" in node20["inputs"]:
            node20["inputs"]["duration_frames"] = int(_gen)
        if "num_frames" in node20["inputs"]:
            node20["inputs"]["num_frames"] = int(_gen)

    node3 = graph.get("3")
    if isinstance(node3, dict) and isinstance(node3.get("inputs"), dict):
        node3["inputs"]["cfg"] = float(
            hparams.get("cfg_scale", node3["inputs"].get("cfg", 3.5))
        )
        node3["inputs"]["steps"] = int(
            round(float(hparams.get("step_count", node3["inputs"].get("steps", 20))))
        )
        node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise

    node35 = graph.get("35")
    if (isinstance(node35, dict) and node35.get("class_type") == "BasicScheduler"
            and isinstance(node35.get("inputs"), dict)):
        node35["inputs"]["steps"] = int(
            round(float(hparams.get("minimax_step_count") or MINIMAX_H3_STEPS))
        )

    node25 = graph.get("25")
    if isinstance(node25, dict) and isinstance(node25.get("inputs"), dict):
        # SaveVideo expects VIDEO via CreateVideo, not images.
        if "images" in node25["inputs"] and "video" not in node25["inputs"]:
            node25["inputs"]["video"] = node25["inputs"].pop("images")
        if prefix and "filename_prefix" in node25["inputs"]:
            node25["inputs"]["filename_prefix"] = str(prefix)

    meta = graph.setdefault("_meta", {})
    if isinstance(meta, dict):
        _ed, _gen = resolve_generation_frames(
            editorial_frames=editorial_frames,
            generation_frames=generation_frames,
        )
        meta["status"] = "MAPPED_FLUX_MINIMAX_HYBRID"
        meta["editorial_frames"] = int(_ed)
        meta["generation_frames"] = int(_gen)
        meta["num_frames"] = int(_gen)  # generation length actually submitted
        meta["note"] = (
            "MiniMaxH3ImageToVideo emits CONDITIONING+LATENT; sampler/decode/"
            "CreateVideo/SaveVideo nodes complete the MP4 path."
        )
        meta["node_map"] = {
            "flux_positive_clip": "6",
            "flux_negative_clip": "7",
            "flux_ksampler": "3",
            "minimax_i2v": "20",
            "minimax_scheduler": "35",
            "save_video": "25",
        }
    return graph



def _flux_safe_hparams(hparams: dict) -> dict:
    """FLUX Empty-Latent T2I: denoise locked at 1.0; only cfg/steps tunable."""
    out = dict(hparams or {})
    out["denoise"] = 1.0
    return out


def build_minimax_graph(
    start_prompt: str,
    video_prompt: str,
    hparams: dict[str, float],
    *,
    negative: str = "",
    prefix: str = "dspy_opt/gvd_minimax",
    stills_only: bool = False,
    clip_id: str = "",
    raw_dialogue: str = "",
    dialogue: list | None = None,
    enable_f5_voice: bool = True,
    voice_provider: str | None = None,
    editorial_frames: int | None = None,
    generation_frames: int | None = None,
    duration_seconds: float | None = None,
    start_frame_path: str | None = None,
    end_frame_path: str | None = None,
    first_frame_path: str | None = None,
    last_frame_path: str | None = None,
    refine_frame_path: str | None = None,
    refine_denoise: float | None = None,
    refine_sharpen_alpha: float = 0.0,
) -> dict:
    """FLUX.1 start frame piped into MiniMax I2V with H3-aligned generation_frames.

    Carries separate editorial_frames vs generation_frames (H3: congruent to 5 mod 17,
    clamp ~124–362). Optional first/last frame paths bind LoadImage → MiniMaxH3ImageToVideo.
    ``refine_frame_path`` instead keeps the FLUX still but makes it a low-denoise
    img2img refinement of that frame (bind_refine_checkpoint); it cannot be
    combined with a first frame, which would bypass FLUX entirely.
    Typed ``dialogue`` array (speaker+text) is preferred over raw_dialogue string.
    """
    if refine_frame_path and (first_frame_path or start_frame_path):
        raise ValueError("refine_frame_path and start/first_frame_path are mutually exclusive")
    if refine_frame_path and refine_denoise is None:
        raise ValueError("refine_frame_path requires an explicit refine_denoise")
    if MINIMAX_GRAPH_TEMPLATE.exists():
        graph = json.loads(MINIMAX_GRAPH_TEMPLATE.read_text(encoding="utf-8"))
        if not isinstance(graph, dict):
            raise RuntimeError(f"MiniMax template must be a dict: {MINIMAX_GRAPH_TEMPLATE}")
    else:
        # Scaffold awaiting user-supplied ComfyUI API JSON.
        graph = {
            "_meta": {
                "architecture": "flux1_fp8_gguf_to_minimax_i2v",
                "status": "AWAITING_COMFY_API_JSON",
                "template_path": str(MINIMAX_GRAPH_TEMPLATE),
                "num_frames": MINIMAX_NUM_FRAMES,
                "filename_prefix": prefix,
            },
            "flux_clip": {
                "class_type": "CLIPTextEncodeFluxPLACEHOLDER",
                "inputs": {"text": "{{START_PROMPT}}", "clip": ["flux_loader", 0]},
            },
            "flux_loader": {
                "class_type": "UNETLoaderGGUFPLACEHOLDER",
                "inputs": {"unet_name": "flux1-dev-fp8-gguf-PLACEHOLDER.gguf"},
            },
            "flux_sampler": {
                "class_type": "KSamplerPLACEHOLDER",
                "inputs": {
                    "seed": 42,
                    "steps": int(round(hparams.get("step_count", 28))),
                    "cfg": float(hparams.get("cfg_scale", 5.5)),
                    "denoise": float(hparams.get("denoise", 1.0)),
                    "model": ["flux_loader", 0],
                    "positive": ["flux_clip", 0],
                    "latent_image": ["flux_empty", 0],
                },
            },
            "flux_empty": {
                "class_type": "EmptyFlux2LatentImagePLACEHOLDER",
                "inputs": {"width": 1280, "height": 704, "batch_size": 1},
            },
            "flux_decode": {
                "class_type": "VAEDecodePLACEHOLDER",
                "inputs": {"samples": ["flux_sampler", 0], "vae": ["flux_vae", 0]},
            },
            "flux_vae": {
                "class_type": "VAELoaderPLACEHOLDER",
                "inputs": {"vae_name": "ae.safetensors"},
            },
            "minimax_i2v": {
                "class_type": "MiniMaxImageToVideoPLACEHOLDER",
                "inputs": {
                    "image": ["flux_decode", 0],
                    "prompt": "{{VIDEO_PROMPT}}",
                    "negative_prompt": negative or "",
                    "num_frames": MINIMAX_NUM_FRAMES,
                    "cfg": float(hparams.get("cfg_scale", 5.5)),
                    "seed": 42,
                },
            },
            "save_mp4": {
                "class_type": "SaveVideoPLACEHOLDER",
                "inputs": {
                    "video": ["minimax_i2v", 0],
                    "filename_prefix": prefix,
                },
            },
        }

    graph = _inject_prompt_fields(
        graph,
        start_prompt=start_prompt,
        video_prompt=video_prompt,
        negative=negative or "",
        hparams=hparams,
    )
    _editorial, _generation = resolve_generation_frames(
        editorial_frames=editorial_frames,
        generation_frames=generation_frames,
        duration_seconds=duration_seconds,
    )
    graph = _force_frame_length(graph, _generation)
    # Always stamp meta
    meta = graph.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["editorial_frames"] = int(_editorial)
        meta["generation_frames"] = int(_generation)
        meta["num_frames"] = int(_generation)
        meta["architecture"] = meta.get("architecture") or "flux1_to_minimax_i2v"
    # Explicit node-ID wiring for flux_minimax_i2v_api.json
    _sp = start_prompt
    _vp = video_prompt if "video_prompt" in locals() else locals().get("video_motion_prompt", "")
    _hp = hparams
    _neg = locals().get("negative", "") or ""
    _pref = locals().get("prefix", None)
    graph = _apply_flux_minimax_node_map(
        graph,
        start_prompt=_sp,
        video_prompt=_vp,
        hparams=_hp,
        negative=_neg,
        prefix=_pref,
        generation_frames=_generation,
        editorial_frames=_editorial,
    )
    _first = first_frame_path or start_frame_path
    _last = last_frame_path or end_frame_path
    if _first or _last:
        graph = bind_h3_image_frames(
            graph,
            first_frame_path=_first,
            last_frame_path=_last,
        )
        if _first and not stills_only:
            # first_frame now comes from LoadImage, so the FLUX T2I branch
            # feeds nothing. Drop it from the payload so the skipped still
            # is explicit in the debug dump (and never validated/loaded).
            graph = prune_unreferenced_flux_nodes(graph)
    if refine_frame_path:
        graph = bind_refine_checkpoint(
            graph,
            frame_path=str(refine_frame_path),
            denoise=float(refine_denoise),
            sharpen_alpha=float(refine_sharpen_alpha or 0.0),
        )
    if stills_only:
        graph = trim_graph_to_stills_only(graph, filename_prefix=prefix)
    elif wants_minimax_ref2vid(str(clip_id or "")):
        # C002+: MiniMaxH3ReferenceToVideo(C001 still + master voice) + native audio mux.
        # Skips Fish/F5 entirely. C001 never enters this branch.
        graph = apply_minimax_ref2vid(
            graph,
            video_prompt=str(video_prompt or ""),
        )
        graph = attach_minimax_native_audio_mux(graph)
        meta = graph.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta["minimax_mode"] = "reference_to_video"
            meta["architecture"] = "flux1_to_minimax_h3_ref2vid"
        print(
            f"  minimax ref2vid [{clip_id}]: ReferenceToVideo + native audio mux "
            f"(skip Fish/F5)"
        )
    elif not stills_only:
        _dialogue = normalize_dialogue_array(dialogue) if dialogue is not None else []
        if not _dialogue and raw_dialogue:
            _dialogue = normalize_dialogue_array(raw_dialogue)
        graph = apply_dynamic_voice_routing(
            graph,
            clip_id=str(clip_id or ""),
            raw_dialogue=str(raw_dialogue or dialogue_to_speech_text(_dialogue) or ""),
            dialogue=_dialogue,
            enable_f5=bool(enable_f5_voice),
            voice_provider=voice_provider,
            fail_closed=True,
        )
    return graph


def build_wan_graph(
    start_name: str,
    end_name: str,
    prompt: str,
    negative: str,
    prefix: str,
    *,
    cfg_scale: float,
    denoise: float,
    step_count: float,
) -> dict:
    """DEPRECATED: Wan FLF path retired. Raises to catch stale callers."""
    raise RuntimeError(
        "build_wan_graph is retired. Use build_minimax_graph(start_prompt, "
        "video_motion_prompt, hparams) for FLUX.1 + MiniMax I2V."
    )




# Small students echo instruction labels into the prompt text, e.g.
# "FLUX.1 T2I: Cinematic drone..." / "MiniMax I2V: Drone captures..." (seen on
# the 2026-09-24 GVD-D01 verify render; the label reached CLIP and MiniMax).
# Removed repeatedly from the start: a field/model label ending in a colon
# ("Start frame:", "Video prompt:", "FLUX.1 still prompt:"), or a bare
# versioned model token ("FLUX.1 ", "MiniMax I2V "). "Flux capacitor" and
# "MiniMax-style" are left alone.
_PROMPT_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"(?:(?:start|video|video[_ ]motion|motion|opening|negative|positive)[_ ]"
    r"(?:prompt|frame)(?:\s*\([^)]{0,40}\))?"
    r"|(?:flux(?:\.1)?|minimax)(?:\s+(?:h3|i2v|t2i))?"
    r"(?:\s+(?:still|video|image))?(?:\s+prompt)?)\s*:"
    r"|flux\.1(?:\s+(?:t2i|still))?\s"
    r"|minimax\s+(?:i2v|t2i|h3)\s"
    r")\s*",
    re.IGNORECASE,
)


def strip_prompt_label(text: str) -> str:
    text = str(text or "").strip()
    while True:
        stripped = _PROMPT_LABEL_RE.sub("", text, count=1)
        if stripped == text:
            return text
        text = stripped.strip()


_ECHO_NGRAM = 6
_echo_cache: dict[str, frozenset] = {}


def _instruction_ngrams() -> frozenset:
    """6-word shingles of the live director instructions + output-field descs."""
    sig = gvd.director_signature_class()
    source = " ".join([str(sig.instructions)] + [
        str(getattr(f, "json_schema_extra", {}).get("desc", "") or "")
        for f in sig.output_fields.values()
    ])
    cached = _echo_cache.get(source)
    if cached is None:
        words = re.findall(r"[a-z0-9]+", source.lower())
        cached = frozenset(
            tuple(words[i:i + _ECHO_NGRAM]) for i in range(len(words) - _ECHO_NGRAM + 1)
        )
        _echo_cache.clear()
        _echo_cache[source] = cached
    return cached


def instruction_echo(text: str) -> bool:
    """True when a prompt repeats 6+ consecutive words of the instructions/descs.

    The 1.5B student sometimes returns its field description as the prompt
    ("descriptive lighting/texture/composition for the opening frame only").
    Tracks the live instruction text, unlike generate_video.looks_like_meta_prompt.
    """
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    shingles = _instruction_ngrams()
    return any(
        tuple(words[i:i + _ECHO_NGRAM]) in shingles
        for i in range(len(words) - _ECHO_NGRAM + 1)
    )


def _director_start_prompt(example: Any, pred: Any) -> str:
    """FLUX still text: dataset override, then pred.start_prompt, then legacy."""
    return strip_prompt_label(
        _field(example, "start_prompt")
        or _field(pred, "start_prompt")
        or _field(pred, "positive_prompt")
        or ""
    )


def _director_motion_prompt(pred: Any) -> str:
    """MiniMax motion text: pred.video_prompt (current), then legacy aliases."""
    return strip_prompt_label(
        _field(pred, "video_prompt")
        or _field(pred, "video_motion_prompt")
        or _field(pred, "motion_prompt")
        or _field(pred, "positive_prompt")
        or ""
    )


def generate_minimax_clip(
    example: Any,
    pred: Any,
    hparams: dict[str, float],
    *,
    timeout_s: float = WAN_TIMEOUT_S,
    stills_only: bool = False,
    editorial_frames: int | None = None,
    generation_frames: int | None = None,
    duration_seconds: float | None = None,
    start_frame_path: str | None = None,
    end_frame_path: str | None = None,
    dialogue: list | None = None,
    voice_provider: str | None = None,
    refine_frame_path: str | None = None,
    refine_denoise: float | None = None,
    refine_sharpen_alpha: float = 0.0,
) -> Path:
    """FLUX.1 start frame → MiniMax I2V (H3-aligned generation_frames). Caller owns VRAM.

    After the MP4 is on disk, immediately POST Comfy ``/free`` so the RTX 5080
    can load Qwen-VL. The graph template may still be a scaffold until the
    user drops the real API JSON at ``graphs/flux_minimax_i2v_api.json``.
    """
    import comfy_api
    from dispatcher import DEFAULT_COMFY_URL as orch_url
    from dispatcher import PipelineOrchestrator
    from live_vram_test import JOB_TIMEOUT_S, VIDEO_TIMEOUT_S, wait_for_video
    # WAN_TIMEOUT_S is module-level in this file; used for fused FLUX+MiniMax track timeout
    import vram_controller

    url = orch_url or DEFAULT_COMFY_URL
    if not comfy_api.ping(url):
        raise TimeoutError("ComfyUI is not listening on 127.0.0.1:8188")

    start_prompt = _director_start_prompt(example, pred)
    video_prompt = _director_motion_prompt(pred)
    negative = str(_field(pred, "negative_prompt") or "").strip()
    clip_id = str(_field(example, "id") or _field(example, "clip_id") or "gvd")
    if not start_prompt:
        raise ValueError("start_prompt is empty; FLUX still skipped")
    if (not video_prompt) and (not stills_only):
        raise ValueError("video_prompt is empty; MiniMax I2V skipped")

    _ex_editorial = editorial_frames
    if _ex_editorial is None:
        _ex_editorial = _field(example, "editorial_frames") or _field(pred, "editorial_frames")
    _ex_generation = generation_frames
    if _ex_generation is None:
        _ex_generation = _field(example, "generation_frames") or _field(pred, "generation_frames")
    _ex_duration = duration_seconds
    if _ex_duration is None:
        _ex_duration = _field(example, "duration_seconds") or _field(pred, "duration_seconds")
    _ed, _gen = resolve_generation_frames(
        editorial_frames=int(_ex_editorial) if _ex_editorial is not None else None,
        generation_frames=int(_ex_generation) if _ex_generation is not None else None,
        duration_seconds=float(_ex_duration) if _ex_duration is not None else None,
    )
    _first = (
        start_frame_path
        or _field(example, "start_frame_path")
        or _field(example, "first_frame_path")
        or None
    )
    _last = (
        end_frame_path
        or _field(example, "end_frame_path")
        or _field(example, "last_frame_path")
        or None
    )
    key = hashlib.sha256(
        json.dumps(
            {
                "start": start_prompt,
                "motion": video_prompt,
                "cfg": hparams["cfg_scale"],
                "denoise": hparams["denoise"],
                "steps": hparams["step_count"],
                "clip": clip_id,
                "editorial_frames": _ed,
                "generation_frames": _gen,
                "first": str(_first or ""),
                "last": str(_last or ""),
                **(
                    {"refine": [str(refine_frame_path), refine_denoise, refine_sharpen_alpha]}
                    if refine_frame_path else {}
                ),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:10]
    prefix = f"dspy_opt/gvd_{clip_id}_{key}"
    raw_dialogue = str(
        _field(example, "raw_dialogue")
        or _field(example, "pack_dialogue")
        or _field(pred, "raw_dialogue")
        or ""
    ).strip()
    _dialogue = dialogue
    if _dialogue is None:
        _dialogue = (
            _field(example, "dialogue")
            or _field(example, "dialogue_lines")
            or _field(pred, "dialogue")
            or None
        )
    _dialogue = normalize_dialogue_array(_dialogue) if _dialogue is not None else []
    if not _dialogue and raw_dialogue:
        _dialogue = normalize_dialogue_array(raw_dialogue)
    if not raw_dialogue and _dialogue:
        raw_dialogue = dialogue_to_speech_text(_dialogue)
    graph = build_minimax_graph(
        start_prompt,
        video_prompt,
        hparams,
        negative=negative,
        prefix=prefix,
        stills_only=bool(stills_only),
        clip_id=str(clip_id or ""),
        raw_dialogue=raw_dialogue,
        dialogue=_dialogue,
        enable_f5_voice=__import__("os").environ.get("GVD_F5_TTS", "1") != "0",
        voice_provider=voice_provider or _field(example, "voice_provider") or None,
        editorial_frames=_ed,
        generation_frames=_gen,
        start_frame_path=str(_first) if _first else None,
        end_frame_path=str(_last) if _last else None,
        refine_frame_path=str(refine_frame_path) if refine_frame_path else None,
        refine_denoise=refine_denoise,
        refine_sharpen_alpha=refine_sharpen_alpha,
    )
    if str((graph.get("_meta") or {}).get("status") or "") == "AWAITING_COMFY_API_JSON":
        raise RuntimeError(
            "FLUX+MiniMax Comfy API JSON not installed yet. Save the workflow "
            f"export to {MINIMAX_GRAPH_TEMPLATE} then re-run."
        )

    global LAST_RENDER_TELEMETRY
    orch = PipelineOrchestrator(comfy_url=url)
    monitor = _PhaseVRAMMonitor()
    monitor.start()
    monitor.set_phase("flux")  # FLUX nodes execute first in the fused graph
    telemetry: dict[str, Any] = {
        "sage_attention_minimax": True,
        "sage_node": "40",
        "sage_class": "PathchSageAttentionKJ",
        "sage_mode": "auto",
        "graph": ("flux_minimax_stills_only.json" if stills_only else "flux_minimax_i2v_api.json"),
    }
    try:
        # DEBUG: dump exact Comfy /prompt body before POST (clip leak / LoRA audit)
        try:
            _dump_dir = Path(os.environ.get("GVD_PAYLOAD_DUMP_DIR") or (HERE / "runtime" / "dspy_opt" / "payload_dumps"))
            _dump_dir.mkdir(parents=True, exist_ok=True)
            _safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(clip_id))[:64]
            _prompt_body = _comfy_prompt_graph(graph)
            _audit = {
                "clip_id": clip_id,
                "resolved_start_prompt": start_prompt,
                "resolved_video_prompt": video_prompt,
                "resolved_negative": negative,
                "hparams": hparams,
                "lora_nodes": [
                    {"id": k, "class_type": v.get("class_type"), "inputs": v.get("inputs")}
                    for k, v in _prompt_body.items()
                    if isinstance(v, dict) and "lora" in str(v.get("class_type", "")).lower()
                ],
                "clip_text_nodes": [
                    {"id": k, "class_type": v.get("class_type"), "text": (v.get("inputs") or {}).get("text")}
                    for k, v in _prompt_body.items()
                    if isinstance(v, dict) and "cliptext" in str(v.get("class_type", "")).lower().replace("_", "")
                ],
                "prompt_graph": _prompt_body,
            }
            _dump_path = _dump_dir / f"debug_{_safe_id}_payload.json"
            _dump_path.write_text(json.dumps(_audit, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  DEBUG payload dump -> {_dump_path}")
            if "c001" in str(clip_id).lower():
                _alias = Path(r"A:/Users/rhine/.grok/long-running-background-tasks") / "debug_c001_payload.json"
                _alias.write_text(json.dumps(_audit, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  DEBUG C001 alias -> {_alias}")
        except Exception as _dump_exc:
            print(f"  DEBUG payload dump failed: {_dump_exc}")
        try:
            queued = orch.submit_prompt(_comfy_prompt_graph(graph))
        except Exception as _sub_exc:
            _kind = classify_voice_submit_error(_sub_exc)
            _voice_meta = ((graph.get("_meta") or {}).get("voice_routing") or {})
            _required = bool(_voice_meta.get("required_dialogue") or _dialogue)
            if _kind in ("voice_node", "class_type"):
                if _required:
                    raise VoiceAudioGateError(
                        f"voice/class_type submit failed with required dialogue "
                        f"(provider={_voice_meta.get('provider')}, kind={_kind}): {_sub_exc}"
                    ) from _sub_exc
                print(f"  voice submit failed ({_sub_exc}); retrying silent (no required dialogue)")
                graph = strip_f5_voice_nodes(graph)
                for _drop in ("42", "43", "44", "90", "91", "92"):
                    graph.pop(_drop, None)
                graph = strip_f5_voice_nodes(graph)
                queued = orch.submit_prompt(_comfy_prompt_graph(graph))
            else:
                raise
        pid = queued["prompt_id"]
        tracked = _track_prompt_with_phase(
            orch,
            pid,
            monitor,
            timeout_s=min(float(WAN_TIMEOUT_S), float(timeout_s)),  # was JOB_TIMEOUT_S=600; MiniMax 192f needs >>10min
        )
        if tracked.get("state") != "complete":
            raise TimeoutError(f"FLUX+MiniMax job did not complete: {tracked}")
        monitor.set_phase("post_minimax")
        if stills_only:
            video_path = comfy_api.wait_for_image(pid, url=orch.comfy_url, timeout_s=120)
            print(f"  stills-only SaveImage -> {video_path}", flush=True)
        else:
            video_path = wait_for_video(pid, orch.comfy_url, timeout_s=60)

        # CRITICAL: free Comfy / FLUX / MiniMax VRAM before Qwen-VL.
        try:
            vram_controller.comfy_free_memory(
                unload_models=True, free_memory=True, update_state=True
            )
        except Exception:
            try:
                vram_controller.release_after_comfyui(reason="MiniMax MP4 saved; /free")
            except Exception:
                pass
        telemetry.update(monitor.summary())
        telemetry["video_path"] = str(video_path)
        LAST_RENDER_TELEMETRY = dict(telemetry)
        print(
            "[phase-telemetry] "
            f"flux_peak={telemetry.get('flux_vram_peak_mib')} "
            f"post_flux_idle={telemetry.get('post_flux_idle_vram_mib')} "
            f"minimax_peak={telemetry.get('minimax_vram_peak_mib')} "
            f"minimax_sec={telemetry.get('minimax_generation_seconds')}",
            flush=True,
        )
        return video_path
    finally:
        monitor.stop()


def generate_wan_clip(
    example: Any,
    pred: Any,
    hparams: dict[str, float],
    *,
    timeout_s: float = WAN_TIMEOUT_S,
    stills_only: bool = False,
) -> Path:
    """DEPRECATED alias — routes to MiniMax I2V path."""
    return generate_minimax_clip(
        example, pred, hparams, timeout_s=timeout_s, stills_only=bool(stills_only)
    )



def extract_eval_frames(video_path: Path, count: int = 3) -> list[Path]:
    from dspy_optimizer import extract_eval_frames as _extract

    return _extract(video_path, count=count)


def run_qwen_director_scores(frames: list[Path], prompt: str, system_prompt: str | None = None) -> dict:
    """Caption V4 on :11436. Caller must have released Comfy VRAM first.

    One retry when the answer arrives without the three scores
    (video_judge.scores_missing: a runaway past num_predict, or a JSON closed
    early), 2026-09-25k. Every call prefills cold (cache_prompt False,
    video_judge.JUDGE_CACHE_PROMPT, 2026-09-25o); otherwise the first call is
    unchanged from 2026-09-24ae.
    """
    import capabilities
    import media_tools
    import video_judge

    if not capabilities.qwen25_vl_runtime_available():
        import dspy_optimizer

        dspy_optimizer._ensure_owned_qwen25_vl_runtime()
    if not capabilities.qwen25_vl_runtime_available():
        raise TimeoutError("Qwen2.5-VL Caption V4 llama.cpp is not live on :11436")

    def _ask(user_prompt: str, *, num_predict: int, repeat_penalty: float, attempt: int) -> dict:
        raw = media_tools._run_vision_gpu(
            frames,
            user_prompt,
            capabilities.QWEN25_VL_MODEL,
            capabilities.QWEN25_VL_RUNTIME_HOST,
            instruction=(system_prompt or VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT),
            num_ctx=32768,
            num_predict=num_predict,
            json_mode=True,
            repeat_penalty=repeat_penalty,
            cache_prompt=video_judge.JUDGE_CACHE_PROMPT,
        )
        envelope = json.loads(raw)
        if not envelope.get("available", True):
            raise TimeoutError(str(envelope.get("reason") or "Qwen2.5-VL unavailable"))
        analysis = str(envelope.get("analysis") or "")
        try:
            dump = HERE / "runtime" / "dspy_opt" / "gvd_vlm_raw.jsonl"
            dump.parent.mkdir(parents=True, exist_ok=True)
            with dump.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "prompt": user_prompt[:500],
                    "analysis": analysis[:8000],
                    "model": envelope.get("model"),
                    "runtime": envelope.get("runtime"),
                    "attempt": attempt,
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        parsed = parse_video_director_scores(
            analysis,
            user_prompt,
            model=envelope.get("model") or EXACT_VLM_MODEL,
            runtime=envelope.get("runtime") or EXACT_VLM_RUNTIME,
        )
        parsed["raw"] = analysis[:4000]
        parsed["raw_chars"] = len(analysis)
        return parsed

    # Fault-checked judge writes one line per frame before the checks
    # (num_predict 1536). repeat_penalty off, deliberately. Measured
    # 2026-09-24 (CHANGELOG 24ae, results_v2c): with 1.08 the yes/no checklist
    # flips answers by token frequency, not evidence (good hallway walks
    # judged "different place"), and 3 of 79 outputs closed the JSON before
    # the scores (0 of 79 at 1.0). 1.0 reproduces the judge validated in
    # 24q/24r/24ac.
    parsed = _ask(prompt, num_predict=1536, repeat_penalty=1.0, attempt=1)
    if not video_judge.scores_missing(parsed):
        return parsed
    first = parsed
    print("  VLM judge: no scores on the first answer ("
          + "; ".join(str(r) for r in first.get("reasons") or [])[:160] + "); retrying once")
    parsed = _ask(video_judge.retry_user_prompt(prompt),
                  num_predict=video_judge.JUDGE_RETRY_NUM_PREDICT,
                  repeat_penalty=video_judge.JUDGE_RETRY_REPEAT_PENALTY, attempt=2)
    parsed["retry"] = {
        "attempt": 2,
        "recovered": not video_judge.scores_missing(parsed),
        "repeat_penalty": video_judge.JUDGE_RETRY_REPEAT_PENALTY,
        "num_predict": video_judge.JUDGE_RETRY_NUM_PREDICT,
        "first_reasons": list(first.get("reasons") or []),
        "first_raw_chars": first.get("raw_chars"),
        "first_raw_tail": (first.get("raw") or "")[-200:],
    }
    return parsed


def judge_rendered_clip(
    example: Any,
    video_path: Path,
    *,
    start_prompt: str,
    motion_prompt: str,
    pred: Any = None,
    extract: Callable[..., list[Path]] | None = None,
    judge: Callable[..., dict] | None = None,
    signals_fn: Callable[[Path], dict] | None = None,
    camera_fn: Callable[[Path, list[float]], list] | None = None,
) -> dict:
    """Score one rendered clip against the brief. Caller owns the VLM VRAM.

    Fault-checked judge (video_judge.py, CHANGELOG 2026-09-24 judge entry):
    the VLM sees the BRIEF (user_intent + constraints), not the student's own
    prompts, describes each frame, answers yes/no fault checks, then scores;
    failed checks and CPU-detected hard cuts / near-black frames cap the axes.
    Returns the parse_video_director_scores shape plus checks/caps/signals.
    """
    import video_judge

    extract = extract or extract_eval_frames
    judge = judge or run_qwen_director_scores
    literal = bool(
        _field(example, "bypass_director")
        or _field(example, "literal_prompt")
        or _field(pred, "bypass_director")
        or _field(pred, "literal_prompt")
    )
    literal_rule = str(_field(example, "vlm_literal_rule") or _field(pred, "vlm_literal_rule") or "")
    brief = (
        str(_field(example, "user_intent") or "").strip()
        or str(_field(example, "expected_scene") or "").strip()
        or f"{start_prompt} {motion_prompt}".strip()
    )
    constraints = str(_field(example, "constraints") or "")
    signals = None
    if Path(video_path).is_file():
        try:
            signals = (signals_fn or video_judge.detect_frame_faults)(Path(video_path))
        except Exception as exc:
            print(f"  frame-fault detector skipped: {type(exc).__name__}: {exc}")
    frames = extract(Path(video_path))
    frame_times = video_judge.frame_times_from_names(frames)
    # 2026-09-25l: camera motion over the gaps between the sampled frames, from
    # the measured estimator (camera_motion.py, 25c/e, unchanged), so a rigid
    # pan or tilt is marked in the user prompt the way dark_spans_s marks a
    # lighting dip (c038: a requested turn to the wall read as a cut). Canned
    # CPU signals (an injected signals_fn) get no measurement unless camera_fn
    # is injected too; production measures. A failed estimate is skipped.
    measure = camera_fn or (video_judge.measured_camera_moves if signals_fn is None else None)
    if measure is not None and isinstance(signals, dict) and frame_times:
        try:
            signals["camera_moves"] = measure(Path(video_path), frame_times)
        except Exception as exc:
            print(f"  camera-motion estimate skipped: {type(exc).__name__}: {exc}")
    system = video_judge.build_judge_system_prompt(literal_mode=literal, literal_rule=literal_rule or None)
    user = video_judge.build_judge_user_prompt(
        brief=brief, constraints=constraints,
        frame_times=frame_times,
        # 2026-09-25h: sampled frames inside a measured lighting dip are
        # marked so the VLM does not read them as a place change or a cut.
        signals=signals,
    )
    try:
        parsed = judge(frames, user, system_prompt=system)
    except TypeError:
        parsed = judge(frames, user)
    print("  VLM literal_mode=", literal)
    return video_judge.apply_fault_caps(parsed or {}, signals, brief, constraints)


def evaluate_live_candidate(
    example: Any,
    pred: Any,
    *,
    iteration: int | None = None,
    render_fn: Callable[..., Path] | None = None,
    vlm_fn: Callable[..., dict] | None = None,
    extract_fn: Callable[..., list[Path]] | None = None,
    check_fn: Callable[..., dict] | None = None,
    prepare_comfy: Callable[..., None] | None = None,
    release_comfy: Callable[..., None] | None = None,
    prepare_vlm: Callable[..., None] | None = None,
    release_vlm: Callable[..., None] | None = None,
    signals_fn: Callable[[Path], dict] | None = None,
    camera_fn: Callable[[Path, list[float]], list] | None = None,
) -> dict[str, Any]:
    """Live metric body. Inject callables in tests; production uses hardware."""
    if iteration is None:
        try:
            iteration = int(os.environ.get("GVD_CURRICULUM_ITERATION", "0"))
        except (TypeError, ValueError):
            iteration = 0
    hparams, hparam_notes = parse_director_hparams(pred)
    start_prompt = _director_start_prompt(example, pred)
    motion_prompt = _director_motion_prompt(pred)
    # VLM judges motion execution against video_motion_prompt; start_prompt is baseline.
    prompt = motion_prompt
    if not start_prompt or not motion_prompt:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error="start_prompt or video_prompt is empty; skipped GPU",
        )
    echoed = [name for name, text in (("start_prompt", start_prompt),
                                      ("video_prompt", motion_prompt))
              if instruction_echo(text)]
    if echoed:
        # "mechanical" -> _fail_penalty 0.02 (prompt/format failure).
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error=f"mechanical: instruction echo in {', '.join(echoed)}; skipped GPU",
        )
    if check_fn is None:
        # The gate reads only the prompts and the example, so it runs before
        # the GPU. Until 2026-09-25j it ran after the render: history row 265
        # (CHANGELOG 2026-09-25i) spent 757 s rendering a Backrooms clip and
        # then scored it 0.02 for a missing motion keyword without judging
        # it. Same error text and penalty as before; the row now carries
        # video_path None. Marker: skipped GPU (2026-09-25j).
        mech = mechanical_director_gate(example, pred)
        if mech.get("status") != "pass":
            return _fail_result(
                hparams=hparams, example=example, pred=pred,
                error=f"mechanical video check failed: {mech.get('reasons')}; skipped GPU",
            )

    prepare_comfy = prepare_comfy or vram_controller.prepare_for_comfyui
    release_comfy = release_comfy or vram_controller.release_after_comfyui
    prepare_vlm = prepare_vlm or vram_controller.prepare_for_vlm
    release_vlm = release_vlm or vram_controller.release_after_vlm
    render = render_fn or generate_minimax_clip
    extract = extract_fn or extract_eval_frames
    judge = vlm_fn or run_qwen_director_scores

    video_path: Path | None = None
    vram_trace: list[dict[str, Any]] = []
    try:
        prepare_comfy(reason="FLUX.1 + MiniMax I2V generation")
        vram_trace.append(_vram_snapshot("after_prepare_comfy"))
        video_path = render(example, pred, hparams)
        # Pull phase-tagged FLUX/MiniMax VRAM telemetry from the render call.
        try:
            phase_telem = dict(LAST_RENDER_TELEMETRY or {})
        except Exception:
            phase_telem = {}
        if phase_telem:
            vram_trace.append(
                {
                    "label": "phase_telemetry",
                    "phase": "summary",
                    **{k: phase_telem.get(k) for k in (
                        "flux_vram_peak_mib",
                        "post_flux_idle_vram_mib",
                        "minimax_vram_peak_mib",
                        "minimax_generation_seconds",
                        "sage_attention_minimax",
                        "sage_mode",
                    )},
                }
            )
        # /free already fired inside generate_minimax_clip after MP4 save.
        try:
            vram_controller.comfy_free_memory(
                unload_models=True, free_memory=True, update_state=True
            )
        except Exception:
            pass
        vram_trace.append(_vram_snapshot("after_minimax_and_free"))
    except TimeoutError as exc:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error=f"TimeoutError: {exc}",
            video_path=str(video_path) if video_path else None,
            vram_trace=vram_trace,
        )
    except Exception as exc:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error=f"{type(exc).__name__}: {exc}",
            video_path=str(video_path) if video_path else None,
            vram_trace=vram_trace,
        )
    finally:
        try:
            release_comfy(reason="FLUX+MiniMax complete; VRAM free for VLM")
        except Exception:
            pass
        vram_trace.append(_vram_snapshot("after_release_comfy"))

    if video_path is None:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error="FLUX+MiniMax produced no video path",
            vram_trace=vram_trace,
        )

    if check_fn is not None:
        # Injected post-render check (tests, or a future check that needs the
        # file). The built-in prompt gate already ran before the render.
        mech = check_fn(video_path, prompt, str(_field(example, "id") or ""))
        if mech.get("status") != "pass":
            return _fail_result(
                hparams=hparams, example=example, pred=pred,
                error=f"mechanical video check failed: {mech.get('reasons')}",
                video_path=str(video_path),
                vram_trace=vram_trace,
            )

    parsed = None
    try:
        prepare_vlm(reason="Qwen2.5-VL judge")
        vram_trace.append(_vram_snapshot("after_prepare_vlm"))
        parsed = judge_rendered_clip(
            example, Path(video_path),
            start_prompt=start_prompt, motion_prompt=motion_prompt, pred=pred,
            extract=extract, judge=judge, signals_fn=signals_fn, camera_fn=camera_fn,
        )
        _rat = ""
        if isinstance(parsed, dict):
            _rat = str(parsed.get("rationale") or parsed.get("raw") or parsed.get("reasons") or "")
        print("  VLM rationale:", _rat[:1500])
        vram_trace.append(_vram_snapshot("after_vlm"))
    except TimeoutError as exc:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error=f"VLM TimeoutError: {exc}",
            video_path=str(video_path),
            vram_trace=vram_trace,
        )
    except Exception as exc:
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error=f"VLM {type(exc).__name__}: {exc}",
            video_path=str(video_path),
            vram_trace=vram_trace,
        )
    finally:
        try:
            release_vlm(reason="Qwen2.5-VL complete")
        except Exception:
            pass
        vram_trace.append(_vram_snapshot("after_release_vlm"))

    if not parsed or parsed.get("status") != "pass" or not parsed.get("scores"):
        # 2026-09-25k: run_qwen_director_scores retried once if the scores
        # were missing; say so in the row. Same leading text as before.
        retried = "; after one retry" if (parsed or {}).get("retry") else ""
        return _fail_result(
            hparams=hparams, example=example, pred=pred,
            error=f"VLM scores rejected: {(parsed or {}).get('reasons')}{retried}",
            video_path=str(video_path),
            vram_trace=vram_trace,
        )

    curriculum = video_director_passes_curriculum(parsed, iteration, use_minimum=True)
    minimum = float(parsed["minimum"])
    mean = float(parsed["mean"])
    mipro_raw = (0.7 * minimum) + (0.3 * mean)
    mipro = _judged_scalar(minimum, mean)
    clip_id = str(_field(example, "id") or _field(example, "clip_id") or "")
    feedback = {
        "mock": False,
        "clip_id": clip_id,
        "category": str(_field(example, "category") or ""),
        "hparams": hparams,
        "step_count_int": int(round(hparams["step_count"])),
        "scores": parsed.get("scores"),
        "mean": parsed.get("mean"),
        "minimum": parsed.get("minimum"),
        "threshold": curriculum["threshold"],
        "iteration": curriculum["iteration"],
        "passes_curriculum": bool(curriculum["pass"]),
        "mipro": mipro,
        # Unfloored 0.7*min + 0.3*mean; differs from mipro only below JUDGED_SCORE_FLOOR.
        "mipro_raw": mipro_raw,
        "reasons": list(curriculum.get("reasons") or []),
        "hparam_warnings": hparam_notes,
        "start_prompt": start_prompt[:500],
        "video_prompt": motion_prompt[:500],
        "video_path": str(video_path),
        "vram_trace": vram_trace,
        # Fault-checked judge: scores above are capped; scores_vlm is what the
        # VLM wrote before caps (video_judge.apply_fault_caps).
        "scores_vlm": parsed.get("scores_vlm"),
        "checks": parsed.get("checks"),
        "caps": parsed.get("caps"),
        "signals": parsed.get("signals"),
        "vlm_raw": (parsed.get("raw") or "")[:4000],
        # 2026-09-25k: present when the first answer had no scores and the
        # retry produced this verdict (attempt, first_reasons, sampler).
        "judge_retry": parsed.get("retry"),
    }
    return {
        "mipro": mipro,
        "passes_curriculum": bool(curriculum["pass"]),
        "hparams": hparams,
        "scores": parsed.get("scores"),
        "parsed": parsed,
        "curriculum": curriculum,
        "feedback": json.dumps(feedback, ensure_ascii=True),
        "feedback_obj": feedback,
        "video_path": str(video_path),
    }


def generalized_video_metric(
    example,
    pred,
    trace=None,
    pred_name=None,
    pred_trace=None,
    **_kwargs,
) -> float:
    """MIPROv2 contract: scalar in [0, 1]. Live Wan + Qwen with VRAM flip-flop."""
    return _store(evaluate_live_candidate(example, pred))


generalized_video_metric.last_feedback = "{}"
generalized_video_metric.last_result = {}


def compile_director(
    *,
    auto: str | None = None,
    trainset=None,
    valset=None,
    save_path: Path | None = None,
    log_dir: Path | None = None,
    num_candidates: int = 1,
    num_trials: int = 1,
):
    """Live MIPROv2. Student LM is local Ollama; metric owns the 16 GB flip-flop."""
    dspy = gvd._dspy()
    if auto not in {None, "light", "medium", "heavy"}:
        raise ValueError("auto must be None, light, medium, or heavy")
    import dspy_optimizer

    task_lm, prompt_lm = dspy_optimizer.configure_video_lms()
    task_lm = harden_student_lm(task_lm)
    student = gvd.build_director_program()
    trainset = list(trainset or gvd.load_beta_trainset())
    valset = list(valset or trainset)
    log_dir = Path(log_dir or (HERE / "runtime" / "dspy_opt" / "gvd_live_logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    save_path = Path(save_path or DEFAULT_SAVE)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    if save_path.name == "temporal_physics_v1.json":
        raise RuntimeError("refusing to overwrite temporal_physics_v1.json")

    optimizer_kwargs: dict[str, Any] = {
        "metric": generalized_video_metric,
        "prompt_model": prompt_lm,
        "task_model": task_lm,
        "num_threads": 1,
        "max_bootstrapped_demos": 0,
        "max_labeled_demos": 0,
        "track_stats": True,
        "log_dir": str(log_dir),
        "seed": 9,
    }
    if auto is None:
        optimizer_kwargs["auto"] = None
        optimizer_kwargs["num_candidates"] = num_candidates
    else:
        optimizer_kwargs["auto"] = auto

    teleprompter = dspy.MIPROv2(**optimizer_kwargs)
    compile_kwargs: dict[str, Any] = {
        "trainset": trainset,
        "valset": valset,
        "minibatch": False,
        "program_aware_proposer": False,
        "data_aware_proposer": False,
        "tip_aware_proposer": False,
        "fewshot_aware_proposer": False,
        "max_bootstrapped_demos": 0,
        "max_labeled_demos": 0,
    }
    if auto is None:
        compile_kwargs["num_trials"] = num_trials
    compiled = teleprompter.compile(student, **compile_kwargs)
    compiled.save(str(save_path))
    return compiled, save_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 3 live MIPROv2: Generalized Video Director against Wan 2.1 "
            "and Qwen2.5-VL with VRAM flip-flop. Does not start ComfyUI."
        ),
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Run live MIPROv2. Refused without this flag. GPU work.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Alias for --compile (live MIPROv2).",
    )
    parser.add_argument("--auto", choices=("light", "medium", "heavy"), default=None)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--candidates", type=int, default=1)
    parser.add_argument("--save", type=Path, default=None)
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated Beta Set ids (temporary slice). Empty = full 16.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=0,
        help="Temporary slice size. 2 = GVD-B01 + GVD-D01.",
    )
    args = parser.parse_args(argv)
    if args.run:
        args.compile = True
    if args.rows and not args.ids.strip():
        if args.rows == 2:
            args.ids = "GVD-B01,GVD-D01"
        else:
            preferred = ["GVD-B01"] + [
                row["id"] for row in gvd.BETA_SET if row["id"] != "GVD-B01"
            ]
            args.ids = ",".join(preferred[: max(1, args.rows)])
    if not args.compile:
        parser.print_help()
        print(
            "\nRefusing to start GPU work without --compile.\n"
            "Live Wan + Qwen flip-flop (16 GB, exclusive ComfyUI on :8188):\n"
            "  python local_agent/dspy_orchestrator.py --compile\n"
            "Two-row VRAM proof:\n"
            "  python local_agent/dspy_orchestrator.py --compile "
            "--ids GVD-B01,GVD-D01 --trials 1 --candidates 1\n"
        )
        return 2
    trainset = None
    if args.ids.strip():
        wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
        rows = [row for row in gvd.BETA_SET if row["id"] in wanted]
        if len(rows) != len(wanted):
            found = {row["id"] for row in rows}
            raise RuntimeError(f"unknown Beta Set ids: {sorted(wanted - found)}")
        trainset = gvd.load_beta_trainset(rows)
    compiled, path = compile_director(
        auto=args.auto,
        trainset=trainset,
        save_path=args.save,
        num_candidates=args.candidates,
        num_trials=args.trials,
    )
    summary = {
        "saved": str(path),
        "optimizer": "mipro",
        "mock": False,
        "auto": args.auto,
        "trials": args.trials if args.auto is None else "auto",
        "trainset": len(trainset) if trainset is not None else len(gvd.BETA_SET),
        "ids": args.ids,
        "last_feedback": generalized_video_metric.last_feedback,
        "history_n": len(METRIC_HISTORY),
        "history": [row.get("feedback_obj") or json.loads(row["feedback"]) for row in METRIC_HISTORY],
    }
    print(json.dumps(summary, indent=2))
    try:
        import time as _time
        trace_dir = ROOT / "logs" / "run_traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        stamp = _time.strftime("%Y%m%dT%H%M%S")
        (trace_dir / f"gvd_live_{stamp}.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8",
        )
    except Exception as exc:
        print(f"trace write failed: {exc}", flush=True)
    return 0 if compiled is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
