# AGENT DIRECTIVE: BACKROOMS SITCOM PIPELINE EXECUTION (REVISED TIMELINE)

Task: Manage and execute the 102-clip (17-minute) generative video pipeline for the "Backrooms Sitcom Audition" project via ComfyUI (Port 8188) and MiniMax/Flux nodes.

---

## 0. EXECUTION NOTES FOR THE AGENT — READ THIS FIRST

- **Chaining tool status:** automatic last-frame chaining (`--start-frame-path` forwarded clip-to-clip) may or may not be wired into the batch pipeline yet, depending on whether that fix has landed. Check first. If it has: use it directly, as described in Section 1. If it has not: replicate it manually — after each video clip finishes, call `video_frames` on the finished clip to pull its final frame, then use `render_story_image` with `mode: "i2i"`, that frame as `reference_name`, and an appropriate `denoise` (see Section 1) to produce the next clip's start reference. **Do not silently fall back to generating an independent fresh still for every clip if the automatic path is missing** — that defeats the entire point of this directive and is the one failure mode to actively avoid.
- **This document is a directive, not a literal 102-block prompt pack.** It does not contain individually authored `Cxxx — START FRAME IMAGE / LAST FRAME IMAGE / VIDEO PROMPT` sections for all 102 clips the way a fully-expanded pack file would. If your ingestion tool expects that literal format and rejects this document (a "no clip prompts parsed" style error), do not force it through that path — that tool is a mechanical text splitter, not an interpreter of scene-level direction. Instead, work clip-by-clip yourself: derive each clip's individual prompts from the scene description, chaining rule, and reference images below, and drive still/video generation directly through the available render tools. Confirm which execution path applies before starting a full run, rather than assuming.
- **Stills approval gate stays in force.** Whatever path you use, do not begin video submission for a scene until its stills have been generated and reviewed/approved per the normal gate — that gate exists for a reason and nothing here overrides it.

---

## 1. PIPELINE EXECUTION & CHAINED GENERATION RULES

- **Chained Scene Pipeline:** Do NOT generate a fresh Flux still image for every single clip. Generate a scene-start Flux reference image ONLY at the 7 major architectural transitions listed in Section 2. For every sequential clip within the same environment, extract the last frame of video clip N (`clip_0xx_last.png`) and use it as the start reference for video clip N+1 — via the automatic chaining path if available, or manually per the note in Section 0 if not.
- **Mid-scene refine checkpoint (drift/artifact reset):** several of the chained sequences below run 12-17 clips deep before the next scene-start image (notably C001–C014, C017–C030, and C079–C095). Chaining that many clips in a row off raw extracted video frames compounds compression artifacts and slow visual drift. Every **10 consecutively chained clips** within a single scene, instead of a plain passthrough chain, run a **refine pass**: take the extracted last frame, regenerate it via `render_story_image` in `mode: "i2i"` at a **low denoise (0.20-0.35)**, conditioned on that scene's own LoRA and prompt, then use *that* cleaned-up frame as the next start reference and reset the chain counter. This is not a fresh independent still (it would break continuity) and not a plain upscale (it won't correct color drift or identity wander) — it's a light regeneration of the actual frame you already have. Treat the denoise value as tunable: low enough to preserve pose/composition/identity, high enough to actually clean up softness. If in doubt, test one frame at 0.25 before committing to a full scene.
- **Camera-Free Flux Prompting:** Flux prompt descriptions must describe ONLY subject, posture, room geometry, lighting, and textures. Strictly omit all optical meta-terms (camcorder, camera, tripod, framing, lens, viewfinder, aspect ratio, handheld shake, motion smear, autofocus, tape damage) to prevent Flux from baking physical cameras or optical overlays into reference frames.
- **Video Kinetics & Artifacts:** Reserve all motion physics, tape hiss, VHS softness, autofocus hunting, exposure pumping, and the lower-right digital timestamp `AUG 09 1998` exclusively for the MiniMax video prompt blocks.
- **Universal Artifact Negative Prompt (apply to all Flux/MiniMax generation steps, including refine-checkpoint passes):**
  no extra limbs, fused fingers, melted hands, face change, costume change, duplicate actor, duplicate entity, floating objects, disappearing objects, warped perspective, crawling wallpaper patterns, duplicated ceiling lights, impossible shadows, unstable geometry, texture swimming, frame tearing, accidental jump cut, random room change, subtitles, captions, watermark, logo, readable text, glossy digital cinema, cartoon style, excessive fog, gore, blood

