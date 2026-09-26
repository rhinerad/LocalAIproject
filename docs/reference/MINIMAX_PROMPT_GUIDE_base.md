# Video Prompt Writing Guide (T2VA / I2VA / FL2VA / L2VA)

**Verbatim copy of MiniMax's official base-mode guide, captured 2026-08-16 from**
`https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md`

This project uses R2V, so `MINIMAX_PROMPT_GUIDE_ref.md` is the governing
document. **But the ref guide defers to this one** for shots, cuts, camera
vocabulary, speaker IDs, and dialogue format — so those rules come from here.

---

## 1. Task Overview

- **T2VA**: builds a complete audiovisual timeline from text.
- **I2VA**: T2VA body + first-frame instruction + a visual path developing forward
  from the first frame.
- **FL2VA**: T2VA body + first-and-last-frame instruction + a continuous path from
  the first frame to the last.
- **L2VA**: T2VA body + last-frame instruction + a path converging from a
  plausible preceding state to the last frame.

## 2. Final Prompt Structure

### 2.1 Part One Is the Instruction

**T2VA** has no image-alignment instruction and begins directly with the three
core fields.

**I2VA**:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from
[Shot 1]) is fully referenced.
```

**FL2VA**:

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1)
aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N)
aligns with the S.SS-second mark of the target video.
```

**L2VA**:

```text
How the reference pictures align with the target video — <Picture 1> (from
[Shot N]) aligns with the S.SS-second mark of the target video.
```

`N` is the index of the actual final shot; `S.SS` is the effective video duration
to exactly two decimal places. The instruction must be the first line, followed by
one blank line before the core fields.

### 2.2 Part Two Contains the Three Core Fields

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

## 3. Incorporating Keyframes

**I2VA** — begin from the image and develop forward. `<Picture 1>` is the actual
first frame at 0.00 s and belongs to `[Shot 1]`. Recommended structure:
**first-frame anchor → action onset → continuous development → result or
reaction**.

**FL2VA** — describe the path between first and last frames. The body should not
repeat two static image descriptions; it should supply the motion path connecting
them. **FL2VA generally favors a single shot** so the model can interpolate
continuously. Recommended: **first-frame state → observable intermediate changes →
progressively narrowing differences → last-frame state**.

**L2VA** — infer the opening and land on the image at the end. Recommended:
**plausible preceding state → explicit action and transition path → gradual
convergence → last-frame landing**.

## 4. The Three Shared Core Sections

### 4.1 Develop the Description Along the Timeline

Every detail should correspond to something visible or audible. At the beginning
of `[Shot 1]`, state the overall style and initial composition. Common styles:
`Cinematic`, `live-action`, `2D-animated`, `3D CG`, `claymation`, `watercolor`,
`vintage film`.

```text
[Shot 1] Live-action, cinematic, a medium-wide shot frames...
```

### 4.2 Shots and Cuts

**Do not add a timestamp to the first shot.** Later shots use sequential numbers
and begin with a strictly increasing cut time within the video duration:

```text
[Shot 2] At 00:03.500, the camera cuts to...
```

For ordinary cuts use `the camera cuts to`, `the shot cuts to`, `the shot
transitions to`, `the shot changes to`, or `the shot switches to`. **A cut should
introduce new information** about subject, space, state, viewpoint, or time. If
only distance or a slight angle needs to change, **prefer camera motion**.

### 4.3 Camera Motion: Motion Type + Amplitude + Speed

Add amplitude and speed only when meaningful; medium amplitude and normal speed
are usually omitted.

| Dimension | Expression | Description |
|---|---|---|
| Motion type | `Zoom In / Zoom Out` | Focal length changes, camera body stationary |
| Motion type | `Push In / Pull Out` | The camera moves forward / backward |
| Motion type | `Pan Left / Pan Right` | Camera in place, lens pivots horizontally |
| Motion type | `Truck Left / Truck Right` | The camera translates horizontally |
| Motion type | `Tilt Up / Tilt Down` | Camera in place, lens pivots vertically |
| Motion type | `Pedestal Up / Pedestal Down` | The entire camera moves up / down |
| Motion type | `Arc Shot` | The camera moves in an arc around the subject |
| Motion type | `Tracking Shot` | The camera follows a moving subject |
| Motion type | `Static Shot` | Camera position and lens remain still |
| Motion type | `Shake Slightly / Shake Strongly` | Slight / strong camera shake |
| Motion type | `POV` | The subject's point of view |
| Motion type | `Roll Clockwise / Roll Counterclockwise` | Rolls around the lens axis |
| Amplitude | `with small amplitude` / `with large amplitude` | |
| Speed | `at slow speed` / `at fast speed` | |

