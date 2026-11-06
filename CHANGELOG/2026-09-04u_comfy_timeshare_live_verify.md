# 2026-09-04u — Option B ComfyUI GPU timeshare live verify (six cases)

Date: 2026-09-04. Host: DuranGamingPC. Times America/New_York (UTC-4).
Rockernow ComfyUI `127.0.0.1:8188` idle at start (queue empty). GPU Ollama `:11434`.
Target 14B: `huihui_ai/qwen3-abliterated:14b`.

Raw JSON: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_live_verify.json`
Audit log: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_gpu_gate_audit.log`
Script: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_live_verify.py`

Mocked suite remains 110/110. This entry is live evidence only.

## gpu_gate audit line (required)

Timeshare still bypasses the sidebar card (`agent.py` skips `gpu_gate.request()` while `gpu_busy()` is True on 8188). Each claim logs logger `local_agent.router.timeshare` at WARNING. Live case 1 example:

```
2026-09-04 17:09:37,305 WARNING ComfyUI timeshare hook claimed the GPU; gpu_busy() was True going in (port 8188 listening). The sidebar gpu_gate permission card did not fire because agent.py still treats 8188 as busy. This is an interim gpu_gate bypass; follow-up is the TODO.md agent.py ticket (CHANGELOG 2026-09-04q).
```

Same line also fired on hop-N already-claimed (17:10:47) and post-generate `/free` (17:11:31). It did **not** fire on owner-CPU, farm skip, or kill-switch.

## Case 1 — Idle 8188 → 14B — PASS

- Queue empty, 8188 listening, owner PID 16900 dead (file present but released).
- nvidia-smi before: **347 MiB**.
- `decide(auto, primary 14B)` 6.395 s. `timeshare.path=clear_vram`. One `mcp_client.call("clear_vram", spawn=False, lock_timeout=0.2)`.
- Post-`/free` used_after **347 MiB** (≤800). Occupancy was idle-open, not the 2459 band.
- GPU generate: **PONG** in 65.201 s. Resident `huihui_ai/qwen3-abliterated:14b`. nvidia-smi after load **11634 MiB**.
- Wall 71.716 s. Reason: `GPU free — cleared idle ComfyUI`.

## Case 2 — Hop-N no second `/free` — PASS

- Same process, 14B still in `/api/ps`, VRAM 11634 MiB.
- `decide` 5.056 s. `timeshare.path=already_claimed`. **n_clears=0**.
- Recheck owners+queue idle. Still GPU 14B. gpu_busy False.

## Case 3 — Owner live PID → CPU + evict — PASS

- Wrote `render_queue_owner.json` pid **44176** (this verifier), then restored the original file.
- `decide` 4.974 s. **n_clears=0**. `timeshare` absent (hook never entered: `gpu_busy()` returns on live owner before 8188).
- Tier **cpu**, model `huihui_ai/qwen3-abliterated:8b`, `num_gpu=0`. Reason includes `render queue claimed by live pid 44176`.
- Evict verified: `/api/ps` [] after, VRAM 11634 → **347 MiB**.

## Case 4 — Post-generate `/free` then 14B — PASS

- `comfy_generate` SD1.5 512² 8 steps, prompt_id `c9f5d1fb-8cd3-4891-9618-844bacaf91e2`, enqueue 38.575 s then wait for empty queue.
- nvidia-smi post-generate **2461 MiB** (matches the 2459 resident band).
- `decide` 6.575 s. One `clear_vram`. used_before 2461 → used_after **413 MiB** (≤800).
- GPU generate: **PONG** in 50.371 s. Resident 14B. VRAM **11700 MiB**.
- Wall 89.014 s.

## Case 5 — Farm tool turn no `/free` — PASS

- Farm snapshot refreshed live (`farm_reachable=true`).
- `decide(auto, prompt="list the files in the current folder")` 2.324 s.
- Tier **farm**, model `richardyoung/qwythos-9b-abliterated:latest`. `timeshare.path=farm_skip`. **n_clears=0**.
- 14B left resident (11700 MiB unchanged). gpu_busy stayed True (8188).

## Case 6 — Kill switch `EQUAL_SHARES_COMFY_TIMESHARE=0` — PASS

- `decide` 4.945 s. `timeshare` null. **n_clears=0**. gpu_busy True, reason ends `a ComfyUI backend is listening on port 8188`.
- CPU 8B fallback, then evict (11700 → 413 MiB, `/api/ps` []). Blunt 8188-busy behavior restored.

## Notes

- MCP warmup `get_system_stats` without `action` failed validation; `/free` still worked because an earlier session left the MCP child up, and queue listing used MCP `source=mcp` with spawn=False.
- Option B live path is closed. Remaining follow-up: `agent.py` sidebar `gpu_gate.request()` when 8188-only (TODO, origin 2026-09-04q). TOCTOU / manual Queue Prompt remain accepted residuals.