---

## 2. 17-MINUTE RUNTIME & 8-BLOCK SCENE PACING ARCHITECTURE

| Phase | Clip Range | Chain Length | Runtime Window | Environment & Narrative Focus | Generation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Act I: The Audition** | C001–C014 | 14 clips | 0:00 – 2:40 | Modest apartment living room audition space for *Wacky Roommates* (Character: Leo). | **Scene Start Image 1** (Apartment); refine checkpoint after C010 |
| **Act I: The Fall & Arrival** | C015–C016 | 2 clips | 2:40 – 3:00 | Sudden floor collapse into damp brown-beige carpet and sickly yellow wallpaper. | Chained fall sequence |
| **Act II: Quiet Exploration & Loop** | C017–C030 | 14 clips | 3:00 – 5:20 | Level 0 narrow corridors. Pure slow-burn atmosphere: fluorescent hum, wall pen-marks shifting position, total isolation. | Chained wandering sequence; refine checkpoint after C026 |
| **Act II: Scene A — Wall Melding Objects** | C031–C042 | 12 clips | 5:20 – 7:20 | Discovering real-world 1980s artifacts (an old skateboard, an electric guitar, a flannel shirt) half-fused and warped directly into the yellow wallpaper. | **Scene Start Image 2** (Wall Objects); refine checkpoint after C040 |
| **Act II: The Pillared Hall** | C043–C052 | 10 clips | 7:20 – 9:00 | Expansive open office spaces with heavy concrete structural pillars and long sightlines. | **Scene Start Image 3** (Pillared Hall) |
| **Act II: Scene C — The Surreal Indoor Seattle Park** | C053–C064 | 12 clips | 9:00 – 11:00 | Finding an indoor space mimicking an outdoor Seattle urban park under concrete ceilings, eerie green lighting, sun-orange bark, and inverted color palettes. | **Scene Start Image 4** (Indoor Park); refine checkpoint after C062 |
| **Act II: Scene B — The Water Break & Exhaustion** | C065–C074 | 10 clips | 11:00 – 12:40 | Finding a mystery water puddle; Leo sets down the camera with immense relief to drink and wash his face after nearly 8 hours of walking. | **Scene Start Image 5** (Water Break) |
| **Act III: The Entity Reveal & Awakening** | C075–C078 | 4 clips | 12:40 – 13:20 | **Minute 12+ Mark:** Static reset brings Leo face-to-face with the tall, thin entity standing silently down the hall. | **Scene Start Image 6** (Encounter Chamber) |
| **Act III: The Mirroring Game** | C079–C095 | 17 clips | 13:20 – 16:10 | Wide carpeted chamber. Horror pivots into surreal absurdist physical comedy as the entity mimics every awkward gesture and dance move. | Chained mirroring routine; refine checkpoint after C088 and after C097 (see note) |
| **Act III: The Twist & Resolution** | C096–C102 | 7 clips | 16:10 – 17:00 | Final close confrontation, unprompted head movement, and dialogue break ending on *"What's weird?"*. | Chained final cut |

*Note: C079–C095 runs 17 clips deep, past the 10-clip refine threshold once. Insert one refine checkpoint mid-scene (around C088) rather than skipping it just because the scene ends before a second threshold would hit.*

---

