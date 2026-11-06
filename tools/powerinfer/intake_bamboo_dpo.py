"""Candidate-only, hash-pinned Bamboo-DPO Q4 PowerInfer intake.

Downloads are possible only with --execute. The command imports no model
runtime, never allocates GPU memory, and never starts a server. It pins every
repository to the immutable revisions in the local metadata lock and preserves
partial files as quarantine evidence if download or verification fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from record_bamboo_dpo_metadata import validate
from vault import VaultError, bundle_paths, create_bundle, init_vault, preflight, protect_source, write_json
from verify_bamboo_dpo_intake import DEFAULT_LOCK, _selected_files, verify


MODEL_ID = "bamboo-dpo-7b"
BUILD_ID = "20260830-q4-runtime-intake"


def _bytes(items: list[dict[str, Any]]) -> int:
    return sum(int(item.get("size_bytes", 0)) for item in items)


def _plan(lock: dict[str, Any]) -> dict[str, Any]:
    sources = lock["sources"]
    selected = {
        "original": sources["original"]["files"],
        "predictor": sources["predictor"]["files"],
        "powerinfer_gguf": _selected_files("powerinfer_gguf", sources["powerinfer_gguf"]["files"], "q4_runtime"),
    }
    return {
        "model_id": MODEL_ID,
        "profile": "q4_runtime",
        "sources": {
            role: {
                "repo": sources[role]["resolved_repo"],
                "revision": sources[role]["full_revision"],
                "patterns": [item["path"] for item in files],
                "bytes": _bytes(files),
            }
            for role, files in selected.items()
        },
        "download_bytes": sum(_bytes(files) for files in selected.values()),
        "margin_bytes": int(sum(_bytes(files) for files in selected.values()) * 0.20),
        "policy": "candidate-only; no GPU/model/server/registry/router work",
    }


def _download(repo: str, revision: str, patterns: list[str], destination: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=repo,
        revision=revision,
        local_dir=str(destination),
        allow_patterns=patterns,
        local_dir_use_symlinks=False,
    )


def _read_lock(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        lock = json.load(handle)
    validate(lock)
    return lock


def execute(lock: dict[str, Any], vault_root: Path, build_id: str, *, resume: bool = False) -> Path:
    plan = _plan(lock)
    init_vault(vault_root)
    preflight(vault_root, need_bytes=plan["download_bytes"])
    expected_root = vault_root / MODEL_ID / build_id
    if expected_root.exists():
        if not resume:
            raise VaultError(f"bundle already exists: {expected_root}; use --resume only for this same pinned intake")
        paths = bundle_paths(vault_root, MODEL_ID, build_id)
        stored_plan = paths["validation"] / "bamboo_dpo_intake_plan.json"
        if not stored_plan.is_file():
            raise VaultError(f"cannot resume without the original intake plan: {stored_plan}")
        with stored_plan.open("r", encoding="utf-8") as handle:
            if json.load(handle) != plan:
                raise VaultError("refusing resume: existing plan does not match the immutable metadata lock")
    else:
        paths = create_bundle(vault_root, MODEL_ID, build_id)
    source_root = paths["source"]
    original = source_root / "original"
    predictor = source_root / "predictor"
    gguf = source_root / "gguf"
    validation = paths["validation"]
    if not (validation / "bamboo_dpo_intake_plan.json").exists():
        write_json(validation / "bamboo_dpo_intake_plan.json", plan)

    locations = {"original": original, "predictor": predictor, "powerinfer_gguf": gguf}
    try:
        for role, destination in locations.items():
            source = lock["sources"][role]
            patterns = plan["sources"][role]["patterns"]
            _download(source["resolved_repo"], source["full_revision"], patterns, destination)
        report = verify(lock, original, predictor, gguf, profile="q4_runtime")
        write_json(validation / "bamboo_dpo_local_hash_verification.json", report)
        if not report["valid"]:
            raise VaultError("local Bamboo-DPO intake does not match the immutable metadata lock")
        for directory in locations.values():
            protect_source(directory, vault_root)
        manifest = {
            "model_id": MODEL_ID,
            "build_id": build_id,
            "status": "candidate",
            "profile": "q4_runtime",
            "metadata_lock": str(DEFAULT_LOCK),
            "revisions": report["lock_revisions"],
            "local_hash_verification": str(validation / "bamboo_dpo_local_hash_verification.json"),
            "allowed_next_step": "operator-approved isolated mechanical/quality gate only",
            "not_allowed": ["registry", "router", "proxy", "server", "GPU model load", "ComfyUI"],
        }
        write_json(paths["manifest"], manifest)
        print(f"CANDIDATE_VERIFIED {paths['root']}")
        return paths["root"]
    except Exception:
        quarantine = {
            "model_id": MODEL_ID,
            "build_id": build_id,
            "status": "quarantine",
            "reason": "intake download or immutable-hash verification failed; partial evidence retained",
        }
        write_json(paths["manifest"], quarantine)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--build-id", default=BUILD_ID)
    parser.add_argument("--execute", action="store_true", help="allow the pinned network download")
    parser.add_argument("--resume", action="store_true", help="continue only the same existing pinned bundle")
    args = parser.parse_args()
    try:
        lock = _read_lock(args.lock)
        plan = _plan(lock)
        if not args.execute:
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        execute(lock, args.vault, args.build_id, resume=args.resume)
        return 0
    except (OSError, ValueError, VaultError, ImportError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
