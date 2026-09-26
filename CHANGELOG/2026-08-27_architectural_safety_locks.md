# 2026-08-27 — Architectural safety locks

## Completed high-priority fixes

### Verified GPU eviction before CPU routing

`local_agent/router.py` now unloads every resident local Ollama GPU model and
polls `/api/ps` for up to 15 seconds before allowing a CPU handoff. A stale,
unreadable, or timed-out inventory is an explicit safe refusal rather than a
possible VRAM collision with ComfyUI. Status polling never triggers eviction.

### Lease-before-send phone scheduling

`local_agent/phone_scheduler.py` now writes a durable dispatch lease before it
queues any LXMF message. A second bridge loop observes that lease and cannot
send the same counter. If a process dies while a send result is unknown, the
job becomes `uncertain`; it is not silently retried and duplicated over mesh.

### Bounded feedback encryption queue

`local_agent/feedback_manager.py` now bounds its idle-only AES-GCM work queue
to 256 records. On overflow, the oldest record is displaced and a metadata-only
fingerprint is quarantined. Records that cannot be encrypted after three tries
are likewise quarantined without persisting a plaintext payload.

## Verification

- `python local_agent/test_router_switching.py` — 25 passed.
- `python local_agent/test_phone_scheduler.py` — 12 passed.
- `python local_agent/test_feedback.py` — 7 passed.

## Context artifact boundary

`local_agent/artifacts.py` now keeps oversized tool results in a local,
fingerprinted JSON artifact and returns a compact pointer for the live model
context. `agent.py` applies that boundary to every tool result at 2,400
characters. The GUI/audit event keeps its operator-facing output behavior,
while the next model hop avoids reprocessing a giant raw response.

- `python local_agent/test_artifacts.py` — 3 passed.
- `python local_agent/test_native_tool_calling.py` — 28 passed, including an
  end-to-end multi-hop artifact-pointer check.

## Byte-stable prompt prefix

`local_agent/prompt_prefix.py` memoizes deterministic static, recalled-memory,
and scoped-project prefix renderers. `agent.system_prompt()` now assembles them
in one stable order before dynamic turn evidence, helping compatible local
Ollama/llama.cpp runners reuse their prefix/KV cache across turns.

- `python local_agent/test_prompt_prefix.py` — 2 passed.
- `python local_agent/test_context_resilience.py` — 5 passed.

## CPU context and memory pipeline (ready, model-gated)

Added `context_compactor.py` for strict-JSON older-turn summaries and
`memory_extractor.py` for asynchronous post-turn extraction of stable,
non-sensitive facts. Both target only `llama3.1:8b` on the private CPU host,
send `num_gpu: 0`, and use `keep_alive: "0"`. Until that exact model is
installed, compaction deterministically falls back to the existing digest and
memory extraction remains dormant. An attempted local `ollama pull` was blocked
by the workstation's outbound-network policy, so no substitute model was used.

- `python local_agent/test_context_compactor.py` — 3 passed.
- `python local_agent/test_memory_extractor.py` — 3 passed.

The normal launcher now has `-EnsureContextModel`, which pulls only
`llama3.1:8b` into the CPU-only Ollama service when explicitly invoked. It is
never configured as a chat model or a GPU model.
