# ComfyUI / agent GPU time-sharing via `clear_vram` (option B)

| Field | Value |
|---|---|
| Author | local_agent (design pass) |
| Date | 2026-09-04 |
| Status | Draft — **delta against live `router.py` (read this pass)** |
| Scope | Design only. Do not implement this pass. |

Sibling: [COMFYUI_MCP_INTEGRATION_PLAN.md](COMFYUI_MCP_INTEGRATION_PLAN.md). Do not rewrite that plan.

Greenfield “add timeshare” is wrong: `_maybe_comfy_timeshare` already runs from `decide()`. This doc is the **alignment spec**. Line cites are from a live read of `local_agent/router.py` this pass.

---

## Overview

Option A is **closed**. 2026-09-04 DynamicVRAM: nvidia-smi **flat 345 MiB** through idle / load / loaded-idle; **28.93 s** lag after generating-phase start; peak 2811; post-generate 2459. A threshold cannot see the claim window.

Option B is partially shipped. **Keep:** live PID in `OWNER` (`:61`) is authoritative — never `/free`; empty ComfyUI queue required; `keep_alive: 0` does **not** reload a ComfyUI checkpoint (~17 s SD1.5 + ~29 s VRAM lag on next `comfy_generate`).

**Operator-approved occupancy and queue (do not strip / do not flip to urllib-first):**

1. Queue: MCP `queue` list `timeout=5`, `lock_timeout=0.2`, `spawn=False`; urllib `/queue` `timeout=2` on spawn-blocked / lock timeout / RPC timeout / unreadable. Successful non-idle MCP list does not urllib. MCP idle iff `running`/`pending` **`type is int`** and both `== 0` (do not `int()` coerce).
2. Occupancy before `/free`: nvidia-smi `None` fail-closed; unexplained used fail-closed unless ≤800, 2000–3200, or already-claimed; path-aware `_is_this_comfyui_python` (Rockernow `standalone-env` waived; `Python312\python.exe` foreign); bare `python.exe` + 8188 is not name-foreign (band still applies); PI compute on a non-PI pin → no `/free`.
3. Keep `_TIMESHARE_GPU_GATE_BYPASS` WARNING. Do not call `gpu_gate.request()` from router. Do not edit `agent.py`.
4. `status()` stays today's busy+CPU badge. Third state is a TODO ticket, not this PR.

---

## Background & Motivation

`gpu_busy()` (`:1008`) still short-circuits on 8188 (`:1017–1020`) before nvidia-smi. Signal 1 (`queue_owner` `:477`, live PID in `OWNER`) stays the “render *intends* to use the card” lock.

### In-tree today (live `def` inventory)

| Symbol | Line | vs this spec |
|---|---|---|
| `mcp_client.call(..., lock_timeout=, spawn=)` | `mcp_client.py:276`, module `:526` | **Landed.** `spawn=False` does not `get_client()` if singleton missing. |
| `_timeshare_enabled` | `:491` | Keep. Default-on; `=0` skip. |
| `_owner_file_idle` / `_owner_lock_files` / `_owners_idle_for_timeshare` | `:495` / `:509` / `:513` | **Landed.** Three paths via `_owner_lock_files()` (not a `_OWNER_LOCK_FILES` constant). Unreadable ≠ idle. |
| `_mcp_queue_int_counts` | `:524` | Uses `int(...)`, not `type is int`. **Tighten** when flipping queue order. Docstring mentions job arrays; **do not** `len(running_jobs)` for idle. |
| `_comfy_queue_via_urllib` | `:541` | **timeout=2.** Lists `queue_running`/`queue_pending`; `len()` on those lists is correct for urllib. |
| `_comfy_queue_idle` | `:568` | **CHANGE.** MCP `timeout=5` first; urllib 2 s only on MCP error/unreadable. Docstring says so. |
| `_resident_is_ours` / `_already_claimed_for_timeshare` | `:595` / `:668` | Keep hop-N skip. |
| `_is_this_comfyui_python` | `:610` | **Remove.** |
| `_timeshare_name_is_foreign` (`_looks_like_path` `:606`) | `:628`, used `:735` | **Remove** from occupancy. |
| `_powerinfer_compute_present` / `_timeshare_pi_compute` | `:648` / `:653` | maybe-PI + `backend_up` **bool**. Replace with **list**. |
| `_vram_band_allows_free` | `:662`, used `:743` | **Remove.** 2000–3200 is option A. |
| `_clear_vram_for_timeshare` | `:685` | Keep: token `VRAM cleared successfully`, used ≤ `TIMESHARE_VRAM_CLEAR_MAX_MIB` 800, timeout=20 (covers 12 s settle). |
| `try_idle_comfy_timeshare` | `:706` | Keep owners→queue→claim; strip foreign-name + VRAM-band guards. **No gpu_gate call.** |
| `_timeshare_would_load_host_gpu` | `:783` | **Change body.** |
| `_maybe_comfy_timeshare` / `decide()` hook | `:794` / `:1415–1417` | Keep farm skip + host-GPU gate before claim; `skip_gpu_inventory` from post-hook `busy` (`:1422`). |
| `_timeshare_gpu_gate` | — | **Not in file.** Dead `TIMESHARE_GPU_GATE_KEY` `:362`, `_TIMESHARE_GPU_GATE_BYPASS` `:365`. Delete constants. |
| `status()` third state | `:1755–1766` | **Landed, keep.** Peek owners+queue; never `/free`. `STATUS_TIMESHARE_IDLE_REASON` `:363`. |
| `gpu_busy` / `want_gpu` / eviction / `unload` | `:1008` / `:1629` / `:1561` / `:1137` | Do not rewrite 8188 short-circuit. Do not use `want_gpu` for the hook (`busy` still True). |

