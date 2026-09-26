# 2026-09-01 — Native multi-tool latency and cross-chat scope correction

## Problem

The native-tool regression suite showed that two read-only tools issued in one
model hop took about 1.4 seconds even though their work overlapped. This made
the interface feel serial and risked failing the intended one-hop multi-tool
capability.

## Cause

Each follow-up model hop repeated GPU telemetry, including a 400 ms loopback
ComfyUI connection probe. A standalone request without a conversation ID also
performed a cross-chat retrieval despite having no durable conversation
boundary to scope that lookup.

## Changes

- `local_agent/agent.py`
  - Cross-chat retrieval now requires a real conversation ID. Identified chats
    retain the existing bounded retrieval behavior; ad-hoc calls do not search
    unrelated stored conversations.
  - One `agent.answer()` call reuses its GPU-state snapshot only after a hop
    containing exclusively tools from the audited read-only allowlist. Any
    other tool invalidates the snapshot before the next model call, so
    render/write/scheduler/media paths still perform a fresh safety check.
- `local_agent/router.py`
  - Reduced the loopback-only ComfyUI status probe limit from 400 ms to 20 ms.
    A timeout remains fail-closed through the surrounding GPU checks; a local
    listener accepts immediately when present.
- `local_agent/test_native_tool_calling.py`
  - Added regressions proving that an identified boundary is required before
    prior-chat lookup and that a read-only tool follow-up reuses exactly one
    GPU-status snapshot.

## Verification

Completed without starting ComfyUI, loading a model, or rendering:

```text
python local_agent\test_native_tool_calling.py  # 45 passed
python local_agent\test_router_switching.py     # 41 passed
python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v
                                                 # 124/124 valid
```

The focused two-read-only-tool timing regression now passes, confirming their
0.3-second waits overlap within the one-hop budget.
