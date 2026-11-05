#!/usr/bin/env python3
"""Create immutable 5-10 second H3 Omni-Reference master voice files.

The evolving source reference map is never used directly by the new pass. This
script creates versioned master files and pins each one by SHA-256. Existing
masters are verified and reused; they are never overwritten.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
SOURCE_MAP = EQ / "voice_reference_map.json"
OUT_MAP = EQ / "omni_voice_master_map.json"
VOX_MANIFEST = EQ / "vox_reference_manifest.json"
MIN_SECONDS = 5.0
MAX_SECONDS = 10.0
TRIM_SECONDS = 8.0

# The user reauthorized these purpose-built VOX references on 2026-08-14 as
# master-voice identity sources only. They never enter the film soundtrack.
# The old rejection records and filenames remain preserved as history.
REAUTHORIZED_VOX_SOURCES = {
    "Aid worker": "runtime/codex_comfy_runtime/output/story/VOX_AID_WORKER_REF/VOX_AID_WORKER_REF_attempt_2_audio.wav",
    "Council member": "runtime/codex_comfy_runtime/output/story/VOX_COUNCIL_MEMBER_REF/VOX_COUNCIL_MEMBER_REF_attempt_1_audio.wav",
    "Wealthy commuter": "voices/wealthy_commuter/h3_voice_ref.V1_REJECTED_DO_NOT_USE.wav",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def next_destination(slug: str) -> Path:
    folder = EQ / "voices" / slug
    folder.mkdir(parents=True, exist_ok=True)
    for version in range(1, 1000):
        candidate = folder / f"omni_master_v{version}.wav"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"no free master version for {slug}")


def main() -> int:
    source_map = json.loads(SOURCE_MAP.read_text(encoding="utf-8-sig"))
    reauthorized_vox = dict(REAUTHORIZED_VOX_SOURCES)
    if VOX_MANIFEST.is_file():
        vox_manifest = json.loads(VOX_MANIFEST.read_text(encoding="utf-8-sig"))
        for entry in vox_manifest.get("clips", {}).values():
            if entry.get("status") == "metric_pass" and entry.get("audio"):
                reauthorized_vox[entry["character"]] = entry["audio"]
    previous = {}
    if OUT_MAP.is_file():
        previous = json.loads(OUT_MAP.read_text(encoding="utf-8-sig")).get("references", {})

    refs: dict[str, dict] = {}
    for character, source in source_map.get("references", {}).items():
        existing = previous.get(character, {})
        existing_rel = existing.get("ref_wav")
        existing_path = EQ / existing_rel if existing_rel else None
        if existing.get("sha256") and existing_path and existing_path.is_file():
            if sha256(existing_path) != existing["sha256"]:
                raise RuntimeError(f"immutable master hash changed: {existing_path}")
            refs[character] = existing
            continue

        source_ref_wav = reauthorized_vox.get(character, source["ref_wav"])
        source_path = Path(source_ref_wav)
        if not source_path.is_absolute():
            source_path = EQ / source_path
        if not source_path.is_file():
            refs[character] = {
                "character": character,
                "eligible": False,
                "reason": "source_reference_missing",
                "source_ref_wav": source_ref_wav,
            }
            continue

        seconds = duration(source_path)
        if seconds < MIN_SECONDS:
            refs[character] = {
                "character": character,
                "slug": source.get("slug"),
                "eligible": False,
                "reason": f"master_too_short_{seconds:.2f}s_need_5_to_10s",
                "source_ref_wav": source_ref_wav,
                "source_seconds": round(seconds, 3),
                "provisional": source.get("provisional", False),
                "requires_ear_review": True,
            }
            continue

        destination = next_destination(source["slug"])
        if seconds <= MAX_SECONDS:
            shutil.copy2(source_path, destination)
        else:
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(source_path), "-t", str(TRIM_SECONDS),
                "-vn", "-c:a", "pcm_s16le", str(destination),
            ], check=True)

        master_seconds = duration(destination)
        refs[character] = {
            "character": character,
            "slug": source["slug"],
            "eligible": MIN_SECONDS <= master_seconds <= MAX_SECONDS,
            "ref_wav": str(destination.relative_to(EQ)).replace("\\", "/"),
            "sha256": sha256(destination),
            "seconds": round(master_seconds, 3),
            "source_ref_wav": source_ref_wav,
            "source_sha256": sha256(source_path),
            "source_clip": source.get("source_clip"),
            "speech_seconds": min(float(source.get("speech_seconds", master_seconds)), master_seconds),
            "provisional": source.get("provisional", False),
            "requires_ear_review": source.get("requires_ear_review", False),
            "source_policy": (
                "user_reauthorized_VOX_identity_master"
                if character in reauthorized_vox
                else "existing_story_voice_reference"
            ),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    payload = {
        "schema_version": 1,
        "strategy": "MiniMax H3 Omni-Reference immutable master voice locking",
        "rules": {
            "master_duration_seconds": [MIN_SECONDS, MAX_SECONDS],
            "same_exact_file_for_every_clip": True,
            "sha256_verified_before_every_render": True,
            "prompt_tags": "<Audio 1>, <Audio 2>, <Audio 3>",
            "maximum_simultaneous_voice_references": 3,
            "non_voice_audio_references_in_voice_pass": False,
            "reference_recording_must_be_inaudible": True,
        },
        "references": refs,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    temp = OUT_MAP.with_name(f"{OUT_MAP.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, OUT_MAP)

    ready = [name for name, row in refs.items() if row.get("eligible")]
    blocked = [name for name, row in refs.items() if not row.get("eligible")]
    print(f"immutable masters ready: {len(ready)}/{len(refs)}")
    if blocked:
        print("need a clean 5-10 second master: " + ", ".join(blocked))
    print(OUT_MAP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
