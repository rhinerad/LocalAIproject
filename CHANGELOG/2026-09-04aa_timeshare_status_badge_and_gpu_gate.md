# 2026-09-04aa — Timeshare follow-ups: status() third state + sidebar gpu_gate

Date: 2026-09-04. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py`: **2026-09-04aa**.

Origins: CHANGELOG `2026-09-04q` (both tickets). Option B itself closed in `2026-09-04z`. This entry closes the last two follow-ups. **Timeshare is fully closed — no further follow-ups.**

## What landed

### 1. `status()` third state

`router.status()` still calls `gpu_busy()` (8188 TCP remains) and `decide(ensure_gpu_evicted=False)` (no `/free`). It does **not** call MCP or urllib `/queue`.

Third state when 8188 is listening, timeshare is enabled, owner files are idle, and the last-known queue (written by `_comfy_queue_idle` on a real timeshare probe) is idle or unknown:

- `timeshare_idle: true`
- `reason: "8188 up, idle, agent may claim"` (`STATUS_TIMESHARE_IDLE_REASON`)
- `gpu_busy` stays **True** (catalogue skip / routing unchanged)
- `routing_reason` remains the CPU fallback string

If the cache says queue not idle, or a live OWNER PID exists, the badge stays plain busy. GUI (`static/index.html`) shows the third-state sentence instead of “GPU busy — ComfyUI is running”.

### 2. `agent.py` sidebar `gpu_gate` before an idle-8188 claim

When 8188-only busy **and** `timeshare_claim_needs_sidebar_gate` (owners idle, host-GPU pin, not farm/Qwythos/CPU-only/PowerInfer), `agent.answer` calls `gpu_gate.request("chat reasoning model load", key=chat:…)` **before** hop-0 `decide()`. Pending/block → `prefer=cpu` → no `/free`. Granted → hop-0 may claim.

The router hook no longer logs a WARNING on claim (the 2026-09-04q interim bypass line).

Qwythos / CPU-only / live owner / farm tool turns still skip the card.

## Tests

- `test_router_status_busy.py`: third state from owners+cache; no urllib/MCP from `status()`; live owner and busy-queue cache stay plain busy.
- `test_agent_timeshare_gpu_gate.py`: predicate + `answer()` requests the sidebar before hop-0 `decide()` and passes `prefer=cpu` while pending.
- `test_router_comfy_timeshare.py`: happy-path claim has **no** timeshare WARNING.
- Combined with switching: **102/102** on the four files.

## Live verify (2026-09-04 23:12–23:14)

8188 pid 26476, queue empty, VRAM 414 MiB. No competing generate.

Raw JSON: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_followups_live_verify.json`

| Check | Result |
|---|---|
| Seed queue via `_comfy_queue_idle` (not `status()`) | idle, urllib, 0.014 s |
| `status()` | `timeshare_idle=true`, reason `8188 up, idle, agent may claim`, **n_urllib_queue=0**, 6.859 s. `gpu_busy` still True. |
| Sidebar | `gpu_gate` mode ask. One pending card `chat reasoning model load`. Hop-0 `decide` used `cpu`. Timeshare WARNING log **empty**. Answer 103 s on CPU 8B. |

`gpu_busy` True + third-state `reason` is the intended split: routing still treats 8188 as busy until a granted turn claims; the badge tells the operator the agent *may* claim.

## Close-out

TODO.md items for `status()` third state and `agent.py` gpu_gate are checked. Remaining-unsafe 5 / TOCTOU / manual Queue Prompt stay accepted residuals of Option B, not open tickets.
