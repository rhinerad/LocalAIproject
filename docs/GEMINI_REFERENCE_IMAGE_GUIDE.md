# Gemini Reference-Image Fallback Guide

Use Gemini image generation only when the required first or last frame cannot be produced reliably through prompt variation, seed changes, 20-step retries, shorter clips, clean cuts, frame holds, or editing with existing approved frames.

Also read `archive/superseded_docs/TECHNICAL_OPERATIONS.md` so the new frame follows the same production and validation workflow ChatGPT/Codex used.

Do not casually regenerate images. Never replace a working approved reference merely to make it prettier.

## Required sources

All required assets are already inside this handoff folder.

### Main character

- `outputs/equal_shares/references/alex_vale_master_v1.png`
- `outputs/equal_shares/references/alex_vale_source.jpg`

These are the authoritative identity references for **Kent Brentwood**, the main character based on the user. Preserve his exact recognizable face, short dark receding hair, neat dark mustache, prominent brows, expressive brown eyes, gently rounded face, and average build.

Kent's default wardrobe is a faded teal cardigan, cream button-up shirt, charcoal trousers, worn brown shoes, and canvas shoulder bag.

### Ensemble character sheet

- `outputs/equal_shares/references/ensemble_cast_master_v1.png`

The five people appear from left to right in this exact order:

1. **Kent Brentwood** — teal cardigan, cream shirt, canvas bag, mustache.
2. **Avery Renfield** — Kent's financially secure older brother; navy coat, pale blue shirt.
3. **Doris Lovelay** — elderly mother; silver curls, lavender robe, cream knitted shawl.
4. **Ryann Sally** — South Asian solicitor; rectangular glasses, black hair in a low bun, burgundy suit, ivory blouse.
5. **Faith White** — older gray-bearded Covenant teacher; sand-colored collarless coat with a circular woven emblem.

The actual faces and clothing visible in this sheet override conflicting prose descriptions. Do not exchange identities, ethnicity, age, wardrobe, or roles.

### Narrator and opening cast

- `outputs/equal_shares/frames/scene_000/boundary_00.png`
- `outputs/equal_shares/frames/scene_000/boundary_05.png`
- `outputs/equal_shares/frames/scene_000/boundary_narrator_close_v3.png`
- Other approved `scene_000` boundary frames in the same folder

The Narrator is a distinct man in his late fifties with a lean face, neatly combed dark-gray hair, dark 1960s suit, white shirt, and narrow black tie. He must never resemble Kent.

Opening continuity is absolute:

- one female receptionist, always behind the staff-only window;
- exactly two male visitors perform the chair interaction;
- both men enter through the separate doorway and remain on the public side;
- one public chair at screen-left;
- no glass gate, fence, divider, extra chair, third man, or role swap.

### Scene and composition continuity

For the specific clip, consult:

- `outputs/equal_shares/story_config.json`
- `outputs/equal_shares/shot_plan.json`
- `outputs/equal_shares/story_bible.json`
- the relevant `outputs/equal_shares/frames/scene_###/` folder;
- `scene_###_review_sheet.jpg` in that folder;
- the neighboring approved first and last boundary frames;
- the last accepted video frame from the preceding clip when applicable.

The configured frame path for the affected clip is authoritative. Do not guess the scene number or substitute a visually similar location.

## Gemini procedure

Before asking Gemini to make an image:

1. Identify the exact clip ID and whether the missing asset is its first frame, last frame, or both.
2. Read that clip's complete action, prompt, negative prompt, continuity rules, character list, first-frame path, and last-frame path from `story_config.json`.
3. Inspect the existing neighboring frames and scene review sheet.
4. Upload only the relevant identity references plus the closest approved scene frame. For Kent, always include `alex_vale_master_v1.png`. For another named principal, include `ensemble_cast_master_v1.png` and explicitly identify the correct left-to-right person.
5. Tell Gemini that the uploaded identities and scene geography are mandatory references, not loose inspiration.
6. Request a single photorealistic 16:9 cinematic still with the exact composition required by the clip.
7. Require no text, captions, logos, watermarks, split panels, collages, duplicated people, extra limbs, malformed hands, glass barriers, or unintended props.
8. Save every Gemini result as a new version. Never overwrite an approved reference.
9. Inspect the result manually before placing its path into `story_config.json`.
10. Run the config check and generate only the affected clip. Do not regenerate unrelated approved clips.

## Reusable Gemini prompt template

```text
Create one photorealistic 16:9 cinematic reference frame for the Equal Shares film.

CLIP: [clip ID]
FRAME PURPOSE: [first frame or last frame]

The uploaded character and scene images are mandatory continuity references. Match the exact faces, apparent ages, hair, facial hair, body types, wardrobe, props, architecture, lighting, color palette, and screen direction. Do not reinterpret or redesign anyone.

CHARACTERS PRESENT:
[List only the characters who must appear. Identify their position in the ensemble sheet.]

EXACT COMPOSITION AND ACTION STATE:
[Describe the single frozen moment required by story_config.json. State where every person, hand, prop, doorway, chair, desk, and important object is positioned.]

CONTINUITY WITH NEIGHBORING FRAME:
[Describe what must remain unchanged from the closest approved boundary frame.]

STYLE:
Restrained near-future social realism, natural faces and anatomy, warm pastel civic design, subtle Twilight Zone unease, humane rather than cynical, cinematic but believable. Use black-and-white 1960s anthology television realism only for the opening waiting-room sequence.

ABSOLUTE EXCLUSIONS:
No extra people, duplicate person, identity drift, face change, altered mustache, wardrobe change, role swap, deformed anatomy, extra fingers or limbs, merged bodies, malformed hands, glass gate, glass fence, invented divider, captions, labels, visible text, logo, watermark, split screen, collage, or unrelated background action.

Return exactly one finished frame, not a character sheet or explanation.
```

## Acceptance gate

Reject the Gemini image if any character does not match the correct sheet, if the number or position of people is wrong, if hands or anatomy are malformed, if architecture or props drift, or if it contradicts the neighboring boundary frame. A generated frame is not approved merely because it looks attractive.

Record the reason for generating it, the uploaded references, the prompt, result path, and acceptance decision in the project notes and `archive/superseded_docs/HANDOFF.md`.