`test_router_switching.py` `:203`, `:271`, `:528` still pass `comfy_port_8188=listening` and assert PowerInfer refuse without mocking queue — environment-dependent.

---

## Goals & Non-Goals

**Goals:** live `OWNER` PID never `/free`; empty queue via urllib-first 1 s; exact host-GPU boolean; PI proc list; strip option-A occupancy (python path-match, 2000–3200 band); no in-router gpu_gate; no ComfyUI reload after `keep_alive: 0`.

**Non-goals:** do not change `comfy_listening()` / `gpu_busy()` 8188; no `plan_vision_vram` `:982` / `media_*` / `agent.py`; no Python this pass.

---

## Proposed Design (delta)

### 1. `_comfy_queue_idle` — **must change in PR 2**

Today (`:568–592`): MCP `queue` `list` `timeout=5`, `lock_timeout=0.2`, `spawn=False`; on exception or `_mcp_queue_int_counts is None`, urllib `timeout=2`. Successful MCP non-idle does not urllib (keep that).

**Replace with urllib-first:**

1. `GET http://127.0.0.1:8188/queue` **timeout=1**. Idle iff both `queue_running` and `queue_pending` **present lists** and empty. Non-empty → not idle, **do not MCP**. Missing/non-list → unreadable → step 2.
2. MCP `list` **timeout=1**, `lock_timeout=0.2`, `spawn=False`. Idle iff `running` and `pending` have **`type is int`** (not `int(...)`) and both `== 0`. `int > 0` → not idle. Any other type (including `running_jobs` arrays) → unreadable. **Do not `len(running_jobs)`.**
3. Both fail → not idle.

Budget: hop-N ~1.2 s; first-claim ~22 s (`clear_vram` 20 s includes `VRAM_SETTLE_TIMEOUT_MS=12000`); queue fail-closed ~2.2 s. MCP timeout=5 is the stall this change exists to kill.

### 2. `_timeshare_would_load_host_gpu` — replace body (`:783–791`)

**Current hole:** `capability in {CAP_CODE, CAP_LOGIC}` with no pin rules; then `return prefer in ("auto", "gpu")` — Qwythos pin and CPU-only pin are True. FALLBACK 8B is already True via that return.

```python
def _timeshare_would_load_host_gpu(prefer, model, capability) -> bool:
    if prefer == "cpu":
        return False
    if is_powerinfer_model(model) or is_gpu_only_opt_in_model(model):
        return True
    if (capability in {CAP_CODE, CAP_LOGIC}
            and (model is None
                 or _is_configured_variant(model, DEEPSEEK_MODEL)
                 or _is_configured_variant(model, JOSIEFIED_CODER_MODEL)
                 or is_coding_model(model))):
        return True  # same as want_capability_gpu :1488–1493
    if model is None:
        return True
    if _is_configured_variant(model, QWYTHOS_MODEL):
        return False
    if any(_is_configured_variant(model, name) for name in GPU_MODELS):
        return True
    if is_coding_model(model):
        return True
    return False  # CPU-only / unknown pin
```

Still evaluated in `_maybe_comfy_timeshare` **before** `try_idle_comfy_timeshare`. Farm skip stays in the caller (`:802–809`).

