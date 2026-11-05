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

import duration_ladder
import render_single_pass as h3
import thermal_guard
import validate_audio_pass as audio_gate

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
STORY_CONFIG = PROJECT / "story_config.json"
# Stage-1 render lengths, shortened to fit the spoken line, then padded with
# digital silence at assembly. Picture NEVER uses these lengths.
#
# CORRECTED 2026-08-18. This comment used to justify the shortening with "H3
# fills whatever window it is given with speech, so a clip scripted at 15 s for
# a 9 s line gets 6 s of invented gibberish." That is NOT supported: 4_`.mp4 in
# the good-audio set is 56% silence and is clean. The 00B failures carried a
# prepended header AND a long duration, and only the duration was noticed.
# Shortening is still right -- cheaper, and one fewer variable -- but it is a
# precaution, not the cause of gibberish. The retry knob for bad words is the
# duration ladder (work/duration_ladder.py).
# See docs/GOLDEN_REFERENCE/PROVEN_FACTS.md section 3.
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
    # The one-off rule (operator, 2026-08-18). voice_requirements.json says which
    # speakers are recurring and therefore get an <Audio N>, and which clips have
    # no recurring speaker at all and leave the reference path entirely.
    req = load_json(PROJECT / "voice_requirements.json", {})
    recurring = set(req.get("recurring", []))
    route = {c["id"]: c for c in req.get("clips", [])}
    if not req:
        raise RuntimeError(
            "outputs/equal_shares/voice_requirements.json is missing — run "
            "work/classify_voice_requirements.py. Without it every clip would be "
            "rendered as ref2va and one-off speakers would be given references "
            "they do not need.")
    rows = []
    for clip in sorted(story.get("clips", []), key=lambda x: x.get("sequence_order", 0)):
        prepared = audio_cfg.get(clip["id"], {})
        prompt_file = prepared.get("prompt_file")
        # ALWAYS fall back to the native prompt set, never to story_config's old
        # prompt. audio_pass_config_omni_v1.json holds only the 78 dialogue clips,
        # so the 46 silent ones had no entry and silently rendered with the
        # pre-native prompt — confirmed in the 30A render of 2026-08-17, whose
        # embedded prompt began "One continuous unbroken take. / CAMERA".
        native = PROJECT / "prompts_native_r2v" / f"{clip['id']}.txt"
        if not prompt_file and native.is_file():
            prompt_file = f"prompts_native_r2v/{clip['id']}.txt"
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
        # Keep only the RECURRING speakers' references. A one-off speaker's
        # provisional master may still be listed in audio_pass_config, and using
        # it would burn one of H3's three audio slots conditioning a voice that
        # has nothing to match. Filter all three parallel lists together.
        prepared_refs = prepared.get("ref_audios", [])
        kept = [x for x in prepared_refs if x["character"] in recurring]
        dropped = [x["character"] for x in prepared_refs if x["character"] not in recurring]
        routing = route.get(clip["id"], {})

        rows.append({
            "id": clip["id"],
            "duration": render_seconds,
            "scripted_duration": scripted,
            # The picture's frame count. This, not scripted seconds, is the
            # ladder's ceiling -- see work/duration_ladder.py.
            "scripted_frames": int(dur_row.get("scripted_frames")
                                   or clip.get("frames")
                                   or duration_ladder.frames_for(scripted)),
            # "ref2va" | "fl2va" | None for a clip with no dialogue at all
            "path": routing.get("path"),
            "node": routing.get("node"),
            "dropped_one_off_refs": dropped,
            "pad_silence_seconds": round(max(0.0, scripted - render_seconds), 3),
            "first_frame": clip.get("first_frame"),
            "last_frame": clip.get("last_frame"),
            "prompt": prompt,
            "voice_refs": [x["wav"] for x in kept],
            "voice_ref_hashes": [x.get("sha256") for x in kept],
            "voice_ref_characters": [x["character"] for x in kept],
            "provisional_voice_ref_characters": [
                x["character"] for x in kept if x.get("provisional")
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
    """Return NOTHING. The prompt goes to H3 exactly as generated.

    DO NOT REINSTATE A PREFIX. Evidence, 2026-08-17:

    All 14 clips in `ComfyUI-Shared/output/video/good audio/` — the operator's
    hand-made takes with zero doubled tracking — begin their prompt with
    `subject_definitions:` and nothing before it. Extracted from the workflow
    embedded in each MP4, so this is what H3 actually received.

    Every autopilot take that came out wrong had this prepended instead:

        AUDIO-FIRST REFERENCE JOBS
        <Picture 1> is the exact opening composition. Begin on it precisely.
        <Picture 2> is the exact closing composition...

    That declares <Picture 1> and <Picture 2> a THIRD time: they are already
    defined in `subject_definitions` and again in `retention_analysis`. The
    MiniMax R2V guide fixes where reference labels are declared, and repetition
    is the specific thing this project has been bitten by over and over.

    The prompt is generated whole by work/build_native_r2v_prompts.py. Nothing
    may be added to it at render time.
    """
    return ""

def retry_suffix(attempt: int) -> str:
    """Return NOTHING. A retry changes the DURATION, not the prompt.

    Operator rule, 2026-08-18: gibberish and mispronounced words are retried by
    walking the duration ladder — 10, 11, 9, 12, 8, 13, 7 — not by appending
    instructions. See work/duration_ladder.py.

    This block used to append a STRICT AUDIO RETRY paragraph. Two reasons it is
    gone. First, it made attempt 2 a different PROMPT as well as a different
    take, so nothing could be attributed. Second, and worse, it is exactly the
    class of change that caused the 2026-08-17 fault: text prepended or appended
    at render time to a prompt that build_native_r2v_prompts.py generated whole.
    None of the 14 known-good clips carries any wrapper text.

    DO NOT REINSTATE. The prompt reaches H3 exactly as generated, on every
    attempt, including retries.
    """
    return ""


def build_workflow(clip: dict, first_file: str, last_file: str | None,
                   audio_files: list[str], seed: int, attempt: int,
                   render_seconds: float | None = None) -> dict:
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
    # The ladder rung's length, not the clip's base length. Attempt 1 is the
    # base, so the two agree on a first attempt and differ on every retry.
    seconds = clip["duration"] if render_seconds is None else render_seconds

    # ------------------------------------------------------------------ fl2va
    # A clip whose every speaker is a one-off has nothing to reference: no voice
    # in it needs to match any other clip (operator rule, 2026-08-18). Those
    # render on plain MiniMaxH3ImageToVideo with no reference sockets at all.
    #
    # Without this branch every clip was built as ref2va, so `01B`, `20B`, `22B`
    # and `30B` would have gone through a reference node carrying zero
    # references — a graph shape nothing has ever validated.
    #
    # Proven shape: `17.mp4` in the good-audio folder IS `01B`, rendered exactly
    # this way at 0.2 MP / 20 steps and kept by the operator.
    if clip.get("path") == "fl2va" or not audio_files:
        if clip.get("path") == "fl2va" and audio_files:
            raise RuntimeError(
                f"{clip['id']}: routed fl2va but {len(audio_files)} audio "
                f"references were staged — voice_requirements.json and the "
                f"staged references disagree")
        workflow = h3.build_fl2va_workflow(
            clip["id"], seconds, first_file, prompt, seed,
            f"story/AUDIO_{clip['id']}/{clip['id']}_audio_a{attempt:02d}",
            last_frame_file=last_file,
        )
        workflow["115"]["inputs"]["megapixels"] = MEGAPIXELS
        return workflow

    # ----------------------------------------------------------------- ref2va
    workflow = h3._common_nodes(
        h3.UNET_REF2VA, seconds, first_file, prompt, seed,
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
    # Pinned so a resumed run continues the same ladder under the same noise
    # instead of restarting it. Written once and never overwritten.
    if attempt.get("seed") is not None:
        entry.setdefault("ladder_seed", attempt["seed"])
    if attempt.get("ladder_rung") is not None:
        entry["latest_ladder_rung"] = attempt["ladder_rung"]
        entry["rungs_tried"] = sorted({
            a["ladder_rung"] for a in entry["attempts"]
            if a.get("ladder_rung") is not None
        })
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

            # LADDER POSITION IS NOT LIFETIME ATTEMPT COUNT.
            #
            # Only attempts made by the ladder-aware renderer carry a
            # `ladder_rung` field. Attempts from before 2026-08-18 do not, and
            # they were rendered under the corrupted prompts (prepended header,
            # 46 clips on the wrong prompt set) — so they say nothing about which
            # durations have been tried for the CURRENT prompt.
            #
            # Counting them pushed resumed clips straight to the far end of the
            # ladder: measured 2026-08-18, 36 of 41 resumable clips would have
            # started at rung 8 (base +-4 s) and 20 of them would have reported
            # the ladder exhausted and rendered nothing at all.
            #
            # Self-healing: pre-ladder attempts are ignored here but preserved in
            # the manifest, so provenance is intact and no reset is required.
            ladder_attempts = sum(
                1 for a in prior.get("attempts", []) if a.get("ladder_rung") is not None
            )

            # ONE seed for every rung of this clip's ladder.
            #
            # The retry variable is the DURATION, not the seed (operator rule,
            # 2026-08-18; see work/duration_ladder.py). Re-rolling the seed as
            # well would mean two things changed between attempt 1 and attempt 2
            # and neither could be credited for a fix — the same attribution
            # failure that let a prepended header hide behind a duration change
            # for a week. A fixed seed does not make the rungs strictly
            # comparable either, because a different frame count is a different
            # latent shape, but it removes the one variable we control.
            #
            # A prior seed is reused when resuming so a part-walked ladder
            # continues rather than restarting under new noise.
            seed = prior.get("ladder_seed") or random.randint(0, 2**53)
            rungs = duration_ladder.ladder(
                float(clip["duration"]), max_frames=int(clip["scripted_frames"]),
            )
            emit(
                f"[{position}/{len(rows)}] {clip['id']} ladder: "
                + " -> ".join(f'{r["seconds"]:.2f}s/{r["frames"]}f' for r in rungs)
                + f"  (seed {seed} held across all rungs)"
            )

            for local_try in range(args.max_attempts):
                # attempt_no is lifetime, for filenames and provenance.
                attempt_no = existing_attempts + local_try + 1
                # ladder_pos is 1-based within the CURRENT prompt generation.
                ladder_pos = ladder_attempts + local_try + 1
                rung = duration_ladder.rung_for_attempt(
                    float(clip["duration"]), ladder_pos,
                    max_frames=int(clip["scripted_frames"]),
                )
                render_seconds, frames = rung["seconds"], rung["frames"]
                if rung.get("exhausted"):
                    emit(
                        f"{clip['id']}: duration ladder exhausted after "
                        f"{len(rungs)} rungs — every legal length has been tried. "
                        f"Marking human_review_needed rather than re-rendering a "
                        f"length that already failed."
                    )
                    break
                emit(
                    f"[{position}/{len(rows)}] {clip['id']} audio attempt {attempt_no}: "
                    f"0.2 MP, rung {rung['rung']} = {render_seconds}s, {frames} frames, "
                    f"seed={seed} (held)"
                )
                workflow = build_workflow(
                    clip, first_file, last_file, staged_refs, seed, attempt_no,
                    render_seconds=render_seconds,
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
                    "seed_held_across_ladder": True,
                    # Which rung of the duration ladder this attempt is. Recorded
                    # so a later listen can say "rung 2 was the clean one" and the
                    # rule can be judged on evidence instead of belief.
                    "ladder_rung": rung["rung"],
                    "ladder_position": ladder_pos,
                    "ladder_nominal_seconds": rung["nominal_seconds"],
                    "render_seconds": render_seconds,
                    "render_frames": frames,
                    "base_seconds": float(clip["duration"]),
                    "scripted_seconds": float(clip["scripted_duration"]),
                    "pad_silence_seconds": round(
                        max(0.0, float(clip["scripted_duration"]) - render_seconds), 3),
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
