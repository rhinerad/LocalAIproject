# 2026-09-14k — C019 start chest-height cuff POV recovery

C018 last remains accepted on
`3edae2d0266d33f6a31a5d745571a2e501d32284df144859469fbece905786a7`.
C019 start paused after two unconditioned SDXL failures. No video.

The authored start line is Mode B chest-height, looking forward into an empty
yellow room, with only a sleeve cuff at the lower edge. Both SDXL candidates
reused the close wallpaper-hand plate. The generic prompt also asked for a
standing actor holding a camcorder. Face/body identity comparison is
inapplicable.

- Donor: `work/runtime/identity_donors/c019_start/c019_start_chest_height_cuff_imagegen_v1.png`
- SHA-256: `b1fd916f73f39f602c427986ec22334afd141fb355c3452141a1ef8c1002495c`
- Policy `c019-start-hash-pinned-chest-cuff-v1` /
  `chest-height-empty-room-cuff-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 142 tests passed.

## v1 false fail and v2

Attempt `fde94d1936d3490a94bd66c40c648cf3` copied the donor. Mechanical QA
passed. Exact VLM failed because the v1 rubric said both "show a sleeve cuff"
and "no hand or fingers", so the cuff was treated as a violation. The pixels
are the authored chest-height empty-room cuff plate.

v2 re-reviews the same hash with the cuff as the requested subject. No new
image. Policy `c019-start-hash-pinned-chest-cuff-v2` /
`cuff-is-requested-subject-v1`.

v2 passed on the same donor
`b1fd916f73f39f602c427986ec22334afd141fb355c3452141a1ef8c1002495c`.
Stills continued to C019 last. No video.
