# 2026-09-05dv — GPU Ollama VRAM is "ours" only when this agent loaded it

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05dv**.

Implements the scoped fix from `2026-09-05dq` (comfy-pilot gap in
`2026-09-05df`). Live occupancy reads are unchanged: owner files+PID,
`:8188`, nvidia-smi, `/api/ps`. Only the **attribution** of GPU_HOST
residents is narrower.

## What changed

`gpu_busy()` no longer waives `VRAM_BUSY_MB` merely because
`GPU_HOST` `/api/ps` is non-empty. Waiver requires a local_agent-owned
signal:

1. **Durable selected tags** in `runtime/gpu_owned_residents.json`
   (`gpu-owned-residents-v1`). Written when a real GPU Ollama
   `decide()` returns a model (`ensure_gpu_evicted=True`, not a
   `status()` poll) or `prepare_gpu_model` verifies a swap. Dropped on
   `unload` / verified `evict_gpu_residents`. Pruned against live
   `/api/ps` when `chat_busy` is false, so a later third-party reload
   of the same tag is not ours.
2. **In-flight load:** `chat_busy()` **and** a selected tag, only when
   `/api/ps` has no unexplained extra resident. A CPU turn with
   `chat_busy` and empty owned list does **not** waive a comfy-pilot
   8B.

Timeshare `_already_claimed_for_timeshare` / `_resident_is_ours` uses
the same owned-resident intersection. A `GPU_MODELS` tag on `/api/ps`
that this process never selected is not `already_claimed`; the hook
falls through to `/free`+verify or CPU.

Unexplained extra residents next to an owned tag also stay **busy**
(mixed occupancy).

## Tests

```
python -m unittest local_agent.test_router_switching local_agent.test_router_comfy_timeshare local_agent.test_capability_routing local_agent.test_vram_arbitration local_agent.test_router_status_busy -q
```

136/136 OK. Explicit cases:

- Third-party Huihui 8B on GPU_HOST, never `note_gpu_owned` →
  `gpu_busy` True, reason includes "not loaded by this agent"
  (7623 MiB, comfy-pilot shape).
- Same 8B during `chat_busy` with empty owned list → still busy.
- Own-turn `note_gpu_owned` of the 14B, still in `/api/ps` → not busy,
  same "resident Ollama" waiver as before.
- In-flight: owned 14B, `chat_busy`, empty `/api/ps`, high VRAM → not
  busy ("loading").
- Owned tag pruned after `/api/ps` empty, then 8B reappears → busy.
- Timeshare: hop-N owned 14B still `already_claimed`; third-party 8B
  is `cpu_fallback`, not `already_claimed`.

## Files

- `local_agent/router.py`
- `local_agent/test_router_switching.py`
- `local_agent/test_router_comfy_timeshare.py`
- `local_agent/test_capability_routing.py`
- `TODO.md` (dq item marked fixed)

No GPU work. Semantic judge / farm / `.env` untouched.
