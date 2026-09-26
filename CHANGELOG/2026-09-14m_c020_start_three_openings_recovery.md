# 2026-09-14m — C020 start three-openings fluorescent recovery

C019 last remains accepted on
`20b17935ca48707fd1887d8f248a9dac9865fd222349f45467097b45e074242b`.
C020 start paused after two unconditioned SDXL failures. No video.

The authored start line is Mode B: three identical yellow doorless openings
with fluorescent fixtures repeating overhead. Both SDXL candidates had three
openings but failed Mode B prompt language and generic full-person
continuity. A sleeve cuff is allowed.

- Donor: `work/runtime/identity_donors/c020_start/c020_start_three_openings_fluorescents_imagegen_v1.png`
- SHA-256: `ec2d158c0a01dfdb263ba160f34c9a717733fe2994ebc2f5b2ccdc5cd873ed4d`
- Policy `c020-start-hash-pinned-three-openings-v1` /
  `three-openings-repeating-fluorescents-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 148 tests passed.

## v1 false fail and v2

Attempt `ce27e2e11947495ebba882579c3f9b72` copied the donor. Exact VLM
returned `pass: true` with matching setting and openings, then failed only
`requested_pose_or_action_visible` on a static environment plate. v2 re-reviewed the same hash and failed because the allowed sleeve cuff was
treated as a torso / entirely-outside-frame violation. v3 re-reviews the
same pixels with the cuff allowed and explicitly not a face or torso.
Policy `c020-start-hash-pinned-three-openings-v3` / `cuff-allowed-not-torso-v1`.

v3 attempt `275cc31fdc874ce484bafa055c8f63e5` passed exact Qwen2.5-VL Caption V4
on the same donor
`ec2d158c0a01dfdb263ba160f34c9a717733fe2994ebc2f5b2ccdc5cd873ed4d`.
Stills continued. No video.
