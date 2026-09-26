# Equal Shares Technical Operations

This records how ChatGPT/Codex has operated the project. Open Interpreter and Gemini must follow this workflow rather than rebuild it.

## Paths

- Live root: `A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2`
- Handoff mirror: `A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`
- ComfyUI: `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI`
- ComfyUI Python: `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe`
- Shared input/output: `A:\Users\rhine\ComfyUI-Shared\input` and `A:\Users\rhine\ComfyUI-Shared\output`
- Raw attempts: `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\attempt_*.mp4`
- API: `http://127.0.0.1:8188`

The live root is authoritative while its supervisor is active. The handoff watcher mirrors changed `outputs` and `work` files about once per minute.

Open Interpreter uses `qwen2.5-coder:14b` through Ollama on `127.0.0.1:11434`. Its launcher wraps every LiteLLM request with `num_gpu=0`, forcing CPU inference so it does not compete with MiniMax for GPU memory. Qwen3 is not used because the installed LiteLLM version misinterprets its separate thinking stream.

## Proven non-Turbo H3 setup

- API graph: `outputs/equal_shares/runtime/proven_manual_minimax_h3_api.json`
- GUI graph: `outputs/equal_shares/runtime/proven_manual_minimax_h3_workflow.json`
- Model: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Text encoder: `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- Video VAE: `minimax_h3_video_vae_fp16.safetensors`
- Audio VAE: `minimax_h3_audio_vae_fp32.safetensors`
- Sampler/scheduler: `res_multistep` / `simple`, denoise 1.0
- Current authoritative steps: 20 single-anchor and 20 dual-anchor
- Generation: 736×416, 16:9, 0.3 MP, multiple 32, 24 fps, 8-bit
- Frame count: round upward to the next value congruent to 5 modulo 17
- One clip per clean ComfyUI backend, SageAttention enabled

Never use `minimax_h3_turbo_4step_ema_ckpt850.safetensors`, Turbo nodes, or Turbo LoRAs. `generation_audit.json` may show the older 13/15-step baseline; current `story_config.json` values of 20/20 override it.

## Supervisor and runner

`work/render_until_complete.py` reads config and manifest, selects the first unresolved clip, clears the old backend, starts ComfyUI on port 8188, runs `outputs/minimax_story_runner.py --resume --only <clip-id>`, then clears the backend and repeats. Never start another supervisor without checking the existing processes, port, and `runtime/render_supervisor.log`.

The runner uploads first/last anchors, loads the proven graph with BOM support, substitutes prompt/negative prompt/seed/frames/duration/output prefix, configures resolution/scheduler/sampler/video saving, and removes the last-frame input for single-anchor clips. Each new attempt increments the seed. It cycles `prompt_variants` when present; otherwise later attempts append retry strategies for static continuity, ordered action beats, locked restrained performance, and endpoint-first anatomy.

Every raw attempt stays in the shared output. The runner creates overview, ending, and every-second validation sheets, makes a silent assembly copy, and merges only the current manifest record so concurrent visual-review decisions are not overwritten.

## Visual review

Mechanical probing is not acceptance. Inspect the complete duration using overview, ending, every-second sheets, literal frames, and source MP4 when necessary. Reject anatomy errors, bad hands, identity drift, merging or duplicated bodies, role swaps, unintended people, architecture/wardrobe/screen-direction drift, incorrect action, object fusion, severe flicker, visible gibberish text, and temporal morphing.

Use `work/build_clip_every_second.py` for strict sheets and `work/reject_clip_visual.py` to reject without deleting raws. Update `visual_audit.json` only after a real visual pass. Gibberish H3 speech alone is not rejection because all H3 audio is discarded.

## Retry and salvage

For failures, vary prompt wording and seed, keep 20 steps, simplify movement, and split overlong actions. If most footage is correct, use clean cuts, approved-frame holds, exact inserts, or subtle motion from existing frames. Existing salvage scripts demonstrate accepted approaches. Preserve and document every original source.

Upscaling only improves detail, softness, and compression. It does not repair warped anatomy or identity changes.

Before making a new image, exhaust prompts, seeds, 20-step retries, shorter clips, cuts, holds, and existing-frame edits. If a new boundary is truly necessary, follow `GEMINI_REFERENCE_IMAGE_GUIDE.md`, upload the exact approved character sheet and closest scene frame, save a new version, and validate it before editing config.

## Audio and finalization

Discard all H3 speech and music. Use:

- `outputs/equal_shares/audio/EQUAL_SHARES_DIALOGUE_TIMELINE.wav`
- `outputs/equal_shares/audio/EQUAL_SHARES_CONTINUOUS_SCORE.wav`

The expected edit is 1266 seconds. `work/finalize_equal_shares_when_ready.py` waits for 124 valid clips, runs `assemble_story.py`, creates the 1344×768 master, and publishes it under `A:\Users\rhine\ComfyUI-Shared\output\equal_shares\final`.

Run `work/audit_equal_shares_completion.py`. Completion requires 124/124 clips valid, every selected raw preserved inside shared output, all assembly clips present, and a 1344×768 H.264 master with AAC audio and duration within two seconds of 1266.

## Progress updates

Give concise plain-language updates at meaningful changes and about once per minute during long work: current clip/stage, running status, pass/fail reason, next solution, and counts. Do not dump raw logs or stop working merely to update the user.
