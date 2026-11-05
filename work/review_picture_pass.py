#!/usr/bin/env python3
"""Record native-resolution Stage-2 review and advance the MP ladder safely."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
MANIFEST = PROJECT / "picture_pass_manifest.json"
ASSEMBLY = PROJECT / "assembly_inputs_audio_first"
LADDER = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]


def next_rung(value: float) -> float | None:
    for index, rung in enumerate(LADDER):
        if abs(rung - value) < 1e-6:
            return LADDER[index + 1] if index + 1 < len(LADDER) else None
    return None


def save(data: dict) -> None:
    temp = MANIFEST.with_name(f"{MANIFEST.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, MANIFEST)


def mux_exact_audio(video: Path, wav: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    proc = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
        "-i", str(video), "-i", str(wav),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(destination),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode or not destination.is_file():
        raise RuntimeError(proc.stderr.strip() or "ffmpeg exact-audio mux failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--accept", action="store_true")
    action.add_argument("--reject", action="store_true")
    parser.add_argument("--note", required=True)
    parser.add_argument("--reviewer", default="local-agent-vision")
    args = parser.parse_args()

    if not MANIFEST.is_file():
        raise SystemExit(f"manifest not found: {MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    entry = data.get("clips", {}).get(args.clip)
    if not entry or not entry.get("attempts"):
        raise SystemExit(f"no Stage-2 attempt recorded for {args.clip}")
    attempt = entry["attempts"][-1]
    if attempt.get("status") not in {"needs_agent_native_review", "auto_reject"}:
        raise SystemExit(f"latest attempt is not reviewable: {attempt.get('status')}")
    stamp = datetime.now().isoformat(timespec="seconds")
    review = {
        "verdict": "accepted" if args.accept else "rejected",
        "reviewed_at": stamp,
        "reviewer": args.reviewer,
        "note": args.note,
        "native_frame_directory": attempt.get("native_frame_directory"),
    }
    attempt.setdefault("reviews", []).append(review)

    if args.reject:
        lower = next_rung(float(attempt["megapixels"]))
        if lower is None:
            entry["status"] = "human_review_needed"
            entry["human_review_reason"] = args.note
            entry.pop("next_megapixels", None)
        else:
            entry["status"] = "review_rejected"
            entry["next_megapixels"] = lower
        entry["updated_at"] = stamp
        save(data)
        print(
            f"{args.clip}: rejected at {attempt['megapixels']:.1f} MP; "
            + (f"next {lower:.1f} MP" if lower is not None else "human review needed")
        )
        return 0

    video = Path(attempt.get("source_video", ""))
    wav = Path(attempt.get("accepted_audio", ""))
    report = Path(attempt.get("validation_report", ""))
    if not video.is_file() or not wav.is_file() or not report.is_file():
        raise SystemExit("source video, approved Stage-1 WAV, or validation report is missing")
    attempt_no = int(attempt.get("attempt") or 0)
    mp_tag = str(attempt.get("megapixels")).replace(".", "p")
    muxed = ASSEMBLY / f"{args.clip}_a{attempt_no:02d}_{mp_tag}mp_exact_audio.mp4"
    mux_exact_audio(video, wav, muxed)
    entry.update({
        "status": "visually_accepted",
        "accepted_attempt": attempt_no,
        "accepted_megapixels": attempt.get("megapixels"),
        "selected_picture_raw": str(video),
        "selected_exact_audio_wav": str(wav),
        "assembly_input": str(muxed),
        "visual_validation_report": str(report),
        "accepted_at": stamp,
        "reviewer": args.reviewer,
        "review_note": args.note,
    })
    entry.pop("next_megapixels", None)
    save(data)
    print(f"{args.clip}: visually accepted; exact Stage-1 audio muxed -> {muxed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
