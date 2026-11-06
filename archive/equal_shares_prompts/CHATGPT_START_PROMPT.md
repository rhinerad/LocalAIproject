# ChatGPT — start prompt. Paste everything below the line.

> **SUPERSEDED 2026-08-16 — historical, do not execute.**
>
> This file instructs rendering purpose-built VOX clips with invented filler
> dialogue. **That is prohibited.** A missing character voice comes only from
> that character's first qualifying actual story soundtrack.
>
> Current instructions: `docs/AUDIO_PASS_RUNBOOK.md` (procedure),
> `docs/H3_PROMPT_RULES.md` (prompt grammar), `CHATGPT_START_AUDIO_PASS.md`
> (paste-able start prompt). `CLAUDE.md` is binding.


> **Current lock, 2026-08-14:** Any VOX, filler-dialogue, one-pass, or 00J
> branch below is historical and must not be executed. Missing voices are
> bootstrapped only from their first qualifying actual story soundtrack using
> `work/render_audio_pass.py --bootstrap-missing-voices` at 0.2 MP, non-Turbo
> MiniMax H3, 20 steps. Complete and approve all 124 soundtracks before Stage 2.
> `CLAUDE.md` and `outputs/equal_shares/story_voice_bootstrap_plan.json` are
> authoritative when this older prompt conflicts.

---

You are taking over the **Equal Shares** film project: a ~21-minute film built as
124 MiniMax H3 clips rendered locally in ComfyUI on a Windows machine.

## First, read the handoff

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\CHATGPT_HANDOFF.md
```

It is self-contained. If you cannot reach the filesystem, say so immediately and
I will paste it in — do not guess at project state or invent file contents.

**Read §15, the decision log, before you change any setting or rule.** Sections
1–14 say what the rules are; §15 says why, with the measurement behind each one.
Several rules look arbitrary and are not. If you think a rule is wrong, check
§15 first, then tell me what evidence would change it.

Then, in the same folder:

* `CLAUDE.md` — standing rules, binding
* `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md` — the plan and the branch logic
* `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` — Tasks 0–5 in operational detail
* `docs/WORKFLOW_NOTES.md` — running log of what works and what does not

**§16 lists what lives outside this folder** — the raw renders, the model
weights and the ComfyUI install are in `A:\Users\rhine\ComfyUI-Shared\`, and you
need read access there. The proven ref2va graph does **not** require parsing a
PNG: it is extracted to
`outputs/equal_shares/ref2va_proven_workflow.api.json`. All 124 prompts are on disk in
`outputs/equal_shares/prompts_native_r2v/`, in H3's native six-section R2V
format. **Read `docs/H3_PROMPT_RULES.md` before editing any prompt.** The older
`prompts_audio_pass/` and `prompts_no_dialogue/` sets are superseded.

Ignore everything in `archive/`. It is kept as evidence, not as instruction. Any
document asserting **736×416 or 0.3 MP** as current is out of date, however
authoritative it sounds.

## Where things stand

**124 rendered · 43 accepted · 22 confirmed rejects · 51 never reviewed.**
"Progress N/124 valid clips" in the supervisor log counts renders, not
approvals. The film is not finished.

Machine state as I hand over:

* ComfyUI port 8188 is not listening.
* `outputs/equal_shares/runtime/render_queue_owner.json` still names PID `12564`.
  That process is gone — **the entry is stale.** Do not read it as an active
  render. Claim the queue with a fresh PID and purpose string.
* `runtime/render_supervisor.log` last advanced 2026-08-12 04:48.

## Job 1 — finish the 00J audit

The test render already exists. **Do not regenerate it.**

```
A:\Users\rhine\ComfyUI-Shared\output\story\TEST_09MP_00J\
    00J_00001_.mp4
    00J_00001_audio.wav
    00J_norm.wav
