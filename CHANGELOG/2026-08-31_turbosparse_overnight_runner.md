# 2026-08-31 — TurboSparse overnight gated runner

## Added

- `tools/powerinfer/START_TURBOSPARSE_OVERNIGHT.ps1` and a `.cmd` launcher.
- A one-shot app automation named **TurboSparse overnight gated rebuild** for
  the next local 2:05 AM window.

## Safety contract

- Waits until after the configured local time, then requires `router.gpu_busy()`
  to report an idle GPU and requires temperature at or below 70 C.
- It never starts, stops, or modifies ComfyUI or any render process.
- It stops its own GPU child process at the fixed 82 C emergency ceiling.
- It refuses to run without the external file of at least 32
  operator-approved contrastive pairs. A missing file is a legitimate blocked
  status, not a reason to reuse the synthetic eight-pair checkpoint.
- It creates a new vault bundle and source output only; it cannot overwrite
  the `20260830b` exploratory checkpoint or prior evidence.

## Scope

With valid pairs, the unattended portion creates the new immutable projected
edit, records the exact ChatML prompt contract, acquires the public C4
calibration manifest, and performs the sparse activation profile. Predictor
training is deliberately opt-in via `-RunPredictorTraining`; conversion,
loopback launch, and the strict two-turn JSON quality capture remain separate
evidence gates.
