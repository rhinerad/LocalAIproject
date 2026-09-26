# 2026-08-30 — UPGRADE 19: Qwen2.5-VL Caption V4 identity pin

## What changed

- Verified the live Hugging Face trees (no assumed filenames). Notes:
  `local_agent/UPGRADE/notes/nsfw_vision_model.md`.
- Pinned the watcher to the **exact** V4 pair, SHA-256 as well as size:
  `capabilities.py` `qwen25_vl_checksums_ok()`; `ensure_qwen25_vl_runtime()`
  returns False on missing file or hash mismatch and does not `Popen`
  llama-server.
- Recorded the same hashes in `Modelfile.qwen25-vl-nsfw-caption` and
  `setup_qwen25_vl_caption.ps1` (exact byte length + SHA-256; no Ollama import).
- Recorded `starsfriday/Qwen-Image-NSFW` / `qwen_image_nsfw.safetensors` as a
  **Qwen-Image LoRA**, not an SDXL checkpoint. Did **not** wire it into
  `work/image_render.py` — that planner only builds `CheckpointLoaderSimple`
  graphs for RealVisXL. Identity lives on `capability("qwen_image_diffusion")`.
- Tests: `local_agent/test_qwen25_vl_identity.py`.
- Index row 19 updated. Did not edit `router.py`, `agent.py`, `ollama_client.py`,
  `tools/powerinfer/**`, or `work/audit_equal_shares_completion.py` (other live
  sessions). This tree has no `.git`; isolation was by timestamp.

## Why

Row 19 was still listed as unbuilt. The watcher already used these V4 files
(UPGRADE 09 supersession) but only with a size floor, so a truncated or swapped
GGUF of similar length could start. The original 19 prompt's Ollama import path
is still rejected by current Ollama; llama.cpp remains the runtime.

## The evidence — exact repos/files/checksums

Fetched `https://huggingface.co/api/models/<repo>/tree/main` on 2026-08-30.

**Chosen VLM** (not V3; V4 is the later caption variant and matches the live pin):

| | |
|---|---|
| Repo | `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF` |
| Source | `thesby/Qwen2.5-VL-7B-NSFW-Caption-V4` |
| Weights | `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.gguf` |
| Weights bytes | 4,684,339,808 |
| Weights SHA-256 | `e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d` |
| mmproj | `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.gguf` (same repo) |
| mmproj bytes | 732,298,784 |
| mmproj SHA-256 | `470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1` |

Local `.local.gguf` copies hashed in this session: **both SHA-256 values match**.

V3 still exists (`mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V3-GGUF`, Q4_K_M sha256
`13dedf926d3a99f1087ab80b91591d8c17154c2887bfa6a00e70160c7d45b872`) and is not used.
Its mmproj is a different size (853,119,744) and must not be paired with V4 weights.

**Diffusion identity (not loaded):**

| | |
|---|---|
| Repo | `starsfriday/Qwen-Image-NSFW` |
| File | `qwen_image_nsfw.safetensors` |
| Kind | LoRA for base `Qwen/Qwen-Image` |
| Bytes | 188,807,872 |
| SHA-256 | `af10a4787691e56cd72803eeaed7f249c1b689583938147cd4ddb31e7d2e1350` |
| On disk | absent |

## What was verified after

```
python local_agent/test_qwen25_vl_identity.py -v
Ran 5 tests in 1.385s
OK

python local_agent/test_qwen25_setup_script.py -v
Ran 1 test in 0.044s
OK

python local_agent/test_media_watcher_exact_qwen.py -v
Ran 5 tests in 0.001s
OK
```

`test_media_analysis.py` was run for regression. The checksum KeyError in
`test_action_model_accepts_complete_lazy_gguf_pair` was fixed (`size_ok` kept
alongside `large_enough`). Two other failures in that file
(`test_existing_whisper_capability_routes_transcription_without_loading_a_model`,
`test_inline_video_prompt_is_found`) are environment/sample-file issues and
were not caused by the identity pin.

No model download, no GPU inference, no `ollama create`.

## What is still unverified

- Live `verify_qwen25_vl_caption.py` load in this session (operator GPU).
- Ollama import of this GGUF (previously rejected; not retried).
- Any Qwen-Image generation path — 13 cannot host this LoRA without a new graph.
