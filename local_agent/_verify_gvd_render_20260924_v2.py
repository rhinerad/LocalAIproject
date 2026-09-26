#!/usr/bin/env python3
"""Retry of _verify_gvd_render_20260924.py on the sanctioned Rockernow backend.

v1 took ComfyUI through BackroomsWatch, whose --disable-all-custom-nodes
whitelist omits KJNodes, so the FLUX+MiniMax template's
PathchSageAttentionKJ nodes (40, 41) were rejected with HTTP 400 before any
render. The 2026-09-23 renders used restart_comfy_rockernow.ps1 ->
start_comfy_rockernow.bat (full Rockernow), so this does too.

That launcher has no thermal guard, so this wraps it per CLAUDE.md:
wait_before_render, an 82 C / 3-telemetry-failure watchdog that POSTs
/interrupt, stop the backend after the one render (verified Rockernow
main.py only), then wait_after_render. Holds batch_render_queue_owner.json.

Reuses v1's director output (same prompt). Does not call _store() or touch
any compiled artifact. Report: runtime/dspy_opt/verify_20260924/report_v2.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT), str(ROOT / "work")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import psutil
import thermal_guard

OUT = HERE / "runtime" / "dspy_opt" / "verify_20260924"
RESTART_PS1 = Path(r"A:\Users\rhine\.grok\long-running-background-tasks\restart_comfy_rockernow.ps1")
OWNER = ROOT / "batch_render_queue_owner.json"
URL = "http://127.0.0.1:8188"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def listener_pid() -> int | None:
    for c in psutil.net_connections(kind="tcp"):
        if c.status == "LISTEN" and c.laddr and c.laddr.port == 8188:
            return c.pid
    return None


def is_rockernow(proc: psutil.Process) -> bool:
    cmd = " ".join(proc.cmdline())
    return "Rockernow" in cmd and "main.py" in cmd


def api_up() -> bool:
    try:
        with urllib.request.urlopen(URL + "/system_stats", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def stop_rockernow() -> None:
    pid = listener_pid()
    if pid is None:
        return
    proc = psutil.Process(pid)
    if not is_rockernow(proc):
        raise RuntimeError(f"refusing to stop pid {pid}: not Rockernow ComfyUI main.py")
    targets = [proc] + proc.children(recursive=True)
    parent = proc.parent()
    if parent is not None and parent.name().lower() == "cmd.exe":
        targets.append(parent)  # the start_comfy_rockernow.bat shell
    for t in targets:
        try:
            t.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(targets, timeout=15)
    for t in alive:
        try:
            t.kill()
        except psutil.NoSuchProcess:
            pass
    deadline = time.monotonic() + 60
    while listener_pid() is not None:
        if time.monotonic() > deadline:
            raise RuntimeError("port 8188 still listening after stop")
        time.sleep(1)


class Watchdog(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.halt = threading.Event()
        self.trip: str | None = None
        self.peak_c = 0.0

    def run(self):
        failures = 0
        while not self.halt.wait(5):
            try:
                s = thermal_guard.check_running_ceiling(log, "GVD-D01-verify")
                self.peak_c = max(self.peak_c, float(s.temperature_c))
                failures = 0
            except thermal_guard.ThermalLimitExceeded as exc:
                self.interrupt(str(exc))
            except Exception as exc:
                failures += 1
                if failures >= 3:
                    self.interrupt(f"three consecutive telemetry failures: {exc}")

    def interrupt(self, reason: str):
        if self.trip:
            return
        self.trip = reason
        log(f"WATCHDOG: {reason}; POST /interrupt")
        try:
            req = urllib.request.Request(URL + "/interrupt", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass


def main() -> int:
    import dspy_orchestrator as orch
    import generalized_video_director as gvd

    v1 = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
    report: dict = {"clip_id": "GVD-D01", "started": time.time(), "pred": v1["pred"],
                    "minimax_h3_steps": orch.MINIMAX_H3_STEPS,
                    "instructions_chars": len(gvd.director_signature_class().instructions)}
    report_path = OUT / "report_v2.json"
    example = next(e for e in gvd.load_beta_trainset() if getattr(e, "id", None) == "GVD-D01")
    pred = SimpleNamespace(**v1["pred"])

    if listener_pid() is not None:
        raise SystemExit("8188 already listening; refusing (one backend, ever)")
    owner = json.loads(OWNER.read_text()) if OWNER.exists() else {}
    if owner.get("pid") and psutil.pid_exists(int(owner["pid"])):
        raise SystemExit(f"queue owned: {owner}")
    OWNER.write_text(json.dumps({"pid": os.getpid(), "purpose": "GVD verify render 2026-09-24",
                                 "started": time.time()}), encoding="utf-8")
    watchdog = Watchdog()
    started_backend = False
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
        log("Rockernow up; running evaluate_live_candidate")
        watchdog.start()
        result = orch.evaluate_live_candidate(example, pred)
        report["result"] = {k: v for k, v in result.items() if k != "feedback_obj"}
        if result.get("error"):
            report["error"] = result["error"]
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    finally:
        watchdog.halt.set()
        report["watchdog_trip"] = watchdog.trip
        report["peak_gpu_c"] = watchdog.peak_c
        if started_backend:
            try:
                stop_rockernow()
                log("Rockernow stopped")
            except Exception as exc:
                report["stop_error"] = f"{type(exc).__name__}: {exc}"
            try:
                thermal_guard.wait_after_render(log)
            except Exception as exc:
                report["cooldown_error"] = str(exc)
        OWNER.write_text(json.dumps({"pid": 0, "purpose": "released", "released_at": time.time()}),
                         encoding="utf-8")
        report["finished"] = time.time()
        report["elapsed_s"] = round(report["finished"] - report["started"], 1)
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log(f"report: {report_path}; error={report.get('error')}")
    return 1 if report.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