### 3. Occupancy — names-only nvidia-smi (`gpu_memory` `:902`)

Idle ComfyUI’s compute name is typically **`python.exe`** at **345 MiB**. Path-matching `COMFYUI_CODE_PATH` cannot work on names-only rows.

| Helper | Decision | Rationale |
|---|---|---|
| `_is_this_comfyui_python` `:610` | **Remove** | Original option B forbade it. Names-only `python.exe` never contains `standalone-env`. Keeping it pretends we identified ComfyUI. |
| `_timeshare_name_is_foreign` `:628` (used `:735`) | **Remove** from hook; delete with `_looks_like_path` | Process-name idle detector is option A. Today it waives `stem==python` whenever 8188 is up (`:643–644`) — i.e. all `python.exe`, not “this ComfyUI.” |
| unexplained `python.exe` | **Not fail-closed** | Fail-closed on `python.exe` makes idle ComfyUI **unclaimable** (measured 345 + `python.exe`). Occupancy is owner + empty queue + post-`/free` ≤800. `python.exe` is not foreign. |
| `_vram_band_allows_free` `:662` (2000–3200, used `:743`) | **Remove** | Option A leftover. 345 is the claim window; 2459 is the post-gen case we **must `/free`**. Do not refuse take-the-card because used is 2459. Do not skip `/free` because used is 345. Post-`/free` verify stays ≤800. |
| `_timeshare_pi_compute` `:653` | **Replace** with list | |

```python
def _timeshare_powerinfer_procs(procs: list[str]) -> list[str]:
    maybe = any(
        Path(p).stem.lower() == Path(POWERINFER_SERVER_EXE).stem.lower()
        or "powerinfer" in str(p).lower()
        for p in procs)
    backend_up = powerinfer_backend_listening() if maybe else False
    return [p for p in procs if _is_powerinfer_compute(p, backend_up=backend_up)]
```

Same maybe-PI gate as `gpu_busy()` `:1031–1038`. TCP 8080 alone is not occupancy. Huihui + `(9000, ["server.exe"])` + 8080 up + empty queue + no Ollama → **no `/free`**.

`try_idle` after owners+queue: `pi_procs = _timeshare_powerinfer_procs(procs)`; PI on non-PI pin → fail closed; already-claimed skip unchanged; **no** foreign-name loop; **no** `_vram_band_allows_free`; else `/free` + ≤800 + recheck.

### 4. gpu_gate

Function `_timeshare_gpu_gate` is **absent**. Do not re-add. Delete unused `TIMESHARE_GPU_GATE_KEY` `:362` and `_TIMESHARE_GPU_GATE_BYPASS` `:365`. `agent.py:1595–1597` still claims consent lives in `try_idle_comfy_timeshare` — **stale; do not edit `agent.py` in PR 2.** Open Question 3.

### 5. After the agent finishes

No ComfyUI reload. Later non-empty owner/queue → `busy` stays True → `:1561` evicts.

**PowerInfer-while-8188:** idle 8188 + PI pin → select PI. Live owner / non-empty queue → refuse as today.

---

## API / Interface Changes

- **Edit:** `_comfy_queue_idle` order/timeouts; `_mcp_queue_int_counts` (`type is int`); `_timeshare_would_load_host_gpu` body; `try_idle_comfy_timeshare` occupancy.
- **Replace:** `_timeshare_pi_compute` / `_powerinfer_compute_present` → `_timeshare_powerinfer_procs() -> list[str]`.
- **Delete:** `_is_this_comfyui_python`, `_timeshare_name_is_foreign`, `_looks_like_path`, `_vram_band_allows_free`, `TIMESHARE_POSTGEN_VRAM_*` if unused, `TIMESHARE_GPU_GATE_KEY`, `_TIMESHARE_GPU_GATE_BYPASS`.
- **Unchanged:** owners helpers, `_clear_vram_for_timeshare` success token + ≤800, `_maybe_comfy_timeshare` control flow, `mcp_client.call` kwargs, `status()` peek.

---

## Data Model Changes

None.

---

## Alternatives Considered

1. Option A VRAM threshold — closed (345 / 28.93 s / 2459 vs 2500).
2. Freeze `_comfy_queue_idle` — **rejected**; live path is MCP-first 5 s.
3. Fail-closed on `python.exe` — **rejected**; idle ComfyUI is names-only `python.exe`.
4. Keep 2000–3200 band — **rejected**; option A; blocks `/free` of 2459 if removed wrong, or skips `/free` of 345 if used as idle detector.
5. Re-add `_timeshare_gpu_gate` — **rejected**; operator left gpu_gate to `agent.py`.
6. `_is_this_comfyui_python` path-match — **rejected**; names-only telemetry.

