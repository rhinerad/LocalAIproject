"""Offline tests for the PowerInfer conversion pipeline helpers. No GPU, no download."""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "powerinfer"
sys.path.insert(0, str(TOOLS))

import pipeline_lib  # noqa: E402
import vault  # noqa: E402


class TargetConfigTests(unittest.TestCase):
    def test_native_runner_requires_cuda_supported_vs2022(self) -> None:
        runner = TOOLS / "run_pipeline.ps1"
        text = runner.read_text(encoding="utf-8")
        self.assertIn("Visual Studio 2022 (17.x)", text)
        self.assertIn("VS 2022 x64 DevCmd + Ninja", text)
        self.assertIn("CMAKE_MAKE_PROGRAM", text)
        self.assertIn("PowerInferNative", text)
        self.assertIn("protobuf tiktoken", text)
        self.assertIn("TrainSamples", text)
        self.assertIn("LayerCount", text)
        self.assertIn("PredictorWorkspace", text)
        self.assertIn("$ArtifactRoot = if ($PredictorWorkspace)", text)
        self.assertIn("Join-Path $ArtifactRoot 'output'", text)
        self.assertIn("predictor assembly deferred", text)
        self.assertIn("Visual Studio 2026 alone is unsupported by CUDA 12.8", text)
        self.assertIn("$env:Path = (Join-Path $PowerInferDir '.venv\\Scripts')", text)
        self.assertIn("$env:PYTHONPATH = $Tools + ';' + $PowerInferDir", text)
        self.assertIn('split_flags_$stamp.json', text)
        self.assertIn('& $MainExe @mainArgs *> $log', text)
        self.assertNotIn('Tee-Object -FilePath $log', text)

    def test_acceptance_gate_scopes_venv_and_keeps_evidence_runs(self) -> None:
        gate = (TOOLS / "record_acceptance_gate.py").read_text(encoding="utf-8")
        self.assertIn("def _powerinfer_child_env()", gate)
        self.assertIn('env["PATH"] = scripts + os.pathsep', gate)
        self.assertIn("env=child_env", gate)
        self.assertIn('main_smoke_bench_{run_stamp}.log', gate)
        self.assertIn('server_{run_stamp}.log', gate)
        self.assertIn('acceptance_gate_{run_stamp}.json', gate)
        self.assertIn('packaged_activation = gguf.parent / "activation"', gate)

    def test_base_class_model_uses_raw_format_not_instruction_template(self) -> None:
        # relu-llama-7b is class:base — no instruction fine-tuning.
        # Its chat_format must be "raw" so the acceptance gate sends plain text
        # continuation prompts instead of [INST] wrappers that produce immediate EOS.
        cfg = pipeline_lib.target_config("relu-llama-7b")
        self.assertEqual("base", cfg["class"])
        self.assertEqual("raw", cfg["chat_format"],
                         "class:base model must use chat_format='raw' to exclude [INST] wrapping")

    def test_render_prompt_raw_format_produces_no_instruction_tags(self) -> None:
        import record_acceptance_gate as gate
        prompt, _ = gate._render_prompt([], "Name the activation family PowerInfer requires.", "raw")
        self.assertNotIn("[INST]", prompt)
        self.assertNotIn("[/INST]", prompt)
        self.assertEqual("Name the activation family PowerInfer requires.", prompt)

    def test_guarded_calibration_continuation_is_layer_scoped(self) -> None:
        runner = TOOLS / "resume_calibration_guarded.ps1"
        text = runner.read_text(encoding="utf-8")
        self.assertIn("[int]$StartLayer = 20", text)
        self.assertIn("[int]$EndLayer = 31", text)
        self.assertIn("[int]$EmergencyC = 82", text)
        self.assertIn("Get-Command 'pwsh.exe'", text)
        self.assertIn("Stop-Process -Id $child.Id -Force", text)
        self.assertIn("Checkpoint already exists", text)
        self.assertIn("Layer $layer completed", text)

    def test_relu_llama_7b_is_active_supported_sparse_poc(self) -> None:
        cfg = pipeline_lib.target_config("relu-llama-7b")
        self.assertEqual(cfg["hf_id"], "SparseLLM/ReluLLaMA-7B")
        self.assertEqual(cfg["expected_hidden_act"], "relu")
        self.assertEqual(cfg["expected_model_type"], "llama")
        self.assertEqual(cfg["hidden_size"], 4096)
        self.assertEqual(cfg["intermediate_size"], 11008)
        self.assertEqual(cfg["num_hidden_layers"], 32)
        self.assertEqual(cfg["vocabtype"], "spm")
        self.assertFalse(cfg["requires_relufication"])
        self.assertFalse(bool(cfg.get("retired")))
        self.assertEqual(cfg["route"], "supported_sparse")

    def test_prosparse_7b_is_retired_but_loadable(self) -> None:
        cfg = pipeline_lib.target_config("prosparse-7b")
        self.assertTrue(cfg["retired"])
        self.assertEqual(cfg["hf_id"], "SparseLLM/prosparse-llama-2-7b")
        self.assertEqual(cfg["hidden_size"], 4096)
        self.assertEqual(cfg["intermediate_size"], 11008)

    def test_both_targets_share_dump_train_fields(self) -> None:
        poc = pipeline_lib.target_config("relu-llama-7b")
        retired = pipeline_lib.target_config("prosparse-7b")
        llama = pipeline_lib.target_config("llama31-8b-abliterated-relu")
        self.assertEqual(poc["hidden_size"], 4096)
        self.assertEqual(poc["intermediate_size"], 11008)
        self.assertEqual(poc["vocabtype"], "spm")
        self.assertFalse(poc["requires_relufication"])
        self.assertEqual(retired["hidden_size"], 4096)
        self.assertEqual(retired["intermediate_size"], 11008)
        self.assertEqual(retired["vocabtype"], "spm")
        self.assertFalse(retired["requires_relufication"])
        self.assertEqual(llama["intermediate_size"], 14336)
        self.assertEqual(llama["vocabtype"], "bpe")
        self.assertTrue(llama["requires_relufication"])
        self.assertEqual(llama["expected_hidden_act"], "relu")
        for cfg in (poc, retired, llama):
            self.assertEqual(cfg["intermediate_size"] % cfg["solver_batch"], 0)
            self.assertEqual(cfg["quant"], "Q4_0")

    def test_unknown_model_exits(self) -> None:
        with self.assertRaises(SystemExit):
            pipeline_lib.target_config("qwen25-abliterated")


