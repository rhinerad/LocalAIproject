#!/usr/bin/env python3
"""Intent-mismatch capture is local JSONL only — no training, no turn mutation."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import feedback_manager
import intent_mismatch
import memory
import store


class IntentMismatchTests(unittest.TestCase):
    def _chat(self, root: Path):
        return patch.object(store, "DIR", root / "chats"), \
            patch.object(intent_mismatch, "LOG_PATH", root / "runtime" / "intent_mismatch.jsonl")

    def _turn(self, user, assistant, *, route=None, tools=None):
        conv = store.create(user)
        store.append(conv["id"], "user", user)
        meta = {"route": route or {}, "tool_evidence": tools or []}
        store.append(conv["id"], "assistant", assistant, meta=meta)
        return conv["id"]

    def test_capture_writes_user_assistant_tools_route_and_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log:
                cid = self._turn(
                    "do the thing",
                    "I listed the folder instead.",
                    route={"model": "huihui_ai/qwen3-abliterated:14b",
                           "tier": "gpu",
                           "reason": "GPU free",
                           "host": "127.0.0.1:11434",
                           "backend": "ollama",
                           "detail": {"capability": "tool"}},
                    tools=[{"tool": "list_dir", "outcome": "result",
                            "summary": "3 files"}])
                before = (store.DIR / f"{cid}.json").read_bytes()
                result = intent_mismatch.capture(cid)
                self.assertTrue(result["ok"])
                self.assertEqual("runtime/intent_mismatch.jsonl", result["path"])
                self.assertEqual(before, (store.DIR / f"{cid}.json").read_bytes())
                rows = intent_mismatch.LOG_PATH.read_text(encoding="utf8").strip().splitlines()
                self.assertEqual(1, len(rows))
                rec = json.loads(rows[0])
                self.assertEqual("intent_mismatch", rec["kind"])
                self.assertEqual("do the thing", rec["user_message"])
                self.assertEqual("I listed the folder instead.", rec["assistant_message"])
                self.assertEqual("list_dir", rec["tool_calls"][0]["tool"])
                self.assertEqual("gpu", rec["route"]["tier"])
                self.assertEqual("huihui_ai/qwen3-abliterated:14b", rec["route"]["model"])
                self.assertEqual("tool", rec["route"]["capability"])
                self.assertFalse(rec["route_incomplete"])
                self.assertIn("ts", rec)
                self.assertIsInstance(rec["flagged_at"], float)

    def test_specific_index_not_the_later_turn(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log:
                conv = store.create("first")
                cid = conv["id"]
                store.append(cid, "user", "vague first request")
                store.append(cid, "assistant", "wrong first reply", meta={
                    "route": {"model": "a", "tier": "cpu", "detail": {"capability": "logic"}},
                    "tool_evidence": [{"tool": "read_file", "outcome": "result", "summary": "ok"}]})
                store.append(cid, "user", "and now something else")
                store.append(cid, "assistant", "later reply", meta={
                    "route": {"model": "b", "tier": "gpu"}})
                intent_mismatch.capture(cid, 1)
                rec = json.loads(intent_mismatch.LOG_PATH.read_text(encoding="utf8"))
                self.assertEqual("vague first request", rec["user_message"])
                self.assertEqual("wrong first reply", rec["assistant_message"])
                self.assertEqual("read_file", rec["tool_calls"][0]["tool"])
                self.assertEqual("cpu", rec["route"]["tier"])
                self.assertEqual(1, rec["assistant_index"])

    def test_defaults_to_last_assistant(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log:
                conv = store.create("first")
                cid = conv["id"]
                store.append(cid, "user", "one")
                store.append(cid, "assistant", "first reply")
                store.append(cid, "user", "two")
                store.append(cid, "assistant", "second reply", meta={
                    "route": {"model": "x", "tier": "gpu"}})
                rec = json.loads(json.dumps(intent_mismatch.capture(cid)))
                line = json.loads(intent_mismatch.LOG_PATH.read_text(encoding="utf8"))
                self.assertEqual("two", line["user_message"])
                self.assertEqual("second reply", line["assistant_message"])
                self.assertEqual(3, rec["assistant_index"])

    def test_append_only_two_flags_two_lines(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log:
                cid = self._turn("q", "a", route={"model": "m", "tier": "cpu"})
                intent_mismatch.capture(cid)
                intent_mismatch.capture(cid)
                lines = intent_mismatch.LOG_PATH.read_bytes().splitlines()
                self.assertEqual(2, len(lines))
                self.assertTrue(intent_mismatch.LOG_PATH.read_bytes().endswith(b"\n"))

    def test_does_not_touch_memory_or_encrypted_feedback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log, \
                 patch.object(memory, "_STORE", root / "memory.json"), \
                 patch.object(memory, "remember") as remembered, \
                 patch.object(feedback_manager, "enqueue") as queued:
                cid = self._turn("q", "a", route={"model": "m", "tier": "gpu"})
                intent_mismatch.capture(cid)
                remembered.assert_not_called()
                queued.assert_not_called()
                self.assertEqual([], memory.list_facts())

    def test_missing_conversation_and_bad_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log:
                with self.assertRaisesRegex(ValueError, "conversation not found"):
                    intent_mismatch.capture("deadbeefdeadbeef")
                cid = self._turn("q", "a")
                with self.assertRaisesRegex(ValueError, "message_index"):
                    intent_mismatch.capture(cid, 0)
                with self.assertRaisesRegex(ValueError, "message_index"):
                    intent_mismatch.capture(cid, "nope")

    def test_old_turn_without_route_is_marked_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats, log = self._chat(root)
            with chats, log:
                conv = store.create("q")
                cid = conv["id"]
                store.append(cid, "user", "q")
                store.append(cid, "assistant", "a")
                store.set_last_tier(cid, "gpu")
                rec = json.loads(json.dumps(intent_mismatch.capture(cid)))
                line = json.loads(intent_mismatch.LOG_PATH.read_text(encoding="utf8"))
                self.assertTrue(line["route_incomplete"])
                self.assertEqual("gpu", line["route"]["tier"])
                self.assertTrue(rec["ok"])

    def test_gui_has_the_flag_button_and_endpoint(self):
        page = (HERE / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("this wasn't what I meant", page)
        self.assertIn("/api/intent_mismatch", page)
        self.assertIn("sendIntentMismatch", page)
        server = (HERE / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/intent_mismatch"', server)
        self.assertIn('"route": dict(_last_route)', server)
        # The exact revision string is pinned against the launcher by
        # test_launcher_revision; pinning it here too goes stale every bump.
        self.assertRegex(server, r'(?m)^APP_REVISION = "[^"]+"$')


if __name__ == "__main__":
    unittest.main()
