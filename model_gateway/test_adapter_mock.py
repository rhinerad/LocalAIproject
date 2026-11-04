"""Adapter tests against the real ``anthropic`` SDK over an in-process mock.

No network: ``httpx2.MockTransport`` answers ``POST /v1/messages`` with a
hand-written SSE stream, so the full SDK streaming path (event parsing,
accumulation, ``get_final_message``) is exercised exactly as in production.
Skipped when the SDK is not installed.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_gateway import config as cfgmod, translate  # noqa: E402
from model_gateway.adapters.anthropic_backend import AnthropicBackend  # noqa: E402
from model_gateway.events import CloudUnavailable, Done, TextDelta, ToolCalls  # noqa: E402

try:
    import anthropic
    import httpx2 as httpx
    HAVE_SDK = True
except ImportError:  # pragma: no cover
    HAVE_SDK = False


def sse(events: list[dict]) -> bytes:
    out = []
    for ev in events:
        out.append(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n")
    return "".join(out).encode()


def message_start(model="claude-opus-5-5"):
    return {"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": model,
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 0,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}


def text_stream(text: str, model="claude-opus-5-5"):
    return [
        message_start(model),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        *({"type": "content_block_delta", "index": 0,
           "delta": {"type": "text_delta", "text": chunk}} for chunk in text.split("|")),
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 7}},
        {"type": "message_stop"},
    ]


def tool_stream():
    return [
        message_start(),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Checking."}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1,
         "content_block": {"type": "tool_use", "id": "toolu_abc", "name": "read_file", "input": {}}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "input_json_delta", "partial_json": '{"path": "a.txt"'}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "input_json_delta", "partial_json": ', "mode": "head"}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
         "usage": {"output_tokens": 20}},
        {"type": "message_stop"},
    ]


def refusal_stream():
    return [
        message_start(),
        {"type": "message_delta",
         "delta": {"stop_reason": "refusal", "stop_sequence": None,
                   "stop_details": {"type": "refusal", "category": "cyber", "explanation": "no"}},
         "usage": {"output_tokens": 0}},
        {"type": "message_stop"},
    ]


@unittest.skipUnless(HAVE_SDK, "anthropic SDK not installed")
class AdapterMockTests(unittest.TestCase):
    def setUp(self):
        translate.forget_raw_blocks()
        self.requests: list[dict] = []
        self.cfg = cfgmod.load_config(
            {"MODEL_GATEWAY_CLOUD": "1", "ANTHROPIC_API_KEY": "sk-test",
             "MODEL_GATEWAY_MAX_RETRIES": "0"}, read_env_file=False)

    def backend(self, responder):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content or b"{}")
            self.requests.append({"path": request.url.path, "body": body,
                                  "headers": dict(request.headers)})
            return responder(request, body)
        client = anthropic.Anthropic(
            api_key="sk-test", max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx.MockTransport(handler)))
        b = AnthropicBackend(self.cfg)
        b._client = client
        return b

    @staticmethod
    def ok(events):
        return lambda req, body: httpx.Response(
            200, content=sse(events), headers={"content-type": "text/event-stream"})

    def run_stream(self, backend, **kw):
        kw.setdefault("model", "claude-opus-5-5")
        kw.setdefault("messages", [{"role": "system", "content": "sys"},
                                   {"role": "user", "content": "hello"}])
        return list(backend.stream(**kw))

    def test_text_stream_yields_deltas_and_done(self):
        pieces = self.run_stream(self.backend(self.ok(text_stream("Hel|lo| there"))))
        text = "".join(p.text for p in pieces if isinstance(p, TextDelta))
        self.assertEqual("Hello there", text)
        done = pieces[-1]
        self.assertIsInstance(done, Done)
        self.assertEqual("end_turn", done.stop_reason)
        self.assertEqual(7, done.telemetry["eval_count"])
        self.assertEqual(12, done.telemetry["prompt_eval_count"])
        self.assertEqual("claude-opus-5-5", done.telemetry["gateway"]["model"])
        self.assertFalse(any(isinstance(p, ToolCalls) for p in pieces))

    def test_request_wire_shape(self):
        self.run_stream(self.backend(self.ok(text_stream("x"))),
                        tools=[{"type": "function", "function": {
                            "name": "read_file", "description": "r",
                            "parameters": {"type": "object", "properties": {}}}}],
                        options={"effort": "high", "num_ctx": 16384, "temperature": 0.3,
                                 "num_gpu": 99, "num_predict": 500})
        body = self.requests[0]["body"]
        self.assertEqual("/v1/messages", self.requests[0]["path"])
        self.assertTrue(body["stream"])
        self.assertEqual(500, body["max_tokens"])            # num_predict honoured
        self.assertEqual({"effort": "high"}, body["output_config"])
        self.assertEqual("sys", body["system"][0]["text"])
        self.assertEqual("read_file", body["tools"][0]["name"])
        self.assertIn("input_schema", body["tools"][0])
        for forbidden in ("temperature", "top_p", "options", "keep_alive", "think", "num_ctx"):
            self.assertNotIn(forbidden, body)
        headers = self.requests[0]["headers"]
        auth = headers.get("authorization", "") + headers.get("x-api-key", "")
        self.assertIn("sk-test", auth)  # SDK 2.x sends a bearer header
        self.assertTrue(headers.get("anthropic-version"))

    def test_tool_use_round_trip(self):
        pieces = self.run_stream(self.backend(self.ok(tool_stream())))
        calls = next(p for p in pieces if isinstance(p, ToolCalls)).calls
        self.assertEqual([{"id": "toolu_abc", "function": {
            "name": "read_file", "arguments": {"path": "a.txt", "mode": "head"}}}], calls)
        self.assertEqual("tool_use", pieces[-1].stop_reason)
        # The raw blocks were cached for the next hop's replay.
        self.assertIn("toolu_abc", translate._RAW_BLOCKS)
        # Next hop: agent appends the assistant turn + tool result in Ollama shape.
        self.run_stream(self.backend(self.ok(text_stream("done"))), messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Checking.", "tool_calls": calls},
            {"role": "tool", "name": "read_file", "content": "file body"},
        ])
        body = self.requests[-1]["body"]
        asst = body["messages"][1]
        self.assertEqual("assistant", asst["role"])
        self.assertEqual(["text", "tool_use"], [b["type"] for b in asst["content"]])
        self.assertEqual("toolu_abc", asst["content"][1]["id"])
        result = body["messages"][2]
        self.assertEqual("tool_result", result["content"][0]["type"])
        self.assertEqual("toolu_abc", result["content"][0]["tool_use_id"])

    def test_json_schema_format_maps_to_output_config(self):
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}},
                  "required": ["ok"], "additionalProperties": False}
        self.run_stream(self.backend(self.ok(text_stream('{"ok": true}'))),
                        response_format=schema)
        body = self.requests[0]["body"]
        self.assertEqual({"type": "json_schema", "schema": schema}, body["output_config"]["format"])

    def test_refusal_raises_cloud_unavailable(self):
        with self.assertRaises(CloudUnavailable) as ctx:
            self.run_stream(self.backend(self.ok(refusal_stream())))
        self.assertEqual("refusal", ctx.exception.kind)
        self.assertIn("cyber", ctx.exception.detail)

    def test_connection_error_is_offline(self):
        def boom(request, body):
            raise httpx.ConnectError("connection refused")
        with self.assertRaises(CloudUnavailable) as ctx:
            self.run_stream(self.backend(boom))
        self.assertEqual("offline", ctx.exception.kind)

    def test_status_errors_map_to_kinds(self):
        for status, kind in ((401, "auth"), (429, "rate_limit"), (503, "server"), (404, "bad_request")):
            with self.subTest(status=status):
                resp = lambda req, body, s=status: httpx.Response(
                    s, json={"type": "error", "error": {"type": "x", "message": "m"}})
                with self.assertRaises(CloudUnavailable) as ctx:
                    self.run_stream(self.backend(resp))
                self.assertEqual(kind, ctx.exception.kind)

    def test_thinking_400_retries_once_without_cached_blocks(self):
        translate.remember_raw_blocks(["toolu_old"], [
            {"type": "thinking", "thinking": "", "signature": "stale"},
            {"type": "tool_use", "id": "toolu_old", "name": "a", "input": {}}])
        calls = [0]

        def responder(request, body):
            calls[0] += 1
            if calls[0] == 1:
                return httpx.Response(400, json={"type": "error", "error": {
                    "type": "invalid_request_error",
                    "message": "thinking block signature does not match prefix"}})
            return httpx.Response(200, content=sse(text_stream("ok")),
                                  headers={"content-type": "text/event-stream"})
        pieces = self.run_stream(self.backend(responder), messages=[
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "toolu_old", "function": {"name": "a", "arguments": {}}}]},
            {"role": "tool", "name": "a", "content": "r"},
        ])
        self.assertEqual(2, calls[0])
        first = self.requests[0]["body"]["messages"][1]["content"]
        second = self.requests[1]["body"]["messages"][1]["content"]
        self.assertEqual("thinking", first[0]["type"])
        self.assertEqual(["tool_use"], [b["type"] for b in second])
        self.assertIsInstance(pieces[-1], Done)

    def test_cooperative_stop(self):
        seen = []

        def stop():
            return len(seen) >= 1
        backend = self.backend(self.ok(text_stream("a|b|c|d")))
        for piece in backend.stream(model="m", messages=[{"role": "user", "content": "x"}],
                                    should_stop=stop):
            if isinstance(piece, TextDelta):
                seen.append(piece.text)
        self.assertEqual(["a"], seen)

    # ── non-streaming completion + plan-only path ─────────────────────────

    @staticmethod
    def ok_json(content, stop_reason="end_turn", model="claude-opus-5-5"):
        return lambda req, body: httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": model,
            "content": content, "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 40, "output_tokens": 9}})

    def test_complete_returns_text_and_telemetry(self):
        b = self.backend(self.ok_json([{"type": "text", "text": "1. look\n2. act"}]))
        result = b.complete(model="claude-opus-5-5",
                            messages=[{"role": "user", "content": "plan it"}],
                            options={"max_tokens": 300, "effort": "high"})
        self.assertEqual("1. look\n2. act", result.text)
        self.assertEqual([], result.calls)
        self.assertEqual("end_turn", result.stop_reason)
        self.assertEqual(40, result.telemetry["gateway"]["input_tokens"])
        body = self.requests[0]["body"]
        self.assertNotIn("stream", body)              # non-streaming create
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)
        self.assertEqual(300, body["max_tokens"])

    def test_complete_refusal_and_errors(self):
        with self.assertRaises(CloudUnavailable) as ctx:
            self.backend(self.ok_json([], stop_reason="refusal")).complete(
                model="m", messages=[{"role": "user", "content": "x"}])
        self.assertEqual("refusal", ctx.exception.kind)
        for status, kind in ((401, "auth"), (429, "rate_limit"), (503, "server"), (400, "bad_request")):
            with self.subTest(status=status):
                resp = lambda req, body, s=status: httpx.Response(
                    s, json={"type": "error", "error": {"type": "x", "message": "m"}})
                with self.assertRaises(CloudUnavailable) as ctx:
                    self.backend(resp).complete(model="m", messages=[{"role": "user", "content": "x"}])
                self.assertEqual(kind, ctx.exception.kind)

    def test_request_plan_wire_shape_and_result(self):
        from model_gateway import planning
        b = self.backend(self.ok_json([{"type": "text", "text": "1. read router.py\n2. edit"}]))
        plan = planning.request_plan("Refactor the router end-to-end",
                                     "assistant: earlier reply", ["read_file", "list_dir"],
                                     config=self.cfg, backend=b)
        self.assertEqual("1. read router.py\n2. edit", plan)
        body = self.requests[0]["body"]
        self.assertEqual("claude-opus-5-5", body["model"])
        self.assertEqual(1500, body["max_tokens"])
        self.assertEqual({"effort": "high"}, body["output_config"])
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)
        self.assertNotIn("stream", body)
        system = body["system"][0]["text"]
        self.assertIn("read_file, list_dir", system)
        self.assertIn("Do not perform the task", system)
        user = body["messages"][0]["content"][0]["text"]
        self.assertIn("Operator request:\nRefactor the router end-to-end", user)
        self.assertIn("assistant: earlier reply", user)
        for forbidden in ("temperature", "top_p", "keep_alive", "think"):
            self.assertNotIn(forbidden, body)

    def test_request_plan_returns_none_on_failure_and_records_fallback(self):
        from model_gateway import dispatch, planning

        def boom(request, body):
            raise httpx.ConnectError("connection refused")
        before = dispatch.status_snapshot(self.cfg)["fallbacks"]
        self.assertIsNone(planning.request_plan("x", config=self.cfg, backend=self.backend(boom)))
        snap = dispatch.status_snapshot(self.cfg)
        self.assertEqual(before + 1, snap["fallbacks"])
        self.assertEqual("offline", snap["last_fallback"]["kind"])

    def test_request_plan_ignores_echoed_tool_calls_and_empty_text(self):
        from model_gateway import planning
        b = self.backend(self.ok_json([
            {"type": "text", "text": "1. do it"},
            {"type": "tool_use", "id": "toolu_x", "name": "read_file", "input": {}}]))
        self.assertEqual("1. do it", planning.request_plan("x", config=self.cfg, backend=b))
        empty = self.backend(self.ok_json([]))
        self.assertIsNone(planning.request_plan("x", config=self.cfg, backend=empty))

    def test_request_plan_skips_when_disabled(self):
        from model_gateway import planning
        off = cfgmod.load_config({"ANTHROPIC_API_KEY": "sk"}, read_env_file=False)
        self.assertIsNone(planning.request_plan("x", config=off, backend=self.backend(self.ok_json([]))))
        self.assertEqual([], self.requests)

    def test_custom_base_url_client(self):
        cfg = cfgmod.load_config({"MODEL_GATEWAY_CLOUD": "1",
                                  "MODEL_GATEWAY_BASE_URL": "http://127.0.0.1:11435"},
                                 read_env_file=False)
        b = AnthropicBackend(cfg)
        client = b.client()
        self.assertEqual("http://127.0.0.1:11435", str(client.base_url).rstrip("/"))
        self.assertEqual("local-proxy", client.api_key)  # placeholder, proxies ignore it
        req = b.build_request(model="qwen3:8b", messages=[{"role": "user", "content": "x"}],
                              tools=None, response_format=None, options={"effort": "high"})
        self.assertNotIn("output_config", req)  # effort not sent to a non-Anthropic endpoint
        self.assertNotIn("cache_control", json.dumps(req))


if __name__ == "__main__":
    unittest.main()
