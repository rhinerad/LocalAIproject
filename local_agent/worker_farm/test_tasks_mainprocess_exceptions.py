r"""Celery MainProcess must be able to unpickle ollama_client exceptions.

Correct invocation — from the repository root, farm venv only:

  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_tasks_mainprocess_exceptions -v

Do not run this file by path. PATH Python is not the farm environment.
"""
from __future__ import annotations

import subprocess
import sys
import unittest

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_tasks_mainprocess_exceptions -v"
)


def _require_package_layout() -> None:
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


class MainProcessOllamaExceptionTests(unittest.TestCase):
    def test_repo_root_alone_cannot_import_ollama_client(self):
        """The original MainProcess layout: repo root on path, not local_agent/."""
        result = subprocess.run(
            [sys.executable, "-c", "import ollama_client"],
            cwd=".",
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn("No module named 'ollama_client'", result.stderr)

    def test_importing_tasks_makes_ollama_unavailable_unpickleable(self):
        """After the fix, loading tasks.py (what Celery MainProcess does via
        celery_app include=) registers ollama_client so a fork-raised
        OllamaUnavailable can be unpickled/repr'd instead of crashing."""
        code = r"""
import pickle
import sys
from local_agent.worker_farm import tasks
assert "ollama_client" in sys.modules, sorted(m for m in sys.modules if "ollama" in m)
import ollama_client
exc = ollama_client.OllamaUnavailable("cannot reach Ollama at 127.0.0.1:11434")
blob = pickle.dumps(exc)
restored = pickle.loads(blob)
assert type(restored) is ollama_client.OllamaUnavailable, type(restored)
assert "cannot reach Ollama" in str(restored)
print("ok")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=".",
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("ok", result.stdout)

    def test_tasks_module_imports_ollama_client_at_load(self):
        import importlib
        import local_agent.worker_farm.tasks as tasks
        importlib.reload(tasks)
        self.assertTrue(hasattr(tasks, "_ollama_client"))
        self.assertEqual(tasks._ollama_client.OllamaUnavailable.__name__, "OllamaUnavailable")


if __name__ == "__main__":
    unittest.main()
