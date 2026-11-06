# 2026-09-05bq — Status sync: Qwen3.8-27B rejected, catalog-drowning fix verified live, semantic judge shipped

## Scope

Operator-facing tracking entry for three reports
(`2026-09-05bm`/`bn`/`bo`). No new production work from this entry.

## 2026-09-05bm — Qwen3.8-27B abliterated: correctly not added to router.py

Real, honest "don't ship it" result. The already-downloaded
`huihui_ai/Qwen3.8-abliterated:latest` (Q4_K_M, 27.3B, digest confirmed
matching the loose GGUF on disk) fills the RTX 5080 with weights alone
(15.3GB CUDA buffer) — only ~370MB free at 2K context, decode already
dropped from 14.6 to 8.3 tok/s by 9.4K filled tokens, and a real 64K
context allocation attempt crashed the server outright (exit
`0xffffffff`). Correctly distinguished this from catalog drowning: hop 0
picked the right tool from the full 68-tool schema with empty content
and native `tool_calls` — the real, more severe problem is that this
tag's `qwen3.8` chat template rejects the assistant+tool follow-up
message entirely (`no user query found in messages`), which means
multi-hop tool use is currently broken for this tag, not just slow.

Correctly recorded the llama.cpp `#27623` upstream bug as still open as
of today, with the exact version baseline (`b10488`) so a future session
can recheck cheaply rather than re-investigating from scratch. Also
correctly identified that this card never even reached the 80K cliff the
bug describes — the card can't hold 64K of KV at all with this quant, so
the software bug isn't even the limiting factor today. Useful design
note for later: if a smaller quant (Q3_K_M/IQ4_XS, already on disk as
loose GGUF but not an Ollama tag) ever makes this viable, the existing
`_apply_ctx_ceiling`/`_trim_context` compaction machinery should be
reused rather than building a second pipeline — no new work needed
there, just wiring.

**Recommendation followed as reported: not added to `GPU_MODELS`, no
pull, no router change.**

## 2026-09-05bn — Catalog-drowning fixes shipped and live-verified

Both fixes from `2026-09-05bc` built and independently verified. The
measured per-schema token constant (60 tokens/schema, from real
`prompt_eval_count` data) drops case 4's estimate from 19352 (over the
16K demotion threshold) to 11536 (comfortably under) on its own. The
curated `gpu_core` fallback schema (6-12 tools depending on whether the
turn is Comfy-related) is scoped correctly — only to the farm-down/
`skip_farm` tool-fallback case, not applied to pinned conversations or
CAP_CODE/CAP_LOGIC specialists. 160 tests pass. Live-verified with the
farm forced down: case 1a now correctly picks `read_file` (previously
`fetch_url`) and case 4 now correctly stays on Huihui-14B (previously
would have demoted to 8B) and picks the right tool
(`comfy_workflow`/`enqueue_workflow`) — the only remaining gap is Comfy
itself being down during the test, which is a live-environment
limitation, not a routing bug.

## 2026-09-05bo — Farm semantic judge pass v1 shipped

Real build, all four safeguards adversarially tested rather than
asserted: the isolation grep-lock catches a deliberately reintroduced
bad import, the kill switch actually skips the Ollama call, the circuit
breaker actually trips and requires `--ack-report` to clear, and a
non-resident model correctly skips the call without mutating the
mechanical rubric's own status. 39/39 tests, fixtures only — no real
chat content touched. Durable control defaults off, matching the
established pattern from `operator_eval.py`/`judge_eval.py`.

## Status

Task #58 (Qwen3.8-27B eval) closed — correctly rejected, well
documented for a future recheck. The catalog-drowning fix (tracked under
`2026-09-05bc`) is closed and live-verified. Task #59 (semantic judge
build) closed.
