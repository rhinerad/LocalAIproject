# Start the local agent — soundtrack pass. Paste everything below the line.

---

You are running the **Equal Shares** soundtrack pass on a Windows machine with a
local ComfyUI install. The audio pipeline is debugged and confirmed working. Your
job is to run it across 124 clips, not to redesign it.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Read first

1. **`docs/GOLDEN_REFERENCE/PROVEN_FACTS.md`** — what is actually established,
   each line with its measurement. **Anything not in it is unproven, however
   confidently the rest of this tree asserts it.**
2. `docs/AUDIO_PASS_RUNBOOK.md` — the procedure
3. `docs/H3_PROMPT_RULES.md` — prompt grammar
4. `CLAUDE.md` — binding standing rules

Official MiniMax and ComfyUI documentation is captured verbatim in
`docs/reference/` — consult it rather than the web. Ignore everything in
`archive/` and anything bannered `SUPERSEDED`.

---

# DO NOT ASK ME QUESTIONS

**Every decision you are likely to hit is pre-answered below. Work through the
whole pass without stopping.** Do not ask for approval, confirmation, or a
preference. Do not stop to report and wait. If something is genuinely undecidable,
write it to `outputs/equal_shares/runtime/agent_questions.md`, pick the safest
option listed here, and keep rendering — I will read that file later.

**Standing answers:**

| Situation | What you do — no asking |
|---|---|
| A character has under 6 s of scripted dialogue and cannot make a strong master | Cut the best contiguous passage anyway, mark it `short_master: true` in the map, carry on. A 2–3 s master of the real voice beats no master. |
| A take fails validation, or speaks gibberish / mispronounced words | **Do NOT re-roll the seed.** Advance one rung on the duration ladder — base, +1, −1, +2, −2, +3, −3 — holding the seed fixed. `work/render_audio_pass.py` does this for you. Three rungs, then `human_review_needed` and move on. |
| A ladder retry trips `WRONG_LENGTH` | The checker is wrong, not the take — an upward rung is longer than `audio_pass_durations.json` by design. Re-run it with `--configured-seconds <that attempt's render_seconds>` and carry on. |
| A take has a doubled or layered voice | That is **not** a length fault. Check `retention_analysis` declares `<Audio N>: reference`, and check nothing was prepended above `subject_definitions:`. Note it and continue; do not walk the ladder for it. |
| VRAM will not fit a clip | Drop that clip 0.1 MP and record it. Never below 0.1 MP for audio. |
| GPU too hot | `work/thermal_guard.py` handles it. Wait, do not intervene. |
| A prompt looks wrong | Do not hand-edit it — prompts are generated and your edit will be overwritten. Note it in `agent_questions.md` and continue. |
| Config reports drift | Rebuild it with `sync_omni_audio_config.py` and continue. |
| Something wants a download | Skip it, note the size in `agent_questions.md`, continue without it. |
| A clip's words cannot be verified | That is expected — see acceptance below. Never block on it. |
| You finish all 124 | Run Job 4, write your notes, then stop. |

---

## Job 1 — verify before the GPU

```
python work\sync_omni_audio_config.py --check
```

`audio_pass_config_omni_v1.json` is what the renderer reads and is assembled from
four upstream files, so it drifts silently. It was once found pointing 78 clips at
a superseded prompt set, naming 16 stale voice masters, and carrying scripted
rather than shortened durations — none visible without this check. If it reports
drift, rebuild without `--check` and continue.

Then confirm nothing owns the GPU: running python/ComfyUI processes, port 8188,
and the tail of `runtime/render_supervisor.log` against the clock. **One backend,
ever.** Claim `runtime/render_queue_owner.json` with your PID.

## Job 2 — replace the **2** remaining provisional voice masters

**This job shrank from 8 characters to 2 on 2026-08-18.** Six of the eight listed
below speak in exactly **one** clip each, and a one-off speaker needs no voice
master and no `<Audio N>` — there is nothing for them to be consistent with.

```
python work\classify_voice_requirements.py     # run this first; it is authoritative
```

