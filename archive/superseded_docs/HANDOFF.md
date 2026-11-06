# Equal Shares — ComfyUI Automation Handoff

Updated from the active project on August 10, 2026 at approximately 12:46 AM Eastern. For the current Open Interpreter transfer, read `OPEN_INTERPRETER_CONTINUATION.md` first.

If a genuinely necessary new first or last frame must be created through Gemini, follow `GEMINI_REFERENCE_IMAGE_GUIDE.md` and use the bundled authoritative character sheets and neighboring scene references.

This folder is also maintained as the project's canonical handoff mirror. A background updater copies changed files from the live `outputs` and `work` folders approximately once per minute. Check `SYNC_STATUS.json` for the latest successful checkpoint and `SYNC_LOG.txt` for sync history.

## Current checkpoint

- 124 configured clips.
- 40 clips are currently visually reviewed and accepted with local assembly copies present.
- 84 clips remain unresolved.
- The current or first unresolved clip at this checkpoint is `09A`.
- The persistent renderer is active; the live project may advance beyond this copied checkpoint.
- Full-quality MiniMax H3 only. Turbo models, Turbo nodes, and Turbo LoRAs are prohibited.
- Current generation settings use 20 steps for both single-anchor and dual-anchor clips.
- Every generated raw attempt remains under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`.
- H3-generated speech and music are discarded. Exact dialogue and one continuous soundtrack are added in post-production.
- No new reference images should be generated unless prompt variation, retries, shorter segments, clean cuts, and edits using existing frames have all failed.

## Package layout

Keep `outputs` and `work` as sibling folders:

```text
COMFYUI_STORY_HANDOFF_2026-08-09/
├── outputs/
│   ├── minimax_story_runner.py
│   ├── dialogue_validator.py
│   └── equal_shares/
│       ├── story_config.json
│       ├── story_bible.json
│       ├── shot_plan.json
│       ├── source_clip_script.json
│       ├── manifest.json
│       ├── frames/
│       ├── references/
│       ├── clips/
│       ├── audio/
│       ├── validation_contacts/
│       └── runtime/
└── work/
    ├── render_until_complete.py
    ├── finalize_equal_shares_when_ready.py
    ├── audit_equal_shares_completion.py
    ├── reject_clip_visual.py
    └── build_clip_every_second.py
```

## Authoritative files

- `outputs/equal_shares/story_config.json`: approved story, prompts, timing, references, constraints, and 20-step settings.
- `outputs/equal_shares/manifest.json`: selected attempts and current generation state.
- `outputs/equal_shares/visual_audit.json`: manual visual-review record.
- `outputs/equal_shares/generation_audit.json`: proof of the non-Turbo H3 model and production settings.
- `outputs/equal_shares/completion_audit.json`: most recent end-to-end completion check.
- `outputs/minimax_story_runner.py`: resumable ComfyUI API runner.
- `work/render_until_complete.py`: persistent one-clip-at-a-time supervisor.
- `work/finalize_equal_shares_when_ready.py`: waits for the complete set, assembles the master, and publishes it.

## Visual acceptance rules

Inspect the full duration of every clip, including the overview, ending strip, and every-second contact sheet. Reject and retry footage with:

- warped, duplicated, merged, disappearing, or anatomically incorrect bodies;
- broken faces, hands, limbs, or object interactions;
- identity, wardrobe, location, or screen-direction drift;
- unintended people, incorrect blocking, or actions contradicting the script;
- severe flicker, morphing, visible gibberish text, or disruptive artifacts.

Ordinary upscaling may improve softness, detail, and compression, but it does not reliably repair incorrect anatomy or temporal identity changes. Structurally broken footage must be regenerated, shortened, or cleanly edited before enhancement.

For a failed clip, try varied prompts and seeds at 20 steps. Preserve all original attempts. If repeated full takes fail, prefer shorter segments, clean cuts, or motion made from existing approved frames before considering a new reference image.

## Critical story continuity

- The receptionist is the only woman in the opening waiting-room sequence and always remains behind the staff window.
- Person 1 and Person 2 are the only people involved in the chair interaction.
- Both men enter through the separate doorway and remain on the public side.
- The Narrator appears only where the approved script explicitly places him.
- No glass gate, glass fence, invented divider, extra chair, or third male visitor.
- In `04C`, Kent has already declined before the clip begins. No bill, donation, transaction, or reaching toward the plate may appear. His hands remain on the closed wallet while the attendant and plate leave.

## Audio and final delivery

- Dialogue timeline: `outputs/equal_shares/audio/EQUAL_SHARES_DIALOGUE_TIMELINE.wav`
- Continuous score: `outputs/equal_shares/audio/EQUAL_SHARES_CONTINUOUS_SCORE.wav`
- Target master: `outputs/equal_shares/EQUAL_SHARES_FINAL_1344x768.mp4`
- Shared final destination: `A:\Users\rhine\ComfyUI-Shared\output\equal_shares\final`
- Required final format: 1344×768 H.264 video with synchronized AAC audio, approximately 21:06.

Do not claim completion until all configured clips are valid, every selected clip has passed full visual review, all original chunks are preserved in the shared ComfyUI output tree, the final master exists, and `work/audit_equal_shares_completion.py` passes every requirement.

## Resume commands

From the folder containing `outputs` and `work`:

```powershell
$Python = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"

& $Python ".\outputs\minimax_story_runner.py" `
  ".\outputs\equal_shares\story_config.json" --check

& $Python ".\work\render_until_complete.py"
```

After all clips pass visual review:

```powershell
& $Python ".\work\finalize_equal_shares_when_ready.py"
& $Python ".\work\audit_equal_shares_completion.py"
```
