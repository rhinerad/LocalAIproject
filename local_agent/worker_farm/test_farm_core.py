"""Worker-farm core tests.

Correct invocation — from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_farm_core local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v

Do not run this file by path. PATH Python is not the farm environment.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_farm_core "
    "local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v"
)


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

from local_agent.worker_farm.farm_core import (
    EncryptedArtifactStore, FarmPolicyError, distill_review_candidates,
    extract_transcript_text, sanitize_text, stage_distillation_source,
)
from local_agent.worker_farm.job_registry import JobRegistry
from local_agent.worker_farm.status import _public
from local_agent.worker_farm import doctor
from local_agent.worker_farm import tasks
from local_agent.worker_farm import submit_distillation
from local_agent.worker_farm import celery_app


KEY = b"k" * 32


class FarmCoreTests(unittest.TestCase):
    def test_sanitizer_removes_path_email_and_token(self):
        value = sanitize_text(
            r"A:\Users\someone\secret.txt user@example.com token=abcd "
            "Authorization: Bearer very-secret-value "
            "https://operator:password@example.invalid/repo "
            "ghp_abcdefghijklmnopqrstuvwxyz123456"
        )
        self.assertNotIn("someone", value)
        self.assertNotIn("user@example.com", value)
        self.assertNotIn("very-secret-value", value)
        self.assertNotIn("operator:password", value)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", value)
        self.assertIn("<REDACTED>", value)

    def test_encrypted_artifact_does_not_contain_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EncryptedArtifactStore(tmp, key=KEY)
            path = store.write_json("artifact_12345678", {"secret": "do not expose"})
            self.assertNotIn("do not expose", path.read_text())
            self.assertEqual("do not expose", store.read_json("artifact_12345678")["secret"])

    def test_tampered_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EncryptedArtifactStore(tmp, key=KEY)
            path = store.write_json("artifact_87654321", {"value": "sealed"})
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["ciphertext_b64"] = "AAAA"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaises(FarmPolicyError) as raised:
                store.read_json("artifact_87654321")
            self.assertNotIn("ciphertext", str(raised.exception).lower())

    def test_distillation_is_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "fixture.txt"
            source.write_text("Preference: always keep C:\\Users\\private\\x hidden\n", encoding="utf-8")
            envelope = stage_distillation_source(source, root=tmp, key=KEY)
            result = distill_review_candidates(envelope, root=tmp, key=KEY)
            self.assertEqual("review_required", result["status"])
            self.assertIn("operator_preference", [item["category"] for item in result["candidates"]])
            self.assertNotIn("private", result["candidates"][0]["text"])

    def test_invalid_key_is_refused(self):
        with self.assertRaises(FarmPolicyError):
            EncryptedArtifactStore(key=b"too-short")

    def test_oversized_source_is_refused_before_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "too-large.txt"
            source.write_text("01234567890", encoding="utf-8")
            with patch("local_agent.worker_farm.farm_core._MAX_SOURCE_BYTES", 10):
                with self.assertRaises(FarmPolicyError):
                    stage_distillation_source(source, root=tmp, key=KEY)

    def test_json_and_html_exports_extract_visible_text_only(self):
        fmt, json_text = extract_transcript_text("export.json", '{"messages":[{"content":"Always keep GPU free"}]}')
        self.assertEqual("json", fmt)
        self.assertIn("Always keep GPU free", json_text)
        fmt, html_text = extract_transcript_text("export.html", "<p>Prefer tests</p><script>password=leak</script>")
        self.assertEqual("html", fmt)
        self.assertIn("Prefer tests", html_text)
        self.assertNotIn("password=leak", html_text)

    def test_job_registry_deduplicates_and_claims_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = JobRegistry(tmp)
            first = {
                "job_id": "distill_aaaaaaaaaaaaaaaaaaaaaaaa",
                "workflow": "historical_memory_distillation",
                "artifact_id": "source_distill_aaaaaaaaaaaaaaaaaaaaaaaa",
                "privacy_class": "private",
                "idempotency_key": "f" * 64,
            }
            second = dict(first, job_id="distill_bbbbbbbbbbbbbbbbbbbbbbbb",
                          artifact_id="source_distill_bbbbbbbbbbbbbbbbbbbbbbbb")
            self.assertTrue(registry.register(first)[0])
            self.assertFalse(registry.register(second)[0])
            registry.mark_queued(first["job_id"])
            self.assertTrue(registry.claim(first["job_id"])[0])
            self.assertFalse(registry.claim(first["job_id"])[0])
            record = registry.complete(first["job_id"], "result_distill_aaaaaaaaaaaaaaaaaaaaaaaa")
            self.assertEqual("completed", record["state"])
            self.assertEqual(1, len(registry.recent()))
            public = _public(record)
            self.assertNotIn("idempotency_key", public)
            self.assertNotIn("artifact_id", public)

    def test_doctor_redis_engine_defaults_to_desktop(self):
        env = {k: v for k, v in os.environ.items() if k != "FARM_REDIS_ENGINE"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual("desktop", doctor.redis_engine())
            argv = doctor.docker_argv()
        self.assertIsNotNone(argv)
        self.assertTrue(argv[0].lower().endswith("docker.exe") or "docker" in Path(argv[0]).name.lower())
        self.assertNotIn("Ubuntu-24.04", argv)

    def test_doctor_redis_engine_wsl_argv(self):
        with patch.dict(os.environ, {"FARM_REDIS_ENGINE": "WSL"}):
            self.assertEqual("wsl", doctor.redis_engine())
            argv = doctor.docker_argv()
        self.assertIsNotNone(argv)
        self.assertIn("Ubuntu-24.04", argv)
        self.assertIn("/usr/bin/docker", argv)
        self.assertNotIn("compose", argv)

    def test_doctor_redis_engine_rejects_unknown(self):
        with patch.dict(os.environ, {"FARM_REDIS_ENGINE": "desktop-linux"}):
            with self.assertRaises(ValueError) as ctx:
                doctor.redis_engine()
        self.assertIn("desktop", str(ctx.exception))
        with patch.dict(os.environ, {"FARM_REDIS_ENGINE": "desktop-linux"}):
            status = doctor.engine_status()
        self.assertFalse(status["ready"])
        self.assertIn("'desktop' or 'wsl'", status["detail"])

    def test_doctor_config_never_exposes_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "REDIS_PASSWORD=secret-value\n"
                "FARM_BROKER_URL=redis://:secret-value@127.0.0.1:6379/0\n"
                "FARM_RESULT_BACKEND=redis://:secret-value@127.0.0.1:6379/1\n"
                "FARM_ROOT=C:/private/farm\n"
                "FARM_ENCRYPTION_KEY_B64=" + "a" * 44 + "\n",
                encoding="utf-8",
            )
            status = doctor.config_status(env_file)
            self.assertTrue(status["valid"])
            self.assertNotIn("secret-value", repr(status))

    def test_transient_task_failure_is_claimable_for_celery_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            envelope = {
                "job_id": "distill_cccccccccccccccccccccccc",
                "workflow": "historical_memory_distillation",
                "artifact_id": "source_distill_cccccccccccccccccccccccc",
                "privacy_class": "private",
                "idempotency_key": "c" * 64,
            }
            registry = JobRegistry(tmp)
            registry.register(envelope)
            registry.mark_queued(envelope["job_id"])
            with patch("local_agent.worker_farm.tasks.JobRegistry", return_value=registry), \
                 patch("local_agent.worker_farm.tasks.distill_review_candidates", side_effect=OSError("offline")):
                with self.assertRaises(OSError):
                    tasks._run_distill(envelope)
            self.assertEqual("queued", registry.get(envelope["job_id"])["state"])

    def test_broker_submission_failure_returns_job_to_staged(self):
        class FailingBroker:
            @staticmethod
            def send_task(*_args, **_kwargs):
                raise OSError("broker offline")

        with tempfile.TemporaryDirectory() as tmp:
            envelope = {
                "job_id": "distill_dddddddddddddddddddddddd",
                "workflow": "historical_memory_distillation",
                "artifact_id": "source_distill_dddddddddddddddddddddddd",
                "privacy_class": "private",
                "idempotency_key": "d" * 64,
            }
            registry = JobRegistry(tmp)
            registry.register(envelope)
            with patch("local_agent.worker_farm.submit_distillation.app", FailingBroker()):
                with self.assertRaises(FarmPolicyError):
                    submit_distillation._queue_envelope(registry, envelope)
            self.assertEqual("staged", registry.get(envelope["job_id"])["state"])

    def test_worker_app_registers_the_distill_task(self):
        # Regression test for a real bug: worker.py launches Celery with
        # `-A local_agent.worker_farm.celery_app:app`, so the worker process
        # only ever imports celery_app.py, never tasks.py directly. Without
        # `include=[...]` on the Celery(...) constructor, distill_export is
        # never registered on the worker's app, so every job submitted by
        # submit_distillation.py's app.send_task(...) (name-based dispatch,
        # not a direct .delay() call) would be silently discarded by the
        # worker as an unregistered task.
        #
        # This must run in a fresh subprocess rather than in-process: this
        # test module already imports local_agent.worker_farm.tasks at file
        # scope (line above), which caches it in sys.modules with app=None
        # (no FARM_BROKER_URL was set yet). A later in-process
        # loader.import_default_modules() call would silently hit that cache
        # and no-op instead of re-registering against a differently
        # configured app, masking the very bug this test exists to catch.
        # A subprocess is also the most faithful reproduction available:
        # worker.py itself starts the real worker as a subprocess.
        probe = (
            "import os, sys\n"
            "try:\n"
            "    import celery  # noqa: F401\n"
            "except ImportError:\n"
            "    print('CELERY_NOT_INSTALLED')\n"
            "    raise SystemExit(2)\n"
            "os.environ['FARM_BROKER_URL'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "os.environ['FARM_RESULT_BACKEND'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "from celery.app.utils import find_app\n"
            "app = find_app('local_agent.worker_farm.celery_app:app')\n"
            "app.loader.import_default_modules()\n"
            "print('REGISTERED' if 'local_agent.worker_farm.tasks.distill_export' in app.tasks else 'MISSING')\n"
        )
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=str(repo_root), env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        marker = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if marker == "CELERY_NOT_INSTALLED" or completed.returncode == 2:
            self.fail(
                "Celery is not installed in this Python environment — you're not "
                "running the farm .venv. From the repository root:\n"
                f"  {_FARM_UNITTEST}"
            )
        self.assertEqual(
            "REGISTERED", marker,
            "worker.py's own '-A local_agent.worker_farm.celery_app:app' load path "
            "never registers distill_export; a submitted job would be silently "
            f"discarded as unregistered. stdout={completed.stdout!r} "
            f"stderr={completed.stderr[-1000:]!r}",
        )

    def test_worker_app_registers_the_connectivity_probe_task(self):
        # Same regression class as test_worker_app_registers_the_distill_task
        # above, for the new connectivity_probe task added for the multi-node
        # LAN plan: a secondary node's worker.py load path must actually
        # register it, or every probe job would be silently discarded.
        probe = (
            "import os, sys\n"
            "try:\n"
            "    import celery  # noqa: F401\n"
            "except ImportError:\n"
            "    print('CELERY_NOT_INSTALLED')\n"
            "    raise SystemExit(2)\n"
            "os.environ['FARM_BROKER_URL'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "os.environ['FARM_RESULT_BACKEND'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "from celery.app.utils import find_app\n"
            "app = find_app('local_agent.worker_farm.celery_app:app')\n"
            "app.loader.import_default_modules()\n"
            "print('REGISTERED' if 'local_agent.worker_farm.tasks.connectivity_probe' in app.tasks else 'MISSING')\n"
        )
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=str(repo_root), env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        marker = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if marker == "CELERY_NOT_INSTALLED" or completed.returncode == 2:
            self.fail(
                "Celery is not installed in this Python environment — you're not "
                "running the farm .venv. From the repository root:\n"
                f"  {_FARM_UNITTEST}"
            )
        self.assertEqual(
            "REGISTERED", marker,
            "connectivity_probe is not registered on the worker's app; "
            f"stdout={completed.stdout!r} stderr={completed.stderr[-1000:]!r}",
        )

    def test_worker_app_registers_the_judge_transcript_task(self):
        # Same regression class as the distill_export/connectivity_probe
        # registration tests above, for the new judge_transcript task.
        probe = (
            "import os, sys\n"
            "try:\n"
            "    import celery  # noqa: F401\n"
            "except ImportError:\n"
            "    print('CELERY_NOT_INSTALLED')\n"
            "    raise SystemExit(2)\n"
            "os.environ['FARM_BROKER_URL'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "os.environ['FARM_RESULT_BACKEND'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "from celery.app.utils import find_app\n"
            "app = find_app('local_agent.worker_farm.celery_app:app')\n"
            "app.loader.import_default_modules()\n"
            "print('REGISTERED' if 'local_agent.worker_farm.tasks.judge_transcript' in app.tasks else 'MISSING')\n"
        )
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=str(repo_root), env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        marker = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if marker == "CELERY_NOT_INSTALLED" or completed.returncode == 2:
            self.fail(
                "Celery is not installed in this Python environment — you're not "
                "running the farm .venv. From the repository root:\n"
                f"  {_FARM_UNITTEST}"
            )
        self.assertEqual(
            "REGISTERED", marker,
            "judge_transcript is not registered on the worker's app; "
            f"stdout={completed.stdout!r} stderr={completed.stderr[-1000:]!r}",
        )

    def test_worker_app_registers_the_judge_transcript_semantic_task(self):
        probe = (
            "import os, sys\n"
            "try:\n"
            "    import celery  # noqa: F401\n"
            "except ImportError:\n"
            "    print('CELERY_NOT_INSTALLED')\n"
            "    raise SystemExit(2)\n"
            "os.environ['FARM_BROKER_URL'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "os.environ['FARM_RESULT_BACKEND'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "from celery.app.utils import find_app\n"
            "app = find_app('local_agent.worker_farm.celery_app:app')\n"
            "app.loader.import_default_modules()\n"
            "print('REGISTERED' if 'local_agent.worker_farm.tasks.judge_transcript_semantic' in app.tasks else 'MISSING')\n"
        )
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=str(repo_root), env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        marker = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if marker == "CELERY_NOT_INSTALLED" or completed.returncode == 2:
            self.fail(
                "Celery is not installed in this Python environment — you're not "
                "running the farm .venv. From the repository root:\n"
                f"  {_FARM_UNITTEST}"
            )
        self.assertEqual(
            "REGISTERED", marker,
            "judge_transcript_semantic is not registered on the worker's app; "
            f"stdout={completed.stdout!r} stderr={completed.stderr[-1000:]!r}",
        )

    def test_judge_transcript_returns_rubric_summary_for_its_envelope(self):
        if tasks.judge_transcript is None:
            self.skipTest("Celery/app not configured in this process")
        envelope = {"chat_id": "abc123", "messages": [
            {"role": "user", "content": "fix the config"},
            {"role": "assistant", "content": "I've fixed the config file."},
        ]}
        result = tasks.judge_transcript.run(envelope)
        self.assertEqual("abc123", result["chat_id"])
        self.assertGreaterEqual(result["finding_count"], 1)

    def test_judge_transcript_rejects_a_malformed_envelope(self):
        if tasks.judge_transcript is None:
            self.skipTest("Celery/app not configured in this process")
        with self.assertRaises(ValueError):
            tasks.judge_transcript.run({"messages": []})
        with self.assertRaises(ValueError):
            tasks.judge_transcript.run({"chat_id": "x", "messages": "not-a-list"})

    def test_worker_app_registers_summarize_and_embed_tasks(self):
        # Same regression class as judge_transcript's registration test above
        # -- and the exact bug that test class exists to catch (a queue in
        # task_routes but not task_queues) was found for `judge` and is why
        # both new queues were added to both dicts together this time.
        probe = (
            "import os, sys\n"
            "try:\n"
            "    import celery  # noqa: F401\n"
            "except ImportError:\n"
            "    print('CELERY_NOT_INSTALLED')\n"
            "    raise SystemExit(2)\n"
            "os.environ['FARM_BROKER_URL'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "os.environ['FARM_RESULT_BACKEND'] = 'redis://:testpass@127.0.0.1:6379/0'\n"
            "from celery.app.utils import find_app\n"
            "app = find_app('local_agent.worker_farm.celery_app:app')\n"
            "app.loader.import_default_modules()\n"
            "names = ('local_agent.worker_farm.tasks.summarize_conversation',\n"
            "         'local_agent.worker_farm.tasks.embed_chunks')\n"
            "missing = [n for n in names if n not in app.tasks]\n"
            "queues = {q.name for q in app.conf.task_queues}\n"
            "missing_queues = [q for q in ('summarize', 'embed') if q not in queues]\n"
            "print('REGISTERED' if not missing and not missing_queues else "
            "f'MISSING tasks={missing} queues={missing_queues}')\n"
        )
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=str(repo_root), env=env,
            capture_output=True, text=True, timeout=30, check=False,
        )
        marker = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if marker == "CELERY_NOT_INSTALLED" or completed.returncode == 2:
            self.fail(
                "Celery is not installed in this Python environment — you're not "
                "running the farm .venv. From the repository root:\n"
                f"  {_FARM_UNITTEST}"
            )
        self.assertEqual(
            "REGISTERED", marker,
            "summarize_conversation/embed_chunks not fully registered "
            f"(task + queue); stdout={completed.stdout!r} stderr={completed.stderr[-1000:]!r}",
        )

    def test_summarize_conversation_returns_helper_result_and_validates_envelope(self):
        if tasks.summarize_conversation is None:
            self.skipTest("Celery/app not configured in this process")
        with patch.object(tasks, "_summarize_messages",
                          return_value={"summarized": True, "summary": {"goal": "x"}}) as mocked:
            result = tasks.summarize_conversation.run(
                {"messages": [{"role": "user", "content": "hi"}]})
        self.assertTrue(result["summarized"])
        mocked.assert_called_once()
        with self.assertRaises(ValueError):
            tasks.summarize_conversation.run({"messages": []})
        with self.assertRaises(ValueError):
            tasks.summarize_conversation.run({})

    def test_summarize_conversation_reports_model_absent_without_raising(self):
        # The realistic first-run case on a fresh worker machine (e.g.
        # mac_worker, which has no LLM installed yet as of 2026-09-02) --
        # this must be a normal reportable result, not a task failure.
        if tasks.summarize_conversation is None:
            self.skipTest("Celery/app not configured in this process")
        with patch.object(tasks, "_summarize_messages",
                          return_value={"summarized": False, "note": "not installed"}):
            result = tasks.summarize_conversation.run(
                {"messages": [{"role": "user", "content": "hi"}]})
        self.assertFalse(result["summarized"])

    def test_summarize_messages_honors_farm_summarize_model_env_var(self):
        # Per-worker model choice (worker_farm/README.md): mac_worker is
        # recorded 2026-09-02 to use a Mistral Nemo abliterated build, not
        # the workstation's llama3.1:8b default. _summarize_messages must
        # read that from this worker's own environment, not a constant.
        seen = {}

        def fake_summarize_old_messages(messages, *, model, host=None, timeout=12):
            seen["model"] = model
            return {"goal": "g", "decisions": [], "open_questions": [],
                    "tool_state": [], "hard_constraints": [], "notable_files": []}

        fake_module = type(sys)("context_compactor")
        fake_module.MODEL = "llama3.1:8b"
        fake_module.summarize_old_messages = fake_summarize_old_messages
        with patch.dict(sys.modules, {"context_compactor": fake_module}), \
             patch.dict(os.environ, {"FARM_SUMMARIZE_MODEL":
                        "krith/mistral-nemo-instruct-2407-abliterated:IQ3_XS"}):
            result = tasks._summarize_messages([{"role": "user", "content": "hi"}])
        self.assertEqual(seen["model"],
                         "krith/mistral-nemo-instruct-2407-abliterated:IQ3_XS")
        self.assertTrue(result["summarized"])
        self.assertEqual(result["model"],
                         "krith/mistral-nemo-instruct-2407-abliterated:IQ3_XS")

    def test_summarize_messages_defaults_to_context_compactor_model_without_env_var(self):
        seen = {}

        def fake_summarize_old_messages(messages, *, model, host=None, timeout=12):
            seen["model"] = model
            return None

        fake_module = type(sys)("context_compactor")
        fake_module.MODEL = "llama3.1:8b"
        fake_module.summarize_old_messages = fake_summarize_old_messages
        with patch.dict(sys.modules, {"context_compactor": fake_module}), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FARM_SUMMARIZE_MODEL", None)
            result = tasks._summarize_messages([{"role": "user", "content": "hi"}])
        self.assertEqual(seen["model"], "llama3.1:8b")
        self.assertFalse(result["summarized"])
        self.assertEqual(result["model_expected"], "llama3.1:8b")

    def test_embed_chunks_returns_helper_result_and_validates_envelope(self):
        if tasks.embed_chunks is None:
            self.skipTest("Celery/app not configured in this process")
        fake = {"vectors": {"a:0": [1.0, 0.0]}, "model": "nomic-embed-text:latest"}
        with patch.object(tasks, "_embed_chunks", return_value=fake) as mocked:
            result = tasks.embed_chunks.run({"chunks": [{"id": "a:0", "text": "hello"}]})
        self.assertEqual(fake, result)
        mocked.assert_called_once()
        with self.assertRaises(ValueError):
            tasks.embed_chunks.run({"chunks": []})
        with self.assertRaises(ValueError):
            tasks.embed_chunks.run({})

    def test_connectivity_probe_returns_only_harmless_identity_fields(self):
        # Direct call (no broker needed) confirming the task body itself never
        # touches the job registry, encrypted artifacts, or any file/network
        # data beyond basic host identity -- it must stay safe to run on an
        # untrusted-by-default new node before any real task exists.
        if tasks.connectivity_probe is None:
            self.skipTest("Celery/app not configured in this process")
        result = tasks.connectivity_probe.run()
        self.assertEqual(
            {"hostname", "platform", "worker_pid", "received_at"}, set(result.keys())
        )
        self.assertIsInstance(result["hostname"], str)
        self.assertIsInstance(result["worker_pid"], int)

    def test_phase1_broker_url_must_be_authenticated_and_loopback(self):
        self.assertTrue(
            celery_app._is_authenticated_loopback_redis_url("redis://:pass@127.0.0.1:6379/0")
        )
        for unsafe_url in (
            "redis://127.0.0.1:6379/0",
            "redis://:pass@192.168.50.10:6379/0",
            "redis://:pass@localhost:6379/0",
            "rediss://:pass@127.0.0.1:6379/0",
            "redis://:pass@127.0.0.1:6379/9",
        ):
            self.assertFalse(celery_app._is_authenticated_loopback_redis_url(unsafe_url))

    def test_phase1_broker_url_accepts_the_one_tunnel_hub_address(self):
        # Added for the multi-node LAN plan (2026-09-01): a secondary node's
        # Celery client points its broker URL at the WireGuard tunnel-hub
        # address, not at 127.0.0.1 (which isn't reachable from another
        # machine at all). This must be narrowly scoped to that one fixed
        # address, db 0 or 1 only -- not "any private IP" -- so the existing
        # 192.168.50.10 rejection above must keep failing.
        self.assertEqual("10.90.90.1", celery_app.FARM_TUNNEL_HUB_HOST)
        self.assertTrue(
            celery_app._is_authenticated_loopback_redis_url(
                "redis://laptop_worker:pass@10.90.90.1:6379/1"
            )
        )
        self.assertTrue(
            celery_app._is_authenticated_loopback_redis_url(
                "redis://:pass@10.90.90.1:6379/0"
            )
        )
        for unsafe_url in (
            "redis://10.90.90.1:6379/0",  # no password
            "redis://:pass@10.90.90.2:6379/0",  # a peer address, not the hub
            "redis://:pass@10.90.90.1:6380/0",  # wrong port
            "rediss://:pass@10.90.90.1:6379/0",  # wrong scheme
            "redis://:pass@10.90.90.1:6379/9",  # unsupported db index
            "redis://:pass@192.168.50.10:6379/0",  # still not a real LAN IP
        ):
            self.assertFalse(celery_app._is_authenticated_loopback_redis_url(unsafe_url))


if __name__ == "__main__":
    sys.stderr.write(
        "ERROR: do not run this file by path. From the repository root, use the farm venv:\n"
        f"  {_FARM_UNITTEST}\n"
    )
    raise SystemExit(2)
