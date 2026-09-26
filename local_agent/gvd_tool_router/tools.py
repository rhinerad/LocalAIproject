"""Local-agent whitelist wrappers for GVD public tools."""
from __future__ import annotations

import json
from typing import Any

from .paths import GvdLayout
from .schema import PUBLIC_TOOL_NAMES, shot_from_dict
from .service import (
    ensure_control_plane,
    execute_tool,
    family_status,
    inventory_report,
    plan_narrative,
    route_shot,
    run_apply_lipsync,
    run_assemble,
    run_discovery,
    run_quality_gate,
    run_repair_video,
    run_synthesize_dialogue,
)


def _layout(args: dict[str, Any]) -> GvdLayout:
    root = args.get("gvd_root")
    return GvdLayout.from_env(root)


def gvd_inventory(args: dict[str, Any] | None = None) -> str:
    args = args or {}
    report = inventory_report(_layout(args))
    env = report.get("environment") or {}
    return json.dumps({
        "gpu": env.get("gpu"),
        "comfy_commit": env.get("comfy_commit"),
        "listeners": env.get("listeners"),
        "object_info_available": env.get("object_info_available"),
        "paths": report.get("paths"),
        "note": "M0 inventory only. No models were downloaded or installed.",
    }, indent=2)


def gvd_route_shot(args: dict[str, Any]) -> str:
    manifest = args.get("manifest") or args
    return json.dumps(route_shot(manifest, _layout(args)), indent=2)


def _execute(name: str, args: dict[str, Any]) -> str:
    live = bool(args.get("live") or args.get("execute"))
    manifest = args.get("manifest") or args
    result = execute_tool(name, manifest, layout=_layout(args), live=live)
    return json.dumps(result, indent=2)


def execute_narrative_scene(args: dict[str, Any]) -> str:
    return _execute("execute_narrative_scene", args)


def execute_continuous_take(args: dict[str, Any]) -> str:
    return _execute("execute_continuous_take", args)


def execute_montage_morph(args: dict[str, Any]) -> str:
    return _execute("execute_montage_morph", args)


def execute_fast_action(args: dict[str, Any]) -> str:
    return _execute("execute_fast_action", args)


def generate_still(args: dict[str, Any]) -> str:
    return _execute("generate_still", args)


def upscale_still(args: dict[str, Any]) -> str:
    return _execute("upscale_still", args)


def discover_workflows_tool(args: dict[str, Any]) -> str:
    capability = str(args.get("capability") or "").strip()
    max_candidates = int(args.get("max_candidates") or 10)
    result = run_discovery(capability, _layout(args), max_candidates=max_candidates)
    result["note"] = "Discovery never installs packages or models. JSON is quarantined."
    return json.dumps(result, indent=2)


def gvd_plan_shot(args: dict[str, Any]) -> str:
    text = str(args.get("text") or args.get("script_intent") or "")
    return json.dumps(plan_narrative(text, _layout(args),
                                     shot_id=str(args.get("shot_id") or "S01"),
                                     user_manifest=args.get("manifest")), indent=2)


def gvd_family_status(args: dict[str, Any] | None = None) -> str:
    args = args or {}
    return json.dumps(family_status(_layout(args)), indent=2)


def synthesize_dialogue_tool(args: dict[str, Any]) -> str:
    return json.dumps(run_synthesize_dialogue(args, _layout(args)), indent=2)


def apply_lipsync_tool(args: dict[str, Any]) -> str:
    return json.dumps(run_apply_lipsync(args, _layout(args)), indent=2)


def repair_video_tool(args: dict[str, Any]) -> str:
    return json.dumps(run_repair_video(args, _layout(args)), indent=2)


def assemble_scene_tool(args: dict[str, Any]) -> str:
    return json.dumps(run_assemble(args, _layout(args)), indent=2)


def gvd_quality_gate(args: dict[str, Any]) -> str:
    return json.dumps(run_quality_gate(args), indent=2)
