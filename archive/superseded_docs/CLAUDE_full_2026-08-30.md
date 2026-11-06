# Equal Shares — standing rules for agents

## SCOPE NOTICE — 2026-08-30, read this before anything below

**Equal Shares is now one preserved, optional project profile of the local
agent, not its operating purpose.** As of 2026-08-30 the operator's stated
priority is a reliable general-purpose local assistant — tool use, file work,
multimodal analysis, model routing, safe GPU control, persistent memory,
phone access, and background-worker infrastructure. Equal Shares' render
pipeline is **explicitly paused**: do not resume its audio pass, do not start
a render, and do not alter its evidence/manifests. This file's "Current job"
section below describes a 2026-08-16 job that is **not** the active job.

For current priorities and architecture, read these first, in this order:
`local_agent/README.md`, `TODO.md` (the execution queue), `docs/design_notes/
architecture_audit_2026-08-27.md`, and recent `CHANGELOG/2026-08-*.md`
entries — newer decisions override older project-era assumptions in this
file. Treat this file (`CLAUDE.md`) as binding **only** for the safety,
verification, evidence-preservation, and thermal/GPU rules below; do not
treat its Equal Shares soundtrack job description or its "keep going until
the audio gate passes" persistence language as current instructions to
resume that work. Everything below this notice was written before the
reprioritization and is preserved for the safety rules it contains and for
anyone doing deliberate, explicitly-requested Equal Shares work later.

## READ FIRST — two folders that override everything else

**`docs/GOLDEN_REFERENCE/`** — the workflow graphs extracted from renders that
actually produced good audio. Ground truth, not documentation. Diff against it
before claiming any render-path change works.

Read **`docs/GOLDEN_REFERENCE/PROVEN_FACTS.md`** first. It is this project's
memory of what is actually established, each line with the measurement behind it.
**Anything not in that file is not proven, however confidently it is asserted
elsewhere in this tree — including by this file.** Three doctrines here were
repeated across a dozen documents and turned out to be wrong.

Two facts from it that change what you would otherwise do:

- **`ComfyUI-Shared\output\video\good audio\` is the Narrator and nobody else.**
  All 14 speaking takes are the opening narration, `00A`–`00O`, with `00B` and
  `00H` missing. It supplies three voices at most and **no audio at all** for
  Kent, Avery, Doris, Ryann, Faith, or the other eleven. It cannot replace the
  audition pass.
- **Silence does not cause gibberish.** `4_`.mp4` is 56% silence and is clean.
  Fitting the render to the line is a precaution, not a cause.

**`CHANGELOG/`** — every change to this project, with evidence, written in the
same session the change is made. **You must add an entry for anything you
change.** Not a summary afterwards.

**Changelog filenames.** Entries are named `YYYY-MM-DDx_description.md` with a
sequential letter `x` (`a`, `b`, `c`, …). Before creating one, list `CHANGELOG/`
for today's date and use the next unused letter rather than guessing — multiple
agents may be working in parallel without visibility into each other's
in-progress work, so two agents can pick the same letter. Run
`python scripts/next_changelog_id.py` (prints e.g. `2026-09-02w`) instead of
inventing the suffix.

At session start, run `python scripts/write_handoff_status.py` and read
`HANDOFF_STATUS.md` for current CHANGELOG/TODO/orphan/persistence state; do
not treat `GROK_STATUS.md` or dated `docs/LOCAL_AGENT_CURRENT_HANDOFF_*.md`
as the live snapshot. Caveats live in that file's header: open TODOs are
checkbox first-lines only, and orphans/persistence are changelog-seeded,
not live-probed.

### Verification means one thing here

A change is **not verified** because the config and the docs agree, because a
drift check is clean, or because regenerated files look right. **All three of
those passed on 2026-08-16 while the renderer was sending a corrupted prompt to
all 124 clips.**

Verified means: the workflow embedded in a real render was extracted
(`ffprobe -show_entries format_tags=prompt` on the MP4, or the PNG metadata) and
diffed against the golden reference. If you have not done that, say the change
is unverified. Never report document consistency as verification.


This file is loaded automatically by Claude Code. Treat every rule here as binding. `PROJECT_CONTINUATION_BRIEF.md` holds the current state and the reasoning behind these rules.

## Current job — 2026-08-16, the soundtrack pass

**Superseded 2026-08-30 — see the SCOPE NOTICE at the top of this file. This
section is history/reference, not an active assignment. The audio pass is
paused; do not resume it, do not render, do not touch its evidence.**

**Read `docs/AUDIO_PASS_RUNBOOK.md` first, then `docs/H3_PROMPT_RULES.md`.**
Those two supersede every older audio instruction in this tree, including the
2026-08-14 Omni-Reference override that used to sit here.

The job is **all 124 Stage-1 soundtracks**, not a limited test. The controlled
00A/00I tests are finished and the pipeline is confirmed working: `00B` rendered
on 2026-08-15 with correct words, one clean voice layer, and no gibberish.

Run it with `work/render_audio_pass.py`, driven by
`outputs/equal_shares/audio_pass_config_omni_v1.json`. Before anything touches
the GPU, run `python work/sync_omni_audio_config.py --check` — that config is
assembled from four upstream files and drifts silently.

