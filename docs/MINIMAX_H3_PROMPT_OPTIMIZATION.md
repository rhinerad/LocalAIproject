# Prompt optimization against the MiniMax H3 guide

Source: **MiniMax H3 Prompting Guide + 44 Video Examples**, Bennett Heyn, fal.ai, last updated 2026-07-30 — <https://fal.ai/learn/devs/minimax-h3-prompting-guide>

**Coverage note.** I read the introduction, the "Three Input Modes" section, and the full "Prompting MiniMax H3: Key Techniques" section, which is where all the actual guidance lives. I sampled but did not read all 44 worked examples in the middle of the page. Nothing below rests on an example I did not read.

One caveat throughout: the guide describes fal's **hosted** endpoints. Equal Shares runs H3 locally in ComfyUI, so endpoint names map to workflow shapes rather than URLs, and the hosted defaults are not binding on a local run. Where that distinction matters I say so.

---

## The headline finding: you are running the model at 29 % of its native short edge

The guide states the native output spec plainly:

> "Every endpoint returns 5 to 15 seconds at 24 FPS in **2K**, which puts **1440 pixels on the short edge** for ratios between 16:9 and 9:16 and reaches roughly **3.7 megapixels** on wider formats."

Equal Shares generates at **736 × 416 — a 416-pixel short edge, 0.31 MP.**

| | Guide's native spec | This project | Ratio |
|---|---|---|---|
| Short edge | 1440 px | 416 px | 29 % |
| Megapixels | ~2.1 at 16:9 (3.7 at 21:9) | 0.31 | ~15 % |
| Frame rate | 24 fps | 24 fps | matches |
| Duration | 5–15 s | 5–15 s | matches |

Everything else about the configuration sits inside the documented envelope. Resolution is the one axis that is far outside it.

This is now the best-supported explanation for the failure that has dominated review — distorted and morphing faces. At 416 px tall, a face in a medium shot is 20 to 30 pixels. The features that make Kent recognisable (mustache, receding hairline, brow) have almost no pixels to live in, and the model fills the gap with a generic face. It also explains the `16A` furniture drift: at this scale the model is failing to hold static set geometry, not just faces.

Two things follow.

**This is the first thing to test in ComfyUI**, ahead of any prompt rewriting. Take one rejected clip — `17C` and `18A` are good candidates, both rejected purely for face failure — and re-render it at a substantially larger size with everything else held constant. If identity holds, resolution was the problem and no amount of prompt work would have fixed it.

**Expect a real cost.** 1440 px short edge is roughly 12× the pixels of 416, so VRAM and time per clip both rise steeply on a 5080. There is likely a usable middle: 1280 × 720 is 2.9× the short edge and 3× the pixels of the current setting. Find the largest size that fits and holds identity, rather than jumping straight to 2K. Whatever you choose, the frame-count rule still applies — round up to the next value congruent to 5 modulo 17.

---

## How the current prompts measure against the eight techniques

Measured across all 124 prompts in `story_config.json`. Median prompt length is **1,361 characters against a 7,000-character budget** — you are using about a fifth of the space available.

| # | Technique | Status |
|---|---|---|
| 1 | Assign a job to every reference | **partial** |
| 2 | Timed shot list for anything longer than one beat | **absent — 0 of 124** |
| 3 | Direct the audio | **done** |
| 4 | State what you do not want | **partial — wrong mechanism** |
| 5 | Lock identity explicitly | **done, and done well** |
| 6 | For edits, name change and constraint together | n/a — not doing edits |
| 7 | Use camera and film language | **absent — 0 of 124** |
| 8 | Describe transitions as events | n/a — you want no transitions |

### 2. No timed shot list — the biggest gap

> "With 7,000 characters to work with and up to 15 seconds of output, you can storyboard inside the prompt. Timecoded blocks work well… MiniMax H3 follows the structure, and **it keeps the pacing from drifting into a slideshow**."

Every prompt carries **dialogue** timing — `[1s-8s] Faith White, calm, looking at Kent: "…"` — and no **visual** timing at all. The picture is described as a single undifferentiated paragraph covering 7 to 15 seconds.

That is very likely why the failures cluster where they do. When the model is given no structure for seconds 4 through 15, it invents one. Look at what it invented:

- `10B` — nothing scripted for seconds 3–15, so it filled the room with eight to ten people.
- `11C` — nothing scripted after the opening beat, so it cut to a new angle at 4 s and put its own name on the counter.
- `12B`, `12C`, `14A` — same shape, jumps between 1 s and 4 s.
- `17A`, `17B`, `18D` — props left undescribed over time, so they morph.

