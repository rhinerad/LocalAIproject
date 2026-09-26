# Resource and safety hardening — 2026-08-25

## What changed

- `ollama_client.py` now accepts and transmits an explicit `keep_alive` value.
  Interactive agent turns retain the selected model for five minutes; planner
  and queued Ollama vision calls request zero retention.
- `media_queue.py` records `interactive` or `batch` priority, drains direct
  operator work first while preserving FIFO within each tier, and can return a
  pre-empted processing job to pending with its audit history intact.
- `media_tools.py` and `media_watcher.py` re-check for a render between video
  frames/action batches. A render pre-empts media work cooperatively; it never
  kills the render or marks a partial analysis as done.
- `tools.py` adds `propose_file_diff`, a protected-file-aware unified-diff
  preview. `agent.py` directs the model to preview a file edit before applying
  one.

## Why

Background model retention could delay VRAM recovery; old bulk media work could
delay a live attachment; and a render arriving mid-video analysis used to leave
the watcher with no safe recovery path. Direct file edits also needed an
operator-visible review step.

## Evidence and verification

- `test_native_tool_calling.py` verifies native schema registration, protected
  diff refusal, non-destructive diff output, and explicit keep-alive payloads.
- `test_media_gpu_queue.py` verifies priority order, duplicate promotion, and
  invalid-priority refusal.
- `test_media_preemption.py` verifies a pre-empted video action job returns to
  pending with a preserved audit record.
- Full local-agent test suite, agentic harness baseline, and 124/124 H3 prompt
  validation are run after this entry is written.

## Still unverified

- The exact 14B Ollama Flash Attention/q8 KV-cache comparison remains blocked
  because that exact primary model is not currently installed. No substitute
  model, live model load, render, or configuration switch was used here.
- A real CPU Whisper transcription remains a separately requested live model
  check; regression tests verify the available runtime gate and routing without
  loading Whisper during every test run.
