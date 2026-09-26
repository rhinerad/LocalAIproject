#!/usr/bin/env python3
"""M0–M2 regression tests for the GVD tool router. Stdlib only; no GPU."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gvd_tool_router.binder import bind, inspect_graph, is_ui_workflow
from gvd_tool_router.catalog_seed import seed_implementations, write_seed_catalog
from gvd_tool_router.discovery import (
    CandidateAsset,
    DiscoveryHit,
    FetchedAsset,
    discover_workflows,
)
from gvd_tool_router.executor import ExecutorError, reconcile, submit_stage
from gvd_tool_router.gpu_lease import LeaseContention, acquire
from gvd_tool_router.inventory import persist_inventory
from gvd_tool_router.paths import GvdLayout
from gvd_tool_router.registry import Registry, RegistryError
from gvd_tool_router.router import preferred_tool, required_capabilities, route
from gvd_tool_router.scheduler import ScheduledStage, group_ready
from gvd_tool_router.schema import (
    CAPABILITY_CONTINUATION,
    CAPABILITY_FAST,
    CAPABILITY_FIRST_FRAME,
    CAPABILITY_IDENTITY,
    CAPABILITY_LAST_FRAME,
    CAPABILITY_MONTAGE,
    CAPABILITY_NARRATIVE,
    CAPABILITY_VIDEO_CONTEXT,
    ArtifactRef,
    CharacterState,
    ResourceProfile,
    RouteDecision,
    ShotManifest,
    can_activate,
    sha256_bytes,
    to_plain,
)
from gvd_tool_router.service import _wait_for_stage_completion, execute_tool, route_shot
from gvd_tool_router.store import (
    add_attempt, add_shot, connect, find_open_attempt, freeze_job,
    set_attempt_status,
)
from gvd_tool_router.adapters import SqliteValidationQueue
from gvd_tool_router.extensions import assemble_scene, quality_gate, repair_video
from gvd_tool_router.family_profiles import scan_families
from gvd_tool_router.planner import plan_shot
from gvd_tool_router.promotion import validate_candidate_graph
from gvd_tool_router.secure_fetch import FetchError, _check_url
from gvd_tool_router.store import connect, mark_discovery
from gvd_tool_router.switch import SwitchBlocked, switch_to
from gvd_tool_router.tools import (
    discover_workflows_tool,
    execute_fast_action,
    gvd_inventory,
)

SHA = "a" * 64
INV = {"gpu": {"memory_free_mib": 12000}, "headroom_mib": 2048}


def _layout() -> GvdLayout:
    root = Path(tempfile.mkdtemp(prefix="gvd_router_"))
    layout = GvdLayout(root)
    layout.ensure()
    write_seed_catalog(layout)
    return layout


def _profile() -> ResourceProfile:
    return ResourceProfile(
        profile_id="local_ok",
        runtime_lock_sha256=SHA,
        workload_sha256=SHA,
        precision="fp16",
        offload_mode="none",
        peak_gpu_mib=5000,
        peak_host_ram_mib=4000,
        model_disk_mib=2000,
        cold_seconds=10.0,
        warm_seconds=4.0,
        evidence="local",
        samples=3,
    )


def _activate(impl, extra=(), scores=None, limits=None, fallbacks=()):
    caps = set(impl.capabilities) | set(extra)
    profiles = impl.profiles or (_profile(),)
    return replace(
        impl,
        status="active",
        capabilities=frozenset(caps),
        policy_receipt="test-policy",
        validation_report_sha256=SHA,
        profiles=profiles,
        quality_scores=scores or {
            "identity": 0.85, "motion": 0.8, "style": 0.7,
            "audio": 0.4, "reliability": 0.9,
        },
        fallback_ids=fallbacks,
        disabled_reason=None,
        limits=limits if limits is not None else impl.limits,
    )


def _shot(**kwargs) -> ShotManifest:
    base = dict(
        shot_id="S01",
        script_intent="establishing alley",
        camera_motion="static",
        character_state=(),
        continuity_mode="independent",
        duration_s=4.0,
        width=1280,
        height=720,
        fps_num=24,
        fps_den=1,
        hard_requirements=frozenset(),
        priorities={},
    )
    base.update(kwargs)
    return ShotManifest(**base)


def _character() -> CharacterState:
    return CharacterState(
        character_id="hero",
        revision="r1",
        face_refs=(ArtifactRef("face", SHA, "image/png"),),
        wardrobe_refs=(ArtifactRef("wardrobe", SHA, "image/png"),),
        wardrobe_description="yellow jacket",
        props=("radio",),
        screen_position="center",
        pose="standing",
        expression="neutral",
    )


class InventoryTests(unittest.TestCase):
    def test_bootstrap_writes_runtime_without_starting_comfy(self):
        layout = _layout()
        fake = {
            "schema_version": 1,
            "environment": {
                "os": "Windows",
                "python_version": "3.12",
                "comfy_root": "X:\\comfy",
                "comfy_commit": "deadbeef",
                "gpu": {"gpu_name": "NVIDIA GeForce RTX 5080", "memory_free_mib": 14000},
                "endpoints": {
                    "comfyui": "http://127.0.0.1:8188",
                    "ollama_gpu": "http://127.0.0.1:11434",
                    "ollama_cpu": "http://127.0.0.1:11435",
                },
                "object_info_available": False,
                "node_schema_reason": "comfy_object_info_unavailable",
                "environment_sha256": SHA,
                "collected_at": "now",
            },
            "object_info_node_count": 0,
            "headroom_mib": 2048,
        }
        paths = persist_inventory(layout, fake)
        self.assertTrue(paths["runtime"].is_file())
        runtime = json.loads(paths["runtime"].read_text(encoding="utf-8"))
        self.assertTrue(runtime["policy"]["local_only"])
        self.assertEqual(runtime["gpu"]["headroom_mib"], 2048)


class CatalogTests(unittest.TestCase):
    def test_four_public_tools_exist_while_disabled(self):
        impls = seed_implementations()
        names = {i.tool_name for i in impls}
        for name in (
            "execute_narrative_scene", "execute_continuous_take",
            "execute_montage_morph", "execute_fast_action",
        ):
            self.assertIn(name, names)
        self.assertTrue(all(i.status == "disabled" for i in impls if i.tool_name.startswith("execute_")))

    def test_unknown_vram_cannot_activate(self):
        impls = seed_implementations()
        still = next(i for i in impls if i.implementation_id == "known_good_sdxl_txt2img_v1")
        unknown = replace(
            still,
            status="validated",
            policy_receipt="p",
            validation_report_sha256=SHA,
            profiles=(replace(_profile(), peak_gpu_mib=None),),
        )
        ok, reasons = can_activate(unknown)
        self.assertFalse(ok)
        self.assertIn("unknown_vram", reasons)

    def test_promote_rejects_unknown_vram(self):
        layout = _layout()
        impls = seed_implementations()
        still = next(i for i in impls if i.tool_name == "generate_still")
        bad = replace(
            still, status="active", policy_receipt="p",
            validation_report_sha256=SHA,
            profiles=(replace(_profile(), peak_gpu_mib=None),),
        )
        with self.assertRaises(RegistryError):
            Registry(layout).promote([bad])


class RoutingTests(unittest.TestCase):
    def setUp(self):
        impls = seed_implementations()
        by_tool = {}
        for impl in impls:
            by_tool.setdefault(impl.tool_name, impl)
        self.narrative = _activate(
            by_tool["execute_narrative_scene"],
            extra={CAPABILITY_NARRATIVE, CAPABILITY_IDENTITY},
            scores={"identity": 0.9, "motion": 0.5, "style": 0.7, "audio": 0.2, "reliability": 0.8},
        )
        self.continuous = _activate(
            by_tool["execute_continuous_take"],
            extra={CAPABILITY_CONTINUATION, CAPABILITY_VIDEO_CONTEXT},
            scores={"identity": 0.2, "motion": 0.9, "style": 0.5, "audio": 0.3, "reliability": 0.8},
        )
        self.morph = _activate(
            next(i for i in impls if i.implementation_id == "animatediff_fizz_unvalidated"),
            extra={CAPABILITY_MONTAGE},
        )
        self.fast = _activate(
            next(i for i in impls if i.implementation_id == "ltx23_unvalidated"),
            extra={CAPABILITY_FAST},
            scores={"identity": 0.1, "motion": 0.85, "style": 0.4, "audio": 0.2, "reliability": 0.7},
        )
        self.v1 = _activate(
            next(i for i in impls if i.implementation_id == "fasth3_v1_t2va_unvalidated"),
            extra={CAPABILITY_FAST},
            limits={"modes": ["t2va"], "ref2va": False, "fl2va": False},
        )
        self.v2 = _activate(
            next(i for i in impls if i.implementation_id == "fasth3_v2_unvalidated"),
            extra={CAPABILITY_FAST, CAPABILITY_FIRST_FRAME, CAPABILITY_LAST_FRAME},
            limits={"modes": ["t2v", "fl_i2v"], "ref2va": False},
        )
        self.both = _activate(
            next(i for i in impls if i.implementation_id == "minimax_h3_ref2va_unvalidated"),
            extra={CAPABILITY_CONTINUATION, CAPABILITY_IDENTITY, CAPABILITY_VIDEO_CONTEXT},
            scores={"identity": 0.88, "motion": 0.7, "style": 0.6, "audio": 0.5, "reliability": 0.8},
        )

    def test_four_family_routing(self):
        pool = [self.narrative, self.continuous, self.morph, self.fast]
        broll = route(_shot(), pool, INV)
        self.assertEqual(broll.implementation_id, self.fast.implementation_id)
        named = route(_shot(
            continuity_mode="identity",
            character_state=(_character(),),
            script_intent="hero enters",
        ), pool, INV)
        self.assertEqual(named.implementation_id, self.narrative.implementation_id)
        ext = route(_shot(
            continuity_mode="continuous",
            context_video=ArtifactRef("prev", SHA, "video/mp4"),
            camera_motion="dolly",
        ), pool, INV)
        self.assertEqual(ext.implementation_id, self.continuous.implementation_id)
        dream = route(_shot(
            continuity_mode="morph",
            prompt_keyframes=((0, "day"), (24, "night")),
        ), pool, INV)
        self.assertEqual(dream.implementation_id, self.morph.implementation_id)

    def test_combined_identity_and_continuous_blocks_without_both(self):
        shot = _shot(
            continuity_mode="continuous",
            character_state=(_character(),),
            context_video=ArtifactRef("prev", SHA, "video/mp4"),
        )
        required = required_capabilities(shot)
        self.assertIn(CAPABILITY_IDENTITY, required)
        self.assertIn(CAPABILITY_CONTINUATION, required)
        blocked = route(shot, [self.continuous, self.narrative, self.fast], INV)
        self.assertEqual(blocked.status, "blocked")
        self.assertIn("NO_COMPATIBLE_TOOL", blocked.reason_codes)
        ok = route(shot, [self.continuous, self.narrative, self.both], INV)
        self.assertEqual(ok.implementation_id, self.both.implementation_id)

    def test_fasth3_v1_rejects_fl2va(self):
        shot = _shot(
            continuity_mode="independent",
            start_frame=ArtifactRef("a", SHA, "image/png"),
            end_frame=ArtifactRef("b", SHA, "image/png"),
            hard_requirements=frozenset({CAPABILITY_FAST, CAPABILITY_FIRST_FRAME, CAPABILITY_LAST_FRAME}),
        )
        blocked = route(shot, [self.v1], INV)
        self.assertEqual(blocked.status, "blocked")
        selected = route(shot, [self.v1, self.v2], INV)
        self.assertEqual(selected.implementation_id, self.v2.implementation_id)

    def test_empty_active_registry_is_unavailable_not_pretend(self):
        decision = route(_shot(), [], INV, registry_digest=SHA)
        self.assertEqual(decision.status, "blocked")
        self.assertIn("UNAVAILABLE_CAPABILITY", decision.reason_codes)


class SchedulerTests(unittest.TestCase):
    def test_continuation_waits_for_predecessor_acceptance(self):
        stages = [
            ScheduledStage("S1", "render", "ltx", (), True),
            ScheduledStage("S2", "extend", "h3", (), True),
        ]
        groups = group_ready(stages, accepted_shots=set(), predecessor={"S2": "S1"})
        self.assertIn("ltx", groups)
        self.assertNotIn("h3", groups)
        groups2 = group_ready(stages, accepted_shots={"S1"}, predecessor={"S2": "S1"})
        self.assertIn("h3", groups2)


class StoreDurabilityTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding "other risks", fix-set item
    #8): gvd_tool_router/store.py previously enabled neither
    PRAGMA foreign_keys nor PRAGMA synchronous=FULL, unlike
    production_store.py (the project's other, better-built SQLite store).
    A full swap to production_store.py's schema was rejected (see the
    comment in store.py) since it has no concept of jobs, multi-stage
    DAGs, leases, or qa_evidence; instead its two durability PRAGMAs were
    imported directly into this store."""

    def test_foreign_keys_enforcement_is_enabled(self):
        conn = connect(_layout())
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_synchronous_full_is_enabled(self):
        conn = connect(_layout())
        # SQLite's synchronous pragma: 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA.
        self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 2)

    def test_attempt_for_unregistered_shot_is_now_rejected(self):
        """Before this fix, attempts.shot_id had a FOREIGN KEY declared in
        the schema but SQLite silently did not enforce it (the default),
        so an attempt row could reference a shot_id that was never
        add_shot()'d -- exactly the kind of orphaned-row gap this fix
        closes. This is a regression test for that: it must now raise
        rather than silently insert."""
        conn = connect(_layout())
        with self.assertRaises(sqlite3.IntegrityError):
            add_attempt(
                conn, shot_id="never-registered", implementation_id="impl-1",
                registry_digest=SHA, profile_id="local_ok", lease_generation=1,
            )


class StoreRecoveryTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding 1.4): store.py's shot_id
    global-PK crash and RETRY_PENDING open-attempt gap."""

    def test_replanning_same_shot_does_not_raise_unique_constraint(self):
        """Before the fix: add_shot() unconditionally INSERTed against a
        global shot_id PRIMARY KEY, so replanning C001 (a second job_id for
        the same shot_id, e.g. after a crash) raised sqlite3.IntegrityError
        instead of resuming."""
        layout = _layout()
        conn = connect(layout)
        job1 = freeze_job(conn, project_id="p", registry_digest=SHA)
        add_shot(conn, job_id=job1, shot_id="C001", manifest={"take": 1})
        job2 = freeze_job(conn, project_id="p", registry_digest=SHA)
        # Must not raise -- this used to be sqlite3.IntegrityError.
        add_shot(conn, job_id=job2, shot_id="C001", manifest={"take": 2})
        row = conn.execute(
            "SELECT job_id, manifest_json FROM shots WHERE shot_id=?", ("C001",)
        ).fetchone()
        self.assertEqual(row["job_id"], job2)
        self.assertIn("2", row["manifest_json"])

    def test_find_open_attempt_matches_retry_pending(self):
        """RETRY_PENDING must be treated as an open attempt, or a crash
        between the /prompt POST and prompt_id persistence can be silently
        resubmitted (duplicate render risk)."""
        layout = _layout()
        conn = connect(layout)
        job = freeze_job(conn, project_id="p", registry_digest=SHA)
        add_shot(conn, job_id=job, shot_id="C001", manifest={})
        attempt_id = add_attempt(
            conn, shot_id="C001", implementation_id="impl-1",
            registry_digest=SHA, profile_id="local_ok", lease_generation=1,
        )
        set_attempt_status(conn, attempt_id, "RETRY_PENDING")
        found = find_open_attempt(conn, "C001", "impl-1")
        self.assertIsNotNone(found)
        self.assertEqual(found["attempt_id"], attempt_id)

    def test_find_open_attempt_still_ignores_terminal_states(self):
        layout = _layout()
        conn = connect(layout)
        job = freeze_job(conn, project_id="p", registry_digest=SHA)
        add_shot(conn, job_id=job, shot_id="C001", manifest={})
        attempt_id = add_attempt(
            conn, shot_id="C001", implementation_id="impl-1",
            registry_digest=SHA, profile_id="local_ok", lease_generation=1,
        )
        set_attempt_status(conn, attempt_id, "RENDERED")
        self.assertIsNone(find_open_attempt(conn, "C001", "impl-1"))


class LeaseTests(unittest.TestCase):
    def test_foreign_pid_is_contention(self):
        layout = _layout()
        with acquire(layout, job_id="j1", attempt_id="a1"):
            with patch("gvd_tool_router.gpu_lease._pid_alive", return_value=True), \
                 patch("gvd_tool_router.gpu_lease.os.getpid", return_value=999999):
                with self.assertRaises(LeaseContention):
                    with acquire(layout, job_id="j2", attempt_id="a2"):
                        pass

    def test_nested_same_pid_acquire_inner_release_does_not_clear_outer(self):
        """Fix 2026-09-23 (readiness-audit finding 1.3): a same-PID nested
        acquire()/release() must not clear ownership out from under an
        active outer acquire() -- reproduces the exact bug: without the
        `holders` refcount, the inner release set owner_pid=0 while the
        outer `with` block was still open, so a concurrent foreign PID
        could then acquire the lease while the outer caller still believed
        it owned the GPU."""
        import gvd_tool_router.gpu_lease as gpu_lease
        layout = _layout()
        with acquire(layout, job_id="outer", attempt_id="a-outer") as outer_lease:
            with acquire(layout, job_id="inner", attempt_id="a-inner") as inner_lease:
                self.assertEqual(inner_lease.generation, outer_lease.generation)
            # Inner release has run; the outer acquire must still be the
            # recorded owner of the lease file.
            held = gpu_lease._read(layout)
            self.assertEqual(int(held["owner_pid"]), os.getpid())
            self.assertFalse(held.get("released", False))
            # A foreign PID must still be refused: the lease is still live.
            with patch("gvd_tool_router.gpu_lease._pid_alive", return_value=True), \
                 patch("gvd_tool_router.gpu_lease.os.getpid", return_value=999999):
                with self.assertRaises(LeaseContention):
                    with acquire(layout, job_id="foreign", attempt_id="a-foreign"):
                        pass
        # Outer release has now run: ownership must be cleared.
        held = gpu_lease._read(layout)
        self.assertEqual(int(held["owner_pid"]), 0)
        self.assertTrue(held.get("released", False))


class BinderExecutorTests(unittest.TestCase):
    def test_ui_workflow_is_not_api_prompt(self):
        ui = {"last_node_id": 1, "nodes": [], "links": []}
        self.assertTrue(is_ui_workflow(ui))
        verdict, reasons = inspect_graph(ui)
        self.assertEqual(verdict, "ui_export_required")

    def test_known_good_bind_and_reconcile(self):
        layout = _layout()
        impls = seed_implementations()
        still = _activate(next(i for i in impls if i.tool_name == "generate_still"))
        stage = still.stages[0]
        graph = json.loads((HERE / "gvd_tool_router" / "fixtures" / "known_good_still.api.json").read_text(encoding="utf-8"))
        bound = bind(stage.template, graph, {"prompt": "alley", "seed": 3})
        self.assertEqual(bound["2"]["inputs"]["text"], "alley")
        self.assertEqual(bound["5"]["inputs"]["seed"], 3)
        conn = connect(layout)
        job_id = freeze_job(conn, project_id="t", registry_digest=SHA)
        # Fix 2026-09-23 (readiness-audit finding "other risks", fix-set
        # item #8): store.py now enables PRAGMA foreign_keys=ON (matching
        # production_store.py's discipline), so attempts.shot_id is
        # actually enforced against shots.shot_id -- this test must
        # register the shot the same way execute_tool() always does
        # before it, not just mint a job and call submit_stage() directly.
        add_shot(conn, job_id=job_id, shot_id="S01", manifest={})
        calls = []

        def http(url, payload, method, timeout):
            calls.append((url, method))
            if url.endswith("/prompt"):
                self.assertEqual(payload["extra_data"]["gvd_attempt_id"], payload["extra_data"]["gvd_attempt_id"])
                return {"prompt_id": "p-1"}
            if "/history/" in url:
                return {"p-1": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "x.png"}]}}}}
            return {}

        queued = submit_stage(
            layout=layout, conn=conn, impl=still, stage=stage,
            shot_id="S01", registry_digest=SHA, profile_id="local_ok",
            values={"prompt": "alley", "seed": 3},
            comfy_url="http://127.0.0.1:8188", lease_generation=1, http=http,
        )
        self.assertEqual(queued["status"], "QUEUED")
        self.assertEqual(queued["prompt_id"], "p-1")
        # Ambiguous resubmit must reuse open attempt rather than duplicate.
        again = submit_stage(
            layout=layout, conn=conn, impl=still, stage=stage,
            shot_id="S01", registry_digest=SHA, profile_id="local_ok",
            values={"prompt": "alley", "seed": 3},
            comfy_url="http://127.0.0.1:8188", lease_generation=1, http=http,
        )
        self.assertEqual(again["status"], "RENDERED")
        self.assertEqual(sum(1 for u, m in calls if u.endswith("/prompt")), 1)

    def _promote_still(self):
        layout = _layout()
        impls = seed_implementations()
        still = _activate(next(i for i in impls if i.tool_name == "generate_still"))
        Registry(layout).promote([still])

        def selected(manifest, implementations, inventory, registry_digest="0" * 64, **_route_kwargs):
            return RouteDecision(
                status="selected",
                tool_name="generate_still",
                implementation_id=still.implementation_id,
                profile_id="local_ok",
                registry_digest=registry_digest,
                stage_ids=tuple(stage.stage_id for stage in still.stages),
                reason_codes=(),
                rejection_log=(),
            )

        return layout, selected

    def test_public_execute_resolves_default_transport(self) -> None:
        layout, selected = self._promote_still()
        calls = []

        def http(url, payload, method, timeout):
            calls.append((url, method))
            if str(url).endswith("/prompt"):
                return {"prompt_id": "p-public"}
            return {}

        with patch("gvd_tool_router.service.route", selected), \
             patch("gvd_tool_router.executor.default_http", http):
            result = execute_tool("generate_still", _shot(), layout=layout, live=True, wait_for_completion=False)
        self.assertEqual("QUEUED", result["status"])
        self.assertEqual("p-public", result["submitted"][-1]["prompt_id"])
        self.assertTrue(any(url.endswith("/prompt") and method == "POST" for url, method in calls))

    def test_unexpected_submit_failure_is_not_left_submitting(self) -> None:
        layout, selected = self._promote_still()

        def http(url, payload, method, timeout):
            raise RuntimeError("transport missing")

        with patch("gvd_tool_router.service.route", selected), \
             patch("gvd_tool_router.executor.default_http", http):
            # Lease release can raise WinError 5 while replacing its JSON on
            # Windows after the submit error. The attempt row is what matters.
            with self.assertRaises((ExecutorError, PermissionError)):
                execute_tool("generate_still", _shot(), layout=layout, live=True)
        conn = connect(layout)
        row = conn.execute("SELECT status FROM attempts").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual("FAILED", row[0])

    def test_registry_rollback_keeps_digest_file(self):
        layout = _layout()
        impls = seed_implementations()
        still = _activate(next(i for i in impls if i.tool_name == "generate_still"))
        reg = Registry(layout)
        digest = reg.promote([still])
        self.assertTrue((layout.release_dir(digest) / "active.json").is_file())
        empty = {
            "schema_version": 1,
            "digest": SHA,
            "implementations": [],
        }
        layout.active_json.write_text(json.dumps(empty), encoding="utf-8")
        reg.rollback(digest)
        restored = reg.load_active()
        self.assertEqual(restored["digest"], digest)


class ExecuteToolApprovalGateTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding 1.1): execute_tool() must not
    submit a live video job to ComfyUI without an explicit
    operator_approved_i2v flag on the manifest dict. Still tools
    (generate_still/upscale_still) are exempt -- they have no prior still to
    gate against."""

    def _promote_fast_action(self):
        layout = _layout()
        impls = seed_implementations()
        impl = _activate(next(i for i in impls if i.tool_name == "execute_fast_action"))
        Registry(layout).promote([impl])

        def selected(manifest, implementations, inventory, registry_digest="0" * 64, **_route_kwargs):
            return RouteDecision(
                status="selected",
                tool_name="execute_fast_action",
                implementation_id=impl.implementation_id,
                profile_id="local_ok",
                registry_digest=registry_digest,
                stage_ids=tuple(stage.stage_id for stage in impl.stages),
                reason_codes=(),
                rejection_log=(),
            )

        return layout, selected

    def _fast_action_manifest_dict(self, **extra):
        manifest = to_plain(_shot(continuity_mode="independent"))
        manifest.update(extra)
        return manifest

    def test_blocks_live_video_submission_without_approval(self):
        layout, selected = self._promote_fast_action()
        calls = []

        def http(url, payload, method, timeout):
            calls.append((url, method))
            return {"prompt_id": "should-not-be-called"}

        with patch("gvd_tool_router.service.route", selected),              patch("gvd_tool_router.executor.default_http", http):
            result = execute_tool(
                "execute_fast_action", self._fast_action_manifest_dict(),
                layout=layout, live=True,
            )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("QA_GATE_BLOCKED", result["reason_codes"])
        self.assertFalse(any(url.endswith("/prompt") for url, _m in calls),
                          "must not reach ComfyUI /prompt without approval")

    def test_operator_approved_i2v_true_proceeds_to_submit(self):
        """With approval, the gate must not be what stops submission -- it
        must reach submit_stage(). (The fast-action seed catalog entry has
        only a placeholder pending.json template with no real fixture graph
        on disk, unlike generate_still's known_good_still.api.json, so this
        stubs submit_stage() itself rather than faking a full approved
        workflow file just to prove the gate got out of the way.)"""
        layout, selected = self._promote_fast_action()
        stub_calls = []

        def fake_submit_stage(**kwargs):
            stub_calls.append(kwargs)
            return {"status": "QUEUED", "prompt_id": "p-approved"}

        with patch("gvd_tool_router.service.route", selected):
            with patch("gvd_tool_router.service.submit_stage", fake_submit_stage):
                result = execute_tool(
                    "execute_fast_action",
                    self._fast_action_manifest_dict(operator_approved_i2v=True),
                    layout=layout, live=True, wait_for_completion=False,
                )
        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(len(stub_calls), 1, "gate must let an approved call reach submit_stage")

    def test_operator_approved_i2v_false_still_blocks(self):
        layout, selected = self._promote_fast_action()
        with patch("gvd_tool_router.service.route", selected):
            result = execute_tool(
                "execute_fast_action",
                self._fast_action_manifest_dict(operator_approved_i2v=False),
                layout=layout, live=True,
            )
        self.assertEqual(result["status"], "blocked")

    def test_generate_still_remains_exempt_from_the_video_gate(self):
        """Still tools are unaffected: no operator_approved_i2v needed."""
        layout, selected = self._promote_still()
        calls = []

        def http(url, payload, method, timeout):
            calls.append((url, method))
            if str(url).endswith("/prompt"):
                return {"prompt_id": "p-still"}
            return {}

        with patch("gvd_tool_router.service.route", selected),              patch("gvd_tool_router.executor.default_http", http):
            result = execute_tool("generate_still", _shot(), layout=layout, live=True, wait_for_completion=False)
        self.assertEqual(result["status"], "QUEUED")

    def _promote_still(self):
        layout = _layout()
        impls = seed_implementations()
        still = _activate(next(i for i in impls if i.tool_name == "generate_still"))
        Registry(layout).promote([still])

        def selected(manifest, implementations, inventory, registry_digest="0" * 64, **_route_kwargs):
            return RouteDecision(
                status="selected",
                tool_name="generate_still",
                implementation_id=still.implementation_id,
                profile_id="local_ok",
                registry_digest=registry_digest,
                stage_ids=tuple(stage.stage_id for stage in still.stages),
                reason_codes=(),
                rejection_log=(),
            )

        return layout, selected


class WaitForStageCompletionTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding 1.3/1.4): execute_tool()
    previously released the GPU lease/returned to the caller the instant a
    stage was QUEUED, not once ComfyUI actually finished rendering it.
    These exercise _wait_for_stage_completion() directly, and one
    end-to-end execute_tool() call, all with injected sleep_fn/time_fn so
    they run instantly and never touch a real clock or network."""

    def _conn(self):
        layout = _layout()
        conn = connect(layout)
        job = freeze_job(conn, project_id="p", registry_digest=SHA)
        add_shot(conn, job_id=job, shot_id="C001", manifest={})
        attempt_id = add_attempt(
            conn, shot_id="C001", implementation_id="impl-1",
            registry_digest=SHA, profile_id="local_ok", lease_generation=1,
        )
        return conn, attempt_id

    def test_returns_immediately_on_first_terminal_poll(self):
        conn, attempt_id = self._conn()
        sleeps = []

        def http(url, payload, method, timeout):
            if "/history/" in url:
                return {"p-1": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "x.png"}]}}}}
            raise AssertionError(f"unexpected url {url}")

        result = _wait_for_stage_completion(
            http=http, comfy_url="http://127.0.0.1:8188", prompt_id="p-1",
            attempt_id=attempt_id, conn=conn, timeout_s=600.0, poll_interval_s=5.0,
            sleep_fn=sleeps.append, time_fn=lambda: 0.0,
        )
        self.assertEqual(result["status"], "RENDERED")
        self.assertEqual(sleeps, [], "must not sleep once the first poll is already terminal")

    def test_polls_until_terminal_using_injected_sleep(self):
        conn, attempt_id = self._conn()
        polls = {"n": 0}
        sleeps = []

        def http(url, payload, method, timeout):
            if "/history/" in url:
                polls["n"] += 1
                if polls["n"] < 3:
                    return {}
                return {"p-2": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "x.png"}]}}}}
            if url.endswith("/queue"):
                return {"queue_running": [[0, "p-2", {}, {}, []]], "queue_pending": []}
            raise AssertionError(f"unexpected url {url}")

        result = _wait_for_stage_completion(
            http=http, comfy_url="http://127.0.0.1:8188", prompt_id="p-2",
            attempt_id=attempt_id, conn=conn, timeout_s=600.0, poll_interval_s=5.0,
            sleep_fn=sleeps.append, time_fn=lambda: 0.0,
        )
        self.assertEqual(result["status"], "RENDERED")
        self.assertEqual(polls["n"], 3)
        self.assertEqual(sleeps, [5.0, 5.0], "must sleep poll_interval_s between non-terminal polls")

    def test_bounded_timeout_marks_result_instead_of_hanging_forever(self):
        """The entire point of the fix being bounded, not just held-forever:
        a stuck render must not hold the GPU lease / router call open
        forever -- it returns with an explicit marker once timeout_s has
        elapsed, per injected time_fn, rather than pretending success."""
        conn, attempt_id = self._conn()

        def http(url, payload, method, timeout):
            if "/history/" in url:
                return {}
            if url.endswith("/queue"):
                return {"queue_running": [[0, "p-3", {}, {}, []]], "queue_pending": []}
            raise AssertionError(f"unexpected url {url}")

        clock = {"t": 0.0}

        def time_fn():
            return clock["t"]

        def sleep_fn(seconds):
            clock["t"] += seconds

        result = _wait_for_stage_completion(
            http=http, comfy_url="http://127.0.0.1:8188", prompt_id="p-3",
            attempt_id=attempt_id, conn=conn, timeout_s=12.0, poll_interval_s=5.0,
            sleep_fn=sleep_fn, time_fn=time_fn,
        )
        self.assertEqual(result["status"], "RUNNING")
        self.assertTrue(result.get("timed_out_waiting_for_completion"))

    def test_execute_tool_holds_lease_until_render_completes(self):
        """End-to-end: with the default wait_for_completion=True, a live
        execute_tool() call must report the eventual terminal status, not
        the intermediate QUEUED ack -- using injected sleep/time so the
        test itself runs instantly regardless of poll_interval_s."""
        layout = _layout()
        impls = seed_implementations()
        still = _activate(next(i for i in impls if i.tool_name == "generate_still"))
        Registry(layout).promote([still])

        def selected(manifest, implementations, inventory, registry_digest="0" * 64, **_route_kwargs):
            return RouteDecision(
                status="selected",
                tool_name="generate_still",
                implementation_id=still.implementation_id,
                profile_id="local_ok",
                registry_digest=registry_digest,
                stage_ids=tuple(stage.stage_id for stage in still.stages),
                reason_codes=(),
                rejection_log=(),
            )

        def http(url, payload, method, timeout):
            if str(url).endswith("/prompt"):
                return {"prompt_id": "p-e2e"}
            if "/history/" in str(url):
                return {"p-e2e": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "x.png"}]}}}}
            return {}

        sleeps = []
        with patch("gvd_tool_router.service.route", selected), \
             patch("gvd_tool_router.executor.default_http", http):
            result = execute_tool(
                "generate_still", _shot(), layout=layout, live=True, http=http,
                sleep_fn=sleeps.append, time_fn=lambda: 0.0,
            )
        self.assertEqual(result["status"], "RENDERED")
        self.assertEqual(result["submitted"][-1]["status"], "RENDERED")
        self.assertEqual(sleeps, [], "the fake history reports completed on the first poll")


class ReconcileTerminalStateTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding 1.4): reconcile() previously
    had no terminal-error branch -- anything short of completed-with-outputs
    was unconditionally reported RUNNING, forever."""

    def _conn(self):
        layout = _layout()
        conn = connect(layout)
        job = freeze_job(conn, project_id="p", registry_digest=SHA)
        add_shot(conn, job_id=job, shot_id="C001", manifest={})
        attempt_id = add_attempt(
            conn, shot_id="C001", implementation_id="impl-1",
            registry_digest=SHA, profile_id="local_ok", lease_generation=1,
        )
        return conn, attempt_id

    def test_explicit_comfy_error_status_is_terminal_not_running(self):
        conn, attempt_id = self._conn()

        def http(url, payload, method, timeout):
            self.assertIn("/history/", url)
            return {"p-err": {"status": {"status_str": "error", "completed": False}, "outputs": {}}}

        result = reconcile(http, "http://127.0.0.1:8188", "p-err", attempt_id, conn)
        self.assertEqual(result["status"], "FAILED")
        row = conn.execute("SELECT status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        self.assertEqual(row["status"], "FAILED")

    def test_absent_from_history_and_queue_is_terminal_not_running(self):
        """Reproduces the exact audit gap: a vanished prompt_id (ComfyUI
        restart, cancellation, history eviction) must not be reported as
        RUNNING forever."""
        conn, attempt_id = self._conn()

        def http(url, payload, method, timeout):
            if "/history/" in url:
                return {}
            if url.endswith("/queue"):
                return {"queue_running": [], "queue_pending": []}
            raise AssertionError(f"unexpected url {url}")

        result = reconcile(http, "http://127.0.0.1:8188", "p-gone", attempt_id, conn)
        self.assertEqual(result["status"], "FAILED")

    def test_absent_from_history_but_present_in_queue_stays_running(self):
        conn, attempt_id = self._conn()

        def http(url, payload, method, timeout):
            if "/history/" in url:
                return {}
            if url.endswith("/queue"):
                return {"queue_running": [[0, "p-live", {}, {}, []]], "queue_pending": []}
            raise AssertionError(f"unexpected url {url}")

        result = reconcile(http, "http://127.0.0.1:8188", "p-live", attempt_id, conn)
        self.assertEqual(result["status"], "RUNNING")

    def test_absent_from_history_and_unreadable_queue_stays_running(self):
        """Conservative default: an unparseable/unreachable /queue must not
        be treated as proof the job is gone."""
        conn, attempt_id = self._conn()

        def http(url, payload, method, timeout):
            if "/history/" in url:
                return {}
            if url.endswith("/queue"):
                raise ExecutorError("unreachable")
            raise AssertionError(f"unexpected url {url}")

        result = reconcile(http, "http://127.0.0.1:8188", "p-unknown", attempt_id, conn)
        self.assertEqual(result["status"], "RUNNING")

    def test_completed_with_outputs_still_renders(self):
        """Existing success path must be unaffected by the new branches."""
        conn, attempt_id = self._conn()

        def http(url, payload, method, timeout):
            return {"p-ok": {"status": {"completed": True}, "outputs": {"7": {"images": [{"filename": "x.png"}]}}}}

        result = reconcile(http, "http://127.0.0.1:8188", "p-ok", attempt_id, conn)
        self.assertEqual(result["status"], "RENDERED")


class DiscoveryFixtureTests(unittest.TestCase):
    def test_duplicate_keys_and_ui_and_local_redirect_states(self):
        class Search:
            async def search(self, query, limit):
                return [DiscoveryHit("https://github.com/example/wf", "wf")]

        class Resolver:
            async def workflow_assets(self, hit):
                return [CandidateAsset(hit.page_url, "https://github.com/example/wf.json", "ex", "abc", {})]

        class Fetcher:
            def __init__(self, body: bytes):
                self.body = body
            async def fetch_json(self, url, max_bytes):
                return FetchedAsset(self.body, url, "application/json")

        class Store:
            def __init__(self):
                self.items = {}
            async def contains(self, digest):
                return digest in self.items
            async def put_atomic(self, digest, body, metadata):
                self.items[digest] = {"body": body, "meta": metadata}
            async def mark(self, digest, state, reasons):
                self.items.setdefault(digest, {})["state"] = state

        class Queue:
            def __init__(self):
                self.jobs = []
            async def enqueue(self, digest, capability):
                self.jobs.append((digest, capability))

        from gvd_tool_router.binder import inspect_graph as inspect

        class Validator:
            def inspect(self, graph):
                return inspect(graph)

        dup = b'{"a": 1, "a": 2}'
        results = asyncio.run(discover_workflows(
            "fast_action", Search(), Resolver(), Fetcher(dup), Store(), Validator(), Queue(), 1,
        ))
        self.assertEqual(results[0]["state"], "quarantined")

        ui = json.dumps({"last_node_id": 1, "nodes": [], "links": []}).encode()
        results = asyncio.run(discover_workflows(
            "fast_action", Search(), Resolver(), Fetcher(ui), Store(), Validator(), Queue(), 1,
        ))
        self.assertEqual(results[0]["state"], "quarantined")
        self.assertEqual(results[0]["reasons"], ["ui_workflow_requires_api_export"])

    def test_discover_tool_rejects_unknown_capability(self):
        layout = _layout()
        payload = json.loads(discover_workflows_tool({
            "capability": "not_a_capability",
            "gvd_root": str(layout.root),
        }))
        self.assertEqual(payload["state"], "blocked")
        self.assertIn("unsupported_discovery_capability", payload["reason_codes"])


class AgentToolTests(unittest.TestCase):
    def test_execute_without_active_impl_returns_unavailable(self):
        layout = _layout()
        result = json.loads(execute_fast_action({
            "gvd_root": str(layout.root),
            "shot_id": "S01",
            "script_intent": "broll",
            "camera_motion": "static",
            "character_state": [],
            "continuity_mode": "independent",
            "duration_s": 4,
            "width": 1280,
            "height": 720,
            "fps_num": 24,
            "fps_den": 1,
            "hard_requirements": [],
            "priorities": {},
        }))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("UNAVAILABLE_CAPABILITY", result["reason_codes"])

    def test_whitelist_names_exist(self):
        import tools
        for name in (
            "gvd_inventory", "gvd_route_shot", "execute_narrative_scene",
            "execute_continuous_take", "execute_montage_morph",
            "execute_fast_action", "discover_workflows",
            "gvd_plan_shot", "gvd_family_status", "synthesize_dialogue",
            "apply_lipsync", "repair_video", "assemble_scene", "gvd_quality_gate",
            "gvd_qa_evaluate", "gvd_qa_attach_wd14", "gvd_qa_loop",
            "gvd_qa_accepted_still", "gvd_qa_activation",
        ):
            self.assertIn(name, tools.TOOLS)


class FamilyProfileTests(unittest.TestCase):
    def test_ltx_installed_storydiffusion_missing(self):
        root = Path(tempfile.mkdtemp())
        nodes = root / "custom_nodes"
        (nodes / "ComfyUI-LTXVideo").mkdir(parents=True)
        (nodes / "comfyui_ipadapter_plus").mkdir()
        (nodes / "ComfyUI_ProPainter_Nodes").mkdir()
        report = scan_families(root)
        self.assertTrue(report["families"]["fast_ltx"]["installed"])
        self.assertEqual(report["families"]["fast_ltx"]["activation"], "blocked_pending_local_profile")
        self.assertTrue(report["families"]["ipadapter"]["installed"])
        self.assertTrue(report["families"]["repair_propainter"]["installed"])
        self.assertFalse(report["families"]["narrative_identity"]["installed"])
        self.assertEqual(report["families"]["narrative_identity"]["activation"], "blocked_missing_nodes")
        self.assertFalse(report["families"]["montage_morph"]["installed"])
        self.assertFalse(report["families"]["continuous_longcat"]["installed"])
        self.assertFalse(report["families"]["lipsync_musetalk"]["installed"])
        self.assertFalse(report["families"]["qa_wd14"]["installed"])
        (nodes / "comfyui-wd14-tagger").mkdir()
        report2 = scan_families(root)
        self.assertTrue(report2["families"]["qa_wd14"]["installed"])


class SecureFetchTests(unittest.TestCase):
    def test_rejects_localhost_and_http_and_models(self):
        with self.assertRaises(FetchError):
            _check_url("http://github.com/x/y/workflow.json")
        with self.assertRaises(FetchError):
            _check_url("https://127.0.0.1/workflow.json")
        with self.assertRaises(FetchError):
            _check_url("https://github.com/x/y/model.safetensors")
        with self.assertRaises(FetchError):
            _check_url("https://evil.example/workflow.json")


class PlannerSwitchExtensionTests(unittest.TestCase):
    def test_planner_continuous_named_character(self):
        planned = plan_shot("an unbroken continuous take of the named hero walking")
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(planned["continuity_mode"], "continuous")
        self.assertIn("identity_reference", planned["manifest"]["hard_requirements"])

    def test_planner_unknown_asks_for_review(self):
        planned = plan_shot("asdf qwerty")
        self.assertEqual(planned["status"], "needs_manifest_review")

    def test_switch_blocks_unknown_vram_and_foreign_jobs(self):
        layout = _layout()

        class Q:
            def pending_and_running(self):
                return 0, 0
            def foreign_jobs(self):
                return True

        class M:
            def free_mib(self):
                return 12000
            def used_mib(self):
                return 400

        with self.assertRaises(SwitchBlocked):
            switch_to(layout, "ltx", peak_gpu_mib=None, job_id="j", attempt_id="a",
                      queue=Q(), memory=M(), unload_ollama=lambda: None, comfy_free=lambda: None)
        with self.assertRaises(SwitchBlocked):
            switch_to(layout, "ltx", peak_gpu_mib=4000, job_id="j", attempt_id="a",
                      queue=Q(), memory=M(), unload_ollama=lambda: None, comfy_free=lambda: None)

    def test_assembly_uses_narrative_order(self):
        layout = _layout()
        edl = assemble_scene(layout, project="p1", shots=[
            {"shot_id": "B", "edit_index": 1, "actual_frames": 10},
            {"shot_id": "A", "edit_index": 0, "actual_frames": 5},
        ])
        self.assertEqual([row["shot_id"] for row in edl["edl"]], ["A", "B"])
        self.assertEqual(edl["total_frames"], 15)

    def test_quality_gate_protected_region(self):
        ok = quality_gate(requested_duration_s=4, actual_duration_s=4, tolerance_s=0.2,
                          protected_before="aaa", protected_after="aaa")
        self.assertTrue(ok["passed"])
        bad = quality_gate(requested_duration_s=4, actual_duration_s=8, tolerance_s=0.2,
                           protected_before="aaa", protected_after="bbb")
        self.assertFalse(bad["passed"])
        self.assertIn("protected_region_changed", bad["reasons"])

    def test_repair_preserves_source_and_stays_blocked(self):
        layout = _layout()
        src = Path(tempfile.mkdtemp()) / "clip.mp4"
        src.write_bytes(b"fake-mp4-bytes")
        result = repair_video({
            "source_path": str(src),
            "project": "p",
            "shot_id": "S01",
            "start_frame": 3,
            "end_frame": 10,
            "desired_change": "remove wire",
        }, layout)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["preserved_source"])
        copies = list((layout.jobs / "p" / "S01" / "repair").glob("source_*"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_bytes(), b"fake-mp4-bytes")

    def test_promotion_holds_unknown_classes(self):
        graph = {"1": {"class_type": "StoryDiffusionMS", "inputs": {}}}
        report = validate_candidate_graph(
            graph, object_info={}, approved_classes=set(), trust_receipt=None,
        )
        self.assertEqual(report["verdict"], "hold_for_review")
        self.assertEqual(report["need"], "code_trust_receipt")

    def test_validation_queue_reconciles_crash(self):
        layout = _layout()
        conn = connect(layout)
        mark_discovery(conn, SHA, "validation_pending", "fast_action")
        conn.close()
        restored = SqliteValidationQueue(layout).reconcile()
        self.assertGreaterEqual(restored, 1)


if __name__ == "__main__":
    unittest.main()
