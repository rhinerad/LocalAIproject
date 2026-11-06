#!/usr/bin/env python3
"""Regression: a still job whose prompt truncates an operator-pasted prompt.

Live 2026-09-24, chat 1d4a42d3b5834081: render_story_image_batch rendered the
Backrooms pack's scene-1 still from only its first sentence.  The traced args
sha256 (5448b458…, 360 bytes) reproduces exactly from the model's native tool
call, so no code cut the prompt; the model copied the batch tool's own 120-char
``prompt_preview`` (which ended on the first period) back as the prompt.
"""
from __future__ import annotations

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
import file_edit_gate
import gpu_gate
import ollama_client as oll
import tools

SHORT = ("Wide interior view of a modest apartment living room converted into a "
         "makeshift audition space for a sitcom casting tape")
FULL = (SHORT + ". An adult male actor in his late 20s, portraying the character Leo, "
        "stands centered on a taped floor mark. Warm domestic lamp lighting.")
PACK = ("3. SCENE-START FLUX REFERENCE PROMPTS\n\n"
        "Scene Start Image 1: Apartment Audition (Clips C001-C014)\n"
        f"Positive Prompt: {FULL}\n"
        "Negative Prompt: [Universal Artifact Negative Prompt]\n")
LIVE_CHAT = HERE / "chats" / "1d4a42d3b5834081.json"


class _Route:
    tier, host, model, backend = "cpu", "127.0.0.1:11435", "stub-model", "ollama"
    detail, reason, gpu_busy = {}, "", False

    def options(self):
        return {}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend}


class TruncatedOperatorPromptTests(unittest.TestCase):

    def _history(self, text=PACK):
        return [{"role": "user", "content": text + "\nRender scene start image 1 using flux."}]

    def test_first_sentence_of_pack_prompt_is_flagged(self):
        dropped = agent._truncated_operator_prompt(SHORT, self._history())
        self.assertTrue(dropped.startswith("An adult male actor"))

    def test_full_prompt_with_or_without_final_period_passes(self):
        self.assertIsNone(agent._truncated_operator_prompt(FULL, self._history()))
        self.assertIsNone(agent._truncated_operator_prompt(FULL.rstrip("."), self._history()))

    def test_whitespace_differences_do_not_hide_truncation(self):
        spaced = SHORT.replace(" a ", "  a\t", 1)
        self.assertIsNotNone(agent._truncated_operator_prompt(spaced, self._history()))

    def test_rewritten_short_or_assistant_only_prompts_are_not_judged(self):
        history = self._history()
        self.assertIsNone(agent._truncated_operator_prompt(
            "A cramped 1990s living room audition set with an actor on a tape mark", history))
        self.assertIsNone(agent._truncated_operator_prompt("Wide interior view", history))
        self.assertIsNone(agent._truncated_operator_prompt(
            SHORT, [{"role": "assistant", "content": PACK}]))

    def test_prompt_complete_elsewhere_is_accepted(self):
        text = PACK + f"\nAlt still: {SHORT}.\n"
        self.assertIsNone(agent._truncated_operator_prompt(SHORT, self._history(text)))

    def test_refusal_names_the_job_and_covers_single_render(self):
        batch = agent._truncated_render_prompt_refusal(
            "render_story_image_batch",
            {"jobs": [{"story": "s", "prompt": FULL}, {"story": "s", "prompt": SHORT}]},
            self._history())
        self.assertTrue(batch.startswith("ERROR: jobs[1].prompt is a truncated copy"))
        single = agent._truncated_render_prompt_refusal(
            "render_story_image", {"story": "s", "prompt": SHORT}, self._history())
        self.assertTrue(single.startswith("ERROR: prompt is a truncated copy"))
        self.assertIsNone(agent._truncated_render_prompt_refusal(
            "search_docs", {"prompt": SHORT}, self._history()))

    @unittest.skipUnless(LIVE_CHAT.is_file(), "live chat evidence not present")
    def test_live_chat_pack_flags_the_exact_rendered_prompt(self):
        chat = json.loads(LIVE_CHAT.read_text(encoding="utf-8"))
        history = [m for m in chat["messages"] if m.get("role") == "user"]
        dropped = agent._truncated_operator_prompt(SHORT, history)
        self.assertTrue(dropped and dropped.startswith("An adult male actor in his late 20s"))


class AnswerPathTests(unittest.TestCase):

    def setUp(self):
        self._gate_dir = tempfile.TemporaryDirectory()
        self._old_gate_file = gpu_gate.STATE_FILE
        gpu_gate.STATE_FILE = Path(self._gate_dir.name) / "gpu_gate.json"
        self._old_file_edit_gate = file_edit_gate.STATE_FILE
        file_edit_gate.STATE_FILE = Path(self._gate_dir.name) / "file_edit_gate.json"
        os.environ["LOCAL_AGENT_TRACING"] = "0"

    def tearDown(self):
        gpu_gate.STATE_FILE = self._old_gate_file
        file_edit_gate.STATE_FILE = self._old_file_edit_gate
        self._gate_dir.cleanup()

    def test_truncated_batch_job_never_reaches_tools_call(self):
        turns = iter([
            [oll.ToolCall([{"function": {"name": "render_story_image_batch", "arguments": {
                "flux": True, "model_profile": "realpro_flux",
                "jobs": [{"story": "Backrooms Sitcom Audition Prompt Pack", "prompt": SHORT}],
            }}}])],
            ["The prompt was incomplete; nothing was rendered."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        events = []
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="{}") as call:
            agent.answer([{"role": "user", "content":
                           PACK + "\nRender scene start image 1 using flux."}],
                         on_event=lambda kind, data: events.append((kind, data)))

        self.assertFalse([c for c in call.call_args_list
                          if c.args and c.args[0] == "render_story_image_batch"])
        results = [d for k, d in events if k == "tool_result"]
        self.assertTrue(any("jobs[0].prompt is a truncated copy" in r for r in results))


class BatchPreviewTests(unittest.TestCase):

    def test_prompt_preview_is_marked_partial(self):
        with patch.object(tools, "render_story_image",
                          side_effect=tools.ToolError("preflight refused")):
            out = json.loads(tools.render_story_image_batch(
                {"jobs": [{"story": "s", "prompt": FULL}, {"story": "s", "prompt": "short one"}],
                 "stop_on_failure": False}))
        long_f, short_f = out["failures"]
        # The live cut: 120 chars is exactly SHORT, ending on the first period.
        self.assertEqual(SHORT + "…", long_f["prompt_preview"])
        self.assertEqual(len(FULL), long_f["prompt_chars"])
        self.assertEqual("short one", short_f["prompt_preview"])
        self.assertEqual(9, short_f["prompt_chars"])


if __name__ == "__main__":
    unittest.main()
