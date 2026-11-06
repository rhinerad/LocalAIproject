# 2026-09-05ah — Status sync: inline media v1 + tracing PR 3 both shipped

## Scope

Operator-facing tracking entry. Two real builds landed
(`2026-09-05ae`, `2026-09-05ag`), both already self-documented in
TODO.md. No new production work from this entry.

## 2026-09-05ae — Inline generated-media display v1

Shipped exactly to the approved v1 cut: `media_artifacts` locator
persisted on the assistant turn for complete story stills, restored by
re-resolving on every GET (no cached bytes), fail-closed on both
out-of-root locators (`uploads/`, `chats/`, `equal_shares/` all
confirmed rejected even under a widened test root) and hash mismatch
(409, does not serve the new bytes under the old turn). `comfy_generate`
correctly not collected this pass. `APP_REVISION` bumped to
`2026-09-05-generated-media-v1-r77` (expected — real GUI-visible
behavior change). 23/23 tests pass, including the two fail-closed cases
explicitly required by the design.

## 2026-09-05ag — tracing.py PR 3 (agent.answer wiring)

Shipped exactly to the approved plan: real `turn`/`route`/`reason`/`tool`
span tree wired into `agent.answer()`, `record_decision()` allow-list
respected, hop-0 reuse handled as an attribute rather than a fake span,
empty-completion retry gets its own hop with `skip_farm=true`. The
motivating use case is proven: a reconstructed empty-completion turn
produced a real two-row span join (hop 0 thinking-only, hop 1 retry
still empty, turn `output_summary` never blank) — this was the original
justification for building tracing.py at all. `LOCAL_AGENT_TRACING=0`
confirmed to produce an identical reply with no DB file. 98/98 tests
pass. PR 4 (MCP JSONL binary offset, completes the mug-image
investigation recipe) is next and last in the plan.

## What was not done

No PR 4. No APP_REVISION bump from the tracing work (correct — it's a
backend-only side channel). No `comfy_job_status` polling or video cards
(media v2, correctly deferred).
