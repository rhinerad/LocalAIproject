# Qwen2.5-VL lazy-load lifecycle benchmark (method only)

**Status:** three controlled lifecycle observations completed on 2026-08-26.
Their output hashes, VRAM peak, and release behavior match, but Windows cache
effects make their process-start figures unsuitable as a reproducible
cold-load metric. A cold-cache protocol and two repetitions are required before
publishing any aggregate performance claim.
See `CHANGELOG/2026-08-26_qwen25_vl_lifecycle_benchmark.md` and the private,
metadata-only report at
`artifacts/benchmarks/qwen25_vl_lifecycle_2026-08-26.json`.

This is the missing “controlled Qwen2.5-VL timing benchmark” from upgrade 20.
It must use only the approved exact pair:

- `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf`
- matching `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf`

No substitute VLM. No Ollama vision model. No render. No Equal Shares job.

## Preconditions

1. Port 8188 is **not** listening.
2. No render-queue owner process is alive.
3. `nvidia-smi` (or the project GPU helper) shows the card idle enough that a
   lazy VLM load will not fight a sampler.
4. Operator has explicitly allowed a model load.

If any precondition fails, stop. Queuing this benchmark behind a render is
allowed; stealing the GPU is not.

## Measurements

Use a public-domain or synthetic still image, not project media. Record:

| Metric | How |
|---|---|
| Cold lazy-load time | watcher start → first successful model-ready log |
| First-analysis latency | model-ready → first caption return |
| Subsequent-analysis latency | second caption on a second benign image |
| VRAM before / during / after | nvidia-smi snapshots at those three points |
| VRAM release time | unload request → VRAM back to the before-load band |
| Text-chat negative control | send a text-only chat; assert the VLM process does not start |
| Render-yield negative control | if ComfyUI later owns 8188, a new media job stays queued |

The opt-in harness is `local_agent/measure_qwen25_vl_lifecycle.py`. Running it
without `--execute` is plan-only. The real measurement needs an explicit model
load approval and a benign input image:

```powershell
python local_agent/measure_qwen25_vl_lifecycle.py <benign-image> --execute --report artifacts/benchmarks/qwen25_vl_lifecycle.json
```

## Output

Write a metadata-only JSON next to the existing caption diagnostic pattern
under `artifacts/benchmarks/`. Allowed fields: timestamps, durations,
VRAM MB, model filenames (not paths), hashes of the diagnostic payload, pass
flags. Forbidden: caption text, file paths, usernames, image content.

Publish only redacted aggregates after **two** matching idle-GPU runs.

## Existing related evidence (not a substitute)

A 2026-08-25 live caption diagnostic already proved the exact pair can load,
return a non-empty result, and release. That run did **not** capture the full
timing/VRAM matrix above. The first full matrix was captured on 2026-08-26; do
not call it a reproducible benchmark until the second matching run exists.
