# 2026-08-23 — MiniCPM-V 2.6 video action extractor

## What changed

### local_agent/capabilities.py
- Added `MINICPM_V_MODEL = "openbmb/minicpm-v2.6:8b"` constant.
- Added `MINICPM_VRAM_MB = 7500` constant.
- Added `action_model(host) -> tuple[str, int]`: checks whether MiniCPM-V 2.6 is
  installed and advertises the `vision` capability on the GPU server; returns
  `(MINICPM_V_MODEL, MINICPM_VRAM_MB)` or raises `RuntimeError` with an explicit
  `ollama pull openbmb/minicpm-v2.6:8b` instruction.  Callers must handle
  `RuntimeError` — the function never crashes the router.

### local_agent/media_tools.py
- Added `_action_frame_instruction(n_frames, fps, focus_character, format_h3_beats)`:
  builds the per-pass instruction that tells MiniCPM-V the frame count, FPS, and
  required output format (`[00:00 - 00:01]: <action>` or Equal Shares H3 beats).
- Added `_ACTION_BATCH_SIZE = 30`: clips ≤ 30 frames run in a single Ollama pass;
  longer clips are chunked into 30-frame batches, each labeled with its time window.
- Added `extract_video_actions(args) -> str`:
  1. Validates `video_path` (absolute or repo-relative; must be a known video extension).
  2. Calls `caps.action_model()` — returns `{"available": False, "install": "..."}` if
     MiniCPM-V is not installed, rather than raising.
  3. VRAM gate: checks `router.gpu_free_mb() >= 7500 + 1024` **and**
     `not router.gpu_busy()`.  If either fails, enqueues as `kind="video_action"` and
     returns `{"queued": True, "job_id": ...}`. Does **not** fall back to CPU.
  4. Extracts frames with `ffmpeg -vf "fps={fps},scale=768:-1"` into a temporary
     directory `local_agent/uploads/tmp_frames_<uuid>/`.
  5. Sends batches to MiniCPM-V 2.6 via `_run_vision_gpu`.
  6. Always removes the temporary frame directory on exit (success or error);
     never touches the source video.
  7. Optional `focus_character` string woven into the instruction;
     `format_h3_beats=true` switches output to `[N-M s]` H3 beat notation.

### local_agent/tools.py
- Added `def extract_video_actions(args) -> str` shim (calls `_media(...)`).
- Added to `TOOLS` dict under the sensory section, after `analyze_video`.
- Added to `_SCHEMAS` dict with three properties:
  - `video_path` (string, required)
  - `format_h3_beats` (boolean, optional, default false)
  - `focus_character` (string, optional)

### local_agent/media_watcher.py
- Added `_minicpm_ready() -> bool`: returns True when
  `gpu_free_mb >= MINICPM_VRAM_MB + VRAM_SAFETY_MB` **and** `not gpu_busy()`.
- Added `_run_video_action_job(job)`: claims and executes one `video_action` job via
  `media_tools.extract_video_actions(args)`.  If the result comes back
  `{"queued": True}` (GPU became busy between claim and execution), moves the job to
  `failed/` with a message to re-queue manually.
- Added video_action drain loop in `run_once()` (after the analyze_video loop, before
  the transcribe loop):
  - Calls `caps.action_model()` to confirm MiniCPM-V is installed; skips silently if
    not.
  - Loops while `_minicpm_ready()`, claiming and running `video_action` jobs.
  - After the batch drains, calls `router.unload(GPU_HOST, MINICPM_V_MODEL)` so
    MiniCPM-V does not hold VRAM against subsequent ComfyUI renders.

## Why

The existing `analyze_video` tool uses the primary vision model (Qwen3-VL 8B Q8_0)
and produces per-second observations plus adjacent-frame motion comparisons.  That is
good for short reference clips.  For longer reference video or checking a test take
frame-by-frame, the operator needed a tool that:
- Explicitly orders all frames in a single model call so the model produces a
  coherent chronological log rather than isolated per-frame snapshots.
- Supports `format_h3_beats` to produce output ready to paste into an H3
  `detailed_description` block.
- Uses MiniCPM-V 2.6, which is specifically trained on multi-image / multi-frame
  inputs, making it a better fit for dense action logging than a general VL model.

MiniCPM-V 2.6 is not yet installed (`openbmb/minicpm-v2.6:8b`).  The tool gates on
`caps.action_model()` and returns a clear install message rather than crashing.  The
watcher also gates on `caps.action_model()` so queued jobs are simply held until the
model is pulled.

## Evidence

### Tool registration
```python
import tools
tools.TOOLS["extract_video_actions"]    # callable ✓
tools._SCHEMAS["extract_video_actions"] # schema with video_path required ✓
```

### Constants
```
MINICPM_V_MODEL : openbmb/minicpm-v2.6:8b ✓
MINICPM_VRAM_MB : 7500 ✓
```

### action_model() gate (tested before and after pull)
Before pull:
```
RuntimeError: 'openbmb/minicpm-v2.6:8b' is not installed … ✓
```
After `ollama pull openbmb/minicpm-v2.6:8b` (Q4_0, 7.6B, 5.5 GB, vision ✓):
```
action_model(): model=openbmb/minicpm-v2.6:8b  vram=7500 MB ✓
```
`ollama show` confirms: architecture=qwen2, parameters=7.6B, quantization=Q4_0,
capabilities: completion + vision, projector: CLIP 503.97M.

### Regression
```
python local_agent/test_native_tool_calling.py   9/9 OK ✓
python local_agent/test_media_analysis.py        8/9 (1 pre-existing Whisper failure) ✓
python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v
124/124 valid ✓
```

## What is still unverified

- `extract_video_actions` has not been exercised end-to-end with a live MiniCPM-V
  model.  `openbmb/minicpm-v2.6:8b` is now installed and `action_model()` resolves,
  but a real frame-extraction → Ollama call has not been observed.  Call the tool on
  a short test video to verify: frame extraction, single-pass call, the H3-beats
  format path, and temp-dir cleanup.
- Batch chunking (> 30 frame clips) is untested.  All Equal Shares clips are 8–15 s
  (8–15 frames at 1 FPS), so the `_ACTION_BATCH_SIZE = 30` guard will never be
  exercised by project video.  Test with a reference clip longer than 30 s.
- The watcher's MiniCPM unload path (`router.unload(GPU_HOST, MINICPM_V_MODEL)`)
  is untested under a live model load.
- `focus_character` is only woven into the instruction; MiniCPM-V's per-character
  attention was not measured against a real video.
