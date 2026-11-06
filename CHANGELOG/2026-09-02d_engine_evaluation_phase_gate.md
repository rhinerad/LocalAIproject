# 2026-09-02 — TODO.md: engine-architecture evaluation phase gate added

## Scope

Operator directive: add a two-phase backlog to `TODO.md`. Phase 1 (inference
engine architecture evaluation — PowerInfer vs. TinyEngine, final decision)
is active and blocks Phase 2 (KV cache quantization, sliding-window context
summarizer, RAG-first Chroma retrieval, swarm offload to "The Farm").
Documentation only — no code, config, or running process touched.

## What was done

Added two new top-of-file sections to `TODO.md`: `PHASE 1: Engine
Architecture Evaluation (ACTIVE...)` and `PHASE 2: Context & Memory
Optimization — BLOCKED by Phase 1`, exactly as the operator specified, ahead
of the existing `Worker farm` section.

## Discrepancies found and recorded (not silently smoothed over)

Reviewed the existing `TODO.md` and `CLAUDE.md` before writing this, per
this project's standing rule that verification means checking the actual
record, not assuming a request's framing is current. Three things in the
operator's requested framing don't match what's already on file, and are
called out inline in the new Phase 1 section rather than overwritten:

1. **PowerInfer is not at square one.** `ReluLLaMA-7B` was already dumped,
   calibrated, and quality-gated — it failed 9/10 instruction cases and was
   rejected for promotion. `TurboSparse-Mistral` is explicitly *parked*
   pending an operator-approved 32-pair calibration set, not "under active
   testing." Task 1 is rescoped as a resume/decide task, not a fresh test.
2. **TinyEngine has zero prior evaluation in this repo** — confirmed via
   `TODO.md`; no doc, no intake script, nothing. Task 2 is flagged as
   genuine from-scratch research, unlike Task 1.
3. **"Swarm offload to The Farm" is largely already built**, not a
   from-scratch design task: the Redis/Celery worker farm is live, a
   WireGuard hub-and-spoke network is standing, a Mac worker is connected
   and `connectivity_probe`-verified end to end, and a real workload
   (`judge_transcript`) shipped the same day this request came in (see
   `2026-09-02c_judge_evaluation_workflow.md`). The operator's spec named a
   different transport (ZeroMQ/FastAPI) than what's running (Celery/Redis
   over WireGuard). Recorded as a note to reconcile against the existing
   farm when Phase 1 unblocks, rather than building a second, redundant
   transport.

Nothing in the existing 748-line `TODO.md` was removed or rewritten to fit
the new framing — the new section sits alongside the existing record and
points back to it.

## Verification

Documentation-only change; verified by re-reading the edited section of
`TODO.md` after the edit for internal consistency (no test/build applicable).

## What was not done

No engine research, no TinyEngine intake, no PowerInfer decision, no worker
farm changes. No GPU, no render, no model load, no queue/broker action.
Phase 1's milestone (final engine decision) is not started, so Phase 2
remains blocked exactly as directed.
