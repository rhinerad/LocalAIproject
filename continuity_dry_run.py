#!/usr/bin/env python3
"""Offline continuity dry-run (audit §13-shaped fake job layout).

Walks a tiny job directory, records a parent boundary PNG hash, builds a
child ContinuityBindPlan, and writes a dry-run report. Never calls ComfyUI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_assets import (  # noqa: E402
    AssetRegistry,
    AssetRole,
    CanonicalAsset,
    EditRelationship,
    apply_bind_plan_to_graph,
    build_continuity_bind_plan,
    parent_switch_invalidates_child,
    record_boundary_from_png,
    reanchor_from_canonical_assets,
    sha256_file,
)
from audio_timeline import (  # noqa: E402
    AudioMode,
    AudioStem,
    AudioTimeline,
    DialogueLineRecord,
    ShotAudioPlan,
    VoiceAssetRecord,
    frames_to_samples,
    hash_text,
)


FAKE_JOB_LAYOUT = """\
{job_root}/
  job.json
  assets/
    characters/char_a_identity_v1.png
    locations/hallway_v1.png
    voices/speaker_a_ref.wav
    voices/speaker_a_ref.txt
  shots/
    C001/
      attempts/
        att_parent/
          clean_render.mp4          # placeholder (not decoded)
          boundary_frame.png        # lossless PNG used for continuity
      selected.json                 # {"attempt_id": "att_parent", "state": "SELECTED"}
    C002/
      plan.json                     # continuity + audio mode
  audio/
    timeline.json
  dry_run_report.json               # written by this script
