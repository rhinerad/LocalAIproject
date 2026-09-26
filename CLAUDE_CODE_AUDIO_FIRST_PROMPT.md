# Local agent — authoritative Equal Shares audio-first assignment

> **SUPERSEDED 2026-08-16 — historical, do not execute.**
>
> This file instructs rendering purpose-built VOX clips with invented filler
> dialogue. **That is prohibited.** A missing character voice comes only from
> that character's first qualifying actual story soundtrack.
>
> Current instructions: `docs/AUDIO_PASS_RUNBOOK.md` (procedure),
> `docs/H3_PROMPT_RULES.md` (prompt grammar), `CHATGPT_START_AUDIO_PASS.md`
> (paste-able start prompt). `CLAUDE.md` is binding.


Working directory:

`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`

Read completely, in order:

1. `CLAUDE.md`
2. `docs/AUTOMATED_STORY_GENERATOR_BACKEND_SPEC.md`
3. the newest entry in `docs/WORKFLOW_NOTES.md`
4. `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`
5. `PROJECT_CONTINUATION_BRIEF.md`
6. `.claude/settings.local.json`

The user's 2026-08-13 clarification is final: **finish and approve the complete
MiniMax H3 soundtrack before generating high-resolution picture.** Ignore every
older instruction that says Task 0 permits a single 0.9 MP pass, that Stage 1 is
optional, that only 78 dialogue clips belong in the audio pass, or that H3 audio
will be discarded.

Equal Shares is also the reference implementation for the reusable automated
story-generator backend. Complete the headless backend and its end-to-end film
test before any GUI work. Keep reusable logic configurable and project-agnostic;
the future GUI will call the backend rather than contain pipeline logic.

## Task 0 — verify the paused state

The earlier single-pass run was intentionally stopped after `00B`. Do not resume
it. Confirm the owner PID is not live, queue state is released, port 8188 is
free, GPU render use is gone, and no active sampler/backend exists. Read:

- `outputs/equal_shares/runtime/pause_after_00B_receipt.json`
- `outputs/equal_shares/runtime/pause_after_00B_recovery_receipt.json`
- `outputs/equal_shares/single_pass_manifest.json`

The recovery receipt is authoritative about the final pause. Preserve `00A` and
`00B` as test evidence. `00A` is mechanically valid but its narration was
rejected for gibberish. Neither test output opens the audio gate.

## Task 1 — lock character and recurring-sound references

Run/check `work/build_voice_reference_map.py` using its first-qualifying-
appearance rule. A qualifying character reference is one contiguous, stable
MiniMax H3 speaking passage from the earliest delivered story appearance with
enough usable speech. A noisy, mixed, silent, or unstable first line is not a
qualifying reference.

For characters with no already-delivered qualifying passage, render their first
qualifying **actual story soundtrack** at 0.2 MP using the original story prompt,
dialogue, opening image, and closing image when present. The plan is
`story_voice_bootstrap_plan.json`; execute it with `render_audio_pass.py
--bootstrap-missing-voices`. Purpose-built VOX clips, filler dialogue, and
non-story voice samples are prohibited. Six useful seconds is the automatic
target; a first real-story passage of 2–6 seconds requires human voice review.

Create/maintain `outputs/equal_shares/audio_continuity_map.json` for recurring
diegetic music, ambience, tones, hums, crowd beds, and sound effects. The first
approved clean occurrence is the reference for later clips in that continuity
group. The non-diegetic score remains one continuous master track and must not
restart with each generation.

## Task 2 — build and render the complete 0.2 MP soundtrack

Rebuild the prompt/config checks first. Then render **all 124 clips**, including
the 46 without dialogue, with full-quality non-Turbo MiniMax H3 ref2va at 0.2 MP.
The low-resolution image is disposable; native H3 audio is the deliverable.

Use:

- `minimax_h3_ref2va_pruned_nvfp4.safetensors`
- `MiniMaxH3ReferenceToVideo`
- Qwen 32B MiniMax text encoder
- MiniMax H3 video/audio VAEs
- 20 steps, `res_multistep` / `simple`, denoise 1.0
- 16:9, multiple 32, 24 fps, 8-bit
- first image as `ref_images.ref_image_0`
- closing image as `ref_images.ref_image_1` whenever `last_frame` exists
- ordered canonical character voice references
- a recurring sound reference when applicable and a reference slot remains

