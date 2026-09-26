#!/usr/bin/env python3
"""2026-09-26b: MiniMax-first engine policy in the GVD tool router.

Operator policy: MiniMax is the default video engine. Wan may be selected
only when the operator's own request names Wan, or when no MiniMax
implementation fits and Wan is the only compatible implementation left; the
second case must be announced, never silent. Stdlib only; no GPU, no ComfyUI.
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gvd_tool_router.catalog_seed import seed_implementations  # noqa: E402
from gvd_tool_router.planner import plan_shot, requested_engine_from_text  # noqa: E402
from gvd_tool_router.registry import Registry  # noqa: E402
from gvd_tool_router.router import (  # noqa: E402
    ENGINE_MINIMAX, ENGINE_OTHER, ENGINE_WAN, engine_family, engine_tier, route,
)
from gvd_tool_router.schema import (  # noqa: E402
    CAPABILITY_CONTINUATION, CAPABILITY_FAST, CAPABILITY_FIRST_FRAME,
    CAPABILITY_VIDEO_CONTEXT, ArtifactRef, shot_from_dict, to_plain,
)
from gvd_tool_router.service import execute_tool  # noqa: E402
from test_gvd_tool_router import INV, SHA, _activate, _layout, _profile, _shot  # noqa: E402

SEED = {impl.implementation_id: impl for impl in seed_implementations()}
CONTINUOUS_CAPS = {CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT}
# Wan deliberately outscores MiniMax on every axis: the policy, not the score,
# must decide.
MINIMAX_SCORES = {"identity": 0.6, "motion": 0.6, "style": 0.6, "audio": 0.6, "reliability": 0.6}
WAN_SCORES = {"identity": 0.9, "motion": 0.9, "style": 0.9, "audio": 0.9, "reliability": 0.9}


def _too_big(impl):
    """Same row, but its only local profile cannot fit INV's free VRAM."""
    return replace(impl, profiles=(replace(_profile(), profile_id="local_big", peak_gpu_mib=20000),))


def _continuous_shot(**extra):
    base = dict(
        continuity_mode="continuous",
        context_video=ArtifactRef("prev", SHA, "video/mp4"),
        camera_motion="dolly",
    )
    base.update(extra)
    return _shot(**base)


class EngineFamilyTests(unittest.TestCase):
    def test_seed_rows_classify_by_identity_and_family_key(self):
        expected = {
            "minimax_h3_fl2va_unvalidated": ENGINE_MINIMAX,
            "minimax_h3_ref2va_unvalidated": ENGINE_MINIMAX,
            "fasth3_v1_t2va_unvalidated": ENGINE_MINIMAX,
            "fasth3_v2_unvalidated": ENGINE_MINIMAX,
            "wan22_i2v_q4_high_unvalidated": ENGINE_WAN,
            "wan22_i2v_q4_dual_unvalidated": ENGINE_WAN,
            "wan22_i2v_8step_unvalidated": ENGINE_WAN,
            "wan22_animate_14b_unvalidated": ENGINE_WAN,
            "wan21_vace_1_3b_unvalidated": ENGINE_WAN,
            "wan21_tile_video_unvalidated": ENGINE_WAN,
            "ltx23_unvalidated": ENGINE_OTHER,
            "longcat_video_unvalidated": ENGINE_OTHER,
            "animatediff_sdxl_pose_ipadapter_unvalidated": ENGINE_OTHER,
            "known_good_sdxl_txt2img_v1": ENGINE_OTHER,
            "ipadapter_sdxl_plus_face_unvalidated": ENGINE_OTHER,
        }
        for impl_id, family in expected.items():
            self.assertEqual(engine_family(SEED[impl_id]), family, impl_id)

    def test_catalog_row_may_state_its_family(self):
        stated = replace(SEED["ltx23_unvalidated"], limits={"engine_family": "wan"})
        self.assertEqual(engine_family(stated), ENGINE_WAN)

    def test_tiers_default_and_explicit(self):
        minimax, wan, other = (SEED["minimax_h3_fl2va_unvalidated"],
                               SEED["wan22_i2v_8step_unvalidated"], SEED["ltx23_unvalidated"])
        self.assertEqual([engine_tier(i, None) for i in (minimax, other, wan)], [0, 1, 2])
        self.assertEqual([engine_tier(i, "wan") for i in (minimax, other, wan)], [1, 1, 0])


class EnginePolicyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.minimax = _activate(SEED["minimax_h3_fl2va_unvalidated"],
                                 extra=CONTINUOUS_CAPS, scores=MINIMAX_SCORES)
        self.wan = _activate(SEED["wan22_i2v_8step_unvalidated"],
                             extra=CONTINUOUS_CAPS, scores=WAN_SCORES)
        self.other = _activate(SEED["longcat_video_unvalidated"],
                               extra=CONTINUOUS_CAPS, scores=WAN_SCORES)

    def test_both_viable_picks_minimax_even_when_wan_outscores_it(self):
        decision = route(_continuous_shot(), [self.wan, self.minimax], INV)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.implementation_id, self.minimax.implementation_id)
        self.assertEqual(decision.engine, ENGINE_MINIMAX)
        self.assertEqual(decision.engine_selection, "default")
        self.assertEqual(decision.reason_codes, ())
        self.assertIsNone(decision.operator_notice)

    def test_minimax_resource_blocked_falls_back_to_wan_and_says_so(self):
        decision = route(_continuous_shot(), [_too_big(self.minimax), self.wan], INV)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.implementation_id, self.wan.implementation_id)
        self.assertEqual(decision.engine, ENGINE_WAN)
        self.assertEqual(decision.engine_selection, "fallback")
        self.assertIn("ENGINE_FALLBACK_WAN", decision.reason_codes)
        self.assertNotIn("ENGINE_EXPLICIT_WAN", decision.reason_codes)
        unfit = [c for c in decision.reason_codes if c.startswith("minimax_unfit:")]
        self.assertEqual(len(unfit), 1)
        self.assertIn("minimax_h3_fl2va_unvalidated", unfit[0])
        self.assertIn("RESOURCE_BLOCKED", unfit[0])
        self.assertIn("MiniMax didn't fit, used Wan instead", decision.operator_notice)
        self.assertIn("RESOURCE_BLOCKED", decision.operator_notice)

    def test_no_minimax_row_at_all_is_still_an_announced_fallback(self):
        decision = route(_continuous_shot(), [self.wan], INV)
        self.assertEqual(decision.implementation_id, self.wan.implementation_id)
        self.assertEqual(decision.engine_selection, "fallback")
        self.assertIn("ENGINE_FALLBACK_WAN", decision.reason_codes)
        self.assertIn("minimax_absent", decision.reason_codes)
        self.assertIn("no MiniMax implementation is active", decision.operator_notice)

    def test_other_family_beats_wan_when_minimax_is_unfit(self):
        # Wan is a last resort, not the second choice: any fitting non-Wan row wins.
        decision = route(_continuous_shot(), [_too_big(self.minimax), self.wan, self.other], INV)
        self.assertEqual(decision.implementation_id, self.other.implementation_id)
        self.assertEqual(decision.engine, ENGINE_OTHER)
        self.assertEqual(decision.engine_selection, "default")
        self.assertIsNone(decision.operator_notice)

    def test_explicit_wan_request_picks_wan_and_is_not_a_fallback(self):
        shot = _continuous_shot(requested_engine="wan")
        decision = route(shot, [self.minimax, self.wan], INV)
        self.assertEqual(decision.implementation_id, self.wan.implementation_id)
        self.assertEqual(decision.engine, ENGINE_WAN)
        self.assertEqual(decision.engine_selection, "explicit_request")
        self.assertIn("ENGINE_EXPLICIT_WAN", decision.reason_codes)
        self.assertNotIn("ENGINE_FALLBACK_WAN", decision.reason_codes)
        self.assertIn("explicitly named Wan", decision.operator_notice)

    def test_explicit_wan_request_that_cannot_fit_falls_to_minimax_with_notice(self):
        shot = _continuous_shot(requested_engine="wan")
        decision = route(shot, [self.minimax, _too_big(self.wan)], INV)
        self.assertEqual(decision.implementation_id, self.minimax.implementation_id)
        self.assertEqual(decision.engine_selection, "requested_engine_unavailable")
        self.assertIn("REQUESTED_ENGINE_UNAVAILABLE:wan", decision.reason_codes)
        self.assertIn("requested Wan but it could not be used", decision.operator_notice)

    def test_neither_fits_keeps_the_existing_blocked_contract(self):
        decision = route(_continuous_shot(), [_too_big(self.minimax), _too_big(self.wan)], INV)
        self.assertEqual(decision.status, "blocked")
        self.assertIn("NO_COMPATIBLE_TOOL", decision.reason_codes)
        self.assertIn("UNAVAILABLE_CAPABILITY", decision.reason_codes)
        self.assertIsNone(decision.implementation_id)
        self.assertIsNone(decision.engine)
        self.assertIsNone(decision.engine_selection)
        self.assertIsNone(decision.operator_notice)
        self.assertTrue(decision.discovery_requested)

    def test_unknown_requested_engine_is_blocked_not_guessed(self):
        decision = route(_continuous_shot(requested_engine="sora"), [self.minimax, self.wan], INV)
        self.assertEqual(decision.status, "blocked")
        self.assertTrue(any(c.startswith("unknown_requested_engine:sora") for c in decision.reason_codes))

    def test_requested_engine_normalises_from_dict(self):
        shot = shot_from_dict({**to_plain(_continuous_shot()), "requested_engine": " WAN "})
        self.assertEqual(shot.requested_engine, "wan")
        shot = shot_from_dict({**to_plain(_continuous_shot()), "requested_engine": ""})
        self.assertIsNone(shot.requested_engine)


