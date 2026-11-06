# -*- coding: utf-8 -*-
"""Dynamic audio cloning helpers for GVD batch / MiniMax.

Providers (explicit — never silently relabel Fish as F5):
  - minimax_native : C001 MiniMax audio VAE decode path
  - local_f5       : local F5TTSAudio (or GVD_LOCAL_F5_CLASS) node
  - fish_audio     : Fish Audio InstantVoiceClone + TextToSpeech (opt-in only)
  - none           : silent mux (only valid when dialogue is not required)

C001: MiniMax native audio -> CreateVideo.audio
C002+: local_f5 preferred; fish_audio only when GVD_VOICE_PROVIDER=fish_audio.
Fail-closed when dialogue is required: voice failure / silent fallback raises
VoiceAudioGateError instead of counting as success.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

C001_MASTER_VOICE_WAV = "C001_master_voice.wav"
C001_MASTER_VOICE_TXT = "C001_master_voice.txt"
MINIMAX_AUDIO_VAE_NAME = "minimax_h3_audio_vae_fp32.safetensors"

# Explicit provider env. Never default Fish under an F5 name.
VOICE_PROVIDER_ENV = "GVD_VOICE_PROVIDER"
LOCAL_F5_CLASS = os.environ.get("GVD_LOCAL_F5_CLASS", "F5TTSAudio")
F5_LOAD_AUDIO_CLASS = os.environ.get("GVD_F5_LOAD_AUDIO_CLASS", "LoadAudio")
FISH_CLONE_CLASS = os.environ.get("GVD_FISH_CLONE_CLASS", "FishAudioInstantVoiceClone")
FISH_TTS_CLASS = os.environ.get("GVD_FISH_TTS_CLASS", "FishAudioTextToSpeech")
FISH_TTS_MODEL = os.environ.get("GVD_FISH_TTS_MODEL", "s2.1-pro")

# Legacy env (deprecated): if set to a Fish class while provider unset, refuse.
_LEGACY_F5_TTS_CLASS = os.environ.get("GVD_F5_TTS_CLASS", "")

_QUOTED_DIALOGUE_RE = re.compile(r"['\"]([^'\"]{2,240})['\"]")
_TAGGED_DIALOGUE_RE = re.compile(
    r"<d>(?:\[.*?\])?\s*(.*?)</d>",
    flags=re.IGNORECASE | re.DOTALL,
)

VALID_PROVIDERS = frozenset({"minimax_native", "local_f5", "fish_audio", "none"})


class VoiceAudioGateError(RuntimeError):
    """Raised when required dialogue audio cannot be produced (fail-closed)."""


@dataclass
class DialogueLine:
    """speaker_id + exact text; voice_asset_id links a versioned VoiceAsset."""
    speaker: str
    text: str
    voice_asset_id: str | None = None

    @property
    def speaker_id(self) -> str:
        return self.speaker

    def to_dict(self) -> dict:
        return {
            "speaker_id": self.speaker,
            "speaker": self.speaker,
            "text": self.text,
            "voice_asset_id": self.voice_asset_id,
        }

    @classmethod
    def from_obj(cls, obj: Any) -> "DialogueLine | None":
        if not isinstance(obj, dict):
            return None
        text = str(
            obj.get("text")
            or obj.get("line")
            or obj.get("spoken_text")
            or obj.get("spoken_line")
            or ""
        ).strip()
        if not text:
            return None
        speaker = str(
            obj.get("speaker")
            or obj.get("speaker_id")
            or obj.get("character")
            or "unknown"
        ).strip() or "unknown"
        voice = obj.get("voice_asset_id")
        voice_s = str(voice).strip() if voice is not None else None
        return cls(speaker=speaker, text=text, voice_asset_id=voice_s or None)


@dataclass
class VoiceRoutingResult:
    provider: str
    status: str  # "ok" | "silent" | "failed"
    reason: str = ""
    required_dialogue: bool = False
    dialogue_lines: list[DialogueLine] = field(default_factory=list)

    @property
    def audio_pass(self) -> bool:
        if not self.required_dialogue:
            return True
        return self.status == "ok"


def normalize_dialogue_array(dialogue: Any) -> list[DialogueLine]:
    """Accept typed [{speaker,text,...}] or a bare string; return DialogueLine list."""
    if dialogue is None:
        return []
    if isinstance(dialogue, str):
        text = dialogue.strip()
        return [DialogueLine(speaker="unknown", text=text)] if text else []
    if isinstance(dialogue, dict):
        line = DialogueLine.from_obj(dialogue)
        return [line] if line else []
    if isinstance(dialogue, (list, tuple)):
        out: list[DialogueLine] = []
        for item in dialogue:
            if isinstance(item, DialogueLine):
                out.append(item)
                continue
            if isinstance(item, str) and item.strip():
                out.append(DialogueLine(speaker="unknown", text=item.strip()))
                continue
            line = DialogueLine.from_obj(item)
            if line:
                out.append(line)
        return out
    return []


def dialogue_to_speech_text(lines: list[DialogueLine]) -> str:
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0].text
    return " ".join(f"{ln.speaker}: {ln.text}" for ln in lines)


def extract_raw_dialogue(clip: dict | None) -> str:
    """Spoken line from the raw pack clip ONLY -- never from DSPy output."""
    lines = extract_dialogue_array(clip)
    return dialogue_to_speech_text(lines)


def extract_dialogue_array(clip: dict | None) -> list[DialogueLine]:
    """Typed dialogue array (speaker + text) from pack/override clip."""
    if not isinstance(clip, dict):
        return []
    # Prefer structured dialogue list
    for key in ("dialogue", "dialogue_lines", "spoken_lines"):
        val = clip.get(key)
        if isinstance(val, list) and val:
            lines = normalize_dialogue_array(val)
            if lines:
                return lines
        if isinstance(val, str) and val.strip():
            # May be a single string field named dialogue
            if key == "dialogue" and not any(
                isinstance(clip.get(k), list) for k in ("dialogue_lines", "spoken_lines")
            ):
                # Heuristic: if it looks like plain speech, keep as one line
                if "<d>" not in val and not val.strip().startswith("["):
                    return [DialogueLine(speaker="unknown", text=val.strip())]
    for key in ("spoken_line", "spoken_text", "line"):
        val = str(clip.get(key) or "").strip()
        if val:
            return [DialogueLine(speaker="unknown", text=val)]
    raw = str(
        clip.get("video_prompt")
        or clip.get("motion_prompt")
        or clip.get("video")
        or clip.get("body")
        or ""
    )
    m_tag = _TAGGED_DIALOGUE_RE.search(raw)
    if m_tag:
        text = re.sub(r"\s+", " ", m_tag.group(1)).strip().strip(" .")
        return [DialogueLine(speaker="unknown", text=text)] if text else []
    m = _QUOTED_DIALOGUE_RE.search(raw)
    if m:
        return [DialogueLine(speaker="unknown", text=m.group(1).strip())]
    m2 = re.search(
        r"(?:says|saying|said)\s*[,:\-]\s*(.+)$",
        raw,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if m2:
        line = m2.group(1).strip()
        m_inner = _TAGGED_DIALOGUE_RE.search(line)
        if m_inner:
            line = m_inner.group(1)
        text = re.sub(r"\s+", " ", line).strip().strip(" .")
        return [DialogueLine(speaker="unknown", text=text)] if text else []
    return []


def is_c001(clip_id: str) -> bool:
    cid = str(clip_id or "").strip().upper()
    if cid in {"C001", "1", "001"}:
        return True
    return cid.endswith("C001") or bool(re.search(r"(?:^|[_-])C?0*1$", cid))


def comfy_input_dir() -> Path:
    try:
        import mcp_client as _mcp

        return Path(_mcp.COMFYUI_PATH) / "input"
    except Exception:
        return Path("/workspace/pipeline_p0/comfy_input_stub")


def c001_master_voice_paths() -> tuple[Path, Path]:
    base = comfy_input_dir()
    return base / C001_MASTER_VOICE_WAV, base / C001_MASTER_VOICE_TXT


def lock_c001_master_voice(
    c001_mp4: str | Path,
    *,
    raw_dialogue: str = "",
    ffmpeg_bin: str | None = None,
) -> Path:
    """Strip C001 MP4 audio -> ComfyUI/input/C001_master_voice.wav (+ .txt)."""
    mp4 = Path(c001_mp4)
    wav, txt = c001_master_voice_paths()
    wav.parent.mkdir(parents=True, exist_ok=True)
    txt.write_text((raw_dialogue or "").strip() + "\n", encoding="utf-8")
    ff = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ff,
        "-y",
        "-i",
        str(mp4),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "24000",
        "-ac",
        "1",
        str(wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  C001 master voice locked -> {wav}")
    except Exception as exc:
        print(f"  C001 master-voice extract failed ({exc}); C002+ may lack ref audio")
    return wav


def resolve_voice_provider(
    *,
    clip_id: str = "",
    explicit: str | None = None,
    enable_voice: bool = True,
) -> str:
    """Return canonical provider name. Never silently call Fish 'F5'."""
    if is_c001(clip_id):
        return "minimax_native"
    if not enable_voice:
        return "none"
    raw = (explicit or os.environ.get(VOICE_PROVIDER_ENV) or "").strip().lower()
    if raw in ("f5", "f5_tts", "f5-tts"):
        raw = "local_f5"
    if raw in ("fish", "fishaudio", "fish-audio"):
        raw = "fish_audio"
    if raw in ("off", "silent", "disabled"):
        raw = "none"
    if raw:
        if raw not in VALID_PROVIDERS:
            raise VoiceAudioGateError(
                f"Unknown voice provider {raw!r}; expected one of {sorted(VALID_PROVIDERS)}"
            )
        return raw
    # Legacy trap: GVD_F5_TTS_CLASS pointing at Fish must not silently become "F5"
    # Read at call-time so operators can set/clear the env without reimport.
    legacy = str(os.environ.get("GVD_F5_TTS_CLASS") or _LEGACY_F5_TTS_CLASS or "").strip()
    if legacy and ("fish" in legacy.lower()):
        raise VoiceAudioGateError(
            f"GVD_F5_TTS_CLASS={legacy!r} names a Fish Audio node but was labeled F5. "
            f"Set {VOICE_PROVIDER_ENV}=fish_audio explicitly (or local_f5 with "
            f"GVD_LOCAL_F5_CLASS=F5TTSAudio). Refusing silent Fish-as-F5."
        )
    # Prefer local F5 when implementable from existing code.
    return "local_f5"


def _find_node_by_class(graph: dict, class_type: str) -> str | None:
    for nid, node in graph.items():
        if isinstance(node, dict) and str(node.get("class_type") or "") == class_type:
            return str(nid)
    return None


def strip_f5_voice_nodes(graph: dict) -> dict:
    """Remove voice-helper nodes and clear mux audio (silent fallback)."""
    if not isinstance(graph, dict):
        return graph
    for drop in ("90", "91", "92"):
        graph.pop(drop, None)
    for class_type in ("CreateVideo", "VHS_VideoCombine"):
        nid = _find_node_by_class(graph, class_type)
        if nid and isinstance(graph.get(nid), dict):
            inputs = dict(graph[nid].get("inputs") or {})
            inputs.pop("audio", None)
            graph[nid] = {**graph[nid], "inputs": inputs}
    return graph


def classify_voice_submit_error(exc: BaseException) -> str:
    """Classify Comfy submit / node errors for the audio gate.

    Returns one of: voice_node | class_type | other
    """
    msg = str(exc).lower()
    voice_keys = (
        "f5",
        "tts",
        "loadaudio",
        "vaedecodeaudio",
        "sanitizegeneratedaudio",
        "fishaudio",
        "voiceclone",
        "instantvoiceclone",
    )
    if any(k in msg for k in voice_keys):
        return "voice_node"
    if "class_type" in msg or ("node" in msg and "not" in msg):
        return "class_type"
    return "other"


def assert_audio_gate(result: VoiceRoutingResult) -> None:
    """Fail closed when dialogue was required but audio did not bind."""
    if result.required_dialogue and result.status != "ok":
        raise VoiceAudioGateError(
            f"audio gate failed: provider={result.provider} status={result.status} "
            f"reason={result.reason or 'required dialogue produced silence'}"
        )


def apply_dynamic_voice_routing(
    graph: dict,
    *,
    clip_id: str,
    raw_dialogue: str = "",
    dialogue: list | None = None,
    enable_f5: bool = True,
    voice_provider: str | None = None,
    require_audio: bool | None = None,
    fail_closed: bool = True,
) -> dict:
    """Route audio onto CreateVideo / VHS_VideoCombine.

    When dialogue is required and routing cannot bind real audio, raises
    VoiceAudioGateError (fail-closed) unless fail_closed=False.
    Stores VoiceRoutingResult on graph['_meta']['voice_routing'].
    """
    if not isinstance(graph, dict):
        return graph

    lines = normalize_dialogue_array(dialogue) if dialogue is not None else []
    if not lines and raw_dialogue:
        lines = normalize_dialogue_array(raw_dialogue)
    speech = dialogue_to_speech_text(lines)
    required = bool(require_audio) if require_audio is not None else bool(speech.strip())

    provider = resolve_voice_provider(
        clip_id=clip_id, explicit=voice_provider, enable_voice=bool(enable_f5)
    )

    g = graph
    create_id = _find_node_by_class(g, "CreateVideo")
    combine_id = _find_node_by_class(g, "VHS_VideoCombine")
    mux_id = create_id or combine_id

    def _finish(status: str, reason: str, *, bound: bool = False) -> dict:
        result = VoiceRoutingResult(
            provider=provider,
            status=status,
            reason=reason,
            required_dialogue=required,
            dialogue_lines=list(lines),
        )
        meta = g.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta["voice_routing"] = {
                "provider": result.provider,
                "status": result.status,
                "reason": result.reason,
                "required_dialogue": result.required_dialogue,
                "audio_pass": result.audio_pass,
                "dialogue": [
                    {"speaker": ln.speaker, "text": ln.text, "voice_asset_id": ln.voice_asset_id}
                    for ln in result.dialogue_lines
                ],
            }
        if fail_closed:
            assert_audio_gate(result)
        return g

    if mux_id is None:
        print("  voice routing: no CreateVideo/VHS_VideoCombine; leaving silent")
        return _finish("silent", "no mux node")

    for drop in ("42", "43", "44", "90", "91", "92"):
        g.pop(drop, None)

    inputs = dict(g[mux_id].get("inputs") or {})
    inputs.pop("audio", None)

    if provider == "minimax_native" or is_c001(clip_id):
        provider = "minimax_native"
        sampler_id = _find_node_by_class(g, "SamplerCustomAdvanced") or "37"
        g["42"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": MINIMAX_AUDIO_VAE_NAME},
        }
        g["43"] = {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": [sampler_id, 0], "vae": ["42", 0]},
        }
        g["44"] = {
            "class_type": "SanitizeGeneratedAudio",
            "inputs": {"audio": ["43", 0]},
        }
        inputs["audio"] = ["44", 0]
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: provider=minimax_native -> {mux_id}")
        return _finish("ok", "minimax native audio bound", bound=True)

    if provider == "none" or not enable_f5:
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: provider=none; silent")
        return _finish("silent", "voice disabled")

    if not speech:
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: empty dialogue; silent")
        return _finish("silent", "empty dialogue")

    wav, txt = c001_master_voice_paths()
    if not wav.is_file():
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(f"  voice routing [{clip_id}]: missing {wav.name}; cannot clone")
        return _finish("failed", f"missing reference wav {wav.name}")

    ref_text = txt.read_text(encoding="utf-8").strip() if txt.is_file() else ""
    if not ref_text:
        ref_text = speech

    g["90"] = {
        "class_type": F5_LOAD_AUDIO_CLASS,
        "inputs": {"audio": C001_MASTER_VOICE_WAV},
    }

    if provider == "fish_audio":
        g["92"] = {
            "class_type": FISH_CLONE_CLASS,
            "inputs": {
                "enhance_audio_quality": True,
                "files.audio0": ["90", 0],
            },
        }
        model = str(FISH_TTS_MODEL or "s2.1-pro")
        tts_inputs: dict = {
            "text": speech,
            "model": model,
            "seed": 42,
        }
        if model == "s1":
            tts_inputs.update(
                {
                    "model.temperature": 0.7,
                    "model.top_p": 0.7,
                    "model.speed": 1.0,
                    "model.volume": 0.0,
                    "model.normalize": True,
                    "model.voice": ["92", 0],
                }
            )
        else:
            tts_inputs.update(
                {
                    "model.temperature": 0.7,
                    "model.top_p": 0.7,
                    "model.speed": 1.0,
                    "model.volume": 0.0,
                    "model.normalize": True,
                    "model.voices.voice0": ["92", 0],
                }
            )
        g["91"] = {
            "class_type": FISH_TTS_CLASS,
            "inputs": tts_inputs,
        }
        inputs["audio"] = ["91", 0]
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(
            f"  voice routing [{clip_id}]: provider=fish_audio "
            f"{FISH_CLONE_CLASS}+{FISH_TTS_CLASS} gen_text={speech[:60]!r} -> {mux_id}"
        )
        return _finish("ok", "fish_audio bound", bound=True)

    if provider == "local_f5":
        clone_class = str(LOCAL_F5_CLASS or "F5TTSAudio")
        if "fish" in clone_class.lower():
            raise VoiceAudioGateError(
                f"provider=local_f5 but GVD_LOCAL_F5_CLASS={clone_class!r} is a Fish node. "
                "Refusing silent Fish-as-F5. Use GVD_VOICE_PROVIDER=fish_audio instead."
            )
        g["91"] = {
            "class_type": clone_class,
            "inputs": {
                "ref_audio": ["90", 0],
                "audio": ["90", 0],
                "sample": ["90", 0],
                "ref_text": ref_text,
                "gen_text": speech,
                "text": speech,
                "seed": 42,
            },
        }
        inputs["audio"] = ["91", 0]
        g[mux_id] = {**g[mux_id], "inputs": inputs}
        print(
            f"  voice routing [{clip_id}]: provider=local_f5 class={clone_class} "
            f"gen_text={speech[:60]!r} -> {mux_id}"
        )
        return _finish("ok", f"local_f5 ({clone_class}) bound", bound=True)

    raise VoiceAudioGateError(f"Unhandled voice provider: {provider}")


# --- Versioned voice assets + shot audio modes (audit §10) -----------------

from enum import Enum


class ShotAudioMode(str, Enum):
    NARRATION_OVER_PICTURE = "narration_over_picture"
    VISIBLE_DIALOGUE = "visible_dialogue"
    NATIVE_H3_AUDIO = "native_h3_audio"
    SILENT_ABSTRACT = "silent_abstract"


SHOT_AUDIO_MODES = frozenset(m.value for m in ShotAudioMode)


@dataclass
class VoiceAsset:
    """Versioned voice asset (replaces shared C001 master-voice assumption)."""
    job_id: str
    speaker_id: str
    voice_version: str
    reference_audio_hash: str
    reference_transcript_hash: str
    tts_backend: str
    checkpoint_hash: str
    language: str = "en"
    delivery_params: dict = field(default_factory=dict)
    reference_audio_path: str | None = None
    reference_transcript: str | None = None
    asset_id: str | None = None

    def __post_init__(self) -> None:
        if self.asset_id is None:
            self.asset_id = f"voice:{self.job_id}:{self.speaker_id}@{self.voice_version}"

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "job_id": self.job_id,
            "speaker_id": self.speaker_id,
            "voice_version": self.voice_version,
            "reference_audio_hash": self.reference_audio_hash,
            "reference_transcript_hash": self.reference_transcript_hash,
            "tts_backend": self.tts_backend,
            "checkpoint_hash": self.checkpoint_hash,
            "language": self.language,
            "delivery_params": dict(self.delivery_params),
            "reference_audio_path": self.reference_audio_path,
            "reference_transcript": self.reference_transcript,
        }

    @classmethod
    def from_dict(cls, obj: Any) -> "VoiceAsset":
        if not isinstance(obj, dict):
            raise VoiceAudioGateError("VoiceAsset.from_dict expects a dict")
        return cls(
            job_id=str(obj["job_id"]),
            speaker_id=str(obj["speaker_id"]),
            voice_version=str(obj["voice_version"]),
            reference_audio_hash=str(obj["reference_audio_hash"]),
            reference_transcript_hash=str(obj["reference_transcript_hash"]),
            tts_backend=str(obj["tts_backend"]),
            checkpoint_hash=str(obj["checkpoint_hash"]),
            language=str(obj.get("language") or "en"),
            delivery_params=dict(obj.get("delivery_params") or {}),
            reference_audio_path=(
                str(obj["reference_audio_path"]) if obj.get("reference_audio_path") else None
            ),
            reference_transcript=(
                str(obj["reference_transcript"]) if obj.get("reference_transcript") else None
            ),
            asset_id=(str(obj["asset_id"]) if obj.get("asset_id") else None),
        )


def gate_shot_audio_mode(
    *,
    mode: str,
    dialogue_lines: list | None = None,
    intentional_silence: bool = False,
) -> None:
    """Fail closed when required dialogue conflicts with silent mode."""
    mode_s = str(mode or "").strip()
    if mode_s not in SHOT_AUDIO_MODES:
        raise VoiceAudioGateError(
            f"unknown shot audio mode {mode_s!r}; expected {sorted(SHOT_AUDIO_MODES)}"
        )
    lines = normalize_dialogue_array(dialogue_lines)
    has_dialogue = bool(lines)
    if mode_s == ShotAudioMode.SILENT_ABSTRACT.value:
        if has_dialogue:
            raise VoiceAudioGateError(
                "required dialogue + silent_abstract mode conflict"
            )
        if not intentional_silence:
            raise VoiceAudioGateError(
                "silent_abstract requires intentional_silence=True"
            )
        return
    if intentional_silence:
        raise VoiceAudioGateError(
            "intentional_silence only valid with silent_abstract"
        )
    if mode_s in {
        ShotAudioMode.VISIBLE_DIALOGUE.value,
        ShotAudioMode.NARRATION_OVER_PICTURE.value,
    } and not has_dialogue:
        raise VoiceAudioGateError(f"mode {mode_s} requires dialogue/narration text")


@dataclass
class LocalF5InferArgs:
    """CLI-shaped args matching f5-tts_infer-cli (no network invocation)."""
    ref_audio: str
    ref_text: str
    gen_text: str
    output_dir: str | None = None
    model: str | None = None
    checkpoint: str | None = None

    def to_argv(self, *, binary: str = "f5-tts_infer-cli") -> list[str]:
        argv = [
            binary,
            "--ref_audio", self.ref_audio,
            "--ref_text", self.ref_text,
            "--gen_text", self.gen_text,
        ]
        if self.output_dir:
            argv.extend(["--output_dir", self.output_dir])
        if self.model:
            argv.extend(["--model", self.model])
        if self.checkpoint:
            argv.extend(["--checkpoint", self.checkpoint])
        return argv

    def to_dict(self) -> dict:
        return {
            "ref_audio": self.ref_audio,
            "ref_text": self.ref_text,
            "gen_text": self.gen_text,
            "output_dir": self.output_dir,
            "model": self.model,
            "checkpoint": self.checkpoint,
        }


def build_local_f5_infer_args(
    *,
    voice: VoiceAsset | None = None,
    ref_audio: str | None = None,
    ref_text: str | None = None,
    gen_text: str,
    provider: str | None = None,
    output_dir: str | None = None,
) -> LocalF5InferArgs:
    """Build f5-tts_infer-cli-shaped args. Fail closed on provider mismatch.

    Does NOT invoke the network or spawn the CLI — documentation / dry-run only.
    """
    if provider is not None:
        raw = str(provider).strip().lower()
        if raw in ("f5", "f5_tts", "f5-tts"):
            raw = "local_f5"
        if raw != "local_f5":
            raise VoiceAudioGateError(
                f"local_f5 helper refuse: provider={raw!r} (expected local_f5)"
            )
    else:
        expected = resolve_voice_provider(explicit=None, enable_voice=True, clip_id="C002")
        if expected != "local_f5":
            raise VoiceAudioGateError(
                f"local_f5 helper refuse: resolved provider={expected!r} "
                f"(set GVD_VOICE_PROVIDER=local_f5 or pass provider='local_f5')"
            )

    ckpt = None
    if voice is not None:
        if voice.tts_backend not in ("local_f5", "f5", "f5_tts", "F5TTSAudio"):
            raise VoiceAudioGateError(
                f"voice.tts_backend={voice.tts_backend!r} incompatible with local_f5 path"
            )
        ref_audio = ref_audio or voice.reference_audio_path
        if ref_text is None:
            ref_text = voice.reference_transcript or ""
        ckpt = voice.checkpoint_hash

    if not ref_audio:
        raise VoiceAudioGateError("local_f5 requires ref_audio (or voice.reference_audio_path)")
    if ref_text is None or not str(ref_text).strip():
        raise VoiceAudioGateError("local_f5 requires ref_text")
    if not str(gen_text or "").strip():
        raise VoiceAudioGateError("local_f5 requires gen_text")

    return LocalF5InferArgs(
        ref_audio=str(ref_audio),
        ref_text=str(ref_text).strip(),
        gen_text=str(gen_text).strip(),
        output_dir=output_dir,
        checkpoint=ckpt,
    )


def store_dialogue_lines(lines: list | None) -> list[dict]:
    """Normalize dialogue for production_store / timeline persistence."""
    out: list[dict] = []
    for ln in normalize_dialogue_array(lines):
        out.append(ln.to_dict())
    return out