The dialogue timecodes prove the model honours timed blocks; that instruction is being followed. The visual track just is not being given any.

### 4. Negative direction is in the wrong place and the wrong form

The guide's examples are natural-language prohibitions written as sentences: *"No soft dissolves or fluid morphs." "Do not introduce Chinese text, garbled characters, or misspellings." "Do not show giant eyes, split mouths, fangs, threatening behavior, lunges, sudden black frames, or jump scares."*

The project has a 251-character comma-separated keyword list in a separate `negative_prompt` field:

> cruel sneering people, obvious villain, dystopian grime, identity drift, face change, wardrobe change, continuity error, duplicate person, missing person, deformed anatomy, extra limbs, flicker, jump cut, text artifacts, watermark, low quality, blurry

That is Stable-Diffusion-style negative conditioning, not the H3-style in-prompt prohibition the guide describes. Note that your prompts already end with a sentence-form prohibition list — *"No subtitles, captions, visible prompt text, logos, watermarks, identity drift, duplicate people, glass barriers, or Turbo generation"* — which is the right mechanism. It is just short, abstract, and doing less work than it could.

Abstract nouns are weak here. `duplicate person` did not prevent two Kents in `13A`. A sentence would have: *"Exactly one person is in this shot. No second figure appears in the doorway, in a mirror, or anywhere in frame at any time."*

Also worth removing: **"Turbo generation" is not a visual concept.** Every prompt ends by telling the model not to be a Turbo model. It cannot act on that, and it spends tokens in the highest-attention position in the prompt. The Turbo prohibition is a pipeline rule, and it belongs in the config and the docs where it already is — not in the prompt.

### 7. No camera or film language

> "MiniMax H3 reads cinematography vocabulary directly. Lens choice, movement, exposure behavior, and stock character all translate."

Not one of the 124 prompts contains a lens, a camera move, or a framing term. The only camera instruction anywhere is the negative phrase *"one continuous shot with no internal edit."*

That is a prohibition without a positive alternative — you have told the model what not to do with the camera and nothing about what to do. Given the number of rejections caused by the shot jumping, this is a cheap, high-value addition: *"Locked-off camera on a tripod, 50 mm, eye level. The framing does not change at any point. No pan, tilt, zoom, push, or reframe."*

### 1. References have jobs, but only two of them

Your anchors are labelled — *"`<Picture 1>` is the opening visual anchor and `<Picture 2>` is the closing visual anchor"* — which is exactly right for first-and-last-frame work.

What the guide points at is bigger. Reference to Video accepts **up to nine images**, and the technique it calls highest-leverage is giving each one a distinct job. You have `references/alex_vale_master_v1.png` and `references/ensemble_cast_master_v1.png` sitting in the project as authoritative identity sheets, and they are currently used only by humans and by Gemini — they are never passed to H3 at generation time.

If your local workflow can take additional reference images alongside the boundary frames, passing the character sheet as a dedicated identity reference is the single most direct attack on the identity problem: *"Use Image 1 as the opening frame and Image 2 as the closing frame. Use Image 3 only as the identity reference for Kent Brentwood — match his face, hairline, mustache, and build exactly; do not take composition, lighting, or wardrobe from it."*

**Check whether `proven_manual_minimax_h3_api.json` supports extra reference inputs before planning around this.** I have not verified that it does, and changing the graph is a bigger step than changing prompt text.

### 3 and 5 — already good

Audio direction remains specific, but the old suppression rationale is
superseded. Native H3 audio is now the Stage-1 deliverable. Dialogue, ambience,
music cues, and effects must be generated and validated at 0.2 MP before picture
work begins. The accepted full WAV is then referenced during Stage 2 and muxed
unchanged onto the selected picture. For clips whose direction says no music,
keep that lock; the continuous score is one master track across the final edit,
not a new H3 song per clip.

Identity locking is genuinely well done and matches technique 5 closely — named features rather than vague description: *"short dark receding hair, distinctive dark mustache, teal cardigan, cream shirt, charcoal trousers, worn brown shoes, canvas shoulder bag."* Keep this exactly as it is.

One speculative note on audio. The model generates speech natively and has been inventing gibberish dialogue throughout. If it is driving lip movement to match invented speech, that is a plausible contributor to face distortion, and the two problems may be one problem. Your prompts already say *"Keep each speaker's mouth closed outside their assigned line."* Worth testing a fully silent variant — *"No speech, no voices, no vocalisations from anyone in frame at any time. All mouths remain closed."* — on a clip with no scripted dialogue, and seeing whether faces improve.

