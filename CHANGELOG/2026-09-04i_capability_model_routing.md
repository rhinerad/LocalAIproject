# 2026-09-04i — Capability-based dynamic model routing in `router.py`

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04i**.
Pulls/smokes: `CHANGELOG/2026-09-04h_capability_routing_model_pulls.md`.
VRAM envelope: `MODEL_VRAM_BUDGET.md` (Q4_K_M, `num_ctx=8192`).

No new `model_router.py`. Routing stays in `local_agent/router.py`.
Qwythos uses `farm_offload.py` Celery (existing summarize queue), not a
second HTTP transport to the Mac.

## Step 1 — tags still present (reconfirmed this session)

| Role | Tag | Digest prefix | Host |
|---|---|---|---|
| Lightweight tool / eval | `richardyoung/qwythos-9b-abliterated:latest` | `82663f041302` | Louises-MBP |
| Deep logic | `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M` | `6b2209ffd758` | DuranGamingPC :11434 |
| Coding | `josiefied-qwen2.5-coder-14b:q4_k_m` | `4a4b6c1f443c` | DuranGamingPC :11434 |

Resolved Coder tag is the local `ollama create` from
`CHANGELOG/2026-09-04h` (no Ollama registry Coder tag exists). All three
loaded and answered a trivial prompt in 2026-09-04h. GPU was idle then
(70 MiB). Re-list this session: all three still installed.

## What shipped

- `router.classify_capability(prompt, model=)` → `tool` / `logic` / `code`.
  Empty prompt = no override (legacy CPU/GPU auto unchanged).
- Unpinned **tool** turns: `Decision(tier=farm, backend=farm,
  model=Qwythos)` when `farm_offload.farm_reachable()`.
- Unpinned **code** / **logic** turns: Josiefied Coder or DeepSeek Q4_K_M
  on GPU at `num_ctx=8192`, after `prepare_gpu_model()` sends
  `keep_alive: 0` (same `unload()` / `/api/generate` as
  `context_compactor` and `evict_gpu_residents`) and waits on `/api/ps`.
- GPU capability path refuses (no swap) when `queue_owner()` is live,
  `gpu_busy()` (including Comfy :8188), or `thermal_guard` is over
  `START_MAX_C` / telemetry missing. Auto then falls through to the
  existing Huihui 8B CPU path; forced `prefer=gpu` returns `model=None`.
- `farm_offload.try_qwythos_on_farm` + worker task
  `qwythos_evaluate` on the existing **summarize** queue (Mac
  `--concurrency=1` cannot hold Qwythos and mistral-nemo together; the
  task unloads the summarize model first). `agent.py` uses that path
  when `backend=farm` and skip-farms locally on `None`.
- Default `CODING_MODEL` is now `josiefied-qwen2.5-coder-14b:q4_k_m`.

## Tests (mocked Ollama — no live load)

```
python test_capability_routing.py  -> 16 tests OK
python test_router_switching.py    -> 42 tests OK
python test_farm_offload.py        -> 44 tests OK
```

Covered: tool→Qwythos farm; code→Josiefied with `keep_alive_sent=[DeepSeek]`;
logic→DeepSeek; queue_owner and thermal refuse (no swap); unverified flush
refuses; farm unreachable returns None; legacy `decide("auto")` without a
prompt still GPU/CPU.

## Live evidence this session

ComfyUI **was listening on 8188**. `gpu_busy()` = True. Thermal None.
`queue_owner` released. `farm_reachable()` True.

Real `router.decide("auto", prompt=...)`:

| Prompt class | Decision |
|---|---|
| tool (`list the files…`) | `farm` / Qwythos |
| code (`write a python function…`) | CPU `huihui_ai/qwen3-abliterated:8b`; `capability_gpu_refused` reason port 8188; **no** `prepare_gpu_model` |
| logic (architect/compare/refactor) | same CPU 8B refuse |

That is a live end-to-end of the routing decision **and** the
queue_owner/Comfy gate. A live GPU 14B↔14B swap was **not** executed:
loading a 14B while 8188 is up would violate the one-owner GPU rule.
Both 14Bs already smoke-tested idle in 2026-09-04h.

`try_qwythos_on_farm(...)` returned `None` in <1s (fail-closed). The Mac
worker has not been restarted onto this tree, so `qwythos_evaluate` is
not registered there yet. Agent falls back locally. Deploy/restart of
`~/worker_farm` on Louises-MBP is required before a live Qwythos Celery
turn will succeed.
