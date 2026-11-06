# Equal Shares — Project Continuation Brief

> **Local-agent current-state notice (2026-08-25):** This brief is historical
> production context. The Equal Shares pipeline is currently paused. For the
> general local assistant and storyboard feature work, use
> `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md` and `local_agent/README.md`.
> Do not copy current state into the parent `outputs/` fork.

> **Authoritative 2026-08-13 correction:** This file remains useful for project
> history and paths, but its audio/render order is superseded by `CLAUDE.md`,
> `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`, and
> `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md`. The current pipeline completes and accepts
> all 124 native MiniMax H3 soundtracks at 0.2 MP first, then generates picture
> around those exact WAVs at 0.9→0.4 MP. Do not follow any statement below that
> says H3 audio is discarded, dialogue is replaced by default, a 0.9 MP
> single-pass branch may continue, or resolution must stop at 0.8 MP.
>
> The product goal is also broader than this film: Equal Shares is the proving
> project for a reusable automated ComfyUI story-generator backend. Complete the
> headless backend before beginning the GUI. See
> `docs/AUTOMATED_STORY_GENERATOR_BACKEND_SPEC.md`.

Written August 10, 2026, from direct inspection of the files in this folder and the live root above it. Everything marked **verified** was read from disk on that date. Everything marked **unverified** could not be checked from the inspecting environment and must be confirmed on the Windows host before it is relied on.

---

## 1. Read this first: the active tree has moved

This is the single most important fact in the brief, and it contradicts `archive/superseded_docs/TECHNICAL_OPERATIONS.md`.

`archive/superseded_docs/TECHNICAL_OPERATIONS.md` states that the live root is authoritative and that this handoff folder is a once-per-minute mirror of it. **That is no longer true.** As of August 10, 2026:

| | Live root `...\referenced-chatgpt-conversation-this-is-an-2\outputs` | This folder `...\COMFYUI_STORY_HANDOFF_2026-08-09\outputs` |
|---|---|---|
| `manifest.json` clip entries | 44 | 77 |
| `manifest.json` mtime | 2026-08-10 01:43:27 | 2026-08-10 17:29:18 |
| `render_supervisor.log` last line | `01:46:11 ComfyUI API ready` | `17:29:32 Started ComfyUI pid=13980` |
| State | frozen | **active** |

The sync watcher (PID `33760`, recorded in `archive/stale_state/SYNC_WATCHER.pid`) wrote its last entry to `archive/stale_state/SYNC_LOG.txt` at `2026-08-10T02:22:44` and stopped. `archive/stale_state/SYNC_STATUS.json` is frozen at that moment and still reports `44/124 valid, next=10B`. **Do not trust `archive/stale_state/SYNC_STATUS.json`.** It is roughly fifteen hours stale and understates progress by more than thirty clips.

Some time around 01:46 the supervisor was restarted with this handoff folder as its project root. It has been rendering into this folder ever since. The mirror became the working tree.

**Consequence:** the authoritative state is `COMFYUI_STORY_HANDOFF_2026-08-09\outputs\equal_shares\manifest.json`. The live root's copy is a stale fork. Anyone who reads `archive/superseded_docs/TECHNICAL_OPERATIONS.md`, concludes the live root is authoritative, and starts a supervisor there will start a second ComfyUI backend competing for port 8188 and for GPU memory, and will begin writing a third divergent manifest. That is the failure mode this brief exists to prevent.

Before any other decision, resolve which tree is canonical and correct or retire the stale one. Recommended: treat this handoff folder as canonical, and either restart the sync watcher in reverse (mirroring this folder outward) or leave the live root alone as a frozen 01:43 snapshot.

---

## 2. Current state (verified)

