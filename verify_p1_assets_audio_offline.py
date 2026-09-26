#!/usr/bin/env python3
"""Offline continuity + audio timeline checks (audit §5 + §10).

Simulates:
  - parent SELECTED attempt → boundary PNG hash recorded
  - child request binds first_frame correctly
  - intentional parent switch invalidates child
  - required dialogue + silent mode conflict fails gate
  - audio sample/frame alignment math (24fps ↔ 48kHz = 2000)

No ComfyUI / GPU / network.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HANDOFF = ROOT / "handoff"
LOCAL_AGENT = HANDOFF / "local_agent"
sys.path.insert(0, str(HANDOFF))
sys.path.insert(0, str(LOCAL_AGENT))

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {name}")
    else:
        msg = f"FAIL: {name}" + (f" — {detail}" if detail else "")
        print(f"  {msg}")
        FAILURES.append(msg)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tiny_png(path: Path) -> None:
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    )


def test_assets_continuity() -> None:
    print("\n[§5] canonical assets + continuity bind")
    ca = load_module("canonical_assets", HANDOFF / "canonical_assets.py")
    store = load_module("production_store", HANDOFF / "production_store.py")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        png = td_path / "boundary.png"
        _tiny_png(png)

        reg = ca.AssetRegistry()
        reg.upsert(
            ca.CanonicalAsset(
                asset_id="char_a",
                role="identity",
                version="1",
                path=str(td_path / "char.png"),
                content_hash="ab" * 32,
                label="A",
            )
        )
        check("identity asset stored", reg.get("char_a") is not None)
        check("role filter", len(reg.list_by_role("identity")) == 1)

        # broken parent rejected
        try:
            ca.assert_parent_usable(
                parent_state="RENDERED",
                parent_attempt_id="att_x",
                boundary=None,
            )
            check("reject non-SELECTED parent", False)
        except ca.ContinuityError:
            check("reject non-SELECTED parent", True)

        boundary = ca.record_boundary_from_png(
            reg,
            attempt_id="att_parent",
            shot_id="C001",
            frame_index=123,
            png_path=png,
            source_artifact=str(td_path / "clean.mp4"),
        )
        check("boundary hash recorded", len(boundary.content_hash) == 64)
        check("boundary frame index", boundary.frame_index == 123)

        # reject VHS-after extraction
        try:
            ca.record_boundary_from_png(
                reg,
                attempt_id="att_bad",
                shot_id="C001",
                frame_index=0,
                png_path=png,
                source_artifact="x",
                extracted_before_vhs=False,
            )
            check("reject post-VHS boundary", False)
        except ca.ContinuityError:
            check("reject post-VHS boundary", True)

        plan = ca.build_continuity_bind_plan(
            reg,
            parent_attempt_id="att_parent",
            parent_state="SELECTED",
            edit_relationship="continuous",
            upload_prefix="C001",
        )
        check("comfy upload name", plan.comfy_upload_name == "C001_boundary.png")
        check("plan frame index", plan.frame_index == 123)

        graph = {
            "20": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "x"}},
        }
        ca.apply_bind_plan_to_graph(graph, plan)
        check(
            "child first_frame bind",
            graph["20"]["inputs"]["first_frame"] == ["1001", 0],
        )
        check(
            "LoadImage upload name",
            graph["1001"]["inputs"]["image"] == "C001_boundary.png",
        )

        # parent switch invalidates child
        check(
            "parent switch invalidates child",
            ca.parent_switch_invalidates_child(
                bound_parent_attempt_id="att_parent",
                current_selected_parent_attempt_id="att_other",
            )
            is True,
        )
        check(
            "same parent keeps child",
            ca.parent_switch_invalidates_child(
                bound_parent_attempt_id="att_parent",
                current_selected_parent_attempt_id="att_parent",
            )
            is False,
        )

        # edit relationship table
        strat = ca.edit_strategy("new_scene")
        check("new_scene reanchors", strat["reanchor_canonical"] is True)
        check("continuous binds boundary", ca.edit_strategy("continuous")["bind_parent_boundary"])

        # production_store boundary wiring
        db = store.connect(":memory:", memory=True)
        store.ensure_shot(db, "C001")
        aid = store.create_attempt(
            db, shot_id="C001", input_payload={"p": 1}, state="READY"
        )
        store.set_attempt_state(
            db, aid, "RENDERED",
            artifact_path=str(td_path / "clean.mp4"),
            artifact_sha256="cd" * 32,
        )
        store.mark_qa_flags(db, aid, technical_pass=True, visual_pass=True, audio_pass=True)
        store.select_attempt(db, "C001", 0, aid)
        store.record_boundary_on_attempt(
            db, aid,
            frame_index=123,
            png_path=str(png),
            content_hash=boundary.content_hash,
            source_artifact=str(td_path / "clean.mp4"),
        )
        b2 = store.get_selected_boundary(db, "C001")
        check("store selected boundary", b2 is not None and b2["frame_index"] == 123)
        store.store_shot_dialogue(
            db, aid,
            [{"speaker_id": "a", "text": "hello", "voice_asset_id": "voice:a@1"}],
            audio_mode="visible_dialogue",
            voice_asset_ids=["voice:a@1"],
        )
        meta = json.loads(
            db.execute("SELECT meta_json FROM attempts WHERE attempt_id=?", (aid,))
            .fetchone()["meta_json"]
        )
        check("dialogue stored with speaker_id", meta["dialogue_lines"][0]["speaker_id"] == "a")


def test_audio_timeline() -> None:
    print("\n[§10] audio timeline + voice assets + modes")
    at = load_module("audio_timeline", HANDOFF / "audio_timeline.py")
    dv = load_module("dynamic_voice", LOCAL_AGENT / "dynamic_voice.py")

    check("samples/frame == 2000", at.SAMPLES_PER_FRAME == 2000)
    check("124 frames → samples", at.frames_to_samples(124) == 124 * 2000)
    check("samples → frames roundtrip", at.samples_to_frames(248000) == 124)
    try:
        at.samples_to_frames(2001)
        check("misaligned samples rejected", False)
    except at.AudioTimelineError:
        check("misaligned samples rejected", True)

    at.assert_frame_sample_alignment(10, 20000)
    check("alignment assert ok", True)

    # dialogue + silent conflict
    try:
        at.gate_shot_audio_mode(
            mode="silent_abstract",
            dialogue_lines=[{"speaker_id": "a", "text": "hi"}],
            intentional_silence=True,
        )
        check("dialogue+silent fails", False)
    except at.AudioTimelineError:
        check("dialogue+silent fails", True)

    try:
        at.ShotAudioPlan(
            shot_id="C002",
            mode="silent_abstract",
            dialogue_lines=[],
            intentional_silence=False,
        )
        check("silent requires intentional flag", False)
    except at.AudioTimelineError:
        check("silent requires intentional flag", True)

    plan_ok = at.ShotAudioPlan(
        shot_id="C002",
        mode="visible_dialogue",
        dialogue_lines=[at.DialogueLineRecord(speaker_id="a", text="hi")],
        stems=[at.AudioStem(kind="dialogue", start_frame=0, end_frame=48)],
    )
    check("visible_dialogue plan ok", plan_ok.mode == "visible_dialogue")
    check("stem sample align", plan_ok.stems[0].end_sample == 48 * 2000)

    voice = at.VoiceAssetRecord(
        job_id="job1",
        speaker_id="a",
        voice_version="2",
        reference_audio_hash="aa" * 32,
        reference_transcript_hash="bb" * 32,
        tts_backend="local_f5",
        checkpoint_hash="cc" * 32,
        language="en",
        delivery_params={"speed": 1.0},
    )
    check("versioned voice asset id", "voice:job1:a@2" == voice.asset_id)

    tl = at.AudioTimeline(job_id="job1")
    tl.register_voice(voice)
    tl.set_shot_plan(plan_ok)
    dumped = tl.to_dict()
    check("timeline stems separate", "dialogue" in {s["kind"] for s in dumped["shots"]["C002"]["stems"]})

    # dynamic_voice VoiceAsset + local_f5 helper
    va = dv.VoiceAsset(
        job_id="job1",
        speaker_id="a",
        voice_version="2",
        reference_audio_hash="aa" * 32,
        reference_transcript_hash="bb" * 32,
        tts_backend="local_f5",
        checkpoint_hash="ckpt",
        reference_audio_path="/tmp/ref.wav",
        reference_transcript="hello ref",
    )
    args = dv.build_local_f5_infer_args(
        voice=va, gen_text="Did you hear that?", provider="local_f5"
    )
    argv = args.to_argv()
    check("f5 cli has --ref_audio", "--ref_audio" in argv and "/tmp/ref.wav" in argv)
    check("f5 cli has --ref_text", "--ref_text" in argv and "hello ref" in argv)
    check("f5 cli has --gen_text", "--gen_text" in argv)

    try:
        dv.build_local_f5_infer_args(
            voice=va, gen_text="x", provider="fish_audio"
        )
        check("f5 helper refuse fish provider", False)
    except dv.VoiceAudioGateError:
        check("f5 helper refuse fish provider", True)

    try:
        dv.gate_shot_audio_mode(
            mode="silent_abstract",
            dialogue_lines=[{"speaker_id": "a", "text": "nope"}],
            intentional_silence=True,
        )
        check("dv dialogue+silent fails", False)
    except dv.VoiceAudioGateError:
        check("dv dialogue+silent fails", True)

    lines = dv.store_dialogue_lines(
        [{"speaker_id": "bob", "text": "exact text", "voice_asset_id": va.asset_id}]
    )
    check("store_dialogue speaker_id", lines[0]["speaker_id"] == "bob")
    check("DialogueLine.speaker_id prop", dv.DialogueLine(speaker="x", text="y").speaker_id == "x")


def test_continuity_dry_run() -> None:
    print("\n[§13] continuity_dry_run fake job (no Comfy)")
    cdr = load_module("continuity_dry_run", HANDOFF / "continuity_dry_run.py")
    with tempfile.TemporaryDirectory() as td:
        job = Path(td) / "fake_job"
        report = cdr.run_dry_run(job)
        check("dry_run wrote report", (job / "dry_run_report.json").is_file())
        check("comfy not called", report["comfy_called"] is False)
        check(
            "first_frame linked",
            report["graph_first_frame"] == ["1001", 0],
        )
        check("parent switch flag", report["parent_switch_invalidates_child"] is True)
        check("timeline json", (job / "audio" / "timeline.json").is_file())
        check("registry json", (job / "assets" / "registry.json").is_file())


def test_no_windows_paths_in_new_modules() -> None:
    print("\n[hygiene] no Windows paths in new modules")
    # Build needles without embedding drive paths in this file's source.
    needle_drive = chr(65) + ":\\"
    needle_users = "Users" + chr(92) + "rhine"
    for rel in (
        "handoff/canonical_assets.py",
        "handoff/audio_timeline.py",
        "handoff/continuity_dry_run.py",
        "handoff/local_agent/dynamic_voice.py",
        "handoff/production_store.py",
        "handoff/master_batch_runner.py",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        bad = (needle_drive in text) or (needle_users in text) or ("ComfyUI-Shared" in text)
        check(f"no Windows path in {rel}", not bad)


def test_master_batch_imports() -> None:
    print("\n[wiring] master_batch_runner can see new helpers")
    src = (HANDOFF / "master_batch_runner.py").read_text(encoding="utf-8")
    check("mentions canonical/audio helpers", "canonical_assets" in src or "audio_timeline" in src)


def main() -> int:
    print("=== verify_p1_assets_audio_offline ===")
    test_assets_continuity()
    test_audio_timeline()
    test_continuity_dry_run()
    test_no_windows_paths_in_new_modules()
    test_master_batch_imports()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(" ", f)
        return 1
    print("ALL ASSETS/AUDIO OFFLINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
