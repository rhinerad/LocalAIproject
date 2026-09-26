# 2026-09-04m — `run_code` farm offload: measured, not worth building

Date: 2026-09-04. Host: DuranGamingPC (16 logical / 8 physical CPUs).
Id from `python scripts/next_changelog_id.py`: **2026-09-04m**.
Parent: `docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md` Finding 3,
`TODO.md` farm-efficiency ticket 3. Measurement only — **no offload code**.

## What was asked

Before anyone considers sending `run_code` to the farm, gather evidence
that host CPU contention with Ollama generation is real. If it isn't,
close the ticket as not worth building.

## How the agent actually runs (no overlap in normal use)

`agent.py` finishes the Ollama hop (`chat_stream` / farm Qwythos) **then**
executes tools. `run_code` is **not** in `tools.CONCURRENCY_SAFE_TOOLS`,
so even a multi-tool hop runs it on the main thread after generation.
CPU Ollama is capped at `router.CPU_THREAD_CAP = 4` of 16 logical
processors. `:11435` (the dedicated CPU instance) was **down** this
session; GPU `:11434` had no resident model. `router.gpu_busy()` was
True because ComfyUI was listening on `:8188` (idle: 0 % GPU / 2750 MiB /
30 C), so this pass did **not** load a GPU 14B.

Forced overlap below is therefore **more** CPU-adversarial than the GPU
host path (which spends the generate on the RTX 5080, not the 4-thread
CPU cap).

## Real sessions

Saved `local_agent/chats` + `runtime/agentic_tasks` contain **three**
executed `run_code` calls across two conversations, plus many phone
denials that never reached the sandbox:

| Chat | What ran | Outcome |
|---|---|---|
| `54483cb19ddf4de4` (2026-09-01 audit) | `language=bash` `hostname` | refused before exec |
| same | python `subprocess.check_output(['hostname'])` | sandbox traceback (tool_evidence truncated); not a long job |
| `_deleted/cdf27454b0534fb4` | python launch of an `.exe` via subprocess | sandbox traceback; not a long job |

Replay of those payloads through live `tools.run_code` today: hello-world
**0.063 s**, hostname subprocess **0.093 s** (now exit 0), json dump
**0.094 s**. None of these can contend with a generate that takes seconds.

## Forced overlap vs CPU Ollama (worst case we can run without stealing Comfy VRAM)

Script: `artifacts/benchmarks/run_code_cpu_contention_2026-09-04.py`
Raw: `artifacts/benchmarks/run_code_cpu_contention_2026-09-04.json`

Host `:11434`, model `llama3.1:8b` (already pulled), options
`num_gpu:0` / `num_thread:4` / `num_predict:48`. Warmup load 104.5 s,
then three generate-only trials, three overlapping typical `print('hello-world')`,
three overlapping 8 s busy loops. Weights unloaded (`keep_alive:0`);
`/api/ps` empty afterwards.

| Condition | tok/s mean (3 trials) | wall_s mean | generate CPU (process %) | sandbox Python CPU |
|---|---|---|---|---|
| generate only | **10.730** (10.759 / 10.851 / 10.581) | 2.151 | ~330 % (~3.3 of 16) | 0 |
| overlap typical `run_code` | **10.661** (−0.64 %) | 2.032 | ~340–385 % | not visible (call 0.22 s) |
| overlap 8 s busy loop | **10.517** (−1.99 %) | 2.083 | diluted by post-generate samples | ~71–75 % of one core |

Busy loop alone: 8.125 s, ~1 core (`sandbox_python_cpu` p95 101.5 %),
host total CPU ~20 %. Host total during generate-only ~47 % — 16-way
machine is nowhere near saturated. The 2 % tok/s dip on a 1-core spin
loop is measurement noise / tiny cache interference, not a bottleneck.

Caveat on the overlap CPU averages: typical `run_code` finishes in
<0.25 s so the 0.2 s sampler often misses it; busy-loop phases keep
sampling for the full 8 s after the 2 s generate, which **lowers**
reported `ollama_cpu_avg`. Token rate during the overlapping window is
the metric that matters, and it barely moved.

## Decision

**Not worth building.** Finding 3's recommendation is confirmed, not
reversed. Offloading `run_code` over WireGuard would add latency and a
farm-down fallback to a tool that is already local, bounded (30 s / 120 s
cap), sub-second in real use, and does not share a hop with host
inference. Ticket 3 closed. Tickets 1 (`--concurrency=2`) and 4 (Ratchet
Loop) unchanged.
