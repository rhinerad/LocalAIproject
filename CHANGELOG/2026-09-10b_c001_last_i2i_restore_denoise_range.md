# 2026-09-10b — C001_last i2i restore + denoise range fix

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only phase. No videos started.
C001_start: `semantic_check: pass`, accepted (attempt `baaf329e`).
C001_last: `semantic_check: fail`, 27 prior attempts.

---

## Root Cause

After the 2026-09-10a frame-guard fix, a second change was added that switched
C001_last from i2i to t2i at `recovery_index >= 10`. The rationale was that at
denoise 0.72 (the `retry_denoise()` cap), the reference anchor was too strong
for a pose change — generating the same standing pose rather than the required
wave/smile.

This was wrong in two ways:

1. **t2i produces wrong setting** (attempt `41856...` log): without an i2i
   reference, SDXL generated a studio-portrait look instead of a living-room scene.

2. **t2i + v1 additive caused floor failure** (PID 300, attempt `e7b1b097`): the
   v1 additive directive includes "small complete figure with generous room space
   above, beside, and below him". In t2i mode (no standing-pose anchor), SDXL
   interpreted this as the actor lying flat in the center of the frame.

The better diagnosis was that 0.72 denoise is too high, not that i2i is wrong.
Evidence: attempt `ec999d11` at 0.62 denoise i2i showed identity OK, smile
present, full body, living room, sofa — only failure was hands clasped instead
of raised. The 0.60–0.68 range is the sweet spot.

---

## Fix

**File changed:** `work/run_prompt_pack_production.py`

### 1. Removed t2i switch

The conditional block:
```python
_c001_last_t2i_after = 10
if not (attempt_job.get("clip_id") == "C001"
        and recovery_index >= _c001_last_t2i_after):
    attempt_job["reference_path"] = str(current_start)
```
was replaced with the original unconditional assignment:
```python
attempt_job["reference_path"] = str(current_start)
```

### 2. Added denoise range override for C001_last

Immediately after `attempt_job["denoise"] = retry_denoise(attempt_job, retry_index)`:
```python
# C001_last identity sweet spot: 0.60-0.68 keeps the standing-pose
# anchor from the start-frame reference while still allowing the
# wave/smile action change.  Above 0.68 the reference weakens and
# SDXL generates different-looking actors; below 0.60 the action
# never appears.  Small increments explore many seeds in the range.
if (attempt_job.get("clip_id") == "C001"
        and attempt_job.get("frame") == "last"
        and recovery_index >= 10
        and attempt_job.get("reference_path")):
    attempt_job["denoise"] = min(0.68, 0.60 + retry_index * 0.02)
```

This keeps every attempt in the 0.60–0.68 window once 10+ attempts have been
accumulated, exploring the range with small increments before settling at 0.68.

---

## Test Results

```
python -m unittest local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -q
Ran 50 tests in 0.729s — OK
```

---

## Ledger Reset

Watchdog cleared: `'stale progress/logs; inspect evidence before retry -- supervised halt for i2i restore + denoise range fix'`
Status reset: `error` → `running`
`supervisor_pid`: 300 (dead) → `None`
Cleared via `prompt_pack_production.save_production(..., clear_watchdog=True)`.

---

## Production State

- C001_start: `semantic_check: pass`, full hash binding, `approval_status: pending`
  Attempt `baaf329eb9d84acba0ade4d8bb3c195c`, recovery_index=21 (v5 fit-sidefill)
- C001_last: `semantic_check: fail`, 27 prior attempts
  Next attempt: recovery_index=27, denoise=0.60, i2i from C001_start reference
- Port 8188: free
- VLM port 11436: lazy watcher will start on demand

Next step: start production loop (`production_2026-09-10d.log`).

---

## What Did NOT Change

- `local_agent/production_integrity.py` — no changes
- Test files — no changes needed (t2i was a run-loop implementation, not tested)
- `outputs/equal_shares/**` — untouched
- No video generation
- All historical attempt directories preserved
