#!/usr/bin/env python3
"""One controlled live check for the exact lazy Qwen2.5-VL Caption V4 pair.

This diagnostic is deliberately opt-in: it refuses while ComfyUI owns the GPU,
starts only the paired CUDA llama.cpp runtime, prints no caption content, and
releases that runtime in ``finally``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import capabilities as caps
import media_tools
import router


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Existing local image to inspect")
    parser.add_argument("--report", type=Path,
                        help="Optional JSON metadata report; caption text is never written")
    args = parser.parse_args()
    image = args.image.resolve()
    if not image.is_file():
        print(json.dumps({"available": False, "reason": "image file not found"}))
        return 2
    owned, why = router.queue_owner()
    if owned or router.comfy_listening():
        print(json.dumps({"available": False, "reason": "ComfyUI/render owns GPU", "detail": why}))
        return 3
    if not caps.qwen25_vl_files_ready():
        print(json.dumps({"available": False, "reason": "exact Qwen2.5-VL GGUF pair is incomplete"}))
        return 4

    started = False
    try:
        started = caps.ensure_qwen25_vl_runtime()
        if not started:
            print(json.dumps({"available": False, "reason": "exact llama.cpp runtime did not start"}))
            return 5
        result = json.loads(media_tools._run_vision_gpu(
            [image],
            "Confirm that this image is readable. Give a concise factual visual description.",
            caps.QWEN25_VL_MODEL,
            router.GPU_HOST,
        ))
        analysis = str(result.get("analysis") or "")
        report = {
            "available": bool(result.get("available")),
            "model": result.get("model"),
            "runtime": result.get("runtime"),
            "host": result.get("host"),
            "analysis_nonempty": bool(analysis.strip()),
            "analysis_characters": len(analysis),
            "analysis_sha256": hashlib.sha256(analysis.encode("utf-8")).hexdigest() if analysis else None,
        }
        rendered = json.dumps(report, indent=2)
        if args.report:
            destination = args.report.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["available"] and report["analysis_nonempty"] else 6
    finally:
        if started or caps.qwen25_vl_runtime_available():
            caps.release_qwen25_vl_runtime()


if __name__ == "__main__":
    raise SystemExit(main())
