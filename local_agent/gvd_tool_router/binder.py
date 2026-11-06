"""Typed API-graph binder. Never interpolates JSON as text or evaluates code."""
from __future__ import annotations

import copy
import json
from typing import Any

from .schema import ToolImplementation, WorkflowTemplate, require_sha256, sha256_bytes

APPROVED_TRANSFORMS = {"identity"}
UI_HINT_KEYS = {"last_node_id", "last_link_id", "nodes", "links", "groups", "config", "extra"}


class BinderError(ValueError):
    pass


def is_ui_workflow(graph: Any) -> bool:
    if not isinstance(graph, dict):
        return False
    if "nodes" in graph and "links" in graph:
        return True
    if any(k in graph for k in ("last_node_id", "last_link_id")):
        return True
    return False


def is_api_workflow(graph: Any) -> bool:
    if not isinstance(graph, dict) or not graph:
        return False
    if is_ui_workflow(graph):
        return False
    for node in graph.values():
        if not isinstance(node, dict) or "class_type" not in node or "inputs" not in node:
            return False
    return True


def inspect_graph(graph: Any) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if _too_deep(graph, 0, limit=24):
        return "reject", ["oversized_or_deep_json"]
    if is_ui_workflow(graph):
        return "ui_export_required", ["ui_workflow_requires_api_export"]
    if not is_api_workflow(graph):
        return "reject", ["not_comfy_api_graph"]
    if len(graph) > 400:
        return "reject", ["too_many_nodes"]
    banned = ("Eval", "Exec", "Shell", "subprocess", "os.system", "LoadImageFromURL")
    for node_id, node in graph.items():
        class_type = str(node.get("class_type") or "")
        if any(token.lower() in class_type.lower() for token in banned):
            reasons.append(f"banned_class:{class_type}")
        blob = json.dumps(node.get("inputs") or {}, ensure_ascii=False).lower()
        if "eval(" in blob or "__import__" in blob or "powershell" in blob:
            reasons.append(f"embedded_code:{node_id}")
    if reasons:
        return "reject", reasons
    return "api_candidate", []


def _too_deep(value: Any, depth: int, limit: int) -> bool:
    if depth > limit:
        return True
    if isinstance(value, dict):
        return any(_too_deep(v, depth + 1, limit) for v in value.values())
    if isinstance(value, list):
        return any(_too_deep(v, depth + 1, limit) for v in value)
    return False


def bind(
    template: WorkflowTemplate,
    graph: dict[str, Any],
    values: dict[str, Any],
    *,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = sha256_bytes(body)
    if digest != require_sha256(template.sha256):
        raise BinderError("workflow sha256 mismatch")
    if is_ui_workflow(graph):
        raise BinderError("UI workflow cannot be submitted as an API prompt")
    if not is_api_workflow(graph):
        raise BinderError("graph is not a Comfy API mapping")
    bound = copy.deepcopy(graph)
    declared = {p.name: p for p in template.inputs}
    for binding in template.bindings:
        if binding.transform not in APPROVED_TRANSFORMS:
            raise BinderError(f"unapproved transform {binding.transform}")
        param = declared.get(binding.parameter)
        if param is None:
            raise BinderError(f"binding parameter {binding.parameter} is not declared")
        if binding.parameter not in values:
            if param.required:
                raise BinderError(f"missing required parameter {binding.parameter}")
            continue
        node = bound.get(binding.node_id)
        if not isinstance(node, dict):
            raise BinderError(f"binding node {binding.node_id} missing")
        if object_info is not None:
            class_type = node.get("class_type")
            info = object_info.get(class_type) if isinstance(class_type, str) else None
            if info:
                inputs = (info.get("input") or {}).get("required") or {}
                inputs.update((info.get("input") or {}).get("optional") or {})
                if binding.node_input not in inputs:
                    raise BinderError(
                        f"{class_type}.{binding.node_input} not in object_info"
                    )
        node.setdefault("inputs", {})
        value = values[binding.parameter]
        _validate_value(param.json_schema, value, binding.parameter)
        node["inputs"][binding.node_input] = value
    return bound


def _validate_value(schema: dict[str, Any], value: Any, name: str) -> None:
    expected = schema.get("type")
    if expected == "string" and not isinstance(value, str):
        raise BinderError(f"{name} must be string")
    if expected == "integer" and not isinstance(value, int):
        raise BinderError(f"{name} must be integer")
    if expected == "number" and not isinstance(value, (int, float)):
        raise BinderError(f"{name} must be number")
    if "enum" in schema and value not in schema["enum"]:
        raise BinderError(f"{name} not in enum")
    if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
        raise BinderError(f"{name} below minimum")
    if "maximum" in schema and isinstance(value, (int, float)) and value > schema["maximum"]:
        raise BinderError(f"{name} above maximum")
    if schema.get("asset_kind") and not isinstance(value, str):
        raise BinderError(f"{name} asset must be an uploaded Comfy filename, not a shell path")


def prompt_payload(graph: dict[str, Any], *, client_id: str, attempt_id: str) -> dict[str, Any]:
    return {
        "prompt": graph,
        "client_id": client_id,
        "extra_data": {"gvd_attempt_id": attempt_id},
    }
