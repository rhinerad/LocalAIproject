# Backrooms Sitcom Audition Prompt Pack — CORRECTED CAMERA LOGIC — 2026-09-08

Corrects: A:\Users\rhine\.codex\attachments\7a6a1cac-a5cb-4e78-8ad4-beab1bea0e7a\pasted-text.txt (rewritten 2026-09-07T19:03:03)

## What was broken

The original pack asserted a single, absolute rule for every post-fall clip: the camcorder is handheld by the actor, POV-locked, no selfie angle, no third-person observer shot. But roughly 60 of the 102 clips then described the actor in full third-person body shots — "Actor stands, holding the camcorder at chest height," "actor and entity facing each other," an entire 25-clip mirroring/dance sequence (C077–C102) showing both characters side by side. A camera the actor is holding and looking through cannot also show him "holding the camcorder" or standing across a room from the entity he's supposedly filming through it. SDXL doesn't reconcile that — it paints whatever the sentence says, so you'd get an unpredictable mix of true POV frames and ordinary third-person frames with no consistent visual grammar, and reference-image continuity would break down clip to clip.

## The fix: three camera modes instead of one absolute rule

This is the actual convention found-footage films use (Blair Witch, REC, Grave Encounters, Cloverfield) to solve exactly this problem — the camera is diegetic throughout, but it is not always in the actor's hand.

**MODE A — Tripod (C001–C014).** Unchanged from the original. Fixed camcorder on a tripod in the apartment. Actor fully visible, ordinary third-person composition. No lore/logic issue here — this mode was already internally consistent in the original pack.

**MODE B — Handheld POV (solo locomotion: walking, exploring, listening, running, being chased, alone in a corridor).** The camera is in the actor's hand, held roughly at chest or eye height, pointed forward. The actor is **never shown as a body** in this mode — only his hand/forearm/sleeve entering frame at the bottom or side edge when he reaches for something, his shadow cast on the wall or carpet, and his breathing/footsteps on the audio track. Any original line that said "Actor walks / stands / kneels / turns / looks" is rewritten to describe what the *view* shows (forward corridor, wall, carpet, entity glimpse) rather than describing his body.

**MODE C — Propped / Set-Down (entity interaction: confrontation, mirroring, dialogue, the recovery scene).** The story needs two-shots of the actor and the entity together, and the original pack's own creative content depends on this (the whole mirroring arc is built on watching both of them at once). Rather than fight that, the story now has the actor explicitly set the camcorder down, wedge it in debris, or lean it against a wall/pillar during these scenes — the camera keeps rolling from a stable fixed position, same as the tripod convention but now diegetically justified inside the Backrooms. This yields ordinary third-person coverage that is still 100% diegetic (nothing outside the story's camcorder ever provides a shot) and doesn't require an outside "film camera," which is what the original rule was actually trying to prohibit.

**FALL (C015 only).** Transitional. The camera is not yet handheld or propped — it's tumbling with the actor mid-fall. Kept close to the original description (violent rotation, muffled impact) since that one was already coherent.

## Corrected Editor Override — Rule 4 (replaces the original "Diegetic Camera Lock")

> **4. Diegetic Camera Lock — Three Modes.** The viewer sees only through the story's physical camcorder, in one of three states, never an outside film camera, drone, gimbal, or omniscient view.
> - *Mode A (C001–C014):* tripod-mounted, static, actor fully visible — ordinary third-person audition framing.
> - *Mode B (solo post-fall movement):* handheld by the actor, forward-facing. Do not depict the actor's face, torso, or full body. Show only his hand/forearm/sleeve at frame edge when he reaches for or touches something, his shadow, and the environment ahead of him. No selfie angle.
> - *Mode C (entity interaction/two-shots):* the camcorder has been deliberately set on the floor, wedged against a wall, or propped on debris by the actor, in-story, before the scene begins. From that point the frame is stable found-footage coverage that can include both the actor and the entity, exactly like a tripod shot, until the story has him pick the camera back up.
> Every still and video prompt in this pack is tagged with its mode below. Do not mix modes within a single clip.

## Corrected Global Camera Rule (replaces the header's single rule)

> Diegetic camcorder POV lock, three states as defined in Editor Override Rule 4 above. Mode is fixed per clip by the Camera Mode column in the tables below — do not infer mode from the action description alone, since ambiguous phrasing was the source of the original contradiction.

## Unchanged from the original pack

