#!/usr/bin/env python3
"""Repair narrator-only 00A and empty-room transition 00C."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG_PATH = PROJECT / "story_config.json"
MANIFEST_PATH = PROJECT / "manifest.json"
config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
clips = {clip["id"]: clip for clip in config["clips"]}

a = clips["00A"]
a["first_frame"] = "frames/scene_000/boundary_narrator_close_v3.png"
a["last_frame"] = None
a["prompt"] = (
    "Standard MiniMax H3 reference-to-video, full-quality non-Turbo, 15 seconds, 16:9, one continuous locked shot. "
    "<Picture 1> is the sole visual anchor. Black-and-white 1960s anthology television realism. Exactly two people "
    "are visible for the entire clip: the same male Narrator in tight foreground addressing the camera and the same "
    "female receptionist behind her rectangular work window in the background. Preserve both exact identities, "
    "wardrobe, wall, framing, and lighting. The crop contains no entrance doorway and no public chair. The Narrator "
    "uses restrained facial movement; the receptionist remains still behind the window. No visitor enters or appears; "
    "no third person, duplicate, woman outside the window, narrator duplicate, camera reveal, cut, morph, captions, "
    "text, logo, watermark, music, glass gate, or Turbo generation. Dialogue is added in post-production; no one "
    "vocalizes in this render. Quiet room tone only."
)
a["visual_acceptance"] = {
    "visible_people": "exactly narrator and receptionist only throughout",
    "receptionist": "behind window throughout",
    "forbidden": "visitor, doorway reveal, public chair, third person, duplicate",
    "reject_on_violation": True,
}

c = clips["00C"]
c["duration"] = 8.0
c["edit_duration"] = 8.0
c.pop("frames", None)
c["force_last_frame"] = True
for timing in c.get("dialogue_timing", []):
    timing["start"] = 0.5
    timing["end"] = 7.8
c["prompt"] = (
    "Standard MiniMax H3 reference-to-video, full-quality non-Turbo, 8 seconds, 16:9, one continuous controlled "
    "camera move. <Picture 1> is the opening anchor and <Picture 2> is the mandatory closing anchor. Begin with "
    "exactly the same male Narrator foreground and the same female receptionist behind the window. The camera glides "
    "past the Narrator and crops him out, ending on the completely empty public waiting room shown in Picture 2: "
    "one empty chair at screen-left, receptionist alone behind the window, and separate open doorway at screen-right. "
    "No visitor enters, emerges, sits, stands, or appears at any time. Start with exactly two people and end with "
    "exactly one visible person, the receptionist behind the window. Preserve architecture and lighting; no cut, "
    "morph, duplicate, third person, male visitor, woman outside the window, glass gate, captions, text, logo, "
    "watermark, music, or Turbo generation. Dialogue is added in post-production; no one vocalizes in this render."
)
c["visual_acceptance"] = {
    "start": "narrator foreground and receptionist behind window only",
    "end": "empty public room; receptionist behind window; no visitors",
    "forbidden": "any visitor, anyone seated, receptionist leaving window, extra person",
    "reject_on_violation": True,
}

CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
for clip_id, reason in {
    "00A": "Every-second audit: narrator-only take invented two visitors who entered and sat.",
    "00C": "Every-second audit: empty-room transition invented two visitors and seated both men.",
}.items():
    record = manifest.setdefault("clips", {}).setdefault(clip_id, {})
    record["status"] = "rejected"
    record["rejection_reason"] = reason
    record["selected_for_regeneration"] = True
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print("Rejected and repaired 00A, 00C")
