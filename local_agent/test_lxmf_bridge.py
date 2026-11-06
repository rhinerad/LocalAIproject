#!/usr/bin/env python3
"""Mocked Phase-1 LXMF security and transport acceptance tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import lxmf_agent
import media_queue
import remote_security
import store
import tools


IDENTITY = "11" * 16
OTHER = "22" * 16


class _FakeAgent:
    def __init__(self, action=None):
        self.calls = []
        self.action = action

    def answer(self, history, **kwargs):
        self.calls.append((history, kwargs))
        if self.action:
            return self.action(kwargs["tool_context"])
        return "Reply from the workstation."


class _EventAgent:
    def answer(self, _history, **kwargs):
        kwargs["on_event"]("route", json.dumps({"tier": "cpu"}))
        kwargs["on_event"]("tool", json.dumps({"tool": "see_image", "args": {"path": "secret"}}))
        kwargs["on_event"]("tool_result", "secret tool result")
        return "Finished safely."


def _message(identity=IDENTITY, text="hello", message_id="aa" * 32):
    return SimpleNamespace(source_hash=bytes.fromhex(identity),
                           content=text.encode(), hash=bytes.fromhex(message_id),
                           fields={})


class LXMFBridgeTests(unittest.TestCase):
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
        self.pairs = self.root / "paired.json"
        self.audit = self.root / "tool-audit.jsonl"
        self.unpaired_audit = self.root / "unpaired-attempts.jsonl"
        self.uploads = self.root / "uploads"
        self.attachment_audit = self.root / "attachment-audit.jsonl"
        self.media_delivery_audit = self.root / "media-delivery-audit.jsonl"
        media_queue.QUEUE_ROOT = self.root / "media-queue"
        self.sent = []

    def tearDown(self):
        store.DIR = self.old_dir
        lxmf_agent.phone_scheduler.STATE = self.old_schedule_state
        lxmf_agent.phone_scheduler.AUDIT = self.old_schedule_audit
        media_queue.QUEUE_ROOT = self.old_queue_root
        self.tmp.cleanup()

    def _core(self, fake):
        return lxmf_agent.BridgeCore(
            lambda recipient, text, fields: self.sent.append((recipient, text, fields)),
            agent_module=fake, pairings_path=self.pairs, audit_path=self.audit,
            unpaired_audit_path=self.unpaired_audit,
            uploads_dir=self.uploads, attachment_audit_path=self.attachment_audit,
            media_completion_audit_path=self.media_delivery_audit,
            choose_model=lambda _pair: "stub-model")

    def test_paired_identity_completes_turn_and_sources_persist(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        fake = _FakeAgent()
        self._core(fake).handle(_message())
        self.assertEqual("Reply from the workstation.", self.sent[-1][1])
        pair = remote_security.get_pair(IDENTITY, self.pairs)
        conv = store.load(pair["conversation_id"])
        self.assertEqual(["phone", "phone"], [m["source"] for m in conv["messages"]])
        self.assertEqual(IDENTITY, conv["messages"][0]["remote_identity"])
        context = fake.calls[0][1]["tool_context"]
        self.assertEqual(IDENTITY, context.remote_identity)
        # The stored conversation needs an initial display model, but a phone
        # with no explicit identity pin must re-run automatic routing per turn.
        self.assertIsNone(fake.calls[0][1]["model"])

    def test_explicit_phone_model_stays_pinned(self):
        remote_security.pair(IDENTITY, "test phone", model="chosen-model", path=self.pairs)
        fake = _FakeAgent()
        self._core(fake).handle(_message())
        self.assertEqual("chosen-model", fake.calls[0][1]["model"])

    def test_exact_phone_cancel_is_immediate_and_identity_scoped(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        lxmf_agent.phone_scheduler.create(IDENTITY, "{n}", 30, 3)
        fake = _FakeAgent()
        self._core(fake).handle(_message(text="cancel the active phone schedule"))
        self.assertFalse(fake.calls)
        self.assertIn("Cancelled the active phone message schedule", self.sent[-1][1])
        jobs = lxmf_agent.phone_scheduler.list_for_identity(IDENTITY)
        self.assertEqual("cancelled", jobs[0]["status"])

    def test_completed_phone_media_is_delivered_once_without_model_call(self):
        pair = remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        conv = store.create("photo", model="stub")
        remote_security.set_conversation(IDENTITY, conv["id"], self.pairs)
        job = {
            "id": "media-job", "kind": "vision",
            "args": {"__remote_media_identity": IDENTITY,
                     "__remote_media_conversation_id": conv["id"],
                     "__remote_media_request_id": "request-1"},
            "result": json.dumps({"available": True,
                                  "analysis": "A clearly described test image."}),
        }
        done = media_queue.QUEUE_ROOT / "done"
        done.mkdir(parents=True)
        (done / "media-job.json").write_text(json.dumps(job), encoding="utf8")
        fake = _FakeAgent()
        core = self._core(fake)
        self.assertEqual(["media-job"], core.drain_media_completions())
        self.assertFalse(fake.calls)
        self.assertEqual("media_result", self.sent[-1][2]["equal_shares_agent"]["kind"])
        self.assertIn("A clearly described test image.", self.sent[-1][1])
        self.assertEqual([], core.drain_media_completions())
        messages = store.load(conv["id"])["messages"]
        self.assertEqual("phone", messages[-1]["source"])

    def test_unpaired_identity_is_refused_before_agent_call(self):
        fake = _FakeAgent()
        message = _message(OTHER)
        message.fields = {lxmf_agent.FIELD_FILE_ATTACHMENTS: [["private.mp4", b"no-save"]]}
        self._core(fake).handle(message)
        self.assertFalse(fake.calls)
        self.assertIn("Not authorised", self.sent[-1][1])
        self.assertFalse(self.uploads.exists())
        self.assertTrue(self.unpaired_audit.is_file())
        self.assertEqual(OTHER, json.loads(self.unpaired_audit.read_text().splitlines()[-1])["identity"])

    def test_gated_remote_tool_is_denied_and_audited(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        def action(context):
            return tools.call("write_file", {"path": "work/phone_attempt.txt",
                                              "content": "must not write"},
                              context=context)
        self._core(_FakeAgent(action)).handle(_message(message_id="bb" * 32))
        self.assertIn("not permitted", self.sent[-1][1])
        self.assertFalse((HERE.parent / "work" / "phone_attempt.txt").exists())
        rows = [json.loads(line) for line in self.audit.read_text().splitlines()]
        self.assertEqual("denied", rows[-1]["outcome"])
        self.assertEqual("write_file", rows[-1]["tool"])
        self.assertNotIn("must not write", json.dumps(rows[-1]))

    def test_remote_media_queue_metadata_is_injected_below_the_model(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        context = remote_security.context_for(
            IDENTITY, "phone-chat", "phone-request", self.pairs, self.audit)
        original = tools.TOOLS["see_image"]
        captured = []
        tools.TOOLS["see_image"] = (lambda args: captured.append(dict(args)) or "queued", original[1])
        try:
            self.assertEqual("queued", tools.call("see_image", {"path": "photo.webp"},
                                                   context=context))
        finally:
            tools.TOOLS["see_image"] = original
        self.assertEqual(IDENTITY, captured[0]["__remote_media_identity"])
        self.assertEqual("phone-chat", captured[0]["__remote_media_conversation_id"])
        self.assertEqual("phone-request", captured[0]["__remote_media_request_id"])

    def test_paired_sideband_attachment_is_path_only_and_tool_directed(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        fake = _FakeAgent()
        message = _message(text="hello", message_id="cc" * 32)
        message.fields = {lxmf_agent.FIELD_IMAGE: ["webp", b"image-bytes"]}
        self._core(fake).handle(message)
        pair = remote_security.get_pair(IDENTITY, self.pairs)
        conv = store.load(pair["conversation_id"])
        user = conv["messages"][0]
        saved = list(self.uploads.rglob("*.webp"))
        self.assertEqual(1, len(saved))
        self.assertEqual(b"image-bytes", saved[0].read_bytes())
        self.assertIn(str(saved[0].resolve()), user["content"])
        self.assertIn("Call see_image", user["content"])
        self.assertNotIn("image-bytes", user["content"])
        self.assertEqual("image", user["attachments"][0]["kind"])
        audit = json.loads(self.attachment_audit.read_text().splitlines()[-1])
        self.assertEqual("received_attachment", audit["event"])
        self.assertNotIn("image-bytes", json.dumps(audit))

    def test_file_attachment_is_routed_by_media_extension(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        fake = _FakeAgent()
        message = _message(text="analyze this", message_id="dd" * 32)
        message.fields = {lxmf_agent.FIELD_FILE_ATTACHMENTS: [["take.mp4", b"video-bytes"]]}
        self._core(fake).handle(message)
        pair = remote_security.get_pair(IDENTITY, self.pairs)
        user = store.load(pair["conversation_id"])["messages"][0]
        self.assertEqual("video", user["attachments"][0]["kind"])
        self.assertIn("Call analyze_video or extract_video_actions", user["content"])

    def test_phone_progress_never_exposes_tool_arguments_or_results(self):
        remote_security.pair(IDENTITY, "test phone", path=self.pairs)
        self._core(_EventAgent()).handle(_message(message_id="ee" * 32))
        statuses = [entry for entry in self.sent
                    if entry[2]["equal_shares_agent"]["kind"] == "status"]
        text = "\n".join(entry[1] for entry in statuses)
        self.assertIn("CPU", text)
        self.assertIn("see_image", text)
        self.assertNotIn("secret", text)

    def test_comfyui_cpu_route_is_described_as_temporary(self):
        core = self._core(_FakeAgent())
        core._phone_event(bytes.fromhex(IDENTITY), "request", "chat", "route",
                          json.dumps({"tier": "cpu", "reason": "a ComfyUI backend is listening"}))
        self.assertIn("temporary CPU fallback", self.sent[-1][1])

    def test_explicit_grant_is_per_identity(self):
        remote_security.pair(IDENTITY, path=self.pairs)
        remote_security.pair(OTHER, path=self.pairs)
        remote_security.set_tool_grant(IDENTITY, "run_build", True, self.pairs)
        allowed = remote_security.context_for(IDENTITY, path=self.pairs)
        denied = remote_security.context_for(OTHER, path=self.pairs)
        self.assertTrue(allowed.permits("run_build"))
        self.assertFalse(denied.permits("run_build"))

    def test_remote_context_never_weakens_underlying_tool_guards(self):
        remote_security.pair(IDENTITY, path=self.pairs)
        remote_security.set_tool_grant(IDENTITY, "run_build", True, self.pairs)
        remote_security.set_tool_grant(IDENTITY, "write_file", True, self.pairs)
        context = remote_security.context_for(
            IDENTITY, "chat", "request", self.pairs, self.audit)
        cases = [
            ("unknown_tool", {}, "ERROR: no tool"),
            ("clip_info", {"clip": "../etc"}, "not a clip id"),
            ("read_doc", {"name": "/etc/passwd"}, "unknown doc"),
            ("run_build", {"action": "rm -rf /"}, "unknown build action"),
            ("write_file", {"path": "outputs/equal_shares/manifest.json",
                            "content": "forbidden"}, "protected project file"),
        ]
        for name, args, expected in cases:
            with self.subTest(name=name):
                self.assertIn(expected, tools.call(name, args, context=context))
        rows = [json.loads(line) for line in self.audit.read_text().splitlines()]
        self.assertEqual([c[0] for c in cases], [row["tool"] for row in rows])
        self.assertTrue(all(row["outcome"] == "refused" for row in rows))

    def test_utf8_chunking_is_lossless_and_bounded(self):
        text = ("Second-by-second motion — café. " * 400).strip()
        chunks = lxmf_agent.chunk_utf8(text, 180)
        self.assertEqual(text, "".join(chunks))
        self.assertTrue(all(len(c.encode("utf8")) <= 180 for c in chunks))

    def test_old_conversation_messages_migrate_to_desktop_source(self):
        conv = store.create("old", model="stub")
        path = store.DIR / f"{conv['id']}.json"
        raw = json.loads(path.read_text())
        raw["messages"] = [{"role": "user", "content": "old", "at": 1}]
        path.write_text(json.dumps(raw))
        self.assertEqual("desktop", store.load(conv["id"])["messages"][0]["source"])

    def test_agent_module_contains_no_transport_import(self):
        source = Path(agent.__file__).read_text(encoding="utf8")
        self.assertNotIn("import RNS", source)
        self.assertNotIn("import LXMF", source)

    def test_outbound_method_uses_ratchet_when_no_direct_link_exists(self):
        class _Router:
            def delivery_link_available(self, _recipient):
                return False
        class _Identity:
            @staticmethod
            def current_ratchet_id(_recipient):
                return b"ratchet"
        class _RNS:
            Identity = _Identity
        class _Message:
            DIRECT = "direct"
            OPPORTUNISTIC = "opportunistic"
        class _LXMF:
            LXMessage = _Message
        self.assertEqual(
            _Message.OPPORTUNISTIC,
            lxmf_agent.choose_delivery_method(_Router(), _RNS, _LXMF, b"x" * 16))

    def test_outbound_method_keeps_direct_link_when_available(self):
        class _Router:
            def delivery_link_available(self, _recipient):
                return True
        class _Identity:
            @staticmethod
            def current_ratchet_id(_recipient):
                return b"ratchet"
        class _RNS:
            Identity = _Identity
        class _Message:
            DIRECT = "direct"
            OPPORTUNISTIC = "opportunistic"
        class _LXMF:
            LXMessage = _Message
        self.assertEqual(
            _Message.DIRECT,
            lxmf_agent.choose_delivery_method(_Router(), _RNS, _LXMF, b"x" * 16))


if __name__ == "__main__":
    unittest.main(verbosity=2)
