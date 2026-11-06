# Open Interpreter Continuation — Equal Shares

Checkpoint captured: **August 10, 2026, approximately 12:46 AM Eastern**.

## Begin here

Continue the project from this canonical handoff folder. Before changing anything, read:

1. `HANDOFF.md`
2. `SYNC_STATUS.json`
3. `outputs/equal_shares/story_config.json`
4. `outputs/equal_shares/manifest.json`
5. `outputs/equal_shares/visual_audit.json`
6. `outputs/equal_shares/generation_audit.json`
7. `outputs/equal_shares/completion_audit.json`
8. `GEMINI_REFERENCE_IMAGE_GUIDE.md`
9. `TECHNICAL_OPERATIONS.md`

Treat those files and the current local machine state as authoritative.

## Exact checkpoint

- Configured clips: **124**
- Visually reviewed and accepted: **40**
- Unresolved: **84**
- Current/next unresolved clip: **09A**
- `08C` completed and passed visual review. `09A` was starting when the final checkpoint was captured.
- Both single-anchor and dual-anchor generations now use **20 steps**.
- Full-quality model: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- Never use MiniMax Turbo, Turbo nodes, or Turbo LoRAs.
- Current completion audit is incomplete, as expected: the project is only partially rendered and no final master exists yet.
- All selected raw chunks and assembly copies are presently accounted for.
- Shared raw-attempt count at the last audit: **70**.

## Do not duplicate active work

Inspect running processes, `outputs/equal_shares/runtime/render_supervisor.log`, and ComfyUI port 8188 before launching anything. The existing supervisor, ComfyUI backend, runner, finalizer, and handoff synchronizer may still be active. Adopt or monitor the existing render instead of starting a competing render queue.

At the checkpoint, the active render-related processes included:

- ComfyUI launcher PID `6780`
- ComfyUI standalone Python PID `49808`
- Finalizer watcher PID `16900`
- Handoff synchronization watcher PID `33760`

PIDs can change; verify rather than assuming they remain current.

## Recently accepted corrections

- `04C` attempt 4 accepted at 20 steps. It correctly begins after Kent has declined: no bill, donation, transaction, or reaching toward the plate. The attendant and plate leave while Kent keeps his hands on the closed wallet.
- `06C` accepted using an exact-invoice clean insert.
- `07C` attempt 2 accepted after correction.
- `08B` accepted using a clean-motion salvage.
- `08C` completed and passed review.
- `visual_audit.json` records successful review through `08C`, with 40 accepted clips.

Never reselect `04C` attempt 3; it visibly showed Kent removing a bill and reaching toward the plate.

## Generation and validation rules

Preserve every generated attempt under:

`A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`

Inspect every clip across its full duration, not merely its first and last frames. Review overview, ending, and every-second contact sheets. Reject and retry footage containing:

- warped, duplicated, merged, disappearing, or anatomically incorrect bodies;
- broken faces, hands, fingers, limbs, or object interactions;
- identity, wardrobe, location, architecture, or screen-direction drift;
- unintended people, incorrect blocking, role swaps, or actions contradicting the script;
- severe flicker, temporal morphing, visible gibberish text, or disruptive artifacts.

Ordinary upscaling improves softness, detail, and compression; it does not reliably repair warped anatomy or temporal identity changes. Structurally defective footage must be regenerated, shortened, or cleanly edited before enhancement.

For failed clips, vary prompt wording and seeds and retain 20 steps. If a full take repeatedly fails, try shorter segments, clean cuts, clean-frame holds, or edits using existing approved frames. Do not generate new reference images unless all prompt, seed, timing, segmentation, and existing-frame editing approaches have failed.

If a genuinely necessary first or last frame still cannot be obtained, use Gemini image generation according to `GEMINI_REFERENCE_IMAGE_GUIDE.md`. Upload the correct character sheet and closest approved scene/boundary frame, preserve exact identities and geography, save the result as a new version, and manually validate it before changing the config. Never ask Gemini to invent a character from prose when an approved visual sheet exists.

Do not reject an otherwise correct visual take merely because H3 produced gibberish speech or changed music. All H3 audio is discarded.

## Opening continuity lock

- The receptionist is the only woman and always remains behind the staff window.
- Person 1 and Person 2 are the only people in the chair interaction.
- Both men enter through the separate doorway and remain on the public side.
- The Narrator appears only where the approved script explicitly places him.
- No glass gate, glass fence, divider, extra chair, or third male visitor.

## Audio and final master

- Exact dialogue: `outputs/equal_shares/audio/EQUAL_SHARES_DIALOGUE_TIMELINE.wav`
- Continuous score: `outputs/equal_shares/audio/EQUAL_SHARES_CONTINUOUS_SCORE.wav`
- Expected edit duration: **1266 seconds (21:06)**
- Target: `outputs/equal_shares/EQUAL_SHARES_FINAL_1344x768.mp4`
- Shared final destination: `A:\Users\rhine\ComfyUI-Shared\output\equal_shares\final`
- Required final format: 1344×768 H.264 video with synchronized AAC audio.

Do not claim completion until all 124 clips are visually accepted, all originals remain preserved, the final master exists, and `work/audit_equal_shares_completion.py` passes every check.

## Required user updates

Keep the user informed in concise, plain language. During active work, do not remain silent for more than approximately 60 seconds. Report:

- the current clip or project stage;
- whether it is generating, validating, retrying, editing, assembling, or auditing;
- what passed or failed and why;
- what will be tried next;
- updated accepted and unresolved counts when they change;
- whether a long generation is still running normally;
- whether any required process stopped unexpectedly.

Do not dump raw logs or stop merely to provide an update. Continue working unless user input is genuinely required.