class OperatorApprovalFlagTests(unittest.TestCase):
    """requires_operator_approval used to change only the headroom arithmetic
    once approval was already present; on its own it gated nothing. It now
    rejects the row outright without approval."""

    def setUp(self):
        self.v2 = _activate(SEED["fasth3_v2_unvalidated"], extra={CAPABILITY_FAST})
        self.assertTrue(self.v2.limits.get("requires_operator_approval"))
        self.ltx = _activate(SEED["ltx23_unvalidated"], extra={CAPABILITY_FAST})

    def test_flagged_row_is_rejected_without_approval_even_with_free_vram(self):
        decision = route(_shot(), [self.v2], INV)
        self.assertEqual(decision.status, "blocked")
        reasons = [r for r in decision.rejection_log if r["implementation_id"] == self.v2.implementation_id]
        self.assertEqual(len(reasons), 1)
        self.assertIn("operator_approval_required", reasons[0]["reasons"])

    def test_flagged_row_is_selected_with_approval(self):
        decision = route(_shot(), [self.v2], INV, operator_approval=True)
        self.assertEqual(decision.status, "selected")
        self.assertEqual(decision.implementation_id, self.v2.implementation_id)

    def test_without_approval_the_unflagged_row_wins_instead(self):
        decision = route(_shot(), [self.v2, self.ltx], INV)
        self.assertEqual(decision.implementation_id, self.ltx.implementation_id)


class PlannerEngineRequestTests(unittest.TestCase):
    def test_explicit_phrasings_name_wan(self):
        for text in (
            "establishing shot of the alley, use wan for this one",
            "action beat; minimax won't handle this, try wan",
            "b-roll of the street on Wan 2.2",
            "draft pass, render it with wan please",
            "establishing shot, switch to wan",
        ):
            planned = plan_shot(text)
            self.assertEqual(planned["status"], "planned", text)
            self.assertEqual(planned["requested_engine"], "wan", text)
            self.assertEqual(planned["manifest"]["requested_engine"], "wan", text)
            self.assertIn("requested_engine", planned["manifest"]["evidence_spans"], text)

    def test_default_is_minimax_with_no_engine_words(self):
        planned = plan_shot("establishing b-roll of the alley")
        self.assertEqual(planned["status"], "planned")
        self.assertIsNone(planned["requested_engine"])
        self.assertIsNone(planned["manifest"]["requested_engine"])

    def test_bare_or_negated_wan_is_not_a_request(self):
        for text in (
            "the hero gives a wan smile",            # English word, no verb of choice
            "establishing shot, don't use wan",
            "b-roll, no wan this time",
            "action shot, minimax not wan",
        ):
            planned = plan_shot(text)
            self.assertEqual(planned["status"], "planned", text)
            self.assertIsNone(planned["requested_engine"], text)

    def test_engine_words_alone_do_not_rescue_an_unreadable_request(self):
        planned = plan_shot("use wan")
        self.assertEqual(planned["status"], "needs_manifest_review")

    def test_user_manifest_field_wins(self):
        planned = plan_shot("establishing b-roll", user_manifest={"requested_engine": "wan"})
        self.assertEqual(planned["manifest"]["requested_engine"], "wan")

    def test_helper_returns_span(self):
        self.assertEqual(requested_engine_from_text("try wan instead")[0], "wan")
        self.assertEqual(requested_engine_from_text("a wan light"), (None, None))
        self.assertEqual(requested_engine_from_text("do not use wan"), (None, None))


