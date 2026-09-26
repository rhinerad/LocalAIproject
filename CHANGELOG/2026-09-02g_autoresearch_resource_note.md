# 2026-09-02 — catalogued karpathy/autoresearch as a reference resource

## Scope

Operator asked to add https://github.com/karpathy/autoresearch to "what we
can use for our harness." Documentation only — no clone, no run, no code
change.

## What was done

Verified the repo exists (it's real, MIT license, released March 2026,
~21k stars) and read the actual upstream README rather than relying on
search-snippet summaries. Recorded it in `TODO.md` under the Phase 2
(blocked) section as a bookmarked resource, not an active dependency.

## Important correction made while recording it

autoresearch is **not** a context-management/tool-orchestration agent
harness — it's an autonomous overnight *ML training experiment* loop: an
agent edits a single `train.py` (a simplified single-GPU nanochat GPT),
runs a fixed 5-minute training budget, keeps the change if validation
bits-per-byte improves, repeats (~12 experiments/hour). That's a different
problem than what this project's "Phase 2 harness" backlog is about
(context compaction, KV cache quantization, RAG-first retrieval, swarm
offload) or what LangChain Deep Agents/Letta-MemGPT actually do.

Recorded two places it might genuinely apply instead of assuming it fits
Phase 2 wholesale:
- Its edit→bounded-run→keep/discard-on-metric loop is a plausible design
  template for the Supervisor Loop item (Phase 2, still blocked).
- It may be a better fit for **automating PowerInfer's own predictor/
  calibration tuning** (Phase 1, Task 1) — that track already has a
  held-out-recall metric and bounded GPU runs; flagged there for the
  operator's Task 1 decision rather than decided unilaterally.

Also noted a community Windows/RTX fork, `jsegov/autoresearch-win-rtx`,
relevant given this host's actual hardware — not vetted, just noted.

## What was not done

No clone, no `uv sync`, no training run, no agent pointed at any of these
repos. This is a bookmark for later, explicitly marked as requiring a
separate approval before any execution.
