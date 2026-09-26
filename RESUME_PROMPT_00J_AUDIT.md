# Resume prompt — finish the 00J audit. Paste everything below the line.

> **Fully superseded for execution, 2026-08-14.** Keep this file as historical
> evidence only. Do not execute its one-pass branch or its VOX/filler section.
> The current path is actual-story voice bootstrap at 0.2 MP with exact scripted
> dialogue, followed by the complete 124/124 accepted soundtrack gate, then
> picture at 0.9-to-0.4 MP. Follow `CLAUDE.md` and
> `outputs/equal_shares/story_voice_bootstrap_plan.json`.

---

Resume this exact Equal Shares session from its last unfinished action.

Reload and follow, in this order:

* `CLAUDE.md` — standing rules, updated 2026-08-13 with the three render paths
* `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md` — the current plan and the Task 0 branch logic
* `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` — Tasks 0 through 5 in operational detail
* `PROJECT_CONTINUATION_BRIEF.md` — background state
* `.claude/settings.local.json` — permissions
* `CLAUDE_CODE_PROMPT.md` — **partly superseded.** Use it only for the one-backend
  procedure, the never-delete rules, the reporting format, and the
  continue-until-finished requirement. Ignore its "Standing constraints",
  "Resume commands", and "Known open items" sections: they name fl2va at
  736×416 / 0.3 MP and point at `render_until_complete.py`, all of which the
  audio-first documents replace.

## Current state

* PID `12564` is no longer running.
* `runtime/render_queue_owner.json` still contains PID `12564`. That entry is
  stale. Do not treat it as an active render. Claim the queue yourself with a
  fresh PID and purpose string.
* ComfyUI port 8188 was not listening at the latest check.
* `runtime/render_supervisor.log` last advanced 2026-08-12 04:48 and reads
  "All clips valid". That is the old fl2va 0.3 MP pass and is a render count,
  not an acceptance count. It does not mean the film is finished.
* The 00J 0.9 MP test already rendered. **Do not regenerate it before auditing
  the existing result.** Existing files:
  * `A:\Users\rhine\ComfyUI-Shared\output\story\TEST_09MP_00J\00J_00001_.mp4`
  * `A:\Users\rhine\ComfyUI-Shared\output\story\TEST_09MP_00J\00J_00001_audio.wav`
  * `A:\Users\rhine\ComfyUI-Shared\output\story\TEST_09MP_00J\00J_norm.wav`
* The previous session stopped while investigating an empty Windows Speech
  transcription result.

## Finish Task 0 — audit the existing 00J test in this order

1. **Voice.** Compare by ear against `outputs/equal_shares/voices/narrator/h3_voice_ref.wav`
   and `A:\Users\rhine\ComfyUI-Shared\output\video\1.mp4`. Is it the same man?
2. **Face.** Inspect Kent and the Narrator at native resolution across the whole
   clip, not on a contact sheet. A contact sheet has never once caught a
   face-level fault in this project.
3. **Camera.** 00J is a continuous descent from high aerial to chest height. At
   1.0 MP the camera previously fell through the ground into a different
   cityscape. Verify it does not, and that it does not cut or reverse.
4. **Words and timing.** The scripted line is in
   `outputs/equal_shares/prompts_audio_pass/00J.txt` and in `dialogue_timing`
   for 00J in `story_config.json`. Listen. If Windows Speech stays empty,
   transcribe by ear or with another method already installed. **Download
   nothing.**

Diagnose the empty transcription — check sample rate, channel count, bit depth
and duration of `00J_norm.wav`, and whether the recogniser is receiving a path it
can read — but do not let a broken transcription tool block the visual and
listening audit. Evaluate everything that can be evaluated independently.

## Then branch, per the pipeline document

* **Voice, face and camera all pass** → drop the two-stage plan. Render the film
  in one ref2va pass at 0.9 MP, using `prompts_audio_pass/` for the 78 dialogue
  clips and the existing prompts for the 46 without. Skip Tasks 1 and 3.
* **Camera wanders, face clean** → retry once at 0.8 MP, then fall back to
  Task 1, the 0.2 MP audio pass.
* **Face degraded** → try 0.8 MP before concluding anything.

Record the verdict for each of the four criteria separately. "It looks fine" is
not a result.

## After the audit, whatever the branch

Render the 7 voice-reference VOX clips in
`outputs/equal_shares/voice_reference_vox_specs.json`. The voice references were
rebuilt on 2026-08-13; 11 characters have a real one and 7 have none, because no
clip has them as the only person talking for most of a shot. 15 s each, 0.2 MP,
single anchor, one person speaking continuously 1–14 s, fresh filler dialogue.
Judge on audio only. Verify with `work/speech_density.py` — good is ≥6 s speech
at ≥70% density. Never add them to `story_config.json` or `manifest.json`.
Files marked `V1_REJECTED_DO_NOT_USE` are from the broken pass; never wire them.

## Standing requirements

Use the configured permissions automatically for normal project commands, edits,
rendering, validation, recovery, assembly, and publishing. Do not ask whether to
continue when the next safe action is already specified.

If a deletion or overwrite permission would arise, do not pause. Keep the
original and write a versioned sibling, copy rather than move, or quarantine an
obsolete generated intermediate. Never delete a raw generation, approved
reference, manifest, audit record, source audio, assembly input, or final
deliverable.

Work through recoverable failures and long-running operations until the project
is finished and `work/audit_equal_shares_completion.py` passes. Stop only for a
user-only credential, a missing source asset, a material creative decision, or
an external condition that cannot be safely worked around.

Report roughly once a minute during long work: current clip or stage, status,
pass or fail with the reason, next step, updated counts. No log dumps.

Begin by confirming the stale PID and the existing 00J output, then finish the
Task 0 evaluation.
