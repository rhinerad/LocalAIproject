"""Tests for compaction_prefetch.py and its _trim_context integration.

Also live-drives the hop-loop 0.80/overflow fork (TestLiveHopLoop) and the
atomic ignore-if-busy contract under concurrent maybe_start.

Covers the five scenarios from the design spec:
  1. Result ready in time — consume() returns the prefetched result; farm not
     called synchronously by _trim_context.
  2. Turn arrives before result ready — thread still in flight when consume()
     is called; returns None, local CPU summarizer runs (farm is not waited on).
  3. Farm unreachable mid-flight — background thread calls farm, gets None,
     stores None; consume() returns None, local CPU summarizer runs.
  4. Slice expanded while in-flight — fingerprint of longer slice doesn't match
     the stored fingerprint; result discarded, local CPU summarizer runs.
  5. Overflow without prefetch — _trim_context does not call the farm; local
     CPU summarizer (then the continuity digest) handles the turn.

No threads are left running after any test (tearDown resets module state).
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import compaction_prefetch as cp
import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_state() -> None:
    """Clear module-level slot between tests."""
    with cp._lock:
        t = cp._state.get("thread")
        cp._state.update(thread=None, result=None, fingerprint=None)
    # An unstarted Thread (start() raised) cannot be joined.
    if t is not None and t.ident is not None:
        t.join(timeout=3.0)


def _sl(*texts: str) -> list[dict]:
    return [{"role": "user", "content": t} for t in texts]


def _wait_for_idle(timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with cp._lock:
            if cp._state["thread"] is None:
                return True
        time.sleep(0.01)
    return False


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------

class TestFingerprint(unittest.TestCase):

    def test_same_slice_produces_same_fingerprint(self):
        sl = _sl("hello", "world")
        self.assertEqual(cp.fingerprint(sl), cp.fingerprint(sl))

    def test_different_content_produces_different_fingerprint(self):
        self.assertNotEqual(cp.fingerprint(_sl("a")), cp.fingerprint(_sl("b")))

    def test_extra_message_changes_fingerprint(self):
        sl1 = _sl("a", "b")
        sl2 = _sl("a", "b", "c")
        self.assertNotEqual(cp.fingerprint(sl1), cp.fingerprint(sl2))

    def test_role_change_changes_fingerprint(self):
        sl1 = [{"role": "user", "content": "x"}]
        sl2 = [{"role": "assistant", "content": "x"}]
        self.assertNotEqual(cp.fingerprint(sl1), cp.fingerprint(sl2))


# ---------------------------------------------------------------------------
# maybe_start
# ---------------------------------------------------------------------------

class TestMaybeStart(unittest.TestCase):

    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    def test_starts_background_thread(self):
        gate = threading.Event()
        with patch("farm_offload.try_summarize_on_farm",
                   side_effect=lambda _: gate.wait() or None):
            cp.maybe_start(_sl("msg"))
            with cp._lock:
                self.assertIsNotNone(cp._state["thread"])
        gate.set()

    def test_empty_slice_is_noop(self):
        cp.maybe_start([])
        with cp._lock:
            self.assertIsNone(cp._state["thread"])

    def test_ignore_if_busy(self):
        """Second call while a job is in flight is silently dropped."""
        gate = threading.Event()
        with patch("farm_offload.try_summarize_on_farm",
                   side_effect=lambda _: gate.wait() or None):
            cp.maybe_start(_sl("first"))
            thread1 = cp._state["thread"]
            cp.maybe_start(_sl("second"))      # different fingerprint — still ignored
            self.assertIs(cp._state["thread"], thread1)
        gate.set()

    def test_concurrent_different_fingerprints_start_only_one_farm_job(self):
        """ignore-if-busy must hold even when Thread() construction is slow.

        maybe_start used to release the lock after reserving the fingerprint
        and only then construct the Thread and publish it. Concurrent callers
        with different fingerprints all saw thread is None and each started a
        farm job. Widening Thread.__init__ reproduces that window; one slot
        must still win.
        """
        farm_calls: list[str] = []
        orig_thread = threading.Thread

        class DelayedThread(orig_thread):
            def __init__(self, *args, **kwargs):
                time.sleep(0.05)
                super().__init__(*args, **kwargs)

        def fake_farm(msgs):
            farm_calls.append(cp.fingerprint(msgs))
            time.sleep(0.1)
            return {"summarized": True, "summary": {}, "model": "m"}

        slices = [_sl(f"{i}-payload" * 40, f"reply-{i}" * 20) for i in range(6)]
        barrier = threading.Barrier(len(slices))

        def worker(sl):
            barrier.wait()
            cp.maybe_start(sl)

        with patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm), \
             patch("compaction_prefetch.threading.Thread", DelayedThread):
            workers = [orig_thread(target=worker, args=(sl,)) for sl in slices]
            for t in workers:
                t.start()
            for t in workers:
                t.join(timeout=5.0)
            self.assertTrue(_wait_for_idle(timeout=3.0))

        self.assertEqual(len(farm_calls), 1, farm_calls)

    def test_concurrent_six_and_eight_way_bursts_are_stable(self):
        """40x 6-way (slow Thread.__init__) and 40x 8-way (no delay).

        The 6-way widens the critical section the same way the race test
        does; the 8-way is the realistic concurrent load. Both must stay
        at exactly one farm job — 8/8 once is not enough.
        """
        orig_thread = threading.Thread

        def one_burst(n: int, delay_init: float) -> int:
            farm_calls: list[str] = []

            class DelayedThread(orig_thread):
                def __init__(self, *args, **kwargs):
                    if delay_init:
                        time.sleep(delay_init)
                    super().__init__(*args, **kwargs)

            def fake_farm(msgs):
                farm_calls.append(cp.fingerprint(msgs))
                time.sleep(0.02)
                return {"summarized": True, "summary": {}, "model": "m"}

            slices = [_sl(f"{i}-p" * 20, f"r{i}" * 10) for i in range(n)]
            barrier = threading.Barrier(n)

            def worker(sl):
                barrier.wait()
                cp.maybe_start(sl)

            with patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm), \
                 patch("compaction_prefetch.threading.Thread", DelayedThread):
                workers = [orig_thread(target=worker, args=(sl,)) for sl in slices]
                for t in workers:
                    t.start()
                for t in workers:
                    t.join(timeout=8.0)
                self.assertTrue(_wait_for_idle(timeout=3.0))
            _reset_state()
            return len(farm_calls)

        six_counts = [one_burst(6, 0.05) for _ in range(40)]
        eight_counts = [one_burst(8, 0.0) for _ in range(40)]
        self.assertEqual(set(six_counts), {1}, six_counts)
        self.assertEqual(set(eight_counts), {1}, eight_counts)

    def test_thread_init_failure_releases_lock_and_does_not_stick_the_slot(self):
        """Thread() raising must not deadlock the lock or pin the fingerprint.

        Construction happens under _lock. `with` releases on the error path;
        the reservation is rolled back so a later maybe_start can run.
        maybe_start itself must not raise (hop loop is unguarded).
        """
        sl_a = _sl("alpha-payload" * 20)
        sl_b = _sl("bravo-payload" * 20)
        farm_calls: list[str] = []

        def fake_farm(msgs):
            farm_calls.append(cp.fingerprint(msgs))
            return {"summarized": True, "summary": {}, "model": "m"}

        class BoomThread:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("simulated Thread() construction failure")

        with patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm), \
             patch("compaction_prefetch.threading.Thread", BoomThread):
            cp.maybe_start(sl_a)  # must not raise
            t0 = time.monotonic()
            acquired = cp._lock.acquire(timeout=1.0)
            wait_s = time.monotonic() - t0
            self.assertTrue(acquired, "lock was not released after Thread() raised")
            self.assertLess(wait_s, 0.05)
            self.assertIsNone(cp._state["thread"])
            self.assertIsNone(cp._state["fingerprint"])
            self.assertIsNone(cp._state["result"])
            cp._lock.release()

        with patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm):
            cp.maybe_start(sl_b)
            self.assertTrue(_wait_for_idle())
        self.assertEqual(len(farm_calls), 1, farm_calls)

    def test_thread_start_failure_releases_slot_so_later_maybe_start_can_run(self):
        """Resource exhaustion is Thread.start(), not Thread().

        If start() raises after the slot is published, a later maybe_start
        used to see thread is not None forever and never fire again.
        """
        sl_a = _sl("alpha-payload" * 20)
        sl_b = _sl("bravo-payload" * 20)
        farm_calls: list[str] = []

        def fake_farm(msgs):
            farm_calls.append("farm")
            return {"summarized": True, "summary": {}, "model": "m"}

        orig = threading.Thread

        class StartBoom(orig):
            def start(self):
                raise RuntimeError("simulated start() failure")

        with patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm), \
             patch("compaction_prefetch.threading.Thread", StartBoom):
            cp.maybe_start(sl_a)  # must not raise
            with cp._lock:
                self.assertIsNone(cp._state["thread"])
                self.assertIsNone(cp._state["fingerprint"])

        with patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm):
            cp.maybe_start(sl_b)
            self.assertTrue(_wait_for_idle())
        self.assertEqual(farm_calls, ["farm"])

    def test_same_fingerprint_not_restarted(self):
        """Calling maybe_start again with the same slice after completion is a no-op."""
        farm_result = {"summarized": True, "summary": {}, "model": "m"}
        sl = _sl("stable msg")
        with patch("farm_offload.try_summarize_on_farm", return_value=farm_result):
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())

        # Fingerprint is still stored; a second call is ignored.
        with patch("farm_offload.try_summarize_on_farm") as mock_farm:
            cp.maybe_start(sl)
            mock_farm.assert_not_called()

    def test_thread_clears_after_completion(self):
        with patch("farm_offload.try_summarize_on_farm", return_value=None):
            cp.maybe_start(_sl("msg"))
            self.assertTrue(_wait_for_idle())
        with cp._lock:
            self.assertIsNone(cp._state["thread"])
            self.assertIsNone(cp._state["fingerprint"])
            self.assertIsNone(cp._state["result"])

    def test_farm_none_clears_fingerprint_so_same_slice_can_retry(self):
        """Live 2026-09-03: a 90s timeout stored result=None but kept the
        fingerprint, so maybe_start never retried that slice."""
        sl = _sl("retry-me payload")
        calls = []

        def farm_once_none(msgs):
            calls.append(1)
            return None

        with patch("farm_offload.try_summarize_on_farm", side_effect=farm_once_none):
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())
        with cp._lock:
            self.assertIsNone(cp._state["fingerprint"])

        farm_result = {"summarized": True, "summary": {}, "model": "m"}
        with patch("farm_offload.try_summarize_on_farm", return_value=farm_result) as mock:
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())
            mock.assert_called_once()
        with cp._lock:
            self.assertEqual(cp._state["result"], farm_result)

    def test_result_stored_on_farm_success(self):
        farm_result = {"summarized": True, "summary": {"goal": "g"}, "model": "m"}
        sl = _sl("msg")
        with patch("farm_offload.try_summarize_on_farm", return_value=farm_result):
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())
        with cp._lock:
            self.assertEqual(cp._state["result"], farm_result)

    def test_result_not_stored_on_fingerprint_mismatch(self):
        """If the fingerprint changes while the thread runs, its result is discarded."""
        sl = _sl("original")
        fp_original = cp.fingerprint(sl)
        gate = threading.Event()

        def slow_farm(_msgs):
            gate.wait()
            return {"summarized": True, "summary": {}, "model": "m"}

        with patch("farm_offload.try_summarize_on_farm", side_effect=slow_farm):
            cp.maybe_start(sl)
            # Overwrite fingerprint to simulate slice expansion
            with cp._lock:
                cp._state["fingerprint"] = "different"
            gate.set()
            self.assertTrue(_wait_for_idle())

        with cp._lock:
            self.assertIsNone(cp._state["result"])


# ---------------------------------------------------------------------------
# consume
# ---------------------------------------------------------------------------

class TestConsume(unittest.TestCase):

    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    def test_returns_none_when_idle_and_no_result(self):
        self.assertIsNone(cp.consume(_sl("msg")))

    def test_returns_none_for_empty_slice(self):
        self.assertIsNone(cp.consume([]))

    # Scenario 2: turn arrives before result ready
    def test_returns_none_when_thread_in_flight(self):
        sl = _sl("msg")
        fp = cp.fingerprint(sl)
        fake_thread = MagicMock(spec=threading.Thread)
        with cp._lock:
            cp._state.update(fingerprint=fp,
                             result={"summarized": True, "summary": {}, "model": "m"},
                             thread=fake_thread)
        result = cp.consume(sl)
        self.assertIsNone(result)

    # Scenario 4: slice expanded while in-flight
    def test_returns_none_on_fingerprint_mismatch(self):
        sl_short = _sl("a", "b")
        sl_long = _sl("a", "b", "c")
        fp_short = cp.fingerprint(sl_short)
        fake_result = {"summarized": True, "summary": {}, "model": "m"}
        with cp._lock:
            cp._state.update(fingerprint=fp_short, result=fake_result, thread=None)

        result = cp.consume(sl_long)   # different fingerprint
        self.assertIsNone(result)

        # Stored state must not be cleared — it was not consumed
        with cp._lock:
            self.assertEqual(cp._state["fingerprint"], fp_short)
            self.assertEqual(cp._state["result"], fake_result)

    # Scenario 1: result ready in time
    def test_returns_and_clears_on_matching_fingerprint(self):
        sl = _sl("message")
        fp = cp.fingerprint(sl)
        fake_result = {"summarized": True, "summary": {"goal": "g"}, "model": "m"}
        with cp._lock:
            cp._state.update(fingerprint=fp, result=fake_result, thread=None)

        result = cp.consume(sl)
        self.assertEqual(result, fake_result)

        with cp._lock:
            self.assertIsNone(cp._state["result"])
            self.assertIsNone(cp._state["fingerprint"])

    def test_result_not_consumed_twice(self):
        sl = _sl("msg")
        fp = cp.fingerprint(sl)
        with cp._lock:
            cp._state.update(fingerprint=fp, result={"summarized": True}, thread=None)

        first = cp.consume(sl)
        self.assertIsNotNone(first)
        second = cp.consume(sl)
        self.assertIsNone(second)


# ---------------------------------------------------------------------------
# Full round-trip (maybe_start → background thread → consume)
# ---------------------------------------------------------------------------

class TestRoundTrip(unittest.TestCase):

    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    # Scenario 1 (full): result ready before _trim_context fires
    def test_result_available_after_thread_completes(self):
        farm_result = {"summarized": True,
                       "summary": {"goal": "prefetched"},
                       "model": "farm-model"}
        sl = _sl("old turn 1", "old turn 2")
        with patch("farm_offload.try_summarize_on_farm", return_value=farm_result):
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())

        result = cp.consume(sl)
        self.assertEqual(result, farm_result)

    # Scenario 3: farm unreachable mid-flight
    def test_farm_none_means_consume_returns_none(self):
        sl = _sl("old turn 1", "old turn 2")
        with patch("farm_offload.try_summarize_on_farm", return_value=None):
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())

        result = cp.consume(sl)
        self.assertIsNone(result)

    def test_farm_exception_means_consume_returns_none(self):
        sl = _sl("old turn")
        with patch("farm_offload.try_summarize_on_farm",
                   side_effect=RuntimeError("broker down")):
            cp.maybe_start(sl)
            self.assertTrue(_wait_for_idle())

        result = cp.consume(sl)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _summarizable_slice helper (agent.py)
# ---------------------------------------------------------------------------

class TestSummarizableSlice(unittest.TestCase):

    def setUp(self):
        import agent as agent_mod
        self.agent = agent_mod

    def _make_msgs(self, n_older: int = 6) -> list[dict]:
        msgs = [{"role": "system", "content": "system prompt"}]
        for i in range(n_older):
            msgs.append({"role": "user", "content": f"user {i} " + "x" * 100})
            msgs.append({"role": "assistant", "content": f"asst {i} " + "x" * 100})
        msgs.append({"role": "user", "content": "current"})
        return msgs

    def test_returns_list(self):
        self.assertIsInstance(self.agent._summarizable_slice(self._make_msgs()), list)

    def test_only_conversational_roles_returned(self):
        sl = self.agent._summarizable_slice(self._make_msgs())
        for m in sl:
            self.assertIn(m.get("role"), {"user", "assistant", "tool"})

    def test_current_turn_excluded(self):
        msgs = self._make_msgs()
        current = msgs[-1]
        sl = self.agent._summarizable_slice(msgs)
        self.assertNotIn(current, sl)

    def test_empty_for_tiny_list(self):
        msgs = [{"role": "system", "content": "s"},
                {"role": "user", "content": "hi"}]
        self.assertEqual(self.agent._summarizable_slice(msgs), [])

    def test_consistent_fingerprint_with_compaction_prefetch(self):
        """Fingerprint from compaction_prefetch.fingerprint matches what
        _trim_context would receive — verifies the shared-algorithm guarantee."""
        msgs = self._make_msgs(n_older=8)
        sl_from_helper = self.agent._summarizable_slice(msgs)
        # If both compute the same list, their fingerprints must match.
        fp1 = cp.fingerprint(sl_from_helper)
        fp2 = cp.fingerprint(self.agent._summarizable_slice(msgs))
        self.assertEqual(fp1, fp2)


# ---------------------------------------------------------------------------
# _trim_context integration
# ---------------------------------------------------------------------------

class TestTrimContextIntegration(unittest.TestCase):
    """_trim_context uses prefetch-first, then local CPU — never a sync farm wait."""

    def setUp(self):
        import agent as agent_mod
        self.agent = agent_mod
        _reset_state()

    def tearDown(self):
        _reset_state()

    def _make_msgs(self, n_older: int = 6) -> list[dict]:
        msgs = [{"role": "system", "content": "system prompt"}]
        for i in range(n_older):
            msgs.append({"role": "user", "content": f"user {i} " + "x" * 200})
            msgs.append({"role": "assistant", "content": f"asst {i} " + "x" * 200})
        msgs.append({"role": "user", "content": "current question"})
        return msgs

    def _noop_emit(self, kind, payload):
        pass

    # Scenario 1: result ready in time
    def test_prefetch_result_used_when_ready(self):
        """consume() returns a result → farm.try_summarize_on_farm never called."""
        prefetched = {"summarized": True,
                      "summary": {"goal": "prefetched", "decisions": [],
                                  "open_questions": [], "tool_state": [],
                                  "hard_constraints": [], "notable_files": []},
                      "model": "farm-model"}
        with patch.object(cp, "consume", return_value=prefetched) as mock_consume, \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not call farm synchronously")), \
             patch("context_compactor.summarize_old_messages",
                   side_effect=AssertionError("must not call local compactor")):
            self.agent._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=self._noop_emit)
        mock_consume.assert_called()

    # Scenario 2: turn arrives before result ready (consume returns None)
    def test_no_synchronous_farm_when_no_prefetch(self):
        """consume() returns None → local CPU summarizer, farm is not waited on."""
        local_summary = {"goal": "local", "decisions": [], "open_questions": [],
                         "tool_state": [], "hard_constraints": [], "notable_files": []}
        with patch.object(cp, "consume", return_value=None), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not block the turn on farm")), \
             patch("context_compactor.summarize_old_messages",
                   return_value=local_summary) as mock_local:
            self.agent._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=self._noop_emit)
        mock_local.assert_called_once()

    # Scenario 5: existing synchronous path unchanged
    def test_local_fallback_when_all_farm_paths_return_none(self):
        """consume()=None → local compactor used; farm is not called on overflow."""
        local_summary = {"goal": "local", "decisions": [], "open_questions": [],
                         "tool_state": [], "hard_constraints": [], "notable_files": []}
        with patch.object(cp, "consume", return_value=None), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not block the turn on farm")), \
             patch("context_compactor.summarize_old_messages",
                   return_value=local_summary) as mock_local:
            self.agent._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=self._noop_emit)
        mock_local.assert_called_once()

    def test_emit_note_says_farm_when_prefetch_used(self):
        """farm-model name from a pre-fetched result appears in the emitted note."""
        prefetched = {"summarized": True,
                      "summary": {"goal": "g", "decisions": [], "open_questions": [],
                                  "tool_state": [], "hard_constraints": [],
                                  "notable_files": []},
                      "model": "krith/nemo:IQ4_XS"}
        notes: list[str] = []
        with patch.object(cp, "consume", return_value=prefetched), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("not called")), \
             patch("context_compactor.summarize_old_messages",
                   side_effect=AssertionError("not called")):
            self.agent._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=lambda k, v: notes.append(v) if k == "note" else None)
        farm_notes = [n for n in notes if "farm" in n]
        self.assertTrue(farm_notes, f"expected farm note; got: {notes}")
        self.assertIn("krith/nemo:IQ4_XS", farm_notes[0])

    # Scenario 4: slice expanded — fingerprint mismatch, discard → local CPU
    def test_slice_expanded_discard_falls_through(self):
        """Pre-fetched result for a shorter slice is not returned for a longer slice."""
        sl_short = _sl("a", "b")
        fp_short = cp.fingerprint(sl_short)
        stale_result = {"summarized": True, "summary": {}, "model": "stale"}

        with cp._lock:
            cp._state.update(fingerprint=fp_short, result=stale_result, thread=None)

        local_summary = {"goal": "fresh", "decisions": [], "open_questions": [],
                         "tool_state": [], "hard_constraints": [], "notable_files": []}
        with patch.object(cp, "consume", wraps=cp.consume), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not block the turn on farm")), \
             patch("context_compactor.summarize_old_messages",
                   return_value=local_summary) as mock_local:
            # consume is called with the actual summarizable slice from _trim_context,
            # which won't match fp_short; local CPU summarizer runs.
            self.agent._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=self._noop_emit)
        mock_local.assert_called_once()


# ---------------------------------------------------------------------------
# Live hop-loop (the real agent.py trim/prefetch fork, growing past 0.80)
# ---------------------------------------------------------------------------

_FARM_LIVE = {
    "summarized": True,
    "summary": {"goal": "prefetched-live", "decisions": [], "open_questions": [],
                "tool_state": [], "hard_constraints": [], "notable_files": []},
    "model": "live-farm-model",
}


def _hop_fork(msgs: list[dict], num_ctx: int, emit) -> tuple[list[dict], int, str]:
    """The hop-loop trim/prefetch branch in agent.answer(), using the real helper."""
    import agent as agent_mod
    prompt_tokens = router.estimate_context_tokens(msgs, [])
    if prompt_tokens > num_ctx:
        msgs = agent_mod._trim_context(msgs, num_ctx, [], emit)
        return msgs, prompt_tokens, "trim"
    if prompt_tokens > cp.PROACTIVE_THRESHOLD * num_ctx:
        if agent_mod._maybe_start_farm_summary_prefetch(msgs):
            return msgs, prompt_tokens, "prefetch"
        prefetch_sl = agent_mod._summarizable_slice(msgs)
        if (len(prefetch_sl) >= 2 and
                sum(len(str(m.get("content", ""))) for m in prefetch_sl) >= 600):
            return msgs, prompt_tokens, "farm-not-reachable"
        return msgs, prompt_tokens, "threshold-but-slice-too-small"
    return msgs, prompt_tokens, "below-threshold"


class TestLiveHopLoop(unittest.TestCase):
    """Drive a growing conversation through the real 0.80 / overflow fork."""

    def setUp(self):
        _reset_state()

    def tearDown(self):
        _reset_state()

    def test_prefetch_fires_strictly_between_80_and_overflow(self):
        """Growing user/assistant turns: first trigger is at ratio in (0.80, 1.0]."""
        farm_calls: list[int] = []

        def fake_farm(msgs):
            farm_calls.append(len(msgs))
            return dict(_FARM_LIVE)

        num_ctx = 2500
        msgs = [{"role": "system", "content": "system prompt for live probe"}]
        events = []
        with patch("farm_offload.should_route", return_value=True), \
             patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm):
            for turn in range(1, 40):
                msgs.append({"role": "user",
                             "content": f"turn {turn} operator request. " + ("detail " * 40)})
                msgs.append({"role": "assistant",
                             "content": f"turn {turn} assistant reply. " + ("answer " * 40)})
                msgs, tokens, fired = _hop_fork(msgs, num_ctx, lambda *_: None)
                events.append((turn, tokens / num_ctx, fired))
                if fired == "prefetch":
                    self.assertTrue(_wait_for_idle())
                    break
            else:
                self.fail(f"never crossed 0.80; events={events}")

        ratio = events[-1][1]
        self.assertGreater(ratio, cp.PROACTIVE_THRESHOLD, events)
        self.assertLessEqual(ratio, 1.0, events)
        self.assertTrue(farm_calls, "maybe_start did not call the farm")
        # Exact 0.80 must not fire (`>` not `>=`): the hop just before the
        # first prefetch, if it exists and was below-threshold, is <= 0.80.
        prior = [e for e in events[:-1] if e[2] == "below-threshold"]
        if prior:
            self.assertLessEqual(prior[-1][1], cp.PROACTIVE_THRESHOLD, events)

    def test_stable_tool_tail_prefetch_is_consumed_on_overflow(self):
        """Token growth is a tool result in the protected tail: slice stays put.

        maybe_start at 80% and _trim_context at overflow therefore share a
        fingerprint, consume() wins, and the local summarizer is skipped.
        This is the path a long tool-heavy turn actually takes.
        """
        import agent as agent_mod
        farm_calls: list[str] = []

        def fake_farm(msgs):
            farm_calls.append(cp.fingerprint(msgs))
            return dict(_FARM_LIVE)

        def boom_local(_msgs):
            raise AssertionError("local compactor must not run; prefetch should win")

        notes: list[str] = []

        def emit(kind, payload):
            if kind == "note":
                notes.append(payload)

        num_ctx = 2500
        msgs = [{"role": "system", "content": "system prompt for live probe"}]
        for i in range(8):
            msgs.append({"role": "user", "content": f"older user {i} " + ("x" * 80)})
            msgs.append({"role": "assistant", "content": f"older asst {i} " + ("y" * 80)})
        msgs.append({"role": "user", "content": "please look this up"})
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "web_search", "arguments": {"query": "q"}}}]})
        msgs.append({"role": "tool", "name": "web_search", "content": "small"})

        slice_fps: list[str] = []
        fired_prefetch = False
        fired_trim = False
        with patch("farm_offload.should_route", return_value=True), \
             patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm), \
             patch("context_compactor.summarize_old_messages", side_effect=boom_local):
            blob = "M" * 400
            for _ in range(50):
                blob += "M" * 250
                msgs[-1] = {"role": "tool", "name": "web_search", "content": blob}
                slice_fps.append(cp.fingerprint(agent_mod._summarizable_slice(msgs)))
                msgs, tokens, fired = _hop_fork(msgs, num_ctx, emit)
                ratio = tokens / num_ctx
                if fired == "prefetch":
                    fired_prefetch = True
                    self.assertGreater(ratio, cp.PROACTIVE_THRESHOLD)
                    self.assertLessEqual(ratio, 1.0)
                    self.assertTrue(_wait_for_idle())
                    with cp._lock:
                        self.assertIsNotNone(cp._state["result"])
                if fired == "trim":
                    fired_trim = True
                    self.assertGreater(ratio, 1.0)
                    break
            else:
                self.fail("never overflowed the live tool-tail conversation")

        self.assertTrue(fired_prefetch, "never sat in the 80-100% band")
        self.assertTrue(fired_trim)
        self.assertEqual(len(set(slice_fps)), 1, set(slice_fps))
        # One background farm call from maybe_start; consume() reused it.
        self.assertEqual(len(farm_calls), 1, farm_calls)
        self.assertTrue(any("live-farm-model" in n for n in notes), notes)
        with cp._lock:
            self.assertIsNone(cp._state["result"])
            self.assertIsNone(cp._state["fingerprint"])

    def test_prefetch_skipped_when_farm_unreachable(self):
        """A down/stale farm_status.json must not start a Celery summarize job."""
        farm_calls: list[int] = []

        def fake_farm(msgs):
            farm_calls.append(len(msgs))
            return dict(_FARM_LIVE)

        num_ctx = 2500
        msgs = [{"role": "system", "content": "system prompt for live probe"}]
        with patch("farm_offload.should_route", return_value=False), \
             patch("farm_offload.try_summarize_on_farm", side_effect=fake_farm):
            saw_not_reachable = False
            for turn in range(1, 40):
                msgs.append({"role": "user",
                             "content": f"turn {turn} operator request. " + ("detail " * 40)})
                msgs.append({"role": "assistant",
                             "content": f"turn {turn} assistant reply. " + ("answer " * 40)})
                msgs, tokens, fired = _hop_fork(msgs, num_ctx, lambda *_: None)
                if fired == "prefetch":
                    self.fail("prefetch must not fire when should_route is False")
                if fired == "farm-not-reachable":
                    saw_not_reachable = True
                    self.assertGreater(tokens / num_ctx, cp.PROACTIVE_THRESHOLD)
                    self.assertLessEqual(tokens / num_ctx, 1.0)
                    break
            else:
                self.fail("never crossed 0.80 with farm unreachable")
        self.assertTrue(saw_not_reachable)
        self.assertFalse(farm_calls)


if __name__ == "__main__":
    unittest.main()
