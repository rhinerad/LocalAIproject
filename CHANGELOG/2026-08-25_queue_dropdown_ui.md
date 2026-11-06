# Media queue dropdown and cooperative cancellation — 2026-08-25

## What changed

- `local_agent/media_queue.py` records per-job timestamps, progress, priority,
  readable source names, and wait reasons. It preserves cancellation evidence
  under `media_queue/cancelled/` and supports a processing-job cooperative flag.
- `local_agent/media_watcher.py` observes that flag at the same safe boundaries
  it already uses for render pre-emption, then releases/requeues or cancels
  without writing a partial job as complete.
- `local_agent/server.py` adds the loopback-only `/api/media_queue/cancel`
  route, factored to reject blank or unknown ids cleanly. It has no render path.
- `local_agent/static/index.html` adds the Queue dropdown, row-level Cancel,
  status/progress/wait text, and client-side ticking timers.

## Why

The earlier queue pill reported only counts, leaving the operator unable to see
why a media task had paused or withdraw a no-longer-wanted attachment safely.

## Evidence and verification

- `python local_agent/test_media_gpu_queue.py` — **26 tests passed**, including
  pending/processing cancellation, immutable cancellation evidence, rich wait
  reason fields, priority, and the endpoint helper's valid/unknown/blank-id
  cases.
- Full local-agent suite — **134 tests passed**; `agentic_eval.py` — **5/5**;
  `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v` —
  **124/124 valid**. These were run with mocked model calls where applicable.

## Still unverified

- The visual dropdown interaction remains a manual desktop check after the
  running local-agent server is refreshed. No model, download, render, or media
  workload was started for this implementation.
