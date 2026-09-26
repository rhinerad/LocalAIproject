#!/usr/bin/env python3
"""Attach a measured local VRAM profile and promote if gates pass."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from gvd_tool_router.catalog_seed import seed_implementations
from gvd_tool_router.paths import GvdLayout
from gvd_tool_router.promotion import PromotionError, try_promote, write_policy_receipt
from gvd_tool_router.registry import Registry
from gvd_tool_router.schema import (
    CAPABILITY_CONTINUATION,
    CAPABILITY_FAST,
    CAPABILITY_FIRST_FRAME,
    CAPABILITY_IDENTITY,
    CAPABILITY_NARRATIVE,
    CAPABILITY_INPAINT,
    CAPABILITY_LIPSYNC,
    CAPABILITY_MONTAGE,
    CAPABILITY_STILL,
    CAPABILITY_TTS,
    CAPABILITY_VIDEO_CONTEXT,
    InputBinding,
    InputParameter,
    OutputBinding,
    ResourceProfile,
    WorkflowStage,
    WorkflowTemplate,
    sha256_bytes,
    sha256_json,
    to_plain,
)


FAMILY_IMPL = {
    "still": "known_good_sdxl_txt2img_v1",
    "ltx": "ltx23_unvalidated",
    "ipadapter": "ipadapter_sdxl_plus_face_unvalidated",
    "wan": "wan22_i2v_q4_high_unvalidated",
    "h3": "fasth3_v1_t2va_unvalidated",
    "montage": "animatediff_fizz_unvalidated",
    "tiled": "tiled_diffusion_unvalidated",
    "propainter": "propainter_unvalidated",
    "f5": "f5_tts_adapter_required",
    "musetalk": "musetalk_unvalidated",
    "wan_dual": "wan22_i2v_q4_dual_unvalidated",
    "longcat": "longcat_video_unvalidated",
    "h3v2": "fasth3_v2_unvalidated",
    "wan8": "wan22_i2v_8step_unvalidated",
    "tile_video": "wan21_tile_video_unvalidated",
}

FAMILY_GRAPH = {
    "ltx": ("ltx23_smoke.api.json", "ltx23", ("6", "10"), "16"),
    "ipadapter": ("ipadapter_smoke.api.json", "ipadapter", ("7", "10"), "12"),
    "wan": ("wan_i2v_smoke.api.json", "wan", ("3", "7"), "9"),
    "h3": ("h3_fasth3_smoke.api.json", "fasth3_v1", ("5", "7"), "12"),
    "montage": ("animatediff_fizz_smoke.api.json", "animatediff_fizz", ("3", "6"), "8"),
    "tiled": ("tiled_diffusion_smoke.api.json", "tiled_diffusion", ("5", "8"), "10"),
    "propainter": ("propainter_smoke.api.json", "propainter", ("5", "5"), "5"),
    "f5": ("f5tts_smoke.api.json", "f5_tts", ("2", "2"), "3"),
    "musetalk": ("musetalk_smoke.api.json", "musetalk", ("10", "10"), "10"),
    "wan_dual": ("wan_dual_moe_smoke.api.json", "wan_dual", ("3", "7"), "11"),
    "longcat": ("longcat_ti2v_smoke.api.json", "longcat", ("4", "8"), "10"),
    "h3v2": ("h3_fasth3_v2_smoke.api.json", "fasth3_v2", ("4", "6"), "11"),
    "wan8": ("wan_i2v_8step_smoke.api.json", "wan_8step", ("3", "7"), "9"),
    "tile_video": ("wan_tile_video_smoke.api.json", "wan_tile_video", ("36", "40"), "42"),
}

FAMILY_CAPS = {
    "ltx": frozenset({CAPABILITY_FAST}),
    "ipadapter": frozenset({CAPABILITY_NARRATIVE, CAPABILITY_IDENTITY, CAPABILITY_STILL}),
    "wan": frozenset({CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT}),
    "h3": frozenset({CAPABILITY_FAST}),
    "montage": frozenset({CAPABILITY_MONTAGE}),
    "tiled": frozenset({CAPABILITY_STILL}),
    "propainter": frozenset({CAPABILITY_INPAINT}),
    "f5": frozenset({CAPABILITY_TTS}),
    "musetalk": frozenset({CAPABILITY_LIPSYNC}),
    "wan_dual": frozenset({CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT}),
    "longcat": frozenset({CAPABILITY_CONTINUATION, CAPABILITY_VIDEO_CONTEXT}),
    "h3v2": frozenset({CAPABILITY_FAST}),
    "wan8": frozenset({CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT}),
    "tile_video": frozenset({CAPABILITY_STILL, CAPABILITY_VIDEO_CONTEXT}),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if report.get("status") != "accepted":
        print(json.dumps({"status": "refused", "reason": "smoke_not_accepted"}))
        return 1
    peak = report.get("peak_gpu_mib")
    if peak is None or int(peak) <= 0:
        print(json.dumps({"status": "refused", "reason": "unknown_vram"}))
        return 1
    family = report["family"]
    impl_id = FAMILY_IMPL[family]
    layout = GvdLayout.from_env()
    impls = {i.implementation_id: i for i in seed_implementations()}
    impl = impls[impl_id]
    runtime_sha = sha256_json(to_plain(impl.runtime))
    workload = sha256_json({
        "family": family,
        "graph_sha256": report.get("graph_sha256"),
        "prompt_id": report.get("prompt_id"),
    })
    profile = ResourceProfile(
        profile_id=f"local_smoke_{family}",
        runtime_lock_sha256=runtime_sha,
        workload_sha256=workload,
        precision="measured",
        offload_mode="installed_default",
        peak_gpu_mib=int(peak),
        peak_host_ram_mib=None,
        model_disk_mib=None,
        cold_seconds=None,
        warm_seconds=None,
        evidence="local",
        samples=1,
        report_uri=str(Path(args.report).resolve()),
    )
    if family in FAMILY_GRAPH:
        fname, family_key, bind_ids, out_id = FAMILY_GRAPH[family]
        graph_path = HERE / "fixtures" / fname
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        digest = sha256_json(graph)
        dest = layout.workflow_dir(digest)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "workflow.api.json").write_text(
            json.dumps(graph, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        prompt_node, seed_node = bind_ids
        seed_input = "noise_seed" if family in {"ltx", "h3", "h3v2"} else "seed"
        if family in {"wan", "wan_dual", "longcat", "wan8"}:
            prompt_bind = InputBinding("prompt", prompt_node, "positive_prompt")
        elif family in {"h3", "h3v2"}:
            prompt_bind = InputBinding("prompt", prompt_node, "prompt")
        elif family == "f5":
            prompt_bind = InputBinding("prompt", prompt_node, "speech")
        elif family == "propainter":
            prompt_bind = InputBinding("prompt", prompt_node, "filename_prefix")
        else:
            prompt_bind = InputBinding("prompt", prompt_node, "text")
        template = WorkflowTemplate(
            relative_path=f"{digest}/workflow.api.json",
            sha256=digest,
            format="comfy_api",
            node_types=tuple(str(n.get("class_type")) for n in graph.values()),
            inputs=(
                InputParameter("prompt", {"type": "string"}, True),
                InputParameter("seed", {"type": "integer", "minimum": 0}, False, 1),
            ),
            bindings=(
                prompt_bind,
                InputBinding("seed", seed_node, seed_input),
            ),
            outputs=(
                OutputBinding("audio", out_id, "audio", "audio/flac")
                if family == "f5"
                else OutputBinding("video", out_id, "Filenames", "video/mp4")
                if family == "tile_video"
                else OutputBinding("image", out_id, "images", "image/png")
            ),
            model_family_key=family_key,
        )
        impl = replace(
            impl,
            stages=(WorkflowStage(f"{family}_smoke", template, (), {"prompt": "manifest.script_intent", "seed": "manifest.seed"}),),
            capabilities=FAMILY_CAPS[family],
        )
    receipt = write_policy_receipt(layout, {
        "implementation_id": impl_id,
        "family": family,
        "smoke_report": args.report,
        "peak_gpu_mib": int(peak),
        "allow_new_nodes": family in {"ltx", "h3", "montage", "tiled", "propainter", "f5", "musetalk", "wan_dual", "longcat", "h3v2", "wan8", "tile_video"},
    })
    validation = sha256_json({"report": report.get("prompt_id"), "peak": int(peak)})
    updated = replace(
        impl,
        status="active",
        profiles=(profile,),
        policy_receipt=receipt,
        validation_report_sha256=validation,
        disabled_reason=None,
        quality_scores={
            "identity": {"ltx": 0.2, "still": 0.4, "ipadapter": 0.7, "wan": 0.3, "h3": 0.2, "montage": 0.3, "tiled": 0.4, "propainter": 0.2, "f5": 0.1, "musetalk": 0.6, "wan_dual": 0.3, "longcat": 0.3}.get(family, 0.3),
            "motion": {"ltx": 0.6, "still": 0.1, "ipadapter": 0.1, "wan": 0.7, "h3": 0.6, "montage": 0.7, "tiled": 0.1, "propainter": 0.3, "f5": 0.1, "musetalk": 0.4, "wan_dual": 0.75, "longcat": 0.7}.get(family, 0.3),
            "style": 0.4,
            "audio": 0.1,
            "reliability": 0.7,
        },
    )
    try:
        digest = try_promote(layout, updated)
    except PromotionError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}))
        return 1
    print(json.dumps({
        "status": "promoted",
        "implementation_id": impl_id,
        "digest": digest,
        "peak_gpu_mib": int(peak),
        "policy_receipt": receipt,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
