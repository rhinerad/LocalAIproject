#!/usr/bin/env python3
"""Wait for the live Stage-1 queue, then preserve and retry Narrator audio.

This coordinator never interrupts a render and never accepts audio. It waits for
both existing owners to release, audits the versioned repair prompts, appends
one new attempt for every Narrator clip, and finally invokes the ordinary
nonblocking continuation once more so an earlier queue exit cannot strand an
unrendered story clip.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
PROJECT = ROOT / "outputs" / "equal_shares"
RUNTIME = PROJECT / "runtime"
OWNER = RUNTIME / "narrator_repair_owner.json"
AUDIO_OWNER = RUNTIME / "audio_generation_owner.json"
RENDER_OWNER = RUNTIME / "render_queue_owner.json"
LOG = RUNTIME / "narrator_repair_supervisor.log"
PROMPTS = PROJECT / "prompts_audio_pass_narrator_repair_v2"
NARRATOR_IDS = (
    "00A", "00B", "00C", "00D", "00D2", "00E", "00F", "00G",
    "00H", "00I", "00J", "00K", "00L", "00M", "00N", "00O",
)


def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recorded_owner(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8-sig")).get("pid", 0))
    except Exception:
        return 0


def port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8188), timeout=1):
            return True
    except OSError:
        return False


def claim() -> bool:
    pid = recorded_owner(OWNER)
    if pid and pid != os.getpid() and process_exists(pid):
        emit(f"Narrator repair coordinator already live at pid={pid}")
        return False
    OWNER.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "wait for Stage 1, then retry single-layer Narrator soundtracks",
    }, indent=2), encoding="utf-8")
    return True


def release() -> None:
    OWNER.write_text(json.dumps({
        "pid": 0,
        "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released",
    }, indent=2), encoding="utf-8")


def run(script: str, *args: str) -> None:
    command = [sys.executable, str(WORK / script), *args]
    emit("run " + script + (" " + " ".join(args) if args else ""))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"{script} exited {result.returncode}")


def wait_for_existing_stage1() -> None:
    last_notice = 0.0
    while True:
        # These owner records are released explicitly with pid=0. Trust their
        # positive values even when Windows denies os.kill(pid, 0); otherwise a
        # normal between-clip ComfyUI restart can look like an empty queue.
        audio_pid = recorded_owner(AUDIO_OWNER)
        render_pid = recorded_owner(RENDER_OWNER)
        if not audio_pid and not render_pid and not port_open():
            return
        now = time.monotonic()
        if now - last_notice >= 300:
            emit(
                f"waiting without interruption: audio_owner={audio_pid or 0}, "
                f"render_owner={render_pid or 0}, port_8188={port_open()}"
            )
            last_notice = now
        time.sleep(30)


def main() -> int:
    if not claim():
        return 3
    try:
        emit("queued; current Stage-1 generation will not be interrupted")
        wait_for_existing_stage1()
        emit("Stage-1 owners released; beginning versioned Narrator repair")
        run("build_narrator_repair_prompts.py")
        audit_args = [
            "--prompt-dir", str(PROMPTS), "--require-narrator-lock",
            "--json", str(RUNTIME / "narrator_repair_prompt_audit.json"),
        ]
        for cid in NARRATOR_IDS:
            audit_args += ["--clip", cid]
        run("audit_audio_prompts.py", *audit_args)

        render_args = [
            "--prompt-dir", str(PROMPTS),
            "--prompt-profile", "narrator_single_layer_repair_v2",
            "--rerender-pending", "--max-attempts", "1",
        ]
        for cid in NARRATOR_IDS:
            render_args += ["--clip", cid]
        run("render_audio_pass.py", *render_args)
        emit("Narrator repair attempts finished; checking for any stranded Stage-1 clips")
        run("continue_audio_generation_nonblocking.py")
        emit("Narrator repairs and the resumable Stage-1 continuation have finished")
        return 0
    except Exception as exc:
        emit(f"Narrator repair coordinator stopped on recoverable error: {exc}")
        return 2
    finally:
        release()


if __name__ == "__main__":
    raise SystemExit(main())
