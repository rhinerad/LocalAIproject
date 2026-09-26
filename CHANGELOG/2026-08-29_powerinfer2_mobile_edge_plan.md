# 2026-08-29 — Pixel mobile sparse-runtime evaluation boundary

## What changed

- Added `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`, a staged Pixel 10
  Pro plan that distinguishes the PowerInfer-2 paper from the currently
  documented upstream Android SmallThinker runtime.
- Added an inert, stdlib-only
  `local_agent/worker_farm/termux_powerinfer2_edge_worker.py` gateway contract
  and offline tests. It limits phone jobs to small `edge_text_inference`
  requests, requires an HTTPS private-overlay gateway, launches a configured
  local binary with a shell-free argument list, and performs at most one job in
  its required initial `--once` mode.
- Updated the TODO, worker-farm README, and Claude/current-handoff notes with
  the same security and verification boundaries.

## Security and architecture decisions

- Pixel 10 Pro is Tensor G5/TPU hardware, not a Qualcomm/Hexagon device. No
  NNAPI/Tensor runtime path is claimed because the inspected upstream Android
  guide documents no such backend.
- Android NDK compilation belongs on an x86_64 Linux/WSL build host; the
  documented NDK host tools are not Termux arm64 executables.
- The phone cannot connect directly to the loopback Redis/Celery broker and
  must never receive the workstation broker password or AES key. A future
  private-overlay, per-device authenticated gateway is required before any
  phone worker is enabled.

## Deliberate non-changes

- Did not download, convert, compile, install, root, launch, or route a mobile
  model/runtime.
- Did not start a queue, service, render, ComfyUI, desktop PowerInfer process,
  or GPU workload.

## Evidence

- Upstream SmallThinker documentation inspected on 2026-08-29 describes an
  Android NDK arm64 build, sparse Q4_0 models, `libaio`/`liburing`, and notes a
  possible Termux root requirement for its memory-efficient path. It does not
  document NNAPI/QNN/Hexagon options.
- Google Pixel 10 Pro official specifications list Tensor G5 and 16 GB RAM.
- Offline test evidence is recorded alongside the contract after the command
  below succeeds; no mobile live claim is made:

  `python -m unittest local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v`
