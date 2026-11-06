#!/usr/bin/env python3
"""Offline P0 correctness checks — no ComfyUI / GPU / network.

Proves:
  - duration helper (h3_generation_frames)
  - image-binding args present on generate_video
  - dialogue passthrough symbols
  - audio gate fail-closed
  - done-before-QA rejected (resume / already_done)
"""
from __future__ import annotations

import ast
import importlib.util
import json
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
    # Register before exec so dataclasses / typing can resolve cls.__module__
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def source_of(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def ast_has_arg(src: str, arg_name: str) -> bool:
    """True if argparse add_argument mentions --arg-name or function has that param."""
    needle = f"--{arg_name}" if not arg_name.startswith("--") else arg_name
    if needle in src:
        return True
    # also accept pythonic kw-only names
    py = arg_name.lstrip("-").replace("-", "_")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.arguments):
            for a in list(node.args) + list(node.kwonlyargs):
                if a.arg == py:
                    return True
        if isinstance(node, ast.FunctionDef) and node.name in {
            "submit_comfy",
            "build_minimax_graph",
            "generate_minimax_clip",
            "apply_dynamic_voice_routing",
        }:
            for a in list(node.args.args) + list(node.args.kwonlyargs):
                if a.arg == py:
                    return True
    return False


def test_duration_helper() -> None:
    print("\n[P0-2] duration / h3_generation_frames")
    gvd = load_module("gvd_core", HANDOFF / "gvd_core.py")
    h3 = gvd.h3_generation_frames
    check("h3(120)==124", h3(120) == 124)
    check("h3(192)==192", h3(192) == 192)
    check("h3(240)==243", h3(240) == 243)
    check("h3(124)==124", h3(124) == 124)
    try:
        h3(363)
        check("h3(363) raises", False, "oversized accepted")
    except ValueError as exc:
        check("h3(363) raises", "Split" in str(exc) or "split" in str(exc).lower())
    ed, gen = gvd.editorial_vs_generation_frames(120)
    check("editorial preserved separately", ed == 120 and gen == 124)
    # Symbols present in orchestrator / generate_video
    orch_src = source_of("handoff/local_agent/dspy_orchestrator.py")
    gv_src = source_of("handoff/generate_video.py")
    check("orchestrator defines/imports h3_generation_frames", "h3_generation_frames" in orch_src)
    check("orchestrator carries editorial_frames", "editorial_frames" in orch_src)
    check("orchestrator carries generation_frames", "generation_frames" in orch_src)
    check("generate_video has --editorial-frames", "--editorial-frames" in gv_src)
    check("generate_video has --generation-frames", "--generation-frames" in gv_src)
    check("MINIMAX_NUM_FRAMES not sole forced length", "resolve_generation_frames" in orch_src)


def test_image_binding_args() -> None:
    print("\n[P0-1] frame binding args + LoadImage wiring")
    gv_src = source_of("handoff/generate_video.py")
    orch_src = source_of("handoff/local_agent/dspy_orchestrator.py")
    master_src = source_of("handoff/master_batch_runner.py")
    check("generate_video --start-frame-path", "--start-frame-path" in gv_src)
    check("generate_video --end-frame-path", "--end-frame-path" in gv_src)
    check("submit_comfy accepts start_frame_path", ast_has_arg(gv_src, "start-frame-path") or "start_frame_path" in gv_src)
    check("bind_h3_image_frames present", "def bind_h3_image_frames" in orch_src)
    check("LoadImage binding", '"LoadImage"' in orch_src or "'LoadImage'" in orch_src)
    check("first_frame field wiring", "first_frame" in orch_src and "1001" in orch_src)
    check("last_frame field wiring", "last_frame" in orch_src and "1002" in orch_src)
    check("master_batch_runner passes --start-frame-path", "--start-frame-path" in master_src)
    check("master_batch_runner passes --end-frame-path", "--end-frame-path" in master_src)
    # Functional bind test without Comfy
    orch_path = LOCAL_AGENT / "dspy_orchestrator.py"
    # Extract bind_h3_image_frames by exec'ing a minimal slice — import full orch needs deps.
    # Instead re-implement call via compiling just the function from source using gvd + copy.
    # Simpler: exec bind function from a stub.
    ns: dict = {}
    # Pull function text roughly
    start = orch_src.index("def bind_h3_image_frames(")
    end = orch_src.index("\ndef resolve_generation_frames(")
    stub = "from pathlib import Path\n" + orch_src[start:end]
    exec(stub, ns)
    graph = {
        "20": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {"prompt": "x", "length": 124},
        }
    }
    out = ns["bind_h3_image_frames"](
        graph, first_frame_path="audit_reference/shot001_start.png", last_frame_path="end.png"
    )
    check("bound first_frame link", out["20"]["inputs"]["first_frame"] == ["1001", 0])
    check("bound last_frame link", out["20"]["inputs"]["last_frame"] == ["1002", 0])
    check("LoadImage node 1001", out["1001"]["class_type"] == "LoadImage")
    check(
        "LoadImage image name",
        out["1001"]["inputs"]["image"] == "audit_reference/shot001_start.png",
    )


