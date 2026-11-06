#!/usr/bin/env python3
"""Small deterministic verifier registry for loop-engineering evidence.

All verifiers are local, read-only, bounded, and return compact facts. They do
not execute commands, contact a service, call a model, or make a completion
decision.  This is intentionally useful before considering a separate-model
verifier.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 8 * 1024 * 1024
KINDS = frozenset({"file_sha256", "json_required_keys", "result_predicate"})


class VerificationError(ValueError):
    pass


def _file(path: object) -> Path:
    target = Path(str(path or "")).resolve()
    if not target.is_file():
        raise VerificationError("evidence file does not exist")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise VerificationError(f"evidence file exceeds {MAX_FILE_BYTES} byte verifier limit")
    return target


def verify(kind: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one fixed verifier and return evidence, never an authorization."""
    if kind not in KINDS or not isinstance(arguments, dict):
        raise VerificationError(f"kind must be one of {sorted(KINDS)} with object arguments")
    if kind == "file_sha256":
        target = _file(arguments.get("path"))
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        expected = str(arguments.get("expected_sha256") or "").lower()
        return {"kind": kind, "passed": bool(expected and digest == expected),
                "sha256": digest, "expected_supplied": bool(expected), "size": target.stat().st_size}
    if kind == "json_required_keys":
        target = _file(arguments.get("path"))
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationError("evidence file is not UTF-8 JSON") from exc
        required = arguments.get("required_keys")
        if not isinstance(required, list) or not required or not all(isinstance(item, str) and item for item in required):
            raise VerificationError("required_keys must be a non-empty list of strings")
        actual = set(document) if isinstance(document, dict) else set()
        missing = sorted(set(required) - actual)
        return {"kind": kind, "passed": not missing, "required_keys": sorted(set(required)),
                "missing_keys": missing, "top_level_type": type(document).__name__}
    result = arguments.get("result")
    field = arguments.get("field")
    if not isinstance(result, dict) or not isinstance(field, str) or not field:
        raise VerificationError("result_predicate requires object result and non-empty field")
    expected = arguments.get("equals")
    actual = result.get(field)
    return {"kind": kind, "passed": field in result and actual == expected,
            "field": field, "actual_type": type(actual).__name__, "expected_type": type(expected).__name__}
