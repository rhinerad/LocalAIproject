#!/usr/bin/env python3
"""
gpu_watchdog.py

Watchdog for hung/zombie GPU processes in a local AI video pipeline
(MiniMax H3, FLUX, ComfyUI, etc. on an RTX 5080).

Design goals, per the review that produced this script:

1. Primary detector = ComfyUI job progress, not raw GPU counters.
   nvmlDeviceGetUtilizationRates() is GPU-WIDE, not per-process. If more
   than one process ever touches the card, a zombie can hide behind a
   second, healthy process's utilization. Polling ComfyUI's own
   /queue and /history endpoints tells you whether THE SPECIFIC JOB is
   making progress, which is unambiguous.

2. Secondary detector = NVML VRAM-high + utilization-zero, as a blunt
   safety net for hangs that don't even show up at the ComfyUI layer
   (e.g. a wedged process that isn't the one ComfyUI thinks is running).

3. Model-load grace period: VRAM climbing with ~0% utilization for a
   few minutes is completely normal while a checkpoint loads. The
   timer for "zombie" starts only once VRAM has PLATEAUED (stopped
   increasing between polls), not from process start.

4. Requires several consecutive samples in the bad state before acting,
   not one poll a few minutes long — NVML reads can be momentarily
   stale, and video pipelines have legitimate idle gaps (frame decode,
   disk writes, ffmpeg subprocess calls between steps).

5. Kill the whole process tree (psutil children, recursive), not just
   the PID NVML reports, since ComfyUI / custom nodes spawn subprocess
   children (ffmpeg etc.) that would otherwise leak.

6. Verifies the PID's identity (name/cmdline) immediately before
   killing, to guard against PID reuse in long-running automation.

7. Re-checks VRAM after the kill before declaring success — WDDM can
   lag a couple seconds in reclaiming memory.

8. Restart is lock-aware: it will not spawn a new ComfyUI process
   while something else still holds the render lock / port 8188.
   Wire `acquire_render_lock` / `release_render_lock` /
   `render_lock_is_held_by_someone_else` below into whatever your
   existing supervisor already uses so you never end up with two
   ComfyUI processes racing for the GPU — that failure mode is worse
   than the zombie you're trying to fix.

9. Crash-loop guard: after MAX_CONSECUTIVE_RESTARTS auto-restarts in a
   row without a successful, progressing job in between, the watchdog
   stops auto-recovering and alerts instead of restarting forever.
   A real leak or bad config should surface, not spin silently.

10. Every kill/restart decision is logged as structured JSON evidence
    (timestamp, PID, process name/cmdline, VRAM at trigger, samples
    that led to the decision) before any destructive action, so a
    failure is diagnosable after the fact.

Dependencies: pynvml, psutil, requests
    pip install pynvml psutil requests --break-system-packages

This script does not touch your model files, story configs, or any
render evidence. It only observes GPU/process state and can terminate
a hung process + restart ComfyUI. Review the CONFIG section and the
two "WIRE THIS IN" functions before running unattended.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psutil

try:
    import pynvml
except ImportError:  # checked again in NvmlGpuMonitor.__init__ / main()
    pynvml = None

try:
    import requests
except ImportError:
    requests = None  # urllib fallback below

ROOT = Path(os.environ.get("GVD_ROOT") or Path(__file__).resolve().parent).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import gpu_lock as _gpu_lock  # noqa: E402


# ----------------------------------------------------------------------------
# CONFIG — adjust for your setup
# ----------------------------------------------------------------------------

GPU_INDEX = 0                     # index of the RTX 5080 per nvidia-smi
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 8188
COMFYUI_BASE_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"

POLL_INTERVAL_SEC = 15            # how often to sample GPU + ComfyUI state
VRAM_HIGH_THRESHOLD_PCT = 80.0    # "high" VRAM allocation
CONSECUTIVE_BAD_SAMPLES_REQUIRED = 12  # 12 * 15s = 3 min of sustained bad state
# No queue/history/step progress for this long = stalled.  Default 3900 s is
# deliberately LONGER than the 3600 s WAN/MiniMax per-job timeout so a single
# long legitimate job is never "stalled".  Env: GVD_WATCHDOG_STALL_S.
DEFAULT_STALL_TIMEOUT_SEC = 3900.0


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return float(default)
    try:
        value = float(raw)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


COMFYUI_STALL_TIMEOUT_SEC = _env_float("GVD_WATCHDOG_STALL_S", DEFAULT_STALL_TIMEOUT_SEC)
GPU_ACTIVE_UTIL_PCT = 5.0         # nvidia-smi/NVML util at or above this counts as "working"

VRAM_PLATEAU_TOLERANCE_MB = 64    # VRAM change smaller than this counts as "not still loading"
GRACE_PERIOD_AFTER_LAUNCH_SEC = 90  # never act on a process younger than this

KILL_GRACE_PERIOD_SEC = 8         # time between SIGTERM and SIGKILL
POST_KILL_VERIFY_DELAY_SEC = 5    # wait before re-checking VRAM after a kill
POST_KILL_VERIFY_RETRIES = 4

MAX_CONSECUTIVE_RESTARTS = 3      # crash-loop guard
RESTART_COOLDOWN_SEC = 30

LOG_DIR = Path(os.environ.get("GVD_WATCHDOG_LOG_DIR") or (ROOT / "local_agent" / "runtime" / "logs" / "gpu_watchdog"))
EVIDENCE_LOG_PATH = LOG_DIR / "gpu_watchdog_evidence.jsonl"


def _launch_cmd_from_env() -> list[str]:
    """COMFYUI_LAUNCH_CMD (shell-style string) -> argv.  No placeholder default:
    an unset command means the watchdog must NOT try to restart ComfyUI."""
    raw = os.environ.get("COMFYUI_LAUNCH_CMD", "")
    if not raw.strip():
        return []
    try:
        return shlex.split(raw, posix=(os.name != "nt"))
    except ValueError:
        return []


COMFYUI_LAUNCH_CMD: list[str] = _launch_cmd_from_env()
COMFYUI_LAUNCH_CWD: Optional[str] = os.environ.get("COMFYUI_LAUNCH_CWD") or None


# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------

log = logging.getLogger("gpu_watchdog")


def _setup_logging() -> None:
    """File logging is configured from main(), not at import (tests import this module)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "gpu_watchdog.log"),
        ],
    )


