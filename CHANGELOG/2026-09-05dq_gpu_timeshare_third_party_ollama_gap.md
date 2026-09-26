# 2026-09-05dq — Audit: GPU timeshare vs third-party Ollama loads (comfy-pilot)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05dq**.

Research/audit only. No code change. Prompted by `2026-09-05df`:
comfy-pilot's Ollama chat backend talked to `:11434`, promoted an
already-CPU-resident Huihui 8B onto the RTX 5080 (~7623 MiB, 94 %
util), then unloaded it with `keep_alive: 0`. That load was outside
`local_agent` routing.

Question: does GPU-gateway / timeshare / preflight / thermal rely on
internal bookkeeping of what *this* process loaded, or live hardware
state? If a third party loads VRAM, would the next `local_agent` turn
see it and adjust, or decide from a stale "we own the card" ledger?

## Verdict

**Most occupancy checks are live. There is no "we loaded model X"
ledger that `decide()` trusts over nvidia-smi.** Every routing turn
re-reads hardware and Ollama `/api/ps`.

**There is still a real, scoped gap: ownership attribution, not stale
VRAM numbers.** Live occupancy of GPU Ollama (`EQUAL_SHARES_GPU_HOST`,
default `127.0.0.1:11434`) is treated as *this agent's* occupancy
whenever `/api/ps` lists any resident model. A third party using that
same server (comfy-pilot's default) is invisible as a foreign owner.
`gpu_busy()` can return **not busy** at 7+ GB, and idle-Comfy timeshare
can take the **already_claimed** path, because the 8B tag is in
`GPU_MODELS`.

This is worth a later fix. Not a silent "hardware is ignored" bug.

## What is live (handled correctly)

`router.gpu_busy()` (`router.py` ~959) is called **before every
`decide()`**. Signals, any one enough:

1. **Owner JSON + live PID** (`render_queue_owner.json` and kin via
   `_pid_alive`). Stale dead-PID claims are ignored (df's 2026-08-10
   owner would not busy the card).
2. **TCP `:8188`** — `comfy_listening()` each call (20 ms). A ComfyUI
   backend up is busy *before* nvidia-smi.
3. **`nvidia-smi`** `memory.used` + `--query-compute-apps`. Missing
   nvidia-smi → busy (fail closed).
4. **GPU Ollama `/api/ps`** — live resident names, not `/api/tags`.

Thermal (`work/thermal_guard.py` `sample_gpu`, used by
`router.thermal_blocks_gpu` and `tools._thermal_blocks_comfy_process`)
is a **fresh nvidia-smi temperature/util/power sample**. There is no
thermal state file. Unknown telemetry refuses GPU capability swaps and
Comfy process control.

Timeshare `try_idle_comfy_timeshare` re-reads: owner files, live
`/queue` (or MCP list), nvidia-smi, `/api/ps`, then after `/free`
nvidia-smi again (`used <= 800 MiB`). Recheck owners+queue after claim.

Vision / media: `gpu_free_mb()` is live nvidia-smi free VRAM.
`_prepare_vision_batch` re-checks after any unload and will not start a
VLM on blind faith. During df, `:8188` listening would also make
`plan_vision_vram` wait (`comfy_listening()`).

`gpu_gate.py` is **operator consent** for *this app's* loads (`ask` /
one-shot keys). Docstring: it does not kill unrelated Windows
processes. It is not an occupancy tracker.

Internal files that exist and are **not** the occupancy source of
truth for `decide()`:

| File / cache | Role |
|---|---|
| `runtime/chat_busy.json` | Do not evict a *streaming local_agent* turn |
| `runtime/media_vram_pressure.json` | Vision asked chat to shrink |
| `runtime/gpu_gate.json` | Sidebar permission mode |
| `_TIMESHARE_QUEUE_CACHE` | `status()` badge only; `decide()` hits `/queue` live |
| `_LAST_VERIFIED_GPU_MODELS` | Picker display while GPU inventory is skipped; comment says it never authorizes a GPU request |

A **separate CUDA process** whose nvidia-smi name is not ollama /
browser / miner / this PowerInfer `server.exe` is **foreign** →
`gpu_busy` True. Manual Comfy `python.exe` on the card is caught that
way if `:8188` somehow was not.

A **second Ollama** that is *not* `GPU_HOST`, with VRAM above
`VRAM_BUSY_MB` and empty `GPU_HOST` `/api/ps`, also busy (threshold
not waived).

## The gap (comfy-pilot-shaped)

After foreign-compute filtering, `gpu_busy` does this
(`router.py` ~1004–1016):

> If VRAM `> VRAM_BUSY_MB` (2500) **and** `GPU_HOST` `/api/ps` is
> non-empty → **not busy**, reason
> `"GPU has {mb} MB in use by this agent's resident Ollama model(s)"`.

Any `ollama` process name is also excluded from the foreign-compute
list. There is no check that *this* agent loaded the resident, that
`chat_busy` is set, or that nvidia-smi **utilization** is idle (df's
94 % would not, by itself, mark busy).

Timeshare `_already_claimed_for_timeshare` is true if any `/api/ps`
name matches `GPU_MODELS` (includes Huihui 8B/14B). That skips
`clear_vram` and treats the card as already ours, then rechecks only
owner files + Comfy **queue** (not "is another HTTP client using
Ollama").

Map onto df (ComfyUI up, queue empty, 8B promoted on `:11434`):

| Next `local_agent` action | What would happen |
|---|---|
| Chat `decide()` | `gpu_busy` True first (`:8188`). Timeshare: owners idle, queue idle, 8B is "ours" → **already_claimed** → `busy` flipped **False**. Auto GPU path may answer on GPU **without** `prepare_gpu_model` (that flush exists only on the capability 14B swap). Two clients on one Ollama, or a 14B load stacked on the 8B. |
| Image-render tool | `gpu_busy()` True while `:8188` listens → refuse. After Comfy is down but 8B still GPU-resident: `gpu_busy` **False** (waiver), port closed, thermal may still pass → could start a Comfy backend **on top of** 7 GB Ollama. |
| Thermal start ceiling | Live °C. 94 % util does not block unless temp exceeds 70/82 C. |
| Media VLM | `:8188` blocks; else live `gpu_free_mb`. May **unload** the third-party-loaded `/api/ps` models (`action == "evict"`) — adjusts by stealing, not by treating them as foreign. |

`keep_alive: 0` from either side can yank the other's model. df already
showed the unload. `evict_gpu_residents` on a later "GPU reserved"
path would do the same to comfy-pilot.

## What is *not* the bug

Not: timeshare remembering an old load and ignoring nvidia-smi.
Not: owner JSON without a live PID.
Not: thermal reading a cached temperature.
Not: `status()` picker cache authorizing GPU.

The system **does** see live VRAM, live `/api/ps`, live `:8188`, live
PIDs. It **mis-labels** same-server Ollama occupancy as local_agent's.

## Later fix (not this task)

Scope for a follow-up, if taken:

1. Do not waive `VRAM_BUSY_MB` solely because `GPU_HOST` `/api/ps` is
   non-empty. Require a local_agent-owned signal (`chat_busy`, or a
   model this turn just selected) before calling that VRAM "ours".
2. Timeshare `already_claimed` should not fire for a configured tag
   that this process did not load; unexplained residency + high VRAM
   while `:8188` is up should stay CPU or `/free`+verify, not claim.
3. Operational: point comfy-pilot at the CPU Ollama (`:11435`) or
   `num_gpu: 0`, as df already warned. That is config, not a router
   fix.

No GPU work this pass. No `router.py` / `gpu_gate.py` / tools edits.
