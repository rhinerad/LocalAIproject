# Media queue clear control and resident-VLM gate repair — 2026-08-24

## What changed

- `local_agent/media_queue.py` now has a `cancelled/` state and
  `clear_pending()`. It preserves each pending job's original arguments and
  timestamps, adding `cancelled_at` and `cancel_reason`; it never removes an
  upload or result file.
- `local_agent/server.py` exposes loopback-only `POST /api/clear_media_queue`.
  It only moves pending jobs. Processing jobs are deliberately untouched.
- `local_agent/static/index.html` now shows pending and running counts
  separately and has **Clear pending media queue**, with an explicit
  preservation warning before it acts.
- The GPU status badge now calls out a resident local vision server instead of
  falsely saying that a render owns the GPU.
- `local_agent/media_queue.py` coalesces an identical pending or processing
  request, preventing duplicate transcription work.
- `local_agent/media_tools.py` and `local_agent/media_watcher.py` distinguish a
  real render claim/ComfyUI server from the resident private Qwen2.5-VL server.
  CPU Whisper no longer waits merely because the vision runtime occupies VRAM;
  the loaded VLM can be reused without demanding cold-load headroom.

## Why

The desktop UI showed three queued media jobs even though no ComfyUI render was
active. The private VLM was incorrectly treated as a foreign GPU workload, so
the watcher withheld CPU-only transcription too. Two records requested the
same `00C.wav` transcription.

## Evidence

At diagnosis, `render_queue_owner.json` was released and port 8188 was closed.
NVIDIA showed the direct `llama-server` consuming about 8.48 GB of VRAM, with
no ComfyUI render. The pending queue held one image-analysis job and two
identical `00C.wav` transcription requests.

## Verification

Run from `local_agent/`:

```text
python test_media_gpu_queue.py
python -m py_compile media_queue.py media_tools.py media_watcher.py server.py
```

Observed: **18 tests, OK**, including preserved clear-pending behavior,
duplicate coalescing, CPU Whisper when no render is active, and the existing
vision queue gates. `py_compile` completed without error. The local app was
reloaded at `http://127.0.0.1:8760` and reports revision
`2026-08-24-qwen25-vl-caption-v4-r21`; the served UI contains both the button
and its loopback endpoint. `python validate_h3_prompt.py --dir
..\\outputs\\equal_shares\\prompts_native_r2v` still reports **124/124 valid**.

## Still unverified

The existing three records are intentionally left pending until the operator
uses the new UI control. The live control was not invoked programmatically, so
those records remain preserved in `media_queue/pending/`; its mutation behavior
is covered by the isolated regression test.
