import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
MANIFEST = PROJECT / "manifest.json"
SOURCE = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\04C\attempt_1_00003_.mp4")
DESTINATION = PROJECT / "clips" / "001_04C.mp4"
OVERVIEW = PROJECT / "validation_contacts" / "04C_attempt_3_overview.jpg"
ENDING = PROJECT / "validation_contacts" / "04C_attempt_3_ending.jpg"
EVERY_SECOND = PROJECT / "validation_contacts" / "04C_attempt_3_every_second.jpg"


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not SOURCE.is_file():
        raise SystemExit("Approved 04C attempt or ffmpeg is unavailable")
    subprocess.run(
        [
            ffmpeg, "-y", "-v", "error", "-i", str(SOURCE),
            "-map", "0:v:0", "-c:v", "copy", "-an", str(DESTINATION),
        ],
        check=True,
        timeout=180,
    )
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    prior = manifest["clips"].get("04C", {})
    manifest["clips"]["04C"] = {
        **prior,
        "status": "valid",
        "attempt": 1,
        "attempt_total": 3,
        "clip": str(DESTINATION),
        "comfy_source": str(SOURCE),
        "chunk_archive": str(SOURCE),
        "duration": 7.0,
        "frames": 175,
        "steps": 15,
        "used_last_frame": True,
        "first_frame": "frames/scene_004/boundary_04C_open_v3.png",
        "last_frame": "frames/scene_004/boundary_04C_close_v2.png",
        "validation_contact": str(OVERVIEW),
        "validation_ending": str(ENDING),
        "validation_every_second": str(EVERY_SECOND),
        "raw_audio_discarded": True,
        "user_approved_visual": True,
        "visual_validation": (
            "User reviewed attempt 3 and judged the action correct. "
            "The brief bill-like intermediate gesture is accepted as reconsideration/refusal; "
            "the shot ends with Kent retaining the closed wallet and the plate untouched."
        ),
        "rejected_predecessors": [
            r"A:\Users\rhine\ComfyUI-Shared\output\story\04C\attempt_1_00001_.mp4",
            r"A:\Users\rhine\ComfyUI-Shared\output\story\04C\attempt_1_00002_.mp4",
        ],
    }
    manifest["clips"]["04C"].pop("visual_rejection_reason", None)
    manifest["clips"]["04C"].pop("visual_rejected_at", None)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Selected user-approved 04C attempt 3: {SOURCE}")


if __name__ == "__main__":
    main()
