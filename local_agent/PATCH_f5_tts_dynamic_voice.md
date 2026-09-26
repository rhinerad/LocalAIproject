# PATCH PROPOSAL: Dynamic audio cloning (CORRECTED) — STAGED

**Status:** review draft only.  
**Do not** edit live `dspy_orchestrator.py`, batch runner, or Comfy graphs yet.  
**Do not** run FFmpeg / F5-TTS / Comfy submits as part of this write-up.

## Correction vs prior proposal

| Wrong | Correct |
|---|---|
| Pull spoken line from DSPy / director `video_prompt` | Pull from **raw pack clip** (`managed_prompt_pack` / pack JSON) before any LLM rewrite |
| Static `master_voice_ref.wav` recorded offline | **C001 MiniMax native audio** becomes the clone ref for C002+ |
| F5 on every clip | F5 only on **C002+**; C001 uses MiniMax → `VHS_VideoCombine.audio` |

## 1) Raw dialogue extraction

Source of truth: the pack clip dict loaded by `managed_prompt_pack` (field is typically `video_prompt` on the raw clip, **not** `pred.video_prompt` after the director).

```python
import re
from typing import Any

_QUOTED = re.compile(
    r"""['\"]([^'\"]{2,240})['\"]"""  # first quoted span in pack motion text
)

def extract_raw_dialogue(clip: dict[str, Any]) -> str:
    """Spoken line from the original pack only — never from DSPy output."""
    # Prefer an explicit pack field if present later:
    for key in ("dialogue", "spoken_line", "line"):
        val = str(clip.get(key) or "").strip()
        if val:
            return val

    raw_motion = str(
        clip.get("video_prompt")
        or clip.get("motion_prompt")
        or clip.get("video")
        or ""
    )
    # Pack lines look like: ... says: "Hi, thanks for having me." ...
    m = _QUOTED.search(raw_motion)
    if m:
        return m.group(1).strip()

    # Fallback: text after says:/saying: without quotes
    m2 = re.search(
        r"(?:says|saying|said)\s*[:\-]\s*(.+)$",
        raw_motion,
        flags=re.IGNORECASE,
    )
    if m2:
        return m2.group(1).strip().strip(" .")

    return ""
```

**Usage rule:** call this on the **pack** `clip` object inside the batch loop. Never pass `pred.video_prompt` / director motion text into F5 `gen_text`.

```python
# batch loop (sketch)
for clip in pack_clips:
    clip_id = str(clip["id"]).upper()          # C001, C002, ...
    raw_dialogue = extract_raw_dialogue(clip)  # LOCKED to pack
    pred, hparams = resolve_pred(...)          # DSPy / literal — visuals only
    graph = build_minimax_picture_graph(pred, hparams, clip_id=clip_id)
    graph = route_audio_for_clip(
        graph,
        clip_id=clip_id,
        raw_dialogue=raw_dialogue,
        minimax_node="20",          # confirm live
        combine_node=None,          # auto-detect VHS_VideoCombine
    )
```

## 2) Conditional graph routing

```python
from __future__ import annotations
from pathlib import Path
from typing import Any

C001_VOICE_WAV = "C001_master_voice.wav"  # relative to ComfyUI/input/
F5_CLASS = "F5TTSAudio"                   # confirm via object_info


def _find_combine(graph: dict) -> str | None:
    for nid, node in graph.items():
        if isinstance(node, dict) and node.get("class_type") == "VHS_VideoCombine":
            return str(nid)
    return None


def route_audio_for_clip(
    graph: dict[str, Any],
    *,
    clip_id: str,
    raw_dialogue: str,
    minimax_node: str = "20",
    enable_f5: bool = True,
) -> dict[str, Any]:
    """C001: MiniMax native audio → combine.
    C002+: F5-TTS(C001_master_voice.wav, raw_dialogue) → combine.

    Fail-open: if F5 disabled/missing dialogue/ref, leave combine audio unset
    (silent) rather than crashing the batch.
    """
    g = {k: (dict(v) if isinstance(v, dict) else v) for k, v in graph.items()}
    combine_id = _find_combine(g)
    if combine_id is None:
        # Optional: create combine; wire images from MiniMax. Prefer retarget.
        combine_id = "92"
        g[combine_id] = {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": [minimax_node, 0],
                "frame_rate": 24,
                "filename_prefix": f"dspy_opt/gvd_br_{clip_id.lower()}",
                "format": "video/h264-mp4",
                "save_output": True,
            },
        }

    inputs = dict(g[combine_id].get("inputs") or {})
    cid = clip_id.upper()

    if cid in {"C001", "1"} or cid.endswith("001") and cid[-3:].isdigit() is False and cid == "C001":
        # --- CLIP 1: native MiniMax audio ---
        # MiniMaxH3ImageToVideo AUDIO output index must be confirmed (often 1).
        inputs["audio"] = [minimax_node, 1]
        # Ensure F5 nodes from a previous template mutation are gone
        for drop in ("90", "91"):
            g.pop(drop, None)
        g[combine_id] = {**g[combine_id], "inputs": inputs}
        return g

    # --- CLIP 2+: F5 clone from C001 master ---
    if not enable_f5 or not raw_dialogue.strip():
        inputs.pop("audio", None)  # silent fail-open
        g[combine_id] = {**g[combine_id], "inputs": inputs}
        return g

    g["90"] = {
        "class_type": "LoadAudio",
        "inputs": {"audio": C001_VOICE_WAV},
    }
    # ref_text: short frozen caption of C001's *pack* line (not director paraphrase)
    # Prefer storing C001's raw dialogue beside the wav when extracted.
    ref_text = _read_c001_ref_text()  # see hook below
    g["91"] = {
        "class_type": F5_CLASS,
        "inputs": {
            "ref_audio": ["90", 0],
            "ref_text": ref_text,
            "gen_text": raw_dialogue,  # UNMODIFIED pack dialogue
            "seed": 42,
        },
    }
    inputs["audio"] = ["91", 0]
    g[combine_id] = {**g[combine_id], "inputs": inputs}
    return g


def _read_c001_ref_text() -> str:
    """Transcript paired with C001_master_voice.wav (written by the C001 hook)."""
    # Path resolved relative to Comfy input dir by the runner; sketch only.
    p = Path("C001_master_voice.txt")
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return ""  # some F5 builds allow empty ref_text; prefer always writing it
```

