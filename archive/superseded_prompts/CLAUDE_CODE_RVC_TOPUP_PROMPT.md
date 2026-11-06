# Claude Code — RVC training top-up for short-dialogue characters. Paste below the line.

---

Working directory:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Read `docs/WORKFLOW_NOTES.md` and `README.md` first. Do not read state from the parent folder's `outputs` — stale fork.

## Where things stand

RVC works. Applio at `A:\Users\rhine\ComfyUI-Shared\tools\applio`, env `dbz-rvc-env\python.exe`, `contentvec` and `rmvpe` already on disk. `harvest` is broken in this build — `compute_f0()` has no harvest branch — so use **rmvpe**. Narrator trained at 100 epochs in ~7 minutes and converted a line successfully.

Four characters have enough training audio and are done for now: Narrator 168.6 s, Kent 177.5 s, Ryann Sally 87.6 s, Avery 74.3 s.

**Four were skipped for too little audio. This job gets them over the line.**

| Character | Counted | Shortfall vs 60 s floor |
|---|---|---|
| Doris | 55.0 s | 5 s |
| Faith White | 28.0 s | 32 s |
| Housing Representative | 17.0 s | 43 s |
| Volunteer | 11.0 s | 49 s (`14B` was silent) |

## Bandwidth

Still on a phone hotspot. **Download nothing.** Everything needed is on disk. If any step wants to fetch weights, stop and report the size first.

## Task 1 — fold in the VOX clips that already exist (no render, do this first)

Four VOX clips were rendered on 2026-08-11 and **were never counted**, because they live in `outputs/equal_shares/vox_output/manifest.json` rather than the main manifest:

```
vox_output/clips/001_VOX_FAITH_WHITE.mp4            15.1 s
vox_output/clips/001_VOX_HOUSING_REPRESENTATIVE.mp4 15.1 s
vox_output/clips/001_VOX_RYANN_SALLY.mp4            15.1 s
vox_output/clips/001_VOX_VOLUNTEER.mp4              15.1 s
```

Each holds roughly 13 s of continuous speech (1 s lead-in, 1 s tail).

Extend `work/build_rvc_training_set.py` to read `vox_output/manifest.json` as a second source and include VOX segments for the matching character. Apply the same filters — drop silence, flag second voices, flag music.

Re-run and report new totals. Expect roughly: Faith White ~41 s, Housing Rep ~30 s, Volunteer ~24 s, Doris unchanged at 55 s.

**This is free audio. Do it before rendering anything.**

## Task 2 — generate top-up VOX clips

Target **75 s** of usable speech per character, not the bare 60 s floor. Narrator's own result showed loss still falling at epoch 100 on 168 s; more data is better and these four will always be the thin end.

Assuming ~13 s usable per 15 s clip, after Task 1:

| Character | Needed | Clips |
|---|---|---|
| Doris | ~20 s | 2 |
| Faith White | ~34 s | 3 |
| Housing Representative | ~45 s | 4 |
| Volunteer | ~51 s | 4 |

Thirteen clips, roughly two hours at ~8 min each. Recompute from your actual Task 1 numbers rather than trusting this table.

### Writing the filler dialogue

**Each clip needs different text.** RVC learns timbre from phonetics, so varied phoneme coverage trains a better model than the same paragraph four times. Write natural, in-register lines for each character — Doris elderly and warm, Faith White measured and pastoral, the Housing Representative procedural and polite, the Volunteer brisk and friendly — and make sure across a character's set you cover a good spread of vowels, plosives, sibilants and nasals.

Content is irrelevant to the film. These clips are never seen or heard in the edit. Do not reuse film dialogue; if a clip ever leaked into the cut it should be obviously not part of the story.

### Clip specs

Follow the existing pattern in `outputs/equal_shares/voice_sample_clips.json` and `vox_render_config.json`:

- id `VOX_<CHARACTER>_02`, `_03`, … so the existing clips are not overwritten
- 15.0 s, 362 frames, 24 fps
- **single anchor** — `first_frame` from that character's first speaking clip, `last_frame` **null**, last-frame input left disconnected
- 16:9 (Widescreen), 0.3 MP, multiple 32, 20 steps, `res_multistep` / `simple`, denoise 1.0, non-Turbo
- prompt in house style: locked camera, exactly one person, identity block, per-beat mouth state, speech across `[1s-14s]`
- render into `story/VOX_<CHARACTER>_NN/`, tracked in `vox_render_config.json` / `vox_output/manifest.json`

**Never add VOX clips to `story_config.json` or `manifest.json`.** They must not reach the edit or the completion audit.

### Before rendering

Check that nothing else owns the GPU: `runtime/render_queue_owner.json`, port 8188, and the tail of `runtime/render_supervisor.log` against the clock. Claim the queue with a clear purpose string, and release it when finished.

### What counts as a good VOX take

Judge on **audio only**. These are never seen.

- Speech runs continuously across the assigned window — no long silences
- One voice only; no second character muttering underneath
- No invented music or score
- Gibberish is fine. Do not re-roll for unintelligible words.

Re-roll only for silence, a second voice, or music.

## Task 3 — rebuild, train, convert one line each

Re-run the training-set builder, confirm each of the four now clears 75 s, then train an RVC model per character with the same settings that worked for Narrator: rmvpe pitch, contentvec embedder, 40 kHz, batch 8, HiFi-GAN pretrained.

**Use more epochs than Narrator's 100** — loss was still falling. Try 250 and report where it plateaus.

Convert one Kokoro line per character as a spot check and verify duration:

- Doris → `audio/dialogue/02B_01_Doris.wav`
- Faith White → `audio/dialogue/04B_01_Faith White.wav`
- Housing Representative → `audio/dialogue/18A_01_Housing representative.wav`
- Volunteer → `audio/dialogue/11C_01_Volunteer.wav`

Match the exact filenames on disk. Write each as `<name>_rvc.wav` beside the original.

**On the duration delta:** Narrator's conversion came out 7.1000 s → 6.9999 s, about 0.1 s short. That is acceptable **because lines are placed at absolute offsets in the timeline, not concatenated end to end** — so the error cannot accumulate across 113 lines. Verify each conversion stays within ±0.15 s of its input, and stop and report if any drifts further.

## Task 4 — stop and report

Do not batch-convert the whole film. Report:

- Task 1 totals before and after folding in the existing VOX clips
- how many top-up clips you rendered per character, how many re-rolls, and why each re-roll happened
- final training seconds per character
- epochs used and where loss plateaued
- input and output duration for each of the four spot-check conversions

Then wait. The user listens and decides.

## Task 5 — append to the notes

Add to the RVC section of `docs/WORKFLOW_NOTES.md`: that `vox_output/manifest.json` is a separate source the training builder originally missed, how much usable speech a 15 s VOX clip actually yields, the epoch count where loss plateaued, and the measured duration deltas. Append; do not rewrite earlier entries.

## Rules

- Do not render story clips. VOX only.
- Do not delete or overwrite any audio. New names for new files.
- Do not modify `EQUAL_SHARES_DIALOGUE_TIMELINE.wav`.
- Do not hand-edit `manifest.json` or `visual_audit.json`.
- Do not touch the Dragon Ball models in `models/rvc/`.
- 124 clips is a render count, not an acceptance count.

Begin with Task 1 and report the new totals before rendering anything.