---

## Security & Privacy

`clear_vram` only after idle owners+queue on a host-GPU turn. Never from `status()`. Never over live `OWNER`. No in-router gpu_gate → timeshare can load while hop `gpu_busy` skip (`agent.py:1611–1614`) withholds the chat card (remaining-unsafe 6).

---

## Observability

`detail["timeshare"]`: `owners`, `queue` (source `urllib`|`mcp`), `occupancy` (used MiB, **PI proc list**, not a foreign-name list), `path`, `clear_vram`, `recheck`. Drop `gpu_gate`.

---

## Rollout Plan

1. This delta. No runtime edits this pass.
2. PR 2 aligns hook **including `_comfy_queue_idle`**.
3. Live verify: `Decision.detail["timeshare"]` + nvidia-smi — **not** `status()["gpu_busy"]` as `/free` proof.
4. Rollback: `EQUAL_SHARES_COMFY_TIMESHARE=0`.

---

## Remaining-unsafe (read before coding)

Grounded in 2026-09-04 (345 flat; **28.93 s** lag; 2811 peak; 2459 post-gen):

1. **TOCTOU vs 28.93 s (high).** Empty queue → `/free` → 14B. Enqueue stays 345 ~29 s; ≤800 cannot see it.
2. **Manual UI (high).** No PID file.
3. **Queue vs owner lag (high).** `OWNER` covers pre-backend; `comfy_generate` `enqueued` immediately (2026-09-04j).
4. **`/free` vs in-flight generate (high).** MCP lock-busy skips `/free`; raw `/prompt` does not hold that lock.
5. **`/free` vs CPU staging (high if unverified).** Success token + used still 345 after loaded-idle is **not** a green `/free`. 2459 after `/free` fail-closes (≤800). 12 s settle is inside the 20 s RPC.
6. **8188 leftover + gpu_gate (medium).** `gpu_busy()` stays True. Vision/media wait (`plan_vision_vram:982`). Hop skip `agent.py:1611`; escalation `:1269`; task-plan uses `gpu_busy` similarly. No in-router gate. Do not teach `agent.py` in PR 2. `status():1755` is observational.
7. Do not change `comfy_listening()` to VRAM (reintroduces A).
8. Hop-N ≤800 bounce if `_already_claimed_for_timeshare` omitted.
9. Cold MCP `/free` fail-closed.
10. Deferred `/free`.
11. Mid-turn yield is per-`decide()` only.
12. PI binary neither `server.exe` nor `powerinfer` in the name is invisible.

---

## Open Questions

Resolved (operator, CHANGELOG `2026-09-04q`; do not implement the alignment-delta rewrite):

1. **`status()` badge — keep today's badge as-is this pass.** Fast-follow later: third state (`8188 up, idle, agent may claim`) from owner+queue only, no `/free`. TODO.md ticket. `status()` uses `gpu_busy()` + `decide(ensure_gpu_evicted=False)` (busy + CPU `routing_reason` while 8188 listens). No MCP/urllib from `status()`.
2. **Post-`/free` cap: 800 MiB**, as designed (345 idle vs 2459 post-generate).
3. **`gpu_gate` bypass: accepted for this pass, not indefinitely deferred.** THIS PR logs `_TIMESHARE_GPU_GATE_BYPASS` WARNING. Do not call `gpu_gate.request()` from router. Do not edit `agent.py`.

Queue remains **MCP list timeout=5 then urllib timeout=2** (`spawn=False`, `lock_timeout=0.2`). Occupancy keeps nvidia-smi None fail-closed, unexplained VRAM fail-closed (not ≤800, not 2000–3200, not already-claimed), path-aware `_is_this_comfyui_python`, bare `python.exe`+8188 not name-foreign, PI compute on non-PI pin → no `/free`.

---

## References

