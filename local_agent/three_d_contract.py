#!/usr/bin/env python3
"""Validate an operator-reviewed 3D ComfyUI workflow contract.

This intentionally knows no node names or workflow defaults.  It only verifies
that a future explicit contract is complete and checksum-pinned before any
separate submission tool may be considered.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ContractError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(contract_path: Path, *, shared_root: Path) -> dict:
    try:
        contract = json.loads(contract_path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"unreadable contract: {exc}") from exc
    if contract.get("status") != "approved":
        raise ContractError("contract status must be explicit 'approved'")
    if not str(contract.get("approved_by", "")).strip():
        raise ContractError("contract requires an operator approved_by value")
    rel = Path(str(contract.get("workflow", "")))
    if not rel.name or rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".json":
        raise ContractError("workflow must be a relative .json path under shared workflows")
    workflow = (shared_root / "workflows" / rel).resolve()
    workflow_root = (shared_root / "workflows").resolve()
    if workflow_root not in workflow.parents or not workflow.is_file():
        raise ContractError("approved workflow is unavailable under shared workflows")
    if contract.get("workflow_sha256") != _sha256(workflow):
        raise ContractError("workflow checksum does not match the approved contract")
    bindings = contract.get("bindings")
    required_bindings = {"prompt", "reference_image", "mesh_output"}
    if not isinstance(bindings, dict) or set(bindings) != required_bindings:
        raise ContractError("bindings must contain exactly prompt, reference_image, mesh_output")
    if any(not isinstance(value, dict) or not str(value.get("node_id", "")).strip()
           or not str(value.get("input", "")).strip() for value in bindings.values()):
        raise ContractError("each binding requires concrete node_id and input")
    node_types = contract.get("required_node_types")
    if not isinstance(node_types, list) or not node_types or any(not isinstance(v, str) or not v.strip() for v in node_types):
        raise ContractError("required_node_types must be a non-empty explicit list")
    extensions = contract.get("mesh_extensions")
    if not isinstance(extensions, list) or not extensions or not set(extensions) <= {".obj", ".glb", ".stl"}:
        raise ContractError("mesh_extensions must be a non-empty subset of .obj, .glb, .stl")
    return {"ready_for_future_tool_review": True, "workflow": str(workflow),
            "workflow_sha256": contract["workflow_sha256"], "mesh_extensions": extensions,
            "required_node_types": node_types}
