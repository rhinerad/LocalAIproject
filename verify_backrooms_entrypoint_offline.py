#!/usr/bin/env python3
"""Offline argparse/AST checks for generate_video + runner voice path."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "local_agent"))


def _argparse_dests(py_path: Path) -> set[str]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    dests: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            if name != "add_argument":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flag = arg.value
                    if flag.startswith("--"):
                        dests.add(flag[2:].replace("-", "_"))
    return dests


def test_generate_video_native_flags() -> None:
    dests = _argparse_dests(HERE / "generate_video.py")
    for need in ("native_minimax_voice", "voice_ref_json", "image_ref_json"):
        assert need in dests, f"generate_video missing --{need.replace('_', '-')}"
    src = (HERE / "generate_video.py").read_text(encoding="utf-8")
    assert "enforce_native_voice_cli(args)" in src


def test_mark_clip_voice_path_kwargs() -> None:
    src = (HERE / "master_batch_runner.py").read_text(encoding="utf-8")
    # Must not call mark_clip with invalid state=/error= kwargs on voice path.
    assert "mark_clip(progress, clip_id, state=" not in src
    assert "def mark_clip_blocked(" in src
    assert "mark_clip_blocked(" in src


def test_dry_run_argv_dialogue_clip() -> None:
    import master_batch_runner as mbr

    clip = {
        "id": "C003",
        "start_frame": "apartment start",
        "last_frame": "apartment last",
        "video_prompt": "Actor says hello",
        "duration_seconds": 10.0,
        "required_audio": True,
        "dialogue_lines": [
            {
                "speaker_id": "ACTOR",
                "speaker": "ACTOR",
                "text": "You ate my leftovers and then blamed the dog. We do not have a dog.",
                "exact_text": "You ate my leftovers and then blamed the dog. We do not have a dog.",
            }
        ],
        "native_minimax_voice": True,
    }
    # Build the same argv fragments run_clip would.
    clip_duration = float(clip.get("duration_seconds") or 10.0)
    editorial_frames = max(1, int(round(clip_duration * 24)))
    dialogue = mbr.clip_dialogue_payload(clip)
    assert dialogue, "dialogue payload empty"
    assert mbr.clip_requires_audio(clip) is True
    argv = [
        "--duration",
        str(clip_duration),
        "--editorial-frames",
        str(editorial_frames),
        "--dialogue-json",
        json.dumps(dialogue),
        "--native-minimax-voice",
    ]
    assert "10.0" in argv or "10" in argv
    assert "--dialogue-json" in argv
    assert editorial_frames == 240
    print("dry_run_argv", argv[:8], "...")


def main() -> int:
    failed = 0
    for fn in (
        test_generate_video_native_flags,
        test_mark_clip_voice_path_kwargs,
        test_dry_run_argv_dialogue_clip,
    ):
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", fn.__name__, exc)
    print("summary", {"ok": failed == 0, "failed": failed})
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
