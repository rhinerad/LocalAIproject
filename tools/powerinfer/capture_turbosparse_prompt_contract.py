#!/usr/bin/env python3
"""Record the exact local TurboSparse chat contract without loading model weights.

The tokenizer stored beside the immutable checkpoint, not a generic Mistral
example from the web, is the only prompt contract this tool accepts.  This is a
read-only inspection: it neither imports model code nor starts CUDA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


EXPECTED = (
    "{% if messages[0]['role'] == 'system' %}{% set system_message = messages[0]['content'] %}{% endif %}"
    "{% if system_message is defined %}{{ '<|im_start|>system\\n' + system_message + '<|im_end|>\\n' }}{% endif %}"
    "{% for message in messages %}{% set content = message['content'] %}{% if message['role'] == 'user' %}"
    "{{ '<|im_start|>user\\n' + content + '<|im_end|>\\n<|im_start|>assistant\\n' }}{% elif message['role'] == 'assistant' %}"
    "{{ content + '<|im_end|>' + '\\n' }}{% endif %}{% endfor %}"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inspect(source: Path) -> dict[str, object]:
    config_path = source / "config.json"
    tokenizer_path = source / "tokenizer_config.json"
    if not config_path.is_file() or not tokenizer_path.is_file():
        raise ValueError("source must contain config.json and tokenizer_config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tokenizer = json.loads(tokenizer_path.read_text(encoding="utf-8"))
    template = tokenizer.get("chat_template")
    if not isinstance(template, str) or not template:
        raise ValueError("checkpoint has no chat_template; refusing to guess one")
    special = tokenizer.get("added_tokens_decoder") or {}
    tokens = {str(row.get("content", "")) for row in special.values() if isinstance(row, dict)}
    required = {"<|im_start|>", "<|im_end|>"}
    if config.get("model_type") != "bamboo" or config.get("hidden_act") != "relu":
        raise ValueError("not the expected Bamboo/ReLU TurboSparse source")
    if not required.issubset(tokens) or not required.issubset(set(template.split())):
        # Template punctuation prevents a simple split on some valid configs.
        if not all(marker in template for marker in required):
            raise ValueError("chat template lacks required ChatML markers")
    if template != EXPECTED:
        raise ValueError("local chat template differs from the reviewed TurboSparse template; inspect before using it")
    return {
        "schema": "turbosparse-prompt-contract-v1",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(source.resolve()),
        "model_type": config["model_type"],
        "hidden_act": config["hidden_act"],
        "template_kind": "checkpoint_chatml",
        "chat_template": template,
        "chat_template_sha256": sha256_text(template),
        "rendered_turn_example": (
            "<|im_start|>system\\nSYSTEM<|im_end|>\\n"
            "<|im_start|>user\\nUSER<|im_end|>\\n<|im_start|>assistant\\n"
        ),
        "status": "verified_local_contract",
    }


def write_once(path: Path, value: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite prompt-contract evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = inspect(args.source)
    write_once(args.out, receipt)
    print(json.dumps({"status": receipt["status"], "out": str(args.out), "template_sha256": receipt["chat_template_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
