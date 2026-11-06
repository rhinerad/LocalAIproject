#!/usr/bin/env python3
"""LXMF bridge abuse limits (audit 2026-11-02 #21), mocked, no RNS/LXMF.

Covers: bounded inbox with a throttled "busy" refusal, per-identity token
bucket for paired turns, per-request attachment total, per-identity disk
quota under uploads/lxmf/<identity>/, and at most one "not authorised"
reply per hour per unpaired source hash.
"""
from __future__ import annotations

import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lxmf_agent
import media_queue
import remote_security
import store


IDENTITY = "11" * 16
OTHER = "22" * 16


class _FakeAgent:
    def __init__(self):
        self.calls = []

    def answer(self, history, **kwargs):
        self.calls.append((history, kwargs))
        return "Reply from the workstation."


def _message(identity=IDENTITY, text="hello", seq=0, fields=None):
    return SimpleNamespace(source_hash=bytes.fromhex(identity),
                           content=text.encode(), hash=bytes.fromhex(f"{seq:064x}"),
                           fields=fields or {})


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_dir = store.DIR
        store.DIR = self.root / "chats"
        self.old_schedule_state = lxmf_agent.phone_scheduler.STATE
        self.old_schedule_audit = lxmf_agent.phone_scheduler.AUDIT
        self.old_queue_root = media_queue.QUEUE_ROOT
        lxmf_agent.phone_scheduler.STATE = self.root / "phone-schedules.json"
        lxmf_agent.phone_scheduler.AUDIT = self.root / "phone-schedule-audit.jsonl"
        media_queue.QUEUE_ROOT = self.root / "media-queue"
        self.pairs = self.root / "paired.json"
        self.audit = self.root / "tool-audit.jsonl"
        self.unpaired_audit = self.root / "unpaired-attempts.jsonl"
        self.uploads = self.root / "uploads"
        self.attachment_audit = self.root / "attachment-audit.jsonl"
        self.sent = []
        self.now = 1000.0
        self.fake = _FakeAgent()
        self.core = lxmf_agent.BridgeCore(
            lambda recipient, text, fields: self.sent.append((recipient, text, fields)),
            agent_module=self.fake, pairings_path=self.pairs, audit_path=self.audit,
            unpaired_audit_path=self.unpaired_audit,
            uploads_dir=self.uploads, attachment_audit_path=self.attachment_audit,
            media_completion_audit_path=self.root / "media-delivery-audit.jsonl",
            choose_model=lambda _pair: "stub-model",
            clock=lambda: self.now)

    def tearDown(self):
        store.DIR = self.old_dir
        lxmf_agent.phone_scheduler.STATE = self.old_schedule_state
        lxmf_agent.phone_scheduler.AUDIT = self.old_schedule_audit
        media_queue.QUEUE_ROOT = self.old_queue_root
        self.tmp.cleanup()

    def _refusals(self):
        return [t for _, t, f in self.sent if f["equal_shares_agent"]["kind"] == "refused"]

    def _audit_rows(self, path):
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class UnpairedThrottleTests(_Base):
    def test_unpaired_sender_hears_one_refusal_per_hour_but_every_attempt_is_audited(self):
        for seq in range(5):
            self.core.handle(_message(OTHER, seq=seq))
        self.assertFalse(self.fake.calls)
        self.assertEqual(1, len(self.sent))
        self.assertIn("Not authorised", self.sent[0][1])
        self.assertEqual(5, len(self._audit_rows(self.unpaired_audit)))

        self.now += lxmf_agent.UNPAIRED_REFUSAL_INTERVAL_SECONDS - 1
        self.core.handle(_message(OTHER, seq=10))
        self.assertEqual(1, len(self.sent), "still inside the hour: silence")

        self.now += 2
        self.core.handle(_message(OTHER, seq=11))
        self.assertEqual(2, len(self.sent), "a new hour allows one more refusal")

    def test_unpaired_throttle_is_per_source_hash(self):
        third = "33" * 16
        self.core.handle(_message(OTHER, seq=1))
        self.core.handle(_message(third, seq=2))
        self.assertEqual([bytes.fromhex(OTHER), bytes.fromhex(third)],
                         [r for r, _, _ in self.sent])


