"""Bounded direct main.py startup probe; no graph submission or model load."""
import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import image_render as ir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--disable-api-nodes", action="store_true")
    ap.add_argument("--no-stacks", action="store_true")
    ap.add_argument("--writable-cache", action="store_true")
    args = ap.parse_args()
    ir.preflight_execute()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = ir.ROOT / "work" / "runtime" / "startup_diagnostics" / stamp
    dest.mkdir(parents=True, exist_ok=False)
    cmd = [str(ir.COMFY_PYTHON), "-u", "main.py", "--listen", "127.0.0.1",
           "--port", "8188", "--disable-auto-launch", "--disable-all-custom-nodes",
           "--user-directory", str(dest / "user"), "--temp-directory", str(dest / "temp"),
           "--input-directory", str(dest / "input"), "--output-directory", str(dest / "output")]
    for name in ("user", "temp", "input", "output"):
        (dest / name).mkdir()
    if args.cpu:
        cmd.append("--cpu")
    if args.disable_api_nodes:
        cmd.append("--disable-api-nodes")
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
               OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4")
    if args.writable_cache:
        cache = ir.ROOT / "work" / "runtime" / "numba_cache"
        cache.mkdir(parents=True, exist_ok=True)
        env["NUMBA_CACHE_DIR"] = str(cache)
    if not args.no_stacks:
        env["LOCAL_AGENT_STARTUP_STACKS"] = "1"
        env["PYTHONPATH"] = str(Path(__file__).parent / "startup_probe_support")
    start = time.monotonic()
    report = {"command": cmd, "cpu": args.cpu, "ready": False, "log": str(dest / "startup.log")}
    with (dest / "startup.log").open("wb") as log:
        proc = subprocess.Popen(cmd, cwd=ir.COMFY_ROOT, stdout=log, stderr=log, env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        report["pid"] = proc.pid
        print(json.dumps(report), flush=True)
        try:
            while time.monotonic() - start < args.seconds:
                if proc.poll() is not None:
                    break
                ir.thermal_guard.check_running_ceiling(print, "startup-probe")
                with socket.socket() as sock:
                    sock.settimeout(0.2)
                    if sock.connect_ex(("127.0.0.1", 8188)) == 0:
                        report["ready"] = True
                        break
                time.sleep(2)
        finally:
            report["elapsed_seconds"] = round(time.monotonic() - start, 3)
            report["exit_before_cleanup"] = proc.poll()
            if proc.poll() is None:
                cleanup = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                         capture_output=True, timeout=20)
                report["cleanup_output"] = (cleanup.stdout + cleanup.stderr).decode(errors="replace")
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    report["cleanup_error"] = "Owned child remains alive; do not launch another backend."
            report["exit_after_cleanup"] = proc.poll()
    report["port_released"] = not ir._port_open()
    (dest / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