def test_dialogue_passthrough() -> None:
    print("\n[P0-3] dialogue passthrough symbols")
    gv_src = source_of("handoff/generate_video.py")
    orch_src = source_of("handoff/local_agent/dspy_orchestrator.py")
    master_src = source_of("handoff/master_batch_runner.py")
    batch_src = source_of("handoff/batch_run_backrooms_gvd.py")
    dv = load_module("dynamic_voice", LOCAL_AGENT / "dynamic_voice.py")
    check("generate_video --dialogue-json", "--dialogue-json" in gv_src)
    check("submit_comfy dialogue param", "dialogue:" in gv_src or "dialogue=" in gv_src)
    check("build_minimax_graph dialogue param", "dialogue:" in orch_src)
    check("generate_minimax_clip dialogue param", "dialogue:" in orch_src)
    check("master clip_dialogue_payload", "clip_dialogue_payload" in master_src)
    check("master passes --dialogue-json", "--dialogue-json" in master_src)
    check("batch extract_dialogue_array", "extract_dialogue_array" in batch_src)
    check("batch submit dialogue=", "dialogue=dialogue_payload" in batch_src)
    lines = dv.normalize_dialogue_array(
        [{"speaker": "A", "text": "Hello"}, {"speaker_id": "B", "text": "World"}]
    )
    check("typed dialogue normalize", len(lines) == 2 and lines[0].speaker == "A")
    check(
        "dialogue_to_speech_text",
        "A: Hello" in dv.dialogue_to_speech_text(lines),
    )
    arr = dv.extract_dialogue_array({"dialogue": [{"speaker": "C", "text": "Yo"}]})
    check("extract_dialogue_array structured", arr and arr[0].text == "Yo")


def test_voice_provider_identity() -> None:
    print("\n[P0-4] voice provider identity")
    dv = load_module("dynamic_voice", LOCAL_AGENT / "dynamic_voice.py")
    import os

    os.environ.pop("GVD_VOICE_PROVIDER", None)
    os.environ.pop("GVD_F5_TTS_CLASS", None)
    prov = dv.resolve_voice_provider(clip_id="C002", enable_voice=True)
    check("default provider is local_f5", prov == "local_f5")
    check("C001 is minimax_native", dv.resolve_voice_provider(clip_id="C001") == "minimax_native")
    os.environ["GVD_F5_TTS_CLASS"] = "FishAudioInstantVoiceClone"
    try:
        dv.resolve_voice_provider(clip_id="C002")
        check("Fish-as-F5 refused", False, "should have raised")
    except dv.VoiceAudioGateError as exc:
        check("Fish-as-F5 refused", "fish_audio" in str(exc).lower() or "Fish" in str(exc))
    finally:
        os.environ.pop("GVD_F5_TTS_CLASS", None)
    os.environ["GVD_VOICE_PROVIDER"] = "fish_audio"
    try:
        check(
            "explicit fish_audio allowed",
            dv.resolve_voice_provider(clip_id="C002") == "fish_audio",
        )
    finally:
        os.environ.pop("GVD_VOICE_PROVIDER", None)
    src = source_of("handoff/local_agent/dynamic_voice.py")
    check("never labels Fish as F5 in fish branch", "provider=fish_audio" in src)
    check("local_f5 path present", "provider=local_f5" in src or 'provider == "local_f5"' in src)


