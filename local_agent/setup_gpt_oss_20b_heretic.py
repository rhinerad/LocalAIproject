#!/usr/bin/env python3
"""Install the opt-in gpt-oss-20b-heretic GGUF as a local Ollama model.

This script is deliberately never called by the normal local-agent launcher.
It downloads the exact Q4_K_M GGUF only when the operator runs it, verifies its
published SHA-256, writes a small Ollama Modelfile, and optionally creates the
model on the private GPU Ollama service (127.0.0.1:11434).

Examples:
    python local_agent/setup_gpt_oss_20b_heretic.py
    python local_agent/setup_gpt_oss_20b_heretic.py --create
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ID = "bartowski/p-e-w_gpt-oss-20b-heretic-GGUF"
REMOTE_FILENAME = "p-e-w_gpt-oss-20b-heretic-Q4_K_M.gguf"
LOCAL_FILENAME = "gpt-oss-20b-heretic.Q4_K_M.gguf"
OLLAMA_MODEL_NAME = "gpt-oss-20b-heretic"
OLLAMA_GPU_HOST = "127.0.0.1:11434"

# Published by the source repository for this exact file. Do not accept a
# differently quantised, renamed, or substitute model under this local name.
EXPECTED_SHA256 = "00b172572804e1b2b1ab87ebd48f067522136e9df56368a999152c02e925e47b"

SYSTEM_PROMPT = """You are LocalAgent, a local-first desktop AI assistant.
Be accurate, practical, and transparent about uncertainty. Use available tools
for local state, files, and project facts when they are available. Respect the
operator's explicit permissions and never claim an action succeeded unless its
result confirms it. Keep responses concise unless the operator requests detail.
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path) -> None:
    actual = sha256_file(path)
    if actual.lower() != EXPECTED_SHA256.lower():
        raise RuntimeError(
            f"SHA-256 mismatch for {path.name}:\n"
            f"  expected {EXPECTED_SHA256}\n"
            f"  got      {actual}\n"
            "The file was retained and was not imported."
        )


def download_model(models_dir: Path) -> Path:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "This installer needs huggingface_hub. Install it in the Python "
            "environment that runs this script: python -m pip install huggingface_hub"
        ) from exc

    models_dir.mkdir(parents=True, exist_ok=True)
    destination = models_dir / LOCAL_FILENAME
    if destination.exists():
        verify(destination)
        print(f"Existing GGUF verified: {destination}")
        return destination

    print(f"Downloading {REMOTE_FILENAME} from {REPO_ID}...")
    downloaded = Path(hf_hub_download(
        repo_id=REPO_ID,
        filename=REMOTE_FILENAME,
        local_dir=models_dir,
    ))
    verify(downloaded)
    # Move, do not copy: the 15.9 GB source is renamed into LocalAgent's stable
    # local name without creating a second model-sized file.
    if downloaded.resolve() != destination.resolve():
        shutil.move(str(downloaded), str(destination))
    print(f"Downloaded and verified: {destination}")
    return destination


def write_modelfile(model_path: Path, modelfile_path: Path) -> None:
    # The path has no spaces in the standard layout. Ollama accepts forward
    # slashes on Windows Modelfiles, avoiding backslash escape ambiguity.
    source_path = model_path.resolve().as_posix()
    modelfile_path.write_text(
        f'''FROM {source_path}

PARAMETER num_ctx 8192
PARAMETER temperature 0.7

SYSTEM """{SYSTEM_PROMPT}"""
''',
        encoding="utf-8",
    )
    print(f"Wrote Modelfile: {modelfile_path}")


def create_ollama_model(modelfile_path: Path) -> None:
    ollama = shutil.which("ollama")
    if not ollama:
        raise RuntimeError(
            "Ollama was not found on PATH. Start/install Ollama, then run:\n"
            f'OLLAMA_HOST={OLLAMA_GPU_HOST} ollama create {OLLAMA_MODEL_NAME} '
            f'-f "{modelfile_path}"'
        )

    environment = dict(os.environ)
    environment["OLLAMA_HOST"] = OLLAMA_GPU_HOST
    command = [ollama, "create", OLLAMA_MODEL_NAME, "-f", str(modelfile_path)]
    print("Creating private-GPU Ollama model:", " ".join(command))
    subprocess.run(command, check=True, env=environment)
    print(f"Created Ollama model {OLLAMA_MODEL_NAME} on {OLLAMA_GPU_HOST}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--create", action="store_true",
        help="Create the Ollama model after downloading and writing the Modelfile.",
    )
    parser.add_argument(
        "--models-dir", type=Path,
        default=Path(__file__).resolve().parent / "models",
        help="Where the GGUF and generated Modelfile are stored.",
    )
    args = parser.parse_args()

    try:
        model_path = download_model(args.models_dir)
        modelfile_path = args.models_dir / "Modelfile.gpt-oss-20b-heretic"
        write_modelfile(model_path, modelfile_path)
        if args.create:
            create_ollama_model(modelfile_path)
        else:
            print("\nDownload/setup complete. Create the Ollama model with:")
            print(f'  ollama create {OLLAMA_MODEL_NAME} -f "{modelfile_path}"')
            print("Use OLLAMA_HOST=127.0.0.1:11434 if another Ollama host is active.")
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
