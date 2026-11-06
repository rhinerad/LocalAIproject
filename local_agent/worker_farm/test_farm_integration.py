r"""Live worker-farm integration tests (slow). Not part of the fast suite.

Submits real summarize_conversation, embed_chunks, and judge_transcript
tasks to the connected farm and waits for a real result. Skips (does not
fail) if the farm is unreachable.

Correct invocation — from the repository root, farm venv only:

  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v

Do not run this file by path. PATH Python is not the farm environment.
This module is deliberately omitted from the README fast-suite command.
"""
from __future__ import annotations

import sys
import unittest

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_farm_integration -v"
)

SUMMARIZE_TASK = "local_agent.worker_farm.tasks.summarize_conversation"
EMBED_TASK = "local_agent.worker_farm.tasks.embed_chunks"
JUDGE_TASK = "local_agent.worker_farm.tasks.judge_transcript"
SUMMARIZE_TIMEOUT_S = 180.0
EMBED_TIMEOUT_S = 90.0
JUDGE_TIMEOUT_S = 60.0


def _require_package_layout() -> None:
    """Fail loudly when this file is executed by path instead of as a package."""
    try:
        import local_agent.worker_farm  # noqa: F401
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
            raise
        sys.stderr.write(
            "ERROR: local_agent is not importable because this file was run by path.\n"
            "From the repository root, use the farm venv:\n"
            f"  {_FARM_UNITTEST}\n"
        )
        raise SystemExit(2) from exc


_require_package_layout()

from local_agent.worker_farm import farm_health
from local_agent.worker_farm._farm_submit_wait import _load_env_file


def _send_live_task(task_name: str, queue: str, envelope: dict, timeout_s: float):
    """Submit one Celery task to the live farm and wait for the result."""
    _load_env_file()
    from local_agent.worker_farm.celery_app import create_app
    app = create_app()
    async_result = app.send_task(task_name, args=[envelope], queue=queue)
    result = async_result.get(timeout=timeout_s, propagate=False)
    if isinstance(result, Exception):
        raise AssertionError(
            f"{task_name} raised {type(result).__name__}: {result}"
        )
    return result, async_result.id


class LiveFarmIntegrationTests(unittest.TestCase):
    """Live-farm / slow / integration. Skip (do not fail) if unreachable."""

    health: dict

    @classmethod
    def setUpClass(cls):
        cls.health = farm_health.check_farm_health(timeout_s=5.0)
        print(
            "LIVE farm health: "
            + farm_health.format_status_line(cls.health),
            flush=True,
        )
        registered = farm_health.registered_report_from_health(cls.health)
        print(
            "LIVE registered-task check: "
            + farm_health.format_registered_line(registered),
            flush=True,
        )

    def setUp(self):
        if self.health.get("status") != "ok":
            self.skipTest(
                f"live farm unreachable ({self.health.get('status')}): "
                f"{self.health.get('error')}"
            )

    def test_registered_tasks_include_summarize_and_embed(self):
        registered = farm_health.registered_report_from_health(self.health)
        names = registered.get("registered_tasks") or []
        print(f"LIVE registered tasks: {names}", flush=True)
        self.assertIn(
            SUMMARIZE_TASK, names,
            msg=f"summarize_conversation not registered; worker reported {names}",
        )
        self.assertIn(
            EMBED_TASK, names,
            msg=f"embed_chunks not registered; worker reported {names}",
        )
        self.assertIn(
            JUDGE_TASK, names,
            msg=f"judge_transcript not registered; worker reported {names}",
        )
        self.assertEqual(registered.get("status"), "ok",
                         msg=farm_health.format_registered_line(registered))

    def test_summarize_conversation_returns_real_result(self):
        envelope = {
            "messages": [
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "4"},
            ],
        }
        result, task_id = _send_live_task(
            SUMMARIZE_TASK, "summarize", envelope, SUMMARIZE_TIMEOUT_S)
        print(
            f"LIVE summarize_conversation task_id={task_id} "
            f"keys={sorted(result.keys()) if isinstance(result, dict) else type(result).__name__} "
            f"summarized={result.get('summarized') if isinstance(result, dict) else None}",
            flush=True,
        )
        self.assertIsInstance(result, dict, msg=f"got {type(result).__name__}: {result!r}")
        self.assertIn("summarized", result)
        if result.get("summarized"):
            summary = result.get("summary")
            self.assertTrue(summary, msg=f"summarized=True but empty summary: {result}")
        else:
            self.assertIn("model_expected", result)
            self.assertIn("note", result)

    def test_embed_chunks_returns_real_vectors(self):
        envelope = {
            "chunks": [
                {"id": "t1", "text": "hello world"},
                {"id": "t2", "text": "farm integration check"},
            ],
        }
        result, task_id = _send_live_task(
            EMBED_TASK, "embed", envelope, EMBED_TIMEOUT_S)
        vectors = result.get("vectors") if isinstance(result, dict) else None
        dims = {
            key: (len(vec) if isinstance(vec, list) else type(vec).__name__)
            for key, vec in (vectors or {}).items()
        }
        print(
            f"LIVE embed_chunks task_id={task_id} "
            f"keys={sorted(result.keys()) if isinstance(result, dict) else type(result).__name__} "
            f"vector_dims={dims} model={result.get('model') if isinstance(result, dict) else None}",
            flush=True,
        )
        self.assertIsInstance(result, dict, msg=f"got {type(result).__name__}: {result!r}")
        self.assertIn("vectors", result)
        self.assertIsInstance(result["vectors"], dict)
        self.assertEqual(set(result["vectors"]), {"t1", "t2"})
        for chunk_id, vec in result["vectors"].items():
            self.assertIsInstance(vec, list, msg=f"{chunk_id} vector is {type(vec).__name__}")
            self.assertGreater(len(vec), 0, msg=f"{chunk_id} vector is empty")
            self.assertIsInstance(vec[0], (int, float))

    def test_judge_transcript_returns_real_result(self):
        envelope = {
            "chat_id": "farm-integration-judge",
            "messages": [
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "4"},
            ],
        }
        result, task_id = _send_live_task(
            JUDGE_TASK, "judge", envelope, JUDGE_TIMEOUT_S)
        print(
            f"LIVE judge_transcript task_id={task_id} "
            f"keys={sorted(result.keys()) if isinstance(result, dict) else type(result).__name__} "
            f"status={result.get('status') if isinstance(result, dict) else None} "
            f"finding_count={result.get('finding_count') if isinstance(result, dict) else None}",
            flush=True,
        )
        self.assertIsInstance(result, dict, msg=f"got {type(result).__name__}: {result!r}")
        self.assertEqual(result.get("chat_id"), envelope["chat_id"])
        self.assertEqual(result.get("message_count"), 2)
        self.assertIn("finding_count", result)
        self.assertIsInstance(result.get("finding_count"), int)
        self.assertIn("findings", result)
        self.assertIsInstance(result["findings"], list)
        self.assertIn("by_rule", result)
        self.assertIsInstance(result["by_rule"], dict)
        self.assertIn(result.get("status"), {"no_findings", "review_required"})


if __name__ == "__main__":
    _require_package_layout()
    unittest.main()