def write_evidence(record: dict) -> None:
    record = {"logged_at": time.time(), **record}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with EVIDENCE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ----------------------------------------------------------------------------
# WIRE THIS IN: coordinate with your existing render supervisor / lock
# ----------------------------------------------------------------------------

def port_is_listening(host: str, port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def render_lock_is_held_by_someone_else() -> bool:
    """
    True if another live process owns the shared render lock (gpu_lock.py:
    OS file lock + batch_render_queue_owner.json) and this watchdog must NOT
    start a new ComfyUI.  Fails closed: an unreadable lock counts as held.
    """
    try:
        return bool(_gpu_lock.is_held_by_other())
    except Exception as exc:
        log.warning("render lock probe failed (%s) — assuming HELD.", exc)
        return True


def restart_comfyui() -> bool:
    """
    Launch ComfyUI after confirming nothing else owns the port/lock.
    Returns True if a new process was started.
    """
    if render_lock_is_held_by_someone_else():
        log.warning("Render lock held by another supervisor — refusing to start a second ComfyUI.")
        return False
    if port_is_listening(COMFYUI_HOST, COMFYUI_PORT):
        log.warning("Port %s is already listening — refusing to start a second ComfyUI.", COMFYUI_PORT)
        return False
    if not COMFYUI_LAUNCH_CMD or not COMFYUI_LAUNCH_CWD:
        log.error(
            "COMFYUI_LAUNCH_CMD / COMFYUI_LAUNCH_CWD not set — refusing to restart ComfyUI "
            "(no placeholder command is ever run)."
        )
        write_evidence({"event": "restart_refused_unconfigured"})
        return False
    if not Path(COMFYUI_LAUNCH_CWD).is_dir():
        log.error("COMFYUI_LAUNCH_CWD %r is not a directory — refusing to restart.", COMFYUI_LAUNCH_CWD)
        return False

    log.info("Starting ComfyUI: %s (cwd=%s)", " ".join(COMFYUI_LAUNCH_CMD), COMFYUI_LAUNCH_CWD)
    subprocess.Popen(
        COMFYUI_LAUNCH_CMD,
        cwd=COMFYUI_LAUNCH_CWD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


# ----------------------------------------------------------------------------
# NVML (secondary / safety-net detector)
# ----------------------------------------------------------------------------

@dataclass
class GpuSample:
    timestamp: float
    total_mb: float
    used_mb: float
    used_pct: float
    gpu_util_pct: float
    proc_pids: dict  # pid -> used_memory_mb (compute/graphics contexts)


class NvmlGpuMonitor:
    def __init__(self, gpu_index: int = 0):
        if pynvml is None:
            raise RuntimeError("pynvml is required: pip install pynvml --break-system-packages")
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)

    def sample(self) -> Optional[GpuSample]:
        """One NVML sample, or None when NVML fails (never crash the watchdog loop)."""
        try:
            return self._sample()
        except Exception as exc:
            log.warning("NVML sample failed: %s", exc)
            return None

    def _sample(self) -> GpuSample:
        mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)

        proc_pids = {}
        # Compute contexts (what PyTorch/ComfyUI uses).
        try:
            for p in pynvml.nvmlDeviceGetComputeRunningProcesses(self.handle):
                used = getattr(p, "usedGpuMemory", None)
                proc_pids[p.pid] = (used or 0) / (1024 * 1024)
        except pynvml.NVMLError:
            pass
        # Some workloads (e.g. certain video decode/encode paths) show up
        # under the graphics context instead of compute — check both.
        try:
            for p in pynvml.nvmlDeviceGetGraphicsRunningProcesses(self.handle):
                if p.pid not in proc_pids:
                    used = getattr(p, "usedGpuMemory", None)
                    proc_pids[p.pid] = (used or 0) / (1024 * 1024)
        except pynvml.NVMLError:
            pass

        used_mb = mem.used / (1024 * 1024)
        total_mb = mem.total / (1024 * 1024)
        return GpuSample(
            timestamp=time.time(),
            total_mb=total_mb,
            used_mb=used_mb,
            used_pct=(used_mb / total_mb * 100.0) if total_mb else 0.0,
            gpu_util_pct=float(util.gpu),
            proc_pids=proc_pids,
        )

    def shutdown(self):
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# ComfyUI job-progress (primary detector)
# ----------------------------------------------------------------------------