class ReluGateTests(unittest.TestCase):
    def test_silu_abliterated_checkpoint_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "config.json").write_text(
                json.dumps(
                    {
                        "hidden_act": "silu",
                        "model_type": "llama",
                        "hidden_size": 4096,
                        "intermediate_size": 14336,
                        "num_hidden_layers": 32,
                    }
                ),
                encoding="utf-8",
            )
            gate = pipeline_lib.relu_gate(path, "relu")
            self.assertFalse(gate["ok"])
            self.assertIn("silu", gate["reason"])

    def test_relu_checkpoint_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "config.json").write_text(
                json.dumps(
                    {
                        "hidden_act": "relu",
                        "model_type": "llama",
                        "hidden_size": 4096,
                        "intermediate_size": 11008,
                        "num_hidden_layers": 32,
                    }
                ),
                encoding="utf-8",
            )
            gate = pipeline_lib.relu_gate(path, "relu")
            self.assertTrue(gate["ok"])

    def test_fatrelu_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "config.json").write_text(
                json.dumps({"hidden_act": "fatrelu_0.01"}),
                encoding="utf-8",
            )
            gate = pipeline_lib.relu_gate(path, "relu")
            self.assertFalse(gate["ok"])
            self.assertIn("FATReLU", gate["reason"])


class HashAndLogTests(unittest.TestCase):
    def test_sha256_tree_combined_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "activation_0.pt").write_bytes(b"abc")
            (root / "activation_1.pt").write_bytes(b"def")
            tree = pipeline_lib.sha256_tree(root, glob="activation_*.pt")
            self.assertEqual(tree["count"], 2)
            self.assertEqual(len(tree["combined_sha256"]), 64)

    def test_parse_split_logs(self) -> None:
        text = """
llm_load_sparse_model_tensors: using CUDA for GPU acceleration
invoking powerinfer Python module to generate gpu split for 12000.00 MiB of VRAM
exported GPU index to model.q4.powerinfer.gguf.generated.gpuidx
apply_tensors_to_base_model: applying gpu_idx adapter from 'model.q4.powerinfer.gguf.generated.gpuidx'
llm_load_gpu_split: offloaded 8000.00 MiB of FFN weights to GPU
sparse_pred_threshold = 0.00
"""
        flags = pipeline_lib.parse_powerinfer_logs(text)
        self.assertTrue(flags["cuda_acceleration"])
        self.assertTrue(flags["ffn_split_working"])

    def test_cached_gpu_index_counts_as_working_split(self) -> None:
        text = """
using CUDA for GPU acceleration
load_gpu_idx_for_model: applying gpu_idx adapter from 'candidate.generated.gpuidx'
llm_load_gpu_split: offloaded 2322.00 MiB of FFN weights to GPU
"""
        flags = pipeline_lib.parse_powerinfer_logs(text)
        self.assertFalse(flags["solver_invoked"])
        self.assertEqual(flags["ffn_offloaded_mib"], 2322.0)
        self.assertTrue(flags["ffn_split_working"])

    def test_zero_mib_is_not_a_working_split(self) -> None:
        text = """
invoking powerinfer Python module to generate gpu split
applying gpu_idx adapter
llm_load_gpu_split: offloaded 0.00 MiB of FFN weights to GPU
"""
        self.assertFalse(pipeline_lib.parse_powerinfer_logs(text)["ffn_split_working"])

    def test_percentile(self) -> None:
        self.assertEqual(pipeline_lib.percentile([1.0, 2.0, 3.0, 4.0], 50), 2.5)


