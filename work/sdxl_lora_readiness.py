"""Read-only dataset preflight for an SDXL/RealVisXL LoRA.

It deliberately does not import torch, load a checkpoint, or start a trainer.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def inspect_dataset(dataset: Path, objective: str) -> dict:
    images = sorted(path for path in dataset.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS)
    captions = [path for path in images if path.with_suffix(".txt").is_file()]
    minimum = 20 if objective == "identity" else 12
    warnings: list[str] = []
    if len(images) < minimum:
        warnings.append(f"{objective} target has {len(images)} images; recommended minimum is {minimum}.")
    if len(captions) != len(images):
        warnings.append(f"{len(images) - len(captions)} image(s) are missing same-name .txt captions.")
    return {
        "dataset": str(dataset), "objective": objective, "images": len(images), "captions": len(captions),
        "ready_for_controlled_run": not warnings, "warnings": warnings,
        "suggested_settings": {"resolution": 1024, "batch_size": 1, "mixed_precision": "bf16", "gradient_checkpointing": True, "cache_latents_to_disk": True, "network_dim": 16, "network_alpha": 16, "unet_lr": "1e-4", "train_unet_only": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--objective", choices=("identity", "style"), required=True)
    args = parser.parse_args()
    if not args.dataset.is_dir(): parser.error(f"dataset is not a directory: {args.dataset}")
    print(json.dumps(inspect_dataset(args.dataset, args.objective), indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
