# 2026-09-02 — recorded worker-farm per-machine model policy + first hardware entry

## Scope

Operator noted a standing fact worth preserving for future sessions: worker
farm machines can each run whichever LLM actually fits their own hardware —
there's no requirement for a uniform model across the fleet — and gave the
first connected test machine's specs. Documentation only.

## What was done

Added two sections to `local_agent/worker_farm/README.md`:
- **"Per-worker model choice — no fleet-wide fixed model"**: records that
  model selection per node is a hardware-fit decision made at that node's
  setup time, and flags that any future workflow dispatching model-bearing
  jobs (e.g. the LLM-based judge follow-up noted in `TODO.md`) must not
  assume a uniform model is available fleet-wide.
- **"Known worker machines"** table: first entry is `mac_worker`
  (`Louises-MacBook-Pro.local`), 2019 MacBook Pro, 16 GB RAM, macOS 13.7.8
  x86_64 — the first secondary node connected, per the operator's own
  framing, to prove connectivity before the rest of the fleet joins. Noted
  its actual current state (WireGuard-connected, `probe`+`judge` queues
  granted, no LLM installed/routed there yet) rather than implying more
  than what CHANGELOG/TODO already established, and flagged its 16 GB RAM
  as a real ceiling on what could run there later.

This is also the first entry in the node-inventory step that both
`docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md` and `TODO.md`'s
10-node deferred section call for and neither had actually started.

## What was not done

No model was installed or configured on `mac_worker`. No routing/dispatch
code was changed. No other machine's hardware was recorded (none have
connected yet).
