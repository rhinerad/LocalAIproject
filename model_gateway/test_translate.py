"""Offline tests for the Ollama <-> Anthropic translation layer."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_gateway import translate  # noqa: E402

OLLAMA_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a text file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "mode": {"type": "string", "enum": ["head", "all"]}},
            "required": ["path"],
        },
    },
}


class ToolSchemaTests(unittest.TestCase):
    def test_openai_shape_maps_to_input_schema(self):
        out = translate.ollama_tools_to_anthropic([OLLAMA_TOOL])
        self.assertEqual(1, len(out))
        self.assertEqual("read_file", out[0]["name"])
        self.assertEqual("Read a text file", out[0]["description"])
        self.assertEqual(OLLAMA_TOOL["function"]["parameters"], out[0]["input_schema"])
        self.assertNotIn("cache_control", out[0])

    def test_cache_marker_on_last_tool_only(self):
        out = translate.ollama_tools_to_anthropic([OLLAMA_TOOL, OLLAMA_TOOL], cache_last=True)
        self.assertNotIn("cache_control", out[0])
        self.assertEqual({"type": "ephemeral"}, out[1]["cache_control"])

    def test_empty_parameters_become_object_schema(self):
        out = translate.ollama_tools_to_anthropic(
            [{"type": "function", "function": {"name": "ping", "parameters": {}}}])
        self.assertEqual({"type": "object", "properties": {}}, out[0]["input_schema"])


class MessageTests(unittest.TestCase):
    def setUp(self):
        translate.forget_raw_blocks()

    def test_system_lifted_and_simple_turns(self):
        system, msgs = translate.ollama_messages_to_anthropic([
            {"role": "system", "content": "You are terse."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "again"},
        ])
        self.assertEqual("You are terse.", system)
        self.assertEqual(["user", "assistant", "user"], [m["role"] for m in msgs])
        self.assertEqual([{"type": "text", "text": "hi"}], msgs[0]["content"])

    def test_tool_round_mints_ids_and_coalesces_results(self):
        system, msgs = translate.ollama_messages_to_anthropic([
            {"role": "system", "content": "s"},
            {"role": "user", "content": "list two things"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "a", "arguments": {"x": 1}}},
                {"function": {"name": "b", "arguments": '{"y": 2}'}},
            ]},
            {"role": "tool", "name": "a", "content": "A!"},
            {"role": "tool", "name": "b", "content": "B!"},
        ])
        asst = msgs[1]
        self.assertEqual("assistant", asst["role"])
        uses = [b for b in asst["content"] if b["type"] == "tool_use"]
        self.assertEqual(2, len(uses))
        self.assertTrue(all(u["id"].startswith(translate.MINTED_ID_PREFIX) for u in uses))
        self.assertEqual({"y": 2}, uses[1]["input"])  # string arguments parsed
        results = msgs[2]
        self.assertEqual("user", results["role"])
        self.assertEqual(["tool_result", "tool_result"], [b["type"] for b in results["content"]])
        self.assertEqual([u["id"] for u in uses], [b["tool_use_id"] for b in results["content"]])
        self.assertEqual("A!", results["content"][0]["content"])

    def test_provider_ids_are_kept(self):
        _, msgs = translate.ollama_messages_to_anthropic([
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "toolu_real_1", "function": {"name": "a", "arguments": {}}}]},
            {"role": "tool", "name": "a", "content": "ok"},
        ])
        self.assertEqual("toolu_real_1", msgs[1]["content"][0]["id"])
        self.assertEqual("toolu_real_1", msgs[2]["content"][0]["tool_use_id"])

    def test_raw_blocks_replayed_for_pending_turn_only(self):
        raw = [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "Let me look."},
            {"type": "tool_use", "id": "toolu_real_1", "name": "a", "input": {}},
        ]
        translate.remember_raw_blocks(["toolu_real_1"], raw)
        history = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "Let me look.", "tool_calls": [
                {"id": "toolu_real_1", "function": {"name": "a", "arguments": {}}}]},
            {"role": "tool", "name": "a", "content": "ok"},
        ]
        _, msgs = translate.ollama_messages_to_anthropic(history)
        self.assertEqual("thinking", msgs[1]["content"][0]["type"])
        # Once a later assistant tool turn exists, the earlier one is replayed
        # as text + tool_use only (thinking dropped from the leading run).
        history += [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "toolu_real_2", "function": {"name": "b", "arguments": {}}}]},
            {"role": "tool", "name": "b", "content": "ok2"},
        ]
        _, msgs = translate.ollama_messages_to_anthropic(history)
        self.assertEqual(["text", "tool_use"], [b["type"] for b in msgs[1]["content"]])

    def test_stray_tool_message_becomes_text(self):
        _, msgs = translate.ollama_messages_to_anthropic([
            {"role": "user", "content": "go"},
            {"role": "tool", "name": "a", "content": "late result"},
        ])
        self.assertEqual(1, len(msgs))
        self.assertIn("late result", msgs[0]["content"][1]["text"])

    def test_mid_conversation_system_becomes_operator_note(self):
        system, msgs = translate.ollama_messages_to_anthropic([
            {"role": "system", "content": "base"},
            {"role": "user", "content": "q"},
            {"role": "system", "content": "planning assist"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "q2"},
        ])
        self.assertEqual("base", system)
        self.assertEqual("user", msgs[0]["role"])
        self.assertTrue(msgs[0]["content"][1]["text"].startswith("[Operator note]"))

    def test_trailing_assistant_is_rejected(self):
        with self.assertRaises(ValueError):
            translate.ollama_messages_to_anthropic([
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ])

    def test_images_become_image_blocks(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        _, msgs = translate.ollama_messages_to_anthropic([
            {"role": "user", "content": "what is this", "images": [png]},
        ])
        block = msgs[0]["content"][0]
        self.assertEqual("image", block["type"])
        self.assertEqual("image/png", block["source"]["media_type"])


class ResponseTests(unittest.TestCase):
    def test_format_schema_maps_to_output_config(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
        cfg, note = translate.response_format_to_output_config(schema)
        self.assertEqual({"format": {"type": "json_schema", "schema": schema}}, cfg)
        self.assertEqual("", note)
        cfg, note = translate.response_format_to_output_config("json")
        self.assertIsNone(cfg)
        self.assertIn("JSON", note)

    def test_blocks_to_calls_and_text(self):
        blocks = [
            {"type": "text", "text": "I will "},
            {"type": "tool_use", "id": "toolu_1", "name": "a", "input": {"k": "v"}},
            {"type": "text", "text": "now."},
        ]
        self.assertEqual("I will now.", translate.blocks_to_text(blocks))
        calls = translate.blocks_to_ollama_calls(blocks)
        self.assertEqual([{"id": "toolu_1", "function": {"name": "a", "arguments": {"k": "v"}}}], calls)

    def test_usage_to_telemetry_uses_ollama_keys(self):
        usage = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100,
                 "cache_creation_input_tokens": 0}
        tel = translate.usage_to_telemetry(usage, total_ns=10, eval_ns=5,
                                           model="m", stop_reason="end_turn")
        self.assertEqual(5, tel["eval_count"])
        self.assertEqual(110, tel["prompt_eval_count"])
        self.assertEqual(100, tel["gateway"]["cache_read_input_tokens"])


if __name__ == "__main__":
    unittest.main()
