"""Facade used by local-agent tools: inventory, route, execute, discover."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import asyncio

from .adapters import BinderStaticValidator, LocalSearchAdapter, SqliteValidationQueue, WorkflowSourceResolver
from .binder import inspect_graph
from .catalog_seed import seed_implementations, write_seed_catalog
from .discovery import ALLOWED_CAPABILITIES, discover_workflows
from .executor import execution_blocked, reconcile, submit_stage
from .extensions import apply_lipsync, assemble_scene, quality_gate, repair_video, synthesize_dialogue
from .family_profiles import scan_families
from .gpu_lease import LeaseContention, acquire
from .inventory import bootstrap
from .paths import GvdLayout
from .planner import plan_shot
from .quarantine import QuarantineStore
from .registry import Registry
from .router import required_capabilities, route
from .scheduler import expand_stages, group_ready, topological_stages
from .schema import (
    PUBLIC_TOOL_NAMES,
    ShotManifest,
    ToolImplementation,
    ToolName,
    shot_from_dict,
    to_plain,
)
from .secure_fetch import SecureFetcher
from .store import add_stage, connect, freeze_job, add_shot


def ensure_control_plane(layout: GvdLayout | None = None) -> GvdLayout:
    layout = layout or GvdLayout.from_env()
    layout.ensure()
    if not layout.catalog_json.exists():
        write_seed_catalog(layout)
    if not layout.runtime_json.exists():
        bootstrap(layout)
    return layout


def inventory_report(layout: GvdLayout | None = None) -> dict[str, Any]:
    layout = ensure_control_plane(layout)
    return bootstrap(layout)


def _active(layout: GvdLayout) -> list[ToolImplementation]:
    return Registry(layout).active_implementations()


def _blocked_capability_report(registry: Registry, required: frozenset[str],
                               active: list[ToolImplementation]) -> dict[str, Any]:
    """Name what is missing and which cataloged implementations could supply it.

    UNAVAILABLE_CAPABILITY alone told the operator nothing about what to
    install or approve (2026-09-25q). ``missing_capabilities`` are the required
    capabilities no active implementation offers; ``blocked_candidates`` are
    the catalog rows (plus seed rows not yet in this catalog) that carry one of
    them, with their status and disabled_reason. Read-only; never activates.
    """
    offered: set[str] = set()
    for impl in active:
        offered |= set(impl.capabilities)
    missing = sorted(required - offered)
    rows: dict[str, ToolImplementation] = {}
    for impl in registry.implementations():
        rows[impl.implementation_id] = impl
    seeded: set[str] = set()
    for impl in seed_implementations():
        if impl.implementation_id not in rows:
            rows[impl.implementation_id] = impl
            seeded.add(impl.implementation_id)
    candidates: list[dict[str, Any]] = []
    for impl in rows.values():
        covers = sorted(set(impl.capabilities) & set(missing))
        if not covers:
            continue
        candidates.append({
            "implementation_id": impl.implementation_id,
            "tool_name": impl.tool_name,
            "status": impl.status,
            "capabilities": sorted(impl.capabilities),
            "covers": covers,
            "disabled_reason": impl.disabled_reason,
            "provenance_urls": list(impl.provenance_urls),
            "source": "seed" if impl.implementation_id in seeded else "catalog",
        })
    candidates.sort(key=lambda row: (-len(row["covers"]), row["implementation_id"]))
    return {"missing_capabilities": missing, "blocked_candidates": candidates}


def route_shot(manifest: ShotManifest | dict[str, Any], layout: GvdLayout | None = None) -> dict[str, Any]:
    layout = ensure_control_plane(layout)
    operator_approval = False
    if isinstance(manifest, dict):
        operator_approval = bool(manifest.get("operator_approved_resource_override"))
        manifest = shot_from_dict(manifest)
    registry = Registry(layout)
    active = registry.active_implementations()
    digest = (registry.load_active().get("digest") or "") or ("0" * 64)
    inventory = {}
    if layout.runtime_json.exists():
        runtime = json.loads(layout.runtime_json.read_text(encoding="utf-8"))
        inventory = {
            "gpu": {"memory_free_mib": None},
            "headroom_mib": (runtime.get("gpu") or {}).get("headroom_mib") or 2048,
            "environment_sha256": None,
        }
    if layout.inventory_dir.joinpath("environment_lock.json").exists():
        env = json.loads(layout.inventory_dir.joinpath("environment_lock.json").read_text(encoding="utf-8"))
        gpu = env.get("gpu") or {}
        inventory["gpu"] = {
            "memory_free_mib": gpu.get("memory_free_mib"),
            "memory_used_mib": gpu.get("memory_used_mib"),
        }
        inventory["environment_sha256"] = env.get("environment_sha256")
    decision = route(
        manifest, active, inventory, registry_digest=digest,
        operator_approval=operator_approval,
    )
    out = to_plain(decision)
    if decision.status == "blocked":
        out.update(_blocked_capability_report(
            registry, required_capabilities(manifest), active))
    return out


def _wait_for_stage_completion(
    *,
    http,
    comfy_url: str,
    prompt_id: str,
    attempt_id: str,
    conn,
    timeout_s: float,
    poll_interval_s: float,
    sleep_fn: Callable[[float], None],
    time_fn: Callable[[], float],
) -> dict[str, Any]:
    """Poll reconcile() until a terminal state or timeout_s elapses.

    Fix 2026-09-23 (readiness-audit finding 1.3/1.4): execute_tool()
    previously released the GPU lease the instant every stage was QUEUED,
    not once it actually finished rendering. Other subsystems (vram_controller,
    chat-model eviction, Qwen-VL startup) treat the lease as the signal that
    it is safe to reclaim/free VRAM; releasing it at QUEUED let a second
    lifecycle operation (e.g. /free or loading Qwen-VL) run concurrently
    with a still-active Comfy render. This keeps the lease held until
    reconcile() reports a terminal state (RENDERED/FAILED) or a bounded
    timeout elapses -- it never hangs forever, and on timeout it releases
    with an explicit "timed_out_waiting_for_completion" marker rather than
    silently pretending the job finished.
    """
    from .executor import default_http
    call_http = http or default_http
    deadline = time_fn() + max(0.0, float(timeout_s))
    last: dict[str, Any] = {"status": "RUNNING"}
    while True:
        last = reconcile(call_http, comfy_url, prompt_id, attempt_id, conn)
        if last.get("status") in ("RENDERED", "FAILED"):
            return last
        if time_fn() >= deadline:
            last = dict(last)
            last["timed_out_waiting_for_completion"] = True
            return last
        sleep_fn(max(0.0, float(poll_interval_s)))


def execute_tool(
    tool_name: ToolName,
    manifest: ShotManifest | dict[str, Any],
    *,
    layout: GvdLayout | None = None,
    live: bool = False,
    http=None,
    comfy_url: str = "http://127.0.0.1:8188",
    wait_for_completion: bool = True,
    completion_timeout_s: float = 600.0,
    completion_poll_interval_s: float = 5.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.time,
) -> dict[str, Any]:
    layout = ensure_control_plane(layout)
    # Fix 2026-09-23 (readiness-audit finding 1.1): this function had zero
    # QA/approval check anywhere before submit_stage() posts to ComfyUI's
    # /prompt. local_agent/tools.py's caller-side stills-review gate does not
    # cover the GVD execution tools, and nothing calling this function
    # directly (bypassing tools.py) was gated at all. Read the approval flag
    # from the raw dict *before* shot_from_dict() strips unknown keys, the
    # same pattern route_shot() already uses for
    # operator_approved_resource_override.
    operator_approved_i2v = False
    operator_approval = False
    wan_fallback_acknowledged = False
    if isinstance(manifest, dict):
        operator_approved_i2v = bool(manifest.get("operator_approved_i2v"))
        # 2026-09-26b: execute_tool used to drop this flag, so an approved
        # requires_operator_approval row could plan but never execute.
        operator_approval = bool(manifest.get("operator_approved_resource_override"))
        wan_fallback_acknowledged = bool(manifest.get("operator_acknowledged_wan_fallback"))
        manifest = shot_from_dict(manifest)
    registry = Registry(layout)
    active = [i for i in registry.active_implementations() if i.tool_name == tool_name]
    all_active = registry.active_implementations()
    digest = registry.load_active().get("digest") or ("0" * 64)
    inventory = {"gpu": {"memory_free_mib": 12000}, "headroom_mib": 2048}
    decision = route(manifest, all_active, inventory, registry_digest=digest,
                     operator_approval=operator_approval)
    if decision.status != "selected" or not decision.implementation_id:
        result = execution_blocked(manifest.shot_id, decision.reason_codes, digest)
        payload = to_plain(result)
        payload["tool_name"] = tool_name
        payload["decision"] = to_plain(decision)
        return payload
    impl = next(i for i in all_active if i.implementation_id == decision.implementation_id)
    if impl.tool_name != tool_name:
        return {
            "status": "blocked",
            "reason_codes": ["tool_mismatch", impl.tool_name],
            "shot_id": manifest.shot_id,
        }
    engine_report = {
        "engine": decision.engine,
        "engine_selection": decision.engine_selection,
        "operator_notice": decision.operator_notice,
    }
    # Operator engine policy (2026-09-26b): Wan chosen as a resource fallback
    # (not by request) is announced, never rendered silently. Planning still
    # returns the DAG with the notice attached; a live submission needs the
    # operator to acknowledge the notice first. An explicit requested_engine
    # of "wan" never reaches this branch (engine_selection is
    # "explicit_request").
    if live and decision.engine_selection == "fallback" and not wan_fallback_acknowledged:
        return {
            "status": "blocked",
            "reason_codes": ["ENGINE_FALLBACK_WAN", "operator_acknowledgement_required",
                             *[c for c in decision.reason_codes if c != "ENGINE_FALLBACK_WAN"]],
            "shot_id": manifest.shot_id,
            "tool_name": tool_name,
            "implementation_id": impl.implementation_id,
            **engine_report,
            "note": (
                "MiniMax did not fit this shot and Wan is the only remaining "
                "implementation. The router will not render with Wan without "
                "telling you: set manifest['operator_acknowledged_wan_fallback'] = true "
                "to proceed with Wan, set requested_engine = 'wan' to ask for it "
                "outright, or change the shot so a MiniMax implementation fits."
            ),
        }
    conn = connect(layout)
    job_id = freeze_job(conn, project_id=manifest.project_id, registry_digest=digest)
    add_shot(conn, job_id=job_id, shot_id=manifest.shot_id, manifest=to_plain(manifest))
    if operator_approved_i2v:
        from .store import emit as _emit_event
        _emit_event(conn, "operator_approved_i2v", {
            "shot_id": manifest.shot_id, "job_id": job_id, "tool_name": tool_name,
        })
    if live and decision.engine_selection == "fallback":
        from .store import emit as _emit_event
        _emit_event(conn, "operator_acknowledged_wan_fallback", {
            "shot_id": manifest.shot_id, "job_id": job_id, "tool_name": tool_name,
            "implementation_id": impl.implementation_id,
            "operator_notice": decision.operator_notice,
        })
    stages = expand_stages(impl, manifest)
    if not live:
        return {
            "status": "planned",
            "live": False,
            "shot_id": manifest.shot_id,
            "job_id": job_id,
            "implementation_id": impl.implementation_id,
            "profile_id": decision.profile_id,
            "registry_digest": digest,
            "stages": [to_plain(s) for s in stages],
            **engine_report,
            "note": "live execute requires operator GPU grant; this call planned the DAG only",
        }
    # Fix 2026-09-23 (readiness-audit finding 1.1), continued: still tools
    # (generate_still/upscale_still) have no prior "still" to gate against —
    # they ARE the still — so only video-producing tools require the
    # explicit operator_approved_i2v flag before a live submission. This is
    # a fail-closed default: the flag must be explicitly set to True by
    # whatever assembles the manifest; it is never set here.
    if tool_name not in ("generate_still", "upscale_still") and not operator_approved_i2v:
        return {
            "status": "blocked",
            "reason_codes": ["QA_GATE_BLOCKED", "operator_approved_i2v_required"],
            "shot_id": manifest.shot_id,
            "tool_name": tool_name,
            "note": (
                "Live video submission through the GVD router requires "
                "manifest['operator_approved_i2v'] = true (an explicit, "
                "logged approval) before any ComfyUI /prompt call. It is "
                "never set automatically."
            ),
        }
    ordered = topological_stages(impl)
    values = {"prompt": manifest.script_intent, "seed": manifest.seed}
    try:
        with acquire(
            layout,
            job_id=job_id,
            attempt_id=manifest.shot_id,
            family_key=ordered[0].template.model_family_key if ordered else "",
        ) as lease:
            submitted = []
            for stage in ordered:
                add_stage(conn, job_id, stage.stage_id, list(stage.depends_on), stage.template.model_family_key)
                submit_kwargs = {
                    "layout": layout,
                    "conn": conn,
                    "impl": impl,
                    "stage": stage,
                    "shot_id": manifest.shot_id,
                    "registry_digest": digest,
                    "profile_id": decision.profile_id or "",
                    "values": values,
                    "comfy_url": comfy_url,
                    "lease_generation": lease.generation,
                }
                if http is not None:
                    submit_kwargs["http"] = http
                result = submit_stage(**submit_kwargs)
                submitted.append(result)
            if (
                wait_for_completion
                and submitted
                and submitted[-1].get("status") == "QUEUED"
                and submitted[-1].get("prompt_id")
            ):
                final = _wait_for_stage_completion(
                    http=http,
                    comfy_url=comfy_url,
                    prompt_id=submitted[-1]["prompt_id"],
                    attempt_id=submitted[-1]["attempt_id"],
                    conn=conn,
                    timeout_s=completion_timeout_s,
                    poll_interval_s=completion_poll_interval_s,
                    sleep_fn=sleep_fn,
                    time_fn=time_fn,
                )
                submitted[-1] = {**submitted[-1], **final}
            return {
                "status": submitted[-1]["status"] if submitted else "blocked",
                "live": True,
                "shot_id": manifest.shot_id,
                "job_id": job_id,
                "implementation_id": impl.implementation_id,
                "registry_digest": digest,
                "submitted": submitted,
                **engine_report,
            }
    except LeaseContention as exc:
        return {
            "status": "blocked",
            "reason_codes": ["RESOURCE_BLOCKED", str(exc)],
            "shot_id": manifest.shot_id,
        }


def unavailable(tool_name: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason_codes": ["UNAVAILABLE_CAPABILITY", *reasons],
        "tool_name": tool_name,
    }


def family_status(layout: GvdLayout | None = None) -> dict[str, Any]:
    layout = ensure_control_plane(layout)
    return scan_families()


def plan_narrative(text: str, layout: GvdLayout | None = None, **kwargs: Any) -> dict[str, Any]:
    ensure_control_plane(layout)
    planned = plan_shot(text, **kwargs)
    if planned.get("status") != "planned":
        return planned
    decision = route_shot(planned["manifest"], layout)
    planned["route"] = decision
    return planned


def run_discovery(capability: str, layout: GvdLayout | None = None, max_candidates: int = 10) -> dict[str, Any]:
    layout = ensure_control_plane(layout)
    if capability not in ALLOWED_CAPABILITIES:
        return {"state": "blocked", "reason_codes": ["unsupported_discovery_capability"]}
    queue = SqliteValidationQueue(layout)
    restored = queue.reconcile()
    try:
        results = asyncio.run(discover_workflows(
            capability,
            LocalSearchAdapter(layout),
            WorkflowSourceResolver(),
            SecureFetcher(),
            QuarantineStore(layout),
            BinderStaticValidator(),
            queue,
            max_candidates=max_candidates,
        ))
    except Exception as exc:
        return {
            "state": "source_unavailable",
            "reason_codes": ["SOURCE_UNAVAILABLE", type(exc).__name__],
            "reconciled": restored,
        }
    return {"state": "completed", "results": results, "reconciled": restored}


def run_synthesize_dialogue(args: dict[str, Any], layout: GvdLayout | None = None) -> dict[str, Any]:
    return synthesize_dialogue(args, ensure_control_plane(layout))


def run_apply_lipsync(args: dict[str, Any], layout: GvdLayout | None = None) -> dict[str, Any]:
    return apply_lipsync(args, ensure_control_plane(layout))


def run_repair_video(args: dict[str, Any], layout: GvdLayout | None = None) -> dict[str, Any]:
    return repair_video(args, ensure_control_plane(layout))


def run_assemble(args: dict[str, Any], layout: GvdLayout | None = None) -> dict[str, Any]:
    layout = ensure_control_plane(layout)
    return assemble_scene(
        layout,
        project=str(args.get("project") or "default"),
        shots=list(args.get("shots") or []),
    )


def run_quality_gate(args: dict[str, Any]) -> dict[str, Any]:
    return quality_gate(
        requested_duration_s=float(args.get("requested_duration_s") or 0),
        actual_duration_s=float(args.get("actual_duration_s") or 0),
        tolerance_s=float(args.get("tolerance_s") or 0.25),
        protected_before=args.get("protected_before"),
        protected_after=args.get("protected_after"),
    )