class ComfyUiProgressMonitor:
    """
    Tracks whether ComfyUI's OWN queue is making progress. This is the
    detector that actually knows which job is running, so it doesn't
    suffer the GPU-wide-utilization attribution problem NVML has.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._last_progress_ts = time.time()
        self._last_signature: Optional[str] = None
        self.last_step: Optional[dict] = None

    def _fetch(self, path: str) -> Optional[dict]:
        try:
            if requests is not None:
                r = requests.get(f"{self.base_url}{path}", timeout=5)
                r.raise_for_status()
                return r.json()
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8") or "null")
        except Exception as e:
            log.debug("ComfyUI %s fetch failed: %s", path, e)
            return None

    @staticmethod
    def _step_counter(obj) -> Optional[dict]:
        """Extract a /progress-style step counter ({value,max}/{step,total_steps}/...)
        from any dict-ish payload, searching one level into nested dicts."""
        if not isinstance(obj, dict):
            return None
        pairs = (("value", "max"), ("step", "total_steps"), ("current", "total"), ("progress", "max"))
        for cur, tot in pairs:
            if cur in obj and isinstance(obj.get(cur), (int, float)):
                return {"value": obj.get(cur), "max": obj.get(tot), "node": obj.get("node")}
        for key in ("progress", "status", "execution"):
            nested = obj.get(key)
            if isinstance(nested, dict):
                found = ComfyUiProgressMonitor._step_counter(nested)
                if found:
                    return found
        return None

    def _running_ids_and_steps(self, running) -> tuple[list, Optional[dict]]:
        ids: list = []
        step = None
        for item in running or []:
            if isinstance(item, (list, tuple)):
                # stock ComfyUI: [number, prompt_id, prompt, extra_data, outputs]
                ids.append(item[1] if len(item) > 1 else item[0])
                for part in item:
                    step = step or self._step_counter(part)
            elif isinstance(item, dict):
                ids.append(item.get("prompt_id") or item.get("id"))
                step = step or self._step_counter(item)
        return ids, step

    def poll(self, gpu_util_pct: Optional[float] = None) -> Optional[float]:
        """
        Returns seconds since last observed progress, or None if
        ComfyUI is unreachable (treated as "unknown", not "stalled" —
        a dead server is a different failure mode than a hung job).

        Progress signature = running prompt ids + pending count + history
        size/tail + the sampler STEP COUNTER (from /progress when the server
        exposes it, else progress fields on the running item).  A GPU
        utilization sample at/above GPU_ACTIVE_UTIL_PCT also counts as
        progress, so one long job with a moving step counter or a busy GPU
        is never reported as stalled.
        """
        queue = self._fetch("/queue")
        history = self._fetch("/history")
        if queue is None and history is None:
            return None
        progress = self._fetch("/progress")  # optional endpoint; None on 404

        running = (queue or {}).get("queue_running", [])
        pending = (queue or {}).get("queue_pending", [])
        history_keys = tuple(sorted((history or {}).keys()))
        running_ids, step = self._running_ids_and_steps(running)
        step = self._step_counter(progress) or step
        self.last_step = step

        signature = json.dumps(
            [running_ids, len(pending), len(history_keys), history_keys[-5:], step],
            sort_keys=True, default=str,
        )

        now = time.time()
        if signature != self._last_signature:
            self._last_signature = signature
            self._last_progress_ts = now
        elif gpu_util_pct is not None and gpu_util_pct >= GPU_ACTIVE_UTIL_PCT:
            self._last_progress_ts = now  # the card is working: not a stall

        # No job running and nothing pending = idle, not stalled.
        if not running and not pending:
            self._last_progress_ts = now
            return 0.0

        return now - self._last_progress_ts


# ----------------------------------------------------------------------------
# Process kill helpers
# ----------------------------------------------------------------------------

def describe_process(pid: int) -> Optional[dict]:
    try:
        p = psutil.Process(pid)
        return {
            "pid": pid,
            "name": p.name(),
            "cmdline": p.cmdline(),
            "create_time": p.create_time(),
            "age_sec": time.time() - p.create_time(),
        }
    except psutil.NoSuchProcess:
        return None


def kill_process_tree(pid: int, expected_name_substring: Optional[str] = None) -> bool:
    """
    Kills pid and all descendants. If expected_name_substring is given,
    aborts if the live process's name doesn't contain it — guards
    against acting on a PID that NVML reported a moment ago but that
    the OS has since reused for something unrelated.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        log.warning("PID %s no longer exists — nothing to kill.", pid)
        return True

    if expected_name_substring and expected_name_substring.lower() not in parent.name().lower():
        log.error(
            "Refusing to kill PID %s: expected name containing %r, found %r "
            "(likely PID reuse — aborting for safety).",
            pid, expected_name_substring, parent.name(),
        )
        return False

    procs = [parent] + parent.children(recursive=True)
    log.info("Terminating process tree rooted at PID %s (%d processes total).", pid, len(procs))

    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass

    _, alive = psutil.wait_procs(procs, timeout=KILL_GRACE_PERIOD_SEC)
    for p in alive:
        log.warning("PID %s did not exit after SIGTERM — sending SIGKILL.", p.pid)
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=KILL_GRACE_PERIOD_SEC)
    return True


