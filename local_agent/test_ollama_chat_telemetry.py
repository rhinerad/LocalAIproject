#!/usr/bin/env python3
"""chat() must capture Ollama token/duration fields instead of discarding them."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ollama_client as oll


class OllamaChatTelemetryTests(unittest.TestCase):
    def test_chat_captures_token_duration_fields(self) -> None:
        def fake_post(_path, _payload, **_kwargs):
            return {
                "message": {"content": "ok", "tool_calls": []},
                "eval_count": 12,
                "prompt_eval_count": 34,
                "total_duration": 1_000_000_000,
                "eval_duration": 400_000_000,
                "load_duration": 99,
            }

        with patch.object(oll, "_post", fake_post):
            result = oll.chat([{"role": "user", "content": "hi"}], model="stub")
        text, calls = result
        self.assertEqual("ok", text)
        self.assertEqual([], calls)
        self.assertEqual(
            {
                "eval_count": 12,
                "prompt_eval_count": 34,
                "total_duration": 1_000_000_000,
                "eval_duration": 400_000_000,
            },
            result.telemetry,
        )
        self.assertNotIn("load_duration", result.telemetry)

    def test_chat_telemetry_omits_missing_and_non_numeric_fields(self) -> None:
        def fake_post(_path, _payload, **_kwargs):
            return {
                "message": {"content": "ok"},
                "eval_count": True,
                "prompt_eval_count": "12",
                "total_duration": None,
            }

        with patch.object(oll, "_post", fake_post):
            result = oll.chat([], model="stub")
        self.assertEqual({}, result.telemetry)

    def test_chat_telemetry_helper_copies_only_the_four_fields(self) -> None:
        self.assertEqual(
            {
                "eval_count": 1,
                "prompt_eval_count": 2,
                "total_duration": 3,
                "eval_duration": 4,
            },
            oll.chat_telemetry({
                "eval_count": 1,
                "prompt_eval_count": 2.0,
                "total_duration": 3,
                "eval_duration": 4,
                "prompt_eval_duration": 5,
            }),
        )
        self.assertEqual({}, oll.chat_telemetry(None))
        self.assertEqual({}, oll.chat_telemetry({"message": {"content": "ok"}}))

    def test_chat_stream_yields_stream_end_with_done_chunk_telemetry(self) -> None:
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({
                        "message": {"content": "hi"},
                        "done": True,
                        "eval_count": 12,
                        "prompt_eval_count": 34,
                        "total_duration": 1_000_000_000,
                        "eval_duration": 400_000_000,
                        "load_duration": 99,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            pieces = list(oll.chat_stream(
                [], model="stub", host="127.0.0.1:11435"))
        self.assertEqual(2, len(pieces))
        self.assertEqual("hi", pieces[0])
        self.assertIsInstance(pieces[1], oll.StreamEnd)
        self.assertEqual(
            {
                "eval_count": 12,
                "prompt_eval_count": 34,
                "total_duration": 1_000_000_000,
                "eval_duration": 400_000_000,
            },
            pieces[1].telemetry,
        )
        self.assertNotIn("load_duration", pieces[1].telemetry)
        self.assertEqual(2, pieces[1].visible_chars)
        self.assertEqual(0, pieces[1].thinking_chars)

    def test_chat_stream_yields_stream_end_on_cooperative_stop(self) -> None:
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({
                        "message": {"content": "hel", "thinking": "abc"},
                        "eval_count": 3,
                    }) + "\n").encode(),
                    (json.dumps({
                        "message": {"content": "lo"},
                        "done": True,
                        "eval_count": 12,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            pieces = list(oll.chat_stream(
                [], model="stub", host="127.0.0.1:11435",
                should_stop=lambda: True))
        self.assertEqual(2, len(pieces))
        self.assertEqual("hel", pieces[0])
        self.assertIsInstance(pieces[1], oll.StreamEnd)
        self.assertEqual({"eval_count": 3}, pieces[1].telemetry)
        self.assertEqual(3, pieces[1].visible_chars)
        self.assertEqual(3, pieces[1].thinking_chars)
        self.assertFalse(any(isinstance(p, oll.ToolCall) for p in pieces))

    def test_chat_stream_empty_completion_still_yields_stream_end(self) -> None:
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                thinking = "n" * 50
                return iter([
                    (json.dumps({
                        "message": {"content": "", "thinking": thinking},
                    }) + "\n").encode(),
                    (json.dumps({
                        "message": {"content": ""},
                        "done": True,
                        "eval_count": 80,
                        "prompt_eval_count": 10,
                        "total_duration": 5,
                        "eval_duration": 4,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()), \
             patch.object(oll, "_log_empty_thinking"):
            pieces = list(oll.chat_stream(
                [], model="stub", think=False, host="127.0.0.1:11435"))
        self.assertEqual(1, len(pieces))
        self.assertIsInstance(pieces[0], oll.StreamEnd)
        self.assertEqual(50, pieces[0].thinking_chars)
        self.assertEqual(0, pieces[0].visible_chars)
        self.assertEqual(80, pieces[0].telemetry["eval_count"])

    def test_chat_stream_tool_calls_then_stream_end_not_empty_toolcall(self) -> None:
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({
                        "message": {
                            "content": "",
                            "tool_calls": [{
                                "function": {
                                    "name": "list_dir",
                                    "arguments": {"path": "."},
                                },
                            }],
                        },
                        "done": True,
                        "eval_count": 7,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            pieces = list(oll.chat_stream(
                [], model="stub", host="127.0.0.1:11435"))
        self.assertEqual(2, len(pieces))
        self.assertIsInstance(pieces[0], oll.ToolCall)
        self.assertEqual("list_dir", pieces[0].calls[0]["function"]["name"])
        self.assertIsInstance(pieces[1], oll.StreamEnd)
        self.assertEqual({"eval_count": 7}, pieces[1].telemetry)
        self.assertFalse(any(
            isinstance(p, oll.ToolCall) and p.calls == [] for p in pieces))


    def test_chat_stream_unclosed_think_block_is_not_silently_dropped(self) -> None:
        """A <think> that opens in content and never closes must leave a trace.

        Live 2026-09-05 (conversation e40fa885d6134050, huihui_ai/qwen3-
        abliterated:14b): a large capability=image turn opened <think> in
        message.content, ignored the think=False API flag, and the model
        exhausted its response (eval_count=275, ~4.3s eval) still inside the
        block. The old filter yielded nothing and thinking_chars stayed 0
        (native message.thinking was never populated either), so the turn
        was indistinguishable from a truly silent model: visible_chars=0,
        thinking_chars=0, tool_call_count=0, no diagnostic trail at all.
        """
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({
                        "message": {"content": "<think>reasoning that just "},
                    }) + "\n").encode(),
                    (json.dumps({
                        "message": {"content": "keeps going and never closes"},
                        "done": True,
                        "eval_count": 275,
                        "prompt_eval_count": 17578,
                        "total_duration": 4_300_000_000,
                        "eval_duration": 4_300_000_000,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()), \
             patch.object(oll, "_log_empty_thinking") as log_mock:
            pieces = list(oll.chat_stream(
                [], model="stub", think=False, host="127.0.0.1:11435"))
        self.assertEqual(1, len(pieces))
        end = pieces[0]
        self.assertIsInstance(end, oll.StreamEnd)
        # Nothing visible ever escaped the filter (reasoning stays hidden).
        self.assertEqual(0, end.visible_chars)
        # But it is no longer indistinguishable from a silent model: the
        # dangling hidden text is counted, both as a fold into thinking_chars
        # (so the existing empty-thinking breadcrumb fires) and as its own
        # explicit field for exact diagnosis.
        self.assertGreater(end.thinking_chars, 0)
        self.assertGreater(end.unclosed_think_chars, 0)
        self.assertEqual(end.thinking_chars, end.unclosed_think_chars)
        self.assertEqual(275, end.telemetry["eval_count"])
        log_mock.assert_called_once()
        _, kwargs = log_mock.call_args
        self.assertEqual(end.unclosed_think_chars, kwargs.get("unclosed_think_chars"))

    def test_chat_stream_closed_think_block_unaffected_no_regression(self) -> None:
        """A normal <think>...</think> followed by real prose is unchanged.

        Guards against the unclosed-tracking change leaking into the normal,
        successful case: unclosed_think_chars must stay 0 once a close tag
        was actually seen, and the visible prose must still stream through.
        """
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({
                        "message": {"content": "<think>internal reasoning</think>Hello"},
                    }) + "\n").encode(),
                    (json.dumps({
                        "message": {"content": " world"},
                        "done": True,
                        "eval_count": 20,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()), \
             patch.object(oll, "_log_empty_thinking") as log_mock:
            pieces = list(oll.chat_stream(
                [], model="stub", host="127.0.0.1:11435"))
        text_pieces = [p for p in pieces if isinstance(p, str)]
        end = [p for p in pieces if isinstance(p, oll.StreamEnd)][0]
        self.assertEqual("Hello world", "".join(text_pieces))
        self.assertEqual(0, end.unclosed_think_chars)
        self.assertEqual(0, end.thinking_chars)
        self.assertGreater(end.visible_chars, 0)
        log_mock.assert_not_called()

    def test_chat_stream_unclosed_think_on_cooperative_stop(self) -> None:
        """Stopping mid-turn while still hidden also reports the dangling text."""
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({
                        "message": {"content": "<think>still reasoning"},
                        "eval_count": 5,
                    }) + "\n").encode(),
                    (json.dumps({
                        "message": {"content": " when stopped"},
                        "done": True,
                        "eval_count": 9,
                    }) + "\n").encode(),
                ])

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            pieces = list(oll.chat_stream(
                [], model="stub", host="127.0.0.1:11435",
                should_stop=lambda: True))
        self.assertEqual(1, len(pieces))
        end = pieces[0]
        self.assertIsInstance(end, oll.StreamEnd)
        self.assertEqual(0, end.visible_chars)
        self.assertGreater(end.unclosed_think_chars, 0)
        self.assertEqual(end.thinking_chars, end.unclosed_think_chars)

    def test_visible_text_filter_pure_whitespace_never_vanishes(self) -> None:
        """275 alternating whitespace tokens must not be held forever.

        Live 2026-09-05 (same conversation family as the unclosed-<think>
        bug above, a third distinct shape): `_VisibleTextFilter`'s "prefix"
        state held a leading marker with
        ``self.OPEN.startswith(leading) or self.CLOSE.startswith(leading)``
        where ``leading = self.pending.lstrip()``. When every fed piece is
        whitespace, ``leading`` stays ``""`` forever, and
        ``"<think>".startswith("")`` is trivially True in Python — so the
        condition never resolves, `pending` grows without the defensive cap
        the "hidden" state already has, and nothing is ever released.
        Ollama reported a real ``eval_count=275`` (~4.1s eval) for a turn
        that produced `visible_chars=0`, `thinking_chars=0`, and (after the
        prior fix in this file) `unclosed_think_chars=0` too, because state
        never left "prefix" so even the unclosed-hidden accounting never
        saw it.
        """
        f = oll._VisibleTextFilter()
        released = []
        for i in range(275):
            piece = f.feed("\n" if i % 2 == 0 else " ")
            if piece:
                released.append(piece)
        # Some whitespace must have been released along the way -- it must
        # not all still be sitting unflushed in `pending`.
        self.assertTrue(released)
        self.assertEqual(275, sum(len(p) for p in released))
        # Once it's clear no tag is forming, the filter gives up waiting
        # instead of staying stuck in "prefix" holding an ever-growing
        # buffer.
        self.assertEqual("visible", f.state)
        self.assertEqual(0, len(f.pending))
        self.assertEqual(0, f.unclosed_hidden_chars())

    def test_visible_text_filter_prose_from_first_token_unaffected(self) -> None:
        """No regression: ordinary prose starting immediately streams through."""
        f = oll._VisibleTextFilter()
        out = f.feed("Hello there")
        self.assertEqual("Hello there", out)
        self.assertEqual("visible", f.state)

    def test_visible_text_filter_prose_after_leading_whitespace_unaffected(self) -> None:
        """No regression: a few leading newlines/spaces then real prose."""
        f = oll._VisibleTextFilter()
        held = f.feed("\n") + f.feed(" ") + f.feed("\n")
        self.assertEqual("", held)
        out = f.feed("Hello world")
        self.assertEqual("\n \nHello world", out)
        self.assertEqual("visible", f.state)

    def test_visible_text_filter_think_block_with_leading_whitespace_unaffected(
        self,
    ) -> None:
        """No regression: leading whitespace, then a full <think>...</think>, then prose."""
        f = oll._VisibleTextFilter()
        held = f.feed("\n") + f.feed(" ")
        self.assertEqual("", held)
        # The close tag and the prose that immediately follows it in the same
        # fed chunk are released together, same as before this fix.
        released = f.feed("<think>reasoning</think>Hello")
        self.assertEqual("Hello", released)
        out = f.feed(" world")
        self.assertEqual(" world", out)
        self.assertEqual("visible", f.state)
        self.assertEqual(0, f.unclosed_hidden_chars())

    def test_visible_text_filter_think_from_first_token_still_hidden(self) -> None:
        """No regression: a <think> that opens immediately still hides, and if it
        never closes it's still reported via unclosed_hidden_chars() -- the
        whitespace-flush path must never intercept a genuine tag prefix."""
        f = oll._VisibleTextFilter()
        out = []
        for ch in "<think>still reasoning":
            piece = f.feed(ch)
            if piece:
                out.append(piece)
        self.assertEqual([], out)
        self.assertEqual("hidden", f.state)
        self.assertGreater(f.unclosed_hidden_chars(), 0)

    def test_visible_text_filter_finish_flushes_leftover_prefix(self) -> None:
        """Stream-end must not discard a short prefix hold.

        Mid-stream, ``prefix`` may hold a few chars while deciding whether a
        ``<think>`` marker is forming. If the stream ends there, those chars
        used to vanish with visible=0 / unclosed=0 / no raw signal.
        """
        f = oll._VisibleTextFilter()
        self.assertEqual("", f.feed("<th"))
        self.assertEqual("prefix", f.state)
        self.assertEqual("<th", f.finish())
        self.assertEqual("visible", f.state)
        self.assertEqual("", f.pending)
        self.assertEqual(0, f.unclosed_hidden_chars())

    def test_visible_text_filter_finish_leaves_hidden_alone(self) -> None:
        f = oll._VisibleTextFilter()
        f.feed("<think>secret")
        self.assertEqual("hidden", f.state)
        self.assertEqual("", f.finish())
        self.assertEqual("hidden", f.state)
        self.assertGreater(f.unclosed_hidden_chars(), 0)


    def test_chat_stream_raw_content_chars_counts_before_filter(self) -> None:
        """Empty visible + nonzero eval must still expose raw content length.

        Live 2026-09-06 post-ee: tokens_out/eval_count=275 with visible/
        thinking/unclosed all 0. Without raw_content_chars the harness cannot
        tell filter-swallow from Ollama returning empty ``message.content``.
        """
        nl = chr(10)
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                # Partial tag held in prefix across the whole stream, then done.
                yield (json.dumps({
                    "message": {"content": "<th"},
                    "done": False,
                }) + nl).encode()
                yield (json.dumps({
                    "message": {"content": ""},
                    "done": True,
                    "eval_count": 275,
                    "prompt_eval_count": 100,
                    "eval_duration": 4_000_000_000,
                    "total_duration": 5_000_000_000,
                }) + nl).encode()

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            pieces = list(oll.chat_stream([], model="stub", host="127.0.0.1:11434"))
        # finish() flushes the leftover prefix as visible text
        texts = [p for p in pieces if isinstance(p, str)]
        ends = [p for p in pieces if isinstance(p, oll.StreamEnd)]
        self.assertEqual(["<th"], texts)
        self.assertEqual(1, len(ends))
        end = ends[0]
        self.assertEqual(3, end.raw_content_chars)
        self.assertEqual(3, end.visible_chars)
        self.assertEqual(0, end.unclosed_think_chars)
        self.assertEqual(275, end.telemetry.get("eval_count"))

    def test_chat_stream_empty_content_nonzero_eval_raw_zero(self) -> None:
        """Model generated tokens but every content field was empty/null."""
        nl = chr(10)
        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                for _ in range(3):
                    yield (json.dumps({
                        "message": {"content": ""},
                        "done": False,
                    }) + nl).encode()
                yield (json.dumps({
                    "message": {"content": None},
                    "done": True,
                    "eval_count": 275,
                    "prompt_eval_count": 17582,
                    "eval_duration": 4_000_000_000,
                    "total_duration": 5_000_000_000,
                }) + nl).encode()

        with patch.object(oll.urllib.request, "urlopen", lambda *_a, **_k: _Resp()):
            pieces = list(oll.chat_stream([], model="stub", host="127.0.0.1:11434"))
        texts = [p for p in pieces if isinstance(p, str)]
        ends = [p for p in pieces if isinstance(p, oll.StreamEnd)]
        self.assertEqual([], texts)
        self.assertEqual(1, len(ends))
        end = ends[0]
        self.assertEqual(0, end.raw_content_chars)
        self.assertEqual(0, end.visible_chars)
        self.assertEqual(0, end.thinking_chars)
        self.assertEqual(0, end.unclosed_think_chars)
        self.assertEqual(275, end.telemetry.get("eval_count"))



if __name__ == "__main__":
    unittest.main(verbosity=2)