**Four rules make the audio come out right. All four are already applied to all
124 prompts; do not undo them.**

1. **`retention_analysis` declaring `<Audio N>: reference`.** This is what fixed
   the doubled voice. Nothing had ever told H3 the master was a reference rather
   than a source to copy.
2. **One scripted line, one `<d>[English] …</d>` block.** Splitting a line puts
   gibberish at the seam.
3. **Delivery before the tag, mouth closes immediately after it.** Prose about a
   character speaking placed after `</d>` reads as speech still in progress.
4. **Render short, pad silence at assembly.** See the duration rule below.

**Fifth rule, added 2026-08-18 — the duration ladder.** A take with gibberish or
mispronounced words is retried by changing the **duration**, never the seed:
**base, +1, −1, +2, −2, +3, −3 seconds**, skipping any rung longer than the
scripted duration, seed held fixed across the whole ladder. Implemented once in
`work/duration_ladder.py`; do not reimplement it anywhere else. Words ÷ duration
is the speech rate the model has to hit, and only the duration can move it — a
seed re-roll asks for the same impossible rate under different noise. See
`docs/H3_PROMPT_RULES.md` §10. A doubled voice is **not** a length fault and must
not be sent up the ladder.

Prompts are generated by `work/build_native_r2v_prompts.py` into
`outputs/equal_shares/prompts_native_r2v/`. **Do not hand-edit a prompt** — it
will be overwritten. Fix the generator or `story_config.json` instead.

**Sixth rule, added 2026-08-18 — one-off speakers need no voice.** A character
who speaks in **only one clip** needs no voice master and gets **no `<Audio N>`**,
even if a provisional master exists on disk. A master exists solely to make a
character sound the same in clip 7 as in clip 3; with one appearance there is
nothing to be consistent with. Routing follows from it:

| the clip contains | node | references |
|---|---|---|
| no recurring speaker | `MiniMaxH3ImageToVideo` (fl2va) | none at all |
| any recurring speaker | `MiniMaxH3ReferenceToVideo` (ref2va) | the **recurring** speakers only |

Measured on this film: **8 of 18 speakers are one-offs**, four clips leave the
reference path entirely (`01B`, `20B`, `22B`, `30B`), and three are mixed
(`00D2`, `27E`, `28C`). The audition list drops 17 → 9 and Job 2 drops 8 → 2.

`work/classify_voice_requirements.py` owns this classification and writes
`outputs/equal_shares/voice_requirements.json`. **Never recount speakers
anywhere else.** One conflict is deliberately unresolved — `Doris recording` is a
recording *of* recurring Doris but counts as a separate one-off name; see
`runtime/agent_questions.md`.

