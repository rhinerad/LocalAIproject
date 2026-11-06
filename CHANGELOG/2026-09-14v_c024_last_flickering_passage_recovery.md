# 2026-09-14v — C024 last flickering-passage recovery

C024 start remains accepted. C024 last paused after two unconditioned SDXL
failures. The authored last line is Mode B: the view turns toward a passage
with one flickering fluorescent light. One SDXL candidate showed a camcorder
on the floor.

- Donor: `work/runtime/identity_donors/c024_last/c024_last_flickering_passage_imagegen_v1.png`
- SHA-256: `83f2810fd7f959061daec28d4bca7d45be082a81675beb72798543f7c67522cf`
- Policy `c024-last-hash-pinned-flickering-passage-v1` /
  `turn-to-flickering-fluorescent-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 175 tests passed.

## Controlled rerun

Attempt `267a53ac19494d0a80f585ce5122f294` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C024 last SHA-256
`83f2810fd7f959061daec28d4bca7d45be082a81675beb72798543f7c67522cf`.
Stills continued to C025 start. No video.
