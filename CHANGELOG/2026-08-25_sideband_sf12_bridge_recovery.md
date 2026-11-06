# 2026-08-25 — Sideband bridge SF12 recovery

## Changed

- Updated the workstation RNode profile on `COM11` to spreading factor 12.
  Frequency, bandwidth, and coding rate remain `914875000`, `500000`, and `5`.
- Restarted the single local LXMF bridge after the prior bridge process was
  closed. The agent remains localhost-only at `127.0.0.1:8760`.
- `lxmf_agent.py` now ignores an unreadable optional vendored RNS copy instead
  of shadowing the working system installation.
- Installed the matching local Python package `LXMF 1.1.1` alongside existing
  `RNS 1.5.0`; no model, render, or ComfyUI service was started.

## Verified

- The bridge process remains running without a startup error.
- The active profile specifies `spreadingfactor = 12` on `COM11`.
- `test_lxmf_bridge.py`: 11/11 passed.
- `validate_h3_prompt.py`: 124/124 valid.

## Operator follow-up

Phone-side Sideband must be restarted after its B8EE RNode configuration change
so both radio endpoints operate with matching SF12 settings. End-to-end mesh
delivery remains experimental until a controlled delivery test is run.
