# 2026-09-04z — Option B PR 2 live re-verify (six cases + bug-fix probes)

Date: 2026-09-04. Host: DuranGamingPC. Times local (EDT, UTC-4).
Id from `python scripts/next_changelog_id.py`: **2026-09-04z**.

Rockernow ComfyUI `127.0.0.1:8188` (pid **26476**, parent 38704, started 18:03:53 — not restarted during this run). GPU Ollama `:11434`. Target 14B: `huihui_ai/qwen3-abliterated:14b`.

Pass criteria: `Decision.detail["timeshare"]` + nvidia-smi. **`status()["gpu_busy"]` is a negative control only** (it stayed True on idle-8188 even after a successful claim).

Raw JSON: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_pr2_live_verify.json`
Audit log: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_pr2_audit.log`
Script: `A:\Users\rhine\.grok\long-running-background-tasks\timeshare_pr2_live_verify.py`

Mocked suite from PR 2 remains **91/91** (`test_router_comfy_timeshare` + `test_router_switching`) plus **3/3** `test_router_status_busy`. This entry is live evidence.

## Pre-flight (8188 exclusive)

Before and during the run: queue empty at start; only one listener on 8188 (pid 26476); the second `main.py` (38704) is its parent, same CreationDate, not a second instance. No other `timeshare_*` / `comfy_generate` / `restart_comfy` process besides this verifier (pid 42716). No competing generate on `/queue`.

## Original six happy-path outcomes — unchanged vs 2026-09-04u

Queue listing is now **urllib `/queue` timeout=1 first** (MCP list only if urllib is unreadable). Occupancy no longer path-matches ComfyUI python or uses the 2000–3200 band. None of that changed the six outcomes.

### Case 1 — Idle 8188 → 14B — PASS

- Queue empty, 8188 listening, owners released.
- nvidia-smi before: **348 MiB**. Procs include Rockernow `standalone-env\python.exe` (full path; stem `python`) plus Brave. Occupancy `powerinfer_compute: []`.
- `decide(auto, primary 14B)` **5.579 s**. `timeshare.path=clear_vram`, `queue.source=urllib`, **n_mcp_queue_lists=0**, one `clear_vram` (`spawn=False`, `lock_timeout=0.2`).
- Post-`/free` used_after **348 MiB** (≤800). See remaining-unsafe 5 below — this is **not** a GPU-resident drop.
- GPU generate: **PONG** in **79.426 s**. Resident `huihui_ai/qwen3-abliterated:14b`. nvidia-smi after load **11487 MiB**.
- Wall **85.096 s**. Reason: `GPU free — cleared idle ComfyUI`.

### Case 2 — Hop-N no second `/free` — PASS

- Same process, 14B still in `/api/ps`, VRAM **11487 MiB**.
- `decide` **11.914 s** (timer includes a `status()` negative-control call). `timeshare.path=already_claimed`. **n_clears=0**. `queue.source=urllib`.
- Still GPU 14B. `decision.gpu_busy` False.

### Case 3 — Owner live PID → CPU + evict — PASS

- Wrote `render_queue_owner.json` pid **42716** (this verifier), then restored the original file.
- `decide` **1.636 s**. **n_clears=0**. `timeshare` absent (`gpu_busy()` returns on live owner before 8188).
- Tier **cpu**, model `huihui_ai/qwen3-abliterated:8b`. Reason includes `render queue claimed by live pid 42716`.
- Evict: VRAM 11487 → **348 MiB**.

### Case 4b — Post-generate `/free` then 14B — PASS

(Case 4a is the urllib-nonempty probe, below.)

