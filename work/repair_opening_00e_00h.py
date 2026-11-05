#!/usr/bin/env python3
"""Reject drifted 00E-00H takes and assign tighter corrected anchors."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG_PATH = PROJECT / "story_config.json"
MANIFEST_PATH = PROJECT / "manifest.json"

CLOSE_LOCK = (
    "CLOSE TWO-MAN FRAME LOCK: Exactly two people are visible: Male Visitor One seated and Male "
    "Visitor Two standing. The receptionist and narrator are outside this tight crop and never enter "
    "the frame. No doorway, reception window, background pedestrian, third man, woman, duplicate, "
    "or additional chair appears. "
)

config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
clips = {clip["id"]: clip for clip in config["clips"]}

clip = clips["00E"]
clip["duration"] = 8.0
clip["edit_duration"] = 8.0
clip.pop("frames", None)
clip["force_last_frame"] = True
for timing in clip.get("dialogue_timing", []):
    timing["start"] = 0.5
    timing["end"] = 7.8

for clip_id, frame in {
    "00F": "frames/scene_000/boundary_seated_close_v3.png",
    "00G": "frames/scene_000/boundary_standing_close_v3.png",
    "00H": "frames/scene_000/boundary_standing_close_v3.png",
}.items():
    clip = clips[clip_id]
    clip["first_frame"] = frame
    clip["last_frame"] = None
    clip.pop("force_last_frame", None)
    prompt = clip["prompt"]
    prompt = re.sub(r"OPENING ROLE LOCK:.*?Scene and performance:", CLOSE_LOCK + "Scene and performance:", prompt, count=1)
    prompt = prompt.replace("Person Two is only partly visible at frame edge.", "Person Two remains visible standing at frame-right.")
    prompt = prompt.replace("The seated person remains frozen at the edge of frame.", "Person One remains seated at the lower-left edge of frame.")
    clip["prompt"] = prompt
    clip["negative_prompt"] += (
        ", receptionist visible, woman visible, narrator visible, doorway visible, reception window visible, "
        "third man, background person, extra visitor, duplicate visitor, two seated people, two chairs"
    )
    clip["visual_acceptance"] = {
        "visible_people": "exactly two male visitors only",
        "person_one": "seated throughout",
        "person_two": "standing throughout",
        "offscreen": "receptionist and narrator remain outside tight crop",
        "reject_on_violation": True,
    }

CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
reasons = {
    "00E": "Every-second audit: generated extra men; regenerate as shorter dual-anchor transition.",
    "00F": "Every-second audit: receptionist entered public room and extra people appeared.",
    "00G": "Every-second audit: receptionist entered public room and extra men appeared.",
    "00H": "Every-second audit: extra men appeared behind the intended seated/standing pair.",
}
for clip_id, reason in reasons.items():
    record = manifest.setdefault("clips", {}).setdefault(clip_id, {})
    record["status"] = "rejected"
    record["rejection_reason"] = reason
    record["selected_for_regeneration"] = True
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print("Rejected and repaired:", ", ".join(reasons))
