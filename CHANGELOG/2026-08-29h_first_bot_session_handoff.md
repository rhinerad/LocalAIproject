# 2026-08-29 — first bot session handoff (local agent + Zing + Harmontown pause)

## What changed

- Rhine created **first bot** and asked it to keep local agent and Harmontown moving while he is away, then (5:21 PM ET) to **stop Harmontown** and focus on local agent, then to install Seedleap Zing-0.5 in WSL.
- Rhine's new standing rule (7:03 PM ET): **anything done on any project must be updated in that project's handoff folder and repo the same session**, so other LLMs can see it. Chat is not the record.
- Local-agent PowerInfer docs/tests from this bot's session (already in CHANGELOG, listed here so the session is one place):
  - `docs/POWERINFER_FATRELU_OPERATOR_DECISION_2026-08-29.md`
  - `CHANGELOG/2026-08-29f_powerinfer_fatrelu_operator_decision.md`
  - `CHANGELOG/2026-08-29g_powerinfer_relullama_test_coverage.md` (20/20 `test_powerinfer_pipeline` at 6:13 PM ET; live PoC ReluLLaMA-7B; ProSparse parked)
- `GROK_STATUS.md` rewritten with a 2026-08-29 current section (PowerInfer, Harmontown pause, Zing smoke, watch schedule).
- Zing-0.5 WSL install + 16GB smoke: see `A:\Users\rhine\zing-local\HANDOFF_2026-08-29.md`. Not part of this git-less tree; recorded here because first bot did it in the same operator session.
- Harmontown: Windows diarize-core test fix only; then paused. Repo note: `docs/FIRST_BOT_SESSION_2026-08-29.md` in the Harmontown tree.

Did **not** resume Equal Shares, compile PowerInfer, bypass relu-gate, download Harmontown audio, or start LoRA training.

## Why

Other agents (Claude Code, Codex, other Grok sessions) only see files. This session's Zing install, Harmontown pause, and the "write the handoff" rule were chat-only until this entry.

## The evidence

- FATReLU gate: `check_relu_gate.py` on the ProSparse vault → exit 2, `hidden_act=fatrelu`.
- ReluLLaMA tests: `python -m unittest test_powerinfer_pipeline -v` from `local_agent/` → Ran 20 tests, OK, 6:13 PM ET.
- Zing smoke: `/root/zing/zing-world-model/outputs/wasd_fast/wasd_fast.mp4` (64 KB, 448×256, 17 frames @ 24 fps), peak 15847/16303 MiB, `--local-attn-size 33 --sink-size 5`.
- Routine `Keep projects moving` now also requires same-session CHANGELOG/GROK_STATUS/Zing handoff writes.

## What was verified after

This file plus `GROK_STATUS.md` exist in the canonical handoff tree. Zing and Harmontown notes are on their own disks (paths above). No GPU job was started to re-verify Zing or PowerInfer in this write-up.

## What is still unverified

- PowerInfer native compile (CUDA Toolkit 12.8+ and VS 2022 C++ still missing).
- Zing live WASD session (offline smoke only).
- Harmontown Episode 43 listening / G1 gold (human).
