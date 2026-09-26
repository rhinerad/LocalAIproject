"""Termux PowerInfer2 edge-worker contract tests.

Correct invocation — from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_farm_core local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

try:
    import local_agent.worker_farm  # noqa: F401
except ModuleNotFoundError as exc:
    if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
        raise
    sys.stderr.write(
        "ERROR: local_agent is not importable because this file was run by path.\n"
        "From the repository root, use the farm venv:\n"
        "  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest "
        "local_agent.worker_farm.test_farm_core "
        "local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v\n"
    )
    raise SystemExit(2) from exc

from local_agent.worker_farm.termux_powerinfer2_edge_worker import (
    EdgePolicyError, build_config, build_runtime_command, validate_job,
)


class TermuxPowerInferContractTests(unittest.TestCase):
    def _files(self, root: str) -> tuple[Path, Path, Path]:
        token, binary, model = (Path(root) / "token", Path(root) / "llama-cli", Path(root) / "model.gguf")
        token.write_text("x" * 32, encoding="utf-8")
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o700)
        model.write_bytes(b"not a real model")
        # Sibling mTLS materials are required (G2). Contents are not parsed in build_config.
        for name in ("ca.cert.pem", "client.cert.pem", "client.key.pem"):
            (Path(root) / name).write_text("-----BEGIN PLACEHOLDER-----\n" + ("x" * 64), encoding="utf-8")
        return token, binary, model

    def test_requires_private_overlay_https_gateway(self):
        with tempfile.TemporaryDirectory() as root:
            token, binary, model = self._files(root)
            with self.assertRaises(EdgePolicyError):
                build_config(gateway="http://192.168.1.2", token_file=token, binary=binary, model=model, threads=2, timeout_seconds=300)
            with self.assertRaises(EdgePolicyError):
                build_config(gateway="https://127.0.0.1", token_file=token, binary=binary, model=model, threads=2, timeout_seconds=300)

    def test_job_allowlist_and_bounded_prompt(self):
        self.assertEqual(
            ("job_1", "brief, non-sensitive prompt", 128),
            validate_job({
                "id": "job_1", "kind": "edge_text_inference",
                "prompt": "brief, non-sensitive prompt", "max_tokens": 128, "attempt": 1,
            }),
        )
        with self.assertRaises(EdgePolicyError):
            validate_job({"id": "job_2", "kind": "run_build", "prompt": "no", "max_tokens": 1})

    def test_requires_mtls_materials_beside_token(self):
        with tempfile.TemporaryDirectory() as root:
            token, binary, model = self._files(root)
            (Path(root) / "ca.cert.pem").unlink()
            with self.assertRaises(EdgePolicyError):
                build_config(gateway="https://10.90.91.1:8743", token_file=token, binary=binary, model=model, threads=2, timeout_seconds=300)

    def test_command_is_shell_free_and_uses_local_paths_only(self):
        with tempfile.TemporaryDirectory() as root:
            token, binary, model = self._files(root)
            with self.assertRaises(EdgePolicyError):
                build_config(gateway="https://edge.example.invalid", token_file=token, binary=binary, model=model, threads=2, timeout_seconds=300)
            config = build_config(gateway="https://10.90.91.1:8743", token_file=token, binary=binary, model=model, threads=2, timeout_seconds=300)
            command = build_runtime_command(config, "a;b && c", 16)
            self.assertEqual(str(binary), command[0])
            self.assertIn("a;b && c", command)
            self.assertIn("-c", command)
            self.assertIn("512", command)
            self.assertIn("-ub", command)
            self.assertNotIn("sh", command)


if __name__ == "__main__":
    sys.stderr.write(
        "ERROR: do not run this file by path. From the repository root, use the farm venv:\n"
        "  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest "
        "local_agent.worker_farm.test_farm_core "
        "local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v\n"
    )
    raise SystemExit(2)
