"""Record and validate *metadata only* for the Bamboo-DPO PowerInfer candidate.

This utility intentionally uses the Hugging Face model metadata API, never a
resolve/download URL. It writes a compact provenance lock record containing the
repository revision and published LFS SHA-256 values. It neither downloads a
model artifact nor contacts a local model/GPU service.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


API_ROOT = "https://huggingface.co/api/models/"
SOURCES = {
    "original": {
        "logical_repo": "PowerInfer/Bamboo-DPO-v0_1",
        "api_repo": "PowerInfer/Bamboo-DPO-v0_1",
    },
    "predictor": {
        "logical_repo": "PowerInfer/Bamboo-DPO-v0.1-predictor",
        "api_repo": "PowerInfer/Bamboo-DPO-v0.1-predictor",
    },
    "powerinfer_gguf": {
        "logical_repo": "PowerInfer/Bamboo-DPO-v0.1-gguf",
        "api_repo": "Tiiny/Bamboo-DPO-v0.1-gguf",
    },
}


def _fetch(repo: str) -> dict:
    request = Request(
        f"{API_ROOT}{repo}?blobs=true",
        headers={"Accept": "application/json", "User-Agent": "equal-shares-metadata-lock/1"},
    )
    with urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS host
        return json.load(response)


def _file_record(file_meta: dict) -> dict:
    lfs = file_meta.get("lfs") or {}
    record = {"path": file_meta["rfilename"]}
    if file_meta.get("blobId"):
        record["git_blob"] = file_meta["blobId"]
    if lfs.get("sha256"):
        record["sha256"] = lfs["sha256"]
    if lfs.get("size") is not None:
        record["size_bytes"] = lfs["size"]
    return record


def _normalise(source: dict, payload: dict) -> dict:
    return {
        "logical_repo": source["logical_repo"],
        "requested_api_repo": source["api_repo"],
        "resolved_repo": payload["id"],
        "full_revision": payload["sha"],
        "license": next((tag.split(":", 1)[1] for tag in payload.get("tags", []) if tag.startswith("license:")), None),
        "files": sorted((_file_record(item) for item in payload.get("siblings", [])), key=lambda item: item["path"]),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(snapshot: dict) -> None:
    """Fail closed if the immutable metadata or expected 32-layer layout is absent."""
    _require(snapshot.get("schema_version") == "powerinfer-bamboo-metadata-v1", "unexpected schema")
    sources = snapshot.get("sources")
    _require(isinstance(sources, dict), "missing sources")

    for role in SOURCES:
        entry = sources.get(role, {})
        revision = entry.get("full_revision", "")
        _require(len(revision) == 40 and all(char in "0123456789abcdef" for char in revision), f"{role}: invalid full revision")
        _require(entry.get("license") == "apache-2.0", f"{role}: expected Apache-2.0 metadata tag")

    original_files = sources["original"]["files"]
    original_shards = [item for item in original_files if item["path"].endswith(".safetensors")]
    _require(len(original_shards) == 3, "original: expected three safetensors shards")
    _require(all(len(item.get("sha256", "")) == 64 for item in original_shards), "original: missing shard SHA-256")

    predictor_names = {item["path"] for item in sources["predictor"]["files"]}
    _require(predictor_names == {f"model_{layer}.pt" for layer in range(32)} | {".gitattributes", "README.md"}, "predictor: unexpected 32-layer layout")
    _require(all(len(item.get("sha256", "")) == 64 for item in sources["predictor"]["files"] if item["path"].startswith("model_")), "predictor: missing SHA-256")

    gguf_files = sources["powerinfer_gguf"]["files"]
    activation_names = {item["path"] for item in gguf_files if item["path"].startswith("activation/")}
    _require(activation_names == {f"activation/activation_{layer}.pt" for layer in range(32)}, "GGUF: unexpected activation layout")
    powerinfer_gguf = next((item for item in gguf_files if item["path"] == "bamboo-7b-dpo-v0.1.powerinfer.gguf"), None)
    _require(powerinfer_gguf is not None and len(powerinfer_gguf.get("sha256", "")) == 64, "GGUF: missing FP16 PowerInfer artifact SHA-256")


def record() -> dict:
    sources = {role: _normalise(source, _fetch(source["api_repo"])) for role, source in SOURCES.items()}
    snapshot = {
        "schema_version": "powerinfer-bamboo-metadata-v1",
        "recorded_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "purpose": "remote provenance lock only; not a model intake or local file verification",
        "architecture": {
            "declared_model_type": "bamboo",
            "activation_topology": "unverified",
            "chat_template": "unverified",
        },
        "sources": sources,
    }
    validate(snapshot)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("bamboo_dpo_remote_metadata_2026-08-30.json"))
    parser.add_argument("--verify", type=Path, help="validate an existing metadata lock without networking")
    args = parser.parse_args()

    try:
        if args.verify:
            with args.verify.open("r", encoding="utf-8") as handle:
                validate(json.load(handle))
            print(f"VALID {args.verify}")
            return 0
        snapshot = record()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"RECORDED {args.out}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
