# MiniMax H3 prompt rules — the definitive spec for this project

Supersedes `docs/PROMPT_STYLE_RULES.md`, `docs/PROMPT_REPETITION_RULE.md`, and the
prompt sections of `docs/MINIMAX_H3_PROMPT_OPTIMIZATION.md`. Those were written
before the official guides were read; where they disagree with this file, this
file wins.

Sources, **captured verbatim in `docs/reference/`** so nothing depends on network
access:

| Local copy | Origin |
|---|---|
| `docs/reference/COMFYUI_MINIMAX_H3_TUTORIAL.md` | <https://docs.comfy.org/tutorials/video/minimax/minimax-h3> |
| **`docs/reference/MINIMAX_PROMPT_GUIDE_ref.md`** | MiniMax official R2V guide — **governs this project** |
| `docs/reference/MINIMAX_PROMPT_GUIDE_base.md` | MiniMax official base-mode guide |

Everything here is either quoted from those guides or was established by a
render on this machine. Where it came from a render, that is stated.

---

## 1. The format

R2V prompts have **six named sections, in this order**. Not five, not reordered.

```
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

### Reference labels

| Label | Use for |
|---|---|
| `<Subject N>` | reusable visible content — a person, a set, a costume, a style |
| `<Picture N>` | an image acting as a **concrete frame anchor**: first frame, keyframe, last frame |
| `<Video N>` | a whole-video relationship — editing, continuation, temporal structure |
| `<Audio N>` | an audio asset that is copied or referenced |

Tags follow **the order the inputs were connected**, which is why the ordered
`ref_audios` arrays in `audio_pass_config.json` matter and why `09B` and `09C`
are wired differently despite both being Kent and Avery.

**An identity-only image does not get a `<Picture N>` entry.** Cite it inside
the `<Subject N>` definition instead. Standalone picture entries are for frame
anchors only.

Limits: 9 reference images, 3 reference videos, 3 standalone audio clips. This
film's worst case is 3 speakers in `27E`, so there is no headroom for a fourth.

---

## 2. `retention_analysis` — the section that fixed the doubled voice

**This is the most important discovery in the project.** Every reference gets a
line declaring what relationship it has to the output.

Visible content: `fully_preserved`, `partially_preserved`, `attribute_transfer`,
`weak_reference`.

Audio: `fully_copy`, `partially_copy`, **`reference`**, `weak_reference`.

For a voice-timbre master the marker is always `reference`:

```
<Audio 1>: reference - S1 follows <Audio 1>'s voice timbre, pitch, accent, and
delivery without copying the original signal; none of its words, breaths, or
room tone appear in the target video.
```

**Why it matters.** For weeks every Narrator take carried a quieter second vocal
layer underneath, and no amount of prose forbidding echo, chorus, or duplication
removed it. The prompts had no `retention_analysis` at all, so nothing ever told
H3 the master was a reference rather than a source to copy — and a partial copy
of the master laid under freshly generated speech is precisely what that sounds
like. Adding the section removed the doubling on the first attempt.

The guide states the rule directly: *"When only timbre, rhythm, emotion, or
delivery is referenced, do not carry the original dialogue from the reference
audio into the target video."*

---

## 3. Dialogue

### One scripted line, one `<d>` block

```
<d>[English] If all people feel that someone without should be helped so they
are no longer without, but in the process they become without, how do people
really help each other?</d>
```

**Never split a line across two quoted fragments or two beats.** Two quoted
strings read as two separate utterances, and H3 fills the seam between them with
speech-shaped noise.

Observed on `00B`: a hand-written prompt split the line at
`…so they are no longer without,` / `but in the process…`, and the render
produced about a second of gibberish at exactly that seam.

### Quotation marks mean on-screen text, not speech

Double quotes are reserved for lettering actually rendered in frame. Speech goes
in `<d>`. This inverts the project's long-standing rule, which existed because
the old format had no `<d>` tag.

Quote marks must also be stripped from stage direction — `00M` once carried
`his expression cools on the word "but"`, which is performable as dialogue.

### Speaker IDs

Stable `(S1)`, `(S2)`, numbered by order of first vocal event and reused
everywhere. When a defined subject speaks, write `<Subject 1> (S1)`.

### Delivery goes BEFORE the tag. The mouth closes AFTER it.

This is the second render-confirmed rule, and it follows the guide's own
examples:

> `<Subject 3> (S1) jerks her hand back and, using the clear youthful voice
> timbre referenced from <Audio 1>, exclaims with light annoyance,
> <d>[English] Hey! Watch your dog!</d> **She closes her lips** and guards the
> cookie…`

> `<Subject 4> (S2) says in a casual young male voice with a playful tone…
> <d>[English] He just likes cookies more than me.</d> **He closes his mouth**
> into an apologetic smile…`

Two of the guide's three examples close the speaker's mouth in the clause
immediately after `</d>`.

**Anything describing voice or delivery placed after `</d>` reads as speech
still in progress.** On `00B`, the sentence `The Narrator's delivery cools.`
sat right after the tag and the model kept talking past the scripted words,
producing a tail of gibberish. Moving delivery before the tag and closing the
mouth after it is the fix.

