# Equal Shares — authoritative audio-first pipeline

Updated 2026-08-13 from the user's explicit workflow clarification. This file
supersedes the earlier Task-0/single-pass branch. There is no shortcut in which
the film is rendered at 0.9 MP before the soundtrack is complete.

## Outcome

Build and approve the complete MiniMax H3 soundtrack first. Only after every
story clip has accepted audio may high-resolution picture generation begin.

The two immutable gates are:

1. **Audio gate:** 124/124 clip soundtracks exist, have provenance back to a
   preserved MiniMax H3 audio-first raw, and pass the relevant speech, timing,
   voice, music, ambience, and sound-effect checks.
2. **Picture gate:** every clip has a visually accepted take generated against
   its approved soundtrack, or is explicitly marked `human_review_needed` after
   the 0.4 MP attempt fails.

Full-quality MiniMax H3 only. Never use Turbo.

## Phase 0 — establish canonical reference sounds

### Character voices

Each speaking character gets one canonical `h3_voice_ref.wav`. Use the first
appearance in story order whose **delivered** audio contains enough clean,
continuous speech to be a reliable reference. A first scripted line that is
silent, mixed with another voice, mostly noise, or unstable is not qualifying.

Selection rules:

- one contiguous passage from one preserved MiniMax H3 take;
- one stable speaker, no voice switching;
- at least 6 seconds of useful speech is required for an automatic canonical
  reference; a real-story passage of 2–6 seconds requires human voice review;
- speech density at least 60%, with no internal gap above 1 second;
- never concatenate separate takes;
- preserve and record the source MP4, extraction window, and character;
- once approved, never overwrite the reference—write a versioned sibling.

If no existing first-appearance candidate qualifies, render the character's
first qualifying actual story soundtrack at 0.2 MP with the original dialogue
and boundary images. That accepted story soundtrack becomes the voice source.
Never invent filler dialogue or create a reference-only VOX scene.

Ear review is an acceptance gate, not a Stage-1 generation stop. A pending
actual-story bootstrap may be labeled provisional and used only to keep voice
conditioning available while the remaining soundtrack candidates render. It
does not count as accepted and cannot open Stage 2. The resumable supervisor is
`work/continue_audio_generation_nonblocking.py`.

Narrator references are voice-identity conditioning, not soundtrack stems. A
take with the intended Narrator plus a quieter replay, echo, whisper, alternate
take, or doubled vocal layer fails even when the timbre is consistent. Use the
single-layer repair profile and preserve the original attempt. Static prompt
preflight is required before submission: every configured line appears exactly
once, every timing window fits, references and boundary frames exist, and
dialogue does not coexist with an absolute no-speech instruction.

`work/build_voice_reference_map.py` implements first-qualifying-appearance
selection and writes `story_voice_bootstrap_plan.json`. `work/render_audio_pass.py
--bootstrap-missing-voices` renders the planned story clips.

### Music, ambience, and recurring effects

Treat recurring sound as reference material just like a voice:

- The non-diegetic score is one continuous, approved master track laid across
  the edit. Do not ask H3 to invent a new song in every clip.
- For diegetic music, room tone, machine hum, phone tone, crowd bed, or another
  recurring sound, the first approved clean occurrence becomes the named sound
  reference for later clips in that continuity group.
- Store these under `outputs/equal_shares/audio/references/` with provenance in
  `outputs/equal_shares/audio_continuity_map.json`.
- MiniMax H3 ref2va allows at most three standalone audio references. Character
  voice references take priority during the audio harvest. If all reference
  slots are occupied, preserve continuity by carrying the approved bed in the
  soundtrack assembly rather than sacrificing a character voice.

## Phase 1 — generate the complete soundtrack at the lowest proven resolution

Render **all 124 clips**, including clips without dialogue, through
`MiniMaxH3ReferenceToVideo` at **0.2 MP**, 20 steps. The picture is disposable;
the sound is the deliverable.

Fixed settings:

| Setting | Value |
|---|---|
| Checkpoint | `minimax_h3_ref2va_pruned_nvfp4.safetensors` |
| Node | `MiniMaxH3ReferenceToVideo` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| Video/audio VAEs | MiniMax H3 FP16 video / FP32 audio |
| Resolution | 16:9, 0.2 MP, multiple 32 |
| Sampling | 20 steps, `res_multistep` / `simple`, denoise 1.0 |
| Output | 24 fps, 8-bit video with native stereo H3 audio |

References for every audio-first job:

- `ref_image_0`: exact opening frame.
- `ref_image_1`: exact closing frame when `last_frame` exists. It must be wired,
  not merely described in prose.
- ordered character `h3_voice_ref.wav` files, based on first spoken appearance
  within the clip;
- a recurring sound reference when relevant and when a slot remains.

Prompt rules:

- Spoken words occur exactly once in the prompt, inside their timed beat.
- State which named speaker is on/off screen and who remains silent.
- Describe every necessary sound event and its window.
- Name the recurring music/ambience/effect reference and tell H3 to preserve its
  timbre, rhythm, level, and acoustic space without copying unrelated content.
