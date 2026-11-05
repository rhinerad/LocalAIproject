#!/usr/bin/env python3
"""Persistent supervisor for the Equal Shares ComfyUI render queue."""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG = PROJECT / "story_config.json"
RUNNER = ROOT / "outputs" / "minimax_story_runner.py"
LOG = PROJECT / "runtime" / "render_supervisor.log"
RUNNER_LOG = PROJECT / "runtime" / "story_runner.log"
OWNER_LOCK = PROJECT / "runtime" / "render_queue_owner.json"
COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
COMFY_PYTHON = COMFY_ROOT / ".venv" / "Scripts" / "python.exe"
MODEL_PATHS = PROJECT / "runtime" / "minimax_model_paths.yaml"


def emit(message):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def process_exists(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ],
        capture_output=True,
    )
    return result.returncode == 0


def claim_render_queue():
    if OWNER_LOCK.exists():
        try:
            owner = json.loads(OWNER_LOCK.read_text(encoding="utf-8-sig"))
            owner_pid = int(owner.get("pid", 0))
        except Exception:
            owner_pid = 0
        if owner_pid != os.getpid() and process_exists(owner_pid):
            print(
                f"Render queue already owned by live supervisor pid={owner_pid}; "
                "monitor the existing queue instead of starting a duplicate.",
                flush=True,
            )
            return False
    OWNER_LOCK.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "claimed_at": datetime.now().isoformat(timespec="seconds"),
                "purpose": "single owner for Equal Shares ComfyUI generation",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return True


def ready():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=5):
            return True
    except Exception:
        return False


def start_comfy():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout = (PROJECT / "runtime" / f"comfy_supervised_{stamp}.stdout.log").open("ab")
    stderr = (PROJECT / "runtime" / f"comfy_supervised_{stamp}.stderr.log").open("ab")
    args = [
        str(COMFY_PYTHON), "main.py", "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch",
        "--extra-model-paths-config", str(MODEL_PATHS),
        "--output-directory", r"A:\Users\rhine\ComfyUI-Shared\output",
        "--input-directory", r"A:\Users\rhine\ComfyUI-Shared\input",
        "--user-directory", str(COMFY_ROOT / "user"),
        "--enable-manager",
        "--use-sage-attention",
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(args, cwd=COMFY_ROOT, stdout=stdout, stderr=stderr, creationflags=flags, env=env)
    emit(f"Started ComfyUI pid={process.pid}")
    for _ in range(90):
        if ready():
            emit("ComfyUI API ready")
            return
        if process.poll() is not None:
            raise RuntimeError(f"ComfyUI exited during startup with code {process.returncode}")
        time.sleep(5)
    raise TimeoutError("ComfyUI did not become ready within 450 seconds")


def stop_comfy():
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8188/interrupt",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=5).read()
    except Exception:
        pass
    time.sleep(2)
    command = (
        "Get-Process | Where-Object { $_.ProcessName -eq 'python' -and "
        "$_.Path -like 'A:\\Users\\rhine\\ComfyUI-Installs\\Rockernow\\*' } | Stop-Process -Force"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True)
    for _ in range(20):
        if not ready():
            emit("ComfyUI stopped; GPU state cleared")
            return
        time.sleep(1)
    raise RuntimeError("ComfyUI did not stop cleanly")


def progress():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest_path = PROJECT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"clips": {}}
    valid_ids = {
        clip["id"] for clip in config["clips"]
        if manifest.get("clips", {}).get(clip["id"], {}).get("status") == "valid"
        and Path(manifest["clips"][clip["id"]].get("clip", "")).is_file()
    }
    next_id = next((clip["id"] for clip in config["clips"] if clip["id"] not in valid_ids), None)
    return len(valid_ids), len(config["clips"]), next_id


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not claim_render_queue():
        return 3
    consecutive_failures = 0
    while True:
        valid, total, next_id = progress()
        emit(f"Progress {valid}/{total} valid clips; next={next_id}")
        if valid == total:
            emit("All clips valid")
            return 0
        # A clean backend per clip is slower but prevents the Qwen/H3 CUDA
        # allocator from aborting on a later prompt after a successful render.
        if ready():
            stop_comfy()
        start_comfy()
        with RUNNER_LOG.open("ab") as runner_log:
            result = subprocess.run(
                [sys.executable, str(RUNNER), str(CONFIG), "--resume", "--only", next_id],
                cwd=ROOT,
                stdout=runner_log,
                stderr=subprocess.STDOUT,
            )
        valid_after, _, next_after = progress()
        if result.returncode == 0:
            consecutive_failures = 0
        elif valid_after > valid:
            consecutive_failures = 0
            emit(
                f"Runner/backend reset after forward progress: "
                f"{valid}->{valid_after} valid clips; next={next_after}"
            )
        else:
            consecutive_failures += 1
            emit(f"Runner exited {result.returncode}; resume pass {consecutive_failures}")
        if ready():
            stop_comfy()
        if consecutive_failures >= 20:
            raise RuntimeError("Twenty consecutive resume passes failed; manual diagnosis required")
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