Still needed: **`Male Visitor One`** (speaks in `00D` and `00D2`) and
**`Terminal voice`** (`11B` and one other). No longer needed: `Aid worker`,
`Council member`, `Crew lead`, `Male Visitor Two`, `Unhoused man`,
`Wealthy commuter` — their audition packs are quarantined under
`EQUAL_SHARES_VOICE_AUDITIONS\_NOT_NEEDED_one_off_speakers\`.

**Do not try to source these from `ComfyUI-Shared\output\video\good audio\`.**
That folder was identified take by take on 2026-08-18: all 14 speaking takes are
the **Narrator** (opening run `00A`–`00O`, with `00B` and `00H` missing). It
contains no audio for any of the eight characters below. The only other voices in
it are Male Visitor One and Male Visitor Two, both inside multi-speaker takes and
both parked as unverified candidates in
`outputs/equal_shares/voices/_good_audio_trimmed/`. See `PROVEN_FACTS.md` §2.

`Aid worker` · `Council member` · `Crew lead` · `Male Visitor One` ·
`Male Visitor Two` · `Terminal voice` · `Unhoused man` · `Wealthy commuter`

Each one's first speaking clip is packaged with prompt, anchor frames, identity
sheets and the correct short render length in
`A:\Users\rhine\Desktop\EQUAL_SHARES_FIRST_APPEARANCE\`.

Render at **0.2 MP**, non-Turbo, 20 steps, using the **short frame count in that
folder's README**. Cut the master from **one contiguous passage from one take —
never stitched**. Verify:

```
python work\speech_density.py <the-cut.wav>
```

Target ≥6 s at ≥70% density. **Four of these characters have only 2–3 s of
scripted dialogue and cannot reach 6 s. Take the best passage you get, mark
`short_master: true`, and move on** — do not ask, and never invent filler
dialogue. Save as `omni_master_v2.wav` (or `_v3`…) under
`outputs/equal_shares/voices/<slug>/`, never overwriting, then re-run
`sync_omni_audio_config.py`.

Start with `048_Terminal_voice` — 12 s of solo scripted speech.

## Job 3 — the soundtrack pass

All 124 clips at **0.2 MP**, ref2va, non-Turbo, 20 steps, `res_multistep` /
`simple`, denoise 1.0, 24 fps, 8-bit, one clean backend per clip, **using the
shortened `frames` from the config**.

### Why the length matters more than anything else

**Length is the retry knob, not the seed.** The number of words is fixed by the
script and the window is fixed by the frame count, so the speech rate the model
must hit is words ÷ duration — and the seed cannot change it. When that rate is
unspeakable H3 does not slow down; it slurs, mispronounces, or invents syllables
to fill the bar. Re-rolling buys a different flavour of the same fault. Moving
one second changes the rate by about 10%.

Hence the operator's ladder: **base, +1, −1, +2, −2, +3, −3**, seed held fixed.

```
python work\duration_ladder.py --clip 00B      # that clip's rungs, in order
```

Correction you must not undo: this file used to say *"H3 fills whatever window it
is given with speech."* **That is false.** `4_`.mp4` in the good-audio set is 56%
silence and is clean. The `00B` failures had a corrupt prepended header as well
as a long duration, and the duration got the blame. Fitting the render to the
line is still right — it is cheaper and removes a variable — but it is a
precaution, not the cause of gibberish.

```
SOUNDTRACK   short   audio_pass_durations.json    00B  345 frames  14.38 s
PICTURE      full    story_config.json            00B  362 frames  15.00 s
ASSEMBLY     pad     +0.63 s digital silence    = 15.00 s
```

**Never write a shortened length into `story_config.json`.** Picture keeps the
film's pacing.

### Accepting a take — mechanically, then queue for ears

You cannot hear. Do not pretend to, and do not stall waiting for me.

```
python work\validate_audio_take.py <take.mp4> --clip <ID>
```

It measures three things and returns exit code 1 on a fault:

- **WRONG_LENGTH** — rendered longer than the config allows. If this take was a
  deliberate ladder retry, re-run the check with `--configured-seconds <its
  render_seconds>`; the checker is wrong, not the take. Otherwise the renderer
  used a stale frame count — re-render at the configured length. **Never re-roll
  the seed for this.**
- **INVENTED** — far more speech than the word count can account for.
- **SILENCE** — too little speech to be the line.

A take with no faults is **plausible, not accepted**. Record it
`pending_ear_review` in `audio_pass_manifest.json` and **move to the next clip**.
Whether the words are right, whether the voice matches, and whether a second
quieter vocal sits underneath are things only I can judge, and I will do it in
batches afterwards. **The audio gate reaching 124/124 accepted is my job, not
yours. Yours is 124/124 rendered and mechanically plausible.**

The speech recogniser cannot decode H3's synthetic voice. **An empty transcript
means unknown, never perfect.** Never mark anything on a transcript alone.

## Job 4 — pad, then stop

```
python work\pad_accepted_soundtracks.py --check
python work\pad_accepted_soundtracks.py
```

Pads each WAV with true digital silence to its scripted duration. Originals kept.

## Hard stops

- **No picture rendering.** Blocked until I accept 124/124 audio.
- **No changes to video timing** in `story_config.json`.
- **No VOX or filler dialogue**, ever.
- **No downloads.** Phone hotspot.
- **Never delete** a raw generation, an approved reference, a manifest, an audit
  record, or source audio. Versioned siblings only.

## How to work

Keep the GPU busy. Do not idle between clips. Report about once a minute: current
clip, status, pass or fail with the reason, next step, updated counts. No log
dumps, no questions.

**Say what you measured.** This project has been misled four times by a checker
that was measuring the wrong thing — a dialogue-accuracy figure reading default
values, a voice check scoring engine noise as speech, a script that failed 68
correct files by searching for a singular verb, and a validator that rejected a
known-good take. When you assert something is good, give the number.

Append what you learn to `docs/WORKFLOW_NOTES.md` under a dated heading.

Begin with Job 1. Report what `sync_omni_audio_config.py --check` says, then keep
going without waiting for me.
