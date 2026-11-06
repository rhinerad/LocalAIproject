#!/usr/bin/env python3
"""First live media-pipeline generation against local ComfyUI (RTX 5080).

Writes each dispatched graph under logs/run_traces/ as the DSPy baseline,
POSTs to /prompt, then blocks on WebSocket execution_success.

Does not start, restart, or kill ComfyUI. Boot Rockernow on :8188 first.
Does not replace work/image_render.py.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

from local_agent.dispatcher import (  # noqa: E402
    DEFAULT_COMFY_URL,
    PipelineDispatchError,
    PipelineOrchestrator,
)

try:
    import comfy_api
except ImportError:
    from local_agent import comfy_api  # noqa: E402

TRACE_DIR = ROOT / "logs" / "run_traces"
COMFY_URL = DEFAULT_COMFY_URL
JOB_TIMEOUT_S = 600.0

CASES = (
    {
        "id": "case_a_image_facedetailer",
        "title": "Image + FaceDetailer",
        "base_prompt": "A tired woman in a corporate office, looking at the camera",
        "target_aspect": "16:9",
        "model_type": "sdxl",
        "style": "default",
        "expect": "facedetailer",
    },
    {
        "id": "case_b_video_temporal_physics",
        "title": "Video + Temporal Physics",
        "base_prompt": "A yellow hallway with flickering fluorescent lights",
        "target_aspect": "16:9",
        "model_type": "video",
        "style": "backrooms",
        "expect": "temporal_physics",
    },
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _graph_has_face_detailer(graph: dict) -> bool:
    return any(node.get("class_type") == "FaceDetailer" for node in graph.values())


def _graph_prompt_text(graph: dict) -> str:
    return " ".join(
        str((node.get("inputs") or {}).get("text") or "")
        for node in graph.values()
    )


def _assert_routing(case: dict, graph: dict) -> None:
    if case["expect"] == "facedetailer" and not _graph_has_face_detailer(graph):
        raise SystemExit(
            f"{case['id']}: FaceDetailer was not injected. "
            "Refusing to submit a mis-routed graph."
        )
    if case["expect"] == "temporal_physics":
        text = _graph_prompt_text(graph).lower()
        if "handheld walking momentum" not in text and "vhs" not in text:
            raise SystemExit(
                f"{case['id']}: temporal physics was not injected. "
                "Refusing to submit a mis-routed graph."
            )


def _write_trace(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    stamp = _utc_stamp()
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    orchestrator = PipelineOrchestrator(comfy_url=COMFY_URL)
    print(f"ComfyUI URL: {orchestrator.comfy_url}")
    print(f"WebSocket:   {orchestrator.websocket_url()}")
    print(f"Traces:      {TRACE_DIR}")

    if not comfy_api.ping(orchestrator.comfy_url):
        print(
            f"\nComfyUI is not listening at {orchestrator.comfy_url}.\n"
            "Boot the Rockernow backend on port 8188 with RealVisXL and the "
            "Impact Pack (FaceDetailer) available, then re-run:\n"
            "  python run_live_test.py\n"
        )
        return 2

    results = []
    for case in CASES:
        print(f"\n=== {case['title']} ({case['id']}) ===")
        graph = orchestrator.build_and_dispatch_payload(
            case["base_prompt"],
            case["target_aspect"],
            case["model_type"],
            case["style"],
        )
        _assert_routing(case, graph)
        trace_path = TRACE_DIR / f"{stamp}_{case['id']}.json"
        envelope = {
            "case_id": case["id"],
            "title": case["title"],
            "generated_at": stamp,
            "comfy_url": orchestrator.comfy_url,
            "client_id": orchestrator.client_id,
            "request": {
                "base_prompt": case["base_prompt"],
                "target_aspect": case["target_aspect"],
                "model_type": case["model_type"],
                "style": case["style"],
            },
            "prompt": graph,
        }
        _write_trace(trace_path, envelope)
        print(f"wrote DSPy baseline graph: {trace_path}")

        queued = orchestrator.submit_prompt(graph)
        prompt_id = queued["prompt_id"]
        print(f"queued prompt_id={prompt_id}")
        tracked = orchestrator.track_prompt_id(prompt_id, timeout_s=JOB_TIMEOUT_S)
        result = {
            "case_id": case["id"],
            "prompt_id": prompt_id,
            "queued": queued,
            "tracked": tracked,
            "trace_path": str(trace_path),
        }
        result_path = TRACE_DIR / f"{stamp}_{case['id']}_result.json"
        _write_trace(result_path, result)
        print(f"track state={tracked.get('state')} type={tracked.get('type')} source={tracked.get('source')}")
        if tracked.get("state") != "complete":
            print(f"FAILED {case['id']}: {tracked}")
            return 1
        results.append(result)

    summary_path = TRACE_DIR / f"{stamp}_summary.json"
    _write_trace(summary_path, {"generated_at": stamp, "jobs": results})
    print(f"\nBoth jobs reached execution_success. Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
