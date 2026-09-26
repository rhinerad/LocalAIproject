#!/usr/bin/env python3
"""Boot Rockernow ComfyUI on :8188, then run live_vram_test.py.

Uses the Rockernow venv (not system Python) so torch/CUDA resolve.
Does not kill ComfyUI on exit. Extra model paths point at ComfyUI-Shared.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
COMFY_PYTHON = COMFY_ROOT / ".venv" / "Scripts" / "python.exe"
COMFY_MAIN = COMFY_ROOT / "main.py"
EXTRA_PATHS = ROOT / "work" / "runtime" / "image_render_model_paths.yaml"
COMFY_URL = "http://127.0.0.1:8188"
BOOT_TIMEOUT_S = 600.0
POLL_S = 3.0
LOG_DIR = ROOT / "logs" / "run_traces"


def _ping() -> dict | None:
    try:
        with urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=3) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def boot_comfy() -> subprocess.Popen:
    if not COMFY_PYTHON.is_file():
        raise SystemExit(f"Rockernow venv python missing: {COMFY_PYTHON}")
    if not COMFY_MAIN.is_file():
        raise SystemExit(f"ComfyUI main.py missing: {COMFY_MAIN}")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = LOG_DIR / f"comfy_boot_{stamp}.log"
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    cmd = [
        str(COMFY_PYTHON),
        str(COMFY_MAIN),
        "--listen", "127.0.0.1",
        "--port", "8188",
    ]
    if EXTRA_PATHS.is_file():
        cmd.extend(["--extra-model-paths-config", str(EXTRA_PATHS)])
    print(f"starting ComfyUI: {' '.join(cmd)}")
    print(f"comfy log: {log_path}")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        cmd,
        cwd=str(COMFY_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    print(f"comfy pid={proc.pid}")
    return proc


def stop_rockernow_comfy() -> None:
    """Stop only Rockernow ComfyUI main.py processes we use on :8188."""
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'Rockernow\\\\ComfyUI\\\\main.py' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, timeout=30,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if _ping() is None:
            return
        time.sleep(1)


def restart_comfy() -> subprocess.Popen:
    """Hard restart so Phase 3 CLIP load does not inherit SDXL RAM pressure."""
    print("restarting Rockernow ComfyUI for a clean CLIP load")
    stop_rockernow_comfy()
    time.sleep(2)
    proc = boot_comfy()
    wait_ready(proc)
    return proc


def wait_ready(proc: subprocess.Popen) -> dict:
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(
                f"ComfyUI exited before becoming ready (code={proc.returncode}). "
                "See logs/run_traces/comfy_boot_*.log"
            )
        stats = _ping()
        if stats is not None:
            print("ComfyUI /system_stats OK")
            return stats
        print("waiting for http://127.0.0.1:8188/system_stats ...")
        time.sleep(POLL_S)
    raise SystemExit(f"ComfyUI did not answer /system_stats within {BOOT_TIMEOUT_S:.0f}s")


def run_live_test() -> int:
    test = ROOT / "live_vram_test.py"
    print(f"executing {test}")
    return subprocess.call(
        [sys.executable, str(test)],
        cwd=str(ROOT),
    )


def latest_vram_report() -> dict | None:
    files = sorted(LOG_DIR.glob("live_vram_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    already = _ping()
    proc = None
    if already is not None:
        print("ComfyUI already answering on :8188 — skipping boot")
    else:
        proc = boot_comfy()
        wait_ready(proc)
    code = run_live_test()
    report = latest_vram_report()
    if report:
        print("--- live_vram_test report json ---")
        print(json.dumps({
            "fallback": report.get("fallback"),
            "peaks_mib": report.get("peaks_mib"),
            "vram_after_image_free_mib": report.get("vram_after_image_free_mib"),
            "files": report.get("files"),
            "tripped": report.get("tripped"),
        }, indent=2))
    if proc is not None:
        print(f"ComfyUI still running as pid={proc.pid} (not killed)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
