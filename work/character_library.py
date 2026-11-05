#!/usr/bin/env python3
"""Consent-gated character-library and SDXL LoRA training planner.

This utility deliberately does *not* start kohya_ss, download a model, or load
the GPU.  It provides a durable, inspectable registration format and a training
plan that an operator may review before separately approving a real training run.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = ROOT / "outputs" / "stories" / "character_library.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class CharacterLibraryError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(value: str, label: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip()).strip("-_")
    if not result or result in {".", ".."}:
        raise CharacterLibraryError(f"{label} must contain letters or numbers")
    return result[:80]


def _read(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "characters": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CharacterLibraryError(f"cannot read character library: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("characters"), list):
        raise CharacterLibraryError("character library has an invalid schema")
    return data


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _image_files(photo_dir: Path) -> list[Path]:
    if not photo_dir.is_dir():
        raise CharacterLibraryError(f"photo directory does not exist: {photo_dir}")
    return sorted(p for p in photo_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)


def training_plan(name: str, trigger_word: str, photo_dir: str | Path) -> dict:
    """Return an SDXL LoRA plan; this function has no write, subprocess, or GPU path."""
    identity = _slug(name, "name")
    trigger = _slug(trigger_word, "trigger word")
    photos = _image_files(Path(photo_dir))
    count = len(photos)
    return {
        "planned": True,
        "executes_training": False,
        "gpu_action": "none",
        "character": identity,
        "trigger_word": trigger,
        "training_images": count,
        "image_count_guidance": "recommended 20–30 varied, consenting-adult photos",
        "warnings": ([f"{count} images found; gather 20–30 varied photos before training"]
                     if not 20 <= count <= 30 else []),
        "proposed_output": f"ComfyUI-Shared/models/loras/characters/{identity}.safetensors",
        "suggested_sdxl_settings": {
            "resolution": 1024,
            "network_dim": 32,
            "network_alpha": 16,
            "unet_learning_rate": "1e-4",
            "text_encoder_learning_rate": "5e-5",
            "batch_size": 1,
            "mixed_precision": "bf16",
            "cache_latents": True,
        },
        "consent_gate": (
            "Before a real training run, the operator must explicitly confirm this "
            "is their own likeness or a consenting adult, then separately approve "
            "the GPU job."
        ),
    }


def register_character(name: str, trigger_word: str, reference_photo: str | Path,
                       lora_filename: str, *, consent_confirmed: bool,
                       library_path: Path = DEFAULT_LIBRARY) -> dict:
    """Register a character only after a direct adult-consent confirmation."""
    if not consent_confirmed:
        raise CharacterLibraryError(
            "registration refused: confirm the likeness is your own or a consenting adult"
        )
    identity = _slug(name, "name")
    trigger = _slug(trigger_word, "trigger word")
    photo = Path(reference_photo)
    if not photo.is_file() or photo.suffix.lower() not in IMAGE_EXTENSIONS:
        raise CharacterLibraryError("reference_photo must be an existing supported image")
    lora = Path(lora_filename).name
    if not lora.lower().endswith(".safetensors"):
        raise CharacterLibraryError("lora_filename must be a .safetensors filename")
    library = _read(library_path)
    if any(row.get("name", "").casefold() == identity.casefold()
           for row in library["characters"]):
        raise CharacterLibraryError(f"character {identity!r} is already registered")
    entry = {
        "name": identity,
        "trigger_word": trigger,
        # Never persist an absolute personal source-photo path.
        "reference_photo_filename": photo.name,
        "lora_filename": lora,
        "consent_confirmed": True,
        "registered_at": _now(),
    }
    library["characters"].append(entry)
    _write(library_path, library)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan", help="create a read-only training plan")
    plan.add_argument("--name", required=True)
    plan.add_argument("--trigger-word", required=True)
    plan.add_argument("--photos", required=True, type=Path)
    reg = sub.add_parser("register", help="register a consented adult character")
    reg.add_argument("--name", required=True)
    reg.add_argument("--trigger-word", required=True)
    reg.add_argument("--reference-photo", required=True, type=Path)
    reg.add_argument("--lora-filename", required=True)
    reg.add_argument("--confirm-consenting-adult", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "plan":
            result = training_plan(args.name, args.trigger_word, args.photos)
        else:
            result = register_character(
                args.name, args.trigger_word, args.reference_photo, args.lora_filename,
                consent_confirmed=args.confirm_consenting_adult, library_path=args.library,
            )
    except CharacterLibraryError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