So the shape is always:

```
<Subject 1> (S1) [action], using the voice timbre referenced from <Audio 1>,
in a [delivery] delivery, says: <d>[English] …</d> He closes his mouth and says
nothing further for the rest of the shot.
```

A speaker with more than one line gets `…and is silent until his next line`
instead, so the prompt never contradicts itself.

### Voiceover

Use the exact phrase `says in an off-screen voiceover`, and immediately after
the `<d>` block state that visible mouths stay closed.

---

## 4. Shots, beats and camera

**`[Shot N]` marks a CUT, not a beat.** A continuous take is a single `[Shot 1]`
with no timestamp. Later shots use `[Shot N] At MM:SS.mmm, the shot cuts to…`.

The project's old `[0-1 s]` / `[1-14 s]` bracket notation is **not** the model's
grammar. Timing inside one shot is expressed in prose — "holds for about a
second", "across roughly thirteen seconds".

Camera motion has a controlled vocabulary: `Static Shot`, `Push In`, `Pull Out`,
`Zoom In/Out`, `Pan Left/Right`, `Truck Left/Right`, `Tilt Up/Down`,
`Pedestal Up/Down`, `Arc Shot`, `Tracking Shot`, `Shake Slightly/Strongly`,
`POV`, `Roll Clockwise/Counterclockwise`. Optionally qualified with
`with small amplitude` / `with large amplitude` and `at slow speed` /
`at fast speed`. Write it as natural English inside the shot, not as trailing
labels.

Length: `detailed_description` runs 350–500 words for generation tasks, but
dialogue-dense content prioritises fitting the spoken timeline over word count.

---

## 5. Soundscape

`overall_soundscape` covers ambience, physical action sounds, and non-verbal
human sounds. Dialogue never appears here — it lives only in `<d>`.

`non_diegetic_music` is audience-only score. **For this film it is always
`N/A`** — the continuous score is added at assembly.

This project adds two house rules to `overall_soundscape` — one because the
doubling bug was expensive, one because the model fills unallotted time with
speech. See §8 for the evidence behind both.

> Most of this shot has no speech in it at all, and silence is correct wherever
> no line is assigned. Never more than one voice at a time: no second voice, no
> quieter duplicate, no echo, no reverb tail, no whisper, no chorus, and no
> backing vocal under the speaker. Once the assigned lines are finished the
> voices stop and only room tone continues to the final frame.

**Do not write "exactly one vocal layer is present at any moment".** That was
the original wording and it parses two ways; the wrong reading is "at every
moment there is one vocal layer", which invites continuous speech. State the
ceiling ("never more than one") and the silence separately.

---

## 6. Rules from this project that still hold

These predate the guides and were confirmed by renders here, not by MiniMax.

- **Every second must be accounted for.** Undirected time gets invented — `10B`
  had nothing scripted after 3 s and filled the room with 8–10 people.
- **Every countable action states its integer.** "They repeatedly offer the
  chair" gave one limp gesture; "exactly three offer-and-refusal exchanges, no
  more and no fewer" gave three.