These parts had no logic problem and are carried over exactly as written — see the original document for full text, not reproduced here to avoid duplicating ~2,000 lines that don't need to change:

- Rule 1 (Separate Still Images From Motion), Rule 2 (Protect the Apartment Opening), Rule 3 (Backrooms Environment After the Fall), Rule 5 (Clean MiniMax Handoffs), Rule 6 (Static Cut Exception, C069), Rule 7 (Continuity Workflow), Rule 8 (Universal Artifact Negative Prompt).
- The Backrooms SDXL LoRA rule and file path.
- The MiniMax video-prompt format rule.
- The universal negative prompt block (append to every still and video prompt, unchanged).
- The Character Bible (actor, entity, camera physical descriptions).
- The Backrooms lore basis and sourcing in the Appendix — this was already reasonably careful (hedged as community-wiki canon, not asserted as universal fact) and needs no change.
- Story Rules, Dialogue Tone for the friendly entity, Generation Notes for C069's static cut.
- All C001–C014 (Mode A, apartment) still and video prompts — already internally consistent, use as originally written.

## Camera Mode Table — all 102 clips

| Clips | Mode | Why |
|---|---|---|
| C001–C014 | A (tripod) | Apartment audition — unchanged |
| C015 | FALL | Transitional tumble |
| C016–C062 | B (handheld POV) | Solo exploration, wallpaper investigation, corridor walking, entity glimpsed only in background/periphery, the chase |
| C063–C071 | C (propped) | Cornered confrontation and the C069 static-cut attack — camera is knocked from his hand or set down at the moment of contact, consistent with C069's existing "static cut" exception |
| C072–C076 | C (propped) | Recovery on the floor, actor sits up, entity visible nearby — needs both in frame |
| C077–C102 | C (propped) | Full mirroring/dance/wave sequence — inherently a two-shot arc, camera has been left propped since C072 |

## Patched still-image action lines (Mode B, C016–C062)

Only the lines that described a visible actor body are rewritten below. Everything else in those clips (filename, boilerplate horror-comedy sensory language, negative prompt, continuity anchors, LoRA instruction) stays as in the original pack — only the bolded action sentence at the end of each positive prompt changes.

| Clip | Frame | Original (contradicts Mode B) | Corrected (Mode B — hand/POV only) |
|---|---|---|---|
| C017 | start | "Actor kneels on unfamiliar damp carpet, camera low and tilted." | "View drops low and tilts as a hand presses into unfamiliar damp carpet at the bottom of frame." |
| C019 | start | "Actor stands, holding the camcorder at chest height, empty yellow room behind him." | "View holds steady at chest height, forward-facing into an empty yellow room; only a sleeve cuff visible at the frame's lower edge." |
| C020 | last | "Actor steps into the center opening." | "View advances into the center opening, footsteps and breathing audible, walls closing in on either side." |
| C021 | start | "Actor walking through a narrow yellow corridor, camera held low and shaky." | "View moves forward low and shaky through a narrow yellow corridor, floor and wallpaper filling the frame." |
| C023 | start | "Actor faces the camera while walking backward, trying to explain the situation." | "View faces backward down the corridor while moving forward, only a hand gesturing into frame as he talks." |
| C023 | last | "He nearly trips on the damp carpet and catches himself." | "The frame lurches downward and catches itself as a hand slaps against the wall for balance." |
| C032 | start | "Actor walking faster, camera bouncing slightly." | "View bounces forward at a faster pace, corridor walls streaking slightly at the edges." |
| C036 | last | "Actor raises the camera and walks backward away from the darkness." | "View rises and retreats backward away from the darkness, a hand briefly crossing frame to steady it." |
| C041 | start | "Actor moving through a wider yellow room with several pillars." | "View moves forward through a wider yellow room, pillars passing left and right of frame." |
| C043 | start | "Actor walking quickly through the pillar room." | "View moves quickly forward through the pillar room, breathing sharp on the audio track." |
| C046 | start | "Actor backs into a wall, camera shaking." | "View backs into a wall, image shaking hard, a shoulder briefly visible at the frame edge." |
| C046 | last | "His hand covers part of the lens while he tries to control his breathing." | "A hand partially covers the lens; the image dims at one edge while breathing is audible." |
| C051 | start | "Actor moving quickly through a corridor, camera bouncing." | "View moves quickly forward through a corridor, image bouncing hard with each footfall." |
| C052 | start | "Actor runs around a corner." | "View swings hard around a corner, wall blurring past at the edge of frame." |
| C053 | start | "Actor running through a room with low pillars." | "View runs forward through a room with low pillars, ceiling scraping close overhead." |
| C054 | start | "Actor glances over his shoulder while running." | "View jerks backward briefly mid-run, corridor behind reduced to a blur, then snaps forward again." |
| C054 | last | "His face fills the frame, terrified and out of breath." | "The frame lurches close to a wall, breath ragged and loud on the audio track, image briefly out of focus." |
| C055 | start | "Actor running directly toward a distant opening." | "View runs directly toward a distant opening, growing larger in frame." |
| C057 | start | "Actor turns and runs back the way he came." | "View whips around and runs back the way it came, the corridor reversing hard." |
| C058 | start | "Camera points low at the wet carpet while running." | (already Mode B compatible — no change needed) |
| C058 | last | "Actor's hand reaches into frame to steady the camera." | (already Mode B compatible — no change needed) |