class TurnRateLimitTests(_Base):
    def setUp(self):
        super().setUp()
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)

    def test_token_bucket_allows_the_burst_then_refuses_without_storing(self):
        limit = lxmf_agent.TURN_RATE_LIMIT
        for seq in range(limit):
            self.core.handle(_message(seq=seq, text=f"turn {seq}"))
        self.assertEqual(limit, len(self.fake.calls))

        self.core.handle(_message(seq=100, text="one too many"))
        self.assertEqual(limit, len(self.fake.calls), "agent must not run")
        refusals = self._refusals()
        self.assertEqual(1, len(refusals))
        self.assertIn("Rate limit", refusals[0])
        pair = remote_security.get_pair(IDENTITY, self.pairs)
        contents = [m["content"] for m in store.load(pair["conversation_id"])["messages"]]
        self.assertFalse(any("one too many" in c for c in contents),
                         "rate-limited turn is not written to the conversation")

    def test_rate_limit_refusal_reply_is_itself_throttled(self):
        for seq in range(lxmf_agent.TURN_RATE_LIMIT):
            self.core.handle(_message(seq=seq))
        self.core.handle(_message(seq=200))
        self.core.handle(_message(seq=201))
        self.core.handle(_message(seq=202))
        self.assertEqual(1, len(self._refusals()), "one refusal per minute per identity")
        self.now += lxmf_agent.LIMIT_REFUSAL_INTERVAL_SECONDS + 1
        self.core.handle(_message(seq=203))
        self.assertEqual(2, len(self._refusals()))

    def test_bucket_refills_at_the_configured_rate(self):
        limit = lxmf_agent.TURN_RATE_LIMIT
        window = lxmf_agent.TURN_RATE_WINDOW_SECONDS
        for seq in range(limit):
            self.core.handle(_message(seq=seq))
        self.core.handle(_message(seq=300))
        self.assertEqual(limit, len(self.fake.calls))
        # One token comes back every window/limit seconds.
        self.now += window / limit + 0.01
        self.core.handle(_message(seq=301, text="after refill"))
        self.assertEqual(limit + 1, len(self.fake.calls))
        self.assertEqual("after refill", self.fake.calls[-1][0][-1]["content"])

    def test_attachments_of_a_rate_limited_turn_are_not_stored(self):
        for seq in range(lxmf_agent.TURN_RATE_LIMIT):
            self.core.handle(_message(seq=seq))
        self.core.handle(_message(seq=400, fields={
            lxmf_agent.FIELD_FILE_ATTACHMENTS: [["evidence.mp4", b"bytes-that-must-not-land"]]}))
        self.assertFalse(list(self.uploads.rglob("*.mp4")))

    def test_rate_limit_is_per_identity(self):
        remote_security.pair(OTHER, "second phone", path=self.pairs)
        for seq in range(lxmf_agent.TURN_RATE_LIMIT):
            self.core.handle(_message(seq=seq))
        self.core.handle(_message(OTHER, seq=500, text="other phone"))
        self.assertEqual("other phone", self.fake.calls[-1][0][-1]["content"])