### Graph dict shape (C001)

```json
{
  "20": { "class_type": "MiniMaxH3ImageToVideo", "inputs": { "...": "..." } },
  "25": {
    "class_type": "VHS_VideoCombine",
    "inputs": {
      "images": ["20", 0],
      "audio": ["20", 1],
      "filename_prefix": "dspy_opt/gvd_br_c001",
      "format": "video/h264-mp4"
    }
  }
}
```

### Graph dict shape (C002+)

```json
{
  "20": { "class_type": "MiniMaxH3ImageToVideo", "inputs": { "...": "..." } },
  "90": {
    "class_type": "LoadAudio",
    "inputs": { "audio": "C001_master_voice.wav" }
  },
  "91": {
    "class_type": "F5TTSAudio",
    "inputs": {
      "ref_audio": ["90", 0],
      "ref_text": "<exact C001 pack dialogue>",
      "gen_text": "<exact C002 pack dialogue>",
      "seed": 42
    }
  },
  "25": {
    "class_type": "VHS_VideoCombine",
    "inputs": {
      "images": ["20", 0],
      "audio": ["91", 0],
      "filename_prefix": "dspy_opt/gvd_br_c002",
      "format": "video/h264-mp4"
    }
  }
}
```

## 3) C001 post hook — lock the clone reference

After C001’s MP4 is on disk (and **before** starting C002), strip audio into Comfy’s input folder:

```python
import shutil
import subprocess
from pathlib import Path

def lock_c001_master_voice(
    c001_mp4: Path,
    *,
    comfy_input_dir: Path,
    c001_raw_dialogue: str,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    """Extract C001 audio → ComfyUI/input/C001_master_voice.wav (+ .txt).

    Fail-open: on error, log and return expected path anyway so C002 can
    decide to run silent rather than crash the batch.
    """
    comfy_input_dir.mkdir(parents=True, exist_ok=True)
    wav = comfy_input_dir / "C001_master_voice.wav"
    txt = comfy_input_dir / "C001_master_voice.txt"

    # Always persist the PACK dialogue used as F5 ref_text (not DSPy text).
    txt.write_text((c001_raw_dialogue or "").strip() + "\n", encoding="utf-8")

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(c001_mp4),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "24000",
        "-ac", "1",
        str(wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except Exception as exc:
        print(f"C001 master-voice extract failed ({exc}); C002+ may be silent")
    return wav
```

### Batch placement

```python
video_path = submit_and_wait(graph)   # existing Comfy path

if clip_id.upper() == "C001":
    lock_c001_master_voice(
        Path(video_path),
        comfy_input_dir=COMFY_INPUT_DIR,          # e.g. .../ComfyUI/input
        c001_raw_dialogue=raw_dialogue,         # from extract_raw_dialogue(clip)
    )

# Optional staged VHS post still OFF until baseline is stable.
# VLM QA grades video_path next.
```

## 4) Fail-safes (batch must not die)

1. **C001** MiniMax has no audio output → combine without `audio` (silent); still try ffmpeg (will fail-open); C002+ skip F5 if wav missing.  
2. **F5 node missing** / submit error → strip nodes `90`/`91`, clear combine `audio`, retry once.  
3. **Empty pack dialogue** → do not call F5; silent clip.  
4. **Never** fill `gen_text` from `pred.video_prompt`.

## 5) Acceptance (when implementation is allowed)

- C001 mux uses MiniMax audio index (verified in UI).  
- `ComfyUI/input/C001_master_voice.wav` + `.txt` exist after C001.  
- `.txt` bytes == pack-extracted C001 dialogue (not director paraphrase).  
- C002 `gen_text` == pack-extracted C002 dialogue character-for-character.  
- Uninstalling F5-TTS → C002+ still finish (silent).

## Out of scope for this document

- Applying the patch to live orch/batch  
- Installing ComfyUI-F5-TTS  
- Running ffmpeg or any render  
