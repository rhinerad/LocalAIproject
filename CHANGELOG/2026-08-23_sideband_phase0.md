# 2026-08-23 — Sideband/LXMF Android-agent Phase 0

## What changed

- Added `local_agent/UPGRADE/notes/sideband_agent_stack.md`, a current-documentation
  recommendation and Phase 1/2 plan for a Sideband/LXMF remote agent.
- Added a README pointer making the approval gate visible to the operator.

## Evidence

- Inspected the current local-agent seams: `agent.answer()` accepts history and an
  event callback without an HTTP dependency; `store.py` is plain JSON and does not
  yet have a source field; `tools.call()` remains the fixed-whitelist dispatch point.
- Confirmed `RNS` and `LXMF` are not installed in the active local-agent Python
  environment.  No packages were installed.
- Checked upstream LXMF router/delivery examples, Reticulum destination/announce
  API, Sideband's LXMF compatibility/plugin/Windows documentation, and Buildozer's
  current WSL guidance.  Links are recorded in the Phase 0 note.

## Not changed

- No bridge, listener, Sideband fork, Android build, package download, render,
  pipeline state, tool whitelist or binding was changed.
- `server.py` remains localhost-only; Phase 1 requires explicit approval.

## Verification status

Documentation and seam audit complete.  Live Sideband/LXMF acceptance is correctly
**unverified** because Phase 1 has not been approved or implemented.