"""


def seed_fake_job(job_root: Path) -> Path:
    """Create the audit §13-shaped tiny fake job if missing."""
    job_root = Path(job_root)
    (job_root / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (job_root / "assets" / "locations").mkdir(parents=True, exist_ok=True)
    (job_root / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    parent_dir = job_root / "shots" / "C001" / "attempts" / "att_parent"
    parent_dir.mkdir(parents=True, exist_ok=True)
    (job_root / "shots" / "C002").mkdir(parents=True, exist_ok=True)
    (job_root / "audio").mkdir(parents=True, exist_ok=True)

    # Minimal valid PNG (1x1) — lossless boundary stand-in
    png = parent_dir / "boundary_frame.png"
    if not png.is_file():
        # 1x1 PNG bytes
        png.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
            )
        )
    clean = parent_dir / "clean_render.mp4"
    if not clean.is_file():
        clean.write_bytes(b"FAKE_MP4_NOT_A_RENDER")

    char_png = job_root / "assets" / "characters" / "char_a_identity_v1.png"
    if not char_png.is_file():
        char_png.write_bytes(png.read_bytes())
    loc_png = job_root / "assets" / "locations" / "hallway_v1.png"
    if not loc_png.is_file():
        loc_png.write_bytes(png.read_bytes())

    ref_wav = job_root / "assets" / "voices" / "speaker_a_ref.wav"
    if not ref_wav.is_file():
        ref_wav.write_bytes(b"RIFF....WAVEfmt ")  # stub
    ref_txt = job_root / "assets" / "voices" / "speaker_a_ref.txt"
    ref_txt.write_text("hello from the hallway\n", encoding="utf-8")

    selected = {
        "attempt_id": "att_parent",
        "shot_id": "C001",
        "state": "SELECTED",
        "artifact": str(clean),
    }
    (job_root / "shots" / "C001" / "selected.json").write_text(
        json.dumps(selected, indent=2) + "\n", encoding="utf-8"
    )

    plan = {
        "shot_id": "C002",
        "continuity": {
            "mode": "continuous",
            "parent_attempt_id": "att_parent",
            "edit_relationship": EditRelationship.CONTINUOUS.value,
            "canonical_asset_ids": ["char_a", "loc_hallway"],
        },
        "audio": {
            "mode": AudioMode.VISIBLE_DIALOGUE.value,
            "dialogue_lines": [
                {"speaker_id": "speaker_a", "text": "Did you hear that?"}
            ],
        },
        "duration_frames": 124,
    }
    (job_root / "shots" / "C002" / "plan.json").write_text(
        json.dumps(plan, indent=2) + "\n", encoding="utf-8"
    )

    job_meta = {"job_id": job_root.name, "layout": "audit_section_13_tiny"}
    (job_root / "job.json").write_text(
        json.dumps(job_meta, indent=2) + "\n", encoding="utf-8"
    )
    return job_root


def run_dry_run(job_root: Path) -> dict:
    job_root = Path(job_root)
    if not (job_root / "job.json").is_file():
        seed_fake_job(job_root)

    job = json.loads((job_root / "job.json").read_text(encoding="utf-8"))
    job_id = str(job.get("job_id") or job_root.name)
    selected = json.loads(
        (job_root / "shots" / "C001" / "selected.json").read_text(encoding="utf-8")
    )
    child_plan = json.loads(
        (job_root / "shots" / "C002" / "plan.json").read_text(encoding="utf-8")
    )

    registry = AssetRegistry()
    char_path = job_root / "assets" / "characters" / "char_a_identity_v1.png"
    loc_path = job_root / "assets" / "locations" / "hallway_v1.png"
    registry.upsert(
        CanonicalAsset(
            asset_id="char_a",
            role=AssetRole.IDENTITY.value,
            version="1",
            path=str(char_path),
            content_hash=sha256_file(char_path),
            label="Character A",
        )
    )
    registry.upsert(
        CanonicalAsset(
            asset_id="loc_hallway",
            role=AssetRole.LOCATION.value,
            version="1",
            path=str(loc_path),
            content_hash=sha256_file(loc_path),
            label="Hallway",
        )
    )

    boundary_png = (
        job_root / "shots" / "C001" / "attempts" / "att_parent" / "boundary_frame.png"
    )
    boundary = record_boundary_from_png(
        registry,
        attempt_id=selected["attempt_id"],
        shot_id="C001",
        frame_index=123,
        png_path=boundary_png,
        source_artifact=str(
            job_root / "shots" / "C001" / "attempts" / "att_parent" / "clean_render.mp4"
        ),
    )

    bind = build_continuity_bind_plan(
        registry,
        parent_attempt_id=selected["attempt_id"],
        parent_state=selected["state"],
        edit_relationship=child_plan["continuity"]["edit_relationship"],
        upload_prefix="C001",
    )

    # Fake H3 graph bind (offline)
    graph = {
        "20": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "cont"}},
    }
    apply_bind_plan_to_graph(graph, bind)

    # Re-anchor assets available at planned cuts
    anchors = reanchor_from_canonical_assets(
        registry, child_plan["continuity"]["canonical_asset_ids"]
    )

    # Audio timeline
    ref_txt = (job_root / "assets" / "voices" / "speaker_a_ref.txt").read_text(
        encoding="utf-8"
    ).strip()
    ref_wav = job_root / "assets" / "voices" / "speaker_a_ref.wav"
    voice = VoiceAssetRecord(
        job_id=job_id,
        speaker_id="speaker_a",
        voice_version="1",
        reference_audio_hash=sha256_file(ref_wav),
        reference_transcript_hash=hash_text(ref_txt),
        tts_backend="local_f5",
        checkpoint_hash="ckpt_stub",
        language="en",
        delivery_params={"speed": 1.0},
    )
    timeline = AudioTimeline(job_id=job_id)
    timeline.register_voice(voice)
    duration = int(child_plan.get("duration_frames") or 124)
    dialogue = [
        DialogueLineRecord.from_dict(x)
        for x in child_plan["audio"]["dialogue_lines"]
    ]
    timeline.set_shot_plan(
        ShotAudioPlan(
            shot_id="C002",
            mode=child_plan["audio"]["mode"],
            dialogue_lines=dialogue,
            stems=[
                AudioStem(kind="dialogue", start_frame=0, end_frame=duration),
                AudioStem(kind="ambience", start_frame=0, end_frame=duration),
            ],
            voice_asset_ids=[voice.asset_id or ""],
        )
    )
    (job_root / "audio" / "timeline.json").write_text(
        json.dumps(timeline.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    registry.save_json(job_root / "assets" / "registry.json")

    # Simulate intentional parent switch invalidation
    invalidated = parent_switch_invalidates_child(
        bound_parent_attempt_id=bind.parent_attempt_id,
        current_selected_parent_attempt_id="att_other_parent",
    )

    report = {
        "job_id": job_id,
        "layout_doc": FAKE_JOB_LAYOUT.replace("{job_root}", str(job_root)),
        "parent": {
            "attempt_id": selected["attempt_id"],
            "state": selected["state"],
            "boundary": boundary.to_dict(),
        },
        "child_bind": bind.to_dict(),
        "graph_first_frame": graph["20"]["inputs"].get("first_frame"),
        "load_image": graph.get("1001"),
        "canonical_anchors": [a.to_dict() for a in anchors],
        "audio_samples_for_duration": frames_to_samples(duration),
        "parent_switch_invalidates_child": invalidated,
        "comfy_called": False,
    }
    out = job_root / "dry_run_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--job-root",
        type=Path,
        default=ROOT.parent / "ref_outputs" / "fake_job_section13",
        help="Tiny fake job directory (created if missing)",
    )
    parser.add_argument(
        "--print-layout",
        action="store_true",
        help="Print the expected layout and exit",
    )
    args = parser.parse_args(argv)
    if args.print_layout:
        print(FAKE_JOB_LAYOUT.replace("{job_root}", str(args.job_root)))
        return 0
    report = run_dry_run(args.job_root)
    print(json.dumps({
        "ok": True,
        "job_root": str(args.job_root),
        "boundary_hash": report["parent"]["boundary"]["content_hash"][:16] + "…",
        "comfy_upload_name": report["child_bind"]["comfy_upload_name"],
        "first_frame_link": report["graph_first_frame"],
        "parent_switch_invalidates_child": report["parent_switch_invalidates_child"],
        "comfy_called": report["comfy_called"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
