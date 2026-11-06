# 2026-08-17 — two faults that corrupted every autopilot render

## What changed

**`work/render_audio_pass.py`**

1. `reference_job_prefix()` now returns `""`. It previously prepended a
   four-line `AUDIO-FIRST REFERENCE JOBS` header to every prompt.
2. `clip_list()` now falls back to `prompts_native_r2v/<clip>.txt` when
   `audio_pass_config_omni_v1.json` has no entry for a clip. It previously fell
   back to `story_config["prompt"]` — the pre-native format.

Backups kept: `render_audio_pass.BACKUP_before_header_removal.py`.

**New:** `docs/GOLDEN_REFERENCE/` holding the proven graph and the rule that
created it. **New:** `work/validate_audio_take.py`.

## Why

The operator hand-made 14 clips with zero doubled tracking and correct speech.
The autopilot, running the same pipeline, reproduced the old faults. The
difference had never been checked at the level that matters — what H3 actually
received.

## The evidence

Extracted from the workflow embedded in the operator's good takes
(`ffprobe -show_entries format_tags=prompt`) and from the autopilot's PNGs.

| | operator's 14 good clips | autopilot |
|---|---|---|
| prompt begins | `subject_definitions:` | `AUDIO-FIRST REFERENCE JOBS` |
| `<Picture N>` declared | twice, per the guide | **three times** |
| prompt set, silent clips | native | **old `story_config` prompt** |
| duration | 7–11 s, fitted | fitted (this part was right) |
| MP / steps / sampler | 0.2 / 20 / res_multistep | identical |

Proof of fault 2: `30A`'s embedded prompt began `One continuous unbroken take. /
CAMERA / REFERENCES`. `audio_pass_config_omni_v1.json` contains 78 entries, not
124 — the 46 silent clips were never in it.

Bad output, measured:

```
29B   2 scripted words -> 3.0s speech   5.2x
29C   0 scripted words -> 8.0s speech
30A   0 scripted words -> 7.3s speech
30C   0 scripted words -> 7.0s speech
```

## Verified after

```
python -m py_compile work/render_audio_pass.py          -> ok
live import of clip_list():
  clips            : 124
  pure native      : 124      <- was 78
  still wrong      : 0
  rendering short  : 75
```

Every one of the 124 prompts the renderer will now send begins
`subject_definitions:`.

## Still unverified

- **No render has been made since the fix.** The fix is verified at the prompt
  level only. It is NOT verified at the audio level until the operator listens.
- The good clips take voice reference from a **video's audio track** (`1.mp4`);
  the autopilot uses a **standalone WAV**. Same socket, different content. If
  doubling survives, this is the next variable to test.
- `speech_density.py` cannot tell speech from crowd ambience. The three silent
  clips above may be legitimate background voices. Only `29B` is certain.

## The error behind the error

Asked whether the handoff folder was correct, the answer given was yes. What had
been checked was document-to-config consistency. What was never checked was the
rendered graph. **Consistency between one's own files is not verification**, and
reporting it as such is how a whole pass got wasted.
