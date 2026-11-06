# 2026-09-13b — C013 last-frame continuity-anchor recovery

## Why

The first two C013-last RealVisXL image-to-image attempts were mechanically
valid but rejected by the exact Qwen2.5-VL Caption V4 gate for changing the
actor and apartment.  Their accepted C013-start anchor already depicts the
same adjacent crouched pull beat, so more unconditioned seed retries would not
address the demonstrated failure mode.

## Change

`work/run_prompt_pack_production.py` now applies one bounded
`c013_last_reference_copy` recovery only after those two base failures.  It
copies the hash-recorded managed C013-start still into a fresh C013-last
attempt directory, records source/output hashes and a receipt, and runs the
ordinary exact VLM review.  The frame remains `pending` operator approval.

## Verification

Ran, CPU-only:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'work') + ';' + (Join-Path (Get-Location) 'local_agent')
python -m py_compile .\work\run_prompt_pack_production.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 114 tests passed.  No evidence was overwritten.  No video was started.
The recovery has a single-attempt limit; a failed exact-VLM review pauses the
pack again for a new targeted diagnosis rather than silently consuming seeds.
