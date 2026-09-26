# 2026-08-26 — exact Qwen2.5-VL lifecycle benchmark, run 1

## Scope

One controlled, unattended lifecycle run using only the approved local pair:

- `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf`
- `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf`

The input was a synthetic geometric still created only for this measurement.
No user upload, project media, render, download, or ComfyUI job was used.

## Measured evidence

Metadata-only report:
`artifacts/benchmarks/qwen25_vl_lifecycle_2026-08-26.json`.

| Metric | Result |
|---|---:|
| GPU before | 0 MB |
| Cold lazy load | 52.844 s |
| GPU after load | 10,530 MB |
| First factual analysis | 30.281 s; non-empty |
| GPU after first analysis | 10,624 MB |
| Second factual analysis | 0.375 s; non-empty |
| GPU after second analysis | 10,628 MB |
| Release to idle | 22.187 s |
| GPU after release | 0 MB |

The report identifies runtime `llama.cpp` and exact model
`qwen25-vl-nsfw-caption:v4-q4_k_m`; it stores result hashes and sizes, not
caption text, image content, local file paths, or user information.

## Lifecycle reliability repair

The benchmark exposed a Windows ownership-probe flaw: `os.kill(pid, 0)` can
return access-denied for a live process, which the old helper treated as gone.
`capabilities._runtime_pid_alive()` now uses `tasklist` on Windows and treats a
failed probe as still live. Cleanup therefore fails safe and preserves its
ownership record rather than falsely claiming VRAM was released.

The first run's VLM cleanup needed a one-time elevated termination of the exact
owned `llama-server` process after the old probe misreported it. The repaired
probe is covered by `local_agent/test_qwen25_release.py` (2/2). Final telemetry
after cleanup: 0% GPU, 0 MB VRAM, 31 C.

## Remaining evidence

## Follow-up runs and negative controls

Two more identical synthetic-image runs completed after the first run. All
three used the same exact model/runtime, returned the same two output hashes,
peaked at 10,626–10,628 MB, and released to 0 MB.

| Run | Process-start/load s | First analysis s | Second analysis s | Release s |
|---|---:|---:|---:|---:|
| 1 | 52.844 | 30.281 | 0.375 | 22.187 |
| 2 | 38.015 | 2.640 | 0.407 | 2.015 |
| 3 | 5.563 | 1.141 | 0.406 | 2.047 |

The later launch times are materially faster because Windows retained filesystem
and/or driver caches after run 1. Therefore the three values are **not** a
reproducible cold-load metric and must not be averaged or published as one.
They do establish stable exact-model output, VRAM peak, warm-process latency,
and release behavior.

Two negative controls were added and passed without loading any model:

- an ordinary text chat cannot call the exact VLM runtime;
- active render ownership blocks VLM work before a VRAM/runtime check.

Evidence: native tool suite 22/22; exact-Qwen watcher suite 5/5;
`test_qwen25_release.py` 2/2; H3 validator 124/124. No chat model or ComfyUI
render was started for these controls.

## Remaining evidence

Design a cold-cache protocol before making a cold-load claim, then repeat it
twice. The current measurements remain private lifecycle observations. The
text-chat and ComfyUI-ownership controls are mocked regression checks; a later
real-render observation may supplement them but must never start a render only
for the benchmark.
