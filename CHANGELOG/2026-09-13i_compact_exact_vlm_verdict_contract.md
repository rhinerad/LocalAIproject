# 2026-09-13i — compact exact-VLM verdict contract

## Finding

The exact Qwen2.5-VL review of the C014 identity-conditioned still returned a
long JSON-like answer that was cut off before its final `checks` object. Its
prompt-aware opening assessment actually said `pass: true`, while its separate
blind continuity comparison disagreed. The parser correctly failed closed, but
the oversized response makes the primary verdict unusable as evidence.

## Change

The prompt-aware exact-VLM verdict now requires a single compact JSON object
under 300 characters, short scalar evidence fields only, and no arrays, nested
objects, markdown fences, or surrounding prose. The required boolean checks
and the independent blind/continuity evidence remain unchanged.

This is a reviewer-output reliability change only. It does not promote a prior
artifact, relax a continuity rule, change model files, or start a render.

## Verification

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'work') + ';' + (Join-Path (Get-Location) 'local_agent')
python -m py_compile .\work\run_prompt_pack_production.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: **115 tests passed**.
