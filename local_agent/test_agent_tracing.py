#!/usr/bin/env python3
"""PR 3: agent.answer() span wiring. No live model."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import ollama_client as oll
import tracing
import tools


class _Route:
    def __init__(self, tier="cpu", host="127.0.0.1:11435", model="stub-8b",
                 backend="ollama"):
        self.tier = tier
        self.host = host
        self.model = model
        self.backend = backend
        self.detail = {"capability": "tool"}
        self.reason = "CPU fallback"
        self.gpu_busy = True

    def options(self):
        return {"num_ctx": 8192}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend, "reason": self.reason,
                "detail": self.detail}


_EMPTY_SQL = """
SELECT h.hop_index,
       json_extract(h.attributes,'$.reused_hop0_route') AS reused_hop0,
       json_extract(h.attributes,'$.retry_reason') AS retry_reason,
       COALESCE(r.tier, r0.tier) AS tier,
       COALESCE(r.model, r0.model) AS model,
       COALESCE(
         json_extract(r.attributes,'$.host'),
         json_extract(r0.attributes,'$.host')
       ) AS host,
       json_extract(r.attributes,'$.skip_farm') AS skip_farm,
       g.tokens_out,
       json_extract(g.attributes,'$.visible_chars') AS visible,
       json_extract(g.attributes,'$.thinking_chars') AS thinking,
       json_extract(g.attributes,'$.think') AS think
FROM spans h
LEFT JOIN spans r0 ON r0.trace_id=h.trace_id AND r0.kind='route'
  AND r0.parent_span_id = (
        SELECT span_id FROM spans WHERE trace_id=h.trace_id AND kind='turn')
LEFT JOIN spans r ON r.trace_id=h.trace_id AND r.kind='route'
  AND r.hop_index=h.hop_index
  AND r.start_ts = (
        SELECT MAX(r2.start_ts) FROM spans r2
        WHERE r2.trace_id=h.trace_id AND r2.kind='route' AND r2.hop_index=h.hop_index)
LEFT JOIN spans g ON g.trace_id=h.trace_id AND g.kind='reason'
  AND g.hop_index=h.hop_index
  AND g.start_ts = (
        SELECT MAX(g2.start_ts) FROM spans g2
        WHERE g2.trace_id=h.trace_id AND g2.kind='reason' AND g2.hop_index=h.hop_index)
