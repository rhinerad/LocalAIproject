#!/usr/bin/env python3
"""Offline unit tests for batch_run_backrooms_gvd.gate_before_video_submit.

Fix 2026-09-23 (readiness-audit finding 1.1): batch_run_backrooms_gvd.py
previously had zero QA/approval code anywhere in the file before submitting
video jobs. These tests lock in the fail-closed gate added in front of
gv.submit_comfy() so a future edit can't silently reopen that gap.

No ComfyUI, no GPU, no live Ollama/VLM connection, no network.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "local_agent") not in sys.path:
    sys.path.insert(0, str(ROOT / "local_agent"))

import batch_run_backrooms_gvd as batch  # noqa: E402


def _fake_gv(*, listening: bool) -> types.SimpleNamespace:
    return types.SimpleNamespace(caption_v4_listening=lambda: listening)


class GateBeforeVideoSubmitTests(unittest.TestCase):
    def _args(self, **overrides):
        ns = types.SimpleNamespace(
            skip_visual_qa=False,
            allow_ungated_i2v=False,
            require_qa_receipt=True,
            qa_receipt=None,
            qa_candidate=None,
            qa_job_dir=None,
        )
        for k, v in overrides.items():
            setattr(ns, k, v)
        return ns

    def _patched_gate(self, return_value=(None, None)):
        """Patch the file-loaded apply_qa_gate without touching real sys.path/import
        resolution (see _load_apply_qa_gate's docstring for why that's fragile here)."""
        fake_apply_qa_gate = MagicMock(return_value=return_value)
        return patch.object(batch, "_load_apply_qa_gate", return_value=fake_apply_qa_gate), fake_apply_qa_gate

    def test_refuses_when_vlm_down_and_no_explicit_override(self):
        """VLM offline + no operator override must block, not silently continue."""
        args = self._args()
        gv = _fake_gv(listening=False)
        patcher, fake_gate = self._patched_gate()
        with patcher:
            with self.assertRaises(RuntimeError):
                batch.gate_before_video_submit(
                    args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
                )
            fake_gate.assert_not_called()

    def test_allow_ungated_i2v_explicit_override_proceeds(self):
        """Explicit --allow-ungated-i2v is the only thing that may bypass an offline VLM."""
        args = self._args(allow_ungated_i2v=True)
        gv = _fake_gv(listening=False)
        patcher, fake_gate = self._patched_gate(return_value=(None, None))
        with patcher:
            batch.gate_before_video_submit(
                args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
            )
            fake_gate.assert_called_once()
        self.assertTrue(args.skip_visual_qa)

    def test_explicit_skip_visual_qa_still_goes_through_the_gate(self):
        args = self._args(skip_visual_qa=True)
        gv = _fake_gv(listening=True)
        patcher, fake_gate = self._patched_gate(return_value=(None, None))
        with patcher:
            batch.gate_before_video_submit(
                args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
            )
            fake_gate.assert_called_once()

    def test_gate_block_code_raises(self):
        """apply_qa_gate returning a non-None exit code must block the clip."""
        args = self._args(skip_visual_qa=True)
        gv = _fake_gv(listening=True)
        patcher, _fake_gate = self._patched_gate(return_value=(4, None))
        with patcher:
            with self.assertRaises(RuntimeError):
                batch.gate_before_video_submit(
                    args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
                )

    def test_vlm_up_no_flags_defers_to_receipt_gate(self):
        """VLM reachable and no skip flag: still routes through apply_qa_gate (receipt-based)."""
        args = self._args()
        gv = _fake_gv(listening=True)
        patcher, fake_gate = self._patched_gate(return_value=(None, "accepted.png"))
        with patcher:
            batch.gate_before_video_submit(
                args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
            )
            fake_gate.assert_called_once()
        self.assertFalse(args.skip_visual_qa)

    def test_load_apply_qa_gate_resolves_the_real_function(self):
        """End-to-end (no mocking): the file-based loader must actually resolve
        gvd_qa/i2v_gate.py's real apply_qa_gate, proving the fix for the
        `import gvd_qa` name collision (ROOT's gvd_qa.py vs. the gvd_qa/
        package under local_agent/) actually works in this process."""
        fn = batch._load_apply_qa_gate(batch.LOCAL_AGENT)
        self.assertTrue(callable(fn))
        self.assertEqual(fn.__name__, "apply_qa_gate")
        # And a real call, with no receipt/candidate and no explicit skip,
        # must fail closed (matches i2v_gate.py's own documented default).
        args = self._args()
        code, still = fn(args, root=batch.ROOT, local_agent=batch.LOCAL_AGENT)
        self.assertEqual(code, 4)
        self.assertIsNone(still)


if __name__ == "__main__":
    unittest.main()
