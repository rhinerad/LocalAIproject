# Creative stills QA (2026-09-20/21)

- Added `creative_still_qa.py`: prompt-aware fail-closed checks (YuNet face detect + SFace identity + room/clothing hist).
- Empty camcorder-POV / no-character prompts: do **not** fail for missing faces; fail if a face appears or room drifts.
- Actor-visible prompts: require face, room/clothing continuity vs prior approved anchor, face identity threshold.
- Wired into `flux_still_batch.auto_approve` / `render_one` (registry approval blocked on creative fail).
- Offline verify: `verify_creative_still_qa_offline.py` (C001 start vs last must fail; self-match pass; empty expectation parses).