class ExecuteToolWanFallbackGateTests(unittest.TestCase):
    """A Wan fallback is announced before rendering (planned DAG carries the
    notice) or instead of rendering (live submission blocked until the
    operator acknowledges). An explicit Wan request is never gated here."""

    def _layout_with(self, *impls):
        layout = _layout()
        Registry(layout).promote(list(impls))
        return layout

    def _manifest(self, **extra):
        manifest = to_plain(_continuous_shot())
        manifest.update(extra)
        return manifest

    def setUp(self):
        self.minimax = _too_big(_activate(SEED["minimax_h3_fl2va_unvalidated"],
                                          extra=CONTINUOUS_CAPS, scores=MINIMAX_SCORES))
        self.wan = _activate(SEED["wan22_i2v_8step_unvalidated"],
                             extra=CONTINUOUS_CAPS, scores=WAN_SCORES)
        # execute_tool routes against a fixed 12,000 MiB inventory; the
        # 20,000 MiB MiniMax profile is RESOURCE_BLOCKED there too.
        self.layout = self._layout_with(self.minimax, self.wan)

    def test_planned_dag_carries_the_fallback_notice(self):
        result = execute_tool("execute_continuous_take", self._manifest(), layout=self.layout, live=False)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["implementation_id"], self.wan.implementation_id)
        self.assertEqual(result["engine_selection"], "fallback")
        self.assertIn("MiniMax didn't fit, used Wan instead", result["operator_notice"])

    def test_live_fallback_is_blocked_until_acknowledged(self):
        stub_calls = []

        def fake_submit_stage(**kwargs):
            stub_calls.append(kwargs)
            return {"status": "QUEUED", "prompt_id": "p-wan"}

        with patch("gvd_tool_router.service.submit_stage", fake_submit_stage):
            result = execute_tool(
                "execute_continuous_take", self._manifest(operator_approved_i2v=True),
                layout=self.layout, live=True, wait_for_completion=False,
            )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason_codes"][:2], ["ENGINE_FALLBACK_WAN", "operator_acknowledgement_required"])
        self.assertIn("MiniMax didn't fit", result["operator_notice"])
        self.assertEqual(stub_calls, [], "must not submit to ComfyUI on an unacknowledged Wan fallback")

    def test_live_fallback_proceeds_once_acknowledged(self):
        stub_calls = []

        def fake_submit_stage(**kwargs):
            stub_calls.append(kwargs)
            return {"status": "QUEUED", "prompt_id": "p-wan"}

        with patch("gvd_tool_router.service.submit_stage", fake_submit_stage):
            result = execute_tool(
                "execute_continuous_take",
                self._manifest(operator_approved_i2v=True, operator_acknowledged_wan_fallback=True),
                layout=self.layout, live=True, wait_for_completion=False,
            )
        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(len(stub_calls), 1)
        self.assertEqual(result["engine_selection"], "fallback")
        self.assertIn("operator_notice", result)

    def test_explicit_wan_request_is_not_gated(self):
        stub_calls = []

        def fake_submit_stage(**kwargs):
            stub_calls.append(kwargs)
            return {"status": "QUEUED", "prompt_id": "p-wan"}

        with patch("gvd_tool_router.service.submit_stage", fake_submit_stage):
            result = execute_tool(
                "execute_continuous_take",
                self._manifest(operator_approved_i2v=True, requested_engine="wan"),
                layout=self.layout, live=True, wait_for_completion=False,
            )
        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(result["engine_selection"], "explicit_request")
        self.assertEqual(len(stub_calls), 1)


if __name__ == "__main__":
    unittest.main()
