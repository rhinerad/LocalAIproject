# Equal Shares — local-agent continuation prompt

> **SUPERSEDED 2026-08-16 — historical, do not execute.**
>
> This file instructs rendering purpose-built VOX clips with invented filler
> dialogue. **That is prohibited.** A missing character voice comes only from
> that character's first qualifying actual story soundtrack.
>
> Current instructions: `docs/AUDIO_PASS_RUNBOOK.md` (procedure),
> `docs/H3_PROMPT_RULES.md` (prompt grammar), `CHATGPT_START_AUDIO_PASS.md`
> (paste-able start prompt). `CLAUDE.md` is binding.


## Authoritative current override — 2026-08-14

Read and follow `docs/OMNI_REFERENCE_VOICE_LOCK_PIPELINE.md`. It supersedes the
older nonblocking MiniMax queue, the VOX prohibition, and Narrator-repair
instructions later in this historical prompt. The next executable is
`work/continue_omni_voice_lock_pipeline.py`. It creates the three remaining
immutable master voices and renders controlled 00A/00I voice-lock tests. It
must not start the full audio pass or any picture pass.

Resume the Equal Shares project from the verified pause after the old 00B test.
The user's latest workflow clarification is authoritative: **finish and approve
the entire native MiniMax H3 soundtrack at 0.2 MP before generating any
high-resolution picture.** Do not resume `work/render_single_pass.py`.

## Current nonblocking instruction — 2026-08-14

Ear review must not stop Stage-1 generations. A mechanically valid, actual-story
audio candidate that is awaiting ear review may be used as a clearly labeled
**provisional, generation-only** character reference. This does not accept that
candidate, satisfy its review, promote it to the canonical soundtrack, or open
Stage 2. VOX, filler, invented dialogue, and mechanically invalid candidates
remain ineligible. Continue the resumable local queue with
`work/continue_audio_generation_nonblocking.py`; if its owner is live, monitor
it instead of starting another copy.

## Canonical project

Work only in:

`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`

The parent tree and everything under `archive/` are not current state.

## Read completely before acting

1. `CLAUDE.md`
2. `docs/AUTOMATED_STORY_GENERATOR_BACKEND_SPEC.md`
3. the newest entry in `docs/WORKFLOW_NOTES.md`
4. `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`
5. `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md`
6. `PROJECT_CONTINUATION_BRIEF.md`
7. `.claude/settings.local.json`

Use `CLAUDE_CODE_PROMPT.md` only for the one-backend procedure, never-delete
rules, reporting format, and persistence requirement. Its model, resolution,
resume command, and old open items are superseded.

The broader deliverable is a reusable automated ComfyUI story-generator backend.
Equal Shares is its regression and acceptance project. Finish the headless
backend and prove it end to end before building a GUI. Keep shared code
configurable; the future GUI must invoke this backend rather than duplicate its
state, render, validation, retry, or assembly logic.

## Verify the handoff before using the GPU

Read:

- `outputs/equal_shares/runtime/pause_after_00B_receipt.json`
- `outputs/equal_shares/runtime/pause_after_00B_recovery_receipt.json`
- `outputs/equal_shares/runtime/render_queue_owner.json`
- `outputs/equal_shares/single_pass_manifest.json`

The recovery receipt is authoritative. Confirm its recorded processes are dead,
port 8188 is free, there is no active sampler/backend, and GPU render use is
gone. Preserve the old test raws:

- `A:\Users\rhine\ComfyUI-Shared\output\story\SP_00A\00A_00001_.mp4`
- the 00B raw named by `single_pass_manifest.json`

The user rejected 00A because its narration contains extensive gibberish. It is
mechanically valid evidence, not accepted audio. 00B is also test evidence until
its full soundtrack is audited. Neither test raw opens the new audio gate.

## Authoritative execution order

Follow `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` exactly:

1. Establish canonical character voices from each character's first qualifying
   delivered **actual story soundtrack** appearance. Never make a purpose-built
   VOX job and never invent reference dialogue. Use
   `story_voice_bootstrap_plan.json` and `render_audio_pass.py
   --bootstrap-missing-voices` for unresolved characters.
2. Establish recurring music, ambience, tone, and sound-effect references. Keep
   the non-diegetic score as one continuous master, never a new song per clip.
3. Render all 124 clip soundtracks with non-Turbo MiniMax H3 ref2va at 0.2 MP.
   Wire the exact opening image and the closing image whenever one exists.
4. Automatically check exact dialogue, order, timing, added/missing speech,
   likely gibberish, clipping/silence, voice continuity, and recurring sound
   continuity. Improve the filter when review finds an error. Pending ear review
   remains recorded but does not pause generation of later Stage-1 candidates.
5. Preserve every attempt. Promote only accepted full-clip native H3 WAVs into
   `outputs/equal_shares/audio/h3_dialogue/` with source provenance.
6. Do not begin picture generation until 124/124 story soundtracks are accepted.
7. Generate picture around each exact approved WAV with ref2va, starting at
   0.9 MP. Validate the whole clip at native resolution after every attempt.
8. On visual failure, preserve the attempt and descend
   `0.9 → 0.8 → 0.7 → 0.6 → 0.5 → 0.4 MP`.
9. If 0.4 MP still fails, mark `human_review_needed` with evidence and stop
   automatic rendering for that clip.
10. Mux the exact approved Phase-1 WAV onto the selected picture. The picture
    pass is never allowed to rewrite accepted dialogue, voices, music, effects,
    or timing.

## MiniMax and preservation locks

- Full-quality MiniMax H3 only; never Turbo, a Turbo node, or Turbo LoRA.
- 20 steps, `res_multistep` / `simple`, denoise 1.0, SageAttention, 24 fps,
  8-bit, 16:9, multiple 32.
- Character `h3_voice_ref.wav` files are timbre inputs, not finished lines.
- Do not use `outputs/equal_shares/audio/dialogue/`; it contains older Kokoro
  and RVC assets.
- Do not use `outputs/equal_shares/audio/_hybrid_parts/`; it is an older mixed
  keep/replace cache.
- Never download anything.
- Exactly one GPU owner and one ComfyUI backend on port 8188.
- Start and stop a clean backend per render job.
- Never delete, move, rename, or overwrite a raw, approved reference, manifest,
  audit record, source audio, assembly input, or deliverable.
- Core `SaveVideo` may report MP4 metadata under a field called `images`; keep
  the parser fix that filters by actual video extension.
- New staged raws may live under
  `outputs/equal_shares/runtime/codex_comfy_runtime/output/`; they are originals
  and must be preserved. Copy to the shared output only as a versioned sibling.

## Acceptance and reporting

Rendered or mechanically valid is not accepted. An empty speech-recognizer
result is unknown, not pass. Contact sheets never pass faces or anatomy. Review
the whole Stage-2 clip at native resolution against the prompt, start/end
references, identity locks, blocking, architecture, and continuity.

Continuity locks in `CLAUDE.md` remain binding, especially the opening-room
receptionist/visitor geometry, Kent's identity references, and accepted 04C
attempt 4.

Report about once a minute during long work: stage, clip, attempt, resolution,
pass/fail reason, next action, accepted-audio count, visually accepted count,
and human-review-needed count. No log dumps. Work through recoverable failures.

Do not claim completion until the completion audit enforces and passes the
124/124 audio gate, 124/124 visual gate, zero human-review-needed clips,
preserved provenance, complete assembly inputs, and final master checks.

Begin with the read-only pause verification. Then implement/check the all-clip
0.2 MP audio-pass runner and validator before claiming the GPU queue.