class VaultLayoutTests(unittest.TestCase):
    def test_pipeline_lib_has_no_default_vault(self) -> None:
        self.assertFalse(hasattr(pipeline_lib, "default_vault"))
        self.assertFalse(hasattr(pipeline_lib, "DEFAULT_VAULT_CANDIDATES"))

    def test_env_overrides_preferred_vault(self) -> None:
        with mock.patch.dict(os.environ, {"POWERINFER_VAULT": r"E:\custom-vault"}):
            self.assertEqual(vault.default_vault_path(), Path(r"E:\custom-vault"))

    def test_missing_preferred_drive_falls_back(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "POWERINFER_VAULT"}
        orig = Path.exists

        def fake_exists(self: Path) -> bool:
            if Path(self) in {vault.PREFERRED_VAULT, vault.PREFERRED_VAULT.parent}:
                return False
            return orig(self)

        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(Path, "exists", fake_exists):
            self.assertEqual(vault.default_vault_path(), vault.FALLBACK_VAULT)

    def test_preferred_parent_existing_is_used(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "POWERINFER_VAULT"}
        orig = Path.exists

        def fake_exists(self: Path) -> bool:
            if Path(self) == vault.PREFERRED_VAULT:
                return False
            if Path(self) == vault.PREFERRED_VAULT.parent:
                return True
            return orig(self)

        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(Path, "exists", fake_exists):
            self.assertEqual(vault.default_vault_path(), vault.PREFERRED_VAULT)

    def test_refuses_repo_path(self) -> None:
        with self.assertRaises(vault.VaultError):
            vault.assert_outside_repo(TOOLS)

    def test_init_and_bundle_and_no_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "vault"
            vault.init_vault(root, allow_in_repo=True)
            for name in vault.ROOT_DIRS:
                self.assertTrue((root / name).is_dir())
            paths = vault.create_bundle(root, "prosparse-7b", "b1")
            self.assertTrue(paths["activation"].is_dir())
            self.assertTrue(paths["predictor"].is_dir())
            with self.assertRaises(vault.VaultError):
                vault.create_bundle(root, "prosparse-7b", "b1")
            with self.assertRaises(vault.VaultError):
                vault.refuse_delete(paths["root"])

    def test_repeated_initialisation_preserves_existing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "vault"
            first = vault.init_vault(root, allow_in_repo=True)
            metadata = root / "vault.json"
            before = metadata.read_text(encoding="utf-8")
            second = vault.init_vault(root, allow_in_repo=True)
            self.assertEqual(first, second)
            self.assertEqual(before, metadata.read_text(encoding="utf-8"))

    def test_preflight_margin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "vault"
            vault.init_vault(root, allow_in_repo=True)
            ok = vault.preflight(root, need_bytes=1024)
            self.assertTrue(ok["ok"])
            with self.assertRaises(vault.VaultError):
                vault.preflight(root, need_bytes=10**18)

    def test_protect_source_readonly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            shard = source / "weights.safetensors"
            shard.write_bytes(b"abc")
            stamp = vault.protect_source(source)
            self.assertEqual(stamp["files_locked"], 1)
            self.assertGreaterEqual(stamp["tree"]["count"], 1)
            with self.assertRaises(PermissionError):
                shard.write_bytes(b"nope")

    def test_encrypt_roundtrip_with_env_key(self) -> None:
        if not vault._CRYPTOGRAPHY_AVAILABLE:
            self.skipTest("cryptography is not installed")
        key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"POWERINFER_VAULT_KEY": key}):
            root = Path(tmp) / "vault"
            vault.init_vault(root, allow_in_repo=True)
            plain = Path(tmp) / "private.jsonl"
            plain.write_text('{"prompt":"secret"}\n', encoding="utf-8")
            result = vault.encrypt_private(root, plain, label="calib-test")
            self.assertFalse(result["deleted_plaintext"])
            self.assertTrue(plain.exists())
            dest = Path(tmp) / "out.jsonl"
            back = vault.decrypt_private(root, Path(result["envelope"]), dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), plain.read_text(encoding="utf-8"))
            self.assertEqual(back["sha256"], result["plaintext_sha256"])
            with self.assertRaises(vault.VaultError):
                vault.encrypt_private(root, plain, label="calib-test")

    def test_estimate_includes_margin(self) -> None:
        est = vault.estimate_bundle_bytes("prosparse-7b", source_bytes=0)
        self.assertGreater(est["need_with_margin"], est["need_bytes"])
        self.assertEqual(est["need_with_margin"], int(est["need_bytes"] * 1.2))


if __name__ == "__main__":
    unittest.main()
