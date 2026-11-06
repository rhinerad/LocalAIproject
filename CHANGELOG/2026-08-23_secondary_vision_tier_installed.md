# 2026-08-23 — Secondary vision tier installed (llama3.2-vision:11b)

## What changed

### ollama pull
- `llama3.2-vision:11b` pulled from the Ollama registry.
  - Quantisation: Q4_K_M
  - Disk / VRAM footprint: 7.8 GB
  - Capabilities (from `ollama show`): `tools`, `completion`, `vision`
  - Parameters: 10.7 B  •  Context: 131 072 tokens

### local_agent/capabilities.py
- `secondary` tier `vram_need_mb` corrected from `7000` to `8000`
  (7.8 GB on disk; the placeholder 7000 was written before the quantisation
  was known — per the TODO comment removed here).
- Placeholder comment `# slot reserved; pull when on real connection. Update
  vram_need_mb once the quantisation is known.` removed; replaced with a
  factual inline note (`# installed 2026-08-23, Q4_K_M`).

## Why

The `CHANGELOG/2026-08-23_media_gpu_queue.md` "What is still unverified" section
noted: "Secondary tier currently resolves to `huihui_ai/qwen3-vl-abliterated:4b`
since Llama 3.2 11B Vision is not yet installed." Internet was not available when
UPGRADE 09 was built. With a real connection, the intended secondary model is now
pulled and active.

`huihui_ai/llama3.2-vision-abliterated:11b` (the abliterated variant listed first
in `_TIER_DEFS`) does not exist in the Ollama registry under that tag, so the
tier resolves to `llama3.2-vision:11b` — the third entry in the preference list.

## Evidence

### Pull
```
ollama pull llama3.2-vision:11b
pulling 9999d473417a: 100%  7.8 GB
success
```

### ollama show
```
architecture   mllama
parameters     10.7B
quantization   Q4_K_M
capabilities   tools  completion  vision
```

### vision_tiers() after change
```python
python -c "
import sys; sys.path.insert(0, 'local_agent')
import capabilities, router
import json
print(json.dumps(capabilities.vision_tiers(router.GPU_HOST), indent=2))
"
[
  {
    "label": "primary",
    "model": "qwen3-vl-abliterated:8b-q8_0",
    "vram_need_mb": 11500,
    "task_strengths": "OCR, dense diagrams, technical analysis, video frame sequences"
  },
  {
    "label": "secondary",
    "model": "llama3.2-vision:11b",
    "vram_need_mb": 8000,
    "task_strengths": "scene descriptions, narrative captions, quick visual checks"
  }
]
```
Both tiers resolve. Primary unchanged; secondary now `llama3.2-vision:11b` ✓

## What is still unverified

- `llama3.2-vision:11b` has not been tested with an actual image query on this
  machine. The Ollama metadata advertises `vision`; end-to-end inference is not
  confirmed.
- Peak VRAM under load is not measured. The `8000` figure is derived from disk
  size (7.8 GB); actual runtime VRAM may differ once KV-cache and compute
  buffers are added. If the model fails to load at the 8000 + 1024 MB safety
  threshold, raise `vram_need_mb` and file a CHANGELOG entry.
- `huihui_ai/llama3.2-vision-abliterated:11b` remains a first-preference slot
  in `_TIER_DEFS` but is not available on the Ollama registry as of 2026-08-23.
  If it appears later and is pulled, `vision_tiers()` will prefer it automatically
  with no code change required.
