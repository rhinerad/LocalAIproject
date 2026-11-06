# Equal Shares — standing rules for agents

This file is loaded automatically by Claude Code. Treat every rule here as binding. `PROJECT_CONTINUATION_BRIEF.md` holds the current state and the reasoning behind these rules.

## Which folder is authoritative

**This folder is the canonical working tree.**

`TECHNICAL_OPERATIONS.md` claims the parent directory (`...\referenced-chatgpt-conversation-this-is-an-2\outputs`) is authoritative and that this folder is a mirror. That was true until 2026-08-10 and is no longer. The sync watcher died at 02:22 and the supervisor was restarted against this folder. The parent's `manifest.json` is frozen at 44 clips; this folder's holds 77 and is advancing.

Never read state from the parent tree. Never trust `SYNC_STATUS.json` or `SYNC_LOG.txt` — both stopped at 02:22 on 2026-08-10. Never trust `SYNC_WATCHER.pid`; PID `33760` is long dead.

## One backend, ever

Exactly one process may bind ComfyUI port 8188 and hold the GPU. `work/render_until_complete.py` owns that lifecycle: it starts a clean backend per clip, renders one clip, stops the backend, clears GPU state, and repeats.

Before launching any render process, verify all three: running python/ComfyUI processes, whether port 8188 is listening, and the tail of `outputs/equal_shares/runtime/render_supervisor.log` against the current clock. If that log is advancing, the render is alive — monitor it, never duplicate it.

Do not start a bare backend for a side experiment. Do not kill the supervisor without saying so first.

## Model and settings — not negotiable

Full-quality MiniMax H3 only.

- Model `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Text encoder `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- Video VAE `minimax_h3_video_vae_fp16.safetensors`, audio VAE `minimax_h3_audio_vae_fp32.safetensors`
- `res_multistep` / `simple`, denoise 1.0, SageAttention on
- 736×416, 16:9, 0.3 MP, multiple of 32, 24 fps, 8-bit
- 20 steps for both single-anchor and dual-anchor
- Frame count rounds up to the next value congruent to 5 modulo 17

**Prohibited:** `minimax_h3_turbo_4step_ema_ckpt850.safetensors`, all Turbo nodes, all Turbo LoRAs. `generation_audit.json` may show an older 13/15-step baseline; `story_config.json` at 20/20 overrides it.

## State files

`outputs/equal_shares/manifest.json` and `visual_audit.json` are written by the runner and by review tooling. Do not hand-edit either while a render is active — the runner merges only the current clip's record so that concurrent review decisions are not overwritten, and a manual write defeats that protection.

`story_config.json` is authoritative for prompts, timing, frame paths, and constraints. Change it only for a specific clip, and re-run the `--check` pass afterward.

## Validation is not acceptance

The supervisor logs "Progress N/124 valid clips." That counts mechanically valid renders. It is **not** an acceptance count and must never be reported as one. Acceptance lives in `visual_audit.json` and requires a human-grade visual pass over the full duration of a clip using the overview, ending, and every-second contact sheets.

Reject for: warped, duplicated, merged, disappearing, or anatomically wrong bodies; broken faces, hands, fingers, limbs, or object interactions; identity, wardrobe, location, architecture, or screen-direction drift; unintended people, wrong blocking, role swaps, actions contradicting the script; severe flicker, temporal morphing, visible gibberish text.

Never reject a visually correct take for gibberish speech or wrong music — all H3 audio is discarded and replaced in post.

Upscaling does not repair anatomy or identity drift. Broken footage is regenerated, shortened, or cut — not enhanced.

## Never destroy evidence

Every raw attempt stays under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`. Reject with `work/reject_clip_visual.py`, which records the rejection without deleting anything. Save new reference images as new versions; never overwrite an approved reference.

## Salvage before regeneration

Vary prompt and seed at 20 steps, then simplify motion, then shorten, then clean cut or approved-frame hold, then an insert or subtle motion built from existing approved frames. A new boundary image is the last resort — see `GEMINI_REFERENCE_IMAGE_GUIDE.md` and `docs/LOCAL_IMAGE_GEN_FALLBACK.md`.

## Continuity locks

Opening: the receptionist is the only woman and never leaves the staff-only window. Exactly two male visitors perform the chair interaction, both entering through the separate doorway and remaining on the public side. One public chair, screen-left. No glass gate, fence, invented divider, extra chair, or third man. The Narrator appears only where the script places him and never resembles Kent.

Identity: `references/alex_vale_master_v1.png` is authoritative for Kent Brentwood. `references/ensemble_cast_master_v1.png` shows, left to right, Kent Brentwood, Avery Renfield, Doris Lovelay, Ryann Sally, Faith White. Those faces and clothes override any prose description.

`04C`: Kent has already declined before the clip begins. No bill, donation, transaction, or reaching toward the plate. Attempt 4 is accepted; attempt 3 must never be reselected.

## Completion

Not complete until 124/124 clips are valid, every clip has passed visual review, all raws are preserved in the shared output tree, all assembly clips exist, and a 1344×768 H.264 master with synchronized AAC audio sits within two seconds of 1266 s. `work/audit_equal_shares_completion.py` is the gate. Do not claim completion before it passes.

## Reporting

Concise plain language at meaningful changes and roughly once a minute during long work: current clip or stage, status, pass or fail with reason, next step, and updated counts. No raw log dumps. Do not stop working merely to report.

## Persistence and permission handling

This is a terminal-condition assignment. Continue autonomously until `work/audit_equal_shares_completion.py` passes and every final deliverable has been verified. Planning, reporting progress, completing a substep, rejecting a clip, a crashed backend, a stale process, a transient file lock, or another recoverable failure is not a stopping point. Diagnose it, preserve evidence, recover safely, and continue.

Do not ask whether to continue when the next safe action is already implied. During long renders, audits, and assembly jobs, monitor at sensible intervals and resume action when their state changes. Use the permissions already granted in `.claude/settings.local.json` automatically for normal project reads, edits, commands, rendering, validation, recovery, and publishing. Do not turn a routine permission into a user question.

Stop only when the completion audit passes, or when progress genuinely requires a user-only credential, approval, missing source asset, material creative decision, or external-state change after every safe in-scope alternative has been exhausted. If blocked, give the exact evidence and request only the smallest action needed. Destructive deletion, credential disclosure, purchases, and unrelated system changes are never implicitly approved.

If a deletion or overwrite permission would normally appear, do not wait for approval and do not stop the task. Treat deletion as unnecessary unless the user explicitly named the exact disposable target. Preserve the existing item, write a versioned sibling, copy rather than move, or place an obsolete generated intermediate in a clearly labeled quarantine/archive folder when cleanup is truly useful. A denied destructive command is a signal to choose one of these non-destructive routes immediately and continue. Never delete raw attempts, approved references, manifests, audit evidence, source audio, assembly inputs, or final deliverables.
