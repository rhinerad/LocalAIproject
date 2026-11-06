# 2026-08-31 — Phone automatic model routing

## Problem

A Sideband phone chat created while ComfyUI owned the GPU recorded the available
8B CPU fallback as its saved conversation model. The bridge then passed that
saved fallback back to `agent.answer()` on every later phone turn, preventing
the normal automatic router from returning to the GPU once it was free.

## Change

`local_agent/lxmf_agent.py` now treats an empty per-identity `model` field as
the automatic policy on every message. It passes no model pin to the agent in
that case, while still preserving an explicit model selected for that exact
paired identity. The stored conversation model remains a display/history value,
not an implicit phone routing override.

The bridge now calls a ComfyUI-caused CPU route a **temporary CPU fallback** in
the Sideband status message. This does not alter GPU ownership safeguards: a
phone never loads a GPU model while ComfyUI owns it.

## Verification

`python local_agent/test_lxmf_bridge.py` passed: 15 tests, including automatic
phone routing, explicit phone pin preservation, and the temporary-status label.

## Documentation

Updated `local_agent/README.md` and
`docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md`.
