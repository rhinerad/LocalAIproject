# 2026-08-24 — Local-agent context resilience

## What changed

- Added `local_agent/OPERATING_MEMORY.md`, a compact reviewed policy record
  loaded into every new and existing local-agent chat.
- Replaced first-message pinning in `agent._trim_context()` with bounded
  continuity compaction: the active tail and complete native tool exchange are
  preserved, while older operator requests become a small non-authoritative
  continuity record.
- Reduced model-context copies of tool results and pre-fetched URL content while
  retaining the full local evidence/result files and GUI action cards.
- Made `memory.recall()` enforce its 1 KB prompt budget instead of exceeding it
  and merely reporting that it had overflowed.
- Added `test_context_resilience.py` and bumped the local-agent revision to r27
  so the launcher replaces the stale process.

## Why

Recent chats contained 24 and 54 messages, including opening pastes over 12 KB
and 16 KB. The old algorithm permanently kept the first user message, so it
removed dozens of newer turns when the CPU route used its 8K window. That loses
the instructions most likely to matter while preserving stale pasted text.

## Evidence

- Recent-chat inspection: `5b3352e81fdb4f08.json` had a 12,391-character
  message; `ef558c62ae034fb3.json` had a 16,494-character message and 54 turns.
- `memory.recall()` previously returned 1,050 bytes despite its declared
  1,024-byte cap.

## Verification

- `python local_agent/test_context_resilience.py` — passed: reviewed memory
  reaches a new chat, giant opening paste is no longer pinned, and native tool
  call/result exchanges stay intact.
- `python local_agent/test_general_assistant.py` — passed.
- `python local_agent/test_native_tool_calling.py` — 10/10 passed.
- `python local_agent/test_router_switching.py` — 14/14 passed.
- `python local_agent/test_ctx_ceiling.py` — all checks passed.

## Still unverified

- A long real GUI chat must be exercised after the r27 restart to measure the
  smaller context-compaction notices in the browser. No render was started and
  no media evidence was modified.
