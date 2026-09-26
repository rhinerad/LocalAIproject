# Equal Shares — standing rules for agents

This file is loaded automatically by Claude Code. Treat every rule here as binding. `PROJECT_CONTINUATION_BRIEF.md` holds the current state and the reasoning behind these rules.

## Current execution override — 2026-08-14 Omni-Reference test

Read `docs/OMNI_REFERENCE_VOICE_LOCK_PIPELINE.md` first. It supersedes every
older instruction in this tree that prohibits VOX identity masters, resumes
`continue_audio_generation_nonblocking.py`, or launches Narrator repair. The
user has reauthorized purpose-built VOX audio strictly as immutable 5-10 second
voice-identity masters for MiniMax H3 Omni-Reference.

The current job is limited to three missing VOX masters plus controlled 00A and
00I tests. Prompts must use the installed node's native `<Audio 1>` and
`<Picture 1>` tags, the same checksum-pinned master file for a character in
every clip, and no non-voice audio reference. Do not start the full audio queue
until both tests are audited. Do not start any 0.9 MP picture generation until
all 124 full soundtracks are accepted.

**Prompt-source lock:** for every new or revised MiniMax H3 prompt, consult the
official ComfyUI H3 tutorial first:
`https://docs.comfy.org/tutorials/video/minimax/minimax-h3`. For ref2va, name
connected references using exact one-based tags and explicitly state each
reference's job. Preserve the project-specific audio gate and no-Turbo rules.

## Which folder is authoritative

**This folder is the canonical working tree.**

`archive/superseded_docs/TECHNICAL_OPERATIONS.md` claims the parent directory (`...\referenced-chatgpt-conversation-this-is-an-2\outputs`) is authoritative and that this folder is a mirror. That was true until 2026-08-10 and is no longer. The sync watcher died at 02:22 and the supervisor was restarted against this folder. The parent's `manifest.json` is frozen at 44 clips; this folder's is current.

Never read state from the parent tree. The dead sync files are in `archive/stale_state/` — `SYNC_STATUS.json` and `SYNC_LOG.txt` both stopped at 02:22 on 2026-08-10, and `SYNC_WATCHER.pid` names PID `33760`, long dead. They are kept as evidence only. Nothing in `archive/` is current; do not act on anything in there.

## Product end goal — backend first, GUI later

Read `docs/AUTOMATED_STORY_GENERATOR_BACKEND_SPEC.md`. Equal Shares is the
reference project and end-to-end acceptance test for a reusable automated
ComfyUI story-generator backend. The backend must eventually accept a new story,
produce an editable narrative/shot/sound/reference plan, run the soundtrack-first
and picture pipelines, validate and retry, resume safely, organize provenance,
assemble the film, and pass a completion audit without project-specific manifest
surgery.

Do not start GUI work yet. The GUI is a later thin client over the proven
backend. New shared logic should move toward project-root/config parameters and
must not hard-code 124 clips, Equal Shares character names, or this film's
duration. Preserve current project adapters while generic services are extracted.

## One backend, ever

Exactly one process may bind ComfyUI port 8188 and hold the GPU. The active
stage supervisor owns that lifecycle: it starts a clean backend per clip,
renders one attempt, stops the backend, clears GPU state, and repeats.

Before launching any render process, verify all three: running python/ComfyUI processes, whether port 8188 is listening, and the tail of `outputs/equal_shares/runtime/render_supervisor.log` against the current clock. If that log is advancing, the render is alive — monitor it, never duplicate it.

Do not start a bare backend for a side experiment. Do not kill the supervisor without saying so first.

## Thermal safety

The offline Ollama agent is CPU-only and capped at four of the host's sixteen
logical processors. Do not remove that cap or run a second local model beside
it. Windows does not expose a usable CPU package-temperature sensor on this
machine, so the thread cap and the ban on overlapping heavy CPU jobs are the
CPU safeguards.

All current render paths use `work/thermal_guard.py`. A new GPU job may start at
70 C or below; if hotter it waits for 60 C. After every render the backend is
stopped and the next job waits for 58 C. During sampling, 82 C is an emergency
ceiling: the attempt is interrupted, recorded as an error by the normal runner,
and the system cools before retrying. If NVIDIA temperature telemetry fails
three consecutive times, do not start another render blindly.

## Model and settings — not negotiable

Full-quality MiniMax H3 only. Updated 2026-08-13; the pre-ref2va version of this
file is preserved as `archive/config_backups/CLAUDE.BACKUP_before_ref2va_2026-08-13.md`.

**Fixed for every path, no exceptions:**

