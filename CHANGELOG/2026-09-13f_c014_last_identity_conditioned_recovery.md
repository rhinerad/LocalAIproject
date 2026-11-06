# 2026-09-13f — C014 last-frame identity-conditioned recovery

## Diagnosis

`C014_last` had two completed ordinary image-to-image attempts. Both failed
semantic review because the checkpoint changed the actor and/or apartment while
trying to produce the authored backward-brace pose. Further seed-only retries
would repeat that uncontrolled failure mode.

An external edit candidate was inspected and rejected before import because it
also changed the framing and room composition. It was not copied into the
repository, registered, or used as a donor.

## Change

`work/run_prompt_pack_production.py` now applies one narrow recovery only after
two completed ordinary failures for `C014_last`:

- route through the installed SDXL FaceID/IP-Adapter `i2i_identity` mode;
- anchor to the accepted C014 start reference;
- use 0.48 denoise and 0.95 identity weight;
- retain the low crouch/frame while requesting only the slight backward-brace
  body language;
- explicitly prohibit visible cameras, lenses, tripods, crew, and production
  equipment;
- cap this recovery policy at two attempts.

This is not acceptance logic. Mechanical QA and exact Qwen2.5-VL semantic QA
still determine whether either artifact can pass. Existing attempts remain
untouched.

## Verification

Ran:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'work') + ';' + (Join-Path (Get-Location) 'local_agent')
python -m py_compile .\work\run_prompt_pack_production.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: **115 tests passed**. The new unit test proves two ordinary C014-last
failures select the bounded IP-Adapter route, rather than another unconditioned
seed.

## Still prohibited

No video job, model replacement, output overwrite/deletion, or acceptance was
performed. No GPU or ComfyUI process was started by this code/test pass.
