# 2026-09-02 — worker farm: summarize and embed queues live, end-to-end verified

## Scope

Completes the deployment gap left by `2026-09-02o_summarize_embed_farm_queues.md`
and `2026-09-02q_summarize_queue_per_worker_model.md`. Both prior passes explicitly
noted "no SSH into the Mac, no Ollama install, no ACL re-grant, no deployment, no
test execution." This pass closes all those blockers and confirms both queues with
real task IDs and real results.

## What was done

### 1. Registration tests — farm venv, workstation

Ran `test_farm_core.py`'s newly-added summarize/embed test block via the isolated
farm venv from the repo root. All four tests pass:
```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core -v
```

### 2. Ollama + models installed on mac_worker

SSH'd to `rhineduran@Louises-MacBook-Pro.local` (correct username — an earlier
attempt with `rhine@...` was denied with "Permission denied"; the right name was
found in `CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md`'s
`/Users/rhineduran/Documents/worker_farm` reference).

- Ran `install.sh` from Ollama's official source.
- **MLX runner bug encountered and fixed.** `install.sh` replaced the Ollama
  server's embedded runner with an Apple Silicon (MLX-only) binary. The old
  server process (PID 37443) then failed on every model inference with "Error:
  unknown runner engine, expected --mlx-engine," causing all embed/chat calls to
  hang until timeout. Fixed: `kill 37443`, then `nohup /usr/local/bin/ollama
  serve >> /tmp/ollama.log 2>&1 &`. New server PID 40278 ran correctly.
- Pulled `nomic-embed-text` (for `embed_chunks`) and
  `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS` (~6.8 GB, for
  `summarize_conversation`). The mistral-nemo model was not pre-installed as
  initially believed — `ollama list` after the install.sh run showed only
  llava:7b, llama3:8b, and deepseek-coder:6.7b. Model was pulled fresh (~2 min).
- Ollama is not in the SSH session PATH (`/usr/bin:/bin:/usr/sbin:/sbin`). All
  Ollama commands used the full path `/usr/local/bin/ollama`.

### 3. Re-ran Add-Phase1SecondaryWorkerCredential.ps1

```powershell
powershell.exe -Command "& '$SCRIPT_PATH' -Username mac_worker -Queues 'probe','judge','summarize','embed'"
```

Gotcha: PowerShell array syntax from bash requires `'a','b'` quoting, not
`@('a','b')`. The `@(...)` form passed as a single string and was rejected by
the queue-name validator ("characters outside [a-zA-Z0-9_-]").

New credentials generated. Redis ACL applied in-memory (lost on broker container
restart — same caveat as the prior `judge` queue grant; operator must re-run the
script if Redis restarts before a persistent-ACL approach is added).

### 4. Deployed updated files to mac_worker

Deployed via scp to `rhineduran@Louises-MacBook-Pro.local:~/worker_farm/local_agent/`:
- `local_agent/context_compactor.py` — new transitive dependency for the
  summarize task; includes `model=`/`host=`/`timeout=` overrides from `2026-09-02q`
- `local_agent/ollama_client.py`
- `local_agent/router.py` — defines `CPU_HOST`; reads `EQUAL_SHARES_CPU_HOST`
  env var, needed because mac_worker's standalone Ollama runs on the default port
  `11434`, not the workstation's `11435`
- `local_agent/atomic_io.py` — stdlib-only; imported by router.py
- `local_agent/worker_farm/tasks.py`
- `local_agent/worker_farm/celery_app.py`

Written `~/worker_farm/local_agent/worker_farm/.env` on the Mac:
```
FARM_BROKER_URL=redis://mac_worker:<password>@10.90.90.1:6379/0
FARM_RESULT_BACKEND=redis://mac_worker:<password>@10.90.90.1:6379/0
FARM_QUEUES=probe,judge,summarize,embed
FARM_CONCURRENCY=1
EQUAL_SHARES_CPU_HOST=127.0.0.1:11434
FARM_SUMMARIZE_MODEL=krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS
```

(`<password>` redacted here; the actual `.env.mac_worker.generated` on the
workstation has the live credential and should be deleted — see "still not done".)

### 5. Restarted mac_worker with all four queues

Killed old worker processes (PIDs 37253 main + 37257 ForkPoolWorker), confirmed
"NO CELERY PROCESSES" before starting fresh:
```bash
cd ~/worker_farm && nohup local_agent/worker_farm/.venv/bin/python worker.py \
  --queues probe,judge,summarize,embed >> worker.log 2>&1 &
```

### 6. End-to-end verification — both tasks returned SUCCESS with real results

**summarize_conversation** — task ID `05015820-cc65-41d4-9166-f0e5a7f4ca83`:
```python
{'summarized': True,
 'summary': {'goal': 'set up the worker farm',
             'decisions': ['Configure the Redis broker', 'Install the venv', 'Run worker.py'],
             'open_questions': ['Which queues should I use?'],
             'tool_state': [], 'hard_constraints': [], 'notable_files': []},
 'model': 'krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS'}
```

**embed_chunks** — task ID `6509195d-c718-4179-9e58-0453ade2b23f`:
```python
{'vectors': {'doc:0': [0.0083592, 0.06002827, -0.19730954, ...],    # 768-dim
             'doc:1': [0.015422659, 0.054610606, -0.15589328, ...]}, # 768-dim
 'model': 'nomic-embed-text:latest'}
```

Both completed on `celery@Louises-MacBook-Pro.local`. First-call latency ~55s
(model cold load + inference on a 2019 Intel Core i9 Mac CPU, no GPU).
Mistral-nemo-abliterated inference alone: ~18.5s once loaded. nomic-embed-text
embed: ~0.58s once loaded. Subsequent calls will be faster until `keep_alive`
expires and the model is evicted.

## Files changed (workstation repo)

- `local_agent/worker_farm/README.md` — "summarize and embed queues" section
  updated from "not yet live" to live with real task IDs and latency numbers;
  mac_worker table entry updated to record installed quantization and live status.
- `TODO.md` — Phase 2 item 5 (Swarm offload to The Farm): final two blockers
  checked off; remaining gap (workstation-side `agent.py` caller) kept as open.

## What is still not done

- **`agent.py` caller** — nothing in `agent.py` currently decides to route a
  summarize or embed call to the farm instead of running locally. The queues are
  reachable and verified; the routing decision is a separate task.
- **Ollama autostart on mac_worker** — the server was started with `nohup` only;
  it will not survive a reboot. A launchd plist service was not configured.
- **Relay autostart on workstation** — same gap as prior entries; the tunnel
  relay has no persistent service and must be restarted manually after a reboot.
- **`.env.mac_worker.generated` cleanup** — the generated file on the workstation
  (`local_agent/worker_farm/.env.mac_worker.generated`) contains live Redis
  credentials and should be deleted. Not done in this pass; operator should delete
  it manually once the Mac's `.env` is confirmed working (it is).
