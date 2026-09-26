# 2026-09-22j — Operator decision: restart all generations from the beginning

Operator decision recorded 2026-09-22. Status/review item, not a render start.

## Decision

- All prior Backrooms generations are being abandoned and restarted from the
  beginning (C001 forward).
- The C-series still-recovery items (C016–C027) and their "Do not start
  videos" gates are superseded; they do not block the fresh run.
- The pending Flux smoke grant `gpu_a38b751666c5` is stale against the fresh
  run and is superseded.
- The hash-bound 204-still approval no longer refers to a completed set; the
  new run will be reviewed clip-by-clip as stills are produced.

## QA runtime verified

- `gvd_qa/smoke_caption_v4.py` succeeded: `ensure_qwen25_vl_runtime` brought
  the Caption V4 llama.cpp vision server up on 127.0.0.1:11436, produced real
  per-criterion verdicts (yellow_walls: fail, person_visible: pass with
  evidence), then released the VLM (VRAM back to ~573 MiB). The semantic QA
  runtime path is confirmed working end-to-end.

## Not changed

- No render or production batch started.
- No generated media, checkpoint, receipt, or registry state was deleted;
  prior attempts remain on disk for evidence.
