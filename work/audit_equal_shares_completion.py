import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG = PROJECT / "story_config.json"
MANIFEST = PROJECT / "manifest.json"
FINAL = PROJECT / "EQUAL_SHARES_FINAL_1344x768.mp4"
SHARED_RAW_ROOT = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story")
REPORT = PROJECT / "completion_audit.json"


def probe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"error": "ffprobe unavailable"}
    result = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration:stream=index,codec_type,codec_name,width,height",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        return {"error": result.stderr.strip() or f"ffprobe exit {result.returncode}"}
    return json.loads(result.stdout)


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    planned = config["clips"]
    records = manifest.get("clips", {})
    expected_ids = [clip["id"] for clip in planned]
    valid_ids = [clip_id for clip_id in expected_ids if records.get(clip_id, {}).get("status") == "valid"]
    missing_or_invalid = [clip_id for clip_id in expected_ids if clip_id not in valid_ids]
    missing_raw = []
    raw_outside_shared = []
    missing_assembly = []
    for clip_id in valid_ids:
        record = records[clip_id]
        raw_value = record.get("chunk_archive") or record.get("comfy_source")
        raw = Path(raw_value) if raw_value else None
        assembly_value = record.get("clip")
        assembly = Path(assembly_value) if assembly_value else None
        if raw is None or not raw.is_file():
            missing_raw.append(clip_id)
        elif SHARED_RAW_ROOT not in raw.resolve().parents:
            raw_outside_shared.append(clip_id)
        if assembly is None or not assembly.is_file():
            missing_assembly.append(clip_id)

    expected_duration = sum(
        float(clip.get("edit_duration", clip["duration"])) for clip in planned
    )
    final_probe = probe(FINAL) if FINAL.is_file() else None
    final_video = None
    final_audio = None
    final_duration = None
    if final_probe and not final_probe.get("error"):
        streams = final_probe.get("streams", [])
        final_video = next((s for s in streams if s.get("codec_type") == "video"), None)
        final_audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        final_duration = float(final_probe.get("format", {}).get("duration", 0.0))

    checks = {
        "all_planned_clips_valid": len(valid_ids) == len(expected_ids),
        "all_accepted_raw_chunks_present": not missing_raw,
        "all_accepted_raw_chunks_in_shared_output": not raw_outside_shared,
        "all_assembly_clips_present": not missing_assembly,
        "final_master_present": FINAL.is_file(),
        "final_resolution_1344x768": bool(
            final_video and final_video.get("width") == 1344 and final_video.get("height") == 768
        ),
        "final_h264_video": bool(final_video and final_video.get("codec_name") == "h264"),
        "final_audio_present": final_audio is not None,
        "final_aac_audio": bool(final_audio and final_audio.get("codec_name") == "aac"),
        "final_duration_matches_edit": bool(
            final_duration is not None and abs(final_duration - expected_duration) <= 2.0
        ),
    }
    report = {
        "complete": all(checks.values()),
        "checks": checks,
        "planned_clip_count": len(expected_ids),
        "valid_clip_count": len(valid_ids),
        "missing_or_invalid": missing_or_invalid,
        "missing_raw": missing_raw,
        "raw_outside_shared": raw_outside_shared,
        "missing_assembly": missing_assembly,
        "shared_raw_attempt_count": len(list(SHARED_RAW_ROOT.glob("**/*.mp4"))),
        "expected_edit_duration_seconds": expected_duration,
        "final_duration_seconds": final_duration,
        "final_probe": final_probe,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
