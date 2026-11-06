#!/usr/bin/env python3
"""Stdlib tests for subtask_dispatch (bounded coordinator/worker fan-out)."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import subtask_dispatch as sd
import tools


class SubtaskDispatchTests(unittest.TestCase):

    def test_refuses_when_worker_model_not_installed(self):
        with patch.object(sd, "_installed", return_value=False):
            with self.assertRaises(sd.DispatchError) as cm:
                sd.dispatch(["a question"])
        self.assertIn("not installed", str(cm.exception))

    def test_refuses_more_than_max_subtasks(self):
        with patch.object(sd, "_installed", return_value=True):
            with self.assertRaises(sd.DispatchError):
                sd.dispatch(["q"] * (sd.MAX_SUBTASKS + 1))

    def test_refuses_empty_list_and_blank_task(self):
        with patch.object(sd, "_installed", return_value=True):
            with self.assertRaises(sd.DispatchError):
                sd.dispatch([])
            with self.assertRaises(sd.DispatchError):
                sd.dispatch(["fine", "   "])

    def test_workers_run_concurrently_and_preserve_order(self):
        call_times = {}
        lock = threading.Lock()

        def fake_chat(messages, **_kwargs):
            q = messages[-1]["content"]
            start = time.monotonic()
            time.sleep(0.2)
            with lock:
                call_times[q] = (start, time.monotonic())
            return (f"answer to: {q}", [])

        with patch.object(sd, "_installed", return_value=True), \
             patch.object(sd.oll, "chat", side_effect=fake_chat):
            t0 = time.monotonic()
            out = sd.dispatch(["first", "second", "third"])
            elapsed = time.monotonic() - t0

        self.assertEqual(["first", "second", "third"], [r["task"] for r in out])
        self.assertEqual(["answer to: first", "answer to: second", "answer to: third"],
                         [r["answer"] for r in out])
        # Three 0.2s calls sequentially would take >=0.6s; concurrent takes ~0.2s.
        self.assertLess(elapsed, 0.4)
        starts = [s for s, _ in call_times.values()]
        ends = [e for _, e in call_times.values()]
        self.assertGreater(min(ends), max(starts), "workers did not overlap")

    def test_long_task_is_truncated(self):
        with patch.object(sd, "_installed", return_value=True), \
             patch.object(sd.oll, "chat", return_value=("ok", [])):
            out = sd.dispatch(["x" * 900])
        self.assertEqual(sd.MAX_SUBTASK_CHARS, len(out[0]["task"]))

    def test_one_worker_exception_does_not_crash_the_batch(self):
        def flaky_chat(messages, **_kwargs):
            if "boom" in messages[-1]["content"]:
                raise RuntimeError("simulated failure")
            return ("fine", [])

        with patch.object(sd, "_installed", return_value=True), \
             patch.object(sd.oll, "chat", side_effect=flaky_chat):
            out = sd.dispatch(["say boom", "say ok"])
        self.assertTrue(out[0]["answer"].startswith("ERROR:"))
        self.assertEqual("fine", out[1]["answer"])

    def test_workers_never_request_gpu(self):
        seen_options = []

        def capture_chat(messages, **kwargs):
            seen_options.append(kwargs.get("options"))
            return ("ok", [])

        with patch.object(sd, "_installed", return_value=True), \
             patch.object(sd.oll, "chat", side_effect=capture_chat):
            sd.dispatch(["one", "two"])
        for opts in seen_options:
            self.assertEqual(0, opts["num_gpu"])
            self.assertEqual(sd.router.CPU_THREAD_CAP, opts["num_thread"])

    def test_registered_as_a_tool_and_wired_through_tools_call(self):
        self.assertIn("dispatch_subtasks", tools.TOOLS)
        with patch.object(sd, "_installed", return_value=False):
            result = tools.call("dispatch_subtasks", {"tasks": ["hello"]})
        self.assertTrue(result.startswith("ERROR:"))


if __name__ == "__main__":
    unittest.main()
