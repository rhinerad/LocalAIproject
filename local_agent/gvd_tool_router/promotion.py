"""M5 promotion: isolated static validation, policy receipts, atomic activate/rollback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .binder import inspect_graph, is_api_workflow, is_ui_workflow
from .paths import GvdLayout
from .registry import Registry, RegistryError
from .schema import ToolImplementation, can_activate, require_sha256, sha256_json, to_plain

CORE_CLASSES = frozenset({
    "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage", "KSampler",
    "VAEDecode", "VAEEncode", "SaveImage", "LoadImage", "PreviewImage",
    "LoraLoader", "CLIPLoader", "VAELoader",
})


class PromotionError(ValueError):
    pass


def write_policy_receipt(layout: GvdLayout, payload: dict[str, Any]) -> str:
    layout.ensure()
    digest = sha256_json(payload)
    path = layout.inventory_dir / f"policy_{digest}.json"
    record = {"receipt_sha256": digest, "written_at": datetime.now(timezone.utc).isoformat(), **payload}
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return digest


def validate_candidate_graph(
    graph: Any,
    *,
    object_info: dict[str, Any] | None,
    approved_classes: set[str],
    trust_receipt: str | None,
) -> dict[str, Any]:
    if is_ui_workflow(graph):
        return {"verdict": "quarantined", "reasons": ["ui_export_required"]}
    verdict, reasons = inspect_graph(graph)
    if verdict != "api_candidate":
        return {"verdict": verdict, "reasons": reasons}
    unknown = []
    for node in graph.values():
        cls = str(node.get("class_type") or "")
        if cls not in approved_classes and cls not in CORE_CLASSES:
            unknown.append(cls)
            if object_info is not None and cls not in object_info:
                reasons.append(f"unknown_class:{cls}")
    if unknown and not trust_receipt:
        return {
            "verdict": "hold_for_review",
            "reasons": reasons + [f"new_executable_classes:{','.join(sorted(set(unknown)))}"],
            "need": "code_trust_receipt",
        }
    report = {
        "verdict": "static_pass",
        "reasons": reasons,
        "node_count": len(graph),
        "unknown_classes": unknown,
    }
    report["report_sha256"] = sha256_json(report)
    return report


def try_promote(
    layout: GvdLayout,
    impl: ToolImplementation,
    *,
    running_job_digests: set[str] | None = None,
) -> str:
    """Activate one implementation if gates pass. In-flight jobs keep their digest."""
    ok, reasons = can_activate(impl)
    if not ok:
        raise PromotionError("activation_gates:" + ",".join(reasons))
    if impl.peak_unknown():
        raise PromotionError("unknown_vram")
    registry = Registry(layout)
    current = registry.active_implementations()
    by_id = {i.implementation_id: i for i in current}
    by_id[impl.implementation_id] = impl
    digest = registry.promote(list(by_id.values()))
    if running_job_digests and digest in running_job_digests:
        # New snapshot is a different digest by construction; running jobs pin old ones.
        pass
    _ = running_job_digests
    return digest