Write camera motion as a natural English action within the shot, not stacked as
labels at the end:

```text
The camera pushes in with small amplitude at slow speed toward the folded letter.
The camera pans right with large amplitude at fast speed, revealing the doorway.
The camera holds a static shot as the runner exits the frame.
```

### 4.4 Speakers, Dialogue, and Singing

Subjects who speak, sing, or produce an off-screen human voice use stable IDs
such as `(S1)` and `(S2)`. When multiple numbered speakers speak together, use a
compound ID such as `(S1,S2)`. **A speaker keeps the same ID across shots;
characters who never vocalize receive no speaker ID.**

When a speaker first appears, provide enough information to establish a stable
identity: character type, age, gender, whether on-screen, pitch, timbre, speaking
rate, or accent. **Place the speaker's identifying phrase, ID, action, and
delivery outside `<d>`.** Inside `<d>`, include only the language tag and the
actual spoken content. Preserve every original word and punctuation mark
verbatim; do not translate or rewrite.

```text
The young woman with a quiet, breathy voice (S1) says: <d>[English] I get off at
the next station.</d>
The two children (S1,S2) shout together, <d>[English] Wait for us!</d>
```

For voiceover, use the exact phrase `says in an off-screen voiceover`.
**Immediately after every voiceover `<d>` block, state that the corresponding
on-screen character's lips remain closed:**

```text
The man (S1) says in an off-screen voiceover: <d>[English] I still remember that
road.</d> while his lips remain completely closed.
```

When the same line crosses a cut, use `<scenetrans>` at the connecting points in
both parts and state that the audio continues across the cut. Use `<cutoff>` when
speech is truncated by the end of the video.

### 4.5 On-Screen Text

Place any banner, sign, label, subtitle, or neon text **actually visible on
screen** in English double quotation marks, preserving original text and
punctuation without translation.

```text
A red neon sign reading "营业中" glows above the doorway.
```

### 4.6 `overall_soundscape`

1–4 English sentences in one paragraph summarizing ambient sound, physical action
sounds, and non-verbal human sounds — wind, rain, traffic, footsteps, fabric
movement, impacts, breathing, laughter, panting. Dialogue, singing, and diegetic
music belong in the multimodal description and **should not be repeated here**.
Use `N/A` only when the user explicitly requests complete silence throughout.

### 4.7 `non_diegetic_music`

1–3 English sentences describing background music only the audience hears. Focus
on instrumentation, speed, rhythm, and dynamic changes; **do not use abstract
mood words** or explain emotional function. Singing, instruments, radio,
television, or phone music audible to the characters are diegetic events and
appear in the multimodal description. Use `N/A` when there is none.

## 5. Cases

### Case 2: I2VA

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from
[Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the young
woman shown in <Picture 1> remains beside the rain-covered train window,
preserving her appearance, clothing, seat position, and the carriage layout. The
camera trucks right with small amplitude at slow speed as she lifts her gaze from
the folded letter toward the passing city lights. Her reflection moves across the
glass while the quiet, breathy young woman (S1) says: <d>[English] I get off at
the next station.</d> She folds the letter along its existing crease.

overall_soundscape: The train wheels produce a steady metallic rhythm beneath a
low ventilation hum. Rain ticks against the window while paper rustles softly in
her hands.

non_diegetic_music: Sustained cello notes at a slow tempo with widely spaced piano
tones, gradually decreasing in volume.
```

### Case 3: FL2VA — an eight-second single shot

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1)
aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1)
aligns with the 8.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, a rain-soaked
cyclist begins in the position and framing established by Picture 1, holding a
closed black umbrella beside a silver bicycle. The camera pulls out with small
amplitude at slow speed as she releases the bicycle handle, raises the umbrella
above her shoulder, and presses the runner upward until the canopy opens. Water
rolls from the expanding fabric while she steps beneath it, rotates the handle
into the final angle, and settles into the pose, spacing, and composition
established by Picture 2 at the end of the shot.

overall_soundscape: Rain falls steadily on the pavement, followed by the metallic
click of the umbrella runner and the soft snap of the canopy opening. Water drips
from the bicycle frame as distant traffic passes.

non_diegetic_music: N/A
```

---

## What this project takes from this guide

- **`[Shot N]` marks a cut, not a beat.** A continuous take is one `[Shot 1]`
  with no timestamp. The old `[0-1 s]` bracket notation was never H3's grammar.
- **Dialogue is `<d>[English] …</d>`.** Double quotes mean on-screen lettering.
- **Delivery goes outside `<d>`, before the tag.**
- **Voiceover uses the exact phrase** `says in an off-screen voiceover`, followed
  immediately by a lips-closed statement.
- **Camera uses the controlled vocabulary above**, written as natural English.
