# Stage-1 soundtrack runbook — the working audio pipeline

**Status 2026-08-15: confirmed working.** `00B` rendered at ~9 s with correct
words, one clean voice layer, and no gibberish tail. This file is how to
reproduce that for the other 77 dialogue clips.

Prompt grammar is in `docs/H3_PROMPT_RULES.md`. This file is the operational
procedure.

---

## The four things that had to be true

Each was found by a render failing, in this order. All four are now automated.

| # | Fault | Fix | Where |
|---|---|---|---|
| 1 | quieter second vocal layer under every take | `retention_analysis` declaring `<Audio N>: reference` | prompt, §2 of rules |
| 2 | gibberish mid-line | one `<d>` block per scripted line, never split | prompt, §3 |
| 3 | gibberish after the line | delivery before the tag, mouth closes after it | prompt, §3 |
| 4 | **gibberish filling the tail** | **render short, pad silence at assembly** | duration, §9 |

| 5 | **gibberish or mispronounced words anywhere** | **walk the duration ladder — base, +1, −1, +2, −2, +3, −3, seed held fixed** | duration, §10 |

Faults 4 and 5 are not prompt problems, and 5 supersedes the old explanation of 4.
Words ÷ duration is the speech rate H3 has to hit and only the duration can move
it, so a seed re-roll asks for the same impossible rate under different noise.

**Correction, 2026-08-18.** This runbook used to explain fault 4 with *"H3 fills
whatever window it is given with speech."* **Not supported** — `4_`.mp4` is 56%
silence and is clean. The `00B` failures had a prepended header *and* a long
duration and only the duration was noticed. Rendering short remains correct
(~30% cheaper, and all 14 known-good takes are short) but it is a precaution. It
is still true that **72 of 78 dialogue clips allot 3 s or more beyond what their
lines take to say** — that is a measurement, and it is why fitting is worth doing.

---

## Sources of truth

| File | Holds |
|---|---|
| `story_config.json` | scripted words, windows, anchors, **picture duration — never edit for audio** |
| `prompts_native_r2v/<clip>.txt` | the 124 prompts in H3's native format |
| `omni_voice_master_map.json` | per-character voice master, path + checksum |
| `audio_pass_durations.json` | shortened render length + padding per clip |
| `audio_pass_config_omni_v1.json` | what the renderer reads; assembled from the four above |

`audio_pass_config_omni_v1.json` drifts. Regenerate it rather than hand-editing:

```
python work\sync_omni_audio_config.py --check    # report drift
python work\sync_omni_audio_config.py            # rebuild, keeps a backup
```

It last found 78 prompts pointing at the superseded set, 16 voice references
still naming `omni_master_v1` after the Narrator moved to v2, and 78 clips
carrying scripted rather than shortened durations. None of that was visible
without running it.

---

## Procedure

**0. Confirm who actually needs a voice.**

```
python work\classify_voice_requirements.py
```

A character who speaks in **one clip only** needs no master and gets **no
`<Audio N>`** — there is nothing for them to be consistent with. This is the
single source of that classification; never recount speakers elsewhere. It writes
`outputs/equal_shares/voice_requirements.json`, which
`build_native_r2v_prompts.py` and `build_voice_auditions.py` both read.

Current result: **18 speakers, 10 recurring, 8 one-off.** Four clips have no
recurring speaker and render on plain `MiniMaxH3ImageToVideo` with no references
at all — **`01B`, `20B`, `22B`, `30B`**. Three are mixed and stay on ref2va with
references for the recurring speakers only — `00D2`, `27E`, `28C`.

**1. Confirm the config is current.**

```
python work\sync_omni_audio_config.py --check
```

**2. Check nothing else owns the GPU.** Running python/ComfyUI processes, port
8188, and the tail of `runtime/render_supervisor.log` against the clock. One
backend, ever.

**3. Render the pass.** One clean backend per clip, at **0.2 MP**, non-Turbo,
20 steps, `res_multistep`/`simple`, denoise 1.0, 24 fps, 8-bit — using the
**shortened** `frames` from the config.

**4. Judge by ear, on audio only.** The 0.2 MP picture will look bad; ignore it.
Accept when all five hold:

- the words are the scripted words
- one voice, one dry layer — no quieter duplicate, echo, whisper, or chorus
- no invented speech after the line ends
- no second character muttering underneath
- no invented music

The recogniser cannot decode H3's synthetic voice. **An empty transcript means
unknown, never perfect.**

