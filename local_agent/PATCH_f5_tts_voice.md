# PATCH PROPOSAL: F5-TTS locked character voice (STAGED)

**Status:** architecture draft only.  
**Do not** edit live `dspy_orchestrator.py`.  
**Do not** execute Comfy submits, F5-TTS, or FFmpeg as part of this proposal.

## Problem

Passing the last visual frame into the next MiniMax I2V clip preserves picture continuity, not timbre. MiniMax (and similar I2V stacks) regenerate speech per clip, so the same character drifts across the 102-clip batch. Audio must be **decoupled** from the video model and driven by a fixed voice reference.

## Approach

1. Keep FLUX → MiniMax as the **picture** path (silent or ignore native MiniMax audio).
2. Add **ComfyUI-F5-TTS** to synthesize speech from:
   - static ref: `ComfyUI/input/master_voice_ref.wav`
   - static transcript: `ComfyUI/input/master_voice_ref.txt` (or text loaded into the node)
   - per-clip dialogue string from DSPy / literal override
3. Mux F5 audio into the MiniMax frame stream via `VHS_VideoCombine.audio`.
4. Fail-open: if F5-TTS is missing or errors, keep silent (or MiniMax native audio) so the batch never crashes.

## Assets (manual once)

Place in the Rockernow / Comfy **input** folder (same machine as `:8188`):

```
ComfyUI/input/master_voice_ref.wav
ComfyUI/input/master_voice_ref.txt   # exact words spoken in the wav
```

`master_voice_ref.txt` must match the reference take; F5-TTS uses it for speaker conditioning, not as the line to speak.

## Graph dictionary sketch (API prompt format)

Node IDs below are **proposal IDs** (`90`–`93`) so they do not collide with the existing FLUX/MiniMax scaffold (`6`/`7` CLIP, `20` MiniMax, etc.). Confirm the real MiniMax video tensor / image output link from the live template before wiring.

```json
{
  "90": {
    "class_type": "LoadAudio",
    "inputs": {
      "audio": "master_voice_ref.wav"
    }
  },
  "91": {
    "class_type": "F5TTSAudio",
    "inputs": {
      "ref_audio": ["90", 0],
      "ref_text": "{{MASTER_VOICE_REF_TEXT}}",
      "gen_text": "{{CLIP_DIALOGUE}}",
      "seed": 42,
      "model": "F5-TTS"
    }
  },
  "92": {
    "class_type": "VHS_VideoCombine",
    "inputs": {
      "images": ["20", 0],
      "audio": ["91", 0],
      "frame_rate": 24,
      "loop_count": 0,
      "filename_prefix": "dspy_opt/gvd_br_{{CLIP_ID}}",
      "format": "video/h264-mp4",
      "pingpong": false,
      "save_output": true
    }
  }
}
```

### Notes on class names

Exact `class_type` strings depend on the installed `ComfyUI-F5-TTS` pack (common variants: `F5TTSAudio`, `F5-TTS Voice`, `F5TTSGenerate`). Before wiring, read Comfy `object_info` once and substitute the real title. Same for whether ref text is a widget string vs a `LoadText` / file node.

If MiniMax already ends in a `VHS_VideoCombine`, **do not add a second combine** — retarget that node’s `audio` input from empty / MiniMax-audio to `["91", 0]` instead of introducing `92`.

### Desired signal flow

```
master_voice_ref.wav ──► LoadAudio(90) ──► F5TTS(91) ──► audio ──┐
DSPy dialogue ──────────────────────────► gen_text ─┘            │
MiniMax frames (node 20) ──────────────────────────────────────► VHS_VideoCombine ──► mp4
```

## Orchestrator injection (proposed only — do not apply yet)

In `dspy_orchestrator.py`, where the API graph dict is filled (same place that sets CLIP `6`/`7` and MiniMax `20` prompts):

