#!/usr/bin/env python3
"""Live MIPROv2 validation pass of the Generalized Video Director (2026-09-25,
CHANGELOG 2026-09-25i, "Phase C").

First real, live optimization pass with every 2026-09-24/25 judge change
active together: fault-checked judge (24q), strict bar 0.80 (24ac), judged
floor 0.10 (24ad), repeat_penalty plumbing with the judge pinned at 1.0 (24ae),
the camera-rig check (25g) and the flicker fixes (25h). Not a production
recompile: it saves to its own artifact and leaves
models/dspy_compiled/generalized_video_director_mipro.json alone.

Slice: GVD-B01 (Backrooms: the 0.80 bar and the flicker rules), GVD-D01 and
GVD-D02 (drone: the rig check), GVD-M03 (24o's false pass). 1 candidate,
1 trial = baseline pass + one trial pass, same as `--compile` defaults.
GVD_CURRICULUM_ITERATION=6 so the run is under the strict 0.80 bar
(media_accuracy_gate._CURRICULUM_STEPS, iteration 6+).

Safety, as in _recompile_gvd_director_20260924.py (24o):
  - refuses if 8188 is listening or the queue owner is live; holds the owner;
  - sanctioned Rockernow backend via restart_comfy_rockernow.ps1, stopped at
    the end; one listener, ever;
  - thermal_guard.wait_before_render (<= 70 C to start) and wait_after_render
    (<= 58 C) around every render; watchdog: >= 82 C or 3 telemetry failures
    -> POST /interrupt;
  - XAI_API_KEY removed: proposer stays local.
Metric rows go to the normal gvd_live_metric_history.jsonl via _store()
(rows 262+). Status: runtime/dspy_opt/phaseC_20260925/status.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

os.environ.pop("XAI_API_KEY", None)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
# Strict bar: iteration 6+ is 0.80 (24ac). Read by evaluate_live_candidate.
os.environ["GVD_CURRICULUM_ITERATION"] = "6"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT), str(ROOT / "work")):
    if p not in sys.path:
        sys.path.insert(0, p)

import psutil
import thermal_guard
from _verify_gvd_render_20260924_v2 import (
    OWNER, RESTART_PS1, Watchdog, api_up, listener_pid, log, stop_rockernow,
)

SLICE_IDS = ("GVD-B01", "GVD-D01", "GVD-D02", "GVD-M03")
OUT = HERE / "runtime" / "dspy_opt" / "phaseC_20260925"
STATUS = OUT / "status.json"
SAVE = ROOT / "models" / "dspy_compiled" / "generalized_video_director_mipro_phaseC_20260925.json"
HISTORY = HERE / "runtime" / "dspy_opt" / "gvd_live_metric_history.jsonl"


def _history_rows() -> int:
    if not HISTORY.exists():
        return 0
    return sum(1 for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> int:
    import subprocess

    import dspy_orchestrator as orch
    import generalized_video_director as gvd
    import media_accuracy_gate as mag
    import video_judge

    OUT.mkdir(parents=True, exist_ok=True)
    status: dict = {"started": time.time(), "renders": [], "state": "starting",
                    "slice": list(SLICE_IDS), "curriculum_iteration": 6,
                    "curriculum_threshold": mag.curriculum_threshold(6),
                    "judged_score_floor": orch.JUDGED_SCORE_FLOOR,
                    "check_keys": list(video_judge.CHECK_KEYS),
                    "history_rows_before": _history_rows(),
                    "save_path": str(SAVE)}
    assert status["curriculum_threshold"] == 0.80, status["curriculum_threshold"]
    assert "camera_or_operator_visible" in video_judge.CHECK_KEYS
    assert hasattr(video_judge, "_dip_returns_same_picture"), "Phase B detector rule missing"

    def save_status() -> None:
        status["updated"] = time.time()
        STATUS.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")

    sig = gvd.director_signature_class()
    assert sig.instructions == gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
    status["instructions_chars"] = len(sig.instructions)
    status["minimax_h3_steps"] = orch.MINIMAX_H3_STEPS
    if SAVE.exists():
        raise SystemExit(f"{SAVE} exists; refusing to overwrite a previous Phase C artifact")

    if listener_pid() is not None:
        raise SystemExit("8188 already listening; refusing (one backend, ever)")
    owner = json.loads(OWNER.read_text()) if OWNER.exists() else {}
    if owner.get("pid") and psutil.pid_exists(int(owner["pid"])):
        raise SystemExit(f"queue owned: {owner}")
    OWNER.write_text(json.dumps({"pid": os.getpid(), "purpose": "GVD live MIPRO validation 2026-09-25 (Phase C)",
                                 "started": time.time()}), encoding="utf-8")

    real_render = orch.generate_minimax_clip

    def guarded_render(example, pred, hparams, **kwargs):
        clip = str(getattr(example, "id", "") or "")
        entry = {"clip_id": clip, "wait_start": time.time()}
        status["renders"].append(entry)
        status["state"] = f"cooling before {clip}"
        save_status()
        thermal_guard.wait_before_render(log)
        if watchdog.trip:
            raise RuntimeError(f"watchdog tripped earlier: {watchdog.trip}")
        entry["render_start"] = time.time()
        status["state"] = f"rendering {clip}"
        save_status()
        try:
            path = real_render(example, pred, hparams, **kwargs)
            entry["video_path"] = str(path)
            return path
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            entry["render_end"] = time.time()
            entry["peak_gpu_c"] = watchdog.peak_c
            status["state"] = f"post-render cooldown {clip}"
            save_status()
            thermal_guard.wait_after_render(log)

    orch.generate_minimax_clip = guarded_render
    watchdog = Watchdog()
    started_backend = False
    code = 1
    try:
        thermal_guard.wait_before_render(log)
        log("starting Rockernow via restart_comfy_rockernow.ps1")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(RESTART_PS1)], check=True, timeout=120)
        started_backend = True
        deadline = time.monotonic() + 600
        while not api_up():
            if time.monotonic() > deadline:
                raise TimeoutError("Rockernow /system_stats not up after 600 s")
            time.sleep(3)
        watchdog.start()
        status["state"] = "compiling"
        save_status()
        rows = [row for row in gvd.BETA_SET if row["id"] in SLICE_IDS]
        assert len(rows) == len(SLICE_IDS), [r["id"] for r in rows]
        trainset = gvd.load_beta_trainset(rows)
        log(f"Rockernow up; compile_director ({len(trainset)} rows, 1 trial, 1 candidate, iteration 6 / bar 0.80)")
        compiled, path = orch.compile_director(trainset=trainset, save_path=SAVE,
                                               num_candidates=1, num_trials=1)
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        status["saved_instructions"] = saved["director.predict"]["signature"]["instructions"]
        status["state"] = "done"
        code = 0
    except Exception as exc:
        status["state"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["traceback"] = traceback.format_exc()
        log("FAILED: " + status["error"])
    finally:
        watchdog.halt.set()
        status["watchdog_trip"] = watchdog.trip
        status["peak_gpu_c"] = watchdog.peak_c
        if started_backend:
            try:
                stop_rockernow()
                log("Rockernow stopped")
            except Exception as exc:
                status["stop_error"] = f"{type(exc).__name__}: {exc}"
            try:
                thermal_guard.wait_after_render(log)
            except Exception as exc:
                status["cooldown_error"] = str(exc)
        OWNER.write_text(json.dumps({"pid": 0, "purpose": "released (Phase C live MIPRO validation)",
                                     "released_at": time.time()}), encoding="utf-8")
        status["history_rows_after"] = _history_rows()
        status["finished"] = time.time()
        save_status()
        log(f"status: {STATUS}; state={status['state']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
