# 2026-09-10c — C001_last: remove all composition recovery (pure no-op)

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only phase. No videos.
C001_start: `semantic_check: pass` (attempt `baaf329e`).
C001_last: `semantic_check: fail`, 96 prior attempt directories
(27 real renders + 61 empty fast-spin dirs from the `image_render` import-path
bug + 4 real renders from PID 40984 with incorrect v1 additive prompts +
4 more empty dirs from the PID 40984 watchdog halt cycle).

---

## Root Cause (discovered this session)

The 2026-09-10a changelog added v1 additive composition recovery for non-start
frames. This turned out to be wrong. Evidence:

**ec999d11** (recovery_index=10, denoise=0.72, `composition_recovery: None`):
- Generated **before** v1 additive was added to the non-start path
- identity_continuity: True (correct dark-haired actor)
- smile: present
- Only failure: hands clasped, not raised in wave

Every attempt **after** v1 additive was added (d1a9997d, 1c272737, 4355c04d,
504b0fec, bd67a478) generated completely wrong actors (long blonde hair, beards)
at all denoise levels tested (0.60–0.68). The diagnosis:

The v1 additive directive injects extreme attention weights (`2.0`, `1.8`) into
the prompt. At 0.60 denoise the i2i reference is strong — but SDXL's cross-
attention to these bolded directives still overwhelms the pixel-level anchor,
producing actors the model associates with "full-length wide shot" + "room space
above, beside, below." Without the directive the reference image's pixel-level
content dominates, preserving identity.

**Secondary bug discovered**: `image_render` import failed when the loop was
started as `python -m work.run_prompt_pack_production` because `work/` was not
on `sys.path`. This caused 61 empty attempt directories in ~30 seconds (2 sec/
cycle). Fixed by starting the loop as `python work/run_prompt_pack_production.py`
(direct script invocation adds `work/` to `sys.path`).

---

## Fix

**File changed:** `work/run_prompt_pack_production.py`

The `apply_composition_recovery()` non-start frame block was changed from a v1
additive (prepend directive + extend negative) to a **pure no-op return**:

```python
if recovered.get("frame") != "start":
    # [long comment explaining evidence]
    return recovered
```

The denoise override (`min(0.62, 0.60 + retry_index * 0.02)`) introduced in
2026-09-10b was also removed. `retry_denoise()` resumes its normal behavior:
base 0.52 + 0.10/retry, cap 0.72. This matches the conditions of ec999d11.

---

## Tests Updated

**`work/test_still_retry_not_stop.py`**

Renamed `test_composition_recovery_v1_additive_for_last_frame_never_v2_replacement`
→ `test_composition_recovery_is_complete_noop_for_last_frame`.

Old test asserted `COMPOSITION RECOVERY` in prompt, v1 version in record.
New test asserts prompt/negative unchanged, `composition_recovery` is None.

---

## Test Results

```
python -m unittest local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -q
Ran 50 tests in 0.505s — OK
```

---

## Production State (paused at clean stopping point)

- **C001_start**: `semantic_check: pass`, attempt `baaf329e`, recovery_index=21
- **C001_last**: `semantic_check: fail`, ledger status=`error`, 96 attempt dirs
  (27 real renders; others empty)
  - Watchdog: `stale progress/logs; inspect evidence before retry -- halting to fix denoise cap 0.68->0.62`
  - Supervisor PID 40984 confirmed dead
  - Port 8188: free

**Next step**: Clear watchdog, restart loop as direct script:
```
python work/run_prompt_pack_production.py --cid f8f7f70e364d40c0
```
At recovery_index=96, retry_index=0:
- denoise = retry_denoise() = min(0.72, 0.52 + 0 * 0.10) = 0.52
- No composition recovery (pure no-op)
- i2i from C001_start reference (`baaf329e/still.png`)

The 0.52 denoise is conservative. Denoise climbs 0.10 per retry_index
(0.52 → 0.62 → 0.72). ec999d11 passed identity at 0.72, so multiple seeds
at 0.72 are the target zone. Expect the wave to appear within ~5-10 attempts
at denoise 0.72 with varied seeds.

---

## What Did NOT Change

- `local_agent/test_production_integrity.py` — no changes
- `outputs/equal_shares/**` — untouched
- No video generation
- All attempt directories preserved
