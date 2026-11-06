# 2026-08-25 — Local-agent backlog reconciliation

## What changed

- Corrected the upgrade index and Sideband Phase-0 note to distinguish the
  completed Tier A workstation bridge from unstarted Tier B Android work.
- Recorded the remaining deliberately operator-gated items in the current
  handoff: anonymized real-task evaluation cases, feedback/exemplar review,
  the explicit 14B KV-cache measurement, advanced storyboard work, and Tier B
  phone media integration.

## Why

The desktop agent's core foundations are implemented, but stale planning text
could make a later session either redo Tier A or claim that review-dependent
work was ordinary unfinished code. The distinction matters for safety: none of
the remaining gates can be completed honestly without an operator decision,
approved source material, a model load, or a real device interaction.

## Verification

- `CHANGELOG/2026-08-23_sideband_phase1.md` records the Tier A implementation.
- `CHANGELOG/2026-08-23_sideband_live_pairing.md` records the real paired
  stock-Sideband turn.
- `python local_agent/test_lxmf_bridge.py` and `python local_agent/test_operator_eval.py`
  remain the no-model regression checks for the two relevant safe foundations.

## Still gated

No Android toolchain, Sideband fork, model load, render, external corpus, or
operator feedback/evaluation record was created by this reconciliation.
