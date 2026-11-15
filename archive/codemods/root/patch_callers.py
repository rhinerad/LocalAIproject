#!/usr/bin/env python3
"""Wire audio Autogrow into batch_render_folder and native-voice guard into generate_video."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])


def patch_batch_render():
    path = ROOT / "work" / "batch_render_folder.py"
    text = path.read_text(encoding="utf-8")
    if "ref_audios.ref_audio_" in text and "audio_filenames" in text:
        print("batch_render already has audio_filenames support")
    else:
        # Extend build_batch_workflow signature
        old_sig = (
            "def build_batch_workflow(\n"
            "    image_filenames: list[str],\n"
            "    video_filename:  str | None,\n"
            "    prompt_text:     str,\n"
            "    duration:        float,\n"
            "    seed:            int,\n"
            "    out_prefix:      str,\n"
            "    megapixels:      float = DEFAULT_MP,\n"
            ") -> dict:"
        )
        new_sig = (
            "def build_batch_workflow(\n"
            "    image_filenames: list[str],\n"
            "    video_filename:  str | None,\n"
            "    prompt_text:     str,\n"
            "    duration:        float,\n"
            "    seed:            int,\n"
            "    out_prefix:      str,\n"
            "    megapixels:      float = DEFAULT_MP,\n"
            "    audio_filenames: list[str] | None = None,\n"
            "    character_ids_for_audio: list[str] | None = None,\n"
            ") -> dict:"
        )
        if old_sig not in text:
            raise SystemExit("build_batch_workflow signature not found")
        text = text.replace(old_sig, new_sig, 1)
        # Insert audio slot wiring after image slots loop
        marker = (
            "    for i, img_fname in enumerate(image_filenames):\n"
            "        img_node = f\"300_{i}\"\n"
            "        wf[img_node] = {\"class_type\": \"LoadImage\", \"inputs\": {\"image\": img_fname}}\n"
            "        ref_inputs[f\"ref_images.ref_image_{i}\"] = [img_node, 0]\n"
        )
        audio_block = marker + (
            "\n"
            "    # Audio slots (zero-based socket -> <Audio N+1>); voice identity only\n"
            "    audio_filenames = list(audio_filenames or [])\n"
            "    if len(audio_filenames) > 3:\n"
            "        raise ValueError(\n"
            "            f\"{len(audio_filenames)} audio refs exceed MiniMax max 3; split/replan shot\"\n"
            "        )\n"
            "    for i, aud_fname in enumerate(audio_filenames):\n"
            "        aud_node = f\"310_{i}\"\n"
            "        wf[aud_node] = {\"class_type\": \"LoadAudio\", \"inputs\": {\"audio\": aud_fname}}\n"
            "        ref_inputs[f\"ref_audios.ref_audio_{i}\"] = [aud_node, 0]\n"
            "    # Optional character mapping note for prompt authors / callers\n"
            "    if character_ids_for_audio:\n"
            "        if len(character_ids_for_audio) != len(audio_filenames):\n"
            "            raise ValueError(\"character_ids_for_audio length must match audio_filenames\")\n"
        )
        if marker not in text:
            raise SystemExit("image slot loop not found")
        text = text.replace(marker, audio_block, 1)
        # Update docstring socket map
        text = text.replace(
            "      ref_videos.ref_video_0  ->  <Video 1>   (motion only, no audio paired)\n",
            "      ref_videos.ref_video_0  ->  <Video 1>   (motion only, no audio paired)\n"
            "      ref_audios.ref_audio_0  ->  <Audio 1>   (voice identity; map to character_id)\n",
            1,
        )
        path.write_text(text, encoding="utf-8")
        print("patched batch_render_folder audio Autogrow")

    # Ensure sys.path can import handoff root helpers when invoked from work/
    text = path.read_text(encoding="utf-8")
    if "gvd_graph_builder" not in text:
        boot = (
            "\n# Shared production Autogrow helpers (handoff root)\n"
            "import sys as _sys\n"
            "from pathlib import Path as _Path\n"
            "_HANDOFF = _Path(__file__).resolve().parents[1]\n"
            "if str(_HANDOFF) not in _sys.path:\n"
            "    _sys.path.insert(0, str(_HANDOFF))\n"
            "try:\n"
            "    import gvd_graph_builder as _ggb  # noqa: F401\n"
            "except Exception:\n"
            "    _ggb = None\n"
        )
        if "from __future__ import annotations" in text:
            text = text.replace(
                "from __future__ import annotations\n",
                "from __future__ import annotations\n" + boot,
                1,
            )
            path.write_text(text, encoding="utf-8")
            print("added gvd_graph_builder import path to batch_render")


def patch_generate_video():
    path = ROOT / "generate_video.py"
    text = path.read_text(encoding="utf-8")
    if "native_minimax_voice_required" in text and "forbid_tts_fallback" in text:
        print("generate_video already guarded")
        return
    boot = (
        "\ntry:\n"
        "    import native_voice_continuity as _nvc\n"
        "except Exception:  # pragma: no cover\n"
        "    _nvc = None\n"
        "try:\n"
        "    import gvd_graph_builder as _ggb  # noqa: F401\n"
        "except Exception:\n"
        "    _ggb = None\n"
    )
    if "from __future__ import annotations" in text and "import native_voice_continuity" not in text:
        text = text.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n" + boot,
            1,
        )
    # Add CLI flags
    if "--native-minimax-voice" not in text:
        needle = '"--voice-provider"'
        idx = text.find(needle)
        if idx < 0:
            raise SystemExit("voice-provider arg missing")
        # find the add_argument block start roughly
        insert = (
            "    parser.add_argument(\n"
            "        \"--native-minimax-voice\",\n"
            "        action=\"store_true\",\n"
            "        help=\"Require native MiniMax voice conditioning; forbid silent F5/Fish fallback.\",\n"
            "    )\n"
            "    parser.add_argument(\n"
            "        \"--voice-ref-json\",\n"
            "        default=None,\n"
            "        help='JSON list of {character_id,comfy_input_name,exact_transcript} for Autogrow audio refs.',\n"
            "    )\n"
            "    parser.add_argument(\n"
            "        \"--image-ref-json\",\n"
            "        default=None,\n"
            "        help='JSON list of {comfy_input_name,character_id?} for Autogrow image refs.',\n"
            "    )\n"
        )
        # insert before --voice-provider
        text = text.replace(
            '    parser.add_argument(\n        "--voice-provider"',
            insert + '    parser.add_argument(\n        "--voice-provider"',
            1,
        )
    # Guard in submit_comfy / main: after voice_provider resolved
    guard_fn = '''

def enforce_native_voice_cli(args) -> None:
    """Fail closed when native MiniMax voice is required but TTS provider selected."""
    native = bool(getattr(args, "native_minimax_voice", False))
    provider = getattr(args, "voice_provider", None)
    if not native:
        return
    if _nvc is None:
        raise RuntimeError("native_voice_continuity unavailable")
    _nvc.forbid_tts_fallback(provider, native_required=True)


def load_ref_binding_plan_from_args(args):
    """Optional RefBindingPlan for callers that mutate graphs post-director."""
    if _ggb is None:
        return None
    import json
    images = []
    audios = []
    if getattr(args, "image_ref_json", None):
        raw = args.image_ref_json
        data = json.loads(Path(raw).read_text(encoding="utf-8") if str(raw).endswith(".json") and Path(str(raw)).is_file() else raw)
        for item in data:
            images.append(_ggb.ImageRef(
                comfy_input_name=str(item["comfy_input_name"]),
                character_id=(str(item["character_id"]) if item.get("character_id") else None),
            ))
    if getattr(args, "voice_ref_json", None):
        raw = args.voice_ref_json
        data = json.loads(Path(raw).read_text(encoding="utf-8") if str(raw).endswith(".json") and Path(str(raw)).is_file() else raw)
        for item in data:
            audios.append(_ggb.AudioRef(
                comfy_input_name=str(item["comfy_input_name"]),
                character_id=str(item["character_id"]),
                exact_transcript=str(item.get("exact_transcript") or item.get("transcript") or ""),
            ))
    if not images and not audios:
        return None
    plan = _ggb.RefBindingPlan(images=images, audios=audios)
    plan.validate()
    return plan

'''
    if "def enforce_native_voice_cli" not in text:
        text = text.replace("\ndef submit_comfy(", "\n" + guard_fn + "\ndef submit_comfy(", 1)
    # Call enforce in main if present
    if "enforce_native_voice_cli(args)" not in text:
        # after args = parser.parse_args()
        if "args = parser.parse_args()" in text:
            text = text.replace(
                "args = parser.parse_args()",
                "args = parser.parse_args()\n    enforce_native_voice_cli(args)",
                1,
            )
        elif "args = build_argparser().parse_args()" in text:
            text = text.replace(
                "args = build_argparser().parse_args()",
                "args = build_argparser().parse_args()\n    enforce_native_voice_cli(args)",
                1,
            )
    path.write_text(text, encoding="utf-8")
    print("patched generate_video native voice CLI")


if __name__ == "__main__":
    patch_batch_render()
    patch_generate_video()
