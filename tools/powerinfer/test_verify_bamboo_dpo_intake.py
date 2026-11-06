"""Bounded tests for local Bamboo-DPO provenance comparison; no network/GPU."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_bamboo_dpo_intake import _selected_files, _verify_sources  # noqa: E402


def git_blob(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode("ascii") + content, usedforsecurity=False).hexdigest()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class BambooIntakeVerifierTest(unittest.TestCase):
    def lock(self, source: bytes, predictor: bytes, gguf: bytes) -> dict:
        # The verifier receives an already metadata-validated lock. A small
        # synthetic fixture keeps this test focused on local hash comparison.
        return {
            "sources": {
                "original": {"full_revision": "a" * 40, "files": [{"path": "config.json", "git_blob": git_blob(source)}]},
                "predictor": {"full_revision": "b" * 40, "files": [{"path": "model_0.pt", "sha256": sha256(predictor)}]},
                "powerinfer_gguf": {"full_revision": "c" * 40, "files": [{"path": "model.powerinfer.gguf", "sha256": sha256(gguf)}]},
            }
        }

    def test_accepts_matching_local_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, predictor, gguf = root / "original", root / "predictor", root / "gguf"
            for directory in (original, predictor, gguf):
                directory.mkdir()
            (original / "config.json").write_bytes(b"config")
            (predictor / "model_0.pt").write_bytes(b"predictor")
            (gguf / "model.powerinfer.gguf").write_bytes(b"gguf")
            report = _verify_sources(self.lock(b"config", b"predictor", b"gguf")["sources"], original, predictor, gguf)
            self.assertTrue(report["valid"])

    def test_refuses_a_local_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, predictor, gguf = root / "original", root / "predictor", root / "gguf"
            for directory in (original, predictor, gguf):
                directory.mkdir()
            (original / "config.json").write_bytes(b"changed")
            (predictor / "model_0.pt").write_bytes(b"predictor")
            (gguf / "model.powerinfer.gguf").write_bytes(b"gguf")
            report = _verify_sources(self.lock(b"config", b"predictor", b"gguf")["sources"], original, predictor, gguf)
            self.assertFalse(report["valid"])
            self.assertEqual(report["reports"][0]["files"][0]["result"], "git_blob_mismatch")

    def test_q4_profile_excludes_other_gguf_variants(self) -> None:
        files = [
            {"path": "bamboo-7b-dpo-v0.1.Q4_0.powerinfer.gguf"},
            {"path": "bamboo-7b-dpo-v0.1.powerinfer.gguf"},
            {"path": "activation/activation_0.pt"},
            {"path": "config.json"},
        ]
        self.assertEqual(
            [item["path"] for item in _selected_files("powerinfer_gguf", files, "q4_runtime")],
            ["bamboo-7b-dpo-v0.1.Q4_0.powerinfer.gguf", "activation/activation_0.pt", "config.json"],
        )


if __name__ == "__main__":
    unittest.main()
