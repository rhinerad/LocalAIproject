#!/usr/bin/env python3
"""Live MIPROv2 recompile of the Generalized Video Director (2026-09-24).

Replaces models/dspy_compiled/generalized_video_director_mipro.json, which was
compiled 2026-09-17 against the one-line docstring (instructions lost
2026-09-16 by _patch_safety3.py). The previous file is backed up first as
generalized_video_director_mipro.json.bak_recompile_<ts>; path_b is untouched.

Same settings as dspy_orchestrator.py --compile defaults: all 16 Beta rows,
1 trial, 1 candidate, 0 demos.

Backend: sanctioned Rockernow (restart_comfy_rockernow.ps1), one listener, held
for the whole compile, stopped at the end. Safety per CLAUDE.md:
  - batch_render_queue_owner.json held for the run;
  - every render: thermal_guard.wait_before_render (start <=70 C) and
    wait_after_render (58 C) around generate_minimax_clip;
  - watchdog: >=82 C or 3 telemetry failures -> POST /interrupt;
  - XAI_API_KEY removed from the environment: proposer stays local.
Metric rows go to the normal gvd_live_metric_history.jsonl via _store().
Status: runtime/dspy_opt/recompile_20260924/status.json (rewritten per render).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

os.environ.pop("XAI_API_KEY", None)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

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

OUT = HERE / "runtime" / "dspy_opt" / "recompile_20260924"
STATUS = OUT / "status.json"


def main() -> int:
    import subprocess

    import dspy_orchestrator as orch
    import generalized_video_director as gvd

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    status: dict = {"started": time.time(), "renders": [], "state": "starting"}

    def save_status() -> None:
        status["updated"] = time.time()
        STATUS.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")

    sig = gvd.director_signature_class()
    assert sig.instructions == gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
    status["instructions_chars"] = len(sig.instructions)
    status["minimax_h3_steps"] = orch.MINIMAX_H3_STEPS

    save_path = orch.DEFAULT_SAVE
    if save_path.exists():
        backup = save_path.with_name(save_path.name + f".bak_recompile_{stamp}")
        shutil.copy2(save_path, backup)
        status["backup"] = str(backup)
    status["save_path"] = str(save_path)

    if listener_pid() is not None:
        raise SystemExit("8188 already listening; refusing (one backend, ever)")
    owner = json.loads(OWNER.read_text()) if OWNER.exists() else {}
    if owner.get("pid") and psutil.pid_exists(int(owner["pid"])):
        raise SystemExit(f"queue owned: {owner}")
    OWNER.write_text(json.dumps({"pid": os.getpid(), "purpose": "GVD director recompile 2026-09-24",
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
        log("Rockernow up; compile_director (16 rows, 1 trial, 1 candidate)")
        compiled, path = orch.compile_director(num_candidates=1, num_trials=1)
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
        OWNER.write_text(json.dumps({"pid": 0, "purpose": "released", "released_at": time.time()}),
                         encoding="utf-8")
        status["finished"] = time.time()
        save_status()
        log(f"status: {STATUS}; state={status['state']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
