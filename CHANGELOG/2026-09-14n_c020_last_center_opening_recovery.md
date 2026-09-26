# 2026-09-14n — C020 last center-opening POV recovery

C020 start remains accepted on
`ec2d158c0a01dfdb263ba160f34c9a717733fe2994ebc2f5b2ccdc5cd873ed4d`.
C020 last paused after two unconditioned SDXL failures. No video.

The authored last-frame line is Mode B: the view advances into the center
opening with walls closing in. One SDXL candidate showed sneakers/legs; the
other showed office doors with knobs.

- Donor: `work/runtime/identity_donors/c020_last/c020_last_center_opening_imagegen_v1.png`
- SHA-256: `eac8d438863f92e884428def8ec8c78a445fdb5196c0dce7c3235a4922782ada`
- Policy `c020-last-hash-pinned-center-opening-v1` /
  `advance-into-center-opening-v1`, `max_attempts: 1`
- Sleeve cuff allowed and not a torso. No pose/action requested.

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 151 tests passed.

## Controlled rerun

Attempt `9df12c98d0dd45cfb41eed0f1147f9d6` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C020 last SHA-256
`eac8d438863f92e884428def8ec8c78a445fdb5196c0dce7c3235a4922782ada`.
Stills continued to C021 start. No video.
