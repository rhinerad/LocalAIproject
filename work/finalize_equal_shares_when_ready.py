#!/usr/bin/env python3
"""Wait for all Equal Shares clips, assemble the master, and publish a copy."""

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG = PROJECT / "story_config.json"
MANIFEST = PROJECT / "manifest.json"
ASSEMBLER = PROJECT / "assemble_story.py"
FINAL = PROJECT / "EQUAL_SHARES_FINAL_1344x768.mp4"
REPORT = PROJECT / "FINAL_VIDEO_REPORT.json"
SHARED_FINAL = Path(r"A:\Users\rhine\ComfyUI-Shared\output\equal_shares\final")
LOG = PROJECT / "runtime" / "finalizer.log"
COMPLETION = PROJECT / "runtime" / "completion.json"


def emit(message):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def valid_progress():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"clips": {}}
    valid = 0
    for clip in config["clips"]:
        record = manifest.get("clips", {}).get(clip["id"], {})
        if record.get("status") == "valid" and Path(record.get("clip", "")).is_file():
            valid += 1
    return valid, len(config["clips"])


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    last_reported = None
    while True:
        valid, total = valid_progress()
        if valid != last_reported:
            emit(f"Waiting for validated clips: {valid}/{total}")
            last_reported = valid
        if valid == total:
            break
        time.sleep(60)

    emit("All clips valid; assembling 1344x768 delivery master")
    result = subprocess.run(
        [sys.executable, str(ASSEMBLER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        emit("Assembly failed: " + (result.stderr.strip() or result.stdout.strip()))
        return 1
    if not FINAL.is_file() or not REPORT.is_file():
        emit("Assembly returned success without the expected final artifacts")
        return 1

    SHARED_FINAL.mkdir(parents=True, exist_ok=True)
    shared_video = SHARED_FINAL / FINAL.name
    shared_report = SHARED_FINAL / REPORT.name
    shutil.copy2(FINAL, shared_video)
    shutil.copy2(REPORT, shared_report)
    completion = {
        "status": "complete",
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "validated_clips": total,
        "project_final": str(FINAL),
        "shared_final": str(shared_video),
        "original_chunks_root": r"A:\Users\rhine\ComfyUI-Shared\output\story",
        "review_contacts": str(PROJECT / "validation_contacts"),
    }
    COMPLETION.write_text(json.dumps(completion, indent=2), encoding="utf-8")
    emit(f"Published final video: {shared_video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
