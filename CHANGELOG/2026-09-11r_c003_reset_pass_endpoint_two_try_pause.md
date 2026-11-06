# 2026-09-11r — C003 reset pass; endpoint stopped after two failures

## C003 start-frame recovery

- Resumed from the bounded C003-start pause with a different recovery method,
  not another diffusion seed.
- Edited the accepted C002 endpoint as the protected continuity source. The
  edit changes only the actor's forward lean/broad grin into an upright,
  neutral reset; the apartment, wardrobe, framing, and invisible-camera rule
  remain locked.
- Staged the candidate non-destructively at
  `work/runtime/identity_donors/c003_start/c003_start_reset_imagegen_v1.png`.
- SHA-256:
  `9c4113875bbca8503ec4aa9ae96a2a34e9dcb856338d68a99ac12d8cff54bbbc`.
- Added the one-attempt `c003-start-hash-pinned-endpoint-v2` policy. It copies
  only that exact hash and still requires the ordinary mechanical and exact
  Qwen2.5-VL Caption V4 gates.
- Attempt `50f62837cc2648008aaf4439659f7dc9` passed those gates and became the
  C003-start continuity image. This is still-only progress, not video approval.

## C003 last-frame failure and loop fix

- C003-last attempt `5b6345f2df704fbdb5d03660579408ef` failed: whole-frame
  SDXL replaced the actor, changed facial hair/room geometry, and missed the
  authored off-camera gesture.
- Attempt `7b830801c51742f3aa21df2cebd8b728` also failed identity continuity.
  Its gesture was readable, but the actor's face, hair, facial hair, and room
  did not match the accepted C003 start.
- The ordinary retry path lacked a two-attempt stop policy and started creating
  `1e35082e610b4c738058100097709a87`. The supervisor was stopped before QA.
  Its completed render is preserved, marked `interrupted_unreviewed`, and is
  explicitly ineligible for acceptance.
- Added `c003_last_base_failure_count()` and a main-loop guard. Future resumes
  pause after two completed unconditioned C003-last QA failures instead of
  rolling a third seed.

## Verification and final state

```powershell
python -m py_compile work\run_prompt_pack_production.py
$env:PYTHONPATH=(Join-Path (Get-Location) 'work')
python -m unittest test_still_retry_not_stop test_image_render local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 110 tests passed.

A live resume against task `f8f7f70e364d40c0` then exited with code 2 and
`PAUSE C003_last after two base failures` before opening port 8188 or allocating
GPU memory. This verifies the stop guard against the real preserved ledger.

- Production status: `paused_for_identity_recovery` at C003-last.
- Supervisor stopped; port 8188 released.
- Exact VLM runtime released; GPU returned to approximately 294 MiB idle use.
- No video generation began. All prior attempts and evidence remain.

Next recovery must be targeted identity/gesture control or a separately
reviewed hash-pinned C003-last donor. Do not resume by seed alone.
