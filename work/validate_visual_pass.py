#!/usr/bin/env python3
"""Mechanical prefilter and native-frame preparation for Stage-2 picture takes.

The output can reject objective failures, but it never grants visual acceptance.
Faces, anatomy, blocking, identity, interactions, and prompt compliance require
agent inspection of the full clip and the native-resolution frame set.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
STORY_CONFIG = PROJECT / "story_config.json"
OUT_ROOT = PROJECT / "visual_validation_stage2"


def run(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )


def probe(video: Path) -> dict:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json", str(video),
    ])
    if proc.returncode:
        return {"ok": False, "error": proc.stderr.strip()}
    payload = json.loads(proc.stdout)
    streams = payload.get("streams", [])
    visual = next((x for x in streams if x.get("codec_type") == "video"), None)
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    return {
        "ok": bool(visual),
        "duration": float(payload.get("format", {}).get("duration") or 0),
        "size": int(payload.get("format", {}).get("size") or 0),
        "width": int((visual or {}).get("width") or 0),
        "height": int((visual or {}).get("height") or 0),
        "fps": (visual or {}).get("r_frame_rate"),
        "video_codec": (visual or {}).get("codec_name"),
        "has_audio": bool(audio),
    }


def filter_events(video: Path, expression: str) -> str:
    proc = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
        "-vf", expression, "-an", "-f", "null", "NUL",
    ])
    return proc.stderr


def extract_native_frames(video: Path, directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    pattern = directory / "frame_%05d.png"
    if not any(directory.glob("frame_*.png")):
        proc = run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
            "-vf", "fps=2", "-vsync", "0", str(pattern),
        ])
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or "native frame extraction failed")
    return [str(x) for x in sorted(directory.glob("frame_*.png"))]


def optional_face_summary(frame_paths: list[str]) -> dict:
    try:
        import cv2  # type: ignore
    except Exception:
        return {"available": False, "note": "OpenCV unavailable; no face-count prefilter"}
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    counts = []
    areas = []
    for text in frame_paths:
        image = cv2.imread(text)
        if image is None:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        counts.append(len(faces))
        areas.append(sorted((int(w * h) for _, _, w, h in faces), reverse=True))
    transitions = sum(a != b for a, b in zip(counts, counts[1:]))
    return {
        "available": True,
        "sampled_frames": len(counts),
        "counts": counts,
        "count_transitions": transitions,
        "largest_face_areas": [row[0] if row else 0 for row in areas],
        "note": "Haar detections are warnings only; profile/small faces may be missed.",
    }


def validate(video: Path, clip: dict, output_dir: Path) -> dict:
    mechanical = probe(video)
    report = {
        "schema_version": 1,
        "clip_id": clip["id"],
        "source_video": str(video),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "mechanical": mechanical,
        "objective_failures": [],
        "warnings": [],
    }
    failures = report["objective_failures"]
    warnings = report["warnings"]
    if not mechanical.get("ok"):
        failures.append("missing or unreadable video stream")
        report["status"] = "auto_reject"
        return report
    width, height = mechanical["width"], mechanical["height"]
    if width <= 0 or height <= 0 or width % 32 or height % 32:
        failures.append(f"invalid MiniMax dimensions {width}x{height}")
    if mechanical.get("fps") != "24/1":
        failures.append(f"unexpected frame rate {mechanical.get('fps')}")
    expected = float(clip.get("duration") or 0)
    if expected and abs(mechanical["duration"] - expected) > 1.0:
        failures.append(
            f"duration {mechanical['duration']:.3f}s differs from requested {expected:.3f}s"
        )

    black = filter_events(video, "blackdetect=d=0.25:pix_th=0.10")
    black_events = re.findall(r"black_start:([\d.]+).*?black_end:([\d.]+)", black)
    if black_events:
        failures.append(f"black-frame intervals detected: {black_events}")

    freeze = filter_events(video, "freezedetect=n=-55dB:d=2.0")
    freeze_starts = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", freeze)]
    freeze_ends = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", freeze)]
    report["freeze_events"] = {"starts": freeze_starts, "ends": freeze_ends}
    if freeze_starts:
        warnings.append("freeze interval over two seconds detected; inspect whether it is intentional")

    scene = filter_events(video, "select='gt(scene,0.60)',showinfo")
    scene_times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", scene)]
    report["hard_scene_change_times"] = scene_times
    prompt = str(clip.get("prompt", ""))
    if scene_times and re.search(r"do not cut|unbroken take|no internal edit", prompt, re.I):
        failures.append(f"probable hard cut(s) in continuous shot at {scene_times}")
    elif scene_times:
        warnings.append(f"hard scene-change candidates at {scene_times}")

    frames_dir = output_dir / "native_frames_2fps"
    frame_paths = extract_native_frames(video, frames_dir)
    report["native_frame_directory"] = str(frames_dir)
    report["native_frame_count"] = len(frame_paths)
    report["face_prefilter"] = optional_face_summary(frame_paths)
    face = report["face_prefilter"]
    if face.get("available") and face.get("sampled_frames", 0) > 4:
        transitions = face.get("count_transitions", 0)
        if transitions > max(4, face["sampled_frames"] // 2):
            warnings.append("face detections change unusually often; inspect identity/body continuity")

    report["status"] = "auto_reject" if failures else "needs_agent_native_review"
    report["acceptance_note"] = (
        "This prefilter cannot pass a clip. Inspect the full motion and native frames for "
        "identity, anatomy, hands, limbs, interactions, blocking, architecture, text, and "
        "prompt/reference compliance."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--attempt-tag", required=True)
    parser.add_argument("--json")
    args = parser.parse_args()
    cfg = json.loads(STORY_CONFIG.read_text(encoding="utf-8-sig"))
    clips = {row["id"]: row for row in cfg["clips"]}
    if args.clip not in clips:
        raise SystemExit(f"unknown clip: {args.clip}")
    video = Path(args.video)
    if not video.is_file():
        raise SystemExit(f"video not found: {video}")
    target = OUT_ROOT / args.clip / args.attempt_tag
    report = validate(video, clips[args.clip], target)
    out = Path(args.json) if args.json else target / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "clip": args.clip,
        "status": report["status"],
        "objective_failures": report.get("objective_failures", []),
        "warnings": report.get("warnings", []),
        "native_frames": report.get("native_frame_directory"),
        "report": str(out),
    }, indent=2, ensure_ascii=False))
    return 2 if report["status"] == "auto_reject" else 0


if __name__ == "__main__":
    raise SystemExit(main())