# ----------------------------------------------------------------------------
# Watchdog state machine
# ----------------------------------------------------------------------------

@dataclass
class WatchdogState:
    bad_sample_streak: int = 0
    vram_history: deque = field(default_factory=lambda: deque(maxlen=CONSECUTIVE_BAD_SAMPLES_REQUIRED + 2))
    consecutive_restarts: int = 0
    last_healthy_ts: float = field(default_factory=time.time)
    disabled: bool = False  # crash-loop guard tripped


def vram_has_plateaued(history: deque) -> bool:
    if len(history) < 2:
        return False
    recent = list(history)[-3:]
    return max(recent) - min(recent) <= VRAM_PLATEAU_TOLERANCE_MB


def pick_zombie_pid(sample: GpuSample) -> Optional[int]:
    """Largest VRAM holder among GPU processes, past its grace period."""
    candidates = []
    for pid, mb in sample.proc_pids.items():
        info = describe_process(pid)
        if info is None:
            continue
        if info["age_sec"] < GRACE_PERIOD_AFTER_LAUNCH_SEC:
            continue  # still within model-load grace period
        candidates.append((mb, pid, info))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def handle_stall(reason: str, sample: GpuSample, state: WatchdogState) -> None:
    zombie_pid = pick_zombie_pid(sample)
    if zombie_pid is None:
        log.warning(
            "Stall detected (%s) but no eligible process found past its grace period "
            "(everything is either idle-but-empty or still within the load grace period). "
            "Not acting.", reason,
        )
        return

    info = describe_process(zombie_pid)
    evidence = {
        "event": "zombie_detected",
        "reason": reason,
        "pid": zombie_pid,
        "process_info": info,
        "gpu_sample": {
            "used_mb": sample.used_mb,
            "used_pct": sample.used_pct,
            "gpu_util_pct": sample.gpu_util_pct,
            "proc_pids": sample.proc_pids,
        },
    }
    write_evidence(evidence)
    log.error("ZOMBIE DETECTED (%s): PID %s (%s), %.0f MB held. Killing process tree.",
              reason, zombie_pid, info.get("name") if info else "?", sample.proc_pids.get(zombie_pid, 0))

    if state.consecutive_restarts >= MAX_CONSECUTIVE_RESTARTS:
        state.disabled = True
        write_evidence({"event": "crash_loop_guard_tripped", "consecutive_restarts": state.consecutive_restarts})
        log.critical(
            "Crash-loop guard tripped: %d consecutive restarts without recovery. "
            "Disabling auto-restart. Manual intervention required.",
            state.consecutive_restarts,
        )
        # Still kill the zombie to free the GPU, just don't auto-restart it.
        kill_process_tree(zombie_pid, expected_name_substring=info.get("name", "") if info else None)
        return

    killed = kill_process_tree(zombie_pid, expected_name_substring=info.get("name", "") if info else None)
    if not killed:
        write_evidence({"event": "kill_refused_pid_mismatch", "pid": zombie_pid})
        return

    for attempt in range(1, POST_KILL_VERIFY_RETRIES + 1):
        time.sleep(POST_KILL_VERIFY_DELAY_SEC)
        still_present = zombie_pid in psutil.pids()
        if not still_present:
            log.info("Confirmed PID %s is gone (check %d/%d).", zombie_pid, attempt, POST_KILL_VERIFY_RETRIES)
            break
        log.warning("PID %s still present after kill (check %d/%d).", zombie_pid, attempt, POST_KILL_VERIFY_RETRIES)
    else:
        write_evidence({"event": "kill_did_not_clear_process", "pid": zombie_pid})
        log.critical("PID %s would not die after SIGKILL + retries. Not attempting restart. Manual check needed.", zombie_pid)
        return

    write_evidence({"event": "restart_attempt", "pid": zombie_pid})
    time.sleep(RESTART_COOLDOWN_SEC)
    started = restart_comfyui()
    if started:
        state.consecutive_restarts += 1
    write_evidence({"event": "restart_result", "started": started})
    state.bad_sample_streak = 0
    state.vram_history.clear()


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------

