#!/usr/bin/env python3
"""Write the per-build lineage manifest. Does not promote status to accepted."""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_lib import sha256_file, sha256_tree, target_config, utc_now, write_json


def maybe_hash(path: Path) -> dict | None:
    if path.is_file():
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if path.is_dir():
        return sha256_tree(path)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--calibration-path", default="")
    parser.add_argument("--activation-dir", default="")
    parser.add_argument("--predictor-dir", default="")
    parser.add_argument("--status", default="candidate", choices=("candidate", "quarantine", "accepted"))
    parser.add_argument("--powerinfer-commit", default="")
    parser.add_argument("--extra-json", default="")
    args = parser.parse_args()
    bundle = Path(args.bundle)
    calibration = Path(args.calibration_path) if args.calibration_path else bundle / "calibration" / "calibration_manifest.json"
    activation = Path(args.activation_dir) if args.activation_dir else bundle / "activation"
    predictor = Path(args.predictor_dir) if args.predictor_dir else bundle / "predictor"
    cfg = target_config(args.model_id)
    gguf = bundle / "output" / f"{args.model_id}.powerinfer.gguf"
    q4 = bundle / "output" / f"{args.model_id}.q4.powerinfer.gguf"
    manifest = {
        "created_at": utc_now(),
        "model_id": args.model_id,
        "build_id": args.build_id,
        "status": args.status,
        "route": cfg["route"],
        "class": cfg["class"],
        "display_name": cfg["display_name"],
        "license": cfg.get("license"),
        "hidden_size": cfg["hidden_size"],
        "intermediate_size": cfg["intermediate_size"],
        "num_hidden_layers": cfg["num_hidden_layers"],
        "vocabtype": cfg["vocabtype"],
        "requires_relufication": cfg["requires_relufication"],
        "powerinfer_commit": args.powerinfer_commit,
        "source": maybe_hash(Path(args.source)),
        "calibration": maybe_hash(calibration),
        "activation": sha256_tree(activation, glob="activation_*.pt"),
        "predictor": sha256_tree(predictor, glob="*"),
        "gguf": maybe_hash(gguf) if gguf.exists() else None,
        "q4_gguf": maybe_hash(q4) if q4.exists() else None,
        "acceptance_gate": str(bundle / "validation" / "acceptance_gate.json"),
    }
    if args.extra_json:
        manifest["tooling"] = __import__("json").loads(Path(args.extra_json).read_text(encoding="utf-8"))
    write_json(bundle / "manifest.json", manifest)
    print(bundle / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
