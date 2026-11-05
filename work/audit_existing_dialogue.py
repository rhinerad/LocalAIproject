#!/usr/bin/env python3
"""Exercise the exact-dialogue gate against known Equal Shares attempts."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs"))
from dialogue_validator import validate_dialogue  # noqa: E402


project = ROOT / "outputs" / "equal_shares"
config = json.loads((project / "story_config.json").read_text(encoding="utf-8"))
by_id = {clip["id"]: clip for clip in config["clips"]}
attempts = {
    "00A": Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00A\attempt_1_00002_.mp4"),
    "00B": Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00B\attempt_1_00002_.mp4"),
    "00C": Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00C\attempt_1_00002_.mp4"),
    "00D": Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00D\attempt_1_00002_.mp4"),
    "00D2": Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00D2\attempt_1_00001_.mp4"),
}
for clip_id, video in attempts.items():
    valid, result = validate_dialogue(video, by_id[clip_id], project, "known_attempt")
    print(json.dumps({
        "id": clip_id,
        "valid": valid,
        "expected": result.get("expected"),
        "recognized": result.get("recognized"),
        "coverage": result.get("coverage"),
        "similarity": result.get("similarity"),
        "reason": result.get("reason"),
    }, ensure_ascii=False))