**VOX and filler dialogue remain prohibited.** The 2026-08-14 reauthorisation of
purpose-built VOX masters is withdrawn. A missing character voice comes only
from that character's first qualifying actual story soundtrack; the per-character
packs are on the Desktop at `EQUAL_SHARES_FIRST_APPEARANCE\`. Eight characters
still hold provisional masters — `Aid worker`, `Council member`, `Crew lead`,
`Male Visitor One`, `Male Visitor Two`, `Terminal voice`, `Unhoused man`,
`Wealthy commuter`. Four of them have only 2–3 s of scripted dialogue and cannot
reach the 6 s target. **Take the best contiguous passage anyway and mark it
`short_master: true` — do not stop to ask, and never invent filler lines.**

Do not start any picture generation until the audio gate reads 124/124 accepted.

**Prompt-source lock:** for every new or revised MiniMax H3 prompt, consult
`docs/H3_PROMPT_RULES.md`, which is built from the official ComfyUI H3 tutorial
and MiniMax's own R2V writing guide. Name connected references using exact
one-based tags and state each reference's job explicitly.

## Do not interrupt the operator

**Superseded 2026-08-30 — see the SCOPE NOTICE at the top of this file.
"Rendering all 124 soundtracks is your job" below described the paused audio
pass, not a current instruction. Do not render, do not resume the audio pass.
The general "work through an assignment without stopping for routine
decisions" habit this section describes still applies to other, current work
— just not to restarting Equal Shares.**

Work the whole assignment through without asking for approval, confirmation, or
a preference. The standing answers are in `START_LOCAL_AGENT.md`. If something is
genuinely undecidable, append it to
`outputs/equal_shares/runtime/agent_questions.md`, take the safest documented
option, and keep working. Stop only for a user-only credential, a missing source
asset, or an external condition with no safe workaround.

**Rendering all 124 soundtracks is your job. Accepting them is not** — you cannot
hear. Validate mechanically with `work/validate_audio_take.py`, mark takes
`pending_ear_review`, and continue. The 124/124 acceptance gate is the operator's.

## `local_agent/` is a different program — do not confuse the two

"The local agent" in this tree means two unrelated things:

- **the render agent** — ChatGPT/Codex or Claude Code driving the 124-clip pass,
  started from `CHATGPT_START_AUDIO_PASS.md` or `START_VOICE_AUDITIONS.md`
- **`local_agent/`** — an offline Ollama chat app that answers questions about
  this project, started from `local_agent\START_LOCAL_AGENT_GUI.ps1`

Rules for `local_agent/`, binding:

- A desktop chat may start only the separate general `start_batch_render` action
  when the operator explicitly asks and supplies a real validated job folder.
  It is forbidden from `outputs/equal_shares/**`, refuses any active queue or
  ComfyUI port, and the existing runner retains the queue lock and thermal guard.
  A folderless desktop “render it” may prepare a fresh isolated job from that
  chat's latest complete prompt set and its earlier attached assets; it never
  treats an output folder as a prompt job or modifies the source assets.
  Phone identities remain default-deny for this action. One ComfyUI, ever.
- Its `tools.py` is a **fixed whitelist**, not a shell. Do not relax it for
  convenience — it is the security model, and more so once the phone can reach it.
- Its HTTP server binds **`127.0.0.1`**. The only sanctioned exceptions are the
  Tailscale interface (`UPGRADE/06`) and `adb reverse` over USB (`UPGRADE/06a`),
  which does not change the binding at all. Never `0.0.0.0`.
- `agent.answer()` stays **transport-agnostic**. It is the seam a Reticulum mesh
  plugs into later — see `local_agent/ROADMAP.md`.
- Work on it is planned in `local_agent/UPGRADE/00_INDEX.md`, nine numbered
  prompts. `UPGRADE/07_batch_renderer.md` specifies a **second, general render
  pipeline** that reuses this project's proven settings and thermal guard but is
  **forbidden from reading or writing `outputs/equal_shares/**`.**

Changes to `local_agent/` still require a `CHANGELOG/` entry like anything else.

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

**Soundtrack length and picture length are different numbers.** The soundtrack is
fitted to the spoken line; the picture keeps the film's pacing.

*(Corrected 2026-08-17. This paragraph used to claim "H3 fills whatever window it
is given with speech, so a clip scripted at 15 s holding a 9 s line gets ~6 s of
invented gibberish." **That is not supported.** `4_`.mp4` in the good-audio set
is 56% silence and is clean. The `00B` failures carried a corrupt prepended
header as well as a long duration; the duration was blamed and the header went
unnoticed for a week. Fitting the render is still correct — cheaper, and one
fewer variable — but it is a precaution, not the cause.)*

Stage-1 soundtrack renders use the shortened
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

`docs/AUDIO_PASS_RUNBOOK.md` is the current procedure and
`docs/H3_PROMPT_RULES.md` the current prompt grammar. Start the local agent with
`CHATGPT_START_AUDIO_PASS.md`.

`docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md` still holds the correct soundtrack-first
staging and the Stage-2 plan; read it for the shape of the pipeline, but take
audio procedure from the runbook.

**Superseded and bannered, do not execute:** `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md`,
`CHATGPT_START_PROMPT.md`, `LOCAL_AGENT_CONTINUATION_PROMPT_2026-08-13.md`,
`CLAUDE_CODE_OMNI_WATCH_PROMPT.md`, `docs/OMNI_REFERENCE_VOICE_LOCK_PIPELINE.md`,
`RESUME_PROMPT_00J_AUDIT.md`. They instruct VOX filler dialogue, limited test
runs, or fl2va at 736×416.

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

**Superseded 2026-08-30 — see the SCOPE NOTICE at the top of this file. This
section describes Equal Shares as "a terminal-condition assignment" to
justify working autonomously toward the 124/124 audio gate; that gate is
paused and this is not a live assignment. Do not resume toward it. The
underlying safety rules two paragraphs down (never implicitly deleting,
never treating destructive commands as approved) remain binding for any
work, current or otherwise.**

This is a terminal-condition assignment. Continue autonomously until `work/audit_equal_shares_completion.py` passes and every final deliverable has been verified. Planning, reporting progress, completing a substep, rejecting a clip, a crashed backend, a stale process, a transient file lock, or another recoverable failure is not a stopping point. Diagnose it, preserve evidence, recover safely, and continue.

Do not ask whether to continue when the next safe action is already implied. During long renders, audits, and assembly jobs, monitor at sensible intervals and resume action when their state changes. Use the permissions already granted in `.claude/settings.local.json` automatically for normal project reads, edits, commands, rendering, validation, recovery, and publishing. Do not turn a routine permission into a user question.

Stop only when the completion audit passes, or when progress genuinely requires a user-only credential, approval, missing source asset, material creative decision, or external-state change after every safe in-scope alternative has been exhausted. If blocked, give the exact evidence and request only the smallest action needed. Destructive deletion, credential disclosure, purchases, and unrelated system changes are never implicitly approved.

If a deletion or overwrite permission would normally appear, do not wait for approval and do not stop the task. Treat deletion as unnecessary unless the user explicitly named the exact disposable target. Preserve the existing item, write a versioned sibling, copy rather than move, or place an obsolete generated intermediate in a clearly labeled quarantine/archive folder when cleanup is truly useful. A denied destructive command is a signal to choose one of these non-destructive routes immediately and continue. Never delete raw attempts, approved references, manifests, audit evidence, source audio, assembly inputs, or final deliverables.