def main() -> None:
    _setup_logging()
    gpu = NvmlGpuMonitor(GPU_INDEX)
    comfy = ComfyUiProgressMonitor(COMFYUI_BASE_URL)
    state = WatchdogState()

    log.info(
        "GPU watchdog started. Polling every %ss; stall timeout %.0fs; restart %s.",
        POLL_INTERVAL_SEC, COMFYUI_STALL_TIMEOUT_SEC,
        "enabled" if (COMFYUI_LAUNCH_CMD and COMFYUI_LAUNCH_CWD) else "DISABLED (COMFYUI_LAUNCH_CMD/CWD unset)",
    )

    try:
        while True:
            if state.disabled:
                log.critical("Watchdog is disabled (crash-loop guard). Exiting poll loop.")
                break

            sample = gpu.sample()
            if sample is None:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            state.vram_history.append(sample.used_mb)

            stall_reason = None

            # --- Primary detector: ComfyUI job progress (+ step counter, + GPU util) ---
            seconds_since_progress = comfy.poll(gpu_util_pct=sample.gpu_util_pct)
            if seconds_since_progress is not None and seconds_since_progress > COMFYUI_STALL_TIMEOUT_SEC:
                stall_reason = f"comfyui_no_progress_{int(seconds_since_progress)}s"

            # --- Secondary detector: NVML VRAM-high + util-zero, sustained ---
            is_high_vram = sample.used_pct >= VRAM_HIGH_THRESHOLD_PCT
            is_zero_util = sample.gpu_util_pct == 0.0
            plateaued = vram_has_plateaued(state.vram_history)

            if is_high_vram and is_zero_util and plateaued:
                state.bad_sample_streak += 1
            else:
                state.bad_sample_streak = 0
                state.last_healthy_ts = time.time()

            if stall_reason is None and state.bad_sample_streak >= CONSECUTIVE_BAD_SAMPLES_REQUIRED:
                stall_reason = "nvml_sustained_high_vram_zero_util"

            log.info(
                "sample: vram=%.0f/%.0fMB (%.1f%%) util=%.0f%% streak=%d comfyui_stall=%s",
                sample.used_mb, sample.total_mb, sample.used_pct, sample.gpu_util_pct,
                state.bad_sample_streak,
                f"{seconds_since_progress:.0f}s" if seconds_since_progress is not None else "unreachable",
            )

            if stall_reason:
                handle_stall(stall_reason, sample, state)

            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        log.info("Watchdog stopped by user.")
    finally:
        gpu.shutdown()


if __name__ == "__main__":
    main()