- **Say each thing exactly once.** 73 of 78 clips once sent every line twice,
  once in the body and once in an appended audio lock.
- **Never describe something not in the shot.** Anything you tell the model to
  light, it may draw. A one-person shot must not carry an identity block
  describing three other people.
- **Name a discriminator between similar characters.** The two visitors wear
  near-identical suits; the standing one has a white pocket square.
- **Light interiors generously even when the mood is sombre.** The daylight
  driving clip `14D` is among the cleanest in the film; the dim interiors in
  scenes 13, 16 and 17 are the worst.
- **Never paste prompt text out of the CSV.** It wraps fields in quotes and
  doubles internal quotes. 0 of 7 quote-wrapped prompts were ever kept.

---

## 7. How the prompts are generated

`work/build_native_r2v_prompts.py` writes all 124 into
`outputs/equal_shares/prompts_native_r2v/`. It reads `story_config.json` for the
authoritative words and windows, the older prompt sets for scene prose, and
`omni_voice_master_map.json` for which characters have a voice master.

Verified after every run:

- 78 dialogue clips, **one `<d>` block per scripted line**, zero splits
- word-for-word fidelity against `dialogue_timing`, zero words added or dropped
- a mouth-closing clause immediately after **every** `</d>`
- no delivery or voice prose left after any `</d>`
- pronoun and verb agreement on every generated clause

Two bugs found by those checks and worth remembering:

1. `parse_sections` originally required headers to be fully capitalised, so
   `SHOT LIST and DIALOGUE TIMING` — with its lowercase "and" — was not
   recognised, and the first run produced 124 prompts containing **no dialogue
   at all**. Structural checks catch this; eyeballing one file does not.
2. The mouth-close clause was first appended to every line, telling a character
   with two lines to fall silent before speaking the second. It is now attached
   only to a speaker's final line.

---

## 8. Telling the model when to STOP — added 2026-08-15 after a third failure

Two earlier fixes (one `<d>` per line; mouth closes after the tag) did not stop
gibberish at the **end** of `00B`. Measuring the render explained why.

```
clip duration      15.1 s
scripted window    1.0 - 14.0 s
line               30 words -> ~9-11 s at a natural pace

render speech      0.74-5.53   6.15-8.05   8.68-10.44   |gap 0.95s|   11.39-14.93
```

The scripted line is finished by about **10.4 s**. Then comes the longest gap in
the clip, and then **3.5 more seconds of speech running to the final frame**.
The model delivered the line, found four seconds of unallotted time, and filled
it — because nothing in the prompt said the remainder is silent.

**The native single-shot format carries no timestamps**, so unless silence is
stated in prose the model has no instruction to stop. Two additions:

**1. State the stop explicitly, allowing for an early finish.**

> There is only one spoken line in this entire shot, and `<Subject 1>` delivers
> it at an unhurried natural pace. When the last line is finished — **however
> early in the shot that falls** — every voice stops. Nobody speaks, mutters,
> hums, sighs, or makes any vocal sound for the whole remainder of the shot, and
> the shot plays out on room tone alone. No extra words are invented to fill the
> remaining time.

The "however early that falls" clause is the important part. The script allots
13 seconds for a line that takes 10, and that gap is where invention happens.

**2. Fix an ambiguous sentence that was inviting the opposite behaviour.**

The soundscape previously read *"Exactly one vocal layer is present at any
moment."* The user spotted that this parses two ways, and the wrong reading is
"at every moment there is one vocal layer" — that is, someone is always talking.
Now split into a ceiling and a silence:

> Most of this shot has no speech in it at all, and silence is correct wherever
> no line is assigned. **Never more than one voice at a time**: no second voice,
> no quieter duplicate, no echo… Once the assigned lines are finished the voices
> stop and only room tone continues to the final frame.

**General lesson: state silence positively.** A prompt that only describes sound
gives the model no model of quiet, and H3 fills unallotted time with speech. Say
how many lines exist, and say that everything else is silent.

---

## 9. When the prompt cannot fix it — shorten the clip. Added 2026-08-15.

