# Phase 1 local worker farm

This is the CPU-only bootstrap for asynchronous local-agent work.  It is
deliberately separate from the interactive GUI, ComfyUI, and LXMF bridge.

Current-state farm architecture (as opposed to plans): [`../../docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md).
Night-of farm diagnostics: [`../../docs/FARM_HEALTH_RUNBOOK.md`](../../docs/FARM_HEALTH_RUNBOOK.md).

**Tests — one correct invocation, from the repository root, farm venv only:**

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core local_agent.worker_farm.test_farm_health local_agent.worker_farm.test_farm_status_daemon local_agent.worker_farm.test_farm_dashboard local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
```

PATH `python` and `python local_agent/worker_farm/test_*.py` are the wrong
interpreters/paths. They do not prove the suite.

Live farm (slow; skips if unreachable; not part of the fast suite above). Submits real summarize_conversation, embed_chunks, and judge_transcript tasks:

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v
```

## Boundary

- Redis is bound to `127.0.0.1` by the checked-in Compose file.
- The RTX GPU is never used by this package.
- Jobs carry only an ID; raw exports are copied into encrypted local artifacts.
- A local SQLite metadata ledger deduplicates jobs by source hash and allows a
  queued job to be claimed only once. The ledger contains IDs, hashes and state;
  raw source/result content remains in encrypted artifacts.
- The first historical-memory task produces review candidates only.  It cannot
  write to Chroma, alter agent memory, render, or execute arbitrary commands.
- JSON exports are deterministically flattened and HTML exports retain visible
  text only (scripts/styles are ignored) before the sanitizer and candidate
  extractor run. The original stays encrypted as an immutable source artifact.
- Laptop and Termux workers remain disabled until a private encrypted overlay
  and per-worker broker credentials are deliberately configured.

## Bootstrap

**Live Redis on DuranGamingPC** is Ubuntu-24.04 Docker CE
(`local-agent-phase1-redis`), started at boot by
`\local-agent-wsl-docker-boot`. User-env `FARM_REDIS_ENGINE=wsl` is the
effective default on this machine (`2026-09-03bg`/`bh`, reboot-verified
`2026-09-04a`). Windows `127.0.0.1:6379` is `wslrelay`. Docker Desktop is
**not** the live engine (AutoStart off).

`START_PHASE1_BROKER.ps1` and `doctor.py` still treat **unset**
`FARM_REDIS_ENGINE` as `desktop`. That code default is **Desktop rollback
only, not the live default.** On this host, rely on the user-env `wsl`
value (or pass `-Engine wsl`). Do not follow the Desktop “wait for
**Engine running**” wait as the primary procedure.

1. Run `.venv\\Scripts\\python.exe -m local_agent.worker_farm.doctor`.
2. Install the Python packages in `requirements.txt` into a dedicated
   environment. Live engine is Ubuntu-24.04 Docker CE (`wsl -d Ubuntu-24.04
   -- docker info`), not Docker Desktop. Install/start Docker Desktop only
   for the rollback path below.
3. Run `Initialize-Phase1Secrets.ps1` once. It creates a unique Redis password
   and a base64 32-byte AES key locally, does not print them, and keeps the
   generated `.env` file out of source control. After write it disables NTFS
   inheritance and grants only `SYSTEM:(R,W)` and `DURANGAMINGPC\rhine:(R,W)`
   (same lockdown as `Add-Phase1SecondaryWorkerCredential.ps1` and the
   `runtime/redis-acl` copies Restore stages). Verify without touching live
   secrets: `Initialize-Phase1Secrets.ps1 -LockdownProbe` or
   `Add-Phase1SecondaryWorkerCredential.ps1 -LockdownProbe`. `FARM_ROOT` is an
   absolute location outside the repository for encrypted private artifacts.
   The generated broker password is URL-safe so the matching Redis URLs remain
   parseable by Celery/Kombu.
   Existing installations created before that correction can run
   `Repair-Phase1BrokerUrls.ps1`; it preserves their Redis password and AES key.
4. Run `START_PHASE1_BROKER.ps1`, then in another terminal run
   `START_PHASE1_CPU_WORKER.ps1`. Both commands refuse placeholder settings.
   If PowerShell appears blank, double-click `START_PHASE1_BROKER_VISIBLE.cmd`;
   it keeps a visible console open with the exact Docker error.
   Live path: confirm Ubuntu CE answers (`wsl -d Ubuntu-24.04 -- docker info`)
   and `FARM_REDIS_ENGINE=wsl` (user env or `-Engine wsl`). Same flag is read
   by `doctor.py` and `Restore-Phase1SecondaryWorkerCredentials.ps1`.
   **Desktop rollback path only:** `FARM_REDIS_ENGINE=desktop` (or unset the
   user env), start Docker Desktop, and wait until it shows **Engine running**
   if the launcher says Docker did not answer within 15 seconds. Do not use
   that wait while the live engine is WSL.
5. Run `RUN_PHASE1_SAMPLE.ps1`.

Secondary Redis ACL users (`mac_worker` and any later `.env.<username>.generated`
files) are reapplied automatically every time the Redis container starts, including
`docker restart`, by `redis-with-acl-restore.sh`. Do not re-run
`Add-Phase1SecondaryWorkerCredential.ps1` just to survive a restart; that script
rotates the password. `Restore-Phase1SecondaryWorkerCredentials.ps1` reapplies
existing generated passwords to a running broker without rotating them.

`--sample` is the only initial live workload.  It creates synthetic benign
input, encrypts source/result artifacts, and writes `review_required` output.
It does not process an operator's historical exports.

Phase 1 accepts only JSON, HTML, or text exports up to 25 MiB. It extracts at
most 500,000 visible characters for review. These limits are deliberate safety
boundaries, not a reason to split or bypass an oversized private export.

Do not rotate the generated AES key casually. Rotation deliberately requires
both `-Force` and `-AcknowledgeExistingArtifactsBecomeUnreadable`, because the
old key is required to authenticate and read prior encrypted artifacts.

If the broker is unavailable during submission, the command refuses rather
than claiming success. The durable job is returned to `staged`, so rerunning
the same command retries the original encrypted source safely.

`START_PHASE1_CPU_WORKER.ps1` sets `CUDA_VISIBLE_DEVICES=-1` as a defense in
depth measure. This Phase 1 package has no model loading code and never shares
the RTX with interactive chat or ComfyUI.

Use `SHOW_PHASE1_STATUS.ps1` to inspect only the metadata state of queued or
completed jobs. It never prints source text, encrypted artifact payloads, Redis
credentials, or the AES key.

Before starting anything, run the read-only readiness report. It checks the
Python dependencies, configuration shape, Docker engine access, and the
loopback Redis port with short timeouts. It never prints credentials and never
starts a service:

```powershell
local_agent\worker_farm\RUN_PHASE1_DOCTOR.ps1
```

## farm_health

Read-only broker + worker ping. Does not submit summarize/embed/judge/distill jobs.
Operator datapath checklist: [`../../docs/FARM_HEALTH_RUNBOOK.md`](../../docs/FARM_HEALTH_RUNBOOK.md).

```
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health
```

Prints one status line (`broker reachable`, `workers responding`, `latency_ms`) and a second `registered-task` line from `check_registered_tasks()` (Celery `inspect.registered()`). Connectivity `status` stays `ok` even when summarize/embed are not registered; `missing_expected_tasks` reports that gap. `--json` dumps the `check_farm_health()` dict plus `checked_at` (UTC ISO-8601) and `registered_check`. Exit 0 only when both broker and a worker answered. Live CLI is a diagnostic — the agent hot path does not call `inspect()`. `farm_offload.farm_reachable()` reads `farm_status.json` (same overall-healthy rule as the dashboard: `status=="ok"` and not stale).

## farm_status.json

Cheap cached snapshot of the same health check, written by `farm_status_daemon` so other code can read a file instead of calling Celery `inspect()` live.

```
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_status_daemon
```

Default interval 30s (`--interval`, or `FARM_STATUS_INTERVAL_S`). `--once` writes one snapshot and exits. Path defaults to `local_agent/worker_farm/farm_status.json` (`--path` or `FARM_STATUS_PATH`). Atomic write (temp file + rename). Failed checks are recorded; the loop keeps running. After N consecutive failed checks (status not `ok`), prints a greppable `FARM_STATUS_OUTAGE` line with the count, latest status, and error. N defaults to 3 (`--fail-alert-after`, or `FARM_STATUS_FAIL_ALERT_AFTER`). Logged on crossing N and every N failures thereafter. The consecutive counter resets on a healthy check; `FARM_STATUS_RECOVERED` is printed if an outage had been declared.

Stable object shape:

```json
{
  "broker_reachable": true,
  "checked_at": "2026-09-02T20:43:00+00:00",
  "error": null,
  "latency_ms": 12.3,
  "status": "ok",
  "workers": ["celery@Louises-MBP"],
  "workers_responding": true
}
```

`status` is `ok` | `unreachable` | `no_workers` | `unconfigured`. `farm_status.json` is gitignored.

## farm dashboard (loopback :8765)

Stdlib `ThreadingHTTPServer`. **Default bind is `127.0.0.1:8765`** (same family as Redis / tunnel-relay — not the home LAN). Polls `farm_status.json`, `farm_health --json`, and existing service checks. Does not submit jobs. GET-only, no auth.

```
powershell -File local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1
```

Open `http://127.0.0.1:8765/`. To reach it from another host, opt in (never `0.0.0.0`):

```
$env:FARM_DASHBOARD_HOST = '192.168.50.208'   # home LAN, unauthenticated
# or
$env:FARM_DASHBOARD_HOST = '10.90.90.1'       # WireGuard hub overlay
powershell -File local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1
```

When the dashboard's existing overall block is not `ok` (including a stale / daemon-down snapshot), it prints a greppable `FARM_DASHBOARD_DEGRADED` line and a best-effort Windows balloon. Stay-degraded polls are silent; `FARM_DASHBOARD_RECOVERED` fires on the first healthy observation after an alert. A 30s watch reads `farm_status.json` so this works without a browser open. Do not run it from the farm venv. Do not attach to :8760.

## Later worker policy

| Worker | Queues | Data limit |
|---|---|---|
| Ryzen CPU | `distill`, `judge` | private, encrypted artifacts only |
| Laptop | `preprocess`, `research` | public/approved sources only |
| Termux phone | `edge` | small, non-sensitive batches only |

The broker must never be exposed on `0.0.0.0`, a public address, ordinary home
Wi-Fi, LoRa, or LXMF.  Remote workers require a private encrypted overlay and
separate credentials before their queue is enabled.

## `summarize` and `embed` queues — live on mac_worker as of 2026-09-02

`worker_farm/tasks.py` has `summarize_conversation` (offloads
`context_compactor`'s compaction) and `embed_chunks` (offloads
`retrieval.EmbeddingScorer`'s embedding calls) tasks, registered on their
own `summarize`/`embed` queues in `celery_app.py`. See
`HARNESS_OPTIMIZATION.md` §4a for the design.

**Both queues are live and end-to-end verified on `mac_worker`.** Confirmed
2026-09-02 with real task IDs:
- `summarize_conversation` — `05015820-cc65-41d4-9166-f0e5a7f4ca83`, returned
  a structured `{goal, decisions, open_questions, ...}` summary using
  `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`.
- `embed_chunks` — `6509195d-c718-4179-9e58-0453ade2b23f`, returned 768-dim
  vectors for two chunks using `nomic-embed-text:latest`.

First-call latency was ~55s (model cold load + inference on a 2019 Intel Core
i9 Mac CPU, no GPU). Mistral-nemo-abliterated inference alone: ~18.5s once
loaded. nomic-embed-text embed: ~0.58s once loaded. Subsequent calls will be
faster until `keep_alive` expires and the model is evicted.

`summarize_conversation` degrades gracefully — reports `{"summarized": false,
"model_expected": "...", "note": "..."}` if the configured model isn't
installed, rather than failing. `embed_chunks` will raise on a connection
error (retried, then fails) since there's no sensible fallback for an
embedding result.

**Still not built:** a workstation-side submission script/classifier in
`agent.py` that decides when to route a summarize or embed call to the farm
vs. running locally. The queues are reachable and verified; nothing calls them
automatically yet. See also `CHANGELOG/2026-09-02r_summarize_embed_queues_live.md`
for the full deployment record including SSH gotchas, the MLX runner bug fix,
and `.env.mac_worker.generated` cleanup reminder.

## Per-worker model choice — no fleet-wide fixed model

Each worker machine is configured with whichever LLM(s) actually run on its
own hardware — there is no requirement that every farm machine run the same
model as the workstation or as each other. Model choice per node is a
hardware-fit decision (RAM, CPU, whether it has a usable GPU), made when that
node is set up, not a fixed global config. Any workflow that dispatches a
job carrying a model choice (e.g. a future LLM-based judge pass, see
`TODO.md`) must account for this — it cannot assume a uniform model is
available across all connected workers.

### Known worker machines (recorded as connected, 2026-09-02)

| Machine | Role | Hardware | Status |
|---|---|---|---|
| `mac_worker` (`Louises-MacBook-Pro.local`) | first secondary node — connectivity/queue proof-of-concept before the rest of the fleet joins | 2019 MacBook Pro, 16 GB RAM, macOS 13.7.8 x86_64 | Connected via WireGuard hub (`10.90.90.2`); `probe` queue verified end-to-end (`connectivity_probe`), `judge` queue granted per `TODO.md`'s judge_evaluation workflow. **Decided model, 2026-09-02: `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`** (~6.8 GB, installed 2026-09-02). Likely reason, inferred not stated explicitly: this worker will see real chat content the operator already approved for unfiltered secondary-machine handling (see the judge_evaluation trust-boundary decision above) — an ordinary safety-tuned model can refuse to summarize sensitive conversation content, which would silently break `summarize_conversation` for exactly the transcripts most worth compacting. A non-abliterated model would not have that problem for `embed_chunks` (embedding doesn't refuse), so this choice is specific to the summarization use, not a blanket policy. **Quantization chosen: `IQ4_XS` (~6.8 GB).** `summarize` and `embed` queues live and end-to-end verified 2026-09-02; first-call latency ~55s (model cold load + ~18.5s inference on 2019 Intel Mac CPU, no GPU). Set via that worker's own `FARM_SUMMARIZE_MODEL` environment variable (see `worker_farm/tasks.py::_summarize_messages` and `context_compactor.summarize_old_messages`'s new `model=`/`host=`/`timeout=` overrides) — do not hardcode this into shared task code, another future worker may choose differently. |

Update this table as each additional LAN machine joins, per
`docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md`'s "prove connectivity
first" approach — this is the inventory step that plan and `TODO.md`'s
10-node deferred section both call for and neither had started yet.

## Mobile sparse-runtime evaluation

`termux_powerinfer2_edge_worker.py` is a **future gateway contract**, not a
Celery/Redis phone worker. It deliberately refuses non-HTTPS/loopback gateway
URLs, non-allow-listed jobs, oversized prompts, unbounded token requests, and
shell execution. It is not a launcher and is disabled unless invoked manually
with `--once`.

The Pixel 10 Pro plan is at
`docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`. Do not copy the local broker
credentials or AES key to a phone. The mobile process may receive only small,
non-sensitive requests through a future private-overlay gateway with separate
per-device credentials.
