#!/usr/bin/env python3
"""Print the authoritative Equal Shares state without modifying the project."""

from pathlib import Path
import json
import ctypes

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"

with (PROJECT / "story_config.json").open(encoding="utf-8-sig") as handle:
    config = json.load(handle)
with (PROJECT / "manifest.json").open(encoding="utf-8-sig") as handle:
    manifest = json.load(handle)
with (PROJECT / "runtime" / "render_queue_owner.json").open(encoding="utf-8-sig") as handle:
    owner = json.load(handle)

ordered_ids = [clip["id"] for clip in config["clips"]]
clip_states = manifest.get("clips", {})
valid = [clip_id for clip_id in ordered_ids if clip_states.get(clip_id, {}).get("status") == "valid"]
unresolved = [clip_id for clip_id in ordered_ids if clip_states.get(clip_id, {}).get("status") != "valid"]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
handle = ctypes.windll.kernel32.OpenProcess(
    PROCESS_QUERY_LIMITED_INFORMATION, False, int(owner.get("pid", 0))
)
owner_alive = bool(handle)
if handle:
    ctypes.windll.kernel32.CloseHandle(handle)

print(json.dumps({
    "authoritative_project": str(PROJECT),
    "configured_clips": len(ordered_ids),
    "valid_clips": len(valid),
    "unresolved_clips": len(unresolved),
    "first_unresolved_clip": unresolved[0] if unresolved else None,
    "render_queue_owner_pid": owner.get("pid"),
    "render_queue_owner_alive": owner_alive,
    "steps_single_anchor": config.get("steps_single_anchor"),
    "steps_dual_anchor": config.get("steps_dual_anchor"),
}, indent=2))
