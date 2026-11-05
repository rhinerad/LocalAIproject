#!/usr/bin/env python3
"""Fix 2026-09-23 (readiness-audit §1.5, fix-set item #9): work/scene_reasoner.py
had zero test coverage before this. Covers the three defects the audit
called out: unvalidated loras/reference_character_ids passing through
_parse_decision, the eviction-status note not being conditioned on
eviction["verified"], and decide_shot() not being wrapped in try/finally
around evict_reasoning_model()."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene_reasoner as sr


FAKE_OPTIONS = {
    "still_model_profiles": list(sr.STILL_MODEL_PROFILES),
    "environment_loras": {
        "backrooms": {
            "name": "BacHal_(Background)_(SDXL)_(AD).safetensors",
            "use_when": "Level 0 Backrooms stills",
            "compatible_profiles": ("realvisxl",),
        },
    },
    "character_loras": [
        {"character": "Alex", "trigger_word": "alx01", "lora_filename": "alex_v1.safetensors"},
    ],
}


def _raw(**overrides) -> str:
    payload = {
        "still_model_profile": "realvisxl",
        "loras": [],
        "continuity_mode": "independent",
        "continuity_source": "none",
        "continuity_reason": "fresh scene",
        "reference_character_ids": [],
        "confidence": 0.9,
        "needs_operator_input": False,
        "question_for_operator": "",
        "reasoning": "fits the prompt",
    }
    payload.update(overrides)
    return json.dumps(payload)


class ParseDecisionLoraValidationTests(unittest.TestCase):
    """§1.5: 'loras' entries were accepted as-is (only the container type
    was checked) -- an invented LoRA filename passed straight through,
    potentially at high confidence, since it never triggered
    forced_operator_input."""

    def test_registered_environment_lora_is_accepted(self):
        raw = _raw(loras=[{"name": "BacHal_(Background)_(SDXL)_(AD).safetensors", "reason": "backrooms env"}])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["loras"], [{"name": "BacHal_(Background)_(SDXL)_(AD).safetensors", "reason": "backrooms env"}])
        self.assertFalse(decision["needs_operator_input"])

    def test_registered_character_lora_is_accepted(self):
        raw = _raw(loras=[{"name": "alex_v1.safetensors", "reason": "Alex appears"}])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual([l["name"] for l in decision["loras"]], ["alex_v1.safetensors"])
        self.assertFalse(decision["needs_operator_input"])

    def test_invented_lora_filename_is_dropped_and_forces_operator_input(self):
        raw = _raw(loras=[{"name": "totally_made_up_lora_v9.safetensors", "reason": "sounds plausible"}])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["loras"], [], "an unregistered LoRA must not reach the renderer")
        self.assertTrue(decision["needs_operator_input"])

    def test_invented_lora_forces_operator_input_even_at_high_confidence(self):
        """The exact audit scenario: a made-up filename must not sail
        through just because the model reported high confidence."""
        raw = _raw(loras=[{"name": "fake.safetensors"}], confidence=0.99)
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertTrue(decision["needs_operator_input"])

    def test_lora_entry_missing_name_is_dropped(self):
        raw = _raw(loras=[{"reason": "no name field at all"}])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["loras"], [])
        self.assertTrue(decision["needs_operator_input"])

    def test_mixed_valid_and_invalid_loras_keeps_only_the_valid_one(self):
        raw = _raw(loras=[
            {"name": "alex_v1.safetensors", "reason": "real"},
            {"name": "not_real.safetensors", "reason": "fake"},
        ])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual([l["name"] for l in decision["loras"]], ["alex_v1.safetensors"])
        self.assertTrue(decision["needs_operator_input"], "the fake entry must still force review")


class ParseDecisionCharacterIdValidationTests(unittest.TestCase):
    """§1.5: 'reference_character_ids' was coerced to a list of strings
    with no membership check against the real character library."""

    def test_registered_character_id_is_accepted(self):
        raw = _raw(reference_character_ids=["Alex"])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["reference_character_ids"], ["Alex"])
        self.assertFalse(decision["needs_operator_input"])

    def test_nonexistent_character_id_is_dropped_and_forces_operator_input(self):
        raw = _raw(reference_character_ids=["SomeoneWhoDoesNotExist"])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["reference_character_ids"], [])
        self.assertTrue(decision["needs_operator_input"])

    def test_empty_reference_character_ids_is_not_an_error(self):
        """Most shots reference no character at all -- an empty list is
        legitimate and must not force review on its own."""
        raw = _raw(reference_character_ids=[])
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["reference_character_ids"], [])
        self.assertFalse(decision["needs_operator_input"])

    def test_non_list_reference_character_ids_forces_operator_input(self):
        raw = _raw(reference_character_ids="Alex")
        decision = sr._parse_decision(raw, FAKE_OPTIONS)
        self.assertEqual(decision["reference_character_ids"], [])
        self.assertTrue(decision["needs_operator_input"])


class DecideShotThreadsOptionsIntoValidationTests(unittest.TestCase):
    """End-to-end: decide_shot() must pass the SAME options it showed the
    model into _parse_decision(), not re-derive them separately."""

    def test_decide_shot_rejects_a_lora_not_in_available_options(self):
        def fake_complete(prompt, model):
            self.assertIn("alex_v1.safetensors", prompt)
            return _raw(loras=[{"name": "invented.safetensors"}])

        with patch("scene_reasoner.available_options", return_value=FAKE_OPTIONS):
            decision = sr.decide_shot(
                story="my story", shot_id="C001", prompt_text="a hallway shot",
                complete=fake_complete,
            )
        self.assertEqual(decision["loras"], [])
        self.assertTrue(decision["needs_operator_input"])


class EvictionNoteHonestyTests(unittest.TestCase):
    """§1.5: reason_about_shot()'s note unconditionally read '...The
    reasoning model was unloaded...' whenever the decision wasn't blocked,
    not conditioned on eviction["verified"] at all -- a failed/unverified
    eviction was reported with the same reassuring text as a verified one."""

    def _stub_decision(self, *, needs_operator_input=False):
        return {
            "confidence": 0.9, "needs_operator_input": needs_operator_input,
            "question_for_operator": "" if not needs_operator_input else "which profile?",
            "reasoning": "ok", "still_model_profile": "realvisxl", "loras": [],
            "continuity_mode": "independent", "continuity_source": "none",
            "continuity_reason": "", "reference_character_ids": [],
            "parse_error": False, "shot_id": "C001", "story": "s",
            "model_used_for_reasoning": sr.DEFAULT_REASONING_MODEL,
            "decided_at": sr._now(), "is_video_shot": False,
        }

    def test_verified_eviction_gives_a_confident_note(self):
        with patch("scene_reasoner.decide_shot", return_value=self._stub_decision()), \
             patch("scene_reasoner.record_decision", return_value=Path("/tmp/x.jsonl")), \
             patch("scene_reasoner.evict_reasoning_model", return_value={"attempted": ["m"], "remaining": [], "verified": True}):
            result = sr.reason_about_shot(story="s", shot_id="C001", prompt_text="p")
        self.assertIn("verified", result["note"])
        self.assertNotIn("NOT", result["note"])

    def test_unverified_eviction_gives_an_honest_warning_not_a_reassurance(self):
        with patch("scene_reasoner.decide_shot", return_value=self._stub_decision()), \
             patch("scene_reasoner.record_decision", return_value=Path("/tmp/x.jsonl")), \
             patch("scene_reasoner.evict_reasoning_model",
                   return_value={"attempted": [], "remaining": None, "verified": False, "reason": "ollama unreachable"}):
            result = sr.reason_about_shot(story="s", shot_id="C001", prompt_text="p")
        self.assertIn("NOT", result["note"])
        self.assertIn("ollama unreachable", result["note"])
        self.assertNotIn("unloaded and verified", result["note"])

    def test_blocked_decision_note_also_reflects_unverified_eviction(self):
        with patch("scene_reasoner.decide_shot", return_value=self._stub_decision(needs_operator_input=True)), \
             patch("scene_reasoner.evict_reasoning_model",
                   return_value={"attempted": [], "remaining": None, "verified": False}):
            result = sr.reason_about_shot(story="s", shot_id="C001", prompt_text="p")
        self.assertEqual(result["status"], "blocked_awaiting_operator")
        self.assertIn("NOT", result["note"])


class EvictionAlwaysRunsTests(unittest.TestCase):
    """§1.5: decide_shot() was not wrapped in try/finally -- a raised
    SceneReasonerError (e.g. _call_ollama's network error) skipped
    evict_reasoning_model() entirely, leaving the model resident."""

    def test_eviction_still_runs_when_decide_shot_raises(self):
        calls = []

        def fake_evict():
            calls.append(1)
            return {"attempted": ["m"], "remaining": [], "verified": True}

        def raising_decide_shot(**kwargs):
            raise sr.SceneReasonerError("resident model call failed: connection refused")

        with patch("scene_reasoner.decide_shot", raising_decide_shot), \
             patch("scene_reasoner.evict_reasoning_model", fake_evict):
            with self.assertRaises(sr.SceneReasonerError):
                sr.reason_about_shot(story="s", shot_id="C001", prompt_text="p")
        self.assertEqual(calls, [1], "eviction must run even though decide_shot raised")

    def test_skip_eviction_true_does_not_call_evict_even_on_raise(self):
        calls = []

        def fake_evict():
            calls.append(1)
            return {"verified": True}

        def raising_decide_shot(**kwargs):
            raise sr.SceneReasonerError("boom")

        with patch("scene_reasoner.decide_shot", raising_decide_shot), \
             patch("scene_reasoner.evict_reasoning_model", fake_evict):
            with self.assertRaises(sr.SceneReasonerError):
                sr.reason_about_shot(story="s", shot_id="C001", prompt_text="p", skip_eviction=True)
        self.assertEqual(calls, [], "an explicit skip_eviction=True must still be honored on the raise path")


class CharacterLibraryFixtureTests(unittest.TestCase):
    """Sanity check that available_options()/_character_loras() (the real,
    unmocked path decide_shot uses by default) still round-trips through
    the new validation without needing a mock in the common case."""

    def test_real_character_library_round_trips_through_parse_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib_path = root / "character_library.json"
            lib_path.write_text(json.dumps({
                "characters": [
                    {"name": "Wren", "trigger_word": "wrn01", "lora_filename": "wren.safetensors"},
                ]
            }), encoding="utf-8")
            with patch.object(sr, "CHARACTER_LIBRARY", lib_path):
                options = sr.available_options()
                raw = _raw(
                    loras=[{"name": "wren.safetensors", "reason": "Wren appears"}],
                    reference_character_ids=["Wren"],
                )
                decision = sr._parse_decision(raw, options)
        self.assertEqual([l["name"] for l in decision["loras"]], ["wren.safetensors"])
        self.assertEqual(decision["reference_character_ids"], ["Wren"])
        self.assertFalse(decision["needs_operator_input"])


class ExplicitHistoryTests(unittest.TestCase):
    """2026-09-23: batch_run_backrooms_gvd passes pack-ordered history with
    shot context; the model must see it, and the on-disk log must not be
    consulted in its place."""

    def test_explicit_history_with_shot_context_reaches_the_prompt(self):
        seen = {}

        def fake_complete(prompt, model):
            seen["prompt"] = prompt
            return _raw(continuity_source="context_video")

        history = [{
            "shot_id": "C016", "camera_mode": "B", "speakers": ["ACTOR"],
            "shot_summary": "hand presses into damp carpet", "continuity_source": None,
        }]
        with patch("scene_reasoner.available_options", return_value=FAKE_OPTIONS), \
             patch("scene_reasoner.load_shot_history", side_effect=AssertionError("log read")):
            sr.decide_shot(
                story="s", shot_id="C017", prompt_text="hand touches wallpaper",
                is_video_shot=True, complete=fake_complete, history=history,
            )
        self.assertIn("hand presses into damp carpet", seen["prompt"])
        self.assertIn('"camera_mode": "B"', seen["prompt"])
        self.assertIn('"speakers": ["ACTOR"]', seen["prompt"])

    def test_history_none_still_reads_the_decision_log(self):
        with patch("scene_reasoner.available_options", return_value=FAKE_OPTIONS), \
             patch("scene_reasoner.load_shot_history", return_value=[]) as loader:
            sr.decide_shot(story="s", shot_id="C001", prompt_text="x",
                           complete=lambda p, m: _raw())
        loader.assert_called_once()

    def test_reason_about_shot_forwards_history(self):
        with patch("scene_reasoner.decide_shot", return_value=EvictionNoteHonestyTests._stub_decision(None)) as d, \
             patch("scene_reasoner.record_decision", return_value=Path("log.jsonl")):
            sr.reason_about_shot(story="s", shot_id="C002", prompt_text="x",
                                 skip_eviction=True, history=[{"shot_id": "C001"}])
        self.assertEqual(d.call_args.kwargs["history"], [{"shot_id": "C001"}])


if __name__ == "__main__":
    unittest.main()
