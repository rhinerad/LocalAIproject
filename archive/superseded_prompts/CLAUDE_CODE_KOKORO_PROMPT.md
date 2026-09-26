# Claude Code — Kokoro voice path. Paste everything below the line.

---

Working directory:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Python: `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe`

Read `README.md` first, then `docs/VOICE_CLONING_MODULE.md`. Do not read state from the parent folder's `outputs` — it is a stale fork.

## Decision you are implementing

**Abandon MiniMax voice cloning. Use Kokoro.** No paid API, no subscription, no `MINIMAX_API_KEY`.

Understand what this does and does not mean before writing code:

- **Kokoro cannot clone a voice.** It is fixed-voice TTS. There is no reference sample, no voice_id, no cloning step.
- Each character already has an assigned Kokoro voice in `outputs/equal_shares/audio/dialogue_manifest.json` — Narrator `am_onyx`, Kent `am_michael`, Doris `af_heart`, Avery `bm_george`, Ryann `af_nicole`, Faith White `bm_daniel`, and so on.
- A fixed voice **cannot drift**, which was the entire problem cloning was meant to solve. This path is simpler and strictly better for consistency.
- `EQUAL_SHARES_DIALOGUE_TIMELINE.wav` already exists: 1266.000 s, 48 kHz stereo, 113 segments. **Most of the work is already done.**

So your job is not to generate voices. It is to close three specific gaps.

## Task 1 — retire the cloning path

In `work/voice_manager.py`:

- Delete or clearly disable `upload_reference()`, `clone_voice()`, `synthesize_line()`, `_api_key()`, and the `CLONE_URL` / `UPLOAD_URL` / `TTS_URL` / `CLONE_MODEL` constants, plus the `clone` subcommand.
- Keep everything else. `get_first_speaker_clips()`, `extract_reference_audio()` and the gate are still useful for reviewing how H3's own audio sounds per clip, which feeds Task 3.
- Update the module docstring so it describes the Kokoro path, not cloning.
- Update `docs/VOICE_CLONING_MODULE.md` to match, or replace it with a Kokoro equivalent. Do not leave documentation describing a path that no longer exists.

The approval gate is now about **which clips keep H3 audio**, not about approving clone sources. Say so in the file.

## Task 2 — add the three missing lines to the Kokoro track

Three on-camera lines were added to `story_config.json` after the dialogue track was built, so the timeline has silence where they should be:

| Clip | Window | Speaker | Line |
|---|---|---|---|
| `00D` | 9–11 s | Male Visitor One | "After you, please." |
| `00D2` | 3–5 s | Male Visitor Two | "No, please, I insist." |
| `00D2` | 5–7 s | Male Visitor One | "Really, please." |

Neither visitor has a Kokoro voice assigned. Pick two distinct male voices not already used by a named principal, add them to the voice map, and record which you chose.

Then re-run `work/generate_dialogue_tracks.py` to rebuild `EQUAL_SHARES_DIALOGUE_TIMELINE.wav` and `dialogue_manifest.json`.

**Verify after rebuilding:** duration must still be exactly **1266.000 s**, and the segment count must be **116**, not 113. If the duration moved, stop and report — the timeline is laid to cumulative `edit_duration` and a drift means something else changed.

## Task 3 — wire the audio choice into assembly

`work/audio_decisions.py` already builds a hybrid timeline: per clip, either H3's own audio (`keep`) or the Kokoro span (`replace`). It was tested and produces 1266.00 s with zero drift. Nothing reads its output.

- Make `outputs/equal_shares/assemble_story.py` use `EQUAL_SHARES_HYBRID_DIALOGUE.wav` when it exists, and fall back to `EQUAL_SHARES_DIALOGUE_TIMELINE.wav` when it does not.
- Do not change the score path, the mix levels, the ducking, or the AAC settings.
- Do not change `-an` on the assembly clips. Video and audio stay separate until the final mix.

Then:

```powershell
& $Py work\audio_decisions.py list
& $Py work\audio_decisions.py build
```

and confirm the built WAV is 1266.00 s.

## Task 4 — repair the gate, then report

`voice_approval_gate.json` currently has 8 characters stuck at `status: "blocked"` from an earlier schema. `check_approval_gate()` skips blocked entries, so the gate reports OPEN while those eight have no voice decision at all: Male Visitor One, Male Visitor Two, Wealthy commuter, Unhoused man, Congregation member, Council member, Crew lead, Aid worker.

Under the Kokoro path they are not blocked — they have a fixed voice like everyone else. Rewrite the gate so it reflects the real question now: **per clip, keep H3 audio or use Kokoro.** `blocked` should no longer exist as a status.

Preserve the 10 existing approvals if they still mean anything under the new schema; if they do not, say so plainly rather than silently discarding them.

## Rules

- **Do not start a render.** This is an audio and code task. If you need to check GPU state, read `runtime/render_queue_owner.json` and the tail of `runtime/render_supervisor.log`; do not start ComfyUI.
- **Do not hand-edit `manifest.json` or `visual_audit.json`.**
- **Do not delete any audio.** Back up `EQUAL_SHARES_DIALOGUE_TIMELINE.wav` before regenerating it.
- **Do not add VOX clips to `story_config.json` or `manifest.json`.** They live in `vox_render_config.json` on purpose. Under the Kokoro path they are no longer needed at all — say whether you think they should be kept or abandoned.
- The four already-rendered VOX clips are in `outputs/equal_shares/vox_output/`. Leave them; do not delete.
- 124 clips is a render count, not an acceptance count. Do not describe the film as finished.

## Report when done

State: which functions you removed, which two voices you assigned to the visitors, the new duration and segment count of the dialogue timeline, whether assembly now reads the hybrid WAV, and what the gate looks like. Flag anything you could not complete.
