#!/usr/bin/env python3
"""Visible agent activity trace v1 — persist, restore, redaction, GUI contract.

Run from local_agent/:  python -m unittest test_activity_trace test_launcher_revision -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import server
import store


class ActivityFromSseTests(unittest.TestCase):
    def test_tool_announce_is_proposal_and_redacts_secret_args(self):
        event = server.activity_from_sse("tool", json.dumps({
            "tool": "write_file",
            "args": {
                "path": "local_agent/README.md",
                "password": "s3cret-value-must-not-persist",
                "content": "full file body must not persist",
                "token": "sk-live-not-for-disk",
            },
        }))
        self.assertIsNotNone(event)
        self.assertEqual("tool_call", event["kind"])
        self.assertEqual("announced", event["state"])
        self.assertEqual("proposal", event["source"])
        blob = json.dumps(event)
        self.assertNotIn("s3cret-value-must-not-persist", blob)
        self.assertNotIn("full file body must not persist", blob)
        self.assertNotIn("sk-live-not-for-disk", blob)
        self.assertIn("password", event["args"]["keys"])
        self.assertEqual("local_agent/README.md", event["args"]["path"])

    def test_tool_result_error_is_observation_not_a_plan(self):
        event = server.activity_from_sse("tool_result", "ERROR: path not found\nsecret=abc")
        self.assertEqual("tool_result", event["kind"])
        self.assertEqual("error", event["state"])
        self.assertEqual("observation", event["source"])
        self.assertEqual("error", event["outcome"])
        self.assertLessEqual(len(event["summary"]), 240)

    def test_refused_tool_result_is_error(self):
        event = server.activity_from_sse("tool_result", "REFUSED: file edit denied")
        self.assertEqual("error", event["state"])

    def test_planning_note_is_proposal(self):
        event = server.activity_from_sse(
            "note", "task plan prepared: read the file; verify the path")
        self.assertEqual("planning", event["kind"])
        self.assertEqual("proposal", event["source"])
        self.assertEqual("announced", event["state"])

    def test_gpu_permission_note_is_waiting_for_permission(self):
        event = server.activity_from_sse(
            "note", "GPU permission is pending in the sidebar: chat reasoning model load")
        self.assertEqual("waiting_for_permission", event["kind"])
        self.assertEqual("announced", event["state"])
        self.assertEqual("observation", event["source"])

    def test_gpu_gate_block_is_not_a_blocked_turn(self):
        # CPU fallback already proceeded; do not persist this as kind=blocked.
        self.assertIsNone(server.activity_from_sse(
            "note", "GPU gate is set to Block; routing this turn to CPU."))

    def test_progress_write_is_draft_not_complete(self):
        event = server.activity_from_sse(
            "progress", json.dumps({"stage": "write", "label": "Writing the answer"}))
        self.assertEqual("planning", event["kind"])
        self.assertEqual("proposal", event["source"])
        self.assertNotEqual("complete", event["kind"])

    def test_progress_evidence_is_verification(self):
        event = server.activity_from_sse(
            "progress", json.dumps({"stage": "evidence", "label": "Checking tool evidence"}))
        self.assertEqual("verification", event["kind"])

    def test_route_keeps_farm_backend_and_capability(self):
        event = server.activity_from_sse("route", json.dumps({
            "tier": "farm",
            "model": "qwen3:8b",
            "backend": "farm",
            "gpu_busy": True,
            "reason": "Mac worker accepted Qwythos",
            "host": "10.90.90.2",
            "detail": {"capability": "tool"},
        }))
        self.assertEqual("route", event["kind"])
        self.assertEqual("farm", event["tier"])
        self.assertEqual("farm", event["backend"])
        self.assertEqual("tool", event["capability"])
        self.assertTrue(event["gpu_busy"])
        self.assertEqual("observation", event["source"])
        self.assertEqual("result", event["state"])
        self.assertNotIn("trace_id", event)

    def test_proposal_farm_route_is_not_observation(self):
        event = server.activity_from_sse("route", json.dumps({
            "tier": "farm",
            "model": "qwythos",
            "backend": "farm",
            "source": "proposal",
            "reason": "attempting farm",
            "hop": 0,
        }))
        self.assertEqual("proposal", event["source"])
        self.assertEqual("announced", event["state"])
        self.assertEqual("attempting farm", event["label"])
        self.assertEqual(0, event["hop"])
        self.assertNotIn("accepted", event["reason"].lower())

    def test_waiting_on_qwythos_progress_is_proposal(self):
        event = server.activity_from_sse("progress", json.dumps({
            "stage": "decide",
            "label": "Waiting on Mac Qwythos",
            "hop": 1,
        }))
        self.assertEqual("planning", event["kind"])
        self.assertEqual("proposal", event["source"])
        self.assertEqual("Waiting on Mac Qwythos", event["label"])
        self.assertEqual(1, event["hop"])

    def test_old_route_without_hop_has_no_hop_key(self):
        event = server.activity_from_sse("route", json.dumps({
            "tier": "gpu", "model": "huihui", "backend": "ollama",
        }))
        self.assertNotIn("hop", event)

    def test_route_copies_hop_null_for_early_return(self):
        event = server.activity_from_sse("route", json.dumps({
            "tier": "cpu", "model": "stub", "backend": "ollama", "hop": None,
        }))
        self.assertIsNone(event["hop"])

    def test_tool_copies_hop(self):
        event = server.activity_from_sse("tool", json.dumps({
            "tool": "list_dir", "args": {"path": "."}, "hop": None,
        }))
        self.assertIsNone(event["hop"])
        event = server.activity_from_sse("tool", json.dumps({
            "tool": "read_file", "args": {"path": "x"}, "hop": 0,
        }))
        self.assertEqual(0, event["hop"])

    def test_tool_result_does_not_grow_a_hop_field(self):
        event = server.activity_from_sse("tool_result", "plain tool text")
        self.assertNotIn("hop", event)

    def test_done_and_error_map_to_complete_and_blocked(self):
        done = server.activity_from_sse("done", "the long assistant reply " * 20)
        self.assertEqual("complete", done["kind"])
        self.assertEqual("Turn complete", done["label"])
        self.assertNotIn("the long assistant reply", done["label"])
        blocked = server.activity_from_sse("error", "OllamaUnavailable: down")
        self.assertEqual("blocked", blocked["kind"])
        self.assertEqual("error", blocked["state"])

    def test_generic_note_is_not_persisted(self):
        self.assertIsNone(server.activity_from_sse("note", "context compacted for the active CPU-safe window"))


class RestoreAndStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(store, "DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_restore_prefers_activity_over_tool_evidence(self):
        message = {
            "role": "assistant",
            "content": "done",
            "activity": [{"kind": "tool_call", "state": "announced", "source": "proposal",
                          "tool": "project_state"}],
            "tool_evidence": [{"tool": "project_state", "outcome": "result", "summary": "ok"}],
        }
        events = server.restore_activity(message)
        self.assertEqual(1, len(events))
        self.assertEqual("tool_call", events[0]["kind"])
        self.assertEqual("proposal", events[0]["source"])

    def test_restore_falls_back_to_tool_evidence_as_observation_only(self):
        events = server.restore_activity({
            "role": "assistant",
            "tool_evidence": [
                {"tool": "read_file", "outcome": "result", "summary": "hello", "path": "README.md"},
                {"tool": "run_code", "outcome": "error", "summary": "ERROR: boom"},
            ],
        })
        self.assertEqual(2, len(events))
        self.assertEqual("tool_result", events[0]["kind"])
        self.assertEqual("observation", events[0]["source"])
        self.assertEqual("result", events[0]["state"])
        self.assertEqual("error", events[1]["state"])
        # Must not invent an announced intention from a stored receipt.
        self.assertFalse(any(e.get("kind") == "tool_call" for e in events))
        self.assertFalse(any(e.get("source") == "proposal" for e in events))

    def test_store_append_round_trips_activity(self):
        conv = store.create("trace restore", model="cpu-test", workspace="general")
        activity = [
            {"kind": "route", "state": "result", "source": "observation", "tier": "cpu",
             "model": "cpu-test", "backend": "ollama"},
            {"kind": "tool_call", "state": "announced", "source": "proposal", "tool": "project_state",
             "args": server.redact_activity_args({"path": "x", "password": "nope"})},
            {"kind": "tool_result", "state": "result", "source": "observation", "tool": "project_state",
             "summary": "ok"},
        ]
        store.append(conv["id"], "assistant", "here is the answer",
                     meta={"activity": activity, "tool_evidence": [
                         {"tool": "project_state", "outcome": "result", "summary": "ok"}],
                           "route": {"tier": "cpu", "model": "cpu-test"}})
        loaded = store.load(conv["id"])
        msg = loaded["messages"][-1]
        self.assertEqual(activity, msg["activity"])
        restored = server.restore_activity(msg)
        self.assertEqual("proposal", restored[1]["source"])
        blob = json.dumps(msg)
        self.assertNotIn("nope", blob)

    def test_farm_last_tier_survives_listing(self):
        conv = store.create("farm turn", model="qwen", workspace="general")
        store.set_last_tier(conv["id"], "farm")
        rows = store.listing()
        match = next(row for row in rows if row["id"] == conv["id"])
        self.assertEqual("farm", match["last_tier"])


class GuiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (HERE / "static" / "index.html").read_text(encoding="utf-8")

    def test_intention_and_observation_labels_are_distinct(self):
        self.assertIn("Announced — not yet observed", self.html)
        self.assertIn("Proposal — not proof of execution", self.html)
        self.assertIn("Observed result", self.html)
        self.assertIn("Observed error", self.html)
        self.assertIn("Waiting for an observed result — this card is not proof the tool ran.",
                      self.html)

    def test_openchat_restores_activity_or_tool_evidence(self):
        self.assertIn("m.activity", self.html)
        self.assertIn("m.tool_evidence", self.html)
        self.assertIn("mountActivity", self.html)

    def test_farm_badge_and_elapsed_are_honest(self):
        compact = self.html.replace(" ", "")
        self.assertIn("t==='farm'?'f'", compact)
        self.assertIn("t==='farm'?'FARM'", compact)
        self.assertIn("fmtElapsed", self.html)
        self.assertIn("Elapsed time is live-only and is not restored", self.html)

    def test_no_trace_id_on_the_wire_contract(self):
        self.assertNotIn("trace_id", self.html)

    def test_live_tool_args_are_redacted(self):
        self.assertIn("function redactArgs", self.html)
        self.assertNotIn("JSON.stringify(t.args)", self.html)

    def test_queued_cards_restamp_from_queue_poll(self):
        self.assertIn("restampQueuedFromQueue", self.html)
        self.assertIn("data-job", self.html)
        self.assertIn("data-kind=queued", self.html)

    def test_hop_and_proposal_farm_route_are_displayed(self):
        self.assertIn("dataset.hop", self.html)
        self.assertIn("attempting farm", self.html)
        self.assertIn("Attempting", self.html)
        self.assertIn("r.source==='proposal'", self.html.replace(" ", ""))


class ReconcileQueuedActivityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        import media_queue as mq
        patcher = patch.object(mq, "QUEUE_ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        chats = root / "chats"
        chats.mkdir()
        chat_patch = patch.object(store, "DIR", chats)
        chat_patch.start()
        self.addCleanup(chat_patch.stop)
        self.mq = mq
        for state in mq._STATES:
            (root / state).mkdir(parents=True)

    def test_pending_queued_card_stays_announced(self):
        job = self.mq.enqueue("vision", {"images": ["probe.png"], "question": "color"})
        activity = [{"kind": "queued", "state": "announced", "source": "observation",
                     "job_id": job["id"], "label": "queued for the next safe media GPU window"}]
        out = server.reconcile_queued_activity(activity)
        self.assertEqual("announced", out[0]["state"])
        self.assertNotIn("filename", out[0])

    def test_done_job_restamps_observed_result_without_inventing_filename(self):
        job = self.mq.enqueue("vision", {"images": ["probe.png"], "question": "color"})
        claimed = self.mq.claim_next(kind="vision")
        self.assertEqual(job["id"], claimed["id"])
        self.mq.complete(job["id"], json.dumps({"available": True, "analysis": "the square is red"}))
        activity = [{"kind": "queued", "state": "announced", "source": "observation",
                     "job_id": job["id"], "label": "queued for the next safe media GPU window"}]
        out = server.reconcile_queued_activity(activity)
        self.assertEqual("queued", out[0]["kind"])
        self.assertEqual("result", out[0]["state"])
        self.assertEqual("observation", out[0]["source"])
        self.assertEqual("done", out[0]["job_status"])
        self.assertIn("red", out[0]["summary"])
        self.assertNotIn("filename", out[0])
        blob = json.dumps(out)
        self.assertNotIn("ComfyUI_", blob)

    def test_failed_and_cancelled_are_observed_errors(self):
        failed = self.mq.enqueue("vision", {"images": ["a.png"]})
        self.mq.claim_next(kind="vision")
        self.mq.fail(failed["id"], "no valid image paths")
        cancelled = self.mq.enqueue("vision", {"images": ["b.png"]})
        self.mq.cancel(cancelled["id"])
        out = server.reconcile_queued_activity([
            {"kind": "queued", "state": "announced", "job_id": failed["id"]},
            {"kind": "queued", "state": "announced", "job_id": cancelled["id"]},
        ])
        self.assertEqual("error", out[0]["state"])
        self.assertEqual("failed", out[0]["job_status"])
        self.assertEqual("error", out[1]["state"])
        self.assertEqual("cancelled", out[1]["job_status"])

    def test_store_round_trip_then_get_shaped_reconcile(self):
        conv = store.create("queued restamp", model="cpu-test", workspace="general")
        job = self.mq.enqueue("vision", {"images": ["probe.png"]})
        store.append(conv["id"], "assistant", "queued",
                     meta={"activity": [{"kind": "queued", "state": "announced",
                                         "source": "observation", "job_id": job["id"],
                                         "label": "queued for the next safe media GPU window"}]})
        self.mq.claim_next(kind="vision")
        self.mq.complete(job["id"], '{"analysis":"red square"}')
        loaded = store.load(conv["id"])
        self.assertTrue(server.reconcile_conversation_activity(loaded))
        store.save(loaded)
        again = store.load(conv["id"])
        card = again["messages"][-1]["activity"][0]
        self.assertEqual("result", card["state"])
        self.assertEqual("media job complete", card["label"])


if __name__ == "__main__":
    unittest.main()