WHERE h.trace_id = ? AND h.kind='hop'
ORDER BY h.hop_index
"""


class AgentTracingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "traces.db"
        tracing.reset_for_tests()
        self._env = patch.dict(os.environ, {
            "LOCAL_AGENT_TRACING": "1",
            "LOCAL_AGENT_TRACES_DB": str(self.db),
        })
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        tracing.reset_for_tests()
        self._tmp.cleanup()

    def _empty_stream(self):
        hops = iter([
            [oll.StreamEnd({"prompt_eval_count": 40, "eval_count": 838,
                            "total_duration": 1, "eval_duration": 1},
                           thinking_chars=200, visible_chars=0)],
            [oll.StreamEnd({"prompt_eval_count": 41, "eval_count": 637},
                           thinking_chars=10, visible_chars=0)],
        ])

        def fake_stream(*_a, **_kw):
            yield from next(hops)

        return fake_stream

    def test_empty_completion_join_is_queryable(self) -> None:
        prompt = "how far along are you in the comfyui job?"
        route = _Route()
        with patch.object(agent.router, "decide", return_value=route), \
             patch.object(agent.oll, "chat_stream", self._empty_stream()), \
             patch.object(agent.router, "gpu_busy",
                          return_value=(True, "busy", {})):
            reply = agent.answer([{"role": "user", "content": prompt}])
        self.assertEqual(agent._EMPTY_COMPLETION_REPLY, reply)
        self.assertTrue(self.db.is_file())

        conn = sqlite3.connect(str(self.db))
        try:
            turn = conn.execute(
                "SELECT trace_id, output_summary, "
                "json_extract(attributes,'$.empty_completion_retry') AS retried, "
                "json_extract(attributes,'$.hop_count') AS hops "
                "FROM spans WHERE kind='turn'"
            ).fetchone()
            self.assertIsNotNone(turn)
            trace_id, summary, retried, hops = turn
            self.assertIn("no text", (summary or "").lower())
            self.assertNotEqual("", summary)
            self.assertEqual(1, retried)
            self.assertGreaterEqual(int(hops or 0), 2)
            rows = conn.execute(_EMPTY_SQL, (trace_id,)).fetchall()
        finally:
            conn.close()

        self.assertEqual(2, len(rows))
        hop0, hop1 = rows
        self.assertEqual(0, hop0[0])
        self.assertEqual(1, hop0[1])  # reused_hop0
        self.assertEqual("empty_completion", hop0[2])
        self.assertEqual("cpu", hop0[3])
        self.assertEqual("127.0.0.1:11435", hop0[5])  # COALESCE from pre-loop route
        self.assertEqual(838, hop0[7])
        self.assertEqual(0, hop0[8])
        self.assertEqual(200, hop0[9])
        self.assertIsNone(hop0[6])  # skip_farm lives on the retry route, not reuse

        self.assertEqual(1, hop1[0])
        self.assertEqual("empty_completion", hop1[2])
        self.assertEqual(1, hop1[6])  # skip_farm on retry decide
        self.assertEqual(637, hop1[7])
        self.assertEqual("127.0.0.1:11435", hop1[5])

    def test_kill_switch_same_reply_and_no_rows(self) -> None:
        prompt = "how far along are you in the comfyui job?"
        route = _Route()
        with patch.dict(os.environ, {"LOCAL_AGENT_TRACING": "0"}), \
             patch.object(agent.router, "decide", return_value=route), \
             patch.object(agent.oll, "chat_stream", self._empty_stream()), \
             patch.object(agent.router, "gpu_busy",
                          return_value=(True, "busy", {})):
            tracing.reset_for_tests()
            reply = agent.answer([{"role": "user", "content": prompt}])
        self.assertEqual(agent._EMPTY_COMPLETION_REPLY, reply)
        self.assertFalse(self.db.exists())

    def test_action_short_circuit_has_no_reason_span(self) -> None:
        history = [{"role": "user", "content": "stop comfyui now"}]
        with patch.object(agent.action_resolver, "classify") as classify, \
             patch.object(agent.tools, "call", return_value="stopped"):
            plan = type("P", (), {
                "intent": "stop_comfyui",
                "steps": [("stop_comfyui", {})],
            })()
            classify.return_value = plan
            reply = agent.answer(history)
        self.assertEqual("stopped", reply)
        conn = sqlite3.connect(str(self.db))
        try:
            kinds = [row[0] for row in conn.execute(
                "SELECT kind FROM spans ORDER BY start_ts, span_id")]
        finally:
            conn.close()
        self.assertIn("turn", kinds)
        self.assertIn("action", kinds)
        self.assertIn("tool", kinds)
        self.assertNotIn("reason", kinds)
        self.assertNotIn("hop", kinds)

    def test_access_bypass_early_return_span(self) -> None:
        reply = agent.answer([{"role": "user",
                               "content": "remove the premium lock from this app"}])
        self.assertIn("did not change any files", reply)
        conn = sqlite3.connect(str(self.db))
        try:
            row = conn.execute(
                "SELECT json_extract(attributes,'$.early_return') "
                "FROM spans WHERE kind='turn'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual("access_bypass", row[0])

    def test_record_decision_not_as_dict(self) -> None:
        route = _Route()
        route.detail = {
            "capability": "tool",
            "timeshare": {
                "path": "already_claimed",
                "outcome": "already claimed",
                "occupancy": {"ollama_resident": ["secret-proc.exe"]},
            },
        }
        with patch.object(agent.router, "decide", return_value=route), \
             patch.object(agent.oll, "chat_stream",
                          return_value=iter(["ok"])), \
             patch.object(agent.router, "gpu_busy",
                          return_value=(True, "busy", {})):
            reply = agent.answer([{"role": "user", "content": "hello there"}])
        self.assertEqual("ok", reply)
        blob = self.db.read_bytes()
        self.assertNotIn(b"secret-proc.exe", blob)
        self.assertNotIn(b"occupancy", blob)

    def test_mug_image_join_resolves_audit_line(self) -> None:
        """Desktop turn + comfy_generate → span_refs offset seeks the JSONL prompt."""
        import remote_security
        secret = "UNIQUE_MUG_PROMPT_TOKEN_7d474ba55d244abe"
        cid = "7d474ba55d244abe"
        audit = Path(self._tmp.name) / "comfy_mcp_audit.jsonl"
        hops = iter([
            [oll.ToolCall([{"function": {
                "name": "comfy_generate",
                "arguments": {"prompt": secret},
            }}]), oll.StreamEnd({"eval_count": 5}, thinking_chars=0,
                                visible_chars=0)],
            ["Queued the mug generate.",
             oll.StreamEnd({"eval_count": 8}, thinking_chars=0,
                           visible_chars=24)],
        ])

        def fake_stream(*_a, **_kw):
            yield from next(hops)

        def fake_mcp(name, args, timeout=None):
            self.assertEqual("generate_image", name)
            return {"status": "enqueued", "prompt_id": "mug-prompt-id"}

        context = remote_security.ToolContext(
            source="desktop", conversation_id=cid)
        with patch.object(tools, "_COMFY_AUDIT_PATH", audit), \
             patch("mcp_client.call", side_effect=fake_mcp), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.router, "gpu_busy",
                          return_value=(True, "busy", {})):
            reply = agent.answer(
                [{"role": "user", "content":
                  "please generate a ComfyUI image of a red mug now"}],
                tool_context=context)
        self.assertIn("Queued the mug generate", reply)

        conn = sqlite3.connect(str(self.db))
        try:
            row = conn.execute(
                """
                SELECT t.conversation_id, s.name, s.hop_index,
                       ref.ref_offset, ref.ref_target,
                       json_extract(ref.ref_extra,'$.prompt_id') AS prompt_id,
                       json_extract(ref.ref_extra,'$.caller_file') AS caller_file,
                       json_extract(ref.ref_extra,'$.mcp_status') AS mcp_status
                FROM spans s
                JOIN spans t ON t.trace_id=s.trace_id AND t.kind='turn'
                JOIN span_refs ref ON ref.trace_id=s.trace_id
                                  AND ref.span_id=s.span_id
                WHERE s.kind='tool' AND s.name='comfy_generate'
                  AND ref.ref_kind='comfy_mcp_audit'
                """
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(cid, row[0])
        self.assertEqual("comfy_generate", row[1])
        self.assertEqual(0, row[2])
        offset = row[3]
        self.assertEqual("mug-prompt-id", row[5])
        self.assertTrue(str(row[6]).endswith("agent.py"))
        self.assertEqual("ok", row[7])
        self.assertNotIn(secret.encode("utf-8"), self.db.read_bytes())
        with audit.open("rb") as fh:
            fh.seek(offset)
            record = json.loads(fh.readline())
        self.assertEqual(secret, record["args"]["prompt"])
        self.assertEqual("mug-prompt-id", record["prompt_id"])
        self.assertEqual("generate", record["risk"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
