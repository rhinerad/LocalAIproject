# 2026-08-31 — Sideband media completion delivery

## Problem fixed

A paired Sideband image could be received, safely queued, and successfully
analyzed by the exact local Qwen2.5-VL Caption V4 runtime, yet the phone would
receive only the original “queued” reply. The media watcher writes its completed
result to the durable queue after the original chat turn has ended; no component
previously returned that result through LXMF.

## Change

- `tools.py` injects the authenticated phone identity, conversation ID, and
  request ID only at the trusted remote tool-dispatch seam for queued media
  tools. Model JSON cannot choose these values.
- `media_tools.py` copies that allowlisted metadata to the durable queue job,
  never to the vision prompt.
- `lxmf_agent.py` scans completed jobs once per bridge loop and sends an
  eligible result to the paired phone. A separate append-only delivery journal
  prevents duplicate delivery; it stores IDs and result hashes, not media
  content.
- A narrow recovery path matches older jobs to the existing attachment audit
  by immutable Sideband request upload directory. It cannot select desktop
  jobs and still requires an active paired identity.

## Security boundary preserved

No remote grant changed. Completed media delivery does not grant file writes,
builds, renders, or any new tool capability. File paths and raw tool status are
not sent to the phone. The bridge remains the only LXMF component and HTTP
remains loopback-only.

## Verification

- `python -m py_compile local_agent/lxmf_agent.py local_agent/media_tools.py local_agent/tools.py`
- `python local_agent/test_lxmf_bridge.py` — 17 tests passed, including
  one-time completed-media delivery with no model call.
- `python local_agent/test_native_tool_calling.py` — 31 tests passed.

## Live verification

The already completed Sideband image job `cb171dbbdb85425b` was recovered and
sent through LXMF after the bridge restart. The outbound delivery callback
recorded `kind: media_result` and state `8` (delivered), so this is not merely a
local queue submission. Its one-time journal row is in
`local_agent/runtime/lxmf/media_completion_delivery.jsonl`.
