# UPGRADE 19 — verify-repos-first (2026-08-30)

Fetched live from Hugging Face. No filenames invented. Weights were not
downloaded in this session; the V4 Q4_K_M + Q8_0 projector already on disk
were SHA-256'd against the LFS oids below.

## VLM (watcher captioning)

| | V3 (prompt's first candidate) | **V4 (chosen; later caption variant, already the live pin)** |
|---|---|---|
| Repo | `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V3-GGUF` | `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF` |
| Source HF model | (sibling V3 caption checkpoint) | `thesby/Qwen2.5-VL-7B-NSFW-Caption-V4` |
| Identity | Qwen2.5-VL-7B NSFW Caption | Qwen2.5-VL-7B NSFW Caption V4 |

V4 is not a loosely named other model: the repo README states it is static
quants of `thesby/Qwen2.5-VL-7B-NSFW-Caption-V4`, Apache-2.0, tags
`qwen2.5-vl`, `image-captioning`, `nsfw`. V3 still exists; it is **not**
the file the watcher is pinned to.

### Chosen pair (Q4_K_M + matching Q8_0 mmproj from the **same** V4 repo)

| File | Bytes | SHA-256 (Hugging Face LFS oid) |
|---|---|---|
| `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.gguf` | 4,684,339,808 | `e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d` |
| `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.gguf` | 732,298,784 | `470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1` |

Same-repo mmproj-f16 also exists (`Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-f16.gguf`,
1,368,264,224 bytes, sha256 `91f3358f84c56726542126097bde92085a1a14c3e4a2aed949425f53609e2a43`).
The live pin uses the Q8_0 projector (VRAM headroom), not f16.

Local verified copies (`.local.gguf` suffix) hashed 2026-08-30:

- `...\Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf` — 4684339808 bytes, sha256 matches V4 Q4_K_M above
- `...\Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf` — 732298784 bytes, sha256 matches V4 mmproj-Q8_0 above

A leftover `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.gguf` of 2,437,632,000 bytes
is a truncated transfer and is **not** the pin.

V3 Q4_K_M for the record (not used): `Qwen2.5-VL-7B-NSFW-Caption-V3.Q4_K_M.gguf`
4,683,072,576 bytes, sha256 `13dedf926d3a99f1087ab80b91591d8c17154c2887bfa6a00e70160c7d45b872`.
Its matching projector is `Qwen2.5-VL-7B-NSFW-Caption-V3.mmproj-Q8_0.gguf`
(853,119,744 bytes) — **not** interchangeable with the V4 mmproj.

## Runtime (not Ollama)

Current Ollama GGUF import still rejects this caption GGUF. The watcher starts
CUDA `llama-server.exe` on `127.0.0.1:11436` with the two pinned files.
`Modelfile.qwen25-vl-nsfw-caption` is the identity record + FROM pair; it is
not `ollama create`'d.

## Diffusion (UPGRADE 13 gate)

| | |
|---|---|
| Repo | `starsfriday/Qwen-Image-NSFW` |
| File | `qwen_image_nsfw.safetensors` |
| Bytes | 188,807,872 |
| SHA-256 | `af10a4787691e56cd72803eeaed7f249c1b689583938147cd4ddb31e7d2e1350` |
| Kind | **LoRA** (`library_name: diffusers`, tags `lora`, `Qwen-Image`) |
| Base | `Qwen/Qwen-Image` |
| Local file | **absent** (`ComfyUI-Shared\models\diffusion_models\qwen_image_nsfw.safetensors`) |

`work/image_render.py` only builds `CheckpointLoaderSimple` graphs for
`RealVisXL_V5.0_fp16.safetensors`. It has no LoRA loader, no Qwen-Image UNET
path, and no model inventory beyond the `ckpt_name` string. There is **no
clean gate** to hang this LoRA behind without inventing a second graph. Identity
is recorded in `capabilities.capability("qwen_image_diffusion")` and is never
loaded at import.

## Human follow-up (no GPU run in this session)

Files are already on disk and checksum-verified. To confirm the watcher can
load them (operator-owned GPU, ComfyUI down):

```
python local_agent\verify_qwen25_vl_caption.py <controlled-image> --report local_agent\runtime\benchmarks\qwen25_vl_caption_identity_2026-08-30.json
```

If the `.local.gguf` pair is missing on another machine:

```
powershell -File local_agent\setup_qwen25_vl_caption.ps1 -Download
```

That script now refuses a SHA-256 mismatch. Do not `ollama create` this pair.
Do not pass `qwen_image_nsfw.safetensors` as `image_render.py --model`.
