# 2026-09-11p — C002 hash-pinned arm donor pass

## What changed

- Added a project-local, immutable arm-down donor at
  `work/runtime/identity_donors/c002_arm_down/c002_arm_down_donor_imagegen_v1.png`
  (SHA-256 `8d5d0095036c1577a06dc56caa8901c3872a8d4a31a0a7f42bd95ac515a2253d`).
- Added `arm_donor_composite` handling to
  `work/run_prompt_pack_production.py`. The full edited donor is never accepted:
  only two bounded arm corridors are transplanted onto the accepted C001 frame,
  with the face hard-protected and a 10% alpha-area ceiling.
- Added the bounded C002 v6 policy and a success guard that pauses before
  `C002_last`.
- Corrected the v6 QA description to use positive at-side pose wording and the
  literal `apartment living room` required by the mechanical prompt linter.
  This prevents the phrase `no raised hand or wave` from being misread as a
  positive raised-wave requirement.
- Corrected the donor-mask coverage calculation to alpha-weight histogram bins.
- Mirrored each active attempt's semantic result and QA receipt into the
  top-level production state so an older failure cannot remain displayed after
  a later pass.
- Added bounded regression coverage in `work/test_still_retry_not_stop.py`.

## Why

The v1–v5a2 SDXL and classical repair ladder could not fill the large raised-arm
hole cleanly. A full image edit produced a normal lowered arm but also changed
unrelated scene pixels. A deterministic donor composite preserves the accepted
C001 identity and room outside the exact arm union.

The first v6 receipt, `ee2797455aa647439ca7ae168c4ab876`, was visually good but
failed QA for two false reasons: the linter required the word `apartment`, and
the negative phrase `no raised hand or wave` activated the C001 raised-wave hand
gate. The same hash-pinned composite was therefore revalidated under corrected
QA semantics rather than regenerated.

## Evidence

- Passing attempt: `379a7e9ed6484f73918e2258c0250146`
- Still SHA-256:
  `c8d8dda8a47d8a4cca510d8280dff232b9ccd1f4c6b5fb50a15e24614b9305ab`
- Mechanical QA: pass
- Exact semantic QA: pass with
  `qwen25-vl-nsfw-caption:v4-q4_k_m` through `llama.cpp`
- Continuity: same person, hair, facial hair, clothing, and room geometry;
  reported difference is hand position only.
- Human/Codex visual inspection: both arms rest naturally, no teal/blue blob,
  no visible camera, and original identity/room pixels remain outside the
  bounded donor union.
- Production state: `paused_for_operator_review`, `supervisor_pid=null`.

## Verification

```text
python -m py_compile work/run_prompt_pack_production.py work/test_still_retry_not_stop.py
$env:PYTHONPATH=(Join-Path (Get-Location) 'work')
python -m unittest test_still_retry_not_stop test_image_render local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
Ran 101 tests in 2.016s — OK
```

The production progress JSON reparses successfully and now points
`semantic_check=pass` and `qa_audit` to the passing v6 receipt.

## Still unverified / blocked

- Operator visual acceptance of the exact C002 hash is pending.
- C002_last and every later still remain unrun.
- The complete 204-still approval gate is pending. No video was started.
