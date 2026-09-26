#!/usr/bin/env python3
"""Auto (may use Mac farm) picker — unpinned chats, no Huihui regression."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import farm_offload
import file_edit_gate
import gpu_gate
import server
import store


class _Route:
    def __init__(self, tier="cpu", host="127.0.0.1:11435", model="stub-model",
                 backend="ollama"):
        self.tier = tier
        self.host = host
        self.model = model
        self.backend = backend
        self.detail = {}
        self.reason = ""
        self.gpu_busy = False

    def options(self):
        return {}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend}


class AutoFarmHelperTests(unittest.TestCase):
    def test_picker_token_is_not_a_local_model_name(self):
        self.assertTrue(server.wants_auto_farm("auto_farm"))
        self.assertTrue(server.wants_auto_farm("auto-farm"))
        self.assertFalse(server.wants_auto_farm("huihui_ai/qwen3-abliterated:14b"))
        self.assertFalse(server.wants_auto_farm(""))
        self.assertFalse(server.wants_auto_farm(None))

    def test_empty_model_without_routing_is_not_auto_farm(self):
        conv = {"model": "", "routing": ""}
        self.assertFalse(server.is_auto_farm_conversation(conv))
        self.assertIsNone(server.answer_model_for_conversation(conv))

    def test_auto_farm_conversation_passes_none(self):
        conv = {"model": "", "routing": "auto_farm"}
        self.assertTrue(server.is_auto_farm_conversation(conv))
        self.assertIsNone(server.answer_model_for_conversation(conv))

    def test_pinned_huihui_is_never_none(self):
        tag = "huihui_ai/qwen3-abliterated:14b"
        conv = {"model": tag, "routing": ""}
        self.assertEqual(tag, server.answer_model_for_conversation(conv))


class AutoFarmStoreAndSendTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        chats = root / "chats"
        chats.mkdir()
        p = patch.object(store, "DIR", chats)
        p.start()
        self.addCleanup(p.stop)
        self._gate_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._gate_dir.cleanup)
        gpu_gate.STATE_FILE = Path(self._gate_dir.name) / "gpu_gate.json"
        file_edit_gate.STATE_FILE = Path(self._gate_dir.name) / "file_edit_gate.json"
        os.environ["LOCAL_AGENT_TRACING"] = "0"

    def _handler(self):
        h = object.__new__(server.Handler)
        h.wfile = io.BytesIO()
        h.send_response = lambda *a, **k: None
        h.send_header = lambda *a, **k: None
        h.end_headers = lambda: None
        h._json = lambda obj, code=200: None
        return h

    def test_new_auto_farm_chat_stays_unpinned_and_answer_gets_none(self):
        captured = {}

        def fake_answer(history, push, **kwargs):
            captured["model"] = kwargs.get("model", "MISSING")
            push("route", json.dumps({"tier": "farm", "backend": "farm",
                                      "source": "proposal", "reason": "attempting farm"}))
            return "ok"

        h = self._handler()
        with patch.object(agent, "answer", fake_answer):
            h._send_turn({"model": "auto_farm", "message": "Where is TODO.md?",
                          "prefer": "auto", "workspace": "general"})
        rows = store.listing()
        self.assertEqual(1, len(rows))
        conv = store.load(rows[0]["id"])
        self.assertEqual("", conv.get("model"))
        self.assertEqual("auto_farm", conv.get("routing"))
        self.assertIsNone(captured.get("model"))

    def test_plain_pin_path_still_stores_a_local_model(self):
        captured = {}

        def fake_answer(history, push, **kwargs):
            captured["model"] = kwargs.get("model", "MISSING")
            return "ok"

        h = self._handler()
        with patch.object(agent, "answer", fake_answer), \
             patch.object(server.Handler, "_valid_chat_model", return_value=None), \
             patch.object(server.router, "decide",
                          return_value=_Route("gpu", "127.0.0.1:11434",
                                              "huihui_ai/qwen3-abliterated:14b")):
            h._send_turn({"model": "", "message": "hello",
                          "prefer": "auto", "workspace": "general"})
        conv = store.load(store.listing()[0]["id"])
        self.assertEqual("huihui_ai/qwen3-abliterated:14b", conv.get("model"))
        self.assertNotEqual("auto_farm", conv.get("routing"))
        self.assertEqual("huihui_ai/qwen3-abliterated:14b", captured.get("model"))

    def test_legacy_empty_model_is_not_treated_as_auto_farm(self):
        conv = store.create("old chat", model="", workspace="general")
        self.assertFalse(server.is_auto_farm_conversation(conv))
        captured = {}

        def fake_answer(history, push, **kwargs):
            captured["model"] = kwargs.get("model", "MISSING")
            return "ok"

        h = self._handler()
        with patch.object(agent, "answer", fake_answer), \
             patch.object(server.Handler, "_valid_chat_model",
                          return_value="huihui_ai/qwen3-abliterated:14b"):
            h._send_turn({"id": conv["id"], "message": "hello",
                          "prefer": "auto", "workspace": "general"})
        loaded = store.load(conv["id"])
        self.assertEqual("huihui_ai/qwen3-abliterated:14b", loaded.get("model"))
        self.assertEqual("huihui_ai/qwen3-abliterated:14b", captured.get("model"))

    def test_pinned_14b_never_calls_qwythos(self):
        farm_route = _Route("farm", "farm", "qwythos", backend="farm")
        gpu_route = _Route("gpu", "127.0.0.1:11434",
                           "huihui_ai/qwen3-abliterated:14b", backend="ollama")
        called = []

        def fake_decide(*_a, model=None, skip_farm=False, **_k):
            return farm_route if model is None else gpu_route

        def fake_qwythos(*_a, **_k):
            called.append("qwythos")
            return {"content": "farm", "tool_calls": []}

        def fake_stream(*_a, **_k):
            yield "local"

        conv = store.create("pinned", model="huihui_ai/qwen3-abliterated:14b",
                            workspace="general")
        with patch.object(agent.router, "decide", side_effect=fake_decide), \
             patch.object(farm_offload, "try_qwythos_on_farm", side_effect=fake_qwythos), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content": "Where is TODO.md?"}],
                model=server.answer_model_for_conversation(conv))
        self.assertEqual("local", reply)
        self.assertEqual([], called)

    def test_gui_auto_farm_path_emits_proposal_then_observation(self):
        log = []
        before_wait = []
        farm_route = _Route("farm", "farm", "qwythos", backend="farm")

        def fake_qwythos(messages, tools=None, timeout_s=None):
            before_wait.append(list(log))
            return {"content": "OK", "tool_calls": [], "model": "qwythos"}

        def on_event(kind, payload):
            log.append((kind, payload))

        conv = store.create("farm mode", model="", workspace="general",
                            routing="auto_farm")
        with patch.object(agent.router, "decide", return_value=farm_route), \
             patch.object(farm_offload, "try_qwythos_on_farm", side_effect=fake_qwythos), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("local chat should not run")):
            reply = agent.answer(
                [{"role": "user", "content": "Where is TODO.md?"}],
                on_event=on_event,
                model=server.answer_model_for_conversation(conv),
                prefer="auto")
        self.assertEqual("OK", reply)
        self.assertIsNone(server.answer_model_for_conversation(conv))
        pre_routes = [json.loads(p) for k, p in before_wait[0] if k == "route"]
        self.assertTrue(all(r.get("source") == "proposal" for r in pre_routes))
        waiting = [json.loads(p) for k, p in before_wait[0] if k == "progress"]
        self.assertTrue(any(p.get("label") == "Waiting on Mac Qwythos" for p in waiting))
        all_routes = [json.loads(p) for k, p in log if k == "route"]
        self.assertGreaterEqual(len(all_routes), 2)
        self.assertEqual("proposal", all_routes[0].get("source"))
        self.assertNotEqual("proposal", all_routes[-1].get("source"))
        cards = [server.activity_from_sse(k, p) for k, p in log if k == "route"]
        cards = [c for c in cards if c]
        self.assertEqual("proposal", cards[0]["source"])
        self.assertEqual("announced", cards[0]["state"])
        self.assertEqual("observation", cards[-1]["source"])
        self.assertEqual("result", cards[-1]["state"])

    def test_gui_html_has_distinct_farm_option(self):
        html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Auto (may use Mac farm)", html)
        self.assertIn("auto_farm", html)
        self.assertIn("activeRouting==='auto_farm'", html.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
