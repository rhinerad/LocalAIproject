# 2026-09-02 — Phase 1 engine evaluation: read-in-full + TinyEngine research

## Scope

Continuing Phase 1 (engine architecture evaluation) per the operator's own
gate in `TODO.md`, after declining to start Phase 2 harness-optimization
work (context compaction middleware / supervisor loop) that the operator
had just blocked pending this decision. Research and documentation only —
no GPU load, no model registration, no code change.

## Task 1 — PowerInfer: re-read in full, no new decision made

Re-read `tools/powerinfer/README.md` and `work/POWERINFER_STATUS_2026-08-30.md`
end to end. Note: there is no `tools/powerinfer/STATUS.md` file — the README
carries that role; `TODO.md`'s Phase 1 section is corrected to say so.

Confirmed state, nothing new found:
- `ReluLLaMA-7B` — mechanically proven (native `sm_120` CUDA build, 20-turn
  cold/warm acceptance gate) but failed 9/10 elementary instruction-format
  cases; diagnostic-only, not eligible for registration.
- `TurboSparse-Mistral` (`...20260830b`) — parked; 32/32 `o_proj` edited,
  2.1e-4 max drift, but calibrated on 8 *synthetic* pairs only. Predictor
  rebuild is refused by the pipeline until ≥32 *operator-approved* pairs
  exist.
- Checked `review-only/turbosparse-mistral-projected-abliteration/`: only
  `operator-source-safe-subset.UNAPPROVED.jsonl` is present. A prior
  session's spec called for three more files
  (`reviewer-worksheet.md`, `DRAFT-NOT-OPERATOR-APPROVED.md`,
  `validation-report...txt`, and a 32-pair draft JSONL) — none of those are
  on disk. That draft is **incomplete**, not merely awaiting approval; this
  is recorded in `TODO.md` so it isn't mistaken for "ready to approve."
- `Bamboo-DPO 7B` — intake mechanically complete (CUDA sparse load, 3,024
  MiB FFN offload) but prompt/chat-template contract unresolved, blocking
  its own quality gate.

No decision was made here — which route to invest further GPU/calibration
effort in is recorded in `TODO.md` as an explicit operator decision (three
options laid out: finish+approve the 32-pair TurboSparse set, resolve
Bamboo-DPO's prompt contract, or drop PowerInfer and stay on Ollama).

## Task 2 — TinyEngine: researched, finding recorded

Web search on `mit-han-lab/tinyengine` (the literal "TinyEngine" the
operator named): it is a **microcontroller-only** inference library —
MCUNet family, benchmarked on an STM32H743 with a 512 KB peak-memory / 2 MB
flash budget. No path to RTX 5080/Ryzen desktop inference; it is not
comparable to llama.cpp/Ollama/PowerInfer for this agent. Ruled out without
needing an intake.

Found a same-lab, differently-named project that likely is what was
intended: `mit-han-lab/TinyChatEngine` — supports x86/ARM/CUDA, with a CUDA
backend for compute capability ≥ 6.1 (RTX 5080 qualifies). This is a real,
not-yet-started candidate (no hash-pinned source, no isolated environment,
no loopback test) — recorded in `TODO.md` as needing an operator
clarification (was "TinyEngine" shorthand for TinyChatEngine?) before any
intake work begins.

Sources: https://github.com/mit-han-lab/tinyengine ,
https://github.com/mit-han-lab/TinyChatEngine

## What was not done

No PowerInfer decision made. No TinyChatEngine intake started (no clone, no
hash pin, no environment). No Phase 1 milestone checked. No Phase 2 work
(the harness-optimization spec the operator had actually asked for in the
same session) was started, per the operator's own choice to hold on that
until this phase closes.

## What's still open

Two explicit operator decisions block the Phase 1 milestone: (1) which
PowerInfer route to pursue, if any; (2) whether "TinyEngine" meant the MCU
project (ruled out) or TinyChatEngine (real candidate, intake not started).
