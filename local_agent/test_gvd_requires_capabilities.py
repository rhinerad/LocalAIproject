#!/usr/bin/env python3
"""limits["requires_capabilities"]: a row that only makes sense for shots
needing a given capability is rejected for every other shot (2026-09-26,
motion transfer)."""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gvd_tool_router.catalog_seed import seed_implementations
from gvd_tool_router.router import route
from gvd_tool_router.schema import (
    CAPABILITY_IDENTITY, CAPABILITY_MOTION_REFERENCE, CAPABILITY_NARRATIVE, ArtifactRef,
)
from test_gvd_tool_router import SHA, _activate, _character, _shot

INV = {"gpu": {"memory_free_mib": 15000}, "headroom_mib": 2048}


def _motion_row():
    seed = next(i for i in seed_implementations()
                if i.implementation_id == "animatediff_sdxl_pose_ipadapter_unvalidated")
    return _activate(seed, limits={"requires_capabilities": [CAPABILITY_MOTION_REFERENCE]})


class RequiresCapabilitiesTests(unittest.TestCase):

    def test_seed_row_declares_the_requirement(self):
        seed = next(i for i in seed_implementations()
                    if i.implementation_id == "animatediff_sdxl_pose_ipadapter_unvalidated")
        self.assertEqual([CAPABILITY_MOTION_REFERENCE], seed.limits.get("requires_capabilities"))
        self.assertTrue({CAPABILITY_MOTION_REFERENCE, CAPABILITY_IDENTITY, CAPABILITY_NARRATIVE}
                        <= seed.capabilities)

    def test_identity_shot_without_motion_reference_is_rejected(self):
        impl = _motion_row()
        shot = _shot(shot_id="S30", continuity_mode="identity", character_state=(_character(),))
        decision = route(shot, [impl], INV, registry_digest="0" * 64)
        self.assertEqual("blocked", decision.status)
        reasons = decision.rejection_log[0]["reasons"]
        self.assertIn("shot_lacks_required_capability:motion_reference", reasons)

    def test_identity_shot_with_motion_reference_selects_it(self):
        impl = _motion_row()
        shot = _shot(shot_id="S31", continuity_mode="identity", character_state=(_character(),),
                     motion_reference_video=ArtifactRef("ref", SHA, "video/mp4"))
        decision = route(shot, [impl], INV, registry_digest="0" * 64)
        self.assertEqual("selected", decision.status)
        self.assertEqual(impl.implementation_id, decision.implementation_id)

    def test_rows_without_the_limit_are_unchanged(self):
        impl = replace(_motion_row(), limits={})
        shot = _shot(shot_id="S32", continuity_mode="identity", character_state=(_character(),))
        decision = route(shot, [impl], INV, registry_digest="0" * 64)
        self.assertEqual("selected", decision.status)


if __name__ == "__main__":
    unittest.main()
