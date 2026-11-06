#!/usr/bin/env python3
"""Mocked ComfyUI GPU timeshare tests. No live ComfyUI, nvidia-smi, or MCP."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mcp_client  # noqa: E402
import router  # noqa: E402

STANDALONE_PY = (
    r"A:\Users\rhine\ComfyUI-Installs\Rockernow\standalone-env\python.exe"
)
PYTHON312_PY = (
    r"A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe"
)
POWERINFER_PY = r"A:\PowerInferBuild\bin\server.exe"
TOOL_PROMPT = "list the files in the current folder"
CODE_PROMPT = "write a python function that parses JSON"
LOGIC_PROMPT = (
    "Please architect a refactor of the repository and compare "
    "the end-to-end workflow against the current implementation."
)
CPU_ONLY_PIN = "equal-shares-cpu"


class _HttpResp:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ComfyTimeshareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.owner = root / "render_queue_owner.json"
        self.batch = root / "batch_render_queue_owner.json"
        self.image = root / "image_render_owner.json"
        self.addCleanup(self.tmp.cleanup)
        self._env = patch.dict(os.environ, {"EQUAL_SHARES_COMFY_TIMESHARE": "1"})
        self._env.start()
        self.addCleanup(self._env.stop)
        for name, path in (
            ("OWNER", self.owner),
            ("BATCH_RENDER_OWNER", self.batch),
            ("IMAGE_RENDER_OWNER", self.image),
        ):
            p = patch.object(router, name, path)
            p.start()
            self.addCleanup(p.stop)
        owned = root / "gpu_owned_residents.json"
        pressure = root / "media_vram_pressure.json"
        for name, path in (("GPU_OWNED_FILE", owned),
                           ("MEDIA_PRESSURE_FILE", pressure)):
            p = patch.object(router, name, path)
            p.start()
            self.addCleanup(p.stop)
        mcp_client.reset_client()
        self.addCleanup(mcp_client.reset_client)
        self.mcp_calls = []
        self.urlopens = []
        self.box = {"used": 345, "procs": ["python.exe"], "used_after": 120}
        self.resident = []
        self.queue_http = {"queue_running": [], "queue_pending": []}
        self.mcp_queue = {"running": 0, "pending": 0}
        self.clear_result = "VRAM cleared successfully"
        self.clear_error = None
        self.free_http = {}
        self.queue_error = None
        self.farm = False
        self._gate = MagicMock()
        self._pid = patch.object(
            router, "_pid_alive", side_effect=lambda pid: pid == os.getpid())
        self._pid.start()
        self.addCleanup(self._pid.stop)

    def _write_owner(self, path: Path, pid=None, raw=None):
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
            return
        path.write_text(json.dumps({"pid": pid, "purpose": "test"}), encoding="utf-8")

    def _fake_mcp(self, name, arguments=None, timeout=None, *,
                  lock_timeout=None, spawn=True):
        rec = {
            "name": name, "arguments": arguments, "timeout": timeout,
            "lock_timeout": lock_timeout, "spawn": spawn,
        }
        self.mcp_calls.append(rec)
        if spawn:
            raise AssertionError("timeshare MCP must use spawn=False")
        if name == "queue":
            if self.queue_error is not None:
                raise self.queue_error
            return self.mcp_queue
        if name == "clear_vram":
            if self.clear_error is not None:
                raise self.clear_error
            self.box["used"] = self.box["used_after"]
            return self.clear_result
        raise mcp_client.McpError(f"unexpected tool {name}")

    def _fake_urlopen(self, url, data=None, timeout=None, context=None):
        u = url.full_url if hasattr(url, "full_url") else str(url)
        self.urlopens.append((u, timeout))
        if "/free" in u:
            if self.free_http is Exception or isinstance(self.free_http, type):
                raise OSError("free down")
            if isinstance(self.free_http, Exception):
                raise self.free_http
            self.box["used"] = self.box["used_after"]
            return _HttpResp(self.free_http if isinstance(self.free_http, dict) else {})
        if "/queue" in u:
            if self.queue_http is Exception or isinstance(self.queue_http, type):
                raise OSError("queue down")
            if isinstance(self.queue_http, Exception):
                raise self.queue_http
            return _HttpResp(self.queue_http)
        raise AssertionError(f"unexpected urlopen {url}")

    def _gpu_mem(self):
        return self.box["used"], list(self.box["procs"])

    def _tags(self, host):
        if host == router.CPU_HOST:
            return [router.FALLBACK_REASONING_MODEL]
        return [
            router.PRIMARY_REASONING_MODEL,
            router.FALLBACK_REASONING_MODEL,
            router.DEEPSEEK_MODEL,
            router.JOSIEFIED_CODER_MODEL,
            router.GPT_OSS_20B_HERETIC_MODEL,
        ]

    def _ctx(self, **extra):
        patches = dict(
            comfy_listening=patch.object(router, "comfy_listening", return_value=True),
            gpu_memory=patch.object(router, "gpu_memory", side_effect=self._gpu_mem),
            running=patch.object(
                router, "_running_models",
                side_effect=lambda host: list(self.resident)
                if self.resident is not None else None),
            farm=patch.object(router, "_farm_reachable", side_effect=lambda: self.farm),
            up=patch.object(router, "up", return_value=True),
            tags=patch.object(router, "_tags", side_effect=self._tags),
            evict=patch.object(
                router, "evict_gpu_residents",
                return_value={"verified": True, "attempted": [], "reason": "empty"}),
            prepare=patch.object(
                router, "prepare_gpu_model",
                return_value={"verified": True, "attempted": [],
                              "keep_alive_sent": [], "remaining": [],
                              "reason": "ok"}),
            thermal=patch.object(router, "thermal_blocks_gpu", return_value=None),
            pi_backend=patch.object(
                router, "powerinfer_backend_listening", return_value=False),
            pi_proxy=patch.object(
                router, "powerinfer_proxy_listening", return_value=False),
            pi_ready=patch.object(
                router, "powerinfer_ready",
                return_value=(True, "PowerInfer proxy and backend are reachable")),
            mcp=patch.object(mcp_client, "call", side_effect=self._fake_mcp),
            urlopen=patch.object(
                router.urllib.request, "urlopen", side_effect=self._fake_urlopen),
            gate=patch("gpu_gate.request", self._gate),
        )
        patches.update(extra)
        return patches

    def _start(self, **extra):
        started = []
        for p in self._ctx(**extra).values():
            p.start()
            started.append(p)
            self.addCleanup(p.stop)
        return started

    def _clears(self):
        return [c for c in self.mcp_calls if c["name"] == "clear_vram"]

    def _lists(self):
        return [c for c in self.mcp_calls if c["name"] == "queue"]

    def test_live_owner_no_free_busy_stays_true(self):
        self._write_owner(self.owner, os.getpid())
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        self.assertEqual([], self._clears())

    def test_unreadable_owner_not_idle(self):
        self._write_owner(self.owner, raw="{not json")
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())
        idle, why = router._owners_idle_for_timeshare()
        self.assertFalse(idle)
        self.assertIn("unreadable", why)

    def test_malformed_owner_pid_not_idle(self):
        self._write_owner(self.owner, raw=json.dumps({"pid": "nope"}))
        idle, why = router._owners_idle_for_timeshare()
        self.assertFalse(idle)
        self.assertIn("unreadable", why)

    def test_live_batch_owner(self):
        self._write_owner(self.batch, os.getpid())
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())

    def test_live_image_render_owner(self):
        self._write_owner(self.image, os.getpid())
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())

    def test_unreadable_batch_file(self):
        self._write_owner(self.batch, raw="<<<")
        idle, why = router._owners_idle_for_timeshare()
        self.assertFalse(idle)
        self.assertIn("unreadable", why)

    def test_unreadable_image_render_file(self):
        self._write_owner(self.image, raw="<<<")
        idle, why = router._owners_idle_for_timeshare()
        self.assertFalse(idle)
        self.assertIn("unreadable", why)

    def test_urllib_non_empty_no_mcp(self):
        self.mcp_queue = {"running": 0, "pending": 0}
        self.queue_http = {"queue_running": [{"id": 1}], "queue_pending": []}
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())
        self.assertEqual([], self._lists())
        self.assertTrue(any("/queue" in u for u, _t in self.urlopens))
        self.assertTrue(all(t == 1 for u, t in self.urlopens if "/queue" in u))

    def test_urllib_idle_does_not_call_mcp_list(self):
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])
        self.assertEqual([], self._lists())
        self.assertTrue(any("/queue" in u for u, _t in self.urlopens))

    def test_mcp_lock_held_after_urllib_fail_fail_closed(self):
        self.queue_http = OSError("queue down")
        self.queue_error = mcp_client.McpError("MCP client lock busy")
        self.clear_error = mcp_client.McpError("MCP client lock busy")
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        self.assertTrue(any("/queue" in u for u, _t in self.urlopens))
        self.assertTrue(self._lists())
        self.assertEqual(1, self._lists()[0]["timeout"])
        self.assertEqual("cpu_fallback", d.detail["timeshare"]["path"])

    def test_spawn_false_uninitialized_list_urllib_no_handshake(self):
        self.queue_http = OSError("queue down")
        mcp_client.reset_client()
        orig = mcp_client.call

        def tracking_call(name, arguments=None, timeout=None, *,
                          lock_timeout=None, spawn=True):
            self.mcp_calls.append({
                "name": name, "arguments": arguments, "timeout": timeout,
                "lock_timeout": lock_timeout, "spawn": spawn,
            })
            return orig(name, arguments, timeout=timeout,
                        lock_timeout=lock_timeout, spawn=spawn)

        handshake = patch.object(
            mcp_client.McpClient, "_ensure_started",
            side_effect=AssertionError("handshake"))
        getc = patch.object(
            mcp_client, "get_client",
            side_effect=AssertionError("get_client must not spawn"))
        handshake.start()
        getc.start()
        self.addCleanup(handshake.stop)
        self.addCleanup(getc.stop)
        self._start(mcp=patch.object(mcp_client, "call", side_effect=tracking_call))
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        self.assertTrue(self._lists())
        self.assertTrue(all(c["spawn"] is False for c in self.mcp_calls))
        self.assertTrue(any("/queue" in u for u, _t in self.urlopens))
        self.assertFalse(mcp_client.ready())
        self.assertEqual("cpu_fallback", d.detail["timeshare"]["path"])

    def test_both_queue_paths_fail_not_idle(self):
        self.queue_error = mcp_client.McpError("down")
        self.queue_http = OSError("down")
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())

    def test_missing_queue_running_key_not_idle(self):
        self.queue_error = mcp_client.McpError("unreadable")
        self.queue_http = {"queue_pending": []}
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())

    def test_standalone_env_python_still_frees(self):
        self.box["used"] = 2459
        self.box["procs"] = [STANDALONE_PY]
        self.box["used_after"] = 200
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(1, len(self._clears()))

    def test_python312_python_exe_is_not_occupancy_and_frees(self):
        self.box["procs"] = [PYTHON312_PY]
        self.box["used_after"] = 100
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual(1, len(self._clears()))
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])

    def test_bare_python_exe_8188_used_345_still_frees(self):
        self.box["used"] = 345
        self.box["procs"] = ["python.exe"]
        self.box["used_after"] = 100
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual(1, len(self._clears()))
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])

    def test_used_5000_still_calls_free_then_cap(self):
        self.box["used"] = 5000
        self.box["procs"] = ["python.exe"]
        self.box["used_after"] = 200
        self._start()
        d = router.decide("auto")
        self.assertEqual(1, len(self._clears()))
        self.assertFalse(d.gpu_busy)
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])

    def test_nvidia_smi_none_no_free(self):
        self.box["used"] = None
        self.box["procs"] = []
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())

    def test_used_5000_post_free_over_cap_fail_closed(self):
        self.box["used"] = 5000
        self.box["procs"] = ["python.exe"]
        self.box["used_after"] = 5000
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual(1, len(self._clears()))
        self.assertEqual("cpu_fallback", d.detail["timeshare"]["path"])

    def test_free_failed_prose_no_throw_fail_closed(self):
        self.clear_result = "Failed to free VRAM: HTTP 500"
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual(1, len(self._clears()))
        self.assertEqual("cpu", d.tier)

    def test_nvidia_smi_still_2459_after_success_token(self):
        self.box["used"] = 2459
        self.box["used_after"] = 2459
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual(1, len(self._clears()))

    def test_used_345_still_calls_free(self):
        self.box["used"] = 345
        self.box["used_after"] = 345
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual(1, len(self._clears()))

    def test_happy_path_clear_vram_no_bypass_warning(self):
        self._start()
        with self.assertNoLogs("local_agent.router.timeshare", level="WARNING"):
            d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, d.model)
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])
        self.assertEqual(1, len(self._clears()))
        ts = d.detail["timeshare"]
        self.assertNotIn("gpu_gate", ts)
        self.assertEqual(0, self._gate.call_count)
        self.assertIn("owners", ts)
        self.assertIn("queue", ts)
        self.assertIn("occupancy", ts)
        self.assertIn("used_mib", ts["occupancy"])
        self.assertEqual([], ts["occupancy"]["powerinfer_compute"])
        self.assertIn("clear_vram", ts)
        self.assertIn("recheck", ts)

    def test_post_free_recheck_new_owner_cpu_no_ollama_load(self):
        def mcp(name, arguments=None, timeout=None, *, lock_timeout=None, spawn=True):
            rec = self._fake_mcp(
                name, arguments, timeout, lock_timeout=lock_timeout, spawn=spawn)
            if name == "clear_vram":
                self._write_owner(self.owner, os.getpid())
            return rec

        self._start(mcp=patch.object(mcp_client, "call", side_effect=mcp))
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        self.assertNotEqual(router.PRIMARY_REASONING_MODEL, d.model)
        self.assertEqual("cpu_fallback", d.detail["timeshare"]["path"])

    def test_post_free_recheck_nonempty_queue_cpu(self):
        def mcp(name, arguments=None, timeout=None, *, lock_timeout=None, spawn=True):
            rec = self._fake_mcp(
                name, arguments, timeout, lock_timeout=lock_timeout, spawn=spawn)
            if name == "clear_vram":
                self.mcp_queue = {"running": 1, "pending": 0}
                self.queue_http = {"queue_running": [{"id": 1}], "queue_pending": []}
            return rec

        self._start(mcp=patch.object(mcp_client, "call", side_effect=mcp))
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)

    def test_hop_n_resident_14b_no_free_does_recheck(self):
        router.note_gpu_owned(router.PRIMARY_REASONING_MODEL)
        self.resident = [router.PRIMARY_REASONING_MODEL]
        self.box["used"] = 9000
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual([], self._clears())
        self.assertEqual("already_claimed", d.detail["timeshare"]["path"])
        self.assertIn("recheck", d.detail["timeshare"])
        self.assertEqual("gpu", d.tier)

    def test_third_party_gpu_models_tag_is_not_already_claimed(self):
        """comfy-pilot load of Huihui 8B must not skip /free as already_claimed."""
        self.resident = [router.FALLBACK_REASONING_MODEL]
        self.box["used"] = 7623
        self.box["used_after"] = 7623
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertNotEqual("already_claimed", d.detail["timeshare"].get("path"))
        self.assertEqual("cpu_fallback", d.detail["timeshare"]["path"])
        self.assertEqual("cpu", d.tier)

    def test_failed_claim_still_hits_evict(self):
        self._write_owner(self.owner, os.getpid())
        evict = patch.object(
            router, "evict_gpu_residents",
            return_value={"verified": True, "attempted": [], "reason": "empty"})
        self._start(evict=evict)
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        router.evict_gpu_residents.assert_called()

    def test_busy_false_before_inventory_capability_gpu(self):
        tagged = []

        def tags(host):
            tagged.append(host)
            return self._tags(host)

        self._start(tags=patch.object(router, "_tags", side_effect=tags))
        d = router.decide("auto", prompt=CODE_PROMPT)
        self.assertFalse(d.gpu_busy)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(router.JOSIEFIED_CODER_MODEL, d.model)
        self.assertIn(router.GPU_HOST, tagged)
        router.prepare_gpu_model.assert_called()

    def test_ensure_gpu_evicted_false_never_free_or_mcp(self):
        self._start()
        d = router.decide("auto", ensure_gpu_evicted=False)
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self.mcp_calls)
        self.assertEqual([], self._clears())

    def test_kill_switch_zero_leaves_busy(self):
        self._env.stop()
        env = patch.dict(os.environ, {"EQUAL_SHARES_COMFY_TIMESHARE": "0"})
        env.start()
        self.addCleanup(env.stop)
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())

    def test_prefer_cpu_never_enters_hook(self):
        self._start()
        d = router.decide("cpu")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        self.assertEqual([], self._clears())
        self.assertNotIn("timeshare", d.detail)

    def test_farm_reachable_tool_prompt_no_clear_busy_true(self):
        self.farm = True
        self._start()
        d = router.decide("auto", prompt=TOOL_PROMPT)
        self.assertEqual("farm", d.tier)
        self.assertTrue(d.gpu_busy)
        self.assertEqual("farm_skip", d.detail["timeshare"]["path"])
        self.assertEqual([], self._clears())

    def test_huihui_auto_powerinfer_tcp_up_not_already_claimed(self):
        self._start(pi_backend=patch.object(
            router, "powerinfer_backend_listening", return_value=True))
        d = router.decide("auto")
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])
        self.assertEqual(1, len(self._clears()))
        self.assertEqual([], d.detail["timeshare"]["occupancy"]["powerinfer_compute"])

    def test_powerinfer_pin_2459_no_pi_compute_must_free(self):
        self.box["used"] = 2459
        self.box["used_after"] = 200
        self._start()
        d = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual(1, len(self._clears()))
        self.assertNotEqual("already_claimed", d.detail["timeshare"].get("path"))
        self.assertFalse(d.gpu_busy)
        self.assertEqual("powerinfer", d.backend)

    def test_powerinfer_pin_pi_compute_already_claimed_no_free(self):
        self.box["used"] = 2459
        self.box["procs"] = [POWERINFER_PY]
        self._start()
        d = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual([], self._clears())
        self.assertEqual("already_claimed", d.detail["timeshare"]["path"])
        self.assertFalse(d.gpu_busy)

    def test_mcp_jobs_arrays_alone_are_not_idle_proof(self):
        self.mcp_queue = {"running_jobs": [], "pending_jobs": []}
        self.queue_http = {"queue_running": [{"id": 1}], "queue_pending": []}
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())
        self.assertTrue(self.urlopens)
        self.assertEqual([], self._lists())

    def test_host_gpu_empty_prompt_true(self):
        self.assertTrue(router._timeshare_would_load_host_gpu("auto", None, ""))

    def test_host_gpu_qwythos_pin_false(self):
        cap = router.classify_capability("hello", model=router.QWYTHOS_MODEL)
        self.assertEqual(router.CAP_TOOL, cap)
        self.assertFalse(
            router._timeshare_would_load_host_gpu("auto", router.QWYTHOS_MODEL, cap))
        self._start()
        d = router.decide("auto", model=router.QWYTHOS_MODEL)
        self.assertEqual([], self._clears())
        self.assertTrue(d.gpu_busy)

    def test_host_gpu_cpu_only_pin_false(self):
        self.assertFalse(
            router._timeshare_would_load_host_gpu("auto", CPU_ONLY_PIN, ""))

    def test_host_gpu_fallback_pin_true(self):
        self.assertTrue(router._timeshare_would_load_host_gpu(
            "auto", router.FALLBACK_REASONING_MODEL, ""))

    def test_host_gpu_logic_plus_cpu_only_pin_false(self):
        cap = router.classify_capability(LOGIC_PROMPT, model=CPU_ONLY_PIN)
        self.assertEqual(router.CAP_LOGIC, cap)
        self.assertFalse(
            router._timeshare_would_load_host_gpu("auto", CPU_ONLY_PIN, cap))
        self._start()
        d = router.decide("auto", model=CPU_ONLY_PIN, prompt=LOGIC_PROMPT)
        self.assertEqual([], self._clears())
        self.assertTrue(d.gpu_busy)

    def test_host_gpu_primary_pin_code_prompt_frees(self):
        cap = router.classify_capability(
            CODE_PROMPT, model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual(router.CAP_CODE, cap)
        self.assertTrue(router._timeshare_would_load_host_gpu(
            "auto", router.PRIMARY_REASONING_MODEL, cap))
        self._start()
        d = router.decide(
            "auto", model=router.PRIMARY_REASONING_MODEL, prompt=CODE_PROMPT)
        self.assertEqual(1, len(self._clears()))
        self.assertFalse(d.gpu_busy)

    def test_host_gpu_fallback_pin_logic_prompt_frees(self):
        cap = router.classify_capability(
            LOGIC_PROMPT, model=router.FALLBACK_REASONING_MODEL)
        self.assertEqual(router.CAP_LOGIC, cap)
        self.assertTrue(router._timeshare_would_load_host_gpu(
            "auto", router.FALLBACK_REASONING_MODEL, cap))
        self._start()
        d = router.decide(
            "auto", model=router.FALLBACK_REASONING_MODEL, prompt=LOGIC_PROMPT)
        self.assertEqual(1, len(self._clears()))
        self.assertFalse(d.gpu_busy)

    def test_mcp_running_list_unreadable_after_urllib_fail_not_idle(self):
        self.mcp_queue = {"running": [], "pending": 0}
        self.queue_http = OSError("queue down")
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())
        self.assertTrue(self.urlopens)
        self.assertTrue(self._lists())
        self.assertEqual("unreadable", d.detail["timeshare"]["queue"].get("mcp"))

    def test_mcp_running_false_unreadable_after_urllib_fail_not_idle(self):
        self.mcp_queue = {"running": False, "pending": 0}
        self.queue_http = OSError("queue down")
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())
        self.assertTrue(self.urlopens)
        self.assertTrue(self._lists())

    def test_huihui_names_only_server_exe_8080_no_free(self):
        self.box["procs"] = ["server.exe"]
        self._start(pi_backend=patch.object(
            router, "powerinfer_backend_listening", return_value=True))
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual([], self._clears())
        self.assertEqual(
            ["server.exe"], d.detail["timeshare"]["occupancy"]["powerinfer_compute"])

    def test_names_only_server_exe_without_backend_is_not_occupancy(self):
        self.box["procs"] = ["server.exe"]
        self.box["used_after"] = 100
        self._start(pi_backend=patch.object(
            router, "powerinfer_backend_listening", return_value=False))
        d = router.decide("auto")
        self.assertEqual(1, len(self._clears()))
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])
        self.assertEqual(
            [], d.detail["timeshare"]["occupancy"]["powerinfer_compute"])

    def test_powerinfer_pin_names_only_server_exe_already_claimed(self):
        self.box["used"] = 2459
        self.box["procs"] = ["server.exe"]
        self._start(pi_backend=patch.object(
            router, "powerinfer_backend_listening", return_value=True))
        d = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual([], self._clears())
        self.assertEqual("already_claimed", d.detail["timeshare"]["path"])
        self.assertFalse(d.gpu_busy)
        self.assertEqual(
            ["server.exe"], d.detail["timeshare"]["occupancy"]["powerinfer_compute"])

    def test_mcp_not_started_falls_back_to_http_free(self):
        """When MCP was never started, timeshare uses ComfyUI HTTP /free."""
        self.clear_error = mcp_client.McpError("MCP client is not started")
        self.box["used"] = 2459
        self.box["used_after"] = 345
        self._start()
        d = router.decide("auto")
        self.assertFalse(d.gpu_busy)
        self.assertEqual("gpu", d.tier)
        self.assertEqual("clear_vram", d.detail["timeshare"]["path"])
        self.assertTrue(any("/free" in u for u, _t in self.urlopens))
        self.assertEqual(1, len(self._clears()))
        cv = d.detail["timeshare"]["clear_vram"]
        self.assertTrue(cv["ok"])
        self.assertIn("HTTP /free", cv["detail"])

    def test_mcp_not_started_and_http_free_fails_cpu_fallback(self):
        self.clear_error = mcp_client.McpError("MCP client is not started")
        self.free_http = OSError("free down")
        self.box["used"] = 2459
        self._start()
        d = router.decide("auto")
        self.assertTrue(d.gpu_busy)
        self.assertEqual("cpu", d.tier)
        self.assertEqual("cpu_fallback", d.detail["timeshare"]["path"])
        self.assertIn(
            "MCP client is not started",
            d.detail["timeshare"]["clear_vram"]["detail"])


if __name__ == "__main__":
    unittest.main()
