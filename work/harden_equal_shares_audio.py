#!/usr/bin/env python3
"""Apply exact-dialogue and continuous-soundtrack policy to Equal Shares."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG_PATH = PROJECT / "story_config.json"
MANIFEST_PATH = PROJECT / "manifest.json"


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
config["retries"] = 0
config["dialogue_validation"] = True
config["audio_policy"] = {
    "h3_music": "forbidden",
    "h3_speech": "exact quoted dialogue only; offline transcription required",
    "final_soundtrack": "one continuous original score mixed during assembly",
    "soundtrack_path": "audio/EQUAL_SHARES_CONTINUOUS_SCORE.wav",
    "soundtrack_gain_db": -25.0,
    "dialogue_duck_db": -8.0,
}
replacement = (
    "Synchronized audio: Quiet natural location ambience and necessary physical action sounds only; "
    "no music, song, score, underscore, sting, motif, or transition cue. No subtitles"
)
for clip in config["clips"]:
    prompt = clip["prompt"]
    prompt, count = re.subn(
        r"Synchronized audio:.*? No subtitles",
        replacement,
        prompt,
        count=1,
        flags=re.DOTALL,
    )
    if count == 0:
        prompt += "\n" + replacement + "."
    clip["prompt"] = prompt
    clip["audio"] = (
        "Quiet natural location ambience and necessary physical action sounds only. "
        "No music; the continuous score is added during final assembly."
    )
save(CONFIG_PATH, config)

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
records = manifest.setdefault("clips", {})
rejections = {
    "00A": "User rejected both generated versions: gibberish/invented speech; earlier attempt also placed an extra man behind reception.",
    "00C": "User rejected generated versions: gibberish/invented speech and incorrect invented people/action in the earlier attempt.",
    "00D": "Offline transcript rejected malformed and invented narration; visual geometry is retained only as review evidence.",
    "00D2": "Offline transcript rejected mostly unintelligible narration; must regenerate with exact-dialogue lock.",
}
for clip_id, reason in rejections.items():
    record = records.setdefault(clip_id, {})
    record["status"] = "rejected"
    record["rejection_reason"] = reason
    record["selected_for_regeneration"] = True
if "00B" in records:
    records["00B"]["status"] = "valid"
    records["00B"]["user_approved"] = True
    records["00B"]["user_approved_source"] = r"A:\Users\rhine\ComfyUI-Shared\output\story\00B\attempt_1_00002_.mp4"
save(MANIFEST_PATH, manifest)

print("Applied no-music/exact-dialogue policy to", len(config["clips"]), "clips")
print("Rejected for regeneration:", ", ".join(rejections))
