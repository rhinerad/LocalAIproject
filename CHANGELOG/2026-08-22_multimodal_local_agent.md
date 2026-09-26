# 2026-08-22 — Local image, audio and video analysis for prompt creation

## Request and observed gap

The browser attachment picker accepted only text. `server.py` inlined every
attachment as UTF-8 and the system prompt explicitly said the agent could not
see images or hear audio. Binary media therefore could not reach an analyzer or
be used as grounded prompt evidence.

No download was authorised or performed.

## Changes

### Binary attachment path

- `local_agent/static/index.html`
  - accepts text, image, audio and video files
  - enforces a 75 MB per-file limit before upload
  - uploads binary media to `/api/upload`; text remains inline
  - permits attachment-only turns and identifies each media kind in its chip
- `local_agent/server.py`
  - added a size-limited base64 upload endpoint
  - permits only known image/audio/video extensions
  - content-addresses files by SHA-256 under `local_agent/uploads/`, preserving
    the original filename as the suffix and never overwriting a different file
  - stores only media paths/descriptions in conversation JSON, never binary data

### Sensory capability and tools

- new `local_agent/capabilities.py`
  - queries Ollama `/api/show` rather than assuming model capability
  - detected installed `qwen3vl-abl:latest` with native `vision`
  - detects FFmpeg/FFprobe, NumPy, faster-whisper and speaker-model availability
- new `local_agent/media_tools.py`
  - `see_image`: native-resolution local Ollama vision, optional exact crop
  - `video_frames`: deterministic FFmpeg frame extraction at explicit times or
    an interval, capped at 12 frames
  - `analyze_video`: multi-frame visual analysis plus audio measurements
  - `read_video_metadata`: MP4 or PNG metadata and embedded ComfyUI graph/prompt;
    reuses `harvest_good_audio_masters.graph_facts`, including inline prompts
  - `audio_measure`: duration, speech spans/density, leading burst and suggested
    head trim with an explicit list of what those measurements cannot establish
  - `transcribe` and `compare_voice`: fully wired but return exact missing-model
    information until those models are deliberately installed
- `local_agent/tools.py`
  - registered all eight sensory functions with native Ollama JSON schemas;
    total tools are now 22
- `local_agent/agent.py` and `build_knowledge_pack.py`
  - attached media must be inspected before it is described or used in a prompt
  - visual evidence may not invent audio; measurements may not claim correct
    words, pronunciation, identity, absence of gibberish, or acceptance
- `local_agent/router.py`
  - ignores NVIDIA's `[Insufficient Permissions]` pseudo-process like the
    already-ignored WDDM browser entries
  - sensory calls distinguish the agent's own resident Ollama vision model from
    ComfyUI/queue ownership; port 8188 or a render owner still blocks vision
- `work/harvest_good_audio_masters.py`
  - made `soundfile` optional for read-only graph/audio analysis; master writing
    still refuses clearly when that package is absent

Documentation and the Upgrade 4 status were updated. Added
`local_agent/test_media_analysis.py`.

## Live verification

### Uploads

The live GUI accepted and content-addressed all three media kinds:

| kind | sample | bytes | result |
|---|---|---:|---|
| image | `boundary_00_v2.png` | 1,826,842 | stored, kind=image |
| audio | `00C.wav` | 1,536,078 | stored, kind=audio |
| video | `11.mp4` | 696,433 | stored, kind=video |

An `.exe` upload was refused with HTTP 400. No conversation JSON exceeded 2.3
KB after these tests, proving binary/base64 was not persisted in chat history.

### Image-to-prompt, through the real GUI

The uploaded PNG produced a native `see_image` tool call using
`qwen3vl-abl:latest`. It correctly identified the black-and-white institutional
interior, the suited foreground man, the seated woman behind the service window,
directional lighting, static eye-level medium framing and spatial layout. The
chat then generated an H3-shaped prompt from those observations.

That first live prompt invented a quiet soundscape from the still image. The
system rules were tightened so image-only prompts must write sound as not
inferable/operator input required; visual analysis itself had already stated it
could not hear audio.

### Audio

The uploaded WAV measured 8.0 s total, 4.76 s speech, 59.5% speech density, one
0.9–5.66 s span and no detected leading burst. A real GUI turn invoked
`audio_measure`; after the explicit limitation was added, its final answer
correctly stated that it could not determine words, gibberish, pronunciation,
speaker identity, voice quality or acceptance.

### Video and embedded prompt

- `video_frames` extracted real native-resolution frames from `11.mp4` at 0 and
  2 seconds.
- `analyze_video` returned visual sequence evidence plus audio measurements.
- `read_video_metadata(11.mp4)` returned ref2va,
  `minimax_h3_ref2va_pruned_nvfp4.safetensors`, 0.2 MP, 20 steps and a prompt
  beginning `subject_definitions:`.
- `read_video_metadata(17.mp4)` found its sampler-inline prompt and both spoken
  lines, preserving the 2026-08-18 bug fix.

### Regression

- native function-calling suite: **8/8 passed**
- media-analysis suite: **4/4 passed**
- tool schemas: **22/22 present**
- existing guard refusals remain covered by the native suite
- H3 prompt validation: **124/124 valid**
- all changed Python files compile

## Available now versus gated

| capability | state |
|---|---|
| image understanding | active — installed `qwen3vl-abl:latest` |
| video visual understanding | active — FFmpeg frames + `qwen3vl-abl` |
| video/PNG Comfy metadata | active |
| audio timing/speech-density/artifact measurement | active |
| open speech transcription | gated — faster-whisper + model absent; estimated ~1.5 GB |
| speaker/voice similarity | gated — no local speaker-embedding model |

Vision yields whenever ComfyUI owns/listens on port 8188 or a render owns the
queue. Uploads remain accepted, but visual analysis reports the GPU conflict and
must be retried after rendering stops.
