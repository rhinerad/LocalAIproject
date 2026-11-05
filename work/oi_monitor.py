#!/usr/bin/env python3
"""Read-only, one-minute status monitor for the Equal Shares handoff."""

from datetime import datetime
from pathlib import Path
import ctypes
import json
import time

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"


def owner_alive(pid):
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    alive = bool(handle)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
    return alive


def status():
    with (PROJECT / "story_config.json").open(encoding="utf-8-sig") as stream:
        config = json.load(stream)
    with (PROJECT / "manifest.json").open(encoding="utf-8-sig") as stream:
        manifest = json.load(stream)
    with (PROJECT / "runtime" / "render_queue_owner.json").open(encoding="utf-8-sig") as stream:
        owner = json.load(stream)
    ordered = [clip["id"] for clip in config["clips"]]
    states = manifest.get("clips", {})
    unresolved = [clip_id for clip_id in ordered if states.get(clip_id, {}).get("status") != "valid"]
    return len(ordered) - len(unresolved), len(ordered), unresolved, int(owner["pid"])


print("Read-only handoff monitor. No Turbo; 20 steps; Gemini is fallback-only.", flush=True)
while True:
    valid, total, unresolved, pid = status()
    alive = owner_alive(pid)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    next_clip = unresolved[0] if unresolved else None
    print(f"[{stamp}] clip={next_clip} stage=existing-supervisor owner_alive={alive} valid={valid}/{total} unresolved={len(unresolved)} next=monitor-and-validate", flush=True)
    if valid == total:
        print("All clips structurally valid; perform full visual audit and finalization per HANDOFF.md.", flush=True)
        raise SystemExit(0)
    if not alive:
        print("Owner stopped; check all backend/runner processes before any replacement.", flush=True)
        raise SystemExit(2)
    time.sleep(60)
