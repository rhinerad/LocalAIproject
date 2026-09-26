"""Verify local Bamboo-DPO files against the immutable remote metadata lock.

This tool never contacts a network endpoint, launches a model, or uses GPU
memory. It only reads a future local intake and compares its content hashes to
the recorded public provenance lock before a candidate can move forward.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from record_bamboo_dpo_metadata import validate


HERE = Path(__file__).resolve().parent
DEFAULT_LOCK = HERE / "bamboo_dpo_remote_metadata_2026-08-30.json"


def _hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_blob_sha1(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _compare_tree(role: str, root: Path, expected: list[dict[str, Any]]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    valid = True
    for item in expected:
        relative = Path(item["path"])
        target = root / relative
        actual: str | None = None
        if not target.is_file():
            result = "missing"
            valid = False
        elif "sha256" in item:
            actual = _hash_file(target, "sha256")
            result = "match" if actual == item["sha256"] else "sha256_mismatch"
            valid = valid and result == "match"
        elif "git_blob" in item:
            actual = _git_blob_sha1(target)
            result = "match" if actual == item["git_blob"] else "git_blob_mismatch"
            valid = valid and result == "match"
        else:
            result = "lock_missing_fingerprint"
            valid = False
        files.append({"path": relative.as_posix(), "result": result, "actual": actual})
    return {"role": role, "root": str(root), "valid": valid, "files": files}


def _selected_files(role: str, files: list[dict[str, Any]], profile: str) -> list[dict[str, Any]]:
    if profile == "full" or role != "powerinfer_gguf":
        return files
    keep = {
        ".gitattributes",
        ".gitignore",
        "README.md",
        "config.json",
        "bamboo-7b-dpo-v0.1.Q4_0.powerinfer.gguf",
    }
    return [item for item in files if item["path"] in keep or item["path"].startswith("activation/")]


def _verify_sources(
    sources: dict[str, Any], original: Path, predictor: Path, gguf: Path, *, profile: str = "full"
) -> dict[str, Any]:
    roots = {"original": original, "predictor": predictor, "powerinfer_gguf": gguf}
    reports = [_compare_tree(role, roots[role], _selected_files(role, sources[role]["files"], profile)) for role in roots]
    return {
        "schema_version": "powerinfer-bamboo-local-intake-verification-v1",
        "verified_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "lock_revisions": {role: sources[role]["full_revision"] for role in roots},
        "profile": profile,
        "reports": reports,
        "valid": all(report["valid"] for report in reports),
    }


def verify(lock: dict[str, Any], original: Path, predictor: Path, gguf: Path, *, profile: str = "full") -> dict[str, Any]:
    validate(lock)
    return _verify_sources(lock["sources"], original, predictor, gguf, profile=profile)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--predictor", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--profile", choices=("full", "q4_runtime"), default="full")
    parser.add_argument("--out", type=Path, help="optional local verification record")
    args = parser.parse_args()

    try:
        with args.lock.open("r", encoding="utf-8") as handle:
            lock = json.load(handle)
        report = verify(lock, args.original, args.predictor, args.gguf, profile=args.profile)
        if args.out:
            _write_json(args.out, report)
        print("VALID" if report["valid"] else "REFUSED")
        return 0 if report["valid"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
