#!/usr/bin/env python3
"""2026-09-25q: a queued media analysis followed by a silent model must end
in an honest progress report, the queued result must be retrievable, and the
prompt-era tool aliases must resolve.

Live reproduction: local_agent/chats/1f0e3e61bdb0487a.json msgs 0-1
(2026-09-25T18:56-19:00Z). analyze_video returned {"queued": true, "job_id":
"9603cd9abe114ed1", ...}; the model then produced blank content on both the
first and the retried hop; the stored reply was the raw
_EMPTY_CONTENT_NONEMPTY_EVAL_REPLY diagnostic. The attached image was never
analysed and the operator was never told which job to ask about.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402
import media_queue as mq  # noqa: E402
import media_tools  # noqa: E402
import ollama_client as oll  # noqa: E402
import remote_security  # noqa: E402
import router  # noqa: E402
import tools  # noqa: E402


class _Route:
    def __init__(self, tier="gpu", host="127.0.0.1:11434", model="stub-model",
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
                "backend": self.backend, "reason": self.reason,
                "gpu_busy": self.gpu_busy, "detail": self.detail}


_VIDEO_PATH = (r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2"
               r"\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\uploads"
               r"\dc4323b0bbee9c02_joss-miss-and-bja-pov-sulbas3d_1080p.mp4")
_IMAGE_PATH = (r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2"
               r"\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\uploads"
               r"\68df742585ca907e_5b0e03cb1ee24a14b5d5e259d8bce550-1200688d4edb9c5f.png")
_IMAGE_NAME = "5b0e03cb1ee24a14b5d5e259d8bce550-1200688d4edb9c5f.png"

# The live msg 0, with the server's attachment blocks exactly as stored.
_LIVE_MSG0 = (
    "I need you to use this video for a visual/action ref for minimax. The character "
    "should be replaced by the image i'll upload of the character. I would like the "
    "entire length of the ref video to be copied but remember the character should be "
    "switched out with the character image ref. \n\n"
    "--- attached video: joss-miss-and-bja-pov-sulbas3d_1080p.mp4 ---\n"
    f"local path: {_VIDEO_PATH}\n"
    "size: 51933648 bytes\n"
    "Call analyze_video or extract_video_actions on this path before writing anything "
    "about its content. You cannot see the video directly. Do not describe, name "
    "characters, or invent shot details without the tool output.\n\n"
    f"--- attached image: {_IMAGE_NAME} ---\n"
    f"local path: {_IMAGE_PATH}\n"
    "size: 992985 bytes\n"
    "Call see_image on this path now. Do not describe the image from memory or "
    "imagination — you cannot see it without the tool.")

# The live analyze_video tool result, verbatim.
_LIVE_QUEUED = json.dumps({
    "queued": True,
    "reason": "exact Qwen2.5-VL Caption V4 runtime is not active",
    "job_id": "9603cd9abe114ed1",
    "free_mb": 2011,
    "message": "Video analysis queued. The background watcher will run it when the GPU is free.",
}, indent=2)

_BLANK_END = dict(telemetry={"eval_count": 275, "prompt_eval_count": 17578,
                             "total_duration": 4_300_000_000,
                             "eval_duration": 4_300_000_000},
                  thinking_chars=0, visible_chars=0, unclosed_think_chars=0,
                  raw_content_chars=0)


def _blank_stream_end() -> oll.StreamEnd:
    return oll.StreamEnd(**_BLANK_END)


class AttachmentParsingTests(unittest.TestCase):
    def test_parses_server_attachment_blocks(self):
        atts = agent._attachments_in_text(_LIVE_MSG0)
        self.assertEqual(2, len(atts))
        self.assertEqual("video", atts[0]["kind"])
        self.assertEqual("joss-miss-and-bja-pov-sulbas3d_1080p.mp4", atts[0]["name"])
        self.assertEqual(_VIDEO_PATH, atts[0]["path"])
        self.assertEqual("image", atts[1]["kind"])
        self.assertEqual(_IMAGE_NAME, atts[1]["name"])
        self.assertEqual(_IMAGE_PATH, atts[1]["path"])

    def test_crlf_and_plain_text_do_not_match(self):
        crlf = _LIVE_MSG0.replace("\n", "\r\n")
        self.assertEqual(2, len(agent._attachments_in_text(crlf)))
        self.assertEqual([], agent._attachments_in_text("no attachments here"))
        self.assertEqual([], agent._attachments_in_text(""))

    def test_queued_tool_result_detection(self):
        info = agent._queued_tool_result("analyze_video", _LIVE_QUEUED)
        self.assertEqual("9603cd9abe114ed1", info["job_id"])
        self.assertIn("Qwen2.5-VL", info["reason"])
        self.assertIsNone(agent._queued_tool_result("analyze_video", "ERROR: nope"))
        self.assertIsNone(agent._queued_tool_result(
            "analyze_video", json.dumps({"available": True, "analysis": "x"})))
        self.assertIsNone(agent._queued_tool_result("x", "not json {"))

    def test_args_paths_and_source_name(self):
        paths = agent._args_paths({"path": _VIDEO_PATH, "question": "q",
                                   "images": [_IMAGE_PATH], "n": 3})
        self.assertIn(agent._norm_path(_VIDEO_PATH), paths)
        self.assertIn(agent._norm_path(_IMAGE_PATH), paths)
        # Pure basename of the stored upload (hash-prefixed); the reply builder
        # maps it back to the operator's attachment name via the message text.
        self.assertEqual("dc4323b0bbee9c02_joss-miss-and-bja-pov-sulbas3d_1080p.mp4",
                         agent._args_source_name({"path": _VIDEO_PATH}))
        self.assertEqual("68df742585ca907e_" + _IMAGE_NAME,
                         agent._args_source_name({"images": [_IMAGE_PATH]}))
        self.assertEqual("", agent._args_source_name({"query": "x"}))


class ToolProgressReplyTests(unittest.TestCase):
    """agent.answer() end to end with a fake model stream and fake tools."""

    def _run(self, streams, tool_results, history=None):
        streams = iter(streams)
        results = iter(tool_results)
        seen_msgs: list[list[dict]] = []
        hops = {"n": 0}

        def fake_stream(messages, **_kwargs):
            hops["n"] += 1
            seen_msgs.append([dict(m) for m in messages])
            yield from next(streams)

        def fake_call(name, args, context=None):
            return next(results)

        events: list[tuple[str, str]] = []
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=fake_call):
            reply = agent.answer(
                history or [{"role": "user", "content": _LIVE_MSG0}],
                lambda k, p: events.append((k, p)))
        return reply, events, hops["n"], seen_msgs

    def test_live_queued_video_then_blank_model_gives_honest_progress_reply(self):
        reply, events, hops, seen = self._run(
            streams=[
                [oll.ToolCall([{"function": {"name": "analyze_video",
                                             "arguments": {"path": _VIDEO_PATH}}}])],
                [_blank_stream_end()],
                [_blank_stream_end()],
            ],
            tool_results=[_LIVE_QUEUED],
        )
        # The retry still happens (hop 1 blank -> retry -> hop 2 blank).
        self.assertEqual(3, hops)
        self.assertTrue(any(k == "note" and agent._EMPTY_COMPLETION_RETRY_NOTE in p
                            for k, p in events))
        # Never the raw diagnostic.
        self.assertNotEqual(agent._EMPTY_CONTENT_NONEMPTY_EVAL_REPLY, reply)
        self.assertNotIn("every streamed message.content", reply)
        self.assertNotIn("nonzero eval_count", reply)
        # The honest content: what is queued, why, which job, what was skipped.
        self.assertIn("Queued, not complete: analyze_video", reply)
        self.assertIn("joss-miss-and-bja-pov-sulbas3d_1080p.mp4", reply)
        self.assertIn("media job 9603cd9abe114ed1", reply)
        self.assertIn("exact Qwen2.5-VL Caption V4 runtime is not active", reply)
        self.assertIn("nothing from that file has been analysed yet", reply)
        self.assertIn(f"Not analysed yet: attached image {_IMAGE_NAME}", reply)
        self.assertIn("Nothing was rendered, generated, or started", reply)
        self.assertIn("ask me to check media job 9603cd9abe114ed1", reply)
        self.assertIn("Ollama reported a real generation but returned blank content", reply)
        self.assertTrue(any(k == "note" and "tool-progress reply" in p
                            and "1 queued job(s)" in p for k, p in events))
        # The hop-1 follow-up told the model the result is queued, by job id.
        followup = seen[1][-1]
        self.assertEqual("user", followup["role"])
        self.assertIn("media job id(s): 9603cd9abe114ed1", followup["content"])
        self.assertIn("Do not wait for it, poll it, or describe the media", followup["content"])
        self.assertIn("media_job_status", followup["content"])

    def test_queued_video_then_image_seen_then_blank_lists_both(self):
        seen_result = json.dumps({"available": True, "tier": "gpu",
                                  "analysis": "A character turnaround sheet."})
        reply, events, hops, seen = self._run(
            streams=[
                [oll.ToolCall([{"function": {"name": "analyze_video",
                                             "arguments": {"path": _VIDEO_PATH}}}])],
                [oll.ToolCall([{"function": {"name": "see_image",
                                             "arguments": {"path": _IMAGE_PATH,
                                                           "question": "describe"}}}])],
                [_blank_stream_end()],
                [_blank_stream_end()],
            ],
            tool_results=[_LIVE_QUEUED, seen_result],
        )
        self.assertEqual(4, hops)
        self.assertIn("Queued, not complete: analyze_video", reply)
        self.assertIn(f"Completed: see_image on {_IMAGE_NAME}", reply)
        self.assertNotIn("Not analysed yet", reply)
        # Hop-2 follow-up (after see_image, a plain result) carries no queued note.
        self.assertNotIn("media job id(s)", seen[2][-1]["content"])

    def test_blank_model_without_tool_activity_keeps_raw_diagnostic(self):
        reply, events, hops, _ = self._run(
            streams=[[_blank_stream_end()], [_blank_stream_end()]],
            tool_results=[],
            history=[{"role": "user", "content": "how far along are you in the comfyui job?"}],
        )
        self.assertEqual(2, hops)
        self.assertEqual(agent._EMPTY_CONTENT_NONEMPTY_EVAL_REPLY, reply)
        self.assertFalse(any(k == "note" and "tool-progress reply" in p for k, p in events))

    def test_tool_error_then_blank_reports_the_failure(self):
        reply, events, hops, _ = self._run(
            streams=[
                [oll.ToolCall([{"function": {"name": "web_search",
                                             "arguments": {"query": "x"}}}])],
                [_blank_stream_end()],
                [_blank_stream_end()],
            ],
            tool_results=["ERROR: search failed"],
            history=[{"role": "user", "content": "search for x"}],
        )
        self.assertIn("Failed: web_search — search failed", reply)
        self.assertNotIn("Queued", reply)
        self.assertNotEqual(agent._EMPTY_CONTENT_NONEMPTY_EVAL_REPLY, reply)

    def test_unclosed_think_after_queued_result_names_that_cause(self):
        end = oll.StreamEnd(
            {"eval_count": 275, "prompt_eval_count": 17578},
            thinking_chars=640, visible_chars=0, unclosed_think_chars=640)
        reply, events, hops, _ = self._run(
            streams=[
                [oll.ToolCall([{"function": {"name": "analyze_video",
                                             "arguments": {"path": _VIDEO_PATH}}}])],
                [end], [end],
            ],
            tool_results=[_LIVE_QUEUED],
        )
        self.assertIn("reasoning without reaching an answer", reply)
        self.assertIn("media job 9603cd9abe114ed1", reply)
        self.assertNotEqual(agent._UNCLOSED_THINK_EMPTY_COMPLETION_REPLY, reply)

    def test_progress_reply_builder_is_deterministic_text(self):
        log = [{"name": "analyze_video", "is_error": False,
                "queued": agent._queued_tool_result("analyze_video", _LIVE_QUEUED),
                "paths": agent._args_paths({"path": _VIDEO_PATH}),
                "source_name": "joss-miss-and-bja-pov-sulbas3d_1080p.mp4", "error": ""}]
        text = agent._tool_progress_empty_reply(_LIVE_MSG0, log, "test cause")
        self.assertTrue(text.startswith("I could not finish this turn"))
        self.assertIn("(test cause)", text)
        self.assertEqual(text, agent._tool_progress_empty_reply(_LIVE_MSG0, log, "test cause"))


class _QueueRootMixin:
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir) / "q"
        self._patcher = patch.object(mq, "QUEUE_ROOT", self._root)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)


class MediaJobStatusToolTests(_QueueRootMixin, unittest.TestCase):
    def test_done_job_returns_full_result(self):
        job = mq.enqueue("analyze_video", {"path": r"C:\x\clip.mp4"}, priority="interactive")
        mq.claim_next()
        mq.complete(job["id"], json.dumps({"source": r"C:\x\clip.mp4", "duration": 3.0,
                                           "frame_by_frame": [{"at": 0.0}]}))
        out = json.loads(tools.call("media_job_status", {"job_id": job["id"]}))
        self.assertEqual("done", out["status"])
        self.assertEqual("analyze_video", out["kind"])
        self.assertEqual(r"C:\x\clip.mp4", out["source"])
        self.assertEqual(3.0, out["result"]["duration"])
        self.assertIn("Complete", out["message"])

    def test_pending_processing_failed_cancelled_shapes(self):
        pending = mq.enqueue("vision", {"images": [r"C:\x\a.png"], "question": "q"})
        out = json.loads(tools.call("media_job_status", {"job_id": pending["id"]}))
        self.assertEqual("pending", out["status"])
        self.assertIn("Nothing has been analysed yet", out["message"])
        self.assertEqual(r"C:\x\a.png", out["source"])

        mq.claim_next()
        out = json.loads(tools.call("media_job_status", {"job_id": pending["id"]}))
        self.assertEqual("processing", out["status"])

        mq.fail(pending["id"], "GPU OOM")
        out = json.loads(tools.call("media_job_status", {"job_id": pending["id"]}))
        self.assertEqual("failed", out["status"])
        self.assertEqual("GPU OOM", out["error"])

        cancelled = mq.enqueue("transcribe", {"path": r"C:\x\b.wav"})
        mq.cancel(cancelled["id"])
        out = json.loads(tools.call("media_job_status", {"job_id": cancelled["id"]}))
        self.assertEqual("cancelled", out["status"])

    def test_unknown_or_missing_args_are_errors(self):
        self.assertTrue(tools.call("media_job_status", {"job_id": "nope"}).startswith("ERROR:"))
        self.assertTrue(tools.call("media_job_status", {}).startswith("ERROR:"))

    def test_lookup_by_path_lists_every_job_and_the_latest_done(self):
        first = mq.enqueue("analyze_video", {"path": r"C:\x\clip.mp4"})
        mq.claim_next()
        mq.complete(first["id"], json.dumps({"duration": 1.0}))
        second = mq.enqueue("analyze_video", {"path": r"C:\x\clip.mp4", "detail": "overview"})
        out = json.loads(tools.call("media_job_status", {"path": r"c:/x/CLIP.mp4"}))
        ids = {j["job_id"] for j in out["jobs"]}
        self.assertEqual({first["id"], second["id"]}, ids)
        self.assertEqual(first["id"], out["latest_done"]["job_id"])
        self.assertEqual(1.0, out["latest_done"]["result"]["duration"])
        self.assertTrue(all("result" not in j for j in out["jobs"]))
        empty = json.loads(tools.call("media_job_status", {"path": r"C:\nothing.mp4"}))
        self.assertEqual([], empty["jobs"])

    def test_registered_read_only_and_phone_visible(self):
        self.assertIn("media_job_status", tools.TOOLS)
        self.assertIn("media_job_status", tools.CONCURRENCY_SAFE_TOOLS)
        self.assertIn("media_job_status", remote_security.REMOTE_DEFAULT_TOOLS)
        names = {s["function"]["name"] for s in tools.schemas()}
        self.assertIn("media_job_status", names)


class ToolAliasTests(unittest.TestCase):
    def test_prompt_era_names_dispatch_to_real_tools(self):
        calls = []

        def fake_see(args):
            calls.append(("see_image", args))
            return "seen"

        def fake_measure(args):
            calls.append(("audio_measure", args))
            return "measured"

        with patch.dict(tools.TOOLS, {"see_image": (fake_see, "d"),
                                      "audio_measure": (fake_measure, "d")}):
            self.assertEqual("seen", tools.call("analyze_image", {"path": "a.png"}))
            self.assertEqual("measured", tools.call("measure_audio", {"path": "a.wav"}))
        self.assertEqual([("see_image", {"path": "a.png"}),
                          ("audio_measure", {"path": "a.wav"})], calls)

    def test_prompt_and_server_name_the_real_tools(self):
        prompt = agent.system_prompt([{"role": "user", "content": "describe the attached image"}])
        self.assertIn("`see_image`", prompt)
        self.assertIn("`audio_measure`", prompt)
        self.assertNotIn("`analyze_image`", prompt)
        self.assertNotIn("`measure_audio`", prompt)
        server_src = (HERE / "server.py").read_text(encoding="utf-8")
        self.assertIn("Call see_image on this path now.", server_src)
        self.assertIn("Call audio_measure on this path", server_src)
        self.assertNotIn("Call analyze_image", server_src)
        self.assertNotIn("Call measure_audio", server_src)


class CompletedResultReuseTests(_QueueRootMixin, unittest.TestCase):
    """Re-attaching an already-analysed, unchanged file returns the stored result."""

    def setUp(self):
        super().setUp()
        self._clip = Path(self._tmpdir) / "clip.mp4"
        self._clip.write_bytes(b"\x00" * 64)
        self._patches = [
            patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=False),
            patch.object(media_tools.router, "gpu_free_mb", return_value=2011),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        super().tearDown()

    def _pending_ids(self):
        return sorted(p.stem for p in (self._root / "pending").glob("*.json"))

    def test_analyze_video_reuses_completed_job_for_unchanged_file(self):
        first = json.loads(media_tools.analyze_video({"path": str(self._clip)}))
        self.assertTrue(first["queued"])
        job_id = first["job_id"]
        job_file = self._root / "pending" / f"{job_id}.json"
        self.assertIn("source_stat", json.loads(job_file.read_text(encoding="utf-8")))
        # watcher runs it
        mq.claim_next(kind="analyze_video")
        mq.complete(job_id, json.dumps({"source": str(self._clip), "duration": 2.0,
                                        "frame_by_frame": [{"at": 0.0, "analysis_status": "ok"}]}))
        again = json.loads(media_tools.analyze_video({"path": str(self._clip)}))
        self.assertNotIn("queued", again)
        self.assertEqual(2.0, again["duration"])
        self.assertEqual(job_id, again["reused_completed_job"]["job_id"])
        self.assertEqual([], self._pending_ids())

    def test_changed_file_or_different_args_queue_a_new_job(self):
        first = json.loads(media_tools.analyze_video({"path": str(self._clip)}))
        mq.claim_next(kind="analyze_video")
        mq.complete(first["job_id"], json.dumps({"duration": 2.0}))
        # different args -> new job
        other = json.loads(media_tools.analyze_video({"path": str(self._clip), "detail": "overview"}))
        self.assertTrue(other["queued"])
        self.assertNotEqual(first["job_id"], other["job_id"])
        # same args, file rewritten -> new job
        time.sleep(0.01)
        self._clip.write_bytes(b"\x00" * 65)
        third = json.loads(media_tools.analyze_video({"path": str(self._clip)}))
        self.assertTrue(third["queued"])
        self.assertNotEqual(first["job_id"], third["job_id"])

    def test_partial_result_is_not_reused(self):
        first = json.loads(media_tools.analyze_video({"path": str(self._clip)}))
        mq.claim_next(kind="analyze_video")
        mq.complete(first["job_id"], json.dumps({
            "duration": 2.0,
            "frame_by_frame": [{"at": 0.0, "analysis_status": "unavailable",
                                "reason": "runtime went away"}]}))
        again = json.loads(media_tools.analyze_video({"path": str(self._clip)}))
        self.assertTrue(again["queued"])
        self.assertNotEqual(first["job_id"], again["job_id"])

    def test_legacy_done_job_without_source_stat_reused_only_if_file_is_older(self):
        args = {"path": str(self._clip)}
        # A done record from before source_stat existed, queued "now".
        (self._root / "done").mkdir(parents=True, exist_ok=True)
        legacy = {"id": "legacy0000000001", "kind": "analyze_video", "args": args,
                  "priority": "interactive",
                  "queued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "done_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "result": json.dumps({"duration": 9.0})}
        (self._root / "done" / "legacy0000000001.json").write_text(
            json.dumps(legacy), encoding="utf-8")
        reused = json.loads(media_tools.analyze_video(args))
        self.assertEqual("legacy0000000001", reused["reused_completed_job"]["job_id"])
        # File touched after the legacy job was queued -> not reused.
        future = time.time() + 120
        os.utime(self._clip, (future, future))
        queued = json.loads(media_tools.analyze_video(args))
        self.assertTrue(queued["queued"])

    def test_vision_and_transcribe_paths_record_source_stat(self):
        img = Path(self._tmpdir) / "a.png"
        img.write_bytes(b"\x89PNG")
        with patch.object(media_tools, "_path", return_value=img):
            first = json.loads(media_tools.see_image({"path": str(img), "question": "q"}))
        self.assertTrue(first["queued"])
        rec = json.loads((self._root / "pending" / f"{first['job_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(str(img), rec["source_stat"]["path"])
        mq.claim_next(kind="vision")
        mq.complete(first["job_id"], json.dumps({"available": True, "analysis": "sheet"}))
        with patch.object(media_tools, "_path", return_value=img):
            again = json.loads(media_tools.see_image({"path": str(img), "question": "q"}))
        self.assertEqual("sheet", again["analysis"])
        self.assertEqual(first["job_id"], again["reused_completed_job"]["job_id"])


if __name__ == "__main__":
    unittest.main()
