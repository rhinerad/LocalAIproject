# 2026-09-04n — Mac worker `--concurrency=2` experiment: negative result, reverted

Date: 2026-09-04. Host: DuranGamingPC. Mac: Louises-MBP (`10.90.90.2`).
Id from `python scripts/next_changelog_id.py`: **2026-09-04n**.
Ticket: `TODO.md` Farm efficiency ticket 1.
Design note: `docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md` Finding 4.

**Kept `--concurrency=1`.** Wall-clock embed throughput did not improve.
Per-job latency roughly doubled. Flag restored on the live worker.

No repository code change. The launch flag is `FARM_CONCURRENCY` in the
Mac worker `.env` (`/Users/rhineduran/worker_farm/local_agent/worker_farm/.env`),
read by `start_celery_worker.sh` → `local_agent.worker_farm.worker`.

## Hardware (live `sysctl`, not the older "2019 i9" label)

- `machdep.cpu.brand_string`: Intel Core i7-7700HQ @ 2.80 GHz
- `hw.physicalcpu=4` `hw.ncpu=8` `hw.memsize=17179869184` (16 GB)
- Single `ollama serve` (`/usr/local/bin/ollama`, pid 318) on `127.0.0.1:11434`
- Idle before the run: load ~2.0, `machdep.xcpm.cpu_thermal_level=0`, no
  models resident (`/api/ps` empty)

## Method

Realistic backlog shape: eight parallel `embed_chunks` submits, 8 chunks
each (`FARM_EMBED_MAX_CHUNKS=8`), ~3000 chars/chunk, `nomic-embed-text:latest`.
Submitted from the workstation farm venv so both workers hit the live
`embed` queue. One discarded warmup job per concurrency setting (model
load). Sampler on the Mac every 2s: load, thermal level, `vm_stat` swap,
ollama/celery RSS.

c1: existing LaunchDaemon, `--concurrency 1 --pool prefork` (one
ForkPoolWorker).
c2: `FARM_CONCURRENCY=2`, `launchctl kickstart -k system/com.local-agent.celery-worker`,
`--concurrency 2` with ForkPoolWorker-1 **and** ForkPoolWorker-2 both
consuming (overlap confirmed in `worker.stderr.log`).

## Before / after

| | `--concurrency=1` | `--concurrency=2` |
|---|---|---|
| Wall clock, 8 jobs | **90.973 s** | **89.769 s** |
| Throughput | 5.276 jobs/min | 5.347 jobs/min (+1.3%) |
| Client wait min / mean / max | 9.107 / 48.136 / 90.971 s | 20.681 / 51.529 / 89.767 s |
| Worker `succeeded in` min / mean / max | 8.774 / 11.263 / 15.134 s | 11.761 / 20.750 / 23.482 s |
| Fork pool | Worker-1 only | Worker-1 and Worker-2 overlapping |
| Load 1-min min / mean / max | 1.94 / 5.34 / 8.03 | 3.76 / 5.73 / 7.97 |
| `cpu_thermal_level` peak | 63 | 55 |
| Swapouts during run | 0 | 0 |
| Swapins during run | +966 pages (~3.8 MiB) | +870 pages (~3.4 MiB) |
| Failures | 0/8 | 0/8 |

c1 worker times (s): 8.774, 9.726, 10.362, 11.369, 12.108, 10.923, 15.134, 11.706.
c2 worker times (s): 20.289, 23.482, 11.761, 20.963, 23.358, 21.263, 21.784, 23.097.

Warmups (not in the table): c1 9.253 s; c2 13.308 s (cold-ish after the
kickstart). All eight c1 and eight c2 jobs returned 8×768-dim vectors
from `nomic-embed-text:latest`.

## Why this is worse, not a keep

Finding 4 asked whether two concurrent 8-chunk embed calls would raise
*backlog wall-clock throughput*. They did not: **90.97 s vs 89.77 s is
noise**. The two Celery children really did overlap; Ollama did not.
Worker-side time went from ~11 s to ~21 s — each job waited on the same
single `ollama serve`. Client min latency 9.1 s → 20.7 s.

That latency hit is the revert trigger in the ticket ("thermal/latency
degrades"). Interactive `search_docs` farm embed uses
`EMBED_TIMEOUT_S=30`; 21–23 s leaves much less headroom than 9–12 s.
Thermal and swap were *not* the failure mode (no swapouts, thermal peak
no higher than c1). The machine was already at load ~8/8 logical CPUs
on a serialized embed; a second Celery child just split the same CPU.

Did **not** separately time a `summarize`+`embed` mix. Embed+embed is
the lighter pair (nomic-embed only, no mistral-nemo / Qwythos). If that
already saturates Ollama, mixed LLM+embed at concurrency 2 would not
help throughput and would add the 16 GB RAM collision already measured
in `CHANGELOG/2026-09-04h` (qwythos + mistral-nemo + nomic-embed → swap).

## Revert

```
FARM_CONCURRENCY=1
launchctl kickstart -k system/com.local-agent.celery-worker
```

Live after revert: `--concurrency 1 --pool prefork` (pids 25840 / 25843).
`farm_health`: broker yes, `celery@Louises-MBP` responding, expected
tasks including `embed_chunks` / `summarize_conversation` /
`qwythos_evaluate` registered, latency_ms 2278.6.

Repo `worker.py` default stays `FARM_CONCURRENCY=1`. Do not retry 2
without a change on the Ollama side (parallel embed runners, or a
second Ollama) — Celery concurrency alone is not the bottleneck.
