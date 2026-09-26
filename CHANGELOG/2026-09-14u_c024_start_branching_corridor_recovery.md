# 2026-09-14u — C024 start branching-corridor recovery

C023 last remains accepted. C024 start paused after two unconditioned SDXL
failures. The authored start line is Mode B: the view steadies and looks down
a branching corridor. SDXL reused the tilted hand-on-wall plate.

- Donor: `work/runtime/identity_donors/c024_start/c024_start_branching_corridor_imagegen_v1.png`
- SHA-256: `3a481fe47b68a43949b98f51353f83e6a0c7ecb740d84ad87d01b473f9defb23`
- Policy `c024-start-hash-pinned-branching-corridor-v1` /
  `steadied-branching-corridor-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 172 tests passed.

## Controlled rerun

Attempt `3be2b8192e7e4d088250e01232a503a5` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C024 start SHA-256
`3a481fe47b68a43949b98f51353f83e6a0c7ecb740d84ad87d01b473f9defb23`.
Stills continued to C024 last. No video.