- Text encoder `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- Video VAE `minimax_h3_video_vae_fp16.safetensors`, audio VAE `minimax_h3_audio_vae_fp32.safetensors`
- `res_multistep` / `simple`, denoise 1.0, SageAttention on
- 16:9, multiple of 32, 24 fps, 8-bit
- 20 steps for both single-anchor and dual-anchor
- Frame count rounds up to the next value congruent to 5 modulo 17

**Soundtrack length and picture length are different numbers.** H3 fills whatever
window it is given with speech, so a clip scripted at 15 s holding a 9 s line
gets ~6 s of invented gibberish. Stage-1 soundtrack renders use the shortened
lengths in `outputs/equal_shares/audio_pass_durations.json`; the accepted WAV is
then padded with digital silence to the scripted duration by
`work/pad_accepted_soundtracks.py`. **Picture always renders the full scripted
duration from `story_config.json`** — the film's pacing is unchanged and the
runtime is still 1266 s. Never write a shortened length into `story_config.json`.
See `docs/H3_PROMPT_RULES.md` section 9.

**Two-stage render path. Do not bypass the audio gate.**

| | checkpoint | node | MP | used for |
|---|---|---|---|---|
| Stage 1 — complete soundtrack | `minimax_h3_ref2va_pruned_nvfp4.safetensors` | `MiniMaxH3ReferenceToVideo` | **0.2** | all 124 clips; picture disposable, native H3 audio retained |
| Stage 2 — picture around approved audio | `minimax_h3_ref2va_pruned_nvfp4.safetensors` | `MiniMaxH3ReferenceToVideo` | **0.9 first** | approved Stage-1 full WAV is the principal audio reference |

The Stage-2 visual fallback ladder is fixed by the user:
**0.9 → 0.8 → 0.7 → 0.6 → 0.5 → 0.4 MP**. Validate after each attempt and
preserve all attempts. Never go below 0.4 MP. If 0.4 still fails, mark the clip
`human_review_needed`; do not keep rendering it automatically.

`ResolutionSelector` drives resolution by **megapixels**. When that node is
present the `width`/`height` values in `story_config.json` are dead tokens.

**Prohibited:** `minimax_h3_turbo_4step_ema_ckpt850.safetensors`, all Turbo nodes, all Turbo LoRAs. `generation_audit.json` may show an older 13/15-step baseline; `story_config.json` at 20/20 overrides it.

**Voice bootstrap lock, updated 2026-08-14:** purpose-built VOX clips,
invented voice-reference dialogue, filler speech, and non-story voice samples
are prohibited. A missing character voice is established only by rendering that
character's first qualifying **actual story soundtrack** at 0.2 MP with its
original scripted dialogue. Six useful seconds is the automatic reliability
target. If the story gives the character only 2–6 seconds, preserve the first
minimally usable story appearance but require human voice review before it can
become canonical. Never concatenate appearances or substitute invented words.

**Ear review is nonblocking for Stage-1 generation, updated 2026-08-14:** when
an actual-story bootstrap candidate is mechanically valid but transcription is
unknown or continuity review is pending, it may be extracted only as a clearly
marked provisional, generation-only voice reference. This does not accept the
soundtrack, does not satisfy the 124/124 audio gate, and does not permit Stage 2.
Continue generating the remaining Stage-1 candidates with
`work/continue_audio_generation_nonblocking.py`; preserve the pending review so
failed dialogue can be rerendered later without stalling unrelated generation.

**Narrator mix repair, updated 2026-08-14:** human listening confirmed that
Narrator identity is consistent, but many takes contain a quieter second vocal
layer. Keep the Narrator voice reference, but treat every `ref_audio` as identity
conditioning only and completely inaudible. The Narrator must be one dry,
centered performance with no replay, leakage, quieter duplicate, backing voice,
whisper, chorus, alternate take, delay, echo, or speech-shaped reverb. Versioned
retry prompts are in `prompts_audio_pass_narrator_repair_v2/`.
`work/retry_narrator_audio_after_stage1.py` must wait for both current owner files
to be explicitly released before retrying 00A through 00O. Never interrupt the
live first pass or start this repair beside it.

## Which handoff prompt is current

`CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` and `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`
are the current plan. The 2026-08-13 user clarification removed the old
single-pass branch: perfect soundtrack first, picture second.

`CLAUDE_CODE_PROMPT.md` predates them and still names fl2va at 736×416 with
`render_until_complete.py` as the resume command. Use it only for the
one-backend procedure and the reporting rules. Where the two disagree on model,
resolution, or what to render next, the audio-first documents win.

## State files

`outputs/equal_shares/manifest.json` and `visual_audit.json` are written by the runner and by review tooling. Do not hand-edit either while a render is active — the runner merges only the current clip's record so that concurrent review decisions are not overwritten, and a manual write defeats that protection.

`story_config.json` is authoritative for prompts, timing, frame paths, and constraints. Change it only for a specific clip, and re-run the `--check` pass afterward.

## Validation is not acceptance

The supervisor logs "Progress N/124 valid clips." That counts mechanically valid renders. It is **not** an acceptance count and must never be reported as one. Acceptance lives in `visual_audit.json` and requires a human-grade visual pass over the full duration of a clip.

**Contact sheets rank; they never pass.** A machine pass over overview, ending and every-second sheets caught every large-area fault — invented crowds, duplicate bodies, camera jumps, burned-in text — and missed **every** face-level fault, because a face at reduced scale is unreadable. Use the sheets to decide what to look at first, then judge faces on native-resolution frames. "No fault visible at reduced scale" means not reviewed, not passed.

As of 2026-08-13: 124 rendered, **43 accepted**, 22 confirmed rejects, 51 never reviewed.

Reject for: warped, duplicated, merged, disappearing, or anatomically wrong bodies; broken faces, hands, fingers, limbs, or object interactions; identity, wardrobe, location, architecture, or screen-direction drift; unintended people, wrong blocking, role swaps, actions contradicting the script; severe flicker, temporal morphing, visible gibberish text.

Audio acceptance and visual acceptance are separate. A visually correct Stage-2
take is not rejected merely because its newly generated audio differs: the exact
approved Stage-1 WAV is muxed onto the selected picture. However, gibberish,
wrong words, voice drift, or inconsistent music in Stage 1 is an audio rejection
and must be regenerated before Stage 2 begins.

Upscaling does not repair anatomy or identity drift. Broken footage is regenerated, shortened, or cut — not enhanced.

## Never destroy evidence

Every raw attempt stays under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`. Reject with `work/reject_clip_visual.py`, which records the rejection without deleting anything. Save new reference images as new versions; never overwrite an approved reference.