**Three prompt fixes failed on the same fault.** After §3's one-`<d>`-per-line
rule, §3's mouth-close rule, and §8's explicit stop instruction, `00B` still
produced fresh speech from the moment the scripted line ended until the final
frame. Different gibberish each time, the same position every time.

> ### CORRECTED 2026-08-17 — read this before believing the section below
>
> This section used to assert: *"H3 fills the clip. Asking it to synthesise
> several seconds of silence is fighting the architecture."* **That is not
> supported by the evidence.** Measured across the operator's 14 known-good
> clips:
>
> | clip | words | duration | speech | silence |
> |---|---|---|---|---|
> | `4_`.mp4` | 13 | 8.0 s | 3.5 s | **56%** |
> | `15.mp4` | 8 | 7.3 s | 5.4 s | 26% |
> | `2.mp4` | 17 | 9.4 s | 7.8 s | 17% |
>
> A clip that is **more than half silence** came out clean. A model that fills
> its window with invented speech could not produce that.
>
> What actually happened: the `00B` failures carried **two** faults at once — a
> prepended `AUDIO-FIRST REFERENCE JOBS` header (see
> `docs/GOLDEN_REFERENCE/README.md`) **and** a long duration. The duration was
> blamed, a whole doctrine was built on it, and the header went unnoticed for a
> week.
>
> **So section 9 is a precaution, not a cause.** Fitting the render to the line
> is still correct — it is cheaper, it removes a variable, and every good clip is
> short. It is not the explanation for gibberish, and it must not be used to
> dismiss a prompt-side fault. Section 10 is the tool that actually addresses
> mispronunciation.

### The measurement that settles it

| | |
|---|---|
| `00B` scripted duration | 15.0 s, 362 frames |
| line | 30 words |
| delivered pace | ~3.5 words/second, measured across three renders |
| speech actually needs | ~9 s |
| **unallotted tail** | **~6 s** |

And across the film: **72 of 78 dialogue clips allot 3 seconds or more beyond
what their lines take to say.** `00A` over-allots by 9.6 s, `00O` by 9.2 s. The
scripted durations were written for picture and pacing; nobody ever checked them
against speech length.

### The rule

**Never ask H3 for silence. Render only as long as the speech needs, and pad
silence at assembly.**

```
Stage 1 (soundtrack)   render audio_pass_frames from audio_pass_durations.json
Assembly               pad the accepted WAV with digital silence to the
                       scripted duration