---

## Revised prompt template

Ordered so the highest-value instructions sit early. Fits comfortably in 7,000 characters.

```
[FORMAT]
{duration} seconds, 16:9, one continuous unbroken take.

[CAMERA]
Locked-off camera on a tripod, {focal length}, {height}. The framing is
identical in the first frame and the last frame. No pan, tilt, zoom, dolly,
push, rack, or reframe at any point. Do not cut. Do not change angle.

[REFERENCES]
Image 1 is the exact opening frame. Image 2 is the exact closing frame.
[Image 3 is the identity reference for {character} — match face, hair,
facial hair and build only; take nothing else from it.]

[CAST — EXACT COUNT]
Exactly {N} people are in this shot for its entire duration: {list them}.
No one else appears at any time. No one enters or leaves frame. No person
appears in a doorway, window, mirror, reflection, or background.

[IDENTITY]
{existing per-character feature lists — keep verbatim}

[SET AND PROPS]
{room, furniture, and their fixed positions}. Every object stays where it
is. {Named prop} keeps the same shape, size, colour, and count for the
whole shot.

[LIGHTING]
{explicit, and bright — see note below}

[SHOT LIST]
[0–2 s] {what the picture does}
[2–5 s] {what the picture does}
[5–{duration} s] {what the picture does}

[DIALOGUE TIMING]
{existing dialogue blocks — keep verbatim}

[AUDIO]
{existing audio suppression line — keep verbatim}

[DO NOT]
No cut, no camera move, no angle change, no dissolve, no morph.
No additional person at any time. No duplicate of any character.
No text, lettering, signage, captions, subtitles, watermarks, or logos
anywhere in frame, including on furniture, walls, screens, and packaging.
No object appearing, disappearing, or changing shape.
No change to any face between the first frame and the last.
```

Two notes on filling it in.

**Lighting.** Write it explicitly and write it bright. The dim interiors are where identity fails — scene 13's night table, scene 16, scene 17 — while the daylight driving clip `14D` is among the cleanest in the film. A dark scene compresses face contrast into a narrow tonal band on top of an already tiny face, and the two effects compound. Keep a scene's mood by all means, but lift the key.

**The text prohibition needs to be that specific.** `11C` put "MiniMAX H3 BRNTWOOD" on the counter front and `12C` wrote "SNS RPJE SR1" on a screen. A generic `text artifacts` did not stop either. Name the surfaces.

---

## Three worked rewrites

Each targets a clip's actual observed failure. Diagnostic first, prompt second.

### `10B` — 15 s, Covenant Hall, invented crowd

Fails from 3 s: a man enters, a body wipes frame, then eight to ten invented men fill the room, several duplicating Faith and Avery. Twelve of fifteen seconds are unscripted.

```
15 seconds, 16:9, one continuous unbroken take.

CAMERA: Locked-off on a tripod, 50 mm, seated eye level, three-quarter
front on the group. Framing is identical at 0 s and at 15 s. No pan, tilt,
zoom, dolly, push, or reframe. Do not cut.

REFERENCES: Image 1 is the exact opening frame. Image 2 is the exact
closing frame.

CAST — EXACT COUNT: Exactly three people are in this shot for its entire
duration: Kent Brentwood seated screen-left, Avery Renfield seated centre,
Faith White seated screen-right. The room is otherwise empty. No fourth
person appears at any time. No one enters through any door. No one is
seated in the background chairs. No one walks through frame. No figure
appears at the edge of frame or crosses in front of the camera.

IDENTITY: Kent Brentwood — short dark receding hair, distinctive dark
mustache, teal cardigan, cream shirt, charcoal trousers, worn brown shoes,
canvas shoulder bag. Avery Renfield — clean-cut salt-and-pepper hair, navy
jacket, pale blue shirt. Faith White — older, grey-bearded, sand-coloured
collarless coat with a woven circular emblem. All three keep the same face,
hair, and clothing from the first frame to the last.

SET: Covenant Hall. Three wooden chairs in a shallow arc. A woven circular
emblem on the wall behind. Low shelving screen-right. The empty background
chairs stay empty and stay where they are. No furniture moves.

LIGHTING: Warm, even, generously lit interior. Faces are clearly and
evenly exposed for the whole shot. No pools of shadow across any face.

SHOT LIST:
[0–2 s]  All three seated and still. Faith turns her head toward Kent.
[2–8 s]  Faith speaks to Kent, hands resting in her lap. Kent listens,
         still. Avery listens, still. Nobody stands. Nobody moves position.
[8–14 s] Faith turns her head from Kent to Avery and speaks to Avery.
         Kent lowers his eyes. Avery meets her look. All three stay seated.
[14–15 s] All three settle into stillness, holding the closing frame.

DIALOGUE TIMING: [1s-8s] Faith White, calm, looking at Kent: "Kent, you
should not wound the brother who tries to ease financial suffering by
refusing the help." [8s-14s] Faith White, turning to Avery: "But Avery,
accepting someone's limits can also be a loving act."

AUDIO: Quiet natural room ambience and small clothing movement only. No
music, song, score, underscore, sting, motif, or transition cue.

DO NOT: No fourth person. No duplicate of Kent, Avery, or Faith. No one
entering or leaving. No cut, camera move, or angle change. No text,
lettering, signage, captions, or watermarks anywhere in frame. No face
changing between the first and last frame. No furniture moving.
```

