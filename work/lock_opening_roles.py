#!/usr/bin/env python3
"""Lock the corrected three-person staging for the monochrome opening."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "outputs" / "equal_shares" / "story_config.json"

ROLE_LOCK = (
    "OPENING ROLE LOCK: The receptionist is the only woman and remains standing or seated at her "
    "work position entirely behind the rectangular reception window for the whole shot. She never "
    "enters the public waiting room, never approaches the chair, never sits in the public chair, and "
    "neither visitor offers her the chair. Only Male Visitor One and Male Visitor Two enter through "
    "the separate open doorway at screen-right, remain on the public side, and perform every chair "
    "offer, refusal, sitting, standing, and anxious reaction. There are exactly these two male visitors "
    "and one female receptionist; do not swap their roles or positions. "
)

NEGATIVE_LOCK = (
    ", receptionist in public room, receptionist sitting in waiting chair, woman offered chair, "
    "woman participating in chair exchange, woman leaving reception window, male receptionist, "
    "visitor behind reception window, visitor behind counter, role swap, gender swap"
)

config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
config.setdefault("audio_policy", {})["h3_speech"] = "postproduction_only"
config["audio_policy"]["dialogue_source"] = (
    "one consistent post-production voice set; never use generated H3 speech in the final mix"
)
changed = []
for clip in config["clips"]:
    clip_id = str(clip.get("id", ""))
    if not clip_id.startswith("00") or clip_id > "00I":
        continue
    prompt = clip["prompt"]
    if ROLE_LOCK not in prompt:
        marker = "Scene and performance:"
        clip["prompt"] = prompt.replace(marker, ROLE_LOCK + marker, 1)
    if "receptionist in public room" not in clip.get("negative_prompt", ""):
        clip["negative_prompt"] = clip.get("negative_prompt", "") + NEGATIVE_LOCK
    clip["visual_acceptance"] = {
        "receptionist": "only woman; stays entirely behind reception window; never uses or is offered chair",
        "visitors": "exactly two men on public side; only participants in chair exchange",
        "architecture": "one public chair at screen-left; separate open entrance at screen-right; no glass gate or new barrier",
        "reject_on_violation": True,
    }
    if clip_id == "00D":
        # The user approved the picture from the 12-second dual-anchor proof.
        # Force the closing anchor even though it exceeds the usual 8s limit.
        clip["duration"] = 12.0
        clip["frames"] = 294
        clip["force_last_frame"] = True
        clip["dialogue_timing"] = [
            {"start": 1.0, "end": 5.0, "line": clip["dialogue_timing"][0]["line"]}
        ]
    elif clip_id in {"00D2", "00E"} and clip.get("last_frame"):
        # These shots must converge on the exact seated/standing relationship;
        # allowing a single-anchor improvisation caused the earlier role swaps.
        clip["force_last_frame"] = True
    changed.append(clip_id)

CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
print("Locked opening roles for:", ", ".join(changed))
