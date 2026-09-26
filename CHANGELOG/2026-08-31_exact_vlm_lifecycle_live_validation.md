# 2026-08-31 — Exact Qwen2.5-VL lifecycle live validation

## Controlled result

With ComfyUI port 8188 closed and no render owner, the corrected lazy runtime
was measured against an existing local test image. The metadata-only report is
`artifacts/benchmarks/qwen25_vl_lifecycle_2026-08-31_final.json`; it contains no
caption text or image path.

| Measurement | Result |
|---|---:|
| Exact model | `qwen25-vl-nsfw-caption:v4-q4_k_m` |
| Runtime | local CUDA llama.cpp on `127.0.0.1:11436` |
| Cold load | 24.047 s |
| First analysis | 30.875 s, non-empty (806 chars) |
| Second analysis | 0.969 s, non-empty (58 chars) |
| Release confirmation | 2.047 s |
| VRAM after release | 81 MB baseline |

The final post-release router report selected
`huihui_ai/qwen3-abliterated:14b` on GPU. No ComfyUI workflow or render was
started, and the temporary VLM process was no longer present.

## Windows cleanup correction

The first controlled run showed that `taskkill` can report success/permission
ambiguity incorrectly for this local CUDA child. Liveness detection now uses
the same local PowerShell `Get-Process` mechanism that can see the server, and
owned cleanup uses PowerShell `Stop-Process` on the PID recorded directly from
the launcher. The final live run verified this complete load/analyze/release
cycle.

## Regression coverage

- `test_qwen25_vl_identity.py` — 7 passed.
- `test_media_analysis.py` — 20 passed.
- `test_media_watcher_exact_qwen.py` — 7 passed.