### `11C` — 12 s, mutual-aid counter, model name on the set

First three seconds are clean and usable. At 4 s it cuts to a wide angle and the counter front reads "MiniMAX H3 BRNTWOOD".

Two independent fixes. Kill the cut with camera language and a shot list; kill the lettering by naming the surface rather than saying "text artifacts". Add:

```
CAMERA: Locked-off on a tripod, 50 mm, chest height, tight two-shot across
the counter. This framing holds for all 12 seconds. Never widen. Never cut
to another angle.

SET: The counter front is plain, unmarked wood. There is no lettering,
logo, signage, sticker, price card, or printed text on the counter, on the
walls, on the shelving, on any packaging, or on the terminal screen. Every
visible surface is blank.

SHOT LIST:
[0–3 s]  The volunteer gestures toward the terminal, speaking to Kent.
[3–8 s]  Kent lowers the mug slightly and answers. The volunteer listens.
         The framing does not change.
[8–12 s] Both settle. Kent glances at the grocery box, still on the
         counter where it began.
```

Also worth trying first, since it is nearly free: `11C`'s opening three seconds are good. A 3-second version off the same anchor may simply pass, and shortening is rung three on the salvage ladder.

### `17A` — 8 s, bills change mid-clip

Prop instability. Nothing in the prompt describes what the bills are, how many there are, or that they must stay the same.

```
PROPS — FIXED: Kent handles exactly {N} paper bills, each the same size,
colour, and design as in the opening frame. The count never changes. No
bill is added, removed, or swapped. Their printed detail stays identical
throughout — the same denomination, the same markings, the same wear.
The papers on the table stay in the same positions and keep the same
appearance for all 8 seconds.

SHOT LIST:
[0–3 s]  Kent looks down at the bills, counting slowly.
[3–6 s]  He moves one bill from the left group to the right. The rest do
         not move.
[6–8 s]  He stops, hand resting on the table, looking at the total.

DO NOT: No bill changing denomination, design, colour, or size. No bill
appearing or disappearing. No text on any bill changing between frames.
```

---

## What to leave alone

- **Identity feature lists.** Already exactly what technique 5 asks for.
- **Audio suppression.** Already specific and correctly aimed.
- **Dialogue timecodes.** Already in the format the guide recommends, and demonstrably obeyed.
- **20 steps, `res_multistep` / `simple`, denoise 1.0, non-Turbo, 24 fps, the frame-count rule.** Nothing in the guide touches these, and they are project invariants.

## What to change, in order

1. **Raise the resolution and measure.** One clip, everything else held constant. This is a settings change, not a prompt change, and it plausibly dominates everything else on this list.
2. **Light the interiors properly.** Also cheap, also testable on one clip.
3. **Add a camera block and a visual shot list to every prompt.** The largest prompt-side gap, and it targets the cut and drift failures directly.
4. **Convert prohibitions to specific sentences and name the surfaces.** Drop "Turbo generation" from the prompt text.
5. **State the exact cast count positively in every multi-person clip.**
6. **Investigate passing the character sheet as an identity reference** — but check the API graph supports it first.

Items 3 through 5 can be applied mechanically to all 124 prompts from the existing `action`, `duration`, and character fields. That is a scripted rewrite of `story_config.json` and should be done as a separate, reviewable pass with a backup, not by hand.