```

This is clip `00J` rendered with the **ref2va checkpoint plus an audio
reference, at 0.9 MP**. Audit it on four criteria and give a **separate verdict
for each** — "it looks fine" is not a result:

1. **Voice.** Compare by ear against
   `outputs/equal_shares/voices/narrator/h3_voice_ref.wav` and
   `A:\Users\rhine\ComfyUI-Shared\output\video\1.mp4`. Same man?
2. **Face.** Kent and the Narrator at native resolution, across the whole clip.
   Not on a contact sheet — contact sheets have never once caught a face fault
   in this project, and §15 explains why.
3. **Camera.** `00J` is a continuous descent from high aerial to chest height.
   At 1.0 MP the camera previously fell through the ground into a different
   cityscape. Verify it does not, and does not cut or reverse.
4. **Words and timing.** Scripted line is in
   `outputs/equal_shares/prompts_audio_pass/00J.txt`.

The previous session stalled on an **empty Windows Speech transcription
result**. Diagnose it — sample rate, channels, bit depth, duration of
`00J_norm.wav`, and whether the recogniser is getting a readable path — but **do
not let a broken transcription tool block criteria 1 through 3.** Transcribe by
ear if you have to.

**Download nothing.** The user is on a phone hotspot. If something needs
weights, state the size and stop for agreement.

### Then branch

| Result | Action |
|---|---|
| Voice, face and camera all pass | Drop the two-stage plan. Render the film in one ref2va pass at 0.9 MP, using `outputs/equal_shares/prompts_audio_pass/` for the 78 dialogue clips and the existing prompts for the 46 without. Skip the stage-1 audio pass and the lipsync stage entirely. |
| Camera wanders, face clean | Retry once at 0.8 MP, then fall back to the 0.2 MP audio pass. |
| Face degraded | Try 0.8 MP before concluding anything. |

This one clip decides roughly 17 hours of rendering against 38 or more, which is
why it comes first.

## Job 2 — render 7 voice-reference VOX clips

Independent of Job 1's outcome, and needed either way.

The voice references were rebuilt on 2026-08-13 after the first set was found to
be wrong — it was cut from *scripted* dialogue windows and validated with mean
dB, so Kent's reference came from the driving clip and was mostly engine noise.
**11 characters now have a real reference. 7 have none, and none was invented
for them:**

`Aid worker` · `Council member` · `Crew lead` · `Male Visitor One` ·
`Male Visitor Two` · `Unhoused man` · `Wealthy commuter`

No clip anywhere in the film has these characters as the only person talking for
most of the shot — their lines run 2–6 seconds inside multi-character scenes. So
each needs a purpose-built clip whose only job is to make them talk.

Specs are in `outputs/equal_shares/voice_reference_vox_specs.json`. Per clip:
15 s, 0.2 MP, single anchor, **exactly one person in frame speaking continuously
from 1 s to 14 s**, fresh filler dialogue in that character's register — never
film dialogue, so a leaked clip is obviously not part of the story. Cover a
spread of vowels, plosives, sibilants and nasals.

**Judge on audio only.** Continuous speech, one voice, no music. Gibberish words
are fine; this is a timbre reference, not a performance. Re-roll only for
silence, a second voice, or invented music.

Then cut each reference with `work/build_voice_reference_map.py --extract` and
verify with `work/speech_density.py`. A reference is good at **≥6 s of speech at
≥70% density**. Report the numbers, do not just say it worked.

Seven clips, about an hour. It unblocks `00D`, `00D2`, `01B`, `27E`, `28C` and
`30B`. Never add VOX clips to `story_config.json`, `manifest.json`, or the
completion audit. Files named `*.V1_REJECTED_DO_NOT_USE.wav` are from the broken
earlier pass — never wire them into a graph.

## How to work

**Keep the GPU busy.** This is many hours of rendering. Do not idle waiting for a
reply and do not pause between clips. If you have a question, ask it inside your
progress report and keep working while you wait.

**Before anything touches the GPU**, check all three: running python/ComfyUI
processes, whether port 8188 is listening, and the tail of
`runtime/render_supervisor.log` against the current clock. Exactly one process
may bind 8188. If that log is advancing, a render is alive — monitor it, never
duplicate it.

**Report roughly once a minute** during long work: current clip or stage, status,
pass or fail with the reason, next step, updated counts. No raw log dumps. Do not
stop working merely to report.

**Verify claims with measurements, not impressions.** This project has twice
been misled by a metric that was measuring the wrong thing — a dialogue-accuracy
figure that was reading default values, and a voice-reference check that scored
engine noise as speech. When you assert something is good, say what you measured.

**Never delete anything.** Not a raw generation, an approved reference, a
manifest, an audit record, source audio, an assembly input, or a deliverable. If
a deletion or overwrite would be needed, keep the original and write a versioned
sibling, copy rather than move, or quarantine the obsolete intermediate. A denied
destructive command means pick a non-destructive route and continue, not stop.

**Do not hand-edit `manifest.json` or `visual_audit.json` while a render is
live.** The runner merges only the current clip's record so concurrent review
decisions survive; a manual write defeats that.

**Keep working through recoverable failures.** A crashed backend, a stale
process, a file lock, a rejected clip, a failed tool — diagnose, preserve
evidence, recover, continue. None of those is a stopping point.

Stop only for a user-only credential, a missing source asset, a material creative
decision, or an external condition that cannot be safely worked around. When you
do stop, give the exact evidence and ask for the smallest action that unblocks
you.

**Append what you learn** to `docs/WORKFLOW_NOTES.md` under a dated heading.
Append; do not rewrite earlier entries. Be specific enough that the eventual
automation program could be built from it — that is the point of the file.

The completion gate is `work/audit_equal_shares_completion.py`. Do not claim the
film is finished before it passes.

Begin by confirming the stale PID and the existing `TEST_09MP_00J` output, then
finish the Task 0 evaluation and tell me the four verdicts.
