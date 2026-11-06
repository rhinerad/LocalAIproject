#!/usr/bin/env python3
"""Fail closed unless the checkpoint is ReLU/ReGLU and matches the target shapes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline_lib import relu_gate, target_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    cfg = target_config(args.model_id)
    gate = relu_gate(Path(args.source), cfg["expected_hidden_act"])
    mismatches = []
    for field in ("hidden_size", "intermediate_size", "num_hidden_layers"):
        if gate.get(field) != cfg[field]:
            mismatches.append(f"{field}: config {gate.get(field)} vs target {cfg[field]}")
    if cfg["expected_model_type"] and gate.get("model_type") not in (cfg["expected_model_type"], ""):
        mismatches.append(f"model_type={gate.get('model_type')!r}")
    gate["shape_ok"] = not mismatches
    gate["shape_mismatches"] = mismatches
    gate["ok"] = bool(gate["ok"] and not mismatches)
    print(json.dumps(gate, indent=2))
    if not gate["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
