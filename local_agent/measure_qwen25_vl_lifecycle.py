#!/usr/bin/env python3
"""Opt-in lifecycle measurements for the exact lazy Qwen2.5-VL Caption V4 pair.

By default this prints the required safe invocation and never contacts a model.
``--execute`` is required for a model load and always releases the runtime in a
``finally`` block. Reports contain timing/VRAM metadata and a hash only—never
caption text or an input path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# These modules deliberately remain unimported until ``--execute``. Importing
# media tooling can initialize optional runtime dependencies; plan-only mode
# must be a zero-model, zero-runtime action.
caps = None
media_tools = None
router = None


def _snapshot() -> dict:
    used_mb, processes = router.gpu_memory()
    return {"used_mb": used_mb, "processes": processes}


def _caption(image: Path, prompt: str) -> dict:
    result = json.loads(media_tools._run_vision_gpu(
        [image], prompt, caps.QWEN25_VL_MODEL, router.GPU_HOST,
    ))
    analysis = str(result.get("analysis") or "")
    return {
        "available": bool(result.get("available")),
        "runtime": result.get("runtime"),
        "model": result.get("model"),
        "analysis_nonempty": bool(analysis.strip()),
        "analysis_characters": len(analysis),
        "analysis_sha256": hashlib.sha256(analysis.encode("utf-8")).hexdigest()
        if analysis else None,
    }


def _wait_for_release(timeout_seconds: float = 90.0) -> tuple[float | None, dict]:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        if not caps.qwen25_vl_runtime_available():
            return round(time.monotonic() - started, 3), _snapshot()
        time.sleep(0.5)
    return None, _snapshot()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path,
                        help="Benign local still image; never written into the report")
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly allow one VLM lifecycle measurement")
    parser.add_argument("--report", type=Path,
                        help="Metadata-only JSON destination (recommended: artifacts/benchmarks/...)")
    args = parser.parse_args()

    if not args.execute:
        print("Plan only. No model was loaded. Use: "
              "python local_agent/measure_qwen25_vl_lifecycle.py <benign-image> "
              "--execute --report artifacts/benchmarks/qwen25_vl_lifecycle.json")
        return 0
    global caps, media_tools, router
    import capabilities as caps_module
    import media_tools as media_tools_module
    import router as router_module
    caps, media_tools, router = caps_module, media_tools_module, router_module
    if not args.image or not args.image.is_file():
        print(json.dumps({"available": False, "reason": "an existing benign image is required"}))
        return 2
    owned, detail = router.queue_owner()
    if owned or router.comfy_listening():
        print(json.dumps({"available": False, "reason": "ComfyUI/render owns GPU", "detail": detail}))
        return 3
    if caps.qwen25_vl_runtime_available():
        print(json.dumps({"available": False,
                          "reason": "runtime is already active; cold-load benchmark requires it released first"}))
        return 4
    if not caps.qwen25_vl_files_ready():
        print(json.dumps({"available": False, "reason": "exact GGUF/projector pair is incomplete"}))
        return 5

    report: dict = {"exact_model": caps.QWEN25_VL_MODEL, "runtime": "llama.cpp",
                    "before": _snapshot()}
    started = False
    try:
        t0 = time.monotonic()
        started = caps.ensure_qwen25_vl_runtime()
        report["cold_load_seconds"] = round(time.monotonic() - t0, 3)
        report["after_load"] = _snapshot()
        if not started:
            report["available"] = False
            report["reason"] = "exact lazy runtime did not start"
            print(json.dumps(report, indent=2))
            return 6
        t1 = time.monotonic()
        report["first_analysis"] = _caption(args.image, "Give a concise factual visual description.")
        report["first_analysis_seconds"] = round(time.monotonic() - t1, 3)
        report["after_first_analysis"] = _snapshot()
        t2 = time.monotonic()
        report["second_analysis"] = _caption(args.image, "Confirm the image is readable in one factual sentence.")
        report["second_analysis_seconds"] = round(time.monotonic() - t2, 3)
        report["after_second_analysis"] = _snapshot()
        report["available"] = bool(report["first_analysis"]["analysis_nonempty"] and
                                   report["second_analysis"]["analysis_nonempty"])
        return 0 if report["available"] else 7
    finally:
        if started or caps.qwen25_vl_runtime_available():
            caps.release_qwen25_vl_runtime()
        report["release_seconds"], report["after_release"] = _wait_for_release()
        rendered = json.dumps(report, indent=2)
        if args.report:
            output = args.report.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)


if __name__ == "__main__":
    raise SystemExit(main())
