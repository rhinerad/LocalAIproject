"""Live farm_offload routing verify — real Mac worker, not mocks.

Skips (does not fail) if farm_status.json is not reachable at start.

From the repository root, system Python (farm_offload subprocesses the farm venv):

  python -m unittest local_agent.test_farm_offload_live -v

Scenarios (reported individually):
  A  prefetch: hop loop past 80% num_ctx, real summarize_conversation,
     _trim_context consumes the farm result at overflow
  B  embed: EmbeddingScorer.vectors_for routes to embed_chunks; local _embed
     is not called; wall-clock recorded
  C  failure injection: stop farm_status_daemon, stale farm_status.json >90s,
     both paths local, no hang, no exception, prefetch slot not wedged
  D  dashboard is_farm_degraded agrees with farm_reachable at the same moment
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import agent as agent_mod
import compaction_prefetch as cp
import farm_offload
import retrieval
import router
from worker_farm.dashboard.collect import (
    is_farm_degraded,
    is_stale,
    overall_from_snapshot,
    read_farm_status,
)

TASK_NAME = r"\local-agent-farm-status-daemon"
STATUS_PATH = farm_offload.status_path()
PREFETCH_WAIT_S = 160.0  # helper timeout is 135+15s
EMBED_BUDGET_S = 20.0
FALLBACK_BUDGET_S = 2.0
HELPER_TASK_SUMMARIZE = "local_agent.worker_farm.tasks.summarize_conversation"
HELPER_TASK_EMBED = "local_agent.worker_farm.tasks.embed_chunks"


def _reset_prefetch() -> None:
    with cp._lock:
        t = cp._state.get("thread")
        cp._state.update(thread=None, result=None, fingerprint=None)
    if t is not None and t.ident is not None:
        t.join(timeout=3.0)


def _wait_prefetch_idle(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with cp._lock:
            if cp._state["thread"] is None:
                return True
        time.sleep(0.05)
    return False


def _dashboard_degraded(path: Path | None = None) -> bool:
    section = read_farm_status(path)
    overall = overall_from_snapshot(section)
    return is_farm_degraded(overall)


def _reachable_matches_dashboard(path: Path | None = None) -> tuple[bool, bool, bool]:
    reachable = farm_offload.farm_reachable(path)
    degraded = _dashboard_degraded(path)
    return reachable, degraded, reachable == (not degraded)


def _ps_scheduled_task(action: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            f"{action}-ScheduledTask -TaskName 'local-agent-farm-status-daemon'",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _task_state() -> str:
    proc = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "(Get-ScheduledTask -TaskName 'local-agent-farm-status-daemon').State",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return (proc.stdout or "").strip()


def _write_stale_snapshot(src: Path) -> dict:
    data = json.loads(src.read_text(encoding="utf-8"))
    data["checked_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=91)
    ).isoformat()
    src.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _stable_tool_tail_msgs(n_older: int = 8) -> list[dict]:
    msgs = [{"role": "system", "content": "system prompt for live farm-offload probe"}]
    for i in range(n_older):
        msgs.append({"role": "user", "content": f"older user {i} " + ("x" * 80)})
        msgs.append({"role": "assistant", "content": f"older asst {i} " + ("y" * 80)})
    msgs.append({"role": "user", "content": "please look this up"})
    msgs.append({"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "web_search", "arguments": {"query": "q"}}}]})
    msgs.append({"role": "tool", "name": "web_search", "content": "small"})
    return msgs


class _HelperSpy:
    """Record real _run_helper calls; do not stub the farm."""

    def __init__(self):
        self.calls: list[dict] = []
        self._orig = farm_offload._run_helper

    def __enter__(self):
        spy = self

        def wrapped(request, timeout_s):
            rec = {
                "task": request.get("task"),
                "queue": request.get("queue"),
                "timeout_s": timeout_s,
                "t0": time.monotonic(),
                "done": False,
            }
            spy.calls.append(rec)
            result = spy._orig(request, timeout_s)
            rec["elapsed_s"] = round(time.monotonic() - rec["t0"], 3)
            rec["none"] = result is None
            rec["done"] = True
            if isinstance(result, dict):
                rec["summarized"] = result.get("summarized")
                rec["model"] = result.get("model")
                rec["vector_ids"] = list((result.get("vectors") or {}).keys())
                rec["error"] = result.get("error")
            return result

        self._patch = patch.object(farm_offload, "_run_helper", side_effect=wrapped)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()

    def tasks(self) -> list[str]:
        return [c["task"] for c in self.calls]


class LiveFarmOffloadRoutingTests(unittest.TestCase):
    """Slow / live. Skip the class if the snapshot is not healthy at start."""

    report: dict

    @classmethod
    def setUpClass(cls):
        cls.report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "farm_reachable": farm_offload.farm_reachable(),
            "status_path": str(STATUS_PATH),
            "snapshot": farm_offload.read_status_snapshot(),
            "scenarios": {},
        }
        print(
            "LIVE snapshot: reachable="
            + str(cls.report["farm_reachable"])
            + " status="
            + str((cls.report["snapshot"] or {}).get("status"))
            + " workers="
            + str((cls.report["snapshot"] or {}).get("workers")),
            flush=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.report["finished_at"] = datetime.now(timezone.utc).isoformat()
        print("LIVE REPORT " + json.dumps(cls.report, default=str), flush=True)

    def setUp(self):
        if not farm_offload.farm_reachable():
            self.skipTest("farm_status.json not reachable (status!=ok or stale)")
        _reset_prefetch()

    def tearDown(self):
        _reset_prefetch()

    def test_01_healthy_consistency(self):
        reachable, degraded, match = _reachable_matches_dashboard()
        self.report["scenarios"]["D_healthy_consistency"] = {
            "pass": match and reachable and not degraded,
            "reachable": reachable,
            "degraded": degraded,
        }
        self.assertTrue(match, "healthy: farm_reachable != not is_farm_degraded")
        self.assertTrue(reachable)
        self.assertFalse(degraded)

    def test_02_embed(self):
        # ------------------------------------------------------------------
        # B — embed blocking path, local _embed must not run
        # ------------------------------------------------------------------
        chunk_id = f"live-farm-offload:{time.time_ns()}"
        chunks = [{"id": chunk_id, "text": "live farm embed probe " + chunk_id}]
        embed_local: list[int] = []

        def boom_embed(texts):
            embed_local.append(len(texts))
            raise AssertionError("local _embed must not run; farm should supply vectors")

        tmp = tempfile.TemporaryDirectory()
        old_file = retrieval.EMBEDDING_CACHE_FILE
        old_cache = retrieval._EMBED_CACHE
        retrieval.EMBEDDING_CACHE_FILE = Path(tmp.name) / "retrieval_embeddings.json"
        retrieval._EMBED_CACHE = None
        helper_b = _HelperSpy()
        embed_elapsed = None
        embed_result = None
        embed_err = None
        try:
            scorer = retrieval.EmbeddingScorer()
            with helper_b, patch.object(scorer, "_embed", side_effect=boom_embed):
                t0 = time.monotonic()
                try:
                    embed_result = scorer.vectors_for(chunks)
                except Exception as exc:
                    embed_err = f"{type(exc).__name__}: {exc}"
                embed_elapsed = round(time.monotonic() - t0, 3)
        finally:
            retrieval.EMBEDDING_CACHE_FILE = old_file
            retrieval._EMBED_CACHE = old_cache
            tmp.cleanup()

        embed_calls = [c for c in helper_b.calls if c["task"] == HELPER_TASK_EMBED]
        b_ok = (
            embed_err is None
            and embed_result is not None
            and chunk_id in (embed_result or {})
            and bool(embed_calls)
            and not embed_calls[0]["none"]
            and not embed_local
            and embed_elapsed is not None
            and embed_elapsed < EMBED_BUDGET_S
        )
        self.report["scenarios"]["B_embed"] = {
            "pass": b_ok,
            "elapsed_s": embed_elapsed,
            "helper_calls": embed_calls,
            "local_embed_calls": embed_local,
            "vector_dim": len((embed_result or {}).get(chunk_id) or []),
            "error": embed_err,
            "budget_s": EMBED_BUDGET_S,
        }
        self.assertIsNone(embed_err, embed_err)
        self.assertTrue(embed_calls, "no real embed helper call — silent local fallback")
        self.assertFalse(embed_calls[0]["none"], f"embed helper returned None: {embed_calls}")
        self.assertFalse(embed_local, "local _embed ran; farm did not supply vectors")
        self.assertIn(chunk_id, embed_result or {})
        self.assertLess(embed_elapsed, EMBED_BUDGET_S)

    def test_03_prefetch(self):
        num_ctx = 2500
        msgs = _stable_tool_tail_msgs()
        local_calls: list[int] = []
        notes: list[str] = []
        fired_prefetch = False
        fired_trim = False
        prefetch_wait_s = None
        local_ran = False

        def local_record(_msgs):
            nonlocal local_ran
            local_ran = True
            local_calls.append(1)
            return None

        helper = _HelperSpy()
        with helper, patch("context_compactor.summarize_old_messages",
                           side_effect=local_record):
            blob = "M" * 400
            for _ in range(60):
                blob += "M" * 250
                msgs[-1] = {"role": "tool", "name": "web_search", "content": blob}
                tokens = router.estimate_context_tokens(msgs, [])
                if tokens > num_ctx:
                    if not fired_prefetch:
                        break
                    wait_t0 = time.monotonic()
                    idle = _wait_prefetch_idle(PREFETCH_WAIT_S)
                    prefetch_wait_s = round(time.monotonic() - wait_t0, 3)
                    if idle:
                        agent_mod._trim_context(
                            msgs, num_ctx, [],
                            emit=lambda k, v: notes.append(v) if k == "note" else None,
                        )
                        fired_trim = True
                    break
                if (tokens > cp.PROACTIVE_THRESHOLD * num_ctx
                        and not fired_prefetch):
                    if agent_mod._maybe_start_farm_summary_prefetch(msgs):
                        fired_prefetch = True
                        self.report["scenarios"]["A_prefetch_fired"] = {
                            "pass": True,
                            "ratio": round(tokens / num_ctx, 3),
                            "tokens": tokens,
                        }

        summarize_calls = [c for c in helper.calls
                           if c["task"] == HELPER_TASK_SUMMARIZE]
        farm_note = any("farm" in n for n in notes)
        a_ok = (
            fired_prefetch
            and fired_trim
            and bool(summarize_calls)
            and summarize_calls[0].get("summarized") is True
            and farm_note
            and not local_ran
        )
        self.report["scenarios"]["A_prefetch"] = {
            "pass": a_ok,
            "fired_prefetch": fired_prefetch,
            "fired_trim": fired_trim,
            "helper_calls": summarize_calls,
            "notes": notes,
            "local_calls": len(local_calls),
            "farm_note": farm_note,
            "prefetch_wait_s": prefetch_wait_s,
        }
        self.assertTrue(fired_prefetch, "prefetch never fired past 80%")
        self.assertTrue(fired_trim, f"overflow never consumed; helper={summarize_calls}")
        self.assertTrue(summarize_calls, "no real summarize helper call")
        self.assertTrue(
            summarize_calls[0].get("summarized") is True,
            f"farm summarize did not complete: {summarize_calls[0]}",
        )
        self.assertTrue(farm_note, f"expected farm note, got {notes}")
        self.assertFalse(local_ran, "local summarizer ran; farm result not consumed")

    def test_04_failure_injection(self):
        scenarios = self.report["scenarios"]
        backup = STATUS_PATH.read_text(encoding="utf-8") if STATUS_PATH.is_file() else None
        restore_err = None
        try:
            rc, out = _ps_scheduled_task("Stop")
            daemon_stopped = rc == 0
            time.sleep(1.0)
            _write_stale_snapshot(STATUS_PATH)

            reachable, degraded, match = _reachable_matches_dashboard()
            scenarios["D_stale_consistency"] = {
                "pass": match and (not reachable) and degraded,
                "reachable": reachable,
                "degraded": degraded,
                "daemon_stopped": daemon_stopped,
                "stop_rc": rc,
                "stop_out": out[:300],
                "task_state": _task_state(),
            }
            self.assertTrue(match, "stale: farm_reachable != not is_farm_degraded")
            self.assertFalse(reachable)
            self.assertTrue(degraded)

            _reset_prefetch()
            helper_c = _HelperSpy()
            local_c: list[int] = []
            sentinel = {
                "goal": "local-fallback-sentinel",
                "decisions": [], "open_questions": [],
                "tool_state": [], "hard_constraints": [], "notable_files": [],
            }

            def local_ok(msgs):
                local_c.append(len(msgs))
                return sentinel

            overflow_msgs = _stable_tool_tail_msgs()
            overflow_msgs[-1] = {
                "role": "tool", "name": "web_search",
                "content": "Z" * 8000,
            }
            started = None
            trim_elapsed = None
            trim_err = None
            embed_c_elapsed = None
            embed_c_err = None
            embed_c_local: list[int] = []
            notes_c: list[str] = []

            def local_embed(texts):
                embed_c_local.append(len(texts))
                return [[0.01, 0.02] for _ in texts]

            with helper_c, \
                    patch("context_compactor.summarize_old_messages",
                          side_effect=local_ok):
                t0 = time.monotonic()
                try:
                    started = agent_mod._maybe_start_farm_summary_prefetch(overflow_msgs)
                    agent_mod._trim_context(
                        overflow_msgs, 200, [],
                        emit=lambda k, v: notes_c.append(v) if k == "note" else None,
                    )
                except Exception as exc:
                    trim_err = f"{type(exc).__name__}: {exc}"
                trim_elapsed = round(time.monotonic() - t0, 3)

            tmp_c = tempfile.TemporaryDirectory()
            old_file = retrieval.EMBEDDING_CACHE_FILE
            old_cache = retrieval._EMBED_CACHE
            retrieval.EMBEDDING_CACHE_FILE = Path(tmp_c.name) / "retrieval_embeddings.json"
            retrieval._EMBED_CACHE = None
            try:
                scorer = retrieval.EmbeddingScorer()
                with patch.object(scorer, "_embed", side_effect=local_embed):
                    t1 = time.monotonic()
                    try:
                        scorer.vectors_for([{
                            "id": f"stale-probe:{time.time_ns()}",
                            "text": "stale farm must not hang search_docs",
                        }])
                    except Exception as exc:
                        embed_c_err = f"{type(exc).__name__}: {exc}"
                    embed_c_elapsed = round(time.monotonic() - t1, 3)
            finally:
                retrieval.EMBEDDING_CACHE_FILE = old_file
                retrieval._EMBED_CACHE = old_cache
                tmp_c.cleanup()

            idle = _wait_prefetch_idle(1.0)
            with cp._lock:
                slot = dict(cp._state)

            c_ok = (
                trim_err is None
                and embed_c_err is None
                and started is False
                and not helper_c.calls
                and bool(local_c)
                and bool(embed_c_local)
                and (trim_elapsed or 0) < FALLBACK_BUDGET_S
                and (embed_c_elapsed or 0) < FALLBACK_BUDGET_S
                and idle
                and slot.get("thread") is None
            )
            scenarios["C_failure_injection"] = {
                "pass": c_ok,
                "prefetch_started": started,
                "helper_calls": helper_c.calls,
                "local_summarize_calls": len(local_c),
                "local_embed_calls": embed_c_local,
                "trim_elapsed_s": trim_elapsed,
                "embed_elapsed_s": embed_c_elapsed,
                "trim_err": trim_err,
                "embed_err": embed_c_err,
                "notes": notes_c,
                "slot_thread_is_none": slot.get("thread") is None,
                "idle": idle,
            }
            self.assertIsNone(trim_err, trim_err)
            self.assertIsNone(embed_c_err, embed_c_err)
            self.assertFalse(started, "prefetch started while snapshot was stale")
            self.assertFalse(helper_c.calls, f"helper ran while down: {helper_c.calls}")
            self.assertTrue(local_c, "overflow did not call local summarizer")
            self.assertTrue(embed_c_local, "embed did not call local _embed")
            self.assertLess(trim_elapsed, FALLBACK_BUDGET_S,
                            f"overflow hung {trim_elapsed}s on a down farm")
            self.assertLess(embed_c_elapsed, FALLBACK_BUDGET_S,
                            f"embed hung {embed_c_elapsed}s on a down farm")
            self.assertTrue(idle)
            self.assertIsNone(slot.get("thread"), "prefetch slot wedged")
        finally:
            if backup is not None:
                try:
                    STATUS_PATH.write_text(backup, encoding="utf-8")
                except OSError as exc:
                    restore_err = f"rewrite snapshot: {exc}"
            rc2, out2 = _ps_scheduled_task("Start")
            scenarios["C_restore"] = {
                "pass": rc2 == 0,
                "start_rc": rc2,
                "start_out": out2[:300],
                "task_state": _task_state(),
                "rewrite_err": restore_err,
            }
            # Do not fail the live verify if Start-ScheduledTask is slow;
            # wait briefly for a fresh ok snapshot.
            deadline = time.monotonic() + 45
            restored = False
            while time.monotonic() < deadline:
                if farm_offload.farm_reachable():
                    restored = True
                    break
                time.sleep(1.0)
            scenarios["C_restore"]["reachable_after"] = farm_offload.farm_reachable()
            scenarios["C_restore"]["pass"] = restored and rc2 == 0
            if not restored:
                print("LIVE WARN: farm_status.json still not reachable after restore",
                      flush=True)


if __name__ == "__main__":
    unittest.main()