```

`work/build_audio_pass_durations.py` computes this per clip at **2.5
words/second** with a **1.5 s** tail margin, snapping to the 17-frame grid. `00B`
goes from 362 frames to **345** and gets 0.63 s of padding at assembly.

*(Pace corrected 2026-08-17. It was 3.5 w/s, taken from a single bad `00B`
render. The 14 known-good clips run at a median of **2.75 w/s**, range 1.14–3.89,
so 3.5 was making every clip too short — the opposite of the intended safety
margin. 2.5 sits just under the observed median.)*

**The timeline is untouched.** Picture still runs its full scripted length; only
the soundtrack render is shortened, and the WAV is padded back to match. The film
is still 1266 s.

Two side benefits: silence added in an editor is *perfectly* silent, which is the
one thing a generative model cannot promise — and the pass costs **31% fewer
frames** overall, 6885 frames saved across 75 shortened clips.

### The general lesson

When three prompt revisions fail on the same fault in the same place, the fault
is probably not in the prompt. Ask what the model is structurally trying to do —
here, fill its output window — and change the shape of the request instead of the
wording.

---

## 10. The DURATION LADDER — how to retry gibberish and mispronounced words. Added 2026-08-18.

**Operator rule, verbatim:**

> "when generating audio and trying to get perfect English words (getting rid of
> gibberish or mispronounced words) use this generation pattern. Example start at
> 10 sec; if gen is bad (has mispronounced words) add a second. If that does not
> work go back to 10 and go down to 9 seconds. The pattern of generation to fix
> gibberish and mispronounced words is the following; 10, 11, 9, 12, 8, 13, 7 and
> so forth."

So from a base length **D**, rungs alternate outward, **up first**:

```
D    D+1    D-1    D+2    D-2    D+3    D-3    D+4    D-4
```

Implemented once, in `work/duration_ladder.py`. Nothing else may reimplement it.

```
python work\duration_ladder.py --seconds 10     # any base
python work\duration_ladder.py --clip 00B       # a story clip, capped at its script
```

### Why duration and not the seed

The number of words is fixed by the script. The size of the window is fixed by
the frame count. So **the speech rate the model has to hit is words ÷ duration,
and only the duration can change it.** A seed changes the noise, not the metre.

When the required rate is one the model cannot speak, it does not slow down or
leave a gap — it slurs, elides, mispronounces, or invents syllables to fill the
bar. That is why re-rolling has been producing *a different flavour of gibberish*
rather than clean speech. One second is roughly a 10% change in rate, which is
enough to land on a metre the model can actually articulate.

Up first because a fractionally slow delivery sounds natural and a rushed one
does not.

### The two knobs, and never turn both

| Symptom | Knob | Why |
|---|---|---|
| **Wrong voice** — words are fine, timbre/age/accent is not the character | **Seed** | Only during voice auditions, where no `<Audio N>` is wired and H3 invents the voice. |
| **Wrong words** — gibberish, slurring, mispronunciation | **Duration ladder** | The seed cannot change words-per-second. |
| **Doubled or layered voice** | Neither | That is a `retention_analysis` fault — see §2 — or a prepended header. Fix the prompt, not the length. |
| **Speech in a clip that should be silent** | Neither | The prompt is wrong or the wrong prompt was sent. Extract the embedded graph and check. |

Changing two things at once is how this project spent a week blaming duration for
a fault the header was causing. **One knob per attempt.**

### The 17-frame block grid makes a "second" approximate

H3 snaps to frame counts congruent to 5 modulo 17 at 24 fps, and this project
rounds **up** (CLAUDE.md, non-negotiable). One block is 0.708 s, so a nominal
one-second step realises as 0.71–1.42 s. From a nominal base of 10 s:

| try | rung | nominal | frames | actual |
|---|---|---|---|---|
| 1 | 0 | 10 s | 243 | 10.125 s |
| 2 | 1 | 11 s | 277 | 11.542 s |
| 3 | 2 | 9 s | 226 | 9.417 s |
| 4 | 3 | 12 s | 294 | 12.250 s |
| 5 | 4 | 8 s | 192 | 8.000 s |
| 6 | 5 | 13 s | 328 | 13.667 s |
| 7 | 6 | 7 s | 175 | 7.292 s |

The rungs are always distinct and always ordered. They are simply not exactly a
second apart, and any doc claiming otherwise is wrong.

### Bounds

**Upper: the clip's scripted duration.** A Stage-1 soundtrack is padded with
digital silence up to the scripted length at assembly, so a soundtrack longer
than its picture is unusable. Out-of-range rungs are **skipped, not clamped** —
clamping would render the same length twice and waste an attempt. A clip whose
base already equals its scripted length therefore gets a purely downward ladder;
`00B` is one of these.

**Lower: 3.0 s.** Below that there is no window for the words at any pace.

### The trap: your own validator will reject your correct retries

`work/validate_audio_take.py` raises `WRONG_LENGTH` when a render is longer than
`audio_pass_durations.json` says. **Every upward rung is longer than that by
design.** Pass the rung's length:

```
python work\validate_audio_take.py <take.mp4> --clip 00A --configured-seconds 10.833
```

`work/render_audio_pass.py` records `render_seconds` on every attempt for exactly
this. This is the fifth time in this project a checker has measured the wrong
thing; do not make it the sixth.

### Status — unverified

This is the operator's rule, taken from their own hand-rendering, implemented as
given. **No render has been made under it.** It changes no node, no model, and no
setting in `docs/GOLDEN_REFERENCE/PROVEN_GOOD_AUDIO_GRAPH.api.json` — only the
`length` value fed to the existing graph. Every attempt now records its
`ladder_rung`, so after the first pass the rule can be judged on which rungs
actually produced clean takes, rather than on belief.