class AttachmentBudgetTests(_Base):
    def setUp(self):
        super().setUp()
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)

    def test_per_request_total_caps_the_sum_not_each_item(self):
        with patch.object(lxmf_agent, "MAX_REQUEST_ATTACHMENT_BYTES", 10), \
             patch.object(lxmf_agent, "MAX_ATTACHMENT_BYTES", 10):
            self.core.handle(_message(seq=1, text="two files", fields={
                lxmf_agent.FIELD_FILE_ATTACHMENTS: [["a.mp4", b"123456"], ["b.mp4", b"abcdef"]]}))
        saved = sorted(p.name for p in self.uploads.rglob("*.mp4"))
        self.assertEqual(["a.mp4"], saved, "second 6-byte file exceeds the 10-byte total")
        pair = remote_security.get_pair(IDENTITY, self.pairs)
        user = store.load(pair["conversation_id"])["messages"][0]
        self.assertIn("Attachment not stored", user["content"])
        self.assertIn("b.mp4", user["content"])
        self.assertEqual(1, len(user["attachments"]))
        events = [r["event"] for r in self._audit_rows(self.attachment_audit)]
        self.assertEqual(["received_attachment", "refused_attachment"], events)
        self.assertEqual(1, len(self.fake.calls))

    def test_identity_disk_quota_refuses_rather_than_evicts(self):
        with patch.object(lxmf_agent, "IDENTITY_UPLOAD_QUOTA_BYTES", 10):
            self.core.handle(_message(seq=1, text="first", fields={
                lxmf_agent.FIELD_FILE_ATTACHMENTS: [["one.mp4", b"123456"]]}))
            self.core.handle(_message(seq=2, text="second", fields={
                lxmf_agent.FIELD_FILE_ATTACHMENTS: [["two.mp4", b"abcdef"]]}))
        saved = sorted(p.name for p in self.uploads.rglob("*.mp4"))
        self.assertEqual(["one.mp4"], saved, "earlier upload is kept; new one refused")
        self.assertTrue((self.uploads / IDENTITY).is_dir(), "quota is measured per identity dir")
        rows = self._audit_rows(self.attachment_audit)
        self.assertEqual("refused_attachment", rows[-1]["event"])
        self.assertIn("quota", rows[-1]["reason"])
        self.assertEqual(2, len(self.fake.calls), "text turns still go through")

    def test_attachment_only_message_over_budget_is_refused_without_a_model_turn(self):
        with patch.object(lxmf_agent, "MAX_REQUEST_ATTACHMENT_BYTES", 3), \
             patch.object(lxmf_agent, "MAX_ATTACHMENT_BYTES", 3):
            self.core.handle(_message(seq=1, text="", fields={
                lxmf_agent.FIELD_IMAGE: ["webp", b"image-bytes"]}))
        self.assertFalse(self.fake.calls)
        self.assertEqual(1, len(self._refusals()))
        self.assertFalse(list(self.uploads.rglob("*.webp")))

    def test_uploads_are_laid_out_per_identity_then_request(self):
        self.core.handle(_message(seq=7, text="photo", fields={
            lxmf_agent.FIELD_IMAGE: ["webp", b"image-bytes"]}))
        saved = list(self.uploads.rglob("*.webp"))
        self.assertEqual(1, len(saved))
        self.assertEqual(IDENTITY, saved[0].parent.parent.name)
        self.assertEqual(f"{7:064x}"[:32], saved[0].parent.name)


class InboxOverflowTests(_Base):
    def test_paired_overflow_gets_one_busy_reply_per_minute_unpaired_gets_silence(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        self.assertTrue(self.core.refuse_overflow(_message(seq=1)))
        self.assertFalse(self.core.refuse_overflow(_message(seq=2)))
        self.assertEqual(1, len(self._refusals()))
        self.assertIn("inbox is full", self._refusals()[0])
        self.assertFalse(self.core.refuse_overflow(_message(OTHER, seq=3)))
        self.assertEqual(1, len(self.sent))
        self.now += lxmf_agent.LIMIT_REFUSAL_INTERVAL_SECONDS + 1
        self.assertTrue(self.core.refuse_overflow(_message(seq=4)))

    def test_bridge_inbox_is_bounded_and_overflow_is_routed_to_the_core(self):
        bridge = lxmf_agent.LXMFBridge.__new__(lxmf_agent.LXMFBridge)
        bridge.inbox = queue.Queue(maxsize=2)
        refused = []
        bridge.core = SimpleNamespace(refuse_overflow=refused.append)
        for seq in range(5):
            bridge._enqueue_inbound(_message(seq=seq))
        self.assertEqual(2, bridge.inbox.qsize())
        self.assertEqual(3, len(refused))
        self.assertEqual(32, lxmf_agent.INBOX_MAX_PENDING)
        source = (HERE / "lxmf_agent.py").read_text(encoding="utf-8")
        self.assertIn("queue.Queue(maxsize=INBOX_MAX_PENDING)", source)
        self.assertIn("register_delivery_callback(self._enqueue_inbound)", source)
        self.assertNotIn("register_delivery_callback(self.inbox.put)", source)


if __name__ == "__main__":
    unittest.main()
