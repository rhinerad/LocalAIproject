# Start the voice auditions — paste everything below the line into Claude Code

---

You are running the **Equal Shares voice audition pass**. Your job is 27 renders,
then stop. You are **not** running the 124-clip soundtrack pass, and you must not
start it.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Read first, in this order

1. **`docs/GOLDEN_REFERENCE/PROVEN_FACTS.md`** — what is actually established,
   each line with its measurement. **Anything not in it is unproven, however
   confidently the rest of this tree asserts it.**
2. `CLAUDE.md` — binding standing rules.
3. `CHANGELOG/2026-08-18c_one_off_speaker_rule.md` — the most recent change set.

Ignore everything under `archive/`, anything bannered `SUPERSEDED`, and anything
inside `outputs/equal_shares/_QUARANTINE_corrupt_prompt_pass_2026-08-17/`.

---

# DO NOT ASK ME QUESTIONS

Every decision you are likely to hit is answered below. Work the whole pass
through. If something is genuinely undecidable, append it to
`outputs/equal_shares/runtime/agent_questions.md`, take the safest option listed
here, and keep rendering.

| Situation | What you do |
|---|---|
| A take sounds wrong to you | You cannot hear. Do not judge takes. Render all 27 and stop. |
| A render fails | Retry that take once. Then record `render_error` and move on. |
| VRAM will not fit | Drop that render 0.1 MP and record it. Never below 0.1 MP. |
| GPU too hot | `work/thermal_guard.py` handles it. Wait; do not intervene. |
| A prompt looks wrong | Do not hand-edit it. Prompts are generated and your edit will be overwritten. Note it and continue. |
| Something wants a download | Skip it, note the size, continue. The operator is on a phone hotspot. |
| You want to start the 124-clip pass | **No.** That is gated on the operator choosing voices. Stop when the 27 are done. |

---

## Job 1 — preflight, before the GPU

```
python work\classify_voice_requirements.py --check
python work\sync_omni_audio_config.py --check
python work\render_voice_auditions.py --dry-run
```

Expected: **18 speakers, 10 recurring, 8 one-off**; drift check clean; **9
characters x 3 takes = 27 renders**.

Then confirm nothing owns the GPU — running python/ComfyUI processes, port 8188,
and the tail of `outputs/equal_shares/runtime/render_supervisor.log` against the
clock. **One backend, ever.** The runner claims
`runtime/render_queue_owner.json` itself; do not bypass it.

## Job 2 — render the 27 auditions

```
python work\render_voice_auditions.py
```

Roughly 2–3 hours. One clean backend per render, thermal guard before and after.
Output lands in `story/AUDITION_<slug>/`, progress in
`outputs/equal_shares/voice_audition_manifest.json`.

### The three things that make an audition valid — do not "fix" any of them

1. **No audio reference.** `ref_audios` stays disconnected. There is no approved
   voice to match; wiring an unapproved master would lock in the exact voice we
   are replacing. The runner skips any pack whose prompt contains `<Audio` rather
   than proceeding.
2. **The prompt starts `subject_definitions:` with nothing above it.** All 15
   known-good renders do. A prepended header is what corrupted the last pass.
3. **Only the seed varies across the three takes.** Seed changes the invented
   voice. That is the point here, and it is the only place in this project where
   re-rolling is correct.

### If a take has the right VOICE but bad WORDS

Do not re-roll. Hold the seed and walk the duration ladder:

```
python work\render_voice_auditions.py --character Kent --seed <that seed> --ladder-rung 1
```

Rungs go base, +1, −1, +2, −2 (`work/duration_ladder.py`). Words ÷ duration is
the speech rate the model must hit and only the duration can move it. Judging
"right voice, bad words" is the operator's call, not yours — only do this if they
ask.

## Job 3 — stop and hand back

When 27 are rendered, print the manifest summary and **stop**. Tell the operator:

> 27 auditions rendered. Listen to `story\AUDITION_<slug>\` and pick one take per
> character, then run:
> `python work\install_audition_winners.py --pick Kent=2 --pick Avery=1 ... --apply`

**You cannot choose the voices.** That is the whole point of this pass.

---

## Why the 124-clip pass is blocked

State was reset on 2026-08-18. All 124 clips will render from scratch, because
every prior take came from the corrupted-prompt pass. Their media and the old
manifest are preserved in
`outputs/equal_shares/_QUARANTINE_corrupt_prompt_pass_2026-08-17/`.

**8 of the 10 recurring characters still have unapproved masters** — the ones the
operator says speak gibberish. Running the pass now would bake those voices into
74 clips. The gate is the operator's ear, not a script.

Once winners are installed:

```
python work\sync_omni_audio_config.py
python work\build_native_r2v_prompts.py
```

and only then does `START_LOCAL_AGENT.md` apply.

---

## Standing constraints

- **No downloads.** Phone hotspot. State the size and ask first.
- **Never delete** a raw generation, an approved reference, a manifest, an audit
  record, or source audio. Versioned siblings and quarantine folders only.
- **No picture rendering.** Blocked until the audio gate reads 124/124 accepted.
- **No changes to video timing** in `story_config.json`.
- **No VOX or filler dialogue**, ever.
- **Write a `CHANGELOG/` entry** in the same session as any change you make, with
  the five required fields. Document consistency is not verification —
  verification means extracting the workflow embedded in a real render and
  diffing it against `docs/GOLDEN_REFERENCE/GOOD_AUDIO_GRAPHS.json`.

## Reporting

Concise plain language roughly once a minute: current character and take, status,
next step, updated counts. No log dumps. **Say what you measured** — this project
has been misled six times by a checker measuring the wrong thing. When you assert
something is good, give the number.
