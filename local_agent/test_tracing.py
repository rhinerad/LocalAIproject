#!/usr/bin/env python3
"""Unit tests for the unwired stdlib span logger. No live model."""
from __future__ import annotations

import ast
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tracing


def _source_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TracingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "traces.db"
        tracing.reset_for_tests()
        self._env = patch.dict(os.environ, {
            "LOCAL_AGENT_TRACING": "0",
            "LOCAL_AGENT_TRACES_DB": str(self.db),
        })
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        tracing.reset_for_tests()
        self._tmp.cleanup()

    def _on(self):
        return patch.dict(os.environ, {"LOCAL_AGENT_TRACING": "1"})

    def test_module_does_not_import_agent_router_tools(self) -> None:
        names = _source_imports(HERE / "tracing.py")
        for banned in ("agent", "router", "tools", "artifacts",
                       "remote_security", "ollama_client"):
            self.assertNotIn(banned, names)
        self.assertNotIn("StreamEnd", (HERE / "tracing.py").read_text(encoding="utf8"))

    def test_schema_wal_and_version(self) -> None:
        with self._on():
            with tracing.span("turn", conversation_id="c1"):
                pass
        self.assertTrue(self.db.is_file())
        conn = sqlite3.connect(str(self.db))
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual("wal", str(mode).lower())
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"spans", "span_refs", "schema_meta"} <= tables)
            version = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
            self.assertEqual("1", version)
        finally:
            conn.close()

    def test_hierarchy_parent_and_inherited_ids(self) -> None:
        with self._on():
            tid = tracing.new_trace_id()
            with tracing.span("turn", name="agent.answer", trace_id=tid,
                              conversation_id="chat-1") as turn:
                with tracing.span("hop", hop_index=0) as hop:
                    with tracing.span("route", name="router.decide"):
                        pass
                    with tracing.span("reason", name="ollama.chat_stream"):
                        pass
                    with tracing.span("tool", name="list_dir") as tool:
                        tool_id = tool.span_id
        rows = tracing.fetch_trace(tid)
        by_kind = {row["kind"]: row for row in rows}
        self.assertEqual("chat-1", by_kind["hop"]["conversation_id"])
        self.assertEqual(0, by_kind["tool"]["hop_index"])
        self.assertEqual(turn.span_id, by_kind["hop"]["parent_span_id"])
        self.assertEqual(hop.span_id, by_kind["route"]["parent_span_id"])
        self.assertEqual(hop.span_id, by_kind["reason"]["parent_span_id"])
        self.assertEqual(hop.span_id, by_kind["tool"]["parent_span_id"])
        self.assertEqual(tool_id, by_kind["tool"]["span_id"])
        self.assertEqual("AGENT", by_kind["turn"]["attributes"]["openinference.span.kind"])
        self.assertEqual("LLM", by_kind["reason"]["attributes"]["openinference.span.kind"])
        starts = [row["start_ts"] for row in rows]
        self.assertEqual(starts, sorted(starts))

    def test_kill_switch_creates_no_file(self) -> None:
        with tracing.span("turn", conversation_id="nope") as sp:
            sp.tokens_in = 9
            sp.set("prefer", "cpu")
            sp.link("changelog", target="2026-09-05m")
        self.assertFalse(self.db.exists())
        self.assertTrue(getattr(sp, "dummy", False))
        self.assertEqual([], tracing.fetch_trace("x"))

    def test_failure_isolation_dummy_span(self) -> None:
        ran = []

        def boom(*_a, **_k):
            raise sqlite3.OperationalError("locked")

        with self._on():
            with patch.object(sqlite3, "connect", boom), \
                 patch.object(tracing.LOG, "warning"):
                with tracing.span("turn") as sp:
                    ran.append("body")
                    sp.tokens_in = 4
                    sp.set("x", "y")
                    sp.link("comfy_mcp_audit", target="runtime/x#0")
        self.assertEqual(["body"], ran)
        self.assertTrue(sp.dummy)
        self.assertFalse(self.db.exists())

    def test_redaction_does_not_call_artifacts_store(self) -> None:
        artifact_dir = HERE / "runtime" / "artifacts"
        before = set(artifact_dir.glob("artifact_*.json")) if artifact_dir.is_dir() else set()
        huge = "PROMPT-SECRET-" + ("n" * 10000)
        with self._on():
            with tracing.span("turn") as turn:
                turn.output_summary = tracing.summarize_text("turn_output", huge)
                tid = turn.trace_id
        after = set(artifact_dir.glob("artifact_*.json")) if artifact_dir.is_dir() else set()
        self.assertEqual(before, after)
        rows = tracing.fetch_trace(tid)
        summary = rows[0]["output_summary"]
        self.assertLessEqual(len(summary), tracing.SUMMARY_LIMIT + 120)
        self.assertNotEqual(huge, summary)
        self.assertNotIn(huge, json.dumps(rows))
        self.assertIn("sha1=", summary)
        self.assertIn("original_chars=10014", summary)
        pointer = "[tool output pruned; artifact_id=artifact_deadbeef; stored locally]"
        self.assertEqual(pointer, tracing.summarize_text("tool", pointer))

    def test_record_decision_allow_list_strips_occupancy(self) -> None:
        route = SimpleNamespace(
            tier="gpu",
            host="127.0.0.1:11434",
            model="huihui_ai/qwen3-abliterated:14b",
            gpu_busy=False,
            reason="GPU free",
            backend="ollama",
            detail={
                "capability": "tool",
                "timeshare": {
                    "path": "already_claimed",
                    "outcome": "already claimed",
                    "clear_vram": {"ok": True, "detail": "cleared"},
                    "occupancy": {
                        "used_mib": 12139,
                        "ollama_resident": ["secret-process.exe"],
                    },
                },
            },
        )
        with self._on():
            with tracing.span("route") as sp:
                tracing.record_decision(sp, route, skip_farm=True, profile="gpu")
                tid = sp.trace_id
        row = tracing.fetch_trace(tid)[0]
        blob = json.dumps(row, ensure_ascii=False)
        self.assertNotIn("secret-process.exe", blob)
        self.assertNotIn("occupancy", blob)
        attrs = row["attributes"]
        self.assertEqual("127.0.0.1:11434", attrs["host"])
        self.assertTrue(attrs["skip_farm"])
        self.assertEqual("tool", attrs["capability"])
        self.assertEqual("already_claimed", attrs["timeshare.path"])
        self.assertEqual("already claimed", attrs["timeshare.outcome"])
        self.assertTrue(attrs["timeshare.clear_vram.ok"])
        self.assertEqual("gpu", row["tier"])
        self.assertEqual(route.model, row["model"])

    def test_tool_arg_summary_stable_sha_and_truncated_path(self) -> None:
        prompt = "a red mug on a table " * 40
        args = {
            "path": "/very/" + ("long/" * 80) + "workflow.json",
            "prompt": prompt,
            "clip": "00A",
        }
        first = tracing.summarize_tool_args(args)
        second = tracing.summarize_tool_args(args)
        self.assertEqual(first.arg_sha256, second.arg_sha256)
        self.assertEqual(["clip", "path", "prompt"], first.arg_keys)
        self.assertTrue(first.text.startswith("keys="))
        self.assertIn("path=", first.text)
        self.assertLessEqual(len(first.text.split("path=")[1].split(";")[0]), 260)
        self.assertNotIn(prompt, first.text)
        with self._on():
            with tracing.span("tool", name="comfy_generate") as sp:
                sp.input_summary = first.text
                sp.set("arg_sha256", first.arg_sha256)
                sp.set("arg_keys", first.arg_keys)
                sp.set("arg_json_bytes", first.arg_json_bytes)
                tid = sp.trace_id
        blob = json.dumps(tracing.fetch_trace(tid), ensure_ascii=False)
        self.assertNotIn(prompt, blob)

    def test_link_round_trips_offset_and_prompt_id(self) -> None:
        with self._on():
            with tracing.span("tool", name="comfy_generate") as sp:
                sp.link(
                    "comfy_mcp_audit",
                    target="runtime/comfy_mcp_audit.jsonl#128",
                    offset=128,
                    ts=1.5,
                    extra={
                        "prompt_id": "abc123",
                        "mcp_status": "ok",
                        "caller_file": "agent.py",
                        "nested": {"drop": True},
                    },
                )
                tid = sp.trace_id
        refs = tracing.fetch_trace(tid)[0]["refs"]
        self.assertEqual(1, len(refs))
        self.assertEqual("comfy_mcp_audit", refs[0]["ref_kind"])
        self.assertEqual("runtime/comfy_mcp_audit.jsonl#128", refs[0]["ref_target"])
        self.assertEqual(128, refs[0]["ref_offset"])
        self.assertEqual(1.5, refs[0]["ref_ts"])
        self.assertEqual("abc123", refs[0]["ref_extra"]["prompt_id"])
        self.assertEqual("ok", refs[0]["ref_extra"]["mcp_status"])
        self.assertEqual("agent.py", refs[0]["ref_extra"]["caller_file"])
        self.assertNotIn("nested", refs[0]["ref_extra"])

    def test_prune_deletes_whole_old_traces(self) -> None:
        with self._on():
            with tracing.span("turn", conversation_id="old") as old:
                with tracing.span("hop", hop_index=0):
                    pass
                old_id = old.trace_id
            with tracing.span("turn", conversation_id="new") as new:
                new_id = new.trace_id
            conn = sqlite3.connect(str(self.db))
            conn.execute(
                "UPDATE spans SET start_ts=1.0 WHERE trace_id=?", (old_id,))
            conn.commit()
            conn.close()
            result = tracing.prune(max_age_days=1, max_spans=50_000)
        self.assertGreaterEqual(result["deleted_spans"], 2)
        self.assertEqual([], tracing.fetch_trace(old_id))
        self.assertEqual(1, len(tracing.fetch_trace(new_id)))

    def test_prune_cap_deletes_oldest_whole_traces(self) -> None:
        ids = []
        with self._on():
            for i in range(3):
                with tracing.span("turn", conversation_id=f"c{i}") as turn:
                    with tracing.span("hop", hop_index=0):
                        pass
                    ids.append(turn.trace_id)
            result = tracing.prune(max_age_days=36500, max_spans=5)
        self.assertGreater(result["deleted_spans"], 0)
        self.assertLessEqual(result["remaining_spans"], 4)
        self.assertEqual([], tracing.fetch_trace(ids[0]))

    def test_concurrency_two_threads(self) -> None:
        errors: list[BaseException] = []

        def worker(label: str) -> None:
            try:
                with tracing.span("turn", conversation_id=label) as turn:
                    with tracing.span("hop", hop_index=0):
                        with tracing.span("reason"):
                            turn.set("label", label)
            except Exception as exc:  # noqa: BLE001 — collect for the parent
                errors.append(exc)

        with self._on():
            threads = [threading.Thread(target=worker, args=(f"t{i}",))
                       for i in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual([], errors)
        conn = sqlite3.connect(str(self.db))
        try:
            n = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(6, n)

    def test_concurrent_first_open_never_marks_broken(self) -> None:
        # Fresh DB per round: the rollback->WAL switch raised an immediate
        # "database is locked" for the losing thread and disabled tracing.
        def worker(label: str) -> None:
            with tracing.span("turn", conversation_id=label):
                pass

        for round_no in range(25):
            db = Path(self._tmp.name) / f"race_{round_no}.db"
            with patch.dict(os.environ, {"LOCAL_AGENT_TRACING": "1",
                                         "LOCAL_AGENT_TRACES_DB": str(db)}):
                threads = [threading.Thread(target=worker, args=(f"r{round_no}t{i}",))
                           for i in range(4)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
            self.assertFalse(tracing._BROKEN, f"round {round_no}")
            conn = sqlite3.connect(str(db))
            try:
                n = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(4, n, f"round {round_no}")
            self.assertEqual("wal", mode)

    def test_dummy_parent_does_not_leak_into_enabled_span(self) -> None:
        with tracing.span("turn") as dummy:
            self.assertTrue(dummy.dummy)
            with self._on():
                with tracing.span("hop", hop_index=1) as hop:
                    hop_id = hop.trace_id
                    hop_parent = hop.parent_span_id
        self.assertIsNone(hop_parent)
        row = tracing.fetch_trace(hop_id)[0]
        self.assertIsNone(row["parent_span_id"])
        self.assertEqual(1, row["hop_index"])

    def test_body_exception_is_reraised_and_recorded(self) -> None:
        with self._on():
            with self.assertRaises(RuntimeError):
                with tracing.span("turn") as turn:
                    tid = turn.trace_id
                    raise RuntimeError("boom-test")
        row = tracing.fetch_trace(tid)[0]
        self.assertEqual("ERROR", row["status_code"])
        self.assertIn("boom-test", row["error"])

    def test_default_db_path_is_not_written_by_this_suite(self) -> None:
        # knowledge/traces.db legitimately exists once the app has run
        # (tracing is on in production), so assert the guard, not the file.
        self.assertEqual(self.db, tracing.db_path())
        self.assertNotEqual(tracing.DEFAULT_DB, tracing.db_path())
        env = {k: v for k, v in os.environ.items()
               if k not in ("LOCAL_AGENT_TRACING", "LOCAL_AGENT_TRACES_DB")}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(tracing, "_connection") as conn:
            self.assertEqual(tracing.DEFAULT_DB, tracing.db_path())
            self.assertFalse(tracing.enabled())
            with tracing.span("turn") as turn:
                self.assertTrue(turn.dummy)
        conn.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