def test_audio_gate_fail_closed() -> None:
    print("\n[P0-5] audio gate fail-closed")
    dv = load_module("dynamic_voice", LOCAL_AGENT / "dynamic_voice.py")
    # Missing mux + required dialogue => silent => raise
    graph = {"1": {"class_type": "CLIPTextEncode", "inputs": {}}}
    try:
        dv.apply_dynamic_voice_routing(
            graph,
            clip_id="C002",
            dialogue=[{"speaker": "A", "text": "Need audio"}],
            enable_f5=True,
            voice_provider="local_f5",
            fail_closed=True,
        )
        check("missing mux fails closed", False, "should raise")
    except dv.VoiceAudioGateError:
        check("missing mux fails closed", True)
    # No dialogue required => silent ok
    g2 = {"39": {"class_type": "CreateVideo", "inputs": {"fps": 24}}}
    out = dv.apply_dynamic_voice_routing(
        g2,
        clip_id="C002",
        dialogue=[],
        enable_f5=True,
        voice_provider="none",
        fail_closed=True,
    )
    meta = (out.get("_meta") or {}).get("voice_routing") or {}
    check("no-dialogue silent allowed", meta.get("status") == "silent" and meta.get("audio_pass") is True)
    # assert_audio_gate direct
    bad = dv.VoiceRoutingResult(
        provider="local_f5", status="silent", reason="test", required_dialogue=True
    )
    try:
        dv.assert_audio_gate(bad)
        check("assert_audio_gate raises", False)
    except dv.VoiceAudioGateError:
        check("assert_audio_gate raises", True)
    orch_src = source_of("handoff/local_agent/dspy_orchestrator.py")
    check("orchestrator refuses silent retry when required", "VoiceAudioGateError" in orch_src)
    check("classify_voice_submit_error used", "classify_voice_submit_error" in orch_src)
    check(
        "required dialogue blocks silent retry",
        "required dialogue" in orch_src.lower() or "required_dialogue" in orch_src,
    )


def test_done_before_qa_rejected() -> None:
    print("\n[P0-6] done-before-QA / resume rejection")
    batch = load_module("batch_run_backrooms_gvd", HANDOFF / "batch_run_backrooms_gvd.py")
    master = load_module("master_batch_runner", HANDOFF / "master_batch_runner.py")
    with tempfile.TemporaryDirectory() as td:
        mp4 = Path(td) / "clip.mp4"
        mp4.write_bytes(b"x" * 20_000)
        # Legacy done + file must NOT count as selected
        legacy = {"status": "done", "video_path": str(mp4)}
        check("legacy done+file rejected by already_done", batch.already_done(legacy) is False)
        rendered = {
            "status": "rendered",
            "pipeline_state": "RENDERED",
            "video_path": str(mp4),
            "verified": False,
        }
        check("RENDERED rejected for resume", batch.already_done(rendered) is False)
        qa_pending = {
            "status": "qa_pending",
            "pipeline_state": "QA_PENDING",
            "video_path": str(mp4),
            "verified": False,
        }
        check("QA_PENDING rejected for resume", batch.already_done(qa_pending) is False)
        selected = {
            "status": "selected",
            "pipeline_state": "SELECTED",
            "video_path": str(mp4),
            "verified": True,
        }
        check("SELECTED accepted for resume", batch.already_done(selected) is True)

        # master_batch_runner is_clip_complete / is_clip_selected
        clip_legacy = {
            "master_batch": {
                "status": "complete",
                "video_path": str(mp4),
                "verified": False,
            }
        }
        check(
            "master rejects complete+file without QA",
            master.is_clip_complete(clip_legacy) is False,
        )
        clip_selected = {
            "master_batch": {
                "status": "selected",
                "pipeline_state": "SELECTED",
                "video_path": str(mp4),
                "verified": True,
            }
        }
        check(
            "master accepts SELECTED",
            master.is_clip_selected(clip_selected) is True,
        )
    batch_src = source_of("handoff/batch_run_backrooms_gvd.py")
    check("batch writes RENDERED before QA", "PIPELINE_RENDERED" in batch_src)
    check("batch writes QA_PENDING", "PIPELINE_QA_PENDING" in batch_src)
    check("batch writes SELECTED after QA", "PIPELINE_SELECTED" in batch_src)
    # Ensure we don't set status done before VLM anymore in the render path
    # (legacy_status alias after selection is ok)
    check(
        "no pre-QA status=done assignment in render block",
        '"status": "done"' not in batch_src.split("qa_required")[1].split("SELECTED")[0]
        if "qa_required" in batch_src
        else False,
    )


def main() -> int:
    print("P0 offline verification")
    print(f"ROOT={ROOT}")
    test_duration_helper()
    test_image_binding_args()
    test_dialogue_passthrough()
    test_voice_provider_identity()
    test_audio_gate_fail_closed()
    test_done_before_qa_rejected()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL P0 OFFLINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