```python
def _inject_f5_tts_voice(graph: dict, *, dialogue: str, clip_id: str, enable: bool) -> dict:
    """Attach F5-TTS + VHS audio mux when the custom node is available.

    Fail-open: if disabled, missing, or malformed, return graph unchanged
    (silent / native MiniMax audio path stays intact).
    """
    if not enable:
        return graph

    dialogue = (dialogue or "").strip()
    if not dialogue:
        return graph  # nothing to speak; leave silent

    # Optional capability probe (pseudo):
    # if "F5TTSAudio" not in comfy_object_info_class_types:
    #     print("F5-TTS missing; continuing without locked voice")
    #     return graph

    ref_text = Path(COMFY_INPUT / "master_voice_ref.txt").read_text(encoding="utf-8").strip()

    graph = dict(graph)  # shallow copy
    graph["90"] = {
        "class_type": "LoadAudio",
        "inputs": {"audio": "master_voice_ref.wav"},
    }
    graph["91"] = {
        "class_type": "F5TTSAudio",  # confirm against object_info
        "inputs": {
            "ref_audio": ["90", 0],
            "ref_text": ref_text,
            "gen_text": dialogue,
            "seed": 42,
            "model": "F5-TTS",
        },
    }

    # Prefer retargeting an existing VHS_VideoCombine if present:
    combine_id = next(
        (nid for nid, n in graph.items()
         if isinstance(n, dict) and n.get("class_type") == "VHS_VideoCombine"),
        None,
    )
    if combine_id is None:
        # Fallback: new combine; wire images from MiniMax node "20" (verify live).
        graph["92"] = {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["20", 0],
                "audio": ["91", 0],
                "frame_rate": 24,
                "filename_prefix": f"dspy_opt/gvd_br_{clip_id.lower()}",
                "format": "video/h264-mp4",
                "save_output": True,
            },
        }
    else:
        inputs = dict(graph[combine_id].get("inputs") or {})
        inputs["audio"] = ["91", 0]
        graph[combine_id] = {**graph[combine_id], "inputs": inputs}

    return graph
```

### Where dialogue comes from

```python
# After director / literal override resolves prompts:
dialogue = (
    getattr(pred, "dialogue", None)
    or getattr(pred, "spoken_line", None)
    or _extract_quoted_speech(getattr(pred, "video_prompt", ""))
    or ""
)

graph = build_minimax_graph(...)          # existing picture graph
graph = _inject_f5_tts_voice(
    graph,
    dialogue=dialogue,
    clip_id=clip_id,
    enable=os.environ.get("GVD_F5_TTS", "0") == "1",  # feature flag
)
```

Literal overrides (`clip_overrides/C00X.json`) can grow an optional `"dialogue"` field so C001’s line is explicit instead of regex-scraped from `video_prompt`.

### Submit-time fail-safe

```python
try:
    queued = orch.submit_prompt(graph)
except Exception as exc:
    if enable_f5 and _looks_like_missing_node(exc):
        print(f"F5-TTS submit failed ({exc}); retrying without voice lock")
        graph = _strip_f5_nodes(graph)   # drop 90/91; clear combine audio
        queued = orch.submit_prompt(graph)
    else:
        raise
```

Batch must **never** hard-fail solely because F5-TTS is absent.

## Interaction with staged VHS post (`PATCH_vhs_pipeline.md`)

Order when both are eventually enabled:

1. Comfy: MiniMax frames + F5 audio → `VHS_VideoCombine` MP4 (voice-locked)  
2. Optional later: `vhs_postprocess.apply_vhs_look` on that MP4  
3. Qwen-VL grades the path intended for QA  

Keep both feature-flagged and off until baseline picture prompt-literalism is stable.

## Acceptance criteria (when implementation is allowed)

- Same `master_voice_ref.wav` used for C001 and C002 → audible same speaker.  
- Changing only `gen_text` / `dialogue` changes words, not identity.  
- Uninstalling ComfyUI-F5-TTS → batch still completes (silent or native audio).  
- No edits to live orch in *this* proposal step (satisfied).

## Out of scope here

- Installing ComfyUI-F5-TTS  
- Writing `master_voice_ref.*`  
- Patching `dspy_orchestrator.py`  
- Any Comfy `/prompt` submit or test render  