- **Configured clips:** 124, from `outputs/equal_shares/story_config.json`.
- **Clips present in the active manifest:** 77.
- **Clips not yet rendered:** 47, beginning at `19A`. The full remaining head is `19A, 19B, 19C, 19D, 20A, 20B, 20C, 20D, 20E, 21A, …`.
- **Supervisor:** running. Last log line `[2026-08-10T17:29:32] Started ComfyUI pid=13980`, working `19A`. The loop is behaving normally — a clean backend start, an API-ready line, a stop-and-clear, and a progress line, repeating roughly every seven to nine minutes per clip.
- **Rendering throughput:** approximately eight minutes per clip across the 15:35–17:29 window. At that rate the remaining 47 clips represent roughly six hours of unattended rendering.

### The visual review backlog is the real bottleneck

`outputs/equal_shares/visual_audit.json` reports:

- `reviewed_through`: `09C`
- `accepted_count_at_review`: **43**
- `reviewed_pass`: a list of 43 clip IDs, running `00A` through `09C` continuously with no gaps
- `review_method`: overview and ending contact sheets, with every-second sheets for the strict opening-role clips

The manifest held 77 rendered clips when this brief was drafted and 78 a few minutes later. Visual review has only reached `09C`. **Around 35 rendered clips have never been visually reviewed, and the number grows by one roughly every eight minutes while the render runs.** The supervisor's own log line reads "Progress N/124 valid clips," which counts mechanically valid renders, not accepted ones — that number is not an acceptance count and should never be reported as one.

This matters because `archive/superseded_docs/TECHNICAL_OPERATIONS.md` is explicit that mechanical probing is not acceptance, and because a rejection at, say, `11B` may invalidate downstream clips whose first frames were derived from it. The longer rendering runs ahead of review, the more expensive a mid-sequence rejection becomes. Consider pausing the render at a clean clip boundary and clearing the review backlog before rendering deeper into the twenties.

### Accepted corrections that must not be undone

- `04C` attempt 4 is the accepted take. It begins after Kent has already declined: no bill, no donation, no transaction, no reaching toward the plate; his hands stay on the closed wallet while the attendant and plate leave. **Never reselect `04C` attempt 3**, which visibly showed him removing a bill.
- `06C` accepted via an exact-invoice clean insert.
- `07C` attempt 2 accepted after correction.
- `08B` accepted via a clean-motion salvage.
- `08C` and `09A`–`09C` completed and passed review.

---

## 3. Production settings (verified against `story_config.json`)

These values are read directly from the active config and override any older figures in `generation_audit.json`.

```
server                 http://127.0.0.1:8188
comfy_root             A:/Users/rhine/ComfyUI-Installs/Rockernow/ComfyUI
api_workflow           runtime/proven_manual_minimax_h3_api.json
workflow_profile       proven_manual_h3
width x height         736 x 416   (16:9, 0.3 MP, multiple of 32)
fps                    24
bit_depth              8
steps_single_anchor    20
steps_dual_anchor      20
dual_anchor_max_seconds 8.0
frame_count_mode       minimax_h3_24fps_17n_plus_5
duration_tolerance     1.0
retries                0
timeout_seconds        2400
poll_seconds           5
comfy_output_root      A:/Users/rhine/ComfyUI-Shared/output
comfy_input_root       A:/Users/rhine/ComfyUI-Shared/input
planned_runtime        21:21  (1281 s)
planned_editorial_runtime  21:06  (1266 s)
```

Model stack, from `archive/superseded_docs/TECHNICAL_OPERATIONS.md`:

