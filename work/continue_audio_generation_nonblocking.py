#!/usr/bin/env python3
"""Continue Stage-1 generation while keeping ear review as a later gate.

This supervisor never accepts audio. It uses pending actual-story bootstrap
soundtracks only as explicitly provisional voice references, renders any
remaining bootstrap dependency, rebuilds the references, and then renders every
still-unrendered Stage-1 soundtrack. Existing candidates and manifests are
preserved. Stage 2 remains blocked by render_picture_pass.py until 124 accepted
full WAVs exist.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
PROJECT = ROOT / "outputs" / "equal_shares"
RUNTIME = PROJECT / "runtime"
OWNER = RUNTIME / "audio_generation_owner.json"
LOG = RUNTIME / "audio_nonblocking_supervisor.log"
BOOTSTRAP_PLAN = PROJECT / "story_voice_bootstrap_plan.json"


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


def claim() -> bool:
    if OWNER.is_file():
        try:
            old = json.loads(OWNER.read_text(encoding="utf-8-sig"))
            pid = int(old.get("pid", 0))
        except Exception:
            pid = 0
        if pid != os.getpid() and process_exists(pid):
            emit(f"nonblocking audio supervisor already live at pid={pid}; not duplicating")
            return False
    OWNER.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "continue all Stage-1 generations with provisional story voice refs",
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


def build_provisional_refs() -> None:
    run(
        "build_voice_reference_map.py", "--extract", "--verbose",
        "--allow-provisional-story-bootstraps",
    )
    run("build_audio_pass_prompts.py")


def main() -> int:
    if not claim():
        return 3
    try:
        emit(
            "ear review is nonblocking for Stage-1 generation; pending audio stays "
            "unaccepted and Stage 2 stays closed"
        )
        build_provisional_refs()
        plan = json.loads(BOOTSTRAP_PLAN.read_text(encoding="utf-8-sig"))
        if plan.get("clips"):
            emit(f"rendering {len(plan['clips'])} remaining actual-story voice bootstrap clip(s)")
            run("render_audio_pass.py", "--bootstrap-missing-voices")
            build_provisional_refs()
        else:
            emit("no remaining voice-bootstrap clip before the full Stage-1 queue")
        emit("starting all still-unrendered Stage-1 soundtrack candidates")
        run("render_audio_pass.py")
        emit("all currently generatable Stage-1 soundtrack candidates have been attempted")
        return 0
    except Exception as error:
        emit(f"supervisor stopped on recoverable error: {error}")
        return 2
    finally:
        release()


if __name__ == "__main__":
    raise SystemExit(main())