Clips not listed above in the C016–C062 range (e.g., C016, C018, C022, C024–C031, C033–C040, C042, C044–C045, C047–C050, C056, C059–C062) already describe hands, environment, or the entity rather than the actor's own body, and are Mode-B-compatible as originally written — no change needed to those action lines.

## Patched still-image action lines (Mode C, C063–C102)

These clips are unchanged in wording (they already describe both the actor and the entity, which is what Mode C is for) — the fix here is not to the action line but to the added **framing note**, inserted once at the front of each Mode C clip's positive prompt in place of the Mode B "handheld" language:

> "Camcorder resting where it was set down, wedged against a wall, or braced on debris — a stable, non-handheld found-footage frame, no tripod visible, no outside camera."

Apply that framing note to every still and video prompt from C063 through C102 in place of the original "handheld by the actor from his real position" line. Everything else — the entity's posture, the actor's dialogue, the mirroring choreography, the negative prompt, the continuity anchors, the LoRA instruction — stays exactly as originally written.

## Patched video-prompt (Section 2) lines

The video prompts inherit whatever mode their stills use, so the same patch logic applies. Two additional video-specific fixes:

| Clip | Original video line | Corrected |
|---|---|---|
| C016 | "Camera lies on the floor. The actor groans and crawls into frame." | Reclassify as the start of Mode C early — the camera has been dropped, not handheld. Keep this line as written; it's already third-person-consistent with a dropped camera, just relabel its mode from B to "C (dropped)" rather than "B (handheld)." |
| C011 (Mode A, apartment) | "Actor decides to review the footage. He walks toward the camera casually" | No change — this is Mode A (tripod), where third-person is correct and intended. |
| C017 video | "Actor slowly realizes the room is wrong... touches the wallpaper" | "A hand touches the wallpaper at the edge of frame; view holds on the texture as breathing catches." |
| C018 video | "Actor notices wall is damp" | "View lingers on a damp patch on the wall as a hand presses into it, breath audible." |

All other video prompts from C016–C062 (Mode B) should have their opening `integrated_multimodal_description` sentence changed from *"the actor's handheld camcorder view from his real position, height, grip, stumble, and turn"* to: *"the actor's handheld camcorder view — hands, environment, and forward motion only; the actor's face and body are never shown"* — this single find-and-replace across those ~46 clips removes the ambiguity that caused the original contradiction, without needing to touch each clip's dialogue or entity-behavior content, which was already fine.

All video prompts from C063–C102 (Mode C) should have that same sentence changed to: *"the camcorder resting where it was set down or propped — stable found-footage coverage of both the actor and the entity, no handheld motion, no tripod visible."*

## Assembly note addition

Add to the Appendix's "Minimax Assembly Notes": *"Confirm each clip's Camera Mode (A / B / C / FALL) from the table above before rendering. Mode B stills must not contain the actor's face or torso — reject and regenerate any Mode B still that does. Mode C stills should show a static, non-shaky frame consistent with a propped camera, not handheld motion blur."*

## Why this is now lore-consistent

Nothing above changes the Backrooms environment description, the entity design, the story beats, or the sourcing in the Appendix — those were already reasonably solid (yellow Level-0 wallpaper, damp carpet, fluorescent maze geometry, hedged sourcing to the Wikidot FAQ and Level 0 page). The only thing that was broken was the camera-logic layer sitting on top of the story, and that's now internally consistent end to end: every clip has exactly one unambiguous camera state, the found-footage conceit is preserved throughout (nothing is ever shot by an outside camera), and the propped-camera device is a standard, audience-legible found-footage convention rather than an invented exception.