Spoken words appear once, inside their timed beat. Include all required
ambience, effects, and music events with timing. Output to preserved
`story/AUDIO_<clip>/` directories and track every attempt in
`outputs/equal_shares/audio_pass_manifest.json`. Never write these disposable
pictures into the story visual manifest.

## Task 3 — validate and perfect every soundtrack clip

After every attempt, extract the full native H3 audio and run the local audio
validator. It must check mechanical sound, expected words and order, insertions,
omissions, repetitions, extra muttering, timing windows, and likely gibberish.
Also check voice and recurring sound continuity whenever the installed tools can
measure them reliably.

An empty/broken transcription is unknown, never pass. Listen to borderline
results and update the filter when it produces a false pass or false reject.
Preserve measurements and revisions in attempt history.

Retry order:

1. tighten the dialogue/sound beat;
2. split long speech at clause boundaries;
3. explicitly lock every non-speaker silent;
4. strengthen the recurring-sound reference job;
5. change the seed.

Only after a take is accepted, extract its authoritative full soundtrack to:

`outputs/equal_shares/audio/h3_dialogue/<clip>_<attempt>_full.wav`

Do not use `audio/dialogue/` or `audio/_hybrid_parts/`; those are older
Kokoro/RVC or hybrid assets. Phase 1 ends only when 124/124 story clip
soundtracks are accepted with source provenance.

## Task 4 — generate the picture around perfect audio

Do not begin this task until the 124/124 audio gate passes.

For each clip, use full-quality MiniMax H3 ref2va with its opening image, closing
image when present, and its accepted full Phase-1 WAV as the principal audio
reference. Rewrite the visual prompt into MiniMax-friendly form with this exact
audio lock near the top:

> The referenced audio is the exact finished soundtrack for this shot. Preserve
> every word, speaker, pause, music cue, ambience, effect, and timestamp. Do not
> paraphrase, repeat, replace, remix, or add speech. Generate the visible
> performance and action around that soundtrack.

Start at 0.9 MP. After each attempt, run the mechanical filter and inspect the
whole clip at native resolution against its prompt and references. Reject face,
identity, anatomy, hand/limb, interaction, temporal, camera, architecture,
continuity, blocking, unintended-person, and visible-text faults.

On visual rejection, preserve the attempt and descend exactly one rung:

`0.9 → 0.8 → 0.7 → 0.6 → 0.5 → 0.4 MP`

Keep 20 steps. Change prompt/seed when the rejection explains a useful fix. If
0.4 MP fails, stop automatic rendering for that clip and mark
`human_review_needed` with all evidence. Never render below 0.4 MP.

## Task 5 — preserve audio exactly and assemble

The picture render's newly decoded soundtrack is diagnostic only. Compare it
against the reference, then mux the exact accepted Phase-1 WAV onto the selected
picture. Never let the high-resolution pass change an accepted word, voice,
music cue, effect, or timing.

Keep the continuous score continuous across cuts. Assemble only visually
accepted picture takes with their matching accepted WAVs. Preserve all raw
attempts and write versioned siblings instead of overwriting.

Extend/run `work/audit_equal_shares_completion.py` so completion requires:

- 124/124 accepted Phase-1 soundtracks with provenance;
- 124/124 visually accepted Phase-2 clips;
- zero `human_review_needed` clips;
- all exact soundtrack and picture assembly inputs present;
- all raw attempts preserved;
- the final 1344×768 H.264/AAC master within two seconds of 1266 seconds.

## Standing rules

- Never use Turbo, download anything, or run two ComfyUI backends.
- Claim the queue before every GPU stage and release it afterward.
- One clean backend per render job.
- Never delete, move, rename, or overwrite evidence.
- Never treat rendered/mechanically valid as accepted.
- Do not hand-edit a runner-owned manifest while rendering.
- During long work, report roughly once a minute with stage, clip, verdict,
  reason, next action, and updated accepted counts.
- Work through recoverable failures. Stop only for the documented
  `human_review_needed` gate or a truly external blocker.

Begin by verifying the paused state, then implement/check the audio-pass runner
and validator before touching the GPU.
