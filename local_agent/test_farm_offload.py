"""Tests for farm_offload.py — workstation-side farm routing.

All tests mock subprocess.run and Path.is_file so no farm venv, no broker,
and no Ollama are required. Covers:
  - farm_reachable / should_route: dashboard farm_status.json gate
  - try_summarize_on_farm: success, subprocess failure, timeout, venv missing,
    model-not-installed result passthrough, empty input, unreachable skip
  - try_embed_on_farm: success, subprocess failure, no vectors key, empty input,
    unreachable skip
  - EmbeddingScorer.vectors_for integration: farm used for stale chunks,
    fallback to local when farm returns None, cache hit skips embedding entirely
  - _trim_context integration: prefetch farm summary used, overflow never
    waits on farm, farm "summarized: false" falls back to local
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure local_agent/ is importable.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import farm_offload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    p = MagicMock()
    p.stdout = stdout
    p.returncode = returncode
    p.stderr = stderr
    return p


def _summarize_success_json(summary=None, model="krith/mistral-nemo:IQ4_XS") -> str:
    if summary is None:
        summary = {"goal": "test", "decisions": [], "open_questions": [],
                   "tool_state": [], "hard_constraints": [], "notable_files": []}
    return json.dumps({"summarized": True, "summary": summary, "model": model})


def _embed_success_json() -> str:
    return json.dumps({"vectors": {"doc:0": [0.1, 0.2], "doc:1": [0.3, 0.4]},
                       "model": "nomic-embed-text:latest"})


# ---------------------------------------------------------------------------
# farm_offload.try_summarize_on_farm
# ---------------------------------------------------------------------------

class TestTrySummarizeOnFarm(unittest.TestCase):

    def setUp(self):
        self._reachable = patch.object(farm_offload, "farm_reachable", return_value=True)
        self._reachable.start()

    def tearDown(self):
        self._reachable.stop()

    def _patch_venv(self, present=True):
        return patch.object(farm_offload, "_farm_venv_present", return_value=present)

    def test_returns_dict_on_success(self):
        proc = _make_proc(stdout=_summarize_success_json())
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNotNone(result)
        self.assertTrue(result["summarized"])
        self.assertIn("summary", result)

    def test_returns_none_when_subprocess_exits_nonzero(self):
        proc = _make_proc(returncode=1, stderr="celery not found")
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNone(result)

    def test_returns_none_on_timeout(self):
        with self._patch_venv(), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("python", 30)):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNone(result)

    def test_returns_none_when_farm_venv_missing(self):
        with self._patch_venv(present=False):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNone(result)

    def test_returns_none_when_stdout_not_json(self):
        proc = _make_proc(stdout="not json at all")
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNone(result)

    def test_returns_none_when_helper_reports_error_key(self):
        proc = _make_proc(stdout=json.dumps({"error": "broker down"}))
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNone(result)

    def test_passes_model_not_installed_result_through(self):
        """{"summarized": false} is a valid farm response, not an error."""
        body = {"summarized": False, "model_expected": "some-model", "note": "not installed"}
        proc = _make_proc(stdout=json.dumps(body))
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertIsNotNone(result)
        self.assertFalse(result["summarized"])

    def test_returns_none_for_empty_messages(self):
        with self._patch_venv():
            result = farm_offload.try_summarize_on_farm([])
        self.assertIsNone(result)

    def test_request_contains_correct_task_and_queue(self):
        proc = _make_proc(stdout=_summarize_success_json())
        captured = {}
        def fake_run(cmd, **kwargs):
            captured["input"] = json.loads(kwargs.get("input", "{}"))
            return proc
        with self._patch_venv(), patch("subprocess.run", side_effect=fake_run):
            farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertEqual(captured["input"]["task"],
                         "local_agent.worker_farm.tasks.summarize_conversation")
        self.assertEqual(captured["input"]["queue"], "summarize")

    def test_prefetch_timeout_covers_mac_cold_start(self):
        """Non-blocking summarize must outlast a ~55s Mac cold load.

        A 25s ceiling (the old blocking cutoff) times out the first prefetch
        of a session; overflow then runs local and the farm result is lost.
        """
        proc = _make_proc(stdout=_summarize_success_json())
        captured = {}
        def fake_run(cmd, **kwargs):
            captured["input"] = json.loads(kwargs.get("input", "{}"))
            captured["subprocess_timeout"] = kwargs.get("timeout")
            return proc
        with self._patch_venv(), patch("subprocess.run", side_effect=fake_run):
            farm_offload.try_summarize_on_farm([{"role": "user", "content": "hi"}])
        self.assertGreaterEqual(captured["input"]["timeout_s"], 120)
        self.assertEqual(captured["input"]["timeout_s"],
                         farm_offload.PREFETCH_SUMMARIZE_TIMEOUT_S)
        self.assertGreaterEqual(captured["subprocess_timeout"],
                                farm_offload.PREFETCH_SUMMARIZE_TIMEOUT_S)


# ---------------------------------------------------------------------------
# farm_offload.try_embed_on_farm
# ---------------------------------------------------------------------------

class TestTryEmbedOnFarm(unittest.TestCase):

    def setUp(self):
        self._reachable = patch.object(farm_offload, "farm_reachable", return_value=True)
        self._reachable.start()

    def tearDown(self):
        self._reachable.stop()

    def _patch_venv(self, present=True):
        return patch.object(farm_offload, "_farm_venv_present", return_value=present)

    def test_returns_vectors_dict_on_success(self):
        proc = _make_proc(stdout=_embed_success_json())
        chunks = [{"id": "doc:0", "text": "hello"}, {"id": "doc:1", "text": "world"}]
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_embed_on_farm(chunks)
        self.assertIsNotNone(result)
        self.assertIn("doc:0", result)
        self.assertEqual(result["doc:0"], [0.1, 0.2])

    def test_returns_none_on_subprocess_failure(self):
        proc = _make_proc(returncode=1, stderr="bad")
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_embed_on_farm([{"id": "x", "text": "t"}])
        self.assertIsNone(result)

    def test_returns_none_when_vectors_key_missing(self):
        proc = _make_proc(stdout=json.dumps({"model": "nomic"}))
        with self._patch_venv(), patch("subprocess.run", return_value=proc):
            result = farm_offload.try_embed_on_farm([{"id": "x", "text": "t"}])
        self.assertIsNone(result)

    def test_returns_none_for_empty_chunks(self):
        with self._patch_venv():
            result = farm_offload.try_embed_on_farm([])
        self.assertIsNone(result)

    def test_request_contains_correct_task_and_queue(self):
        proc = _make_proc(stdout=_embed_success_json())
        captured = {}
        def fake_run(cmd, **kwargs):
            captured["input"] = json.loads(kwargs.get("input", "{}"))
            return proc
        chunks = [{"id": "doc:0", "text": "hello"}]
        with self._patch_venv(), patch("subprocess.run", side_effect=fake_run):
            farm_offload.try_embed_on_farm(chunks)
        self.assertEqual(captured["input"]["task"],
                         "local_agent.worker_farm.tasks.embed_chunks")
        self.assertEqual(captured["input"]["queue"], "embed")
        self.assertEqual(captured["input"]["envelope"]["chunks"], chunks)


# ---------------------------------------------------------------------------
# EmbeddingScorer.vectors_for integration (mocking farm_offload)
# ---------------------------------------------------------------------------

class TestEmbeddingScorerFarmRouting(unittest.TestCase):
    """Tests for EmbeddingScorer.vectors_for farm routing.

    All tests mock both _load_embedding_cache and _save_embedding_cache to
    prevent disk I/O and avoid inter-test state pollution via the shared
    knowledge/retrieval_embeddings.json file.
    """

    def setUp(self):
        import retrieval
        self.retrieval = retrieval
        self.scorer = retrieval.EmbeddingScorer()
        self._route = patch("farm_offload.should_route", return_value=True)
        self._route.start()

    def tearDown(self):
        self._route.stop()

    def _empty_cache(self) -> dict:
        return {"model": "nomic-embed-text:latest", "vectors": {}}

    def test_farm_vectors_used_for_stale_chunks(self):
        """When farm returns vectors, _embed is never called."""
        farm_vectors = {"c1": [1.0, 0.0], "c2": [0.0, 1.0]}
        chunks = [{"id": "c1", "text": "alpha"}, {"id": "c2", "text": "beta"}]
        with patch("retrieval._load_embedding_cache", return_value=self._empty_cache()), \
             patch("retrieval._save_embedding_cache"), \
             patch("farm_offload.try_embed_on_farm", return_value=farm_vectors) as mock_farm, \
             patch.object(self.scorer, "_embed", side_effect=AssertionError("should not call")):
            result = self.scorer.vectors_for(chunks)
        mock_farm.assert_called_once()
        self.assertEqual(result["c1"], [1.0, 0.0])
        self.assertEqual(result["c2"], [0.0, 1.0])

    def test_falls_back_to_local_when_farm_returns_none(self):
        """When farm returns None, _embed is called as the local fallback."""
        local_vectors = [[0.5, 0.5], [0.6, 0.4]]
        chunks = [{"id": "c1", "text": "alpha"}, {"id": "c2", "text": "beta"}]
        with patch("retrieval._load_embedding_cache", return_value=self._empty_cache()), \
             patch("retrieval._save_embedding_cache"), \
             patch("farm_offload.try_embed_on_farm", return_value=None), \
             patch.object(self.scorer, "_embed", return_value=local_vectors) as mock_local:
            result = self.scorer.vectors_for(chunks)
        mock_local.assert_called()
        self.assertIn("c1", result)
        self.assertIn("c2", result)

    def test_farm_used_only_for_stale_chunks(self):
        """Cache hits are not re-submitted to the farm."""
        import hashlib
        h = hashlib.sha1("alpha".encode()).hexdigest()
        primed_cache = {
            "model": "nomic-embed-text:latest",
            "vectors": {"c1": {"hash": h, "vector": [9.0, 9.0]}},
        }
        chunks = [{"id": "c1", "text": "alpha"}, {"id": "c2", "text": "beta"}]
        farm_vectors = {"c2": [7.0, 7.0]}
        with patch("retrieval._load_embedding_cache", return_value=primed_cache), \
             patch("retrieval._save_embedding_cache"), \
             patch("farm_offload.try_embed_on_farm", return_value=farm_vectors) as mock_farm, \
             patch.object(self.scorer, "_embed", side_effect=AssertionError("not expected")):
            result = self.scorer.vectors_for(chunks)
        call_chunks = mock_farm.call_args[0][0]
        self.assertEqual([c["id"] for c in call_chunks], ["c2"])
        self.assertEqual(result["c1"], [9.0, 9.0])
        self.assertEqual(result["c2"], [7.0, 7.0])

    def test_farm_partial_miss_falls_back_locally(self):
        """If farm returns vectors for some chunks but not others, local fills the gap."""
        chunks = [{"id": "c1", "text": "alpha"}, {"id": "c2", "text": "beta"}]
        with patch("retrieval._load_embedding_cache", return_value=self._empty_cache()), \
             patch("retrieval._save_embedding_cache"), \
             patch("farm_offload.try_embed_on_farm", return_value={"c1": [1.0]}), \
             patch.object(self.scorer, "_embed", return_value=[[2.0]]) as mock_local:
            result = self.scorer.vectors_for(chunks)
        mock_local.assert_called_once()
        self.assertEqual(result["c1"], [1.0])
        self.assertEqual(result["c2"], [2.0])

    def test_skips_farm_when_should_route_false(self):
        """A down farm_status.json must not submit embed_chunks from search_docs."""
        chunks = [{"id": "c1", "text": "alpha"}]
        with patch("retrieval._load_embedding_cache", return_value=self._empty_cache()), \
             patch("retrieval._save_embedding_cache"), \
             patch("farm_offload.should_route", return_value=False), \
             patch("farm_offload.try_embed_on_farm",
                   side_effect=AssertionError("must not call farm")), \
             patch.object(self.scorer, "_embed", return_value=[[0.1, 0.2]]):
            result = self.scorer.vectors_for(chunks)
        self.assertEqual(result["c1"], [0.1, 0.2])

    def test_caps_farm_embed_payload(self):
        """Live 2026-09-03: search_docs submitted ~1000 stale chunks; the
        30s caller timeout left that job running on mac_worker and blocked
        later embed/summarize. Farm at most FARM_EMBED_MAX_CHUNKS; rest local.
        """
        n = farm_offload.FARM_EMBED_MAX_CHUNKS + 5
        chunks = [{"id": f"c{i}", "text": f"t{i}"} for i in range(n)]
        farm_vecs = {f"c{i}": [float(i)] for i in range(farm_offload.FARM_EMBED_MAX_CHUNKS)}
        local_vecs = [[99.0]] * 5
        captured = []

        def fake_farm(stale):
            captured.append(stale)
            return farm_vecs

        with patch("retrieval._load_embedding_cache", return_value=self._empty_cache()), \
             patch("retrieval._save_embedding_cache"), \
             patch("farm_offload.try_embed_on_farm", side_effect=fake_farm), \
             patch.object(self.scorer, "_embed", return_value=local_vecs):
            result = self.scorer.vectors_for(chunks)
        self.assertEqual(len(captured[0]), farm_offload.FARM_EMBED_MAX_CHUNKS)
        self.assertEqual([c["id"] for c in captured[0]],
                         [f"c{i}" for i in range(farm_offload.FARM_EMBED_MAX_CHUNKS)])
        self.assertTrue(all("text" in c and "id" in c for c in captured[0]))
        self.assertEqual(len(result), n)
        self.assertEqual(result["c0"], [0.0])
        self.assertEqual(result[f"c{farm_offload.FARM_EMBED_MAX_CHUNKS}"], [99.0])


# ---------------------------------------------------------------------------
# _trim_context integration (mocking farm_offload and context_compactor)
# ---------------------------------------------------------------------------

class TestTrimContextFarmRouting(unittest.TestCase):

    def _make_msgs(self, n_older: int = 6) -> list[dict]:
        """Build a message list long enough to trigger compaction."""
        msgs = []
        for i in range(n_older):
            msgs.append({"role": "user", "content": f"user message {i} " + "x" * 200})
            msgs.append({"role": "assistant", "content": f"assistant reply {i} " + "x" * 200})
        msgs.append({"role": "user", "content": "current question"})
        return msgs

    def test_farm_summary_used_when_prefetch_ready(self):
        """A ready prefetch result is used; overflow does not call the farm."""
        import agent as agent_mod
        farm_summary = {"goal": "farm goal", "decisions": [], "open_questions": [],
                        "tool_state": [], "hard_constraints": [], "notable_files": []}
        farm_result = {"summarized": True, "summary": farm_summary,
                       "model": "krith/nemo:IQ4_XS"}
        events = []
        with patch("compaction_prefetch.consume", return_value=farm_result), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not block the turn on farm")), \
             patch("context_compactor.summarize_old_messages",
                   side_effect=AssertionError("should not call local")):
            agent_mod._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=lambda k, v: events.append((k, v)),
            )
        farm_notes = [v for k, v in events if k == "note" and "farm" in v]
        self.assertTrue(farm_notes, "expected a farm-summary note in emit output")

    def test_falls_back_to_local_when_no_prefetch(self):
        """Overflow without a ready prefetch uses local CPU, not a farm wait."""
        import agent as agent_mod
        local_summary = {"goal": "local", "decisions": [], "open_questions": [],
                         "tool_state": [], "hard_constraints": [], "notable_files": []}
        with patch("compaction_prefetch.consume", return_value=None), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not block the turn on farm")), \
             patch("context_compactor.summarize_old_messages",
                   return_value=local_summary) as mock_local:
            agent_mod._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=lambda k, v: None,
            )
        mock_local.assert_called_once()

    def test_falls_back_to_local_when_farm_summarized_false(self):
        """Prefetch returned summarized=false (model not installed) → local."""
        import agent as agent_mod
        not_installed = {"summarized": False, "model_expected": "some-model", "note": "absent"}
        local_summary = {"goal": "local", "decisions": [], "open_questions": [],
                         "tool_state": [], "hard_constraints": [], "notable_files": []}
        with patch("compaction_prefetch.consume", return_value=not_installed), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("must not block the turn on farm")), \
             patch("context_compactor.summarize_old_messages",
                   return_value=local_summary) as mock_local:
            agent_mod._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=lambda k, v: None,
            )
        mock_local.assert_called_once()

    def test_overflow_does_not_import_farm_offload(self):
        """_trim_context overflow path must not submit to Celery."""
        import agent as agent_mod
        local_summary = {"goal": "local", "decisions": [], "open_questions": [],
                         "tool_state": [], "hard_constraints": [], "notable_files": []}
        with patch("compaction_prefetch.consume", return_value=None), \
             patch("farm_offload.try_summarize_on_farm",
                   side_effect=AssertionError("overflow must not call farm")), \
             patch("context_compactor.summarize_old_messages",
                   return_value=local_summary) as mock_local:
            agent_mod._trim_context(
                self._make_msgs(), num_ctx=4096, tool_schemas=[],
                emit=lambda k, v: None,
            )
        mock_local.assert_called_once()


# ---------------------------------------------------------------------------
# farm_reachable / should_route (dashboard farm_status.json gate)
# ---------------------------------------------------------------------------

def _ok_snapshot(**overrides) -> dict:
    body = {
        "broker_reachable": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "latency_ms": 12.3,
        "status": "ok",
        "workers": ["celery@Louises-MBP"],
        "workers_responding": True,
    }
    body.update(overrides)
    return body


class TestFarmReachable(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "farm_status.json"
        self.env = patch.dict(os.environ, {farm_offload.STATUS_PATH_ENV: str(self.path)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self._tmpdir.cleanup()

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_stale_after_matches_dashboard(self):
        from worker_farm.dashboard.collect import STALE_AFTER_S
        self.assertEqual(farm_offload.STATUS_STALE_AFTER_S, STALE_AFTER_S)

    def test_ok_fresh_snapshot_is_reachable(self):
        self._write(_ok_snapshot())
        self.assertTrue(farm_offload.farm_reachable())

    def test_missing_file_is_not_reachable(self):
        self.assertFalse(farm_offload.farm_reachable())

    def test_malformed_json_is_not_reachable(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertFalse(farm_offload.farm_reachable())

    def test_no_workers_is_not_reachable(self):
        self._write(_ok_snapshot(status="no_workers", workers_responding=False,
                                 workers=[], error="broker reachable, no worker"))
        self.assertFalse(farm_offload.farm_reachable())

    def test_unreachable_status_is_not_reachable(self):
        self._write(_ok_snapshot(status="unreachable", broker_reachable=False,
                                 workers_responding=False, workers=[]))
        self.assertFalse(farm_offload.farm_reachable())

    def test_stale_ok_snapshot_is_not_reachable(self):
        old = datetime.now(timezone.utc) - timedelta(seconds=91)
        self._write(_ok_snapshot(checked_at=old.isoformat()))
        self.assertFalse(farm_offload.farm_reachable())

    def test_just_inside_stale_window_is_reachable(self):
        age = farm_offload.STATUS_STALE_AFTER_S - 5
        recent = datetime.now(timezone.utc) - timedelta(seconds=age)
        self._write(_ok_snapshot(checked_at=recent.isoformat()))
        self.assertTrue(farm_offload.farm_reachable())

    def test_missing_checked_at_is_not_reachable(self):
        self._write(_ok_snapshot(checked_at=None))
        self.assertFalse(farm_offload.farm_reachable())

    def test_reachable_matches_dashboard_overall_not_degraded(self):
        """Hot-path reachable == dashboard overall block is not degraded."""
        from worker_farm.dashboard.collect import (
            is_farm_degraded, is_stale, overall_from_snapshot)

        snap = _ok_snapshot()
        self._write(snap)
        overall = overall_from_snapshot({
            **snap,
            "stale": is_stale(snap.get("checked_at")),
            "age_s": 0,
        })
        self.assertEqual(farm_offload.farm_reachable(),
                         not is_farm_degraded(overall))

        self._write(_ok_snapshot(status="no_workers", workers_responding=False,
                                 workers=[]))
        snap = json.loads(self.path.read_text(encoding="utf-8"))
        overall = overall_from_snapshot({
            **snap,
            "stale": is_stale(snap.get("checked_at")),
            "age_s": 0,
        })
        self.assertFalse(farm_offload.farm_reachable())
        self.assertTrue(is_farm_degraded(overall))


class TestShouldRoute(unittest.TestCase):

    def test_summarize_nonblocking_routes_when_reachable(self):
        with patch.object(farm_offload, "farm_reachable", return_value=True):
            self.assertTrue(farm_offload.should_route(
                farm_offload.KIND_SUMMARIZE, blocking=False))

    def test_summarize_blocking_never_routes(self):
        """Cold start ~55s / warm ~18.5s must not stall the operator turn."""
        with patch.object(farm_offload, "farm_reachable", return_value=True):
            self.assertFalse(farm_offload.should_route(
                farm_offload.KIND_SUMMARIZE, blocking=True))

    def test_embed_routes_when_reachable(self):
        with patch.object(farm_offload, "farm_reachable", return_value=True):
            self.assertTrue(farm_offload.should_route(
                farm_offload.KIND_EMBED, blocking=True))

    def test_embed_does_not_route_when_unreachable(self):
        with patch.object(farm_offload, "farm_reachable", return_value=False):
            self.assertFalse(farm_offload.should_route(
                farm_offload.KIND_EMBED, blocking=True))

    def test_unknown_kind_does_not_route(self):
        with patch.object(farm_offload, "farm_reachable", return_value=True):
            self.assertFalse(farm_offload.should_route("judge", blocking=False))

    def test_summarize_nonblocking_does_not_route_when_unreachable(self):
        with patch.object(farm_offload, "farm_reachable", return_value=False):
            self.assertFalse(farm_offload.should_route(
                farm_offload.KIND_SUMMARIZE, blocking=False))


class TestHealthGateSkipsSubprocess(unittest.TestCase):
    """A down farm must not wait 25–40s on Celery before falling back locally."""

    def test_summarize_skips_helper_when_unreachable(self):
        proc = _make_proc(stdout=_summarize_success_json())
        with patch.object(farm_offload, "farm_reachable", return_value=False), \
             patch.object(farm_offload, "_farm_venv_present", return_value=True), \
             patch("subprocess.run", return_value=proc) as mock_run:
            result = farm_offload.try_summarize_on_farm(
                [{"role": "user", "content": "hi"}])
        self.assertIsNone(result)
        mock_run.assert_not_called()

    def test_summarize_blocking_skips_helper_even_when_reachable(self):
        proc = _make_proc(stdout=_summarize_success_json())
        with patch.object(farm_offload, "farm_reachable", return_value=True), \
             patch.object(farm_offload, "_farm_venv_present", return_value=True), \
             patch("subprocess.run", return_value=proc) as mock_run:
            result = farm_offload.try_summarize_on_farm(
                [{"role": "user", "content": "hi"}], blocking=True)
        self.assertIsNone(result)
        mock_run.assert_not_called()

    def test_embed_skips_helper_when_unreachable(self):
        proc = _make_proc(stdout=_embed_success_json())
        with patch.object(farm_offload, "farm_reachable", return_value=False), \
             patch.object(farm_offload, "_farm_venv_present", return_value=True), \
             patch("subprocess.run", return_value=proc) as mock_run:
            result = farm_offload.try_embed_on_farm(
                [{"id": "x", "text": "t"}])
        self.assertIsNone(result)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
