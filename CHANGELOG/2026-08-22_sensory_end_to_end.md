# Image watcher, video watcher and audio listener verified — 2026-08-22

## What changed

- `local_agent/media_tools.py`
  - vision automatically uses the GPU when free and the isolated four-thread
    CPU Ollama server when ComfyUI/rendering owns the GPU
  - vision results report the tier, host, model and GPU-state reason
  - transcription uses the existing local ComfyUI Whisper-tiny checkpoint
  - CPU Ollama is evicted before Whisper so only one local CPU inference model
    is resident at a time
- `local_agent/capabilities.py` detects the existing Whisper checkpoint and
  compatible ComfyUI Python environment without downloading anything. Vision
  capability reporting now gives the selected installed model's actual Ollama
  size and does not show install/download instructions when vision is active.
  Vision selection is host-specific because the CPU and GPU Ollama services can
  expose different model stores/tags.
- `local_agent/whisper_transcribe_worker.py` maps all 167 Hugging Face
  safetensor names to the installed OpenAI Whisper decoder and refuses any
  incomplete or mismatched map. It runs offline, CPU-only, with four threads.
- Knowledge, README, sensory roadmap and regression tests were updated.

## Why

Attachment plumbing and waveform measurements worked, but transcription was
incorrectly reported unavailable. The checkpoint was under
`ComfyUI-Shared/models/sonicLipsyncFor_comfyui/sonic/whisper-tiny`. Generic
Transformers decoding proved impractical on CPU; the installed OpenAI decoder
using the identical 167 tensors completed promptly.

## Evidence

- Real PNG: CPU `qwen3vl-abl` returned grounded subjects, setting, composition,
  lighting, camera, visible action and spatial relationships while port 8188
  remained open.
- Real MP4: native-resolution samples at 0 and 2 seconds were analyzed together;
  duration was 9.417 s and audio measurement reported 6.76 s speech.
- Real WAV `00C.wav`: Whisper returned the complete sentence beginning “When no
  one else feels…” through the public `transcribe` tool.
- Real MP4 `11.mp4`: Whisper returned two timestamped English segments through
  the same tool. Its first phrase contained an apparent recognition error,
  confirming why Whisper-tiny output remains evidence rather than acceptance.
- No download occurred. NVIDIA remained idle while CPU sensory fallbacks ran.
- Live GUI SSE turn emitted `tool=transcribe`, a `tool_result`, streamed answer
  tokens and `done`; the final answer contained the 21-word transcript.
- `START_LOCAL_AGENT_GUI.ps1` repaired a dead CPU Ollama service even while the
  web app was already open. Previously it exited early and left that half-started
  state in place.
- A live preferred-model check caught that the GPU service had
  `qwen3-vl-abliterated:8b-q8_0` while the CPU service had `qwen3vl-abl:latest`.
  The watcher now chooses per host instead of sending a GPU-only tag to CPU and
  receiving HTTP 404.
- The final restart check exposed two Windows listeners on port 8760. `server.py`
  now claims the named mutex `Local\\EqualSharesLocalAgent8760` before binding,
  preventing duplicate web-agent processes even when Windows permits the socket
  reuse.

## Safety preserved

- A render/ComfyUI backend is never displaced or competed with for GPU memory.
- CPU work remains four-thread capped.
- Binary data is stored out of chat history; only paths/results enter context.
- Audio measurement cannot claim words, speakers, music, sound events or
  acceptance. Whisper cannot establish speaker identity or acceptance.

## Still unavailable

- speaker-identity embedding/comparison
- general music and sound-event recognition
