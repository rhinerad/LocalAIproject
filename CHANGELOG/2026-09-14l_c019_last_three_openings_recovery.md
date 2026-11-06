# 2026-09-14l — C019 last three-openings POV recovery

C019 start remains accepted on
`b1fd916f73f39f602c427986ec22334afd141fb355c3452141a1ef8c1002495c`.
C019 last paused after two unconditioned SDXL failures. No video.

The authored last-frame line is Mode B: the view pans toward three identical
openings. Both SDXL candidates showed mismatched doorways (two large sides
plus closed rear doors). A sleeve cuff is allowed, not required.

- Donor: `work/runtime/identity_donors/c019_last/c019_last_three_openings_imagegen_v1.png`
- SHA-256: `20b17935ca48707fd1887d8f248a9dac9865fd222349f45467097b45e074242b`
- Policy `c019-last-hash-pinned-three-openings-v1` /
  `pan-to-three-identical-openings-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 145 tests passed.

## Controlled rerun

Attempt `c6fe2b7d76f84c65bf9f858ed0c39e0a` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C019 last SHA-256
`20b17935ca48707fd1887d8f248a9dac9865fd222349f45467097b45e074242b`.
Stills continued to C020 start. No video.