- Model: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Text encoder: `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- Video VAE: `minimax_h3_video_vae_fp16.safetensors`
- Audio VAE: `minimax_h3_audio_vae_fp32.safetensors`
- Sampler / scheduler: `res_multistep` / `simple`, denoise 1.0
- SageAttention enabled, one clip per clean backend

**Prohibited without exception:** `minimax_h3_turbo_4step_ema_ckpt850.safetensors`, any Turbo node, any Turbo LoRA. Full-quality H3 only.

The negative prompt in effect for every clip is:

> cruel sneering people, obvious villain, dystopian grime, identity drift, face change, wardrobe change, continuity error, duplicate person, missing person, deformed anatomy, extra limbs, flicker, jump cut, text artifacts, watermark, low quality, blurry

---

## 4. The one-backend rule

`render_until_complete.py` owns the backend lifecycle: it selects the first unresolved clip, clears any old backend, starts ComfyUI on port 8188, runs `minimax_story_runner.py --resume --only <clip-id>`, then clears the backend and repeats. One clip per clean backend is deliberate — it prevents VRAM fragmentation and cross-clip state leakage across a 124-clip run.

Because exactly one process may own port 8188 and the GPU, **any agent, script, or person must verify before launching anything**:

1. Check for a running `render_until_complete.py` and for ComfyUI Python processes.
2. Check whether port 8188 is bound.
3. Read the tail of `outputs/equal_shares/runtime/render_supervisor.log` and compare its timestamp to the current clock.

If the log is advancing, the render is alive. Adopt or monitor it. Do not start a competing supervisor, do not start a bare ComfyUI backend for a side experiment, and do not run the finalizer expecting it to render anything.

Note that the Open Interpreter setup deliberately pins `qwen2.5-coder:14b` to CPU (`num_gpu=0`) through Ollama on `127.0.0.1:11434` precisely so the assistant model does not contend with MiniMax for VRAM. Preserve that constraint if Open Interpreter is used again. Qwen3 is avoided because the installed LiteLLM version mishandles its separate thinking stream.

---

## 5. Continuity locks (non-negotiable)

Opening waiting-room sequence:

- The receptionist is the only woman, and she never leaves the area behind the staff-only window.
- Exactly two male visitors perform the chair interaction — Person 1 and Person 2, nobody else.
- Both men enter through the separate doorway and remain on the public side.
- One public chair, at screen-left.
- The Narrator appears only where the approved script explicitly places him, and must never resemble Kent.
- No glass gate, glass fence, invented divider, extra chair, or third male visitor.

Identity: `outputs/equal_shares/references/alex_vale_master_v1.png` and `alex_vale_source.jpg` are authoritative for **Kent Brentwood**. `ensemble_cast_master_v1.png` shows, left to right: Kent Brentwood, Avery Renfield, Doris Lovelay, Ryann Sally, Faith White. The faces and clothing in that sheet override any conflicting prose description anywhere in the project.

---

## 6. Rejection criteria and salvage ladder

Reject a take for: warped, duplicated, merged, disappearing, or anatomically incorrect bodies; broken faces, hands, fingers, limbs, or object interactions; identity, wardrobe, location, architecture, or screen-direction drift; unintended people, incorrect blocking, role swaps, or actions contradicting the script; severe flicker, temporal morphing, visible gibberish text, or disruptive artifacts.

Historical note: this rule applied to the earlier visual-first assembly. Under
the authoritative audio-first pipeline, gibberish or invented music is a Stage-1
audio rejection. Stage-2 visual review remains separate because the accepted
Stage-1 WAV is muxed back onto any visually accepted picture.

Upscaling improves softness, detail, and compression. It does not repair warped anatomy or temporal identity change. Structurally broken footage must be regenerated, shortened, or cleanly edited before any enhancement.

Salvage ladder, cheapest first — exhaust each rung before climbing:

1. Vary prompt wording; vary seed. Keep 20 steps.
2. Simplify or slow the movement; split an overlong action into ordered beats.
3. Shorten the clip.
4. Clean cut, or a hold on an approved frame.
5. An exact insert or subtle motion built from existing approved frames. Working examples live in `work/salvage_*.py`, `work/select_*.py`, and `work/repair_*.py`.
6. Only after all of the above: a new boundary image, per `docs/GEMINI_REFERENCE_IMAGE_GUIDE.md` or `docs/LOCAL_IMAGE_GEN_FALLBACK.md`.

Preserve every original attempt under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`. Use `work/reject_clip_visual.py` to reject without deleting raws, and `work/build_clip_every_second.py` for strict contact sheets.

