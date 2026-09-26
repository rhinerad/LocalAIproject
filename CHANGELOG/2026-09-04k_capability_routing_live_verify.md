# 2026-09-04k — Live verification of Qwythos farm + DeepSeek→Coder swap

Date: 2026-09-04. Host: DuranGamingPC. Mac: Louises-MBP.
Id from `python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04k**
(`2026-09-04j` was already claimed). Routing/tests remain
`CHANGELOG/2026-09-04i_capability_model_routing.md` — this entry only
closes the two live gaps that session left open.

## Gap 1 — Mac worker restart, live `try_qwythos_on_farm`

Deployed onto `/Users/rhineduran/worker_farm` (LaunchDaemon cwd), not
a second tree:

- scp `local_agent/worker_farm/tasks.py` and `celery_app.py` (adds
  `qwythos_evaluate` on the existing **summarize** queue)
- inserted `QWYTHOS_MODEL` on the Mac's slim `router.py` (did not
  replace the whole host router)
- `launchctl kickstart -k system/com.local-agent.celery-worker`

Worker stdout after restart lists
`local_agent.worker_farm.tasks.qwythos_evaluate`. (A 2026-09-04i
submit of that name was discarded as unregistered; that is the
fail-closed path this restart closes.)

Live from the workstation farm venv:

| Check | Result |
|---|---|
| `farm_offload.farm_reachable()` | True (`status=ok`) |
| `router.decide("auto", prompt="list the files… using the available tools")` | `tier=farm` `backend=farm` `model=richardyoung/qwythos-9b-abliterated:latest` (2.164 s) |
| `try_qwythos_on_farm([{"role":"user","content":"Reply with the single word OK."}])` | **not None** — `{"content":"OK","tool_calls":[],"model":"richardyoung/qwythos-9b-abliterated:latest"}` in **62.423 s** (cold load on the 2019 Intel Mac) |

Mac `/usr/local/bin/ollama ps` after the turn: empty (Qwythos not left
resident).

## Gap 2 — real DeepSeek-14B → Coder-14B `keep_alive:0` swap

Comfy Desktop was running. The Rockernow backend (`ComfyUI\main.py`
`--port 8188 --reserve-vram 1`, python PID 40268) had an empty queue
(`queue_running=[]`, `queue_pending=[]`), GPU 0 % / 31 C / ~297 MiB,
`queue_owner` released. :8188 was the occupancy that made
`gpu_busy()` true. After that check, the idle backend tree
(40268 / 33812 / 37216) was stopped; Comfy Desktop.exe was left up.
Post-stop: :8188 closed, `gpu_busy()` False, `nvidia-smi` 70 MiB / 0 %.

Then a real swap through `router.decide("auto", …)` (not a mocked
call):

1. Loaded `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M`
   via `/api/generate`. Wall **75.657 s** (`load_duration` 74.7 s).
   `/api/ps` = that tag only. VRAM **10145 MiB**, GPU 98 %, 45 C.
   Model produced a DeepSeek-style `<think>` prefix (think:false did
   not fully suppress it) rather than a clean `PONG`.
2. `decide("auto", prompt="write a python function named ping that returns 1")`
   in **2.484 s** → `tier=gpu` `model=josiefied-qwen2.5-coder-14b:q4_k_m`.
   `host_model_swap.keep_alive_sent` =
   `[huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M]`,
   `verified=true`, `remaining=[]`.
3. Spy on `urllib.request.urlopen` captured the actual POST body to
   `http://127.0.0.1:11434/api/generate`:
   `{"model":"huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M","keep_alive":0}`.
4. `/api/ps` immediately after decide: **`[]`**. VRAM **70 MiB**.
   DeepSeek was gone before Coder loaded.
5. Coder `/api/generate` wall **131.118 s** (`load_duration` 129.5 s).
   Response:

   ```python
   def ping():
       return 1
   ```

   `/api/ps` = `josiefied-qwen2.5-coder-14b:q4_k_m`. VRAM **10149 MiB**.
6. `router.unload` of Coder: `/api/ps` `[]`, VRAM **70 MiB** / 32 C.

Raw capture: `artifacts/benchmarks/2026-09-04k_live_capability_verify.json`.

The idle Comfy backend was then restarted with the same
`--listen 127.0.0.1 --port 8188 --reserve-vram 1` command so Desktop
is not left without a backend.

## Not changed

No routing-code edits. 2026-09-04i tests and changelog stay as-is.
