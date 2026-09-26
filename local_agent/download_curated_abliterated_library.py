#!/usr/bin/env python3
"""Download the curated offline abliterated-model library.

This is an archive downloader, not a model launcher.  It never changes the
Local Agent's selected model, starts an inference server, or loads VRAM.  The
GGUF files can later be registered explicitly after a compatibility check.

The default ``recommended`` set is deliberately small and useful:
* Qwen3 30B-A3B Q3_K_M: a 14.7 GB MoE model for constrained local use.
* DeepSeek-R1-Distill-Qwen 32B IQ4_XS: a reasoning model for CPU/partial GPU.
* DeepSeek-R1-Distill-Llama 70B Heretic Q4_K_M: archive / future hardware.
* GPT-OSS 120B Heretic Q4_K_M: archive / future hardware.

Downloads are resumable through huggingface_hub.  The script does not download
an entire repository: each entry pins one GGUF file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


LIBRARY = {
    "qwen3_30b_a3b": {
        "label": "Huihui Qwen3 30B-A3B Abliterated (Q3_K_M)",
        "repo_id": "DevQuasar/huihui-ai.Qwen3-30B-A3B-abliterated-GGUF",
        "filename": "huihui-ai.Qwen3-30B-A3B-abliterated.Q3_K_M.gguf",
        "expected_gb": 14.7,
        "use": "Local GPU candidate with a small context, or CPU/partial offload.",
        "availability": "potentially_runnable",
    },
    "deepseek_r1_32b": {
        "label": "DeepSeek-R1-Distill-Qwen 32B Abliterated (IQ4_XS)",
        "repo_id": "bartowski/DeepSeek-R1-Distill-Qwen-32B-abliterated-GGUF",
        "filename": "DeepSeek-R1-Distill-Qwen-32B-abliterated-IQ4_XS.gguf",
        "expected_gb": 17.69,
        "use": "Higher-quality local reasoning via CPU or partial GPU offload.",
        "availability": "cpu_or_partial_offload",
    },
    "deepseek_r1_70b_heretic": {
        "label": "DeepSeek-R1-Distill-Llama 70B Heretic (Q4_K_M)",
        "repo_id": "ThalisAI/DeepSeek-R1-Distill-Llama-70B-heretic",
        "filename": "DeepSeek-R1-Distill-Llama-70B-heretic-Q4_K_M.gguf",
        "expected_gb": 39.60,
        "use": "Archive for future high-RAM hardware; not practical on 16 GB VRAM / 32 GB RAM.",
        "availability": "archive_only",
    },
    "gpt_oss_120b_heretic": {
        "label": "GPT-OSS 120B Heretic (Q4_K_M)",
        "repo_id": "hrktos-37/GPT-OSS-120B-Heretic-GGUF",
        # The repository's public picker label is Q4_K_M, but its actual file
        # name is lowercase and includes the -GGUF suffix. Keep this exact
        # filename so a resumable download cannot silently select another quant.
        "filename": "gpt-oss-120b-heretic-GGUF-q4_k_m.gguf",
        "expected_gb": 87.9,
        "use": "Archive for future high-RAM hardware; the closest vetted large-model class to the requested 128B tier.",
        "availability": "archive_only",
    },
}

DEFAULT_SELECTION = tuple(LIBRARY)


def write_manifest(destination: Path, selected: list[str]) -> None:
    manifest = {
        "schema_version": 1,
        "purpose": "Curated offline abliterated GGUF archive; not auto-loaded.",
        "models": [{"id": model_id, **LIBRARY[model_id]} for model_id in selected],
        "estimated_total_gb": round(sum(LIBRARY[item]["expected_gb"] for item in selected), 2),
    }
    (destination / "CURATED_ABLITERATED_LIBRARY.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def download(destination: Path, selected: list[str], *, disable_xet: bool) -> int:
    # Xet is normally a good default for huge Hugging Face files. It can become
    # stuck before writing bytes on this Windows host, however.  This opt-in
    # switch uses Hugging Face's normal resumable HTTP transfer instead; it does
    # not change sources, model files, or integrity behaviour.
    if disable_xet:
        os.environ["HF_HUB_DISABLE_XET"] = "1"
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "Missing dependency: install huggingface_hub first with "
            "python -m pip install -U huggingface_hub",
            file=sys.stderr,
        )
        return 2

    destination.mkdir(parents=True, exist_ok=True)
    write_manifest(destination, selected)
    for number, model_id in enumerate(selected, start=1):
        model = LIBRARY[model_id]
        model_dir = destination / model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{number}/{len(selected)}] {model['label']} (~{model['expected_gb']} GB)")
        path = hf_hub_download(
            repo_id=model["repo_id"],
            filename=model["filename"],
            local_dir=model_dir,
        )
        print(f"  complete: {path}")
    print("Curated library download complete. Nothing was imported into Ollama or loaded into VRAM.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download the selected model files.")
    parser.add_argument("--models-dir", type=Path, default=Path(__file__).resolve().parent / "models" / "curated_abliterated_library")
    parser.add_argument("--only", choices=sorted(LIBRARY), action="append", help="Download only this model; may be supplied more than once.")
    parser.add_argument("--disable-xet", action="store_true", help="Use standard resumable HTTP if a Xet transfer stalls before writing data.")
    args = parser.parse_args()
    selected = args.only or list(DEFAULT_SELECTION)
    print("Curated model plan:")
    for model_id in selected:
        model = LIBRARY[model_id]
        print(f"- {model_id}: {model['expected_gb']} GB; {model['availability']}; {model['use']}")
    print(f"Total expected download: {sum(LIBRARY[item]['expected_gb'] for item in selected):.2f} GB")
    if not args.download:
        print("\nReview only. Re-run with --download to begin resumable downloads.")
        return 0
    return download(args.models_dir, selected, disable_xet=args.disable_xet)


if __name__ == "__main__":
    raise SystemExit(main())
