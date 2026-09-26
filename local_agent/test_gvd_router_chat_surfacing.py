#!/usr/bin/env python3
"""2026-09-26f: the GVD tool router's honest-failure statuses reach the
operator's chat reply as a fixed, specific question (stdlib only).

Shapes come from the real service functions wherever the seed catalog can
produce them (plan_narrative / route_shot / route()); the two literal
service.py blocks (ENGINE_FALLBACK_WAN, QA_GATE_BLOCKED) are copied as dicts.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import file_edit_gate
import gpu_gate
import ollama_client as oll
from gvd_tool_router.catalog_seed import seed_implementations
from gvd_tool_router.router import route
from gvd_tool_router.schema import to_plain
from gvd_tool_router.service import plan_narrative, route_shot
from test_gvd_tool_router import _activate, _layout, _profile, _shot
from test_native_tool_calling import _Route


def _independent_manifest(**over) -> dict:
    base = {
        "shot_id": "S07", "script_intent": "a car drives past", "camera_motion": "static",
        "character_state": [], "continuity_mode": "independent", "duration_s": 4.0,
        "width": 1280, "height": 720, "fps_num": 24, "fps_den": 1,
        "hard_requirements": [], "priorities": {},
    }
    base.update(over)
    return base


def _seed(tool_name: str):
    return next(i for i in seed_implementations() if i.tool_name == tool_name)


class RouterQuestionShapeTests(unittest.TestCase):
    """_gvd_router_question over real router outputs, one per status."""

    def test_planner_needs_manifest_review_asks_which_kind_of_shot(self):
        result = plan_narrative("make it nice", _layout())
        self.assertEqual(result["status"], "needs_manifest_review")
        self.assertEqual(result["reason_codes"], ["NEEDS_MANIFEST_REVIEW"])
        text = agent._gvd_router_question("gvd_plan_shot", result)
        self.assertTrue(text.startswith("No video tool was chosen or run for this shot "
                                        "(gvd_plan_shot returned needs_manifest_review)"))
        self.assertIn("(a) a continuous take", text)
        self.assertIn("(d) an independent action clip", text)
        self.assertIn("I will not pick an option for you.", text)

    def test_router_low_confidence_hard_requirement_names_it(self):
        # validate_manifest flags a hard requirement whose own confidence is
        # below 0.5 (the key must be the requirement itself).
        manifest = _independent_manifest(hard_requirements=["tts"],
                                         inferred_confidence={"tts": 0.3})
        result = route_shot(manifest, _layout())
        self.assertEqual(result["status"], "needs_manifest_review")
        self.assertIn("NEEDS_MANIFEST_REVIEW", result["reason_codes"])
        result["manifest"] = manifest   # gvd_plan_shot nests it; route_shot callers pass it
        text = agent._gvd_router_question("gvd_route_shot", result)
        self.assertIn("read as needing tts", text)
        self.assertIn("tts 0.30", text)
        self.assertIn("Confirm which of those you actually need", text)

    def test_continuous_without_start_frame_asks_for_the_file(self):
        manifest = _independent_manifest(shot_id="S02", continuity_mode="continuous")
        result = route_shot(manifest, _layout())
        self.assertEqual(result["status"], "blocked")
        self.assertIn("continuous_requires_start_or_context", result["reason_codes"])
        # A RouteDecision carries no shot id; the guard passes the id from the
        # tool call's own manifest argument as a hint.
        text = agent._gvd_router_question("gvd_route_shot", result)
        self.assertIn("for this shot (gvd_route_shot returned blocked)", text)
        text = agent._gvd_router_question("gvd_route_shot", result, shot_hint="S02")
        self.assertIn("for S02 (gvd_route_shot returned blocked)", text)
        self.assertIn("needs a start frame or a context video", text)
        self.assertIn("Which file?", text)

    def test_unknown_engine_is_named(self):
        manifest = _independent_manifest(requested_engine="sora")
        result = route_shot(manifest, _layout())
        self.assertEqual(result["status"], "blocked")
        text = agent._gvd_router_question("gvd_route_shot", result)
        self.assertIn("'sora' is not a video engine here", text)
        self.assertIn("MiniMax is the default", text)

    def test_unavailable_capability_lists_missing_and_candidates(self):
        # Seed catalog, nothing active: a motion-reference request has no
        # implementation, and the blocked report names the seed rows that
        # could supply it (2026-09-25q).
        manifest = _independent_manifest(hard_requirements=["motion_reference"])
        result = route_shot(manifest, _layout())
        self.assertEqual(result["status"], "blocked")
        self.assertIn("NO_COMPATIBLE_TOOL", result["reason_codes"])
        self.assertIn("UNAVAILABLE_CAPABILITY", result["reason_codes"])
        # required_capabilities() adds the mode capability (fast_action) too.
        self.assertEqual(result["missing_capabilities"], ["fast_action", "motion_reference"])
        self.assertTrue(result["blocked_candidates"])
        text = agent._gvd_router_question("gvd_route_shot", result)
        self.assertIn("No active tool offers: fast_action, motion_reference.", text)
        first = result["blocked_candidates"][0]["implementation_id"]
        self.assertIn(first, text)
        self.assertIn("Approve enabling or installing one of them", text)
        self.assertIn("no longer needs fast_action, motion_reference", text)

    def test_no_active_implementation_at_all_names_the_mode_capability(self):
        # Seed catalog, nothing active: even a plain independent shot is
        # missing its mode capability, and the seed rows that carry it are
        # listed as the things to approve.
        result = route_shot(_independent_manifest(), _layout())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["missing_capabilities"], ["fast_action"])
        text = agent._gvd_router_question("gvd_route_shot", result)
        self.assertIn("No active tool offers: fast_action.", text)
        self.assertIn("Approve enabling or installing one of them", text)

    def test_no_rows_and_no_missing_capability_is_said_plainly(self):
        plain = {"status": "blocked", "tool_name": "execute_fast_action",
                 "reason_codes": ["NO_COMPATIBLE_TOOL", "UNAVAILABLE_CAPABILITY"],
                 "rejection_log": [], "missing_capabilities": [], "blocked_candidates": []}
        text = agent._gvd_router_question("gvd_route_shot", plain)
        self.assertIn("No active implementation is registered for execute_fast_action", text)
        self.assertIn("workflow discovery search", text)

    def test_resource_blocked_names_the_rows_and_the_two_ways_out(self):
        impl = _activate(_seed("execute_fast_action"))
        decision = route(_shot(shot_id="S09"), [impl],
                         {"gpu": {"memory_free_mib": 1000}, "headroom_mib": 2048},
                         registry_digest="0" * 64)
        self.assertEqual(decision.status, "blocked")
        plain = to_plain(decision)
        self.assertTrue(any("RESOURCE_BLOCKED" in e["reasons"] for e in plain["rejection_log"]))
        text = agent._gvd_router_question("gvd_route_shot", plain)
        self.assertIn("not the free VRAM right now: " + impl.implementation_id, text)
        self.assertIn("approve the resource override", text)
        self.assertNotIn("No active implementation is registered", text)

    def test_profile_required_says_measure_first(self):
        impl = replace(_activate(_seed("execute_fast_action")),
                       profiles=(replace(_profile(), evidence="vendor"),))
        decision = route(_shot(shot_id="S10"), [impl],
                         {"gpu": {"memory_free_mib": 15000}, "headroom_mib": 2048},
                         registry_digest="0" * 64)
        self.assertEqual(decision.status, "blocked")
        plain = to_plain(decision)
        self.assertTrue(any("PROFILE_REQUIRED" in e["reasons"] for e in plain["rejection_log"]))
        text = agent._gvd_router_question("gvd_route_shot", plain)
        self.assertIn("no measured local VRAM profile yet: " + impl.implementation_id, text)
        self.assertIn("apply_profile.py", text)

    def test_operator_approval_required_is_named(self):
        impl = _activate(_seed("execute_fast_action"),
                         limits={"requires_operator_approval": True})
        decision = route(_shot(shot_id="S11"), [impl],
                         {"gpu": {"memory_free_mib": 15000}, "headroom_mib": 2048},
                         registry_digest="0" * 64)
        self.assertEqual(decision.status, "blocked")
        text = agent._gvd_router_question("gvd_route_shot", to_plain(decision))
        self.assertIn(impl.implementation_id + " may only be used with your explicit approval", text)

    def test_execute_tool_blocked_payload_reads_the_nested_decision(self):
        # execute_tool() wraps execution_blocked() around the decision.
        impl = _activate(_seed("execute_fast_action"))
        decision = route(_shot(shot_id="S12"), [impl],
                         {"gpu": {"memory_free_mib": 1000}, "headroom_mib": 2048},
                         registry_digest="0" * 64)
        payload = {
            "shot_id": "S12", "attempt_id": "", "status": "blocked",
            "reason_codes": list(decision.reason_codes),
            "tool_name": "execute_fast_action", "decision": to_plain(decision),
        }
        text = agent._gvd_router_question("execute_fast_action", payload)
        self.assertIn("for S12 (execute_fast_action returned blocked)", text)
        self.assertIn("not the free VRAM right now: " + impl.implementation_id, text)

    def test_wan_fallback_block_quotes_the_notice_and_the_three_ways(self):
        payload = {   # literal shape from service.execute_tool (2026-09-26b)
            "status": "blocked",
            "reason_codes": ["ENGINE_FALLBACK_WAN", "operator_acknowledgement_required",
                             "minimax_unfit:fasth3_v2_unvalidated:RESOURCE_BLOCKED"],
            "shot_id": "S13", "tool_name": "execute_continuous_take",
            "implementation_id": "wan22_i2v_8step",
            "engine": "wan", "engine_selection": "fallback",
            "operator_notice": "MiniMax didn't fit, used Wan instead (wan22_i2v_8step), "
                               "because fasth3_v2_unvalidated: RESOURCE_BLOCKED.",
            "note": "MiniMax did not fit this shot and Wan is the only remaining implementation.",
        }
        text = agent._gvd_router_question("execute_continuous_take", payload)
        self.assertIn(payload["operator_notice"], text)
        self.assertIn("acknowledge the Wan fallback", text)
        self.assertIn("change the shot so a MiniMax implementation fits", text)

    def test_qa_gate_block_asks_for_video_approval(self):
        payload = {"status": "blocked",
                   "reason_codes": ["QA_GATE_BLOCKED", "operator_approved_i2v_required"],
                   "shot_id": "S14", "tool_name": "execute_fast_action"}
        text = agent._gvd_router_question("execute_fast_action", payload)
        self.assertIn("needs your explicit approval (operator_approved_i2v)", text)

    def test_lease_contention_is_a_wait_not_a_guess(self):
        payload = {"status": "blocked",
                   "reason_codes": ["RESOURCE_BLOCKED", "lease held by job j1 (generation 4)"],
                   "shot_id": "S15"}
        text = agent._gvd_router_question("execute_fast_action", payload)
        self.assertIn("The GPU is held by another job (lease held by job j1 (generation 4))", text)

    def test_selected_route_is_not_a_question(self):
        impl = _activate(_seed("execute_fast_action"))
        decision = route(_shot(shot_id="S16"), [impl],
                         {"gpu": {"memory_free_mib": 15000}, "headroom_mib": 2048},
                         registry_digest="0" * 64)
        self.assertEqual(decision.status, "selected")
        self.assertIsNone(agent._gvd_router_question("gvd_route_shot", to_plain(decision)))
        planned = {"status": "planned", "manifest": {"shot_id": "S16"},
                   "route": to_plain(decision)}
        self.assertIsNone(agent._gvd_router_question("gvd_plan_shot", planned))

    def test_plan_shot_nested_blocked_route_is_read(self):
        planned = {"status": "planned", "manifest": _independent_manifest(shot_id="S17"),
                   "route": route_shot(_independent_manifest(shot_id="S17"), _layout())}
        text = agent._gvd_router_question("gvd_plan_shot", planned)
        self.assertIn("for S17 (gvd_plan_shot returned blocked)", text)


class HopAggregationTests(unittest.TestCase):

    def test_non_router_tool_in_the_hop_defers_to_the_model(self):
        review = json.dumps(plan_narrative("make it nice", _layout()))
        self.assertIsNone(agent._gvd_router_questions(
            [("gvd_plan_shot", review), ("read_file", "contents")]))

    def test_error_result_defers_to_the_normal_error_path(self):
        self.assertIsNone(agent._gvd_router_questions(
            [("gvd_plan_shot", "ERROR: boom")]))

    def test_selected_and_asked_in_one_hop_reports_both(self):
        impl = _activate(_seed("execute_fast_action"))
        selected = to_plain(route(_shot(shot_id="S18"), [impl],
                                  {"gpu": {"memory_free_mib": 15000}, "headroom_mib": 2048},
                                  registry_digest="0" * 64))
        review = plan_narrative("make it nice", _layout())
        text = agent._gvd_router_questions([
            ("gvd_route_shot", json.dumps(selected)),
            ("gvd_plan_shot", json.dumps(review)),
        ])
        self.assertIn("(a) a continuous take", text)
        self.assertIn("The other call(s) this turn (gvd_route_shot) returned a selected "
                      "or planned route and are not affected.", text)

    def test_notice_appended_once_and_not_when_already_present(self):
        notice = "MiniMax didn't fit, used Wan instead (wan22_i2v_8step), because X."
        self.assertEqual(agent._append_gvd_notices("Planned.", [notice, notice]),
                         "Planned.\n\nRouter notice: " + notice)
        self.assertEqual(agent._append_gvd_notices("Planned. " + notice, [notice]),
                         "Planned. " + notice)
        self.assertEqual(agent._append_gvd_notices("Planned.", []), "Planned.")


class ChatReplyTests(unittest.TestCase):
    """What the operator actually sees, through agent.answer()."""

    def setUp(self):
        self._gate_dir = tempfile.TemporaryDirectory()
        self._old_gate_file = gpu_gate.STATE_FILE
        gpu_gate.STATE_FILE = Path(self._gate_dir.name) / "gpu_gate.json"
        self._old_file_edit_gate = file_edit_gate.STATE_FILE
        file_edit_gate.STATE_FILE = Path(self._gate_dir.name) / "file_edit_gate.json"
        os.environ["LOCAL_AGENT_TRACING"] = "0"

    def tearDown(self):
        gpu_gate.STATE_FILE = self._old_gate_file
        file_edit_gate.STATE_FILE = self._old_file_edit_gate
        self._gate_dir.cleanup()

    def _answer(self, history, tool_name, tool_args, tool_json, narration):
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": tool_name, "arguments": tool_args}}])],
            [narration],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=tool_json) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))
        return reply, events, call

    def test_ambiguous_request_becomes_a_question_not_a_render_story(self):
        # Before 26f the second model turn below was the operator's reply.
        history = [{"role": "user", "content": "make a video that is nice"}]
        tool_json = json.dumps(plan_narrative("make it nice", _layout()))
        narration = ("I planned the shot and will render it now with the fastest "
                     "available tool; the video will be ready in a few minutes.")
        reply, events, call = self._answer(history, "gvd_plan_shot",
                                           {"text": "make it nice"}, tool_json, narration)
        call.assert_called_once()
        self.assertEqual("gvd_plan_shot", call.call_args.args[0])
        self.assertTrue(reply.startswith("No video tool was chosen or run for this shot "
                                         "(gvd_plan_shot returned needs_manifest_review)"),
                        reply)
        self.assertIn("(a) a continuous take", reply)
        self.assertIn("I will not pick an option for you.", reply)
        for claim in ("will render", "ready in a few minutes", "fastest available"):
            self.assertNotIn(claim, reply)
        self.assertTrue(any(k == "note" and "gvd router: honest-failure status" in p
                            for k, p in events), events)

    def test_missing_start_frame_asks_for_the_file(self):
        history = [{"role": "user", "content": "continue the last shot for 4 seconds"}]
        manifest = _independent_manifest(shot_id="S02", continuity_mode="continuous")
        tool_json = json.dumps(route_shot(manifest, _layout()))
        reply, _events, call = self._answer(history, "gvd_route_shot",
                                            {"manifest": manifest}, tool_json,
                                            "Continuing the shot now.")
        call.assert_called_once()
        self.assertIn("for S02 (gvd_route_shot returned blocked)", reply)
        self.assertIn("needs a start frame or a context video", reply)
        self.assertNotIn("Continuing the shot now", reply)

    def test_wan_fallback_notice_survives_the_model_reply(self):
        history = [{"role": "user", "content": "route a 4 second continuous take"}]
        notice = ("MiniMax didn't fit, used Wan instead (wan22_i2v_8step), because "
                  "fasth3_v2_unvalidated: RESOURCE_BLOCKED. Wan was the only compatible "
                  "implementation left; confirm before rendering.")
        selected = {
            "status": "selected", "tool_name": "execute_continuous_take",
            "implementation_id": "wan22_i2v_8step", "profile_id": "p1",
            "registry_digest": "0" * 64, "stage_ids": ["s1"],
            "reason_codes": ["ENGINE_FALLBACK_WAN", "minimax_unfit:fasth3_v2_unvalidated:RESOURCE_BLOCKED"],
            "rejection_log": [], "score": 0.7, "discovery_requested": False,
            "engine": "wan", "engine_selection": "fallback", "operator_notice": notice,
        }
        reply, _events, call = self._answer(history, "gvd_route_shot",
                                            {"manifest": {"shot_id": "S03"}},
                                            json.dumps(selected),
                                            "Routed: the take is planned.")
        call.assert_called_once()
        self.assertIn("Routed: the take is planned.", reply)
        self.assertIn("Router notice: " + notice, reply)

    def test_selected_route_without_notice_is_left_to_the_model(self):
        history = [{"role": "user", "content": "route a 4 second action clip"}]
        impl = _activate(_seed("execute_fast_action"))
        selected = to_plain(route(_shot(shot_id="S19"), [impl],
                                  {"gpu": {"memory_free_mib": 15000}, "headroom_mib": 2048},
                                  registry_digest="0" * 64))
        reply, _events, call = self._answer(history, "gvd_route_shot",
                                            {"manifest": {"shot_id": "S19"}},
                                            json.dumps(selected), "Routed to the fast-action tool.")
        call.assert_called_once()
        self.assertEqual("Routed to the fast-action tool.", reply)


if __name__ == "__main__":
    unittest.main()
