#!/usr/bin/env python3
"""One bounded live GVD render to verify the 2026-09-24 fixes end to end.

Checks, on a real FLUX.1 + MiniMax I2V render of Beta row GVD-D01:
  - the director runs with the restored DIRECTOR_SIGNATURE_INSTRUCTIONS
    (lost 2026-09-16 by _patch_safety3.py) and emits start/video prompts;
  - FLUX KSampler denoise is 1.0 (DENOISE_RANGE pin) and MiniMax node 35
    runs at MINIMAX_H3_STEPS (20), not the FLUX step_count.

Order: student LM first (keep_alive 0, unloads), then ComfyUI via
BackroomsWatch (queue owner, one-backend refusal, thermal guard, emergency
stop), then the production evaluate_live_candidate (render -> VLM judge).

Does NOT call _store(): gvd_live_metric_history.jsonl and every compiled
artifact under models/dspy_compiled are left untouched. Report goes to
runtime/dspy_opt/verify_20260924/.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

OUT = HERE / "runtime" / "dspy_opt" / "verify_20260924"
CLIP_ID = "GVD-D01"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"clip_id": CLIP_ID, "started": time.time()}
    report_path = OUT / "report.json"

    import dspy_optimizer
    import dspy_orchestrator as orch
    import generalized_video_director as gvd

    sig = gvd.director_signature_class()
    assert sig.instructions == gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS, "instructions not restored"
    report["instructions_chars"] = len(sig.instructions)
    report["minimax_h3_steps"] = orch.MINIMAX_H3_STEPS

    example = next(e for e in gvd.load_beta_trainset() if getattr(e, "id", None) == CLIP_ID)
    log(f"director: {CLIP_ID} with restored instructions ({len(sig.instructions)} chars)")
    task_lm, _ = dspy_optimizer.configure_video_lms()
    orch.harden_student_lm(task_lm)
    program = gvd.build_director_program()
    pred = program(**example.inputs())
    report["pred"] = {k: getattr(pred, k, None) for k in (
        "start_prompt", "video_prompt", "negative_prompt", "cfg_scale", "step_count")}
    report["hparams"], report["hparam_notes"] = orch.parse_director_hparams(pred)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log("director output: " + json.dumps(report["pred"], default=str)[:600])

    from backrooms_watch import BackroomsWatch

    watch = BackroomsWatch()
    watch.acquire()
    try:
        watch.restart("gvd_verify_20260924")
        log("ComfyUI owned on :8188; running evaluate_live_candidate")
        result = orch.evaluate_live_candidate(example, pred)
        report["result"] = {k: v for k, v in result.items() if k != "feedback_obj"}
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        log("FAILED: " + report["error"])
    finally:
        try:
            watch.close()
            log("ComfyUI stopped; queue owner released")
        except Exception as exc:
            report["close_error"] = f"{type(exc).__name__}: {exc}"
        report["finished"] = time.time()
        report["elapsed_s"] = round(report["finished"] - report["started"], 1)
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log(f"report: {report_path}")
    return 0 if "error" not in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
