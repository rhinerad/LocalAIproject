#!/usr/bin/env python3
"""PowerInfer picker transport tests. No server.exe or proxy is started."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ollama_client as oll
import powerinfer_client
import router


class PowerInferChatRouteTests(unittest.TestCase):
    def test_flatten_merges_tool_results_into_alternating_text_roles(self):
        messages = [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Read it"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file"}}]},
            {"role": "tool", "name": "read_file", "content": "hello"},
            {"role": "user", "content": "Thanks"},
        ]
        flat = powerinfer_client.flatten_messages(messages)
        self.assertEqual(
            [m["role"] for m in flat],
            ["system", "user", "assistant", "user"],
        )
        self.assertIn("Tool read_file result:", flat[3]["content"])
        self.assertIn("Thanks", flat[3]["content"])

    def test_chat_stream_dispatches_to_powerinfer_client_not_ollama_api(self):
        seen = {}

        def fake_stream(*_args, **kwargs):
            seen.update(kwargs)
            yield "ok"

        with patch.object(powerinfer_client, "chat_stream", side_effect=fake_stream):
            pieces = list(oll.chat_stream(
                [{"role": "user", "content": "Hi"}],
                model=router.POWERINFER_MODEL_ALIAS,
                host=router.POWERINFER_PROXY_HOST,
                tools=[{"type": "function"}],
            ))
        self.assertEqual(["ok"], pieces)
        self.assertEqual(router.POWERINFER_PROXY_HOST, seen["host"])
        self.assertNotIn("tools", seen)

    def test_unreachable_proxy_raises_without_hanging(self):
        class Boom(Exception):
            pass

        def fail_open(*_args, **_kwargs):
            raise TimeoutError("timed out")

        with patch.object(powerinfer_client.urllib.request, "urlopen", fail_open):
            with self.assertRaises(oll.OllamaUnavailable) as ctx:
                powerinfer_client.chat(
                    [{"role": "user", "content": "Hi"}],
                    host="127.0.0.1:65534",
                    model=router.POWERINFER_MODEL_ALIAS,
                    timeout=1,
                )
        self.assertIn("does not start", str(ctx.exception))

    def test_sse_stream_yields_delta_content(self):
        chunks = [
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            b"data: [DONE]\n",
        ]

        class _Resp:
            def __iter__(self):
                return iter(chunks)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch.object(powerinfer_client.urllib.request, "urlopen",
                          return_value=_Resp()):
            text = "".join(powerinfer_client.chat_stream(
                [{"role": "user", "content": "Hi"}],
                host=router.POWERINFER_PROXY_HOST,
                model=router.POWERINFER_MODEL_ALIAS,
            ))
        self.assertEqual("Hello", text)

    def test_tcp_probe_timeout_does_not_wait_on_inference(self):
        # powerinfer_ready must use the short connect timeout, not an HTTP generate.
        with patch.object(router, "_tcp_up", return_value=False) as probe:
            ready, why = router.powerinfer_ready()
        self.assertFalse(ready)
        self.assertGreaterEqual(probe.call_count, 1)
        self.assertLessEqual(probe.call_args.kwargs.get("timeout", 0.4), 0.4)
        self.assertIn("does not start", why)

    def test_powerinfer_picker_entry_is_base_completion_not_chat(self):
        with patch.object(router, "powerinfer_ready", return_value=(False, "not running")):
            with patch.object(router, "up", return_value=False):
                models = router.chat_models(include_gpu=False)
        pi_entry = next(
            (m for m in models if m["name"] == router.POWERINFER_MODEL_ALIAS), None
        )
        self.assertIsNotNone(pi_entry)
        self.assertEqual("base_completion", pi_entry["kind"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
