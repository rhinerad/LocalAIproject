"""Offline tests for accepted-manifest-only PowerInfer registration."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import production_registry as registry  # noqa: E402


class ProductionRegistryTests(unittest.TestCase):
    def _bundle(self, root: Path, *, status: str = "accepted", complete: bool = True) -> Path:
        bundle = root / "bundle"
        gguf = bundle / "output" / "relu-llama-7b.powerinfer.gguf"
        gguf.parent.mkdir(parents=True)
        gguf.write_bytes(b"verified sparse model fixture")
        digest = __import__("hashlib").sha256(gguf.read_bytes()).hexdigest()
        checklist = {key: complete for key in registry.REQUIRED_ACCEPTANCE_CHECKS}
        gate = bundle / "validation" / "acceptance_gate.json"
        gate.parent.mkdir(parents=True)
        gate.write_text(json.dumps({"acceptance_checklist": checklist}), encoding="utf-8")
        manifest = bundle / "manifest.json"
        manifest.write_text(json.dumps({
            "model_id": "relu-llama-7b", "status": status, "route": "supported_sparse",
            "gguf": {"path": str(gguf), "sha256": digest}, "acceptance_gate": str(gate),
        }), encoding="utf-8")
        return manifest

    def test_candidate_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(registry.RegistryError, "status must be accepted"):
                registry.validate_bundle(self._bundle(Path(raw), status="candidate"))

    def test_incomplete_acceptance_gate_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(registry.RegistryError, "acceptance gate is incomplete"):
                registry.validate_bundle(self._bundle(Path(raw), complete=False))

    def test_explicit_registration_rechecks_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest = self._bundle(root)
            registry_path = root / "registry.json"
            entry = registry.register(registry_path, manifest, evidence_id="operator-benchmark-001")
            self.assertEqual("relu-llama-7b", entry["model_id"])
            self.assertEqual("powerinfer-relu-llama-7b", entry["alias"])
            self.assertEqual(entry["gguf"]["sha256"], registry.load_registered_model(registry_path, "relu-llama-7b")["gguf"]["sha256"])
            gate = manifest.parent / "validation" / "acceptance_gate.json"
            gate.write_text(json.dumps({"acceptance_checklist": {}}), encoding="utf-8")
            with self.assertRaisesRegex(registry.RegistryError, "incomplete"):
                registry.load_registered_model(registry_path, "relu-llama-7b")

    def test_turbosparse_requires_template_bound_agentic_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bundle = root / "bundle"
            gguf = bundle / "output" / "turbosparse-mistral-instruct.powerinfer.gguf"
            gguf.parent.mkdir(parents=True)
            gguf.write_bytes(b"candidate")
            digest = __import__("hashlib").sha256(gguf.read_bytes()).hexdigest()
            validation = bundle / "validation"
            validation.mkdir()
            (validation / "acceptance_gate.json").write_text(json.dumps({"acceptance_checklist": {key: True for key in registry.REQUIRED_ACCEPTANCE_CHECKS}}), encoding="utf-8")
            manifest = bundle / "manifest.json"
            manifest.write_text(json.dumps({
                "model_id": "turbosparse-mistral-instruct", "status": "accepted", "route": "supported_sparse",
                "gguf": {"path": str(gguf), "sha256": digest}, "acceptance_gate": str(validation / "acceptance_gate.json"),
            }), encoding="utf-8")
            with self.assertRaisesRegex(registry.RegistryError, "prompt contract"):
                registry.validate_bundle(manifest)
            contract_hash = "b" * 64
            (validation / "prompt_contract.json").write_text(json.dumps({"schema": "turbosparse-prompt-contract-v1", "status": "verified_local_contract", "chat_template_sha256": contract_hash}), encoding="utf-8")
            (validation / "agentic_quality_gate.json").write_text(json.dumps({"schema": "turbosparse-agentic-quality-gate-v1", "status": "passed", "prompt_contract_sha256": contract_hash}), encoding="utf-8")
            self.assertEqual(registry.validate_bundle(manifest)["model_id"], "turbosparse-mistral-instruct")


if __name__ == "__main__":
    unittest.main(verbosity=2)
