"""Offline contract tests for the unlaunched PowerInfer OpenAI adapter."""
from __future__ import annotations

import unittest

import powerinfer_openai_proxy as proxy


class PowerInferProxyTests(unittest.TestCase):
    def test_renders_system_and_multi_turn_llama2_prompt(self):
        prompt = proxy.render_llama2_chat([
            {"role": "system", "content": "Follow local policy."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Continue"},
        ])
        self.assertIn("<<SYS>>\nFollow local policy.", prompt)
        self.assertIn("Hello [/INST] Hi</s>", prompt)
        self.assertTrue(prompt.endswith("[INST] Continue [/INST]"))

    def test_rejects_non_alternating_or_tool_messages(self):
        with self.assertRaises(proxy.ProxyError):
            proxy.render_llama2_chat([{"role": "assistant", "content": "No"}])
        with self.assertRaises(proxy.ProxyError):
            proxy.render_llama2_chat([{"role": "user", "content": "A"}, {"role": "tool", "content": "B"}])

    def test_payload_clamps_completion_and_enables_prompt_cache(self):
        payload = proxy.completion_payload({
            "messages": [{"role": "user", "content": "Test"}],
            "max_tokens": proxy.MAX_COMPLETION_TOKENS + 1,
        })
        self.assertEqual(proxy.MAX_COMPLETION_TOKENS, payload["n_predict"])
        self.assertTrue(payload["cache_prompt"])
        self.assertEqual(-1, payload["n_keep"])

    def test_default_stop_sequences_injected_when_caller_omits_stop(self):
        payload = proxy.completion_payload({
            "messages": [{"role": "user", "content": "Test"}],
        })
        self.assertIn("stop", payload)
        self.assertIn("</s>", payload["stop"])
        self.assertIn("[INST]", payload["stop"])

    def test_caller_stop_sequences_are_not_overridden(self):
        payload = proxy.completion_payload({
            "messages": [{"role": "user", "content": "Test"}],
            "stop": ["END"],
        })
        self.assertEqual(["END"], payload["stop"])

    def test_proxy_refuses_non_loopback_bind(self):
        old = proxy.LISTEN_HOST
        try:
            proxy.LISTEN_HOST = "0.0.0.0"
            with self.assertRaises(SystemExit):
                proxy.main()
        finally:
            proxy.LISTEN_HOST = old

    def test_proxy_refuses_to_start_without_an_accepted_registry_bundle(self):
        old_host, old_path, old_model = proxy.LISTEN_HOST, proxy.REGISTRY_PATH, proxy.REGISTRY_MODEL_ID
        try:
            proxy.LISTEN_HOST = "127.0.0.1"
            proxy.REGISTRY_PATH = ""
            proxy.REGISTRY_MODEL_ID = ""
            with self.assertRaisesRegex(SystemExit, "accepted sparse bundle"):
                proxy.main()
        finally:
            proxy.LISTEN_HOST, proxy.REGISTRY_PATH, proxy.REGISTRY_MODEL_ID = old_host, old_path, old_model


if __name__ == "__main__":
    unittest.main(verbosity=2)
