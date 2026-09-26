#!/usr/bin/env python3
"""Bounded tests for the frozen prompt-contract classifier."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from classify_bamboo_dpo_prompt_contract import classify


class PromptContractTests(unittest.TestCase):
    def _candidate(self, template: str | None = None, raw_example: bool = False) -> Path:
        root = Path(tempfile.mkdtemp())
        original = root / "source" / "original"
        original.mkdir(parents=True)
        (original / "config.json").write_text(json.dumps({"model_type": "bamboo", "hidden_act": "relu"}), encoding="utf-8")
        tokenizer = {} if template is None else {"chat_template": template}
        (original / "tokenizer_config.json").write_text(json.dumps(tokenizer), encoding="utf-8")
        source = "self.act_fn(self.gate_proj(x)) * self.act_fn(self.up_proj(x))"
        if raw_example:
            source += '\\nprompt = "Hello"\\ninputs = tokenizer(prompt, return_tensors="pt")\\nmodel.generate(inputs.input_ids)'
        (original / "modeling_bamboo.py").write_text(source, encoding="utf-8")
        (original / "README.md").write_text("plain pretraining description", encoding="utf-8")
        return root

    def test_missing_template_blocks_chat_routing(self) -> None:
        report = classify(self._candidate())
        self.assertEqual(report["status"], "prompt_contract_unresolved")
        self.assertFalse(report["chat_routing_allowed"])
        self.assertFalse(report["instruction_quality_gate_allowed"])
        self.assertFalse(report["raw_completion_diagnostic_allowed"])
        self.assertTrue(report["source"]["d_relu_verified_from_frozen_code"])

    def test_source_raw_example_allows_only_a_raw_diagnostic(self) -> None:
        report = classify(self._candidate(raw_example=True))
        self.assertTrue(report["source"]["source_raw_completion_example_present"])
        self.assertTrue(report["raw_completion_diagnostic_allowed"])
        self.assertFalse(report["chat_routing_allowed"])
        self.assertFalse(report["instruction_quality_gate_allowed"])

    def test_declared_template_allows_a_future_review_gate(self) -> None:
        report = classify(self._candidate("<s>[INST] {{ message }} [/INST]"))
        self.assertEqual(report["status"], "chat_template_declared")
        self.assertTrue(report["instruction_quality_gate_allowed"])
        self.assertFalse(report["chat_routing_allowed"])


if __name__ == "__main__":
    unittest.main()