**4a. When a take is rejected, change ONE thing — and it is usually the
duration.**

| Symptom | What to change | Why |
|---|---|---|
| gibberish, slurring, **mispronounced words** | **duration ladder** — next rung | words ÷ duration is the speech rate the model must hit, and only the duration moves it |
| doubled or layered voice | the prompt's `retention_analysis` (H3_PROMPT_RULES §2), or a prepended header | never a length problem |
| speech in a clip scripted silent | the prompt — extract the embedded graph and check what was actually sent | the renderer may be sending the wrong file |
| voice is the wrong person | the voice master — re-audition | the length cannot fix identity |

The ladder is the operator's rule of 2026-08-18: **base, +1, −1, +2, −2, +3, −3**,
skipping any rung longer than the scripted duration.

```
python work\duration_ladder.py --clip 00B     # that clip's ladder, in order
```

`work/render_audio_pass.py` walks it automatically and **holds the seed fixed
across every rung**, so the only declared variable is length. Each attempt records
`ladder_rung` and `render_seconds` in `audio_pass_manifest.json`.

**Validating a ladder retry:** an upward rung is longer than
`audio_pass_durations.json` allows and will trip `WRONG_LENGTH` unless you pass
its own length.

```
python work\validate_audio_take.py <take.mp4> --clip 00A --configured-seconds 10.833
```

**5. Pad back to the film's timing.**

```
python work\pad_accepted_soundtracks.py --check   # show what will be added
python work\pad_accepted_soundtracks.py
```

Every accepted WAV is padded with true digital silence to its scripted
duration. `00B` becomes 10.83 s + 4.17 s = 15.00 s. Originals are kept; padded
files get a `_padded` suffix.

---

## The duration split — the thing most likely to be broken by accident

```
SOUNDTRACK   short   audio_pass_durations.json     00B  345 frames  14.38 s
PICTURE      full    story_config.json             00B  362 frames  15.00 s
ASSEMBLY     pad     +0.63 s of digital silence  = 15.00 s
```

*(Figures updated 2026-08-17: the pace was corrected from 3.5 to 2.5 words/second
after measuring the 14 known-good clips at a median of 2.75. The old 3.5 came
from one bad `00B` render and was making every clip too short.)*

**The film's pacing is unchanged.** Picture renders its full scripted length;
only the soundtrack render is shortened and then padded back. Runtime is still
1266 s.

`work/render_picture_pass.py` reads duration from `story_config.json` and
strips any shortened value that reaches it, so this cannot leak. **Never write a
shortened length into `story_config.json`.**

Side benefit: the pass costs **31% fewer frames**, 6885 saved across 75 clips.

---

## Voice masters

11 characters have an approved master. 7 do not, and none was invented for them:

`Aid worker` · `Council member` · `Crew lead` · `Male Visitor One` ·
`Male Visitor Two` · `Unhoused man` · `Wealthy commuter`

None has a clip where they are the only person talking for most of the shot.
Their first speaking appearance is packaged per character in
`Desktop\EQUAL_SHARES_FIRST_APPEARANCE\`, each folder holding the prompt, anchor
frames, identity sheets, and the short render length.

Rules that produced the working masters:

- **One contiguous passage from one take.** Never stitched — splicing teaches an
  average of two deliveries, which is the drift the master exists to prevent.
- **Verify it is speech, not level.** Kent's first master came from `14D`, the
  driving clip: 14.6 s of road noise with ~2 s of dialogue, which measured
  −19.9 dB mean and "100% voiced" under a silence gate. Score it with
  `work/speech_density.py`; good is **≥6 s of speech at ≥70% density**.
- **Never overwrite a master.** Save `omni_master_v2.wav`, `_v3`, and so on, and
  re-run `sync_omni_audio_config.py` so the renderer follows.

---

## Regenerating the prompts

```
python work\build_native_r2v_prompts.py
```

Rebuilds all 124 from `story_config.json`. Verified on every run: one `<d>` per
scripted line, exact word fidelity, a mouth-close after every `</d>`, no
delivery prose after any `</d>`, correct pronoun and verb agreement.

If a clip's dialogue changes in `story_config.json`, re-run this **and**
`build_audio_pass_durations.py`, because the render length is derived from word
count.

---

## What still blocks completion

The audio gate is 0 of 124 accepted. Picture is hard-blocked until it reads
124/124. Nothing about Stage 2 has been validated with the corrected audio yet —
that is the next problem, deliberately left until the soundtrack is finished.