---

## 7. Audio and final delivery

All H3 speech and music are discarded. The delivered audio is:

- `outputs/equal_shares/audio/EQUAL_SHARES_DIALOGUE_TIMELINE.wav`
- `outputs/equal_shares/audio/EQUAL_SHARES_CONTINUOUS_SCORE.wav`

`work/finalize_equal_shares_when_ready.py` waits for 124 valid clips, runs `assemble_story.py`, builds the 1344×768 master, and publishes to `A:\Users\rhine\ComfyUI-Shared\output\equal_shares\final`. Target file: `outputs/equal_shares/EQUAL_SHARES_FINAL_1344x768.mp4`.

Completion requires all of: 124/124 clips valid; every clip visually accepted; every selected raw preserved in the shared output tree; all assembly clips present; a 1344×768 H.264 master with synchronized AAC audio within two seconds of 1266. `work/audit_equal_shares_completion.py` is the gate. Do not claim completion before it passes every requirement.

---

## 8. Open items, in priority order

1. **Resolve the two-tree divergence.** Decide that this handoff folder is canonical, correct `archive/superseded_docs/TECHNICAL_OPERATIONS.md`, and either restart the sync watcher pointing outward or formally retire the live root. Until this is done, every reader of the existing docs is one step away from starting a second backend.
2. **Clear the visual review backlog.** Roughly 34 rendered clips between `09C` and `18D` have never been reviewed. Review them before rendering much further.
3. **Restart or retire the sync watcher.** `archive/stale_state/SYNC_WATCHER.pid` still holds `33760`, a process that has been dead since 02:22. The stale PID file is itself a hazard.
4. **Continue the render** to 124, monitoring rather than restarting.
5. **Finalize and audit** once review reaches 124/124.

---

## 9. Shared output tree (verified 2026-08-10, added after the first draft)

`A:\Users\rhine\ComfyUI-Shared\output\story\` holds **79 clip directories** and **110 raw attempt files** in total.

**There is a discrepancy worth investigating.** Summing `attempt_total` across the manifest gives 128 attempts, but only 110 raw files exist. The gap is concentrated in exactly the clips that retried most:

| Clip | Attempts recorded | Files on disk |
|---|---|---|
| `01A` | 17 | 12 |
| `00C` | 10 | 4 |
| `00A` | 7 | 4 |
| `00D` | 7 | 4 |
| `00B` | 5 | 2 |
| `04C` | 4 | 4 |
| `00E`, `07C`, and all others | matches | matches |

The benign explanation is that some attempts errored, timed out, or were rejected before writing a file, so no artefact was ever produced — plausible for the opening clips, which were also the period when the workflow itself was being stabilised. The concerning explanation is that raws were deleted at some point, which would violate the standing "never destroy evidence" rule.

Note that `work/audit_equal_shares_completion.py` checks that every *selected* raw is preserved, not that every attempt is. So the completion gate can pass even if this gap is real deletion. Resolve it by reading the runner log for the affected clips before trusting the archive as complete.

**The final destination does not exist yet.** There is no `A:\Users\rhine\ComfyUI-Shared\output\equal_shares\` directory at all. This is expected — no master has been built — but the finalizer will need to create the path, so confirm it has permission to do so rather than discovering it at the end of a six-hour render.

## 10. What remains unverified

Still not checked, and requiring the Windows host:

- Whether the current ComfyUI process is alive and whether port 8188 is bound. (The supervisor log was advancing normally as of 17:39, which is strong indirect evidence.)
- Whether the finalizer watcher (previously PID `16900`) is still running.
- Whether any process is still writing to the live root.
- GPU memory headroom, which also gates whether local image generation is feasible between clips.

Model inventory is now **verified** — see `docs/LOCAL_IMAGE_GEN_FALLBACK.md`, which lists what is actually installed.