## Salvage before regeneration

Vary prompt and seed at 20 steps, then simplify motion, then shorten, then clean cut or approved-frame hold, then an insert or subtle motion built from existing approved frames. A new boundary image is the last resort — see `docs/GEMINI_REFERENCE_IMAGE_GUIDE.md` and `docs/LOCAL_IMAGE_GEN_FALLBACK.md`.

## Continuity locks

Opening: the receptionist is the only woman and never leaves the staff-only window. Exactly two male visitors perform the chair interaction, both entering through the separate doorway and remaining on the public side. One public chair, screen-left. No glass gate, fence, invented divider, extra chair, or third man. The Narrator appears only where the script places him and never resembles Kent.

Identity: `references/alex_vale_master_v1.png` is authoritative for Kent Brentwood. `references/ensemble_cast_master_v1.png` shows, left to right, Kent Brentwood, Avery Renfield, Doris Lovelay, Ryann Sally, Faith White. Those faces and clothes override any prose description.

`04C`: Kent has already declined before the clip begins. No bill, donation, transaction, or reaching toward the plate. Attempt 4 is accepted; attempt 3 must never be reselected.

## Completion

Not complete until the Stage-1 audio gate is 124/124 accepted, every Stage-2
clip has passed visual review, no clip remains `human_review_needed`, all raws
and provenance are preserved, all assembly clips and exact approved WAV inputs
exist, and a 1344×768 H.264 master with synchronized AAC audio sits within two
seconds of 1266 s. `work/audit_equal_shares_completion.py` is the final gate and
must be extended to enforce the audio-first state. Do not claim completion
before it passes.

## Reporting

Concise plain language at meaningful changes and roughly once a minute during long work: current clip or stage, status, pass or fail with reason, next step, and updated counts. No raw log dumps. Do not stop working merely to report.

## Persistence and permission handling

This is a terminal-condition assignment. Continue autonomously until `work/audit_equal_shares_completion.py` passes and every final deliverable has been verified. Planning, reporting progress, completing a substep, rejecting a clip, a crashed backend, a stale process, a transient file lock, or another recoverable failure is not a stopping point. Diagnose it, preserve evidence, recover safely, and continue.

Do not ask whether to continue when the next safe action is already implied. During long renders, audits, and assembly jobs, monitor at sensible intervals and resume action when their state changes. Use the permissions already granted in `.claude/settings.local.json` automatically for normal project reads, edits, commands, rendering, validation, recovery, and publishing. Do not turn a routine permission into a user question.

Stop only when the completion audit passes, or when progress genuinely requires a user-only credential, approval, missing source asset, material creative decision, or external-state change after every safe in-scope alternative has been exhausted. If blocked, give the exact evidence and request only the smallest action needed. Destructive deletion, credential disclosure, purchases, and unrelated system changes are never implicitly approved.

If a deletion or overwrite permission would normally appear, do not wait for approval and do not stop the task. Treat deletion as unnecessary unless the user explicitly named the exact disposable target. Preserve the existing item, write a versioned sibling, copy rather than move, or place an obsolete generated intermediate in a clearly labeled quarantine/archive folder when cleanup is truly useful. A denied destructive command is a signal to choose one of these non-destructive routes immediately and continue. Never delete raw attempts, approved references, manifests, audit evidence, source audio, assembly inputs, or final deliverables.
