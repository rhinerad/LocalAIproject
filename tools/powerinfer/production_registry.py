#!/usr/bin/env python3
"""Validate and register an explicitly approved PowerInfer production bundle.

This module is deliberately offline and filesystem-only.  It does not start a
model, proxy, server, or GPU workload.  A bundle is eligible only when its
lineage manifest is marked ``accepted`` *and* its recorded acceptance checks
are complete.  Registration is a separate, explicit operator action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_lib import target_config, write_json


REQUIRED_ACCEPTANCE_CHECKS = (
    "cuda_acceleration", "ffn_split_working", "activation_present",
    "predictor_present", "gguf_hashed", "cold_20turn_recorded",
    "warm_20turn_recorded", "host_ram_recorded", "vram_recorded",
)


def _require_turbosparse_agentic_evidence(manifest_path: Path) -> None:
    """Require template-bound JSON tool-call evidence for the instruct candidate."""
    validation = manifest_path.parent / "validation"
    contract = _read_object(validation / "prompt_contract.json", "TurboSparse prompt contract")
    gate = _read_object(validation / "agentic_quality_gate.json", "TurboSparse agentic quality gate")
    contract_hash = str(contract.get("chat_template_sha256") or "")
    if contract.get("schema") != "turbosparse-prompt-contract-v1" or contract.get("status") != "verified_local_contract" or len(contract_hash) != 64:
        raise RegistryError("TurboSparse prompt contract is not verified")
    if gate.get("schema") != "turbosparse-agentic-quality-gate-v1" or gate.get("status") != "passed":
        raise RegistryError("TurboSparse agentic quality gate did not pass")
    if gate.get("prompt_contract_sha256") != contract_hash:
        raise RegistryError("TurboSparse quality gate is not bound to the verified prompt contract")


class RegistryError(ValueError):
    """A production registry validation failure safe to show to an operator."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise RegistryError(f"{label} must be a JSON object: {path}")
    return value


def validate_bundle(manifest_path: Path) -> dict[str, Any]:
    """Return normalized registry data or refuse an incomplete bundle."""
    manifest_path = manifest_path.resolve()
    manifest = _read_object(manifest_path, "manifest")
    model_id = str(manifest.get("model_id") or "")
    if not model_id:
        raise RegistryError("manifest has no model_id")
    cfg = target_config(model_id)
    if cfg.get("retired"):
        raise RegistryError(f"{model_id} is retired: {cfg.get('retired_reason', 'no production route')}")
    if manifest.get("status") != "accepted":
        raise RegistryError("manifest status must be accepted; candidate and quarantine bundles cannot deploy")
    if manifest.get("route") != "supported_sparse":
        raise RegistryError("only a supported_sparse model may enter the production registry")
    if cfg.get("class") == "instruct_candidate":
        _require_turbosparse_agentic_evidence(manifest_path)

    gate_path = Path(str(manifest.get("acceptance_gate") or ""))
    if not gate_path.is_absolute():
        gate_path = (manifest_path.parent / gate_path).resolve()
    if not gate_path.is_file():
        raise RegistryError("acceptance gate is missing")
    gate = _read_object(gate_path, "acceptance gate")
    checks = gate.get("acceptance_checklist")
    if not isinstance(checks, dict):
        raise RegistryError("acceptance gate has no acceptance_checklist")
    failed = [key for key in REQUIRED_ACCEPTANCE_CHECKS if checks.get(key) is not True]
    if failed:
        raise RegistryError("acceptance gate is incomplete: " + ", ".join(failed))

    gguf = manifest.get("gguf") or manifest.get("q4_gguf")
    if not isinstance(gguf, dict) or not gguf.get("path") or not gguf.get("sha256"):
        raise RegistryError("manifest has no hashed PowerInfer GGUF")
    gguf_path = Path(str(gguf["path"]))
    if not gguf_path.is_absolute():
        gguf_path = (manifest_path.parent / gguf_path).resolve()
    if not gguf_path.is_file() or _digest(gguf_path) != gguf["sha256"]:
        raise RegistryError("PowerInfer GGUF is missing or its SHA-256 no longer matches the manifest")

    return {
        "model_id": model_id,
        "alias": cfg["alias"],
        "manifest": str(manifest_path),
        "manifest_sha256": _digest(manifest_path),
        "acceptance_gate": str(gate_path),
        "acceptance_gate_sha256": _digest(gate_path),
        "gguf": {"path": str(gguf_path), "sha256": gguf["sha256"]},
    }


def load_registered_model(registry_path: Path, model_id: str) -> dict[str, Any]:
    """Revalidate one registry entry at process startup; never trust stale JSON."""
    registry = _read_object(registry_path, "production registry")
    models = registry.get("models")
    if not isinstance(models, dict) or model_id not in models:
        raise RegistryError(f"no registered production bundle for {model_id!r}")
    entry = models[model_id]
    if not isinstance(entry, dict):
        raise RegistryError("registered model entry is invalid")
    verified = validate_bundle(Path(str(entry.get("manifest") or "")))
    if verified["manifest_sha256"] != entry.get("manifest_sha256"):
        raise RegistryError("registered manifest changed after approval; re-approve it explicitly")
    if verified["acceptance_gate_sha256"] != entry.get("acceptance_gate_sha256"):
        raise RegistryError("acceptance evidence changed after approval; re-approve it explicitly")
    return verified


def register(registry_path: Path, manifest_path: Path, *, evidence_id: str) -> dict[str, Any]:
    """Write an approved entry after all static evidence is revalidated."""
    if not evidence_id.strip():
        raise RegistryError("an operator evidence_id is required for registration")
    entry = validate_bundle(manifest_path)
    if registry_path.exists():
        registry = _read_object(registry_path, "production registry")
    else:
        registry = {"schema": "powerinfer-production-registry-v1", "models": {}}
    if registry.get("schema") != "powerinfer-production-registry-v1":
        raise RegistryError("unrecognized production registry schema")
    models = registry.setdefault("models", {})
    entry["approved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry["evidence_id"] = evidence_id.strip()
    models[entry["model_id"]] = entry
    write_json(registry_path, registry)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, help="path outside the repository/vault")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate a bundle without registering it")
    check.add_argument("--manifest", required=True)
    approve = sub.add_parser("register", help="explicitly add a validated bundle")
    approve.add_argument("--manifest", required=True)
    approve.add_argument("--evidence-id", required=True,
                         help="operator review/benchmark record identifier")
    args = parser.parse_args()
    try:
        if args.command == "check":
            result = validate_bundle(Path(args.manifest))
        else:
            result = register(Path(args.registry), Path(args.manifest), evidence_id=args.evidence_id)
    except RegistryError as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