- A single clip may be retried with tighter timing, clause-boundary splits,
  explicit silence locks, and then a new seed. Never solve dialogue with Turbo.

Every raw goes to `story/AUDIO_<clip>/` and every attempt is preserved. Accepted
full-clip audio is extracted to:

`outputs/equal_shares/audio/h3_dialogue/<clip>_<attempt>_full.wav`

Line-level inspection copies may sit beside it, but the full-clip WAV is the
authoritative soundtrack reference because it also contains timing, ambience,
music, and effects.

Do not use these older folders as native-H3 sources:

- `outputs/equal_shares/audio/dialogue/` — Kokoro and RVC material;
- `outputs/equal_shares/audio/_hybrid_parts/` — an older mixed assembly cache.

### Audio validation loop

After every audio-first generation:

1. Probe duration, sample rate, channels, clipping, silence, and missing audio.
2. Extract each scripted dialogue window with small timing padding.
3. Transcribe locally and compare normalized expected words, word recall, word
   order, insertions, omissions, and extra speech.
4. Flag likely gibberish, invented words, repeated lines, a second muttering
   voice, or speech outside assigned windows.
5. Compare the speaker and recurring-bed reference features when a reliable
   local comparison is available.
6. Listen to borderline/empty-recognizer results. A broken recognizer never
   converts an unknown result into a pass.

Automatic acceptance is intentionally strict. A dialogue line should normally
have at least 0.95 expected-word recall, high sequence agreement, no substantive
insertions, and correct timing. Store measurements, transcript, source raw,
prompt revision, seed, and verdict in `audio_pass_manifest.json`. Improve the
filter when a false pass or false reject is discovered; preserve the old result
as audit history.

Phase 1 is complete only when every clip is `accepted`, not merely rendered.

## Phase 2 — generate picture around the approved soundtrack

Phase 2 is blocked until the Phase-1 audio gate passes.

For each clip, use ref2va with:

- the exact opening image;
- the exact closing image when one exists;
- the accepted full-clip Phase-1 WAV as the principal audio reference;
- a prompt written for MiniMax that says the referenced audio is the exact
  soundtrack: preserve every word, speaker, pause, music cue, ambience, effect,
  and timing; generate the visual performance around it; do not paraphrase,
  replace, remix, repeat, or add speech.

Start at **0.9 MP**. If the visual gate rejects the take, create a new preserved
attempt at the next rung:

`0.9 → 0.8 → 0.7 → 0.6 → 0.5 → 0.4 MP`

Keep 20 steps on every rung. Resolution is the only automatic ladder variable;
prompt and seed may also change when the rejection explains what must be fixed.
Never go below 0.4 MP. If the 0.4 MP take still fails, stop automatic rendering
for that clip and set `status: human_review_needed`, including every attempt,
failure reason, prompt, seed, and resolution so the user can help diagnose it.

### Visual validation after every attempt

The filter must evaluate the full clip at native resolution against the prompt
and references, not merely a contact sheet. Check:

- missing, duplicated, merged, extra, or disappearing people;
- face/identity drift, facial collapse, and inconsistent hair or wardrobe;
- malformed hands, fingers, limbs, joints, gait, or object interactions;
- temporal morphing, severe flicker, unintended cuts, camera reversals, black
  frames, freezes, or unrelated scene changes;
- architecture, props, geography, screen direction, and start/end frame intent;
- visible gibberish text, logos, captions, or watermarks;
- action, blocking, and speaker behavior against the prompt.

Mechanical/video metrics may reject obvious failures. Agent vision must inspect
native-resolution frames and motion for semantic and anatomical faults. A
contact sheet may rank work but cannot accept a take. Upscaling cannot repair
identity or anatomy.

### Preserve the perfect soundtrack

H3 may reinterpret a reference even when prompted not to. Therefore the audio
from the high-resolution picture render is never the soundtrack authority.
Compare it for diagnostics, then mux the exact approved Phase-1 WAV onto the
selected video without rewriting it. This guarantees that accepted words,
voices, music, ambience, effects, and timing reach the film unchanged.

## Phase 3 — assembly and completion

- Assemble only visually accepted picture takes.
- Use only their corresponding accepted Phase-1 full-clip WAVs.
- Carry the continuous score as one track across cuts; do not restart it per
  generation.
- Preserve every raw, reference, manifest, validation report, assembly input,
  and versioned deliverable.
- The completion audit must include the audio gate, visual gate, provenance, and
  `human_review_needed` count. The film is not complete while that count is
  nonzero.

## Operational safeguards

- One ComfyUI backend and one GPU owner on port 8188 at a time.
- One clean backend per render job.
- Never download anything.
- Never use Turbo.
- Never delete or overwrite evidence.
- Never hand-edit a runner-owned manifest during a render.
- Mechanical validity is not audio or visual acceptance.