- `local_agent/router.py` — `OWNER` `:61`; `_comfy_queue_idle` `:568`; `_is_this_comfyui_python` `:610`; `_timeshare_name_is_foreign` `:628`; `_timeshare_pi_compute` `:653`; `_vram_band_allows_free` `:662`; `try_idle` `:706`; `_timeshare_would_load_host_gpu` `:783`; `_maybe_comfy_timeshare` `:794`; `gpu_busy` `:1008`; `decide` `:1405`; eviction `:1561`; `want_gpu` `:1629`; `status` `:1755`; `unload` `:1137`; `queue_owner` `:477`
- `local_agent/mcp_client.py` `:276` / `:526`
- `local_agent/agent.py` `:1269`, hop `:1590–1619`
- `test_router_switching.py` `:203` / `:271` / `:528`
- `docs/adr/0005-gpu-cpu-reasoning-fallback.md`; `CHANGELOG/2026-09-04j_comfyui_mcp_live_generate.md`
- comfyui-mcp `memory-management.ts`, `vram-settle.ts` (`VRAM_SETTLE_TIMEOUT_MS=12000`), `QueueSummary` ints
- 2026-09-04 DynamicVRAM probe (345 / 28.93 s / 2811 / 2459) — not in-repo

---

## Key Decisions

| Decision | Rationale |
|---|---|
| Spec is a delta vs **live** helpers | Previous table froze the wrong queue path. |
| **Change** `_comfy_queue_idle` to urllib-first 1 s | Live is MCP-first 5 s; that stalls every 8188-up hop. |
| MCP idle iff `type is int` and `== 0` | Do not `int()`-coerce; do not `len(running_jobs)`. |
| Host-GPU hole = prefer too wide + CAP_* pins | FALLBACK is already included; Qwythos/CPU-only must be False. |
| Remove `_is_this_comfyui_python` | Names-only `python.exe`; original option B. |
| Do **not** fail-closed on `python.exe` | Idle ComfyUI is that row; fail-closed = never claim. |
| Remove `_timeshare_name_is_foreign` | Process-name occupancy is option A. |
| Remove `_vram_band_allows_free` | 2000–3200 is option A; `/free` 2459 then ≤800. |
| `_timeshare_powerinfer_procs` list | Names-only `server.exe` needs `backend_up`. |
| Do not re-add `_timeshare_gpu_gate` | Absent in live file; agent.py later. |
| No ComfyUI reload after `keep_alive: 0` | Lazy; ~17 s + ~29 s accepted. |

---

## PR Plan

This pass implements nothing.

### PR 1 — mcp_client bounds (**already landed**)

- **Title:** none
- **Files:** `mcp_client.py`, `test_mcp_client.py` — spawn-false / lock_timeout already tested.
- **Deps:** none
- **Changes:** none.

### PR 2 — Align the existing hook (**includes queue flip**)

- **Title:** Align ComfyUI timeshare: urllib-first queue, host-GPU gate, drop option-A occupancy
- **Files:** `local_agent/router.py`, `local_agent/test_router_comfy_timeshare.py`, `local_agent/test_router_switching.py`
- **Deps:** none
- **Must edit:** `_comfy_queue_idle` (MCP-first 5 s / urllib 2 s → urllib-first timeout=1, MCP timeout=1 fallback). Tighten `_mcp_queue_int_counts`. Replace `_timeshare_would_load_host_gpu` body. `_timeshare_powerinfer_procs` list. Delete `_is_this_comfyui_python`, `_timeshare_name_is_foreign`, `_looks_like_path`, `_vram_band_allows_free`, dead gpu_gate constants. Strip those calls from `try_idle_comfy_timeshare`.
- **Do not edit:** `comfy_listening()`, `gpu_busy()` 8188 short-circuit, `plan_vision_vram`, `media_*`, `agent.py`.
- **`test_router_switching.py` `:203`/`:271`/`:528`:** mock owners or queue fail-closed so PI **refuses**; add idle-8188 → select PI.
- **Timeshare tests:** live `OWNER` never `/free`; urllib non-empty no MCP; MCP `running` as list unreadable; `int==0` idle; Qwythos/CPU-only host-GPU False; empty prompt True; Huihui+`server.exe`+8080 no `/free`; idle `python.exe` **does** `/free`; used=2459 still `/free` then ≤800; used=345 still calls `/free`; no `_vram_band_allows_free`; farm skip; kill switch `=0`.

### PR 3 — Changelog + live verify

- **Title:** Record timeshare alignment
- **Files:** dated `CHANGELOG/`
- **Deps:** PR 2
- **Verify:** `Decision.detail["timeshare"]` + nvidia-smi, not `status()["gpu_busy"]` as `/free` proof. Idle 8188 → 14B; hop 2 no second `/free`; live owner → CPU; post-gen 2459 → `/free`; farm skip; Huihui+`server.exe`+8080 no `/free`; idle-8188 PI pin selects PI; `=0` restores 8188-hard-busy. 345 after loaded-idle = remaining-unsafe 5, not green `/free`.
