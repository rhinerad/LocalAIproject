# 2026-09-14r — C022 last longer-corridor recovery

C022 start remains accepted on
`3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`.
The authored last-frame line is Mode B: the same corridor appears subtly
longer and more distant.

- Donor: `work/runtime/identity_donors/c022_last/c022_last_longer_corridor_imagegen_v1.png`
- SHA-256: `c3e38d4a020e932ac526a2b4d697d86325e1113b06bf5bee0afc91d2ba6bb8a9`
- Policy `c022-last-hash-pinned-longer-corridor-v1` /
  `corridor-subtly-longer-distant-v1`, `max_attempts: 1`

Two C022 last SDXL attempts failed mechanical QA. Donor review started. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 163 tests passed.

## Controlled rerun

Attempt `67b3041f32554af791515c8ae5764cbc` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C022 last SHA-256
`c3e38d4a020e932ac526a2b4d697d86325e1113b06bf5bee0afc91d2ba6bb8a9`.
Stills continued to C023 start. No video.
