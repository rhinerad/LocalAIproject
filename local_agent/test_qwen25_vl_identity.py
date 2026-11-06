#!/usr/bin/env python3
"""Checksum-pinned Qwen2.5-VL identity. Never starts llama.cpp or downloads."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import capabilities as caps


def _write(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Qwen25VlIdentityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.weights = root / "weights.gguf"
        self.mmproj = root / "mmproj.gguf"
        self.server = root / "llama-server.exe"
        self.state = root / "qwen25_vl_runtime.json"
        _write(self.server, b"stub")
        self._expected_w = b"exact-weights-body"
        self._expected_m = b"exact-mmproj-body"
        self._sha_w = _sha(self._expected_w)
        self._sha_m = _sha(self._expected_m)

    def tearDown(self):
        self._tmp.cleanup()

    def _pin(self, **extra):
        ctx = patch.multiple(
            caps,
            QWEN25_VL_GGUF=self.weights,
            QWEN25_VL_MMPROJ=self.mmproj,
            QWEN25_VL_LLAMA_SERVER=self.server,
            QWEN25_VL_RUNTIME_STATE=self.state,
            # Mocked launches must not write fake headers into the real server log.
            QWEN25_VL_SERVER_LOG=self.state.with_name("qwen25_vl_llama_server.log"),
            QWEN25_VL_WEIGHTS_BYTES=len(self._expected_w),
            QWEN25_VL_MMPROJ_BYTES=len(self._expected_m),
            QWEN25_VL_WEIGHTS_SHA256=self._sha_w,
            QWEN25_VL_MMPROJ_SHA256=self._sha_m,
            _SHA256_CACHE={},
            **extra,
        )
        return ctx

    def test_missing_file_is_not_ready_and_does_not_start_runtime(self):
        with self._pin(), patch.object(caps.subprocess, "Popen") as popen, \
             patch.object(caps.llama_cpp_client, "up", return_value=False):
            self.assertFalse(caps.qwen25_vl_files_ready())
            self.assertFalse(caps.qwen25_vl_checksums_ok())
            self.assertFalse(caps.ensure_qwen25_vl_runtime(timeout_seconds=0))
        popen.assert_not_called()

    def test_checksum_mismatch_refuses_to_start(self):
        _write(self.weights, self._expected_w)
        _write(self.mmproj, b"short")
        with self._pin(), patch.object(caps.subprocess, "Popen") as popen, \
             patch.object(caps.llama_cpp_client, "up", return_value=False):
            self.assertFalse(caps.qwen25_vl_files_ready())  # size mismatch
            self.assertFalse(caps.ensure_qwen25_vl_runtime(timeout_seconds=0))
        popen.assert_not_called()

        _write(self.mmproj, self._expected_m[:-1] + b"Z")  # same length, wrong hash
        with self._pin(), patch.object(caps.subprocess, "Popen") as popen, \
             patch.object(caps.llama_cpp_client, "up", return_value=False):
            self.assertTrue(caps.qwen25_vl_files_ready())
            self.assertFalse(caps.qwen25_vl_checksums_ok())
            self.assertFalse(caps.ensure_qwen25_vl_runtime(timeout_seconds=0))
        popen.assert_not_called()

    def test_matching_checksums_are_required_before_popen(self):
        _write(self.weights, self._expected_w)
        _write(self.mmproj, self._expected_m)
        proc = MagicMock()
        proc.pid = 4242
        with self._pin(), patch.object(caps.subprocess, "Popen", return_value=proc) as popen, \
             patch.object(caps.llama_cpp_client, "up", side_effect=[False, True]), \
             patch.object(caps.time, "sleep"):
            self.assertTrue(caps.qwen25_vl_checksums_ok())
            self.assertTrue(caps.ensure_qwen25_vl_runtime(timeout_seconds=1))
        popen.assert_called_once()
        argv = popen.call_args[0][0]
        self.assertEqual(str(self.weights), argv[argv.index("--model") + 1])
        self.assertEqual(str(self.mmproj), argv[argv.index("--mmproj") + 1])

    def test_state_write_failure_terminates_the_exact_newly_spawned_pid(self):
        _write(self.weights, self._expected_w)
        _write(self.mmproj, self._expected_m)
        proc = MagicMock()
        proc.pid = 4242
        with self._pin(), patch.object(caps.subprocess, "Popen", return_value=proc), \
             patch.object(caps.llama_cpp_client, "up", return_value=False), \
             patch.object(caps, "_write_qwen25_vl_runtime_state", side_effect=OSError("disk")), \
             patch.object(caps, "_terminate_qwen25_vl_pid", return_value=True) as terminate:
            self.assertFalse(caps.ensure_qwen25_vl_runtime(timeout_seconds=1))
        terminate.assert_called_once_with(4242)

    def test_readiness_timeout_releases_the_owned_runtime(self):
        _write(self.weights, self._expected_w)
        _write(self.mmproj, self._expected_m)
        proc = MagicMock()
        proc.pid = 4242
        with self._pin(), patch.object(caps.subprocess, "Popen", return_value=proc), \
             patch.object(caps.llama_cpp_client, "up", return_value=False), \
             patch.object(caps, "release_qwen25_vl_runtime", return_value=True) as release:
            self.assertFalse(caps.ensure_qwen25_vl_runtime(timeout_seconds=0))
        release.assert_called_once_with()

    def test_pinned_constants_are_the_verified_huggingface_v4_pair(self):
        self.assertEqual("mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF",
                         caps.QWEN25_VL_REPOSITORY)
        self.assertEqual("qwen25-vl-nsfw-caption:v4-q4_k_m", caps.QWEN25_VL_MODEL)
        self.assertTrue(str(caps.QWEN25_VL_GGUF).endswith(
            "Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf"))
        self.assertTrue(str(caps.QWEN25_VL_MMPROJ).endswith(
            "Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf"))
        self.assertEqual(4_684_339_808, caps.QWEN25_VL_WEIGHTS_BYTES)
        self.assertEqual(
            "e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d",
            caps.QWEN25_VL_WEIGHTS_SHA256)
        self.assertEqual(732_298_784, caps.QWEN25_VL_MMPROJ_BYTES)
        self.assertEqual(
            "470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1",
            caps.QWEN25_VL_MMPROJ_SHA256)
        self.assertEqual("starsfriday/Qwen-Image-NSFW",
                         caps.QWEN_IMAGE_NSFW_REPOSITORY)
        self.assertEqual(
            "af10a4787691e56cd72803eeaed7f249c1b689583938147cd4ddb31e7d2e1350",
            caps.QWEN_IMAGE_NSFW_SHA256)
        self.assertEqual([caps.QWEN25_VL_MODEL], caps.VISION_PREFERENCES)

    def test_qwen_image_is_identity_only_and_not_an_sdxl_checkpoint(self):
        info = caps.capability("qwen_image_diffusion")
        self.assertEqual("lora", info["kind"])
        self.assertEqual("Qwen/Qwen-Image", info["base_model"])
        self.assertFalse(info["loaded"])
        self.assertIn("no Qwen-Image LoRA", info["load_policy"])
        self.assertIn("CheckpointLoaderSimple", info["load_policy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
