# 2026-08-25 — Grok portfolio evidence docs (no GPU, no Android build)

## Why

Codex was already working the Sideband Tier B NumPy/`mesonpy` Android blocker.
A parallel Grok session took **documentation-only** upgrade-20 items so the two
agents would not share WSL, radios, or the GPU.

## Added (private tree, portfolio-safe)

- `GROK_STATUS.md` — coordination note for Codex.
- `docs/portfolio/experimental_rnode_inventory.md` — sanitized Heltec LoRa32 v3
  / SX1262 inventory and SF12 profile; no node IDs or keys.
- `docs/portfolio/radio_packet_experiment.md` — packet-delivery experiment
  design. **Not executed.**
- `docs/portfolio/vlm_lifecycle_benchmark.md` — exact-pair lazy-load timing
  method. **Not executed** (ComfyUI was on port 8188).
- `docs/portfolio/license_inventory.md` — draft candidate-module / Sideband
  license boundary. Not an SBOM and not a publish authorization.
- `docs/portfolio/public_repo_layout.md` — planned public tree. No repo created.
- `docs/portfolio/case_study_and_resume_bullets.md` — claim-checked copy from
  existing tests/changelogs.

## Not done / left with Codex

- Sideband custom APK / python-for-android NumPy recipe.
- Radio airtime experiment.
- VLM VRAM/latency measurement.
- Public GitHub extraction, secret scan, or screen-capture demo.
- Any Equal Shares render or ComfyUI job.

## Verified

- No ComfyUI, Ollama, WSL build, or radio command was started for this change.
- `docs/portfolio/` now contains the new files listed above.

## Unverified

- Hardware SKU of the phone-side board beyond “ESP32 LoRa V3 class.”
- Whether the phone is currently on SF12 (operator follow-up in the SF12
  changelog still applies).
