# Claude Code — RVC voice conversion. Paste everything below the line.

---

Working directory:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Python: `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe`

Read `README.md` and `docs/WORKFLOW_NOTES.md` first. Do not read state from the parent folder's `outputs` — it is a stale fork.

## Bandwidth budget — hard limit

**The user is on a phone hotspot.** You are approved for **one download of about 190 MB**: `hubert_base.pt`.

Do **not** download `rmvpe.pt`, XTTS, F5-TTS, Chatterbox, or any other model. If a node package or dependency wants to pull weights on first run, stop and report the size before proceeding. If something cannot be done inside that budget, say so and leave it queued rather than downloading anyway.

RVC works without `rmvpe.pt` by using `harvest` or `pm` pitch extraction, which are algorithmic. Use `harvest`. `rmvpe` is a later quality upgrade, not a requirement.

## Gibberish speech is not a problem — read this before worrying about it

Most of the rendered clips contain gibberish or invented speech. **This does not affect RVC
training.** RVC learns *timbre* — formants, pitch behaviour, resonance, breathiness — not
words. Nonsense syllables are still voiced speech with real phonetics, so they train a
voice model exactly as well as intelligible dialogue. This is the main reason RVC suits
this project better than a TTS cloner.

The project's own transcripts confirm there is plenty of voiced material: of 138 validation
transcripts, **132 contain recognised speech**, median 19 words per clip.

What *would* poison training, and what you must filter:

1. **Silence.** Six clips produced no recognised speech at all: `04C`, `06A`, `14B`, `14E`,
   `16E`, `17C`. A window from those is room tone. Drop any segment whose RMS is near the
   noise floor.
2. **A second voice in the window.** H3 sometimes gives an unscripted character muttering.
   If another person speaks during the assigned window, the segment teaches a blend of two
   people. Flag segments where speech continues past the assigned end, or where the
   transcript in `validation_transcripts/<clip>_attempt_N.json` shows recognitions outside
   the window.
3. **Invented music or score.** The audio lock forbids it but it happens. Flag anything
   with sustained tonal content under the speech.

Filter on these, report how many seconds were dropped per character, and do not silently
train on contaminated audio.

## Goal

Give each character one consistent voice by converting the **existing Kokoro dialogue lines** into that character's timbre with RVC. Kokoro provides correct words and correct timing; RVC changes only how it sounds.

This preserves the 1266.000 s timeline exactly, because voice conversion does not change duration. That is the whole reason for choosing RVC over a TTS cloner.

## What is already on disk

- `models/rvc/` — two unrelated character models (Dragon Ball). Ignore them; do not delete them.
- `models/Kokorotts/Kokoro-82M/` — complete, 157 voices.
- `outputs/equal_shares/audio/dialogue/` — **113 per-line Kokoro WAVs**, correctly timed.
- `outputs/equal_shares/audio/EQUAL_SHARES_DIALOGUE_TIMELINE.wav` — 1266.000 s, 113 segments.
- `outputs/equal_shares/voices/<character>/reference_sample.wav` — 10 samples, 12–15 s each.
- 124 rendered clips with H3 audio under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip>\`.

## Task 1 — build RVC training sets (no download needed, do this first)

**Do not train on the 12–15 s reference samples.** They are sized for zero-shot cloners; RVC trains a model and needs much more.

Write `work/build_rvc_training_set.py` that, for a given character, extracts **every** segment of their speech from all rendered clips and concatenates it:

- Read speakers and windows from `dialogue_timing` in `story_config.json` (the speaker is the text before the first `:`, before the first `,`).
- Locate each clip's selected take via `comfy_source` in `manifest.json`.
- Extract each window with ffmpeg, mono, 44.1 kHz, loudness-normalised, with ~0.15 s padding.
- Concatenate per character to `outputs/equal_shares/voices/<slug>/rvc_training/all_speech.wav`.
- Report total seconds per character, before and after filtering, and skip any character
  left with under 60 s, flagging them.
- Cross-check each clip against `outputs/equal_shares/validation_transcripts/<clip>_attempt_N.json`,
  which already holds speech-recognition output per clip: word counts, per-recognition
  start times and durations. Use it to drop silent segments and to spot speech that runs
  outside the assigned window.

Expected totals: Kent ~201 s, Narrator ~169 s, Ryann Sally ~95 s, Avery ~74 s, Doris ~42 s, Faith White ~28 s, Volunteer ~22 s, Housing representative ~17 s.

Characters below the threshold — Male Visitor One and Two, Wealthy commuter, Unhoused man, Congregation member, Council member, Crew lead, Aid worker — have only 2–6.5 s each. **Leave them on their Kokoro voice.** Do not attempt to train them. Note this decision in the notes file.

The H3 audio drifts between takes. That is acceptable and arguably desirable here: RVC will learn an average of the character rather than one take.

## Task 2 — get RVC running

Determine what RVC tooling exists in the ComfyUI install (`A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\custom_nodes\`). Report what you find before installing anything.

Download **only** `hubert_base.pt` into wherever the installed RVC implementation expects it. Report the exact path and the actual size.

Then prove the pipeline works end to end on **one** character before touching the rest. Use **Narrator** — 169 s of training audio, and his voice appears in 16 clips, so an improvement is easy to hear.

Train an RVC model for Narrator, then convert one Kokoro line — `outputs/equal_shares/audio/dialogue/00A_01_Narrator.wav` — and write the result beside it as `00A_01_Narrator_rvc.wav`.

**Verify the converted file has the same duration as the input.** If it does not, stop; the timing guarantee is the reason for this approach and a duration change breaks the timeline.

## Task 3 — stop and report

Do not batch-convert 113 lines. Stop after the single Narrator line and report:

- what RVC tooling was found or installed, and exactly what was downloaded and its size
- training settings used, epochs, and how long it took
- the input and output durations of the converted line
- your honest assessment of whether it sounds like the Narrator's H3 voice

The user will listen and decide whether to continue.

## Task 4 — append to the notes

Add a dated section to `docs/WORKFLOW_NOTES.md` under a new "RVC" heading covering: what worked, what failed, exact model paths, training parameters, per-character training seconds, and anything that would waste time on a second attempt. Be specific enough that the eventual automation program can be built from it.

Keep the existing structure — append, do not rewrite earlier entries.

## Rules

- **Do not start a video render.** This is audio work. Reading `runtime/render_queue_owner.json` and the supervisor log tail is fine; starting ComfyUI for generation is not. If RVC needs the GPU, check first that nothing else holds it.
- **Do not delete or overwrite any audio.** Converted files get a new name; originals stay.
- **Do not modify `EQUAL_SHARES_DIALOGUE_TIMELINE.wav`.**
- **Do not hand-edit `manifest.json` or `visual_audit.json`.**
- Do not touch `models/rvc/*Dragon Ball*` models.
- 124 clips is a render count, not an acceptance count. The film is not finished.

Begin with Task 1, which needs no download at all, and report the per-character training seconds before you download anything.
