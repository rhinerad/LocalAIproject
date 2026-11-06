# 2026-09-14a — C014 endpoint pose evidence repair

## Scope

Backrooms prompt-pack stills only. No video job was started. The Equal Shares
audio/render pipeline was not touched.

## What changed

- Added a hash-pinned, versioned C014-last endpoint candidate under
  `work/runtime/identity_donors/c014_last/`; every candidate remains preserved.
- Added a bounded C014-only endpoint route. It copies the immutable candidate
  into a receipt-bearing attempt and still requires the normal exact local
  Qwen2.5-VL gate; it is not an auto-accept path.
- Fixed a general QA representation mismatch: when the exact VLM returns a
  single subject record, its literal expression, hands, clothing, and action
  fields are now losslessly promoted for the existing safety checks.
- Added a C014-only torso crop review. It must report a high/medium-confidence
  `backward_lean`; independent full-frame evidence must separately show effort,
  both hands on the floor, no visible equipment, and a literal continuity pass.

## Verification

```
python -m py_compile work/run_prompt_pack_production.py work/test_still_retry_not_stop.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 117 tests passed.

Controlled C014-last re-review attempt:

`outputs/media/stills/pack_f8f7f70e364d40c0_72a7c2e5_c014_last/14597e26c63445848946a5195fb648ba/`

Exact runtime evidence: `qwen25-vl-nsfw-caption:v4-q4_k_m` through lazy
llama.cpp, matching the installed projector. The final status is `pass`:
the crop reports `backward_lean`, the full-frame review reports a pained actor
with both hands on the floor and no camera/tripod, and the two-image comparison
reports the same person, hair, facial hair, clothing, and room geometry.

## Guardrails retained

- C014 still has `approval_status: pending`; it is not operator-approved for
  video generation.
- Failed candidates and their QA receipts remain untouched.
- No ComfyUI backend, video render, model-weight change, or destructive action
  ran in this recovery.
