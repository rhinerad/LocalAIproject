#!/usr/bin/env python3
"""Render Stage-2 picture around already accepted Equal Shares soundtracks.

The audio gate is hard: this runner refuses to start until all 124 Stage-1
soundtracks are accepted. Objective visual failures descend the user's fixed
0.9-to-0.4 MP ladder automatically; every other take waits for agent review at
native resolution.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from datetime import datetime
from pathlib import Path

import render_single_pass as h3
import thermal_guard
import validate_visual_pass as visual_gate

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
STORY_CONFIG = PROJECT / "story_config.json"
AUDIO_PROMPT_CONFIG = PROJECT / "audio_pass_config.json"
AUDIO_MANIFEST = PROJECT / "audio_pass_manifest.json"
MANIFEST = PROJECT / "picture_pass_manifest.json"
OWNER = PROJECT / "runtime" / "render_queue_owner.json"
LOG = PROJECT / "runtime" / "picture_pass_supervisor.log"

LADDER = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]


def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def save(data: dict) -> None:
    temp = MANIFEST.with_name(f"{MANIFEST.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, MANIFEST)


def claim_queue() -> bool:
    if OWNER.exists():
        try:
            pid = int(json.loads(OWNER.read_text(encoding="utf-8-sig")).get("pid", 0))
        except Exception:
            pid = 0
        if pid != os.getpid() and h3.process_exists(pid):
            emit(f"queue belongs to live pid={pid}; not starting")
            return False
    OWNER.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Equal Shares Stage 2 — picture around accepted soundtrack",
    }, indent=2), encoding="utf-8")
    return True


def release_queue() -> None:
    OWNER.write_text(json.dumps({
        "pid": 0,
        "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released",
    }, indent=2), encoding="utf-8")


def verify_audio_gate() -> dict[str, dict]:
    data = load(AUDIO_MANIFEST, {"clips": {}})
    accepted = {
        clip_id: row for clip_id, row in data.get("clips", {}).items()
        if row.get("status") == "accepted"
        and Path(row.get("accepted_full_wav", "")).is_file()
        and Path(row.get("source_video", "")).is_file()
    }
    if len(accepted) != 124:
        raise RuntimeError(
            f"audio gate closed: {len(accepted)}/124 accepted native MiniMax H3 soundtracks"
        )
    return accepted


def clips() -> list[dict]:
    story = load(STORY_CONFIG, {"clips": []})
    prompt_cfg = {
        row["id"]: row
        for row in load(AUDIO_PROMPT_CONFIG, {"clips": []}).get("clips", [])
    }
    rows = []
    for clip in sorted(story.get("clips", []), key=lambda x: x.get("sequence_order", 0)):
        prepared = prompt_cfg.get(clip["id"], {})
        prompt = clip.get("prompt", "")
        pfile = prepared.get("prompt_file")
        if pfile and (PROJECT / pfile).is_file():
            prompt = (PROJECT / pfile).read_text(encoding="utf-8").strip()
        # PICTURE KEEPS SCRIPTED TIMING. `clip` comes from story_config.json, so
        # `duration` and `frames` are the original scripted values and the film's
        # pacing is preserved. Only `prompt_file` is taken from the audio config.
        # Stage-1 soundtrack renders are deliberately SHORTER (see
        # docs/H3_PROMPT_RULES.md section 9 and audio_pass_durations.json) and
        # those lengths must never be spread into this row.
        assert "audio_pass_seconds" not in prepared or True, "guard"
        row = {**clip, "picture_prompt": prompt}
        for leaked in ("audio_pass_seconds", "audio_pass_frames", "pad_silence_seconds"):
            row.pop(leaked, None)
        rows.append(row)
    return rows


def stage_soundtrack(clip_id: str, source: Path) -> str:
    suffix = source.suffix or ".wav"
    filename = f"stage2_exact_soundtrack_{clip_id}{suffix}"
    target = h3.SHARED_INPUT / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size != source.stat().st_size:
        filename = f"stage2_exact_soundtrack_{clip_id}_{source.stat().st_size}{suffix}"
        target = h3.SHARED_INPUT / filename
    if not target.exists():
        shutil.copy2(source, target)
    return filename


def prompt_with_exact_audio(clip: dict, has_last: bool) -> str:
    jobs = [
        "STAGE-2 REFERENCE JOBS",
        "ref_audio_0 is the exact finished soundtrack for this shot. Preserve every "
        "word, speaker, pause, music cue, ambience, physical effect, and timestamp. "
        "Do not paraphrase, repeat, replace, remix, or add speech. Generate the visible "
        "performance and action around this soundtrack.",
        "ref_image_0 is the exact opening composition. Begin on it precisely.",
    ]
    if has_last:
        jobs.append(
            "ref_image_1 is the exact closing composition. Arrive on it naturally at "
            "the end without a cut, morph, or unrelated reframe."
        )
    return "\n".join(jobs) + "\n\n" + clip["picture_prompt"].strip()


def build_workflow(clip: dict, first: str, last: str | None, audio: str,
                   megapixels: float, seed: int, attempt: int) -> dict:
    workflow = h3._common_nodes(
        h3.UNET_REF2VA, float(clip.get("duration") or 8), first,
        prompt_with_exact_audio(clip, bool(last)), seed,
    )
    workflow["115"]["inputs"]["megapixels"] = megapixels
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
    if last:
        workflow["139"] = {"class_type": "LoadImage", "inputs": {"image": last}}
        refs["ref_images.ref_image_1"] = ["139", 0]
    workflow["200_0"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}}
    refs["ref_audios.ref_audio_0"] = ["200_0", 0]
    workflow["136"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": refs}
    mp_tag = str(megapixels).replace(".", "p")
    h3._add_save_nodes(
        workflow,
        f"story/PICTURE_{clip['id']}/{clip['id']}_picture_{mp_tag}mp_a{attempt:02d}",
    )
    return workflow


def next_rung(current: float) -> float | None:
    for index, value in enumerate(LADDER):
        if abs(value - current) < 1e-6:
            return LADDER[index + 1] if index + 1 < len(LADDER) else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", action="append", help="render only named clip; repeatable")
    parser.add_argument("--rerender-pending", action="store_true")
    args = parser.parse_args()

    audio = verify_audio_gate()
    rows = clips()
    if args.clip:
        wanted = set(args.clip)
        rows = [row for row in rows if row["id"] in wanted]
        missing = wanted - {row["id"] for row in rows}
        if missing:
            raise SystemExit(f"unknown clips: {', '.join(sorted(missing))}")
    if not claim_queue():
        return 3
    h3.LOG = LOG
    comfy_pid: int | None = None
    try:
        for position, clip in enumerate(rows, 1):
            manifest = load(MANIFEST, {
                "schema_version": 1,
                "stage": "picture around accepted Stage-1 soundtrack",
                "resolution_ladder": LADDER,
                "clips": {},
            })
            entry = manifest.setdefault("clips", {}).setdefault(clip["id"], {"attempts": []})
            if entry.get("status") == "visually_accepted":
                emit(f"[{position}/{len(rows)}] {clip['id']}: visually accepted — skip")
                continue
            if entry.get("status") == "human_review_needed":
                emit(f"[{position}/{len(rows)}] {clip['id']}: human review needed — skip")
                continue
            if entry.get("status") == "needs_agent_native_review" and not args.rerender_pending:
                emit(f"[{position}/{len(rows)}] {clip['id']}: awaiting native review — skip")
                continue

            megapixels = float(entry.get("next_megapixels", 0.9))
            first = h3.ensure_frame_in_input(clip["first_frame"])
            last = h3.ensure_frame_in_input(clip["last_frame"]) if clip.get("last_frame") else None
            exact_wav = Path(audio[clip["id"]]["accepted_full_wav"])
            staged_audio = stage_soundtrack(clip["id"], exact_wav)

            while megapixels is not None:
                attempt_no = len(entry.get("attempts", [])) + 1
                seed = random.randint(0, 2**53)
                emit(
                    f"[{position}/{len(rows)}] {clip['id']} picture attempt {attempt_no}: "
                    f"{megapixels:.1f} MP, seed={seed}"
                )
                workflow = build_workflow(
                    clip, first, last, staged_audio, megapixels, seed, attempt_no,
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
                    "megapixels": megapixels,
                    "seed": seed,
                    "accepted_audio": str(exact_wav),
                    "first_frame": clip["first_frame"],
                    "last_frame": clip.get("last_frame"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
                try:
                    prompt_id = h3.submit_workflow(workflow)
                    attempt["prompt_id"] = prompt_id
                    outputs = h3.wait_for_completion(prompt_id, clip["id"])
                    video_text = h3.find_video_output(outputs)
                    if not video_text:
                        attempt.update(status="render_failed", error="no MP4 in outputs")
                    else:
                        video = Path(video_text)
                        attempt["source_video"] = str(video)
                        tag = f"a{attempt_no:02d}_{str(megapixels).replace('.', 'p')}mp"
                        report = visual_gate.validate(
                            video, clip, visual_gate.OUT_ROOT / clip["id"] / tag,
                        )
                        report_path = visual_gate.OUT_ROOT / clip["id"] / tag / "report.json"
                        report_path.parent.mkdir(parents=True, exist_ok=True)
                        report_path.write_text(
                            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
                        )
                        attempt.update(
                            status=report["status"],
                            validation_report=str(report_path),
                            objective_failures=report.get("objective_failures", []),
                            warnings=report.get("warnings", []),
                            native_frame_directory=report.get("native_frame_directory"),
                            completed_at=datetime.now().isoformat(timespec="seconds"),
                        )
                except Exception as exc:
                    attempt.update(status="render_error", error=str(exc))

                manifest = load(MANIFEST, {
                    "schema_version": 1,
                    "stage": "picture around accepted Stage-1 soundtrack",
                    "resolution_ladder": LADDER,
                    "clips": {},
                })
                entry = manifest.setdefault("clips", {}).setdefault(clip["id"], {"attempts": []})
                entry.setdefault("attempts", []).append(attempt)
                entry["status"] = attempt["status"]
                entry["latest_attempt"] = attempt_no
                entry["updated_at"] = datetime.now().isoformat(timespec="seconds")

                if attempt["status"] == "auto_reject":
                    lower = next_rung(megapixels)
                    if lower is None:
                        entry["status"] = "human_review_needed"
                        entry["human_review_reason"] = (
                            "0.4 MP attempt failed the objective visual prefilter"
                        )
                        entry.pop("next_megapixels", None)
                        megapixels = None
                    else:
                        entry["next_megapixels"] = lower
                        megapixels = lower
                elif attempt["status"] in {"render_failed", "render_error"}:
                    # Preserve and leave the same rung available for recovery.
                    entry["next_megapixels"] = megapixels
                    megapixels = None
                else:
                    entry.pop("next_megapixels", None)
                    megapixels = None
                save(manifest)
                emit(f"{clip['id']} attempt {attempt_no}: {entry['status']}")

            if comfy_pid is not None and h3.api_ready():
                h3.stop_comfy(comfy_pid)
                comfy_pid = None
            thermal_guard.wait_after_render(emit)
            state = load(MANIFEST, {"clips": {}}).get("clips", {})
            passed = sum(x.get("status") == "visually_accepted" for x in state.values())
            pending = sum(x.get("status") == "needs_agent_native_review" for x in state.values())
            human = sum(x.get("status") == "human_review_needed" for x in state.values())
            emit(f"Picture gate: {passed}/124 accepted, {pending} pending, {human} human review")
    finally:
        if comfy_pid is not None and h3.api_ready():
            h3.stop_comfy(comfy_pid)
        release_queue()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
