# Upgrade 4 — build the eyes and ears now, switch them on later. No internet needed.

**Implemented 2026-08-22.** The already-installed `qwen3vl-abl` activates
vision now; FFmpeg frame extraction, media metadata and audio measurement are
active. The existing ComfyUI Whisper-tiny checkpoint now provides offline
English transcription through the installed OpenAI decoder. Speaker comparison
remains explicitly gated because no speaker-embedding model is installed. See
`CHANGELOG/2026-08-22_sensory_end_to_end.md`.

Paste everything below the line into Claude Code. Run **after** upgrades 1–3.

---

Build every vision and audio tool **now**, fully wired and tested, returning a
clear "model not installed" until the downloads land. **No downloads in this
prompt.** When the models arrive nothing needs rewiring — the tools start working.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## The principle

The main chat model stays **text-only and smart**. Vision and audio are *tools it
calls*, not a multimodal model it becomes. That way you never trade reasoning
quality for the ability to look at a frame, and each sense can be swapped
independently.

## Job 1 — a capability registry

New file `local_agent/capabilities.py`. One place that answers "is this available
right now, and if not, exactly what is missing."

```python
capability("vision")  -> {"available": bool, "reason": str, "install": str, "size": str}
```

Check for: an Ollama vision model on the GPU host, an embeddings model, and
`faster_whisper` importable. Every gated tool asks here first and returns the
`install` hint on failure — so the agent can tell you precisely what to download,
with the size, rather than failing vaguely.

Add a `capabilities` tool so you can ask "what can you do right now?"

## Job 2 — vision tools, gated

- **`see_image`** — `{"path": "...", "question": "..."}`. Base64-encodes the
  image into an Ollama `/api/chat` request with an `images` array. Gated on a
  vision model being present.
- **`video_frames`** — `{"path": "...", "at": [1.0, 4.5]}` or `every_n_seconds`.
  Extracts frames with **ffmpeg**, which is already on this machine (the project
  uses it for `ffprobe`). **This one works today, no model needed.**
- **`read_video_metadata`** — `{"path": "..."}`. Extracts the embedded ComfyUI
  graph from an MP4 or PNG and reports node, checkpoint, megapixels, steps, seed,
  duration, references, and the prompt text. The logic already exists in
  `work/harvest_good_audio_masters.py` — reuse it, do not rewrite it. **Works
  today.** Note the bug fixed there: read the prompt from *any* node input named
  `prompt`, not only `PrimitiveStringMultiline`, or inline-prompt graphs come back
  empty.

Critical instruction for `see_image` once a model exists: this project measured
that **contact sheets caught every large-area fault and missed every face-level
one**, because a face at reduced scale is unreadable. So `see_image` must pass
native-resolution crops, never downscaled full frames, when the question is about
a face or hands. Build cropping in now.

## Job 3 — audio tools, gated

- **`transcribe`** — `{"path": "...", "expected_text": "..."}`. Uses
  `faster_whisper` if importable. When `expected_text` is supplied, report a
  word-level diff, not just a transcript — you almost always know what *should*
  have been said, which makes this verification rather than open transcription.
- **`audio_measure`** — duration, speech seconds, speech density, leading-burst
  detection, quiet tail. Wrap the existing `work/speech_density.py` and the
  analysis in `work/harvest_good_audio_masters.py`. **Works today, no model.**
- **`compare_voice`** — `{"a": "...", "b": "..."}`, speaker similarity. Gate it
  and return the install hint; the model comes later.

## Job 4 — honesty rules the agent must follow

Add to `CONVERSATION_RULES`:

- when a sensory tool is unavailable, say **what** is missing and **how big** the
  download is — never pretend, never guess at content
- a transcript is **evidence, not acceptance**. The operator accepts takes by
  ear. Existing project rule: an empty transcript means *unknown*, never
  *perfect*.
- never describe an image it has not actually passed through `see_image`
- always report the measurement alongside the judgement — "78% speech density"
  not "sounds fine"

## Verify

Tools that must work **today**:

- [ ] `video_frames` extracts real frames from a real project MP4
- [ ] `read_video_metadata` on
      `ComfyUI-Shared\output\video\good audio\11.mp4` returns ref2va,
      `minimax_h3_ref2va_pruned_nvfp4`, 0.2 MP, 20 steps, and a prompt starting
      `subject_definitions:`
- [ ] the same tool on `17.mp4` correctly finds its **inline** prompt and reports
      the two spoken lines — this is the bug that made an earlier pass report
      "no dialogue"
- [ ] `audio_measure` on a good-audio take matches `speech_density.py`

Tools that must **fail cleanly**:

- [ ] `see_image`, `transcribe`, `compare_voice` each return a specific missing
      component and its download size
- [ ] `capabilities` lists all of them accurately
- [ ] the agent, asked to look at a frame, says what is missing instead of
      inventing a description

And:

- [ ] guard rails still refuse; `validate_h3_prompt.py` still **124/124**

## Do not stop

Stop only when every box is ticked and the `CHANGELOG/` entry is written, listing
exactly which capabilities are gated and what each one needs.