## 3. SCENE-START FLUX REFERENCE PROMPTS (7 KEY GENERATION POINTS)

### Scene Start Image 1: Apartment Audition (Clips C001–C014)
- **Positive:** Wide interior view of a modest apartment living room converted into a makeshift audition space for a sitcom casting tape. An adult male actor in his late 20s, portraying the character Leo, with short messy dark hair, a faint five-o'clock shadow, olive-green overshirt over a faded gray T-shirt, and dark jeans stands centered on a taped floor mark. Warm domestic lamp lighting from the side and a flat ceiling light illuminate the room, with ordinary household clutter and script pages visible on a small chair.
- **Negative:** [Use Universal Artifact Negative Prompt]

### Scene Start Image 2: Scene A — Wall Melding Objects (Clips C031–C042)
- **Positive:** Medium-angle interior view of a Backrooms corridor where ordinary real-world items — an old 1980s skateboard, a wooden electric guitar, and a plaid flannel shirt — are half-fused and warped directly into the sickly yellow patterned wallpaper like melted wax. The adult male actor stands staring at the wall in stunned disbelief under harsh rectangular fluorescent ceiling tiles.
- **Required LoRA:** `A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)_(SDXL)_(AD).safetensors` (Strength: 0.70)
- **Negative:** [Use Universal Artifact Negative Prompt]

### Scene Start Image 3: The Pillared Hall (Clips C043–C052)
- **Positive:** Wide architectural view of an enormous, empty open-plan office space inside Level 0. Heavy industrial concrete structural pillars stretch into the distance under a low grid of rectangular fluorescent ceiling fixtures emitting harsh yellow light. The floor is covered in damp, stained brown-beige patterned office carpet. The adult male actor stands small in the frame near a pillar, looking cautiously down long sightlines bordered by repetitive sickly yellow patterned wallpaper walls with no windows.
- **Required LoRA:** `A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)_(SDXL)_(AD).safetensors` (Strength: 0.65)
- **Negative:** [Use Universal Artifact Negative Prompt]

### Scene Start Image 4: Scene C — The Surreal Indoor Seattle Park (Clips C053–C064)
- **Positive:** Wide interior view of a surreal indoor park space imitating an outdoor urban park, enclosed entirely under low concrete and fluorescent grid ceilings. The artificial lighting casts an eerie green glow, tree trunks have glowing sun-orange bark, and surrounding foliage colors are inverted and incorrect. The adult male actor stands on a gravel path, reacting with bewildered awe.
- **Required LoRA:** `A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)_(SDXL)_(AD).safetensors` (Strength: 0.75)
- **Negative:** [Use Universal Artifact Negative Prompt]

### Scene Start Image 5: Scene B — The Water Break (Clips C065–C074)
- **Positive:** Low-angle interior view of a damp Backrooms corridor where a shallow, clear puddle of mystery water sits on the stained brown-beige patterned office carpet. The adult male actor is visible kneeling on the floor with immense physical relief, washing his face and scooping water to drink, looking exhausted from hours of walking.
- **Required LoRA:** `A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)_(SDXL)_(AD).safetensors` (Strength: 0.70)
- **Negative:** [Use Universal Artifact Negative Prompt]

### Scene Start Image 6: The Encounter & Mirroring Chamber (Clips C075–C102)
- **Positive:** Wide interior view of an open-plan carpeted chamber in the Backrooms. Damp brown-beige patterned carpet covers the floor, enclosed by endless walls of sickly yellow patterned wallpaper under a uniform grid of rectangular fluorescent ceiling fixtures. The adult male actor stands frozen in the foreground, staring down the corridor where a very tall, extremely thin humanoid silhouette stands motionless in the middle distance under the humming lights.
- **Required LoRA:** `A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)_(SDXL)_(AD).safetensors` (Strength: 0.70)
- **Negative:** [Use Universal Artifact Negative Prompt]
