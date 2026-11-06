# 2026-09-04y — CPU Ollama :11435 disables Vulkan (ollama#16508)

Date: 2026-09-04. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04y**.

Closes the ops ticket opened from the empty-completion investigation
(`CHANGELOG/2026-09-04r_empty_completion_guard.md`, chat
`7d474ba55d244abe`). Independent of that PR.

## Root cause

Ollama **0.32.15**: `CUDA_VISIBLE_DEVICES=-1` only skips CUDA discovery.
Vulkan stays on by default (`OLLAMA_VULKAN:true`) and still enumerates
the RTX 5080. Upstream: [ollama#16508](https://github.com/ollama/ollama/issues/16508).
The dedicated CPU server on `127.0.0.1:11435` was advertising the card
over Vulkan. When 11435 was down, `router._paired_cpu_fallback` used
`gpu_store_cpu_only` on **11434**, which GPU-loaded Huihui 8B (41/41
layers, ~8161 MiB) while Comfy `:8188` was up (HTTP 499).

Not a Windows env-propagation miss: the launcher did set
`CUDA_VISIBLE_DEVICES=-1` on the child. Short diagnostic `ollama serve`
processes that vanished mid-discovery were job-object kills of the
parent, not a native crash.

A session-only CPU `:11435` (pid 30080, `OLLAMA_VULKAN=false`) was
started during diagnosis as a **manual stopgap**. It is not this fix.
The verification `Start-Server` child (pid 19960) was replaced after
the checks by another session-lived `ollama serve` with the same three
env vars so a test-job teardown would not take 11435 down again.
Durable ops path is the patched desktop launcher.

## What shipped

`local_agent/START_LOCAL_AGENT_GUI.ps1` `Start-Server` when `$CpuOnly`:

- keep `CUDA_VISIBLE_DEVICES=-1`
- add `OLLAMA_VULKAN=false`
- add `GGML_VK_VISIBLE_DEVICES=-1`

GPU `Start-Server` still does not set those three.

## Before / after (live process)

Before (diagnosis, launcher env = CUDA `-1` only, pid 43000 via psutil):

```
CUDA_VISIBLE_DEVICES=-1
OLLAMA_VULKAN=<unset>
```

Ollama log: `OLLAMA_VULKAN:true`, then
`inference compute ... library=Vulkan ... NVIDIA GeForce RTX 5080`
`total="15.6 GiB"`.

After (this PR, **actual** `Start-Server '127.0.0.1:11435' 'cpu' $true`
from the patched launcher, pid 19960 via psutil):

```
CUDA_VISIBLE_DEVICES=-1
OLLAMA_VULKAN=false
GGML_VK_VISIBLE_DEVICES=-1
OLLAMA_HOST=127.0.0.1:11435
```

Ollama log (`local_agent/ollama_cpu.err.log`):

```
OLLAMA_VULKAN:false
user overrode visible devices CUDA_VISIBLE_DEVICES=-1
user overrode visible devices GGML_VK_VISIBLE_DEVICES=-1
inference compute id=cpu library=cpu ... total="30.9 GiB"
vram-based default context total_vram="0 B"
```

Matches the 2026-09-03bb eval configuration that already proved
`id=cpu` / `total_vram=0 B`.

## Fallthrough (Comfy :8188 up)

`router.decide("auto")`: `tier=cpu` `host=127.0.0.1:11435`
`model=huihui_ai/qwen3-abliterated:8b` `gpu_busy=True`
(`a ComfyUI backend is listening on port 8188`). Chat hop
`num_gpu:0` `num_thread:4` `num_ctx:16384` replied `ping`.

- 11435 `/api/ps`: 8B loaded, **`size_vram`: 0**, llama-server
  `-ngl 0 -t 4`, `reason=cpu`
- 11434 `/api/ps`: `{"models":[]}` before and after (only GET
  `/api/ps` + `/api/tags` in `server.log`; no chat/load)
- nvidia-smi compute: Comfy `python.exe` + Brave; no llama-server

## Tests

```
python local_agent/test_launcher_kv_cache.py -q
  Ran 4 tests
  OK
```

New assertion: CPU `Start-Server` sets CUDA `-1`, `OLLAMA_VULKAN=false`,
and `GGML_VK_VISIBLE_DEVICES=-1`; the GPU flash_q8 branch does not.
