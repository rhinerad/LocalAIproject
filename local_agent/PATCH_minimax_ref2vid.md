# PATCH — MiniMax H3 Reference-To-Video for C002+ (STAGED)

**Status:** STAGED ONLY — do not apply while chasing Fish/F5.  
**Goal:** Keep C001 on `MiniMaxH3ImageToVideo` (proven). For C002+, condition MiniMax on C001 still + `C001_master_voice.wav` via `MiniMaxH3ReferenceToVideo`, then mux **MiniMax-native** audio (same decode path as C001). No Fish/F5.

## Assets (already staged into Comfy input)

- `A:\Users\rhine\ComfyUI-Shared\input\C001_ref_still.png` (from C001 FLUX still)
- `A:\Users\rhine\ComfyUI-Shared\input\C001_master_voice.wav` (from C001 native audio lock)

## New module

`local_agent/minimax_ref2vid.py`

- `wants_minimax_ref2vid(clip_id, override)` — **always False for C001**
- `apply_minimax_ref2vid(graph, video_prompt=...)` — swaps node `20` I2V → ReferenceToVideo + LoadImage/LoadAudio/audio VAE
- `attach_minimax_native_audio_mux(graph)` — C001-style VAEDecodeAudio → CreateVideo.audio

## Opt-in

In `clip_overrides/C002.json`:

```json
"minimax_ref2vid": true
```

Or env `GVD_MINIMAX_REF2VID=1` (still skips C001).

## Inject into `build_minimax_graph` (after `_apply_flux_minimax_node_map`, before Fish/F5 voice routing)

```python
from minimax_ref2vid import wants_minimax_ref2vid, apply_minimax_ref2vid, attach_minimax_native_audio_mux

# ... after graph = _apply_flux_minimax_node_map(...) ...
if wants_minimax_ref2vid(clip_id, override=None) and not stills_only:
    graph = apply_minimax_ref2vid(graph, video_prompt=str(video_prompt or ""))
    graph = attach_minimax_native_audio_mux(graph)
    # IMPORTANT: skip apply_dynamic_voice_routing Fish/F5 branch for this clip
elif not stills_only:
    graph = apply_dynamic_voice_routing(...)
```

Pass `clip_id` / override into `build_minimax_graph` if not already available.

## Prompt tags

ReferenceToVideo expects tags in the motion prompt:

- `<Picture 1>` — C001 still identity / wardrobe / room
- `<Audio 1>` — speak with the locked C001 master voice

`apply_minimax_ref2vid` auto-prepends/appends these if missing.

## Verify offline (no GPU)

```python
import json
from pathlib import Path
from minimax_ref2vid import apply_minimax_ref2vid, attach_minimax_native_audio_mux
g = json.loads(Path("graphs/flux_minimax_i2v_api.json").read_text())
prompt = g.get("prompt", g)
out = attach_minimax_native_audio_mux(apply_minimax_ref2vid(prompt, video_prompt="test line"))
assert out["20"]["class_type"] == "MiniMaxH3ReferenceToVideo"
assert out["50"]["class_type"] == "LoadImage"
assert out["51"]["class_type"] == "LoadAudio"
print("ok", out["20"]["inputs"].get("prompt")[:80])
```

## Execute later (only when greenlit)

```bat
python batch_run_backrooms_gvd.py --clip C002 --force
```

Do **not** re-run C001 unless intentionally refreshing the master voice/still.
