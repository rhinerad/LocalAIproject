#!/usr/bin/env python3
"""Read-only preflight for a new approved-pair TurboSparse projected edit.

This intentionally validates before any GPU work.  It does not load weights,
write a checkpoint, create an output directory, or contact a model registry.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from capture_turbosparse_prompt_contract import inspect as inspect_prompt_contract
from validate_approved_calibration_pairs import validate as validate_pairs


def preflight(source: Path, pairs: Path, output: Path) -> dict[str, object]:
    if not source.is_dir():
        raise ValueError(f"source checkpoint is not a directory: {source}")
    if output.exists():
        raise ValueError(f"immutable output path already exists: {output}")
    approval = validate_pairs(pairs)
    prompt_contract = inspect_prompt_contract(source)
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    return {
        "status": "ready_for_explicit_gpu_approval",
        "source": str(source.resolve()),
        "output": str(output),
        "pairs": approval,
        "architecture": {key: config.get(key) for key in ("model_type", "hidden_act", "hidden_size", "intermediate_size", "num_hidden_layers")},
        "prompt_contract_sha256": prompt_contract["chat_template_sha256"],
        "next_step": "Run abliterate_turbosparse_v2.py only after a fresh GPU-gateway approval and idle preflight.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--pairs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(preflight(args.source, args.pairs, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
