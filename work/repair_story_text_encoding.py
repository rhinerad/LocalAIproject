#!/usr/bin/env python3
"""Repair UTF-8 text that was previously decoded as Windows-1252."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"


def repair_text(value: str) -> str:
    if not any(marker in value for marker in ("â€", "â€™", "â€”", "Ã", "Â")):
        return value
    try:
        repaired = value.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired.count("â") < value.count("â") else value


def repair(value):
    if isinstance(value, dict):
        return {key: repair(item) for key, item in value.items()}
    if isinstance(value, list):
        return [repair(item) for item in value]
    if isinstance(value, str):
        return repair_text(value)
    return value


for name in ("story_config.json", "shot_plan.json", "source_clip_script.json", "story_bible.json"):
    path = PROJECT / name
    if not path.is_file():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(repair(data), indent=2, ensure_ascii=False), encoding="utf-8")
    print("Repaired", path)
