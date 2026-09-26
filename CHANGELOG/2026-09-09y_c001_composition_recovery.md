# 2026-09-09y — C001 composition-recovery retry

## What changed

`work/run_prompt_pack_production.py` now applies a narrow, versioned
composition-recovery directive to **C001 only** after three prior attempts for
that endpoint. The directive is prepended only to the retry's runtime prompt
and adds weighted requirements for a wide, full-length actor, both shoes, and
visible floor. Its matching crop-related negatives are recorded in that retry's
receipt. The immutable source prompt is never edited.

`local_agent/test_production_integrity.py` adds two CPU-only tests covering
recovery activation, evidence metadata, and preservation of all other jobs and
early attempts.

## Why

The controlled resumed worker rendered and exact-Qwen2.5-VL-reviewed three
distinct C001 start-frame candidates. All three had the requested actor and a
living-room setting, but cropped the feet/shoes. Random seed changes alone did
not repair that repeated composition error. Continuing without a composition
change would have been an unbounded chance-only loop.

## Evidence

The preserved failed attempts are under:

`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/revisions/72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a/outputs/media/stills/pack_f8f7f70e364d40c0_72a7c2e5_c001_start/`

- Attempt `338efb9b7a69428aa60d42e3a9abe772`: waist-up crop; blind review
  recorded both feet false and white sneakers absent.
- Attempt `1915683761d04454aa590bb837cae001`: legs and shoes cropped; the
  review again failed literal full-body evidence.
- Attempt `802ba8dc2107479392ab24c3fbb7e796`: rejected by the same exact VLM
  gate; receipt and failure evidence remain in place.

The known supervisor and its backend children were paused after the third
rejection. Port 8188 was free and GPU memory returned to baseline before code
changes; no unknown process was touched.

## Verification

CPU-only verification:

```powershell
python -m unittest local_agent.test_production_integrity work.test_still_retry_not_stop local_agent.test_prompt_pack_production -q
python -m py_compile work\run_prompt_pack_production.py
```

Result: **35 tests passed** and compilation succeeded. No model was loaded by
the test suite.

## Still unverified

The recovery directive has not yet produced an accepted C001 image. Production
must resume at the still-only phase, pass the exact VLM and explicit approval
gates, and only then can the video phase be considered.
