from __future__ import annotations

import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class LauncherKvCacheTests(unittest.TestCase):
    def test_gpu_cache_candidate_is_explicit_and_baseline_stays_default(self):
        text = (HERE / "START_LOCAL_AGENT_GUI.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$GpuKvCache = 'baseline'", text)
        self.assertIn("[ValidateSet('baseline', 'flash_q8')]", text)
        self.assertIn("elseif ($GpuKvCacheMode -eq 'flash_q8')", text)
        self.assertIn("$envs['OLLAMA_FLASH_ATTENTION'] = '1'", text)
        self.assertIn("$envs['OLLAMA_KV_CACHE_TYPE'] = 'q8_0'", text)

    def test_coding_model_pull_is_opt_in(self):
        text = (HERE / "START_LOCAL_AGENT_GUI.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$EnsureCodingModel", text)
        self.assertIn("EQUAL_SHARES_ENSURE_CODING_MODEL", text)
        self.assertIn("huihui_ai/qwen2.5-coder-abliterate:14b", text)
        self.assertIn("Ensuring coding model (explicit flag/env; not a default pull)", text)
        self.assertIn("Ensure-GpuChatModel $StartupGpuModel", text)

    def test_cpu_server_is_started_without_the_gpu_candidate_flag(self):
        text = (HERE / "START_LOCAL_AGENT_GUI.ps1").read_text(encoding="utf-8")
        self.assertIn("Start-Server '127.0.0.1:11435' 'cpu' $true", text)
        self.assertIn("Start-Server '127.0.0.1:11434' 'gpu' $false $GpuKvCache", text)

    def test_cpu_server_disables_cuda_and_vulkan(self):
        text = (HERE / "START_LOCAL_AGENT_GUI.ps1").read_text(encoding="utf-8")
        start_server = text.split("function Start-Server", 1)[1].split(
            "function Get-ServerModels", 1)[0]
        self.assertIn("$envs['CUDA_VISIBLE_DEVICES'] = '-1'", start_server)
        self.assertIn("$envs['OLLAMA_VULKAN'] = 'false'", start_server)
        self.assertIn("$envs['GGML_VK_VISIBLE_DEVICES'] = '-1'", start_server)
        gpu_candidate = start_server.split(
            "elseif ($GpuKvCacheMode -eq 'flash_q8') {", 1)[1]
        self.assertNotIn("OLLAMA_VULKAN", gpu_candidate.split("}", 1)[0])
        self.assertNotIn("GGML_VK_VISIBLE_DEVICES", gpu_candidate.split("}", 1)[0])
        self.assertNotIn("CUDA_VISIBLE_DEVICES", gpu_candidate.split("}", 1)[0])


if __name__ == "__main__":
    unittest.main()
