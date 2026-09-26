# 2026-09-14q — C022 start empty-corridor recovery

C021 last remains accepted. C022 start paused after two unconditioned SDXL
failures. The authored start line is Mode B: the corridor ahead appears empty
and ordinary. Reuse the reviewed C021 start corridor plate.

- Donor: `work/runtime/identity_donors/c022_start/c022_start_empty_corridor_imagegen_v1.png`
- SHA-256: `3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`
- Policy `c022-start-hash-pinned-empty-corridor-v1` /
  `empty-ordinary-corridor-ahead-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 160 tests passed.

## Controlled rerun

Attempt `195fdf8ebaea4c0aa0bf6a3f52c75261` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C022 start SHA-256
`3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`.
Stills continued to C022 last. No video.