- Live SD1.5 512² 20 steps while 4a held the queue, then queue empty.
- nvidia-smi post-generate **2462 MiB** (matches 2026-09-04u's 2461 resident band).
- `decide` **3.095 s**. One `clear_vram`. used_before **2462** → used_after **414 MiB** (≤800). **Δ 2048 MiB**. `queue.source=urllib`.
- GPU generate: **PONG** in **73.884 s**. Resident 14B. VRAM **11701 MiB**.
- Wall **77.063 s**.

### Case 5 — Farm tool turn no `/free` — PASS

- Farm reachable.
- `decide(auto, prompt="list the files in the current folder")` **0.990 s**.
- Tier **farm**, model `richardyoung/qwythos-9b-abliterated:latest`. `timeshare.path=farm_skip`. **n_clears=0**.
- 14B left resident (11701 MiB). `decision.gpu_busy` stayed True (8188).

### Case 6 — Kill switch `EQUAL_SHARES_COMFY_TIMESHARE=0` — PASS

- `decide` **1.580 s**. `timeshare` null. **n_clears=0**. `decision.gpu_busy` True, reason still 8188-listening.
- CPU 8B fallback, then evict (11701 → **414 MiB**). Blunt 8188-busy behavior restored.

## PR 2 bug-fix probes (live)

### A / B — Host-GPU gate: CPU-only and Qwythos pins — PASS

- `_timeshare_would_load_host_gpu("auto", equal-shares-cpu, …)` **False**. `decide` **1.483 s**. `timeshare` null. **n_clears=0**. VRAM stayed 348.
- `_timeshare_would_load_host_gpu("auto", Qwythos, …)` **False**. `decide` **1.472 s**. `timeshare` null. **n_clears=0**. VRAM stayed 348.
- FALLBACK/14B path still entered the gate in cases 1/2/4b (not regressed).

### 4a — Non-empty urllib queue never reaches MCP — PASS

- ComfyUI `/queue` at decide: `running=1`, `pending=0`.
- `decide` **1.552 s**. `timeshare.path=cpu_fallback`, `queue.source=urllib`, `running=1`.
- **n_mcp_queue_lists=0**. **n_clears=0**. CPU 8B. This is the live proof of the urllib-first flip.

### Python occupancy is not a block — PASS (live path form)

- This host's nvidia-smi names ComfyUI as
  `A:\Users\rhine\ComfyUI-Installs\Rockernow\standalone-env\python.exe`
  (full path, stem `python`), not a bare `python.exe`.
- Case 1 still `/free`'d with that row present (`python_not_occupancy`). Option-A path-match / foreign-name filter is gone; names-only `python.exe` remains covered by the mocked suite (`test_bare_python_exe_8188_used_345_still_frees`).

### PowerInfer proc detection — not live-exercised (backend not on the card)

- Occupancy `powerinfer_compute` was `[]` on every claim. TCP 8080 was not a false occupancy. Names-only `server.exe` + `backend_up` remains mocked (`test_huihui_names_only_server_exe_8080_no_free`).

## Remaining-unsafe 5 — still open, correctly not closed

`_clear_vram_for_timeshare` still returns `ok=True` whenever post-`/free` nvidia-smi is **≤800**, including **348 → 348**.

| | used_before | used_after | `clear_vram.ok` | GPU-resident drop? |
|---|---|---|---|---|
| Case 1 idle/loaded-idle band | 348 | 348 | True | **No** (Δ 0). Remaining-unsafe 5. |
| Case 4b post-generate | 2462 | 414 | True | **Yes** (Δ 2048). This is the actual `/free`. |

Do not read case 1's success token as “we freed GPU-resident weights.” DynamicVRAM still hides the claim window at ~345 MiB. Case 4b is the only live proof `/free` moved nvidia-smi.

## Audit lines

Claim log (no gpu_gate constant; `agent.py` still untouched):

```
2026-09-04 22:47:30,049 WARNING ComfyUI timeshare hook claimed the GPU (port 8188 listening; cleared idle ComfyUI)
2026-09-04 22:49:00,406 WARNING ComfyUI timeshare hook claimed the GPU (port 8188 listening; already claimed)
2026-09-04 22:49:42,616 WARNING ComfyUI timeshare hook claimed the GPU (port 8188 listening; cleared idle ComfyUI)
```

Did **not** fire on CPU-only, Qwythos pin, owner-CPU, urllib-busy, farm skip, or kill-switch.

## Close-out

Option B (explicit time-sharing via `clear_vram`) is **fully closed**, including the PR 2 correctness fixes (urllib-first queue, occupancy strip, host-GPU gate). Follow-ups that remain are **not** Option B: `agent.py` sidebar `gpu_gate.request()` when 8188-only, and `status()` third badge state. TOCTOU / manual Queue Prompt / remaining-unsafe 5 stay accepted residuals.
