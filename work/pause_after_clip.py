#!/usr/bin/env python3
"""Pause the Equal Shares single-pass queue immediately after one clip is valid.

This is intentionally non-destructive: it never edits the render manifest or a
raw. It waits for the renderer to commit a valid manifest entry, records that
raw's mechanical metadata, stops only the current queue-owner process tree, and
then releases the runtime owner record after the backend is confirmed gone.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
RUNTIME = PROJECT / "runtime"
MANIFEST = PROJECT / "single_pass_manifest.json"
OWNER = RUNTIME / "render_queue_owner.json"
LOG = RUNTIME / "pause_after_current_clip.log"
API = "http://127.0.0.1:8188"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def emit(message: str) -> None:
    line = f"[{now()}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
        capture_output=True,
    )
    return result.returncode == 0


def port_owner() -> int:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue | "
         "Select-Object -First 1 -ExpandProperty OwningProcess)"],
        capture_output=True, text=True,
    )
    try:
        return int(result.stdout.strip())
    except (TypeError, ValueError):
        return 0


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    return {
        "ok": bool(video and audio and path.stat().st_size > 0),
        "video": video,
        "audio": audio,
        "format": data.get("format", {}),
    }


def kill_tree(pid: int) -> dict:
    if pid <= 0:
        return {"pid": pid, "attempted": False}
    result = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True, text=True,
    )
    return {
        "pid": pid,
        "attempted": True,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def interrupt_backend() -> None:
    try:
        request = urllib.request.Request(
            f"{API}/interrupt", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(request, timeout=5).read()
    except Exception:
        pass


def atomic_write(path: Path, data: dict) -> None:
    temp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "00B"
    receipt = RUNTIME / f"pause_after_{target}_receipt.json"
    if receipt.exists():
        emit(f"Receipt already exists for {target}; nothing to do")
        return 0

    initial_owner = read_json(OWNER)
    initial_pid = int(initial_owner.get("pid") or 0)
    emit(f"Armed to pause after {target}; initial queue owner pid={initial_pid}")

    while True:
        manifest = read_json(MANIFEST)
        entry = manifest.get("clips", {}).get(target, {})
        raw_text = entry.get("comfy_source", "")
        raw = Path(raw_text) if raw_text else None
        if entry.get("status") == "valid" and raw and raw.is_file():
            mechanical = probe(raw)
            if mechanical.get("ok"):
                break
            emit(f"{target} is marked valid but raw probe has not passed: {mechanical}")
        time.sleep(0.25)

    owner_state = read_json(OWNER)
    owner_pid = int(owner_state.get("pid") or initial_pid or 0)
    emit(f"{target} is valid at {raw}; pausing queue owner pid={owner_pid}")

    # Stop during the renderer's post-manifest backend-cleanup window. If the
    # next backend started in the race, /T stops it as part of the same tree.
    interrupt_backend()
    tree_result = kill_tree(owner_pid)
    time.sleep(3)

    listener_pid = port_owner()
    listener_result = None
    if listener_pid and listener_pid != owner_pid:
        listener_result = kill_tree(listener_pid)
        time.sleep(3)

    owner_alive = process_exists(owner_pid)
    remaining_listener = port_owner()
    released = not owner_alive and remaining_listener == 0
    if released:
        atomic_write(OWNER, {
            "pid": 0,
            "released_at": now(),
            "purpose": f"paused after {target} for local-agent handoff",
        })

    final_entry = read_json(MANIFEST).get("clips", {}).get(target, {})
    record = {
        "target_clip": target,
        "paused_at": now(),
        "paused": released,
        "raw": str(raw),
        "raw_probe": mechanical,
        "manifest_entry": final_entry,
        "initial_owner": initial_owner,
        "tree_stop": tree_result,
        "listener_stop": listener_result,
        "owner_alive_after_stop": owner_alive,
        "port_8188_owner_after_stop": remaining_listener,
        "next_action": "Do not resume automatically. Continue with the local agent using LOCAL_AGENT_CONTINUATION_PROMPT_2026-08-13.md.",
    }
    atomic_write(receipt, record)
    emit(f"Pause result for {target}: paused={released}; receipt={receipt}")
    return 0 if released else 2


if __name__ == "__main__":
    raise SystemExit(main())
