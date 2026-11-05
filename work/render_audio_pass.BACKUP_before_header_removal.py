#!/usr/bin/env python3
"""Render the complete Equal Shares soundtrack before high-resolution picture.

All 124 story clips are rendered through full-quality MiniMax H3 ref2va at the
lowest proven resolution (0.2 MP). The video is disposable; every native H3
audio attempt and its validation report are preserved. This runner never writes
the story picture manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
from datetime import datetime
from pathlib import Path

import importlib

import render_single_pass as h3
import thermal_guard
import validate_audio_pass as audio_gate

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
STORY_CONFIG = PROJECT / "story_config.json"
# Stage-1 render lengths, shortened to fit the spoken line. H3 fills whatever
# window it is given with speech, so a clip scripted at 15 s for a 9 s line gets
# 6 s of invented gibberish. Render short, pad silence at assembly.
# See docs/H3_PROMPT_RULES.md section 9. Picture NEVER uses these lengths.
AUDIO_DURATIONS = PROJECT / "audio_pass_durations.json"
AUDIO_CONFIG = PROJECT / "audio_pass_config_omni_v1.json"
BOOTSTRAP_PLAN = PROJECT / "story_voice_bootstrap_plan.json"
MANIFEST = PROJECT / "audio_pass_manifest.json"
OWNER = PROJECT / "runtime" / "render_queue_owner.json"
LOG = PROJECT / "runtime" / "audio_pass_supervisor.log"

MEGAPIXELS = 0.2
MAX_AUDIO_REFS = 3

NARRATOR_SINGLE_LAYER_LOCK = (
    "\n\nVOCAL MIX — SINGLE NARRATOR PERFORMANCE ONLY\n"
    "The Narrator is exactly one dry, centered, foreground voice with one timbre, "
    "one cadence, and one performance. Every numbered audio item is identity conditioning "
    "only and is completely inaudible in the result. Generate a new performance; do "
    "not replay, copy, overlay, mix, echo, whisper, shadow, chorus, harmonize, delay, "
    "or leak the reference recording, its words, breaths, or room tone. Do not create "
    "a second Narrator, a quieter duplicate, backing speech, an alternate take, or a "
    "speech-shaped reverb layer. Natural ambience contains no voices.\n"
)


def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def claim_queue() -> bool:
    if OWNER.exists():
        try:
            old = json.loads(OWNER.read_text(encoding="utf-8-sig"))
            pid = int(old.get("pid", 0))
        except Exception:
            pid = 0
        if pid != os.getpid() and h3.process_exists(pid):
            emit(f"queue belongs to live pid={pid}; not starting")
            return False
    OWNER.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Equal Shares Stage 1 — 0.2 MP native MiniMax H3 soundtrack",
    }, indent=2), encoding="utf-8")
    return True


def release_queue() -> None:
    OWNER.write_text(json.dumps({
        "pid": 0,
        "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released",
    }, indent=2), encoding="utf-8")


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_manifest(data: dict) -> None:
    temp = MANIFEST.with_name(f"{MANIFEST.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, MANIFEST)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clip_list(prompt_dir: Path | None = None) -> list[dict]:
    story = load_json(STORY_CONFIG, {"clips": []})
    audio_cfg = {
        row["id"]: row
        for row in load_json(AUDIO_CONFIG, {"clips": []}).get("clips", [])
    }
    short = {
        row["id"]: row
        for row in load_json(AUDIO_DURATIONS, {"clips": []}).get("clips", [])
    }
    rows = []
    for clip in sorted(story.get("clips", []), key=lambda x: x.get("sequence_order", 0)):
        prepared = audio_cfg.get(clip["id"], {})
        prompt_file = prepared.get("prompt_file")
        prompt = clip.get("prompt", "")
        override_used = False
        if prompt_dir is not None:
            path = prompt_dir / f"{clip['id']}.txt"
            if path.is_file():
                prompt = path.read_text(encoding="utf-8").strip()
                override_used = True
            elif prompt_file:
                fallback = PROJECT / prompt_file
                if fallback.is_file():
                    prompt = fallback.read_text(encoding="utf-8").strip()
        elif prompt_file:
            path = PROJECT / prompt_file
            if path.is_file():
                prompt = path.read_text(encoding="utf-8").strip()
        # Soundtrack length: the shortened value when one exists, otherwise the
        # scripted length. story_config is never modified -- the picture pass
        # reads its scripted duration from there and must keep the original
        # pacing of the film.
        scripted = float(clip.get("duration") or 8)
        dur_row = short.get(clip["id"], {})
        render_seconds = float(dur_row.get("audio_pass_seconds") or scripted)
        if render_seconds > scripted:            # never exceed the script
            render_seconds = scripted
        rows.append({
            "id": clip["id"],
            "duration": render_seconds,
            "scripted_duration": scripted,
            "pad_silence_seconds": round(max(0.0, scripted - render_seconds), 3),
            "first_frame": clip.get("first_frame"),
            "last_frame": clip.get("last_frame"),
            "prompt": prompt,
            "voice_refs": [x["wav"] for x in prepared.get("ref_audios", [])],
            "voice_ref_hashes": [x.get("sha256") for x in prepared.get("ref_audios", [])],
            "voice_ref_characters": [x["character"] for x in prepared.get("ref_audios", [])],
            "provisional_voice_ref_characters": [
                x["character"] for x in prepared.get("ref_audios", [])
                if x.get("provisional")
            ],
            "speakers": prepared.get("speakers", []),
            # The voice-lock pass intentionally accepts no music, ambience, or
            # effects references. Those extra audio latents previously created
            # leakage and double tracking. Only one immutable master per actual
            # speaker is allowed here.
            "sound_refs": [],
            "story": clip,
            "prompt_override_used": override_used,
        })
    return rows


def stage_input_audio(path_text: str, index: int, expected_sha256: str | None) -> str:
    source = Path(path_text)
    if not source.is_absolute():
        source = PROJECT / path_text
    if not source.is_file():
        raise FileNotFoundError(source)
    actual = file_sha256(source)
    if not expected_sha256:
        raise RuntimeError(f"voice master has no pinned SHA-256: {source}")
    if actual != expected_sha256:
        raise RuntimeError(f"voice master hash changed: {source}")
    suffix = source.suffix or ".wav"
    # Include the first 8 hex chars of the SHA-256 in the staged name so that
    # two different characters whose source files share the same basename (e.g.
    # both named omni_master_v1.wav) never collide in the shared input dir.
    hash_tag = expected_sha256[:8]
    name = f"audio_pass_ref_{index:02d}_{source.stem}_{hash_tag}{suffix}"
    destination = h3.SHARED_INPUT / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    elif file_sha256(destination) != expected_sha256:
        raise RuntimeError(f"staged voice master hash mismatch: {destination}")
    return name


def reference_job_prefix(has_last: bool, has_dialogue: bool) -> str:
    lines = [
        "AUDIO-FIRST REFERENCE JOBS",
        "<Picture 1> is the exact opening composition. Begin on it precisely.",
    ]
    if has_last:
        lines.append(
            "<Picture 2> is the exact closing composition. Arrive on it naturally "
            "at the end without a cut or morph."
        )
    lines.append("Follow the exact timed action and quoted speech below.")
    if not has_dialogue:
        lines.append("No character speaks. Do not invent speech, muttering, or lyrics.")
    return "\n".join(lines) + "\n\n"


def retry_suffix(attempt: int) -> str:
    if attempt <= 1:
        return ""
    return (
        "\n\nSTRICT AUDIO RETRY\n"
        "The previous take failed the soundtrack validator. Speak every quoted line "
        "exactly once, word for word, only in its assigned window. Do not paraphrase, "
        "repeat, add filler, mutter, or let a silent character speak. Preserve all "
        "specified sound events and do not invent music.\n"
    )


def build_workflow(clip: dict, first_file: str, last_file: str | None,
                   audio_files: list[str], seed: int, attempt: int) -> dict:
    base_prompt = clip["prompt"].strip()
    if "REFERENCE JOBS" in base_prompt:
        target = "AUDIO-FIRST TARGET\nFollow the exact timed action and quoted speech below.\n\n"
    else:
        target = reference_job_prefix(
            bool(last_file), bool(clip["story"].get("dialogue_timing")),
        )
    narrator_lock = (
        NARRATOR_SINGLE_LAYER_LOCK if "Narrator" in clip.get("speakers", []) else ""
    )
    prompt = target + base_prompt + narrator_lock + retry_suffix(attempt)
    workflow = h3._common_nodes(
        h3.UNET_REF2VA, clip["duration"], first_file, prompt, seed,
    )
    workflow["115"]["inputs"]["megapixels"] = MEGAPIXELS
    refs: dict = {
        "prompt": ["138", 0],
        "width": ["115", 0],
        "height": ["115", 1],
        "length": ["131", 1],
        "ref_image_size": "match",
        "clip": ["128", 0],
        "vae": ["119", 0],
        "audio_vae": ["120", 0],
        "ref_images.ref_image_0": ["137", 0],
    }
    if last_file:
        workflow["139"] = {"class_type": "LoadImage", "inputs": {"image": last_file}}
        refs["ref_images.ref_image_1"] = ["139", 0]
    for index, filename in enumerate(audio_files[:MAX_AUDIO_REFS]):
        node = f"200_{index}"
        workflow[node] = {"class_type": "LoadAudio", "inputs": {"audio": filename}}
        refs[f"ref_audios.ref_audio_{index}"] = [node, 0]
    workflow["136"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": refs}
    h3._add_save_nodes(
        workflow, f"story/AUDIO_{clip['id']}/{clip['id']}_audio_a{attempt:02d}",
    )
    return workflow


def append_attempt(manifest: dict, clip_id: str, attempt: dict) -> None:
    entry = manifest.setdefault("clips", {}).setdefault(clip_id, {"attempts": []})
    entry.setdefault("attempts", []).append(attempt)
    entry["status"] = attempt["status"]
    entry["latest_attempt"] = attempt["attempt"]
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", action="append", help="render only this clip; repeatable")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--prompt-dir",
        help="versioned per-clip prompt override directory; selected clips must exist",
    )
    parser.add_argument(
        "--prompt-profile", default="standard_stage1",
        help="provenance label recorded on every new manifest attempt",
    )
    parser.add_argument(
        "--rerender-pending", action="store_true",
        help="render again even when a candidate is waiting for continuity/ear review",
    )
    parser.add_argument(
        "--bootstrap-missing-voices", action="store_true",
        help="render only planned real story clips that establish missing voices",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="print the selected queue without claiming the GPU",
    )
    args = parser.parse_args()

    h3.LOG = LOG  # lifecycle progress belongs in the audio-pass log
    prompt_dir = Path(args.prompt_dir).resolve() if args.prompt_dir else None
    rows = clip_list(prompt_dir)
    bootstrap_by_clip = {
        row["id"]: row
        for row in load_json(BOOTSTRAP_PLAN, {"clips": []}).get("clips", [])
    }
    if args.bootstrap_missing_voices:
        rows = [row for row in rows if row["id"] in bootstrap_by_clip]
    if args.clip:
        wanted = set(args.clip)
        rows = [row for row in rows if row["id"] in wanted]
        missing = wanted - {row["id"] for row in rows}
        if missing:
            raise SystemExit(f"unknown clips: {', '.join(sorted(missing))}")
        if prompt_dir:
            missing_overrides = [row["id"] for row in rows if not row["prompt_override_used"]]
            if missing_overrides:
                raise SystemExit(
                    "prompt override missing for selected clips: "
                    + ", ".join(missing_overrides)
                )
    if not rows:
        raise SystemExit("no clips found")
    if args.check:
        print(json.dumps({
            "mode": "story_voice_bootstrap" if args.bootstrap_missing_voices else "stage_1_audio",
            "megapixels": MEGAPIXELS,
            "turbo": False,
            "checkpoint": h3.UNET_REF2VA,
            "node": "MiniMaxH3ReferenceToVideo",
            "steps": 20,
            "prompt_dir": str(prompt_dir) if prompt_dir else None,
            "prompt_profile": args.prompt_profile,
            "clips": [
                {
                    "id": row["id"],
                    "speakers": row["speakers"],
                    "available_voice_references": row["voice_ref_characters"],
                    "provisional_voice_references": row["provisional_voice_ref_characters"],
                    "missing_voice_references": [
                        x for x in row["speakers"] if x not in row["voice_ref_characters"]
                    ],
                    "bootstrap_characters": bootstrap_by_clip.get(row["id"], {}).get(
                        "bootstrap_characters", []
                    ),
                    "actual_story_prompt": True,
                }
                for row in rows
            ],
        }, indent=2))
        return 0
    if not claim_queue():
        return 3

    comfy_pid: int | None = None
    try:
        for position, clip in enumerate(rows, 1):
            manifest = load_json(MANIFEST, {
                "schema_version": 2,
                "stage": "complete native MiniMax H3 soundtrack at 0.2 MP",
                "clips": {},
            })
            prior = manifest.get("clips", {}).get(clip["id"], {})
            if prior.get("status") == "accepted":
                emit(f"[{position}/{len(rows)}] {clip['id']}: accepted — skip")
                continue
            if (prior.get("status") in {
                "needs_ear_review", "auto_pass_pending_continuity_review"
            } and not args.rerender_pending):
                emit(f"[{position}/{len(rows)}] {clip['id']}: pending review — skip")
                continue

            missing_speakers = [
                name for name in clip["speakers"]
                if name not in clip["voice_ref_characters"]
            ]
            bootstrap_targets = bootstrap_by_clip.get(clip["id"], {}).get(
                "bootstrap_characters", []
            )
            allowed_bootstrap = bool(
                args.bootstrap_missing_voices
                and missing_speakers
                and set(missing_speakers).issubset(set(bootstrap_targets))
            )
            if missing_speakers and not allowed_bootstrap:
                emit(
                    f"[{position}/{len(rows)}] {clip['id']}: blocked — missing story voice "
                    f"reference(s): {', '.join(missing_speakers)}; complete the earlier "
                    "real-story bootstrap first"
                )
                entry = manifest.setdefault("clips", {}).setdefault(clip["id"], {"attempts": []})
                entry.update({
                    "status": "blocked_missing_voice_reference",
                    "speakers": clip["speakers"],
                    "available_voice_references": clip["voice_refs"],
                    "missing_voice_references": missing_speakers,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                })
                save_manifest(manifest)
                continue
            if allowed_bootstrap:
                emit(
                    f"[{position}/{len(rows)}] {clip['id']}: real-story voice bootstrap for "
                    f"{', '.join(missing_speakers)}; actual script dialogue only"
                )

            first_file = h3.ensure_frame_in_input(clip["first_frame"])
            last_file = h3.ensure_frame_in_input(clip["last_frame"]) if clip["last_frame"] else None
            voice_refs = list(clip["voice_refs"])
            voice_hashes = list(clip["voice_ref_hashes"])
            refs = voice_refs
            if len(refs) > MAX_AUDIO_REFS:
                raise RuntimeError(
                    f"{clip['id']}: {len(refs)} speakers exceeds H3's "
                    f"{MAX_AUDIO_REFS}-audio Omni-Reference limit"
                )
            staged_refs = [
                stage_input_audio(path, i, voice_hashes[i])
                for i, path in enumerate(refs)
            ]

            existing_attempts = len(prior.get("attempts", []))
            for local_try in range(args.max_attempts):
                attempt_no = existing_attempts + local_try + 1
                seed = random.randint(0, 2**53)
                frames = h3.frame_count(clip["duration"])
                emit(
                    f"[{position}/{len(rows)}] {clip['id']} audio attempt {attempt_no}: "
                    f"0.2 MP, {clip['duration']}s, {frames} frames, seed={seed}"
                )
                workflow = build_workflow(
                    clip, first_file, last_file, staged_refs, seed, attempt_no,
                )

                if h3.api_ready():
                    if comfy_pid is None:
                        raise RuntimeError(
                            "port 8188 is occupied by an unowned ComfyUI backend; "
                            "refusing to stop it or add a second GPU workload"
                        )
                    h3.stop_comfy(comfy_pid)
                    comfy_pid = None
                    thermal_guard.wait_after_render(emit)
                thermal_guard.wait_before_render(emit)
                comfy_pid = h3.start_comfy()
                attempt = {
                    "attempt": attempt_no,
                    "seed": seed,
                    "megapixels": MEGAPIXELS,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                    "first_frame": clip["first_frame"],
                    "last_frame": clip["last_frame"],
                    "audio_references": refs[:MAX_AUDIO_REFS],
                    "audio_reference_sha256": voice_hashes[:MAX_AUDIO_REFS],
                    "omni_reference_voice_lock": True,
                    "prompt_reference_grammar": "<Audio 1> / <Picture 1>",
                    "non_voice_audio_references": [],
                    "provisional_voice_references": clip[
                        "provisional_voice_ref_characters"
                    ],
                    "mode": "story_voice_bootstrap" if allowed_bootstrap else "stage_1_audio",
                    "prompt_profile": args.prompt_profile,
                    "prompt_source": str(prompt_dir / f"{clip['id']}.txt") if prompt_dir else (
                        str(PROJECT / "prompts_audio_pass" / f"{clip['id']}.txt")
                    ),
                    "single_layer_narrator_lock": "Narrator" in clip.get("speakers", []),
                    "bootstrap_characters": missing_speakers if allowed_bootstrap else [],
                }
                try:
                    prompt_id = h3.submit_workflow(workflow)
                    attempt["prompt_id"] = prompt_id
                    outputs = h3.wait_for_completion(prompt_id, clip["id"])
                    video_text = h3.find_video_output(outputs)
                    if not video_text:
                        attempt.update(status="render_failed", error="no MP4 in workflow outputs")
                    else:
                        video = Path(video_text)
                        attempt["source_video"] = str(video)
                        candidate = (
                            audio_gate.CANDIDATE_DIR
                            / f"{clip['id']}_a{attempt_no:02d}_full.wav"
                        )
                        importlib.reload(audio_gate)
                        verdict = audio_gate.validate(video, clip["story"], candidate)
                        audit_path = (
                            audio_gate.AUDIT_DIR
                            / f"{clip['id']}_a{attempt_no:02d}.json"
                        )
                        audit_path.parent.mkdir(parents=True, exist_ok=True)
                        audit_path.write_text(
                            json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8",
                        )
                        attempt.update(
                            status=verdict["status"],
                            candidate_full_wav=str(candidate),
                            validation_report=str(audit_path),
                            validation_reasons=verdict.get("reasons", []),
                            completed_at=datetime.now().isoformat(timespec="seconds"),
                        )
                except Exception as exc:
                    attempt.update(status="render_error", error=str(exc))

                manifest = load_json(MANIFEST, {
                    "schema_version": 2,
                    "stage": "complete native MiniMax H3 soundtrack at 0.2 MP",
                    "clips": {},
                })
                append_attempt(manifest, clip["id"], attempt)
                save_manifest(manifest)
                emit(
                    f"{clip['id']} attempt {attempt_no}: {attempt['status']}"
                    + (f" — {'; '.join(attempt.get('validation_reasons', []))}" if attempt.get("validation_reasons") else "")
                )
                if attempt["status"] != "retry_required":
                    break

            if comfy_pid is not None and h3.api_ready():
                h3.stop_comfy(comfy_pid)
                comfy_pid = None
            thermal_guard.wait_after_render(emit)

            current = load_json(MANIFEST, {"clips": {}})
            accepted = sum(x.get("status") == "accepted" for x in current.get("clips", {}).values())
            pending = sum(x.get("status") in {
                "needs_ear_review", "auto_pass_pending_continuity_review"
            } for x in current.get("clips", {}).values())
            emit(f"Audio gate: {accepted}/124 accepted, {pending} pending review")
    finally:
        if comfy_pid is not None and h3.api_ready():
            h3.stop_comfy(comfy_pid)
        release_queue()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
