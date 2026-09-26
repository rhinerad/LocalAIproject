# 2026-09-10a — C001 last-frame composition-recovery guard

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only phase. No videos started.
No Equal Shares changes. C001_start has `semantic_check: pass` (attempt `baaf329e`,
full hash binding). Production paused at `paused_for_composition_recovery` after six
C001_last failures.

---

## Root Cause

`apply_composition_recovery()` in `work/run_prompt_pack_production.py` checked
`clip_id == "C001"` but not `frame == "start"`. When `recovery_index >= 7` the
function replaces the entire generation prompt with a neutral-standing description and
adds `"waving, arms raised"` to the **negative** prompt — making any endpoint
that requires a wave or smile structurally impossible to satisfy.

C001_last requires a sitcom wave and practiced smile as its endpoint action.  All
six prior C001_last attempts used recovery indices 0–7 (the first five from a fresh
start, the sixth reaching the v2 static stage). The v2 static prompt generated
actors standing with arms at their sides, which correctly failed the QA gate. The
`paused_for_composition_recovery` state was reached after three v2-indexed attempts
(one genuine v2 attempt and two v2-era attempts whose QA correctly rejected the
neutral pose).

Separately, one C001_last attempt (`3b88948a`, recovery_index=4) failed because the
VLM did not start (`exact Qwen2.5-VL runtime did not start`). This was a transient
infrastructure event; subsequent attempts show the VLM running again.

---

## Fix

**File changed:** `work/run_prompt_pack_production.py`

Added a frame guard immediately after the existing `clip_id != "C001"` check:

```python
# C001 composition recovery is designed for the neutral-standing opening
# plate (frame=="start").  Endpoint frames require a specific action such
# as a wave or smile; the v2+ static-pose recovery replaces the entire
# prompt with a neutral-standing description and adds "waving, arms raised"
# to the negative — which guarantees an endpoint action will fail QA.
# Non-start frames are left unchanged so their endpoint requirements are
# always preserved regardless of how many prior attempts have been made.
if recovered.get("frame") != "start":
    return recovered
```

This is a one-line logical guard. All v1 through v5 recovery stages (idx 3–∞)
are skipped for non-start frames. C001_last will now:
- Use its authored endpoint prompt (wave + smile required) on every attempt
- Receive the i2i reference from the accepted C001_start still (set by the run loop)
- Benefit from the adaptive `retry_denoise()` increase (0.42 → 0.72 over retries)
  to allow the pose change without losing identity

---

## Tests Updated

**`local_agent/test_production_integrity.py`** — added `"frame": "start"` to all
five C001 composition-recovery test fixtures (recovery indices 3, 7, 10, 12, 14).
These tests verify start-frame recovery still applies correctly.

**`work/test_still_retry_not_stop.py`** — two new tests added:

- `test_composition_recovery_is_noop_for_last_frame_at_v2_stage`: confirms that at
  recovery_index=7 a last-frame job returns unchanged, prompt preserved, "waving"
  absent from negative, no composition_recovery record attached.
- `test_composition_recovery_v2_still_applies_to_start_frame`: confirms v2 static
  recovery continues to apply to start-frame jobs at idx=7, including the "waving"
  negative and the composition_recovery record.

Two existing tests (`test_v5_delivery_target_is_4_by_3_and_keeps_required_visible_facts`,
`test_v5c_qa_prompt_disambiguates_layered_clothing_and_drops_unassessable_details`)
had their fixtures updated to include `"frame": "start"`.

---

## Test Results

```
python -m unittest local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -q
Ran 50 tests in 0.442s — OK
```

Syntax check:
```
python -m py_compile work/run_prompt_pack_production.py
```

---

## Production State

- C001_start: `semantic_check: pass`, full hash binding, `approval_status: pending`
  Attempt `baaf329eb9d84acba0ade4d8bb3c195c`, recovery_index=21 (v5 fit-sidefill)
- C001_last: `semantic_check: fail`, six prior attempts (indices 0–7),
  `paused_for_composition_recovery`; ledger `supervisor_pid: None`; PID 10128 dead
- Port 8188: free (ComfyUI not running)
- VLM port 11436: not listening (lazy watcher will restart on demand)

Next step: restart the production loop. The fixed `apply_composition_recovery()`
will skip all C001 recovery for last-frame jobs. The run loop sets
`attempt_job["reference_path"] = str(current_start)` for last-frame jobs when the
start frame has passed, so C001_last attempts will use the accepted C001_start still
as an i2i reference at adaptive denoise (0.42 → 0.72).

---

## What Did NOT Change

- `local_agent/production_integrity.py` — no changes
- `outputs/equal_shares/**` — untouched
- No video generation
- No model downloads
- No router/PowerInfer/GPU config changes
- All historical attempt directories, renders, receipts, and QA JSON files preserved
