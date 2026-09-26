#!/usr/bin/env python3
"""Unit tests for the comfy_* tool wrappers and the comfy_process guardrail.

Mocks mcp_client, thermal_guard, and supervisor liveness. No live ComfyUI.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import remote_security
import tools


class _FakeSample:
    def __init__(self, temperature_c: int) -> None:
        self.temperature_c = temperature_c
        self.utilization_percent = 0
        self.power_watts = 0.0


class ComfyToolDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audit = Path(tmp.name) / "comfy_mcp_audit.jsonl"
        self.audit_patch = patch.object(tools, "_COMFY_AUDIT_PATH", self.audit)
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)

        def fake_call(name, args, timeout=None):
            self.calls.append((name, dict(args)))
            if name == "generate_image":
                return {
                    "status": "enqueued",
                    "prompt_id": "probe-prompt-id",
                    "queue_remaining": 1,
                }
            return {"ok": True, "tool": name, "args": args}

        self.patcher = patch("mcp_client.call", side_effect=fake_call)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_all_seven_registered(self):
        for name in (
            "comfy_generate", "comfy_workflow", "comfy_assets",
            "comfy_models", "comfy_nodes", "comfy_system", "comfy_process",
        ):
            self.assertIn(name, tools.TOOLS)

    def test_project_only_includes_process_and_nodes(self):
        self.assertIn("comfy_process", tools.PROJECT_ONLY_TOOLS)
        self.assertIn("comfy_nodes", tools.PROJECT_ONLY_TOOLS)

    def test_none_are_concurrency_safe(self):
        for name in (
            "comfy_generate", "comfy_workflow", "comfy_assets",
            "comfy_models", "comfy_nodes", "comfy_system", "comfy_process",
        ):
            self.assertNotIn(name, tools.CONCURRENCY_SAFE_TOOLS)

    def test_phone_gated(self):
        for name in (
            "comfy_generate", "comfy_workflow", "comfy_assets",
            "comfy_models", "comfy_nodes", "comfy_system", "comfy_process",
        ):
            self.assertIn(name, remote_security.GATED_REMOTE_TOOLS)

    def test_generate_defaults_to_image_action(self):
        raw = tools.comfy_generate({"prompt": "a lamp"})
        data = json.loads(raw)
        self.assertEqual(self.calls[-1][0], "generate_image")
        self.assertEqual(self.calls[-1][1]["action"], "image")
        self.assertEqual(self.calls[-1][1]["prompt"], "a lamp")
        self.assertEqual(data["status"], "enqueued")

    def test_generate_writes_audit_with_prompt_id_and_caller(self):
        tools.comfy_generate({
            "prompt": "a lamp",
            "filename_prefix": "mcp_live_verify_should_not_matter",
        })
        lines = self.audit.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["local_tool"], "comfy_generate")
        self.assertEqual(record["mcp_tool"], "generate_image")
        self.assertEqual(record["risk"], "generate")
        self.assertEqual(record["mcp_status"], "ok")
        self.assertEqual(record["prompt_id"], "probe-prompt-id")
        self.assertEqual(record["args"]["prompt"], "a lamp")
        self.assertEqual(record["args"]["filename_prefix"], "mcp_live_verify_should_not_matter")
        self.assertIn("pid", record["caller"])
        self.assertTrue(record["caller"]["file"].endswith("test_comfy_tools.py"))
        self.assertEqual(record["caller"]["function"], "test_generate_writes_audit_with_prompt_id_and_caller")

    def test_generate_audit_on_mcp_error(self):
        with patch("mcp_client.call", side_effect=tools.ToolError("mcp down")):
            with self.assertRaises(tools.ToolError):
                tools.comfy_generate({"prompt": "a lamp"})
        record = json.loads(self.audit.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(record["mcp_status"], "error")
        self.assertIsNone(record["prompt_id"])
        self.assertIn("mcp down", record["error"])

    def test_workflow_rejects_unknown_mcp_tool(self):
        with self.assertRaises(tools.ToolError) as ctx:
            tools.comfy_workflow({"tool": "restart_comfyui"})
        self.assertIn("not a raw MCP passthrough", str(ctx.exception))
        self.assertFalse(self.calls)

    def test_workflow_dispatches_named_tool(self):
        tools.comfy_workflow({"tool": "queue", "action": "status"})
        self.assertEqual(self.calls[-1], ("queue", {"action": "status"}))

    def _api_graph(self, prefix="mcp_test/unit"):
        return {
            "1": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "v1-5-pruned-emaonly-fp16.safetensors"}},
            "7": {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0], "filename_prefix": prefix}},
        }

    def test_enqueue_passes_dict_workflow_through(self):
        graph = self._api_graph()
        tools.comfy_workflow({
            "tool": "enqueue_workflow",
            "action": "enqueue",
            "workflow": graph,
        })
        name, payload = self.calls[-1]
        self.assertEqual(name, "enqueue_workflow")
        self.assertEqual(payload["action"], "enqueue")
        self.assertEqual(payload["workflow"]["7"]["class_type"], "SaveImage")
        self.assertNotIn("workflow_path", payload)

    def test_enqueue_loads_workflow_path_and_strips_alias(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "graph.json"
        graph = self._api_graph("mcp_test/from_path")
        path.write_text(json.dumps(graph), encoding="utf-8")
        tools.comfy_workflow({
            "tool": "enqueue_workflow",
            "action": "enqueue",
            "workflow_path": str(path),
        })
        name, payload = self.calls[-1]
        self.assertEqual(name, "enqueue_workflow")
        self.assertEqual(payload["workflow"]["7"]["inputs"]["filename_prefix"],
                         "mcp_test/from_path")
        self.assertNotIn("workflow_path", payload)
        self.assertNotIn("path", payload)

    def test_enqueue_loads_path_string_in_workflow_field(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "graph.json"
        graph = self._api_graph()
        path.write_text(json.dumps(graph), encoding="utf-8")
        tools.comfy_workflow({
            "tool": "enqueue_workflow",
            "action": "enqueue",
            "workflow": str(path),
        })
        _, payload = self.calls[-1]
        self.assertIsInstance(payload["workflow"], dict)
        self.assertEqual(payload["workflow"]["1"]["class_type"],
                         "CheckpointLoaderSimple")

    def test_enqueue_parses_workflow_json_string(self):
        graph = self._api_graph()
        tools.comfy_workflow({
            "tool": "enqueue_workflow",
            "workflow": json.dumps(graph),
        })
        _, payload = self.calls[-1]
        self.assertEqual(payload["action"], "enqueue")
        self.assertEqual(payload["workflow"]["1"]["inputs"]["ckpt_name"],
                         "v1-5-pruned-emaonly-fp16.safetensors")

    def test_enqueue_unwraps_prompt_wrapper(self):
        graph = self._api_graph()
        tools.comfy_workflow({
            "tool": "enqueue_workflow",
            "action": "enqueue",
            "workflow": {"prompt": graph, "client_id": "x"},
        })
        _, payload = self.calls[-1]
        self.assertIn("1", payload["workflow"])
        self.assertNotIn("client_id", payload["workflow"])

    def test_enqueue_missing_file_does_not_call_mcp(self):
        with self.assertRaises(tools.ToolError) as ctx:
            tools.comfy_workflow({
                "tool": "enqueue_workflow",
                "action": "enqueue",
                "workflow_path": "does/not/exist.json",
            })
        self.assertIn("not found", str(ctx.exception))
        self.assertFalse(self.calls)

    def test_enqueue_rejects_url_path(self):
        with self.assertRaises(tools.ToolError) as ctx:
            tools.comfy_workflow({
                "tool": "enqueue_workflow",
                "action": "enqueue",
                "workflow": "https://example.invalid/graph.json",
            })
        self.assertIn("URL", str(ctx.exception))
        self.assertFalse(self.calls)

    def test_enqueue_rejects_ui_format(self):
        with self.assertRaises(tools.ToolError) as ctx:
            tools.comfy_workflow({
                "tool": "enqueue_workflow",
                "action": "enqueue",
                "workflow": {"nodes": [{"id": 1, "type": "SaveImage"}], "links": []},
            })
        self.assertIn("UI-format", str(ctx.exception))
        self.assertFalse(self.calls)

    def test_queue_status_does_not_consume_workflow_path(self):
        tools.comfy_workflow({
            "tool": "queue",
            "action": "status",
            "workflow_path": "ignored.json",
        })
        self.assertEqual(self.calls[-1], ("queue", {"action": "status"}))

    def test_system_defaults_to_get_system_stats(self):
        tools.comfy_system({})
        self.assertEqual(self.calls[-1][0], "get_system_stats")
        self.assertEqual(self.calls[-1][1].get("action"), "stats")

    def test_nodes_and_model_remove_write_audit(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        audit = Path(tmp.name) / "comfy_mcp_audit.jsonl"
        with patch.object(tools, "_COMFY_AUDIT_PATH", audit):
            tools.comfy_models({"tool": "list_local_models", "action": "remove", "filename": "x.safetensors"})
            tools.comfy_nodes({"tool": "install_custom_node", "url": "https://example.invalid/pack"})
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        self.assertEqual(first["risk"], "model_delete")
        self.assertEqual(second["risk"], "custom_node_install")

    def test_audit_binary_offset_seek_roundtrip(self):
        tools.comfy_generate({"prompt": "first mug"})
        first = tools.last_comfy_audit()
        tools.comfy_generate({"prompt": "second mug"})
        second = tools.last_comfy_audit()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertLess(first[0], second[0])
        self.assertEqual("probe-prompt-id", second[1])
        with self.audit.open("rb") as fh:
            fh.seek(first[0])
            row = json.loads(fh.readline())
        self.assertEqual("first mug", row["args"]["prompt"])
        with self.audit.open("rb") as fh:
            fh.seek(second[0])
            row = json.loads(fh.readline())
        self.assertEqual("second mug", row["args"]["prompt"])

    def test_audit_link_does_not_copy_prompt_into_traces_db(self):
        import tracing
        secret = "UNIQUE_MUG_PROMPT_TOKEN_7d474ba55d244abe"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "traces.db"
        with patch.dict(os.environ, {
            "LOCAL_AGENT_TRACING": "1",
            "LOCAL_AGENT_TRACES_DB": str(db),
        }):
            tracing.reset_for_tests()
            with tracing.span("tool", name="comfy_generate") as span:
                tools.comfy_generate({"prompt": secret})
                tid = span.trace_id
            rows = tracing.fetch_trace(tid)
        refs = rows[0]["refs"]
        self.assertEqual(1, len(refs))
        self.assertEqual("comfy_mcp_audit", refs[0]["ref_kind"])
        self.assertEqual("probe-prompt-id", refs[0]["ref_extra"]["prompt_id"])
        self.assertTrue(str(refs[0]["ref_extra"]["caller_file"]).endswith(
            "test_comfy_tools.py"))
        self.assertNotIn(secret.encode("utf-8"), db.read_bytes())
        with self.audit.open("rb") as fh:
            fh.seek(refs[0]["ref_offset"])
            record = json.loads(fh.readline())
        self.assertEqual(secret, record["args"]["prompt"])

    def test_audit_link_failure_does_not_fail_generate(self):
        import tracing
        with patch.object(tracing, "current_span",
                          side_effect=RuntimeError("link boom")), \
             patch.object(tracing.LOG, "warning"):
            raw = tools.comfy_generate({"prompt": "a lamp"})
        data = json.loads(raw)
        self.assertEqual("probe-prompt-id", data["prompt_id"])
        self.assertTrue(self.audit.is_file())
        self.assertEqual("probe-prompt-id", tools.last_comfy_audit()[1])


class ComfyProcessGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mcp = patch("mcp_client.call", return_value={"ok": True, "restarted": True})
        self.mcp.start()
        self.addCleanup(self.mcp.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audit = Path(tmp.name) / "audit.jsonl"
        self.audit_patch = patch.object(tools, "_COMFY_AUDIT_PATH", self.audit)
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)

    def test_refuses_when_supervisor_owns_process(self):
        with patch.object(tools, "_thermal_blocks_comfy_process", return_value=None), \
             patch.object(tools, "_supervisor_owns_comfyui",
                          return_value="stage supervisor owns ComfyUI (render queue claimed by live pid 4242 (audio pass))"):
            raw = tools.call("comfy_process", {"action": "restart"})
        self.assertTrue(raw.startswith("ERROR:"), raw)
        self.assertIn("comfy_process refused", raw)
        self.assertIn("stage supervisor owns ComfyUI", raw)
        self.assertIn("4242", raw)
        self.assertFalse(self.audit.exists(), "refusal must not call MCP or write a process-control audit")

    def test_refuses_when_gpu_over_thermal_ceiling(self):
        work = str((HERE.parent / "work").resolve())
        if work not in sys.path:
            sys.path.insert(0, work)
        import thermal_guard as real_tg
        with patch.object(real_tg, "sample_gpu", return_value=_FakeSample(91)), \
             patch.object(real_tg, "EMERGENCY_C", 82), \
             patch.object(real_tg, "START_MAX_C", 70), \
             patch.object(tools, "_supervisor_owns_comfyui", return_value=None):
            raw = tools.call("comfy_process", {"action": "stop"})
        self.assertTrue(raw.startswith("ERROR:"), raw)
        self.assertIn("comfy_process refused", raw)
        self.assertIn("91", raw)

    def test_refuses_when_thermal_telemetry_missing(self):
        work = str((HERE.parent / "work").resolve())
        if work not in sys.path:
            sys.path.insert(0, work)
        import thermal_guard as real_tg
        with patch.object(real_tg, "sample_gpu",
                          side_effect=real_tg.ThermalTelemetryError("nvidia-smi not found")), \
             patch.object(tools, "_supervisor_owns_comfyui", return_value=None):
            raw = tools.call("comfy_process", {"action": "start"})
        self.assertTrue(raw.startswith("ERROR:"), raw)
        self.assertIn("thermal telemetry unavailable", raw)

    def test_supervisor_check_uses_live_pid_same_as_start_batch_render(self):
        with patch("router.queue_owner", return_value=(False, "queue owner released")), \
             patch.object(tools, "_json", return_value={"pid": 0}), \
             patch.object(tools, "_pid_is_live", return_value=False):
            self.assertIsNone(tools._supervisor_owns_comfyui())
        with patch("router.queue_owner",
                   return_value=(True, "render queue claimed by live pid 99 (stage supervisor)")):
            reason = tools._supervisor_owns_comfyui()
        self.assertIn("stage supervisor owns ComfyUI", reason)
        self.assertIn("99", reason)

    def test_allows_when_cool_and_unowned_then_calls_restart_comfyui(self):
        with patch.object(tools, "_thermal_blocks_comfy_process", return_value=None), \
             patch.object(tools, "_supervisor_owns_comfyui", return_value=None):
            raw = tools.comfy_process({"action": "restart"})
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertTrue(self.audit.is_file())
        record = json.loads(self.audit.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["mcp_tool"], "restart_comfyui")
        self.assertEqual(record["risk"], "process_control")


class _HistResp:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ComfyJobStatusTests(unittest.TestCase):
    PID = "8182b9d1-e080-4d9e-9f85-bc5bccdb4be6"

    def _complete_payload(self, filename="ComfyUI_00214_.png"):
        return {
            self.PID: {
                "outputs": {
                    "7": {"images": [{"filename": filename, "subfolder": "",
                                      "type": "output"}]},
                },
                "status": {"status_str": "success", "completed": True},
            }
        }

    def test_registered_read_only_and_not_phone_gated(self):
        self.assertIn("comfy_job_status", tools.TOOLS)
        self.assertIn("comfy_job_status", tools.CONCURRENCY_SAFE_TOOLS)
        self.assertNotIn("comfy_job_status", remote_security.GATED_REMOTE_TOOLS)
        self.assertNotIn("comfy_job_status", tools.PROJECT_ONLY_TOOLS)

    def test_rejects_bad_prompt_id(self):
        with self.assertRaises(tools.ToolError):
            tools.comfy_job_status({})
        with self.assertRaises(tools.ToolError):
            tools.comfy_job_status({"prompt_id": "../etc/passwd"})
        with self.assertRaises(tools.ToolError):
            tools.comfy_job_status({"prompt_id": "short"})

    def test_complete_history_resolves_outputs_without_mcp(self):
        sleeps = []
        mcp_calls = []

        def fake_urlopen(url, timeout=None):
            self.assertIn("/history/" + self.PID, str(url))
            return _HistResp(self._complete_payload())

        with patch.object(tools.urllib.request, "urlopen", side_effect=fake_urlopen), \
             patch.object(tools, "_sleep", side_effect=lambda s: sleeps.append(s)), \
             patch("mcp_client.call", side_effect=lambda *a, **k: mcp_calls.append(a)):
            raw = tools.comfy_job_status({"prompt_id": self.PID, "timeout_s": 90})
        data = json.loads(raw)
        self.assertEqual("complete", data["state"])
        self.assertEqual(1, len(data["outputs"]))
        self.assertEqual("ComfyUI_00214_.png", data["outputs"][0]["filename"])
        self.assertEqual([], sleeps)
        self.assertEqual([], mcp_calls)

    def test_empty_history_until_timeout_is_pending(self):
        sleeps = []

        def fake_urlopen(url, timeout=None):
            return _HistResp({})

        with patch.object(tools.urllib.request, "urlopen", side_effect=fake_urlopen), \
             patch.object(tools, "_sleep", side_effect=lambda s: sleeps.append(s)):
            raw = tools.comfy_job_status({"prompt_id": self.PID, "timeout_s": 0})
        data = json.loads(raw)
        self.assertEqual("pending", data["state"])
        self.assertTrue(data.get("timeout"))
        self.assertEqual([], data["outputs"])
        self.assertIn("call comfy_job_status again", data["note"])
        self.assertEqual(0, len(sleeps))

    def test_backoff_then_complete(self):
        sleeps = []
        hits = {"n": 0}

        def fake_urlopen(url, timeout=None):
            hits["n"] += 1
            if hits["n"] == 1:
                return _HistResp({})
            return _HistResp(self._complete_payload())

        with patch.object(tools.urllib.request, "urlopen", side_effect=fake_urlopen), \
             patch.object(tools, "_sleep", side_effect=lambda s: sleeps.append(s)):
            raw = tools.comfy_job_status({"prompt_id": self.PID, "timeout_s": 30})
        data = json.loads(raw)
        self.assertEqual("complete", data["state"])
        self.assertEqual([0.5], sleeps)
        self.assertEqual(2, data["polls"])

    def test_parse_video_gifs_key(self):
        payload = {
            self.PID: {
                "outputs": {
                    "9": {"gifs": [{"filename": "clip_00001_.mp4", "subfolder": "video",
                                    "type": "output"}]},
                },
                "status": {"status_str": "success", "completed": True},
            }
        }
        parsed = tools.parse_comfy_history(payload, self.PID)
        self.assertEqual("complete", parsed["state"])
        self.assertEqual("clip_00001_.mp4", parsed["outputs"][0]["filename"])
        self.assertEqual("video", parsed["outputs"][0]["subfolder"])
        self.assertEqual("gifs", parsed["outputs"][0]["media_key"])

    def test_timeout_s_is_capped(self):
        clock = [0.0]

        def mono():
            return clock[0]

        def sleeper(seconds):
            clock[0] += seconds

        with patch.object(tools.urllib.request, "urlopen",
                          return_value=_HistResp({})), \
             patch.object(tools.time, "monotonic", side_effect=mono), \
             patch.object(tools, "_sleep", side_effect=sleeper):
            raw = tools.comfy_job_status({"prompt_id": self.PID, "timeout_s": 9999})
        data = json.loads(raw)
        self.assertEqual(tools.COMFY_JOB_STATUS_TIMEOUT_MAX_S, data["timeout_s"])
        self.assertEqual("pending", data["state"])
        self.assertGreaterEqual(clock[0], tools.COMFY_JOB_STATUS_TIMEOUT_MAX_S)


if __name__ == "__main__":
    unittest.main()
