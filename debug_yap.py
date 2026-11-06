#!/usr/bin/env python3
"""Dump the raw local Qwen 1.5b DSPy output for GeneralizedVideoDirector."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from pprint import pprint


ROOT = Path(__file__).resolve().parent
LOCAL_AGENT = ROOT / "local_agent"
for path in (ROOT, LOCAL_AGENT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _print_history(lm, n: int = 1) -> None:
    print("\n=== lm.inspect_history(n=1) ===", flush=True)
    try:
        lm.inspect_history(n=n)
    except Exception as exc:
        print(f"inspect_history failed: {type(exc).__name__}: {exc}", flush=True)

    print("\n=== raw lm.history[-1] ===", flush=True)
    history = getattr(lm, "history", None)
    if not history:
        print("No lm.history entries found.", flush=True)
        return
    last = history[-1]
    try:
        print(json.dumps(last, indent=2, ensure_ascii=False, default=str), flush=True)
    except Exception:
        pprint(last)

    print("\n=== best-effort completion text ===", flush=True)
    if isinstance(last, dict):
        for key in ("response", "completion", "outputs", "output", "text"):
            if key in last:
                print(f"[{key}]", flush=True)
                print(last[key], flush=True)
        messages = last.get("messages")
        if messages:
            print("[messages]", flush=True)
            print(json.dumps(messages, indent=2, ensure_ascii=False, default=str), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one GeneralizedVideoDirector dspy.Predict call against the "
            "same local qwen2.5:1.5b LM path used by dspy_orchestrator.py, "
            "then dump the raw LM history."
        )
    )
    parser.add_argument(
        "--prompt",
        default="A drone flying over a cliff",
        help="Single user_intent to send to the director signature.",
    )
    args = parser.parse_args(argv)

    import dspy
    from dspy.dsp.utils.settings import settings

    import dspy_optimizer
    import dspy_orchestrator
    import generalized_video_director as gvd

    print("Configuring local DSPy video LM exactly through dspy_optimizer.configure_video_lms()...", flush=True)
    task_lm, _prompt_lm = dspy_optimizer.configure_video_lms()
    print(f"Initial task LM: {getattr(task_lm, 'model', task_lm)!r}", flush=True)

    print("Applying dspy_orchestrator.harden_student_lm()...", flush=True)
    task_lm = dspy_orchestrator.harden_student_lm(task_lm)
    active_lm = getattr(settings, "lm", None) or task_lm
    print(f"Active task LM: {getattr(active_lm, 'model', active_lm)!r}", flush=True)
    print(f"Active task LM kwargs: {getattr(active_lm, 'kwargs', None)!r}", flush=True)

    signature = gvd.director_signature_class()
    predictor = dspy.Predict(signature)

    inputs = {
        "user_intent": args.prompt,
        "category": "drone_high_kinematics",
        "vbench_focus": "dynamic_degree, scene, motion_smoothness",
        "duration_seconds": 8.0,
        "constraints": "Continuous aerial move, no still photograph, no text, no watermark.",
    }
    print("\n=== DSPy Predict inputs ===", flush=True)
    print(json.dumps(inputs, indent=2), flush=True)

    try:
        pred = predictor(**inputs)
        print("\n=== parsed DSPy prediction ===", flush=True)
        print(pred, flush=True)
        try:
            print(json.dumps(pred.toDict(), indent=2, ensure_ascii=False, default=str), flush=True)
        except Exception:
            pass
    except Exception:
        print("\n=== predictor raised ===", flush=True)
        traceback.print_exc()
    finally:
        _print_history(active_lm, n=1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
