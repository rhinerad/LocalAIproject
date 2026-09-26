#!/usr/bin/env python3
"""Classify the frozen Bamboo-DPO prompt contract without loading a model.

This is an evidence gate, not a chat-template guesser.  A missing tokenizer
chat template means native instruction/chat routing is unresolved; it does not
authorize an invented [INST], Alpaca, or other wrapper merely because a
repository name contains "DPO".  The result is written once beside the
candidate's immutable validation evidence.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def classify(candidate_root: Path) -> dict[str, Any]:
    original = candidate_root / "source" / "original"
    config = _load_json(original / "config.json")
    tokenizer = _load_json(original / "tokenizer_config.json")
    source = (original / "modeling_bamboo.py").read_text(encoding="utf-8")
    readme = (original / "README.md").read_text(encoding="utf-8")
    architecture = str(config.get("model_type", ""))
    d_relu = (
        architecture == "bamboo"
        and str(config.get("hidden_act", "")) == "relu"
        and "self.act_fn(self.gate_proj(x)) * self.act_fn(self.up_proj(x))" in source
    )
    template = tokenizer.get("chat_template")
    has_template = isinstance(template, str) and bool(template.strip())
    # The frozen modeling file has a concrete Transformers inference example.
    # It is useful evidence for the *raw completion* boundary, but it is not a
    # chat template and must never be promoted into a fictitious chat contract.
    raw_completion_example = (
        "prompt =" in source
        and "tokenizer(prompt, return_tensors=" in source
        and "model.generate(inputs.input_ids" in source
    )
    # The received model card is the exact source-side evidence.  Name tokens
    # or hosting metadata do not count as instruction-format documentation.
    readme_lower = readme.lower()
    explicit_format_markers = ("[inst]", "### instruction", "### response", "<|assistant|>")
    documented_format = next((marker for marker in explicit_format_markers if marker in readme_lower), "")
    if has_template:
        status = "chat_template_declared"
        recommendation = "Use only the frozen declared template in a separate approved quality gate."
    else:
        status = "prompt_contract_unresolved"
        recommendation = (
            "Do not use an invented chat wrapper or run an instruction-following acceptance gate. "
            "The frozen source supports only a bounded raw-completion diagnostic; it does not establish "
            "chat routing or instruction-following quality until exact prompt-format evidence is supplied."
        )
    return {
        "schema_version": "powerinfer-bamboo-prompt-contract-v1",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate_root": str(candidate_root),
        "source": {
            "model_type": architecture,
            "hidden_act": config.get("hidden_act"),
            "d_relu_verified_from_frozen_code": d_relu,
            "tokenizer_chat_template_present": has_template,
            "tokenizer_chat_template": template if has_template else None,
            "source_readme_explicit_format_marker": documented_format or None,
            "source_raw_completion_example_present": raw_completion_example,
        },
        "status": status,
        "chat_routing_allowed": False,
        "instruction_quality_gate_allowed": has_template,
        "raw_completion_diagnostic_allowed": raw_completion_example,
        "recommendation": recommendation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite evidence: {args.out}")
    report = classify(args.candidate_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(args.out), "status": report["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
