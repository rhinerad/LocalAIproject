#!/usr/bin/env python3
"""Offline CPU-only transcription using the Whisper checkpoint already in ComfyUI.

This helper runs under ComfyUI's Python because the local-agent stdlib runtime
does not carry Torch/Transformers. It never resolves a remote model identifier:
the model directory and media path are required local paths.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: whisper_transcribe_worker.py AUDIO MODEL_DIR")
    audio_path = Path(sys.argv[1]).resolve()
    model_dir = Path(sys.argv[2]).resolve()
    if not audio_path.is_file():
        raise SystemExit(f"audio not found: {audio_path}")
    required = ("config.json", "preprocessor_config.json", "model.safetensors")
    if not model_dir.is_dir() or any(not (model_dir / n).is_file() for n in required):
        raise SystemExit(f"incomplete local Whisper model: {model_dir}")

    import torch
    import whisper
    from safetensors.torch import load_file
    from whisper.model import ModelDimensions, Whisper

    device = os.environ.get("EQUAL_SHARES_WHISPER_DEVICE", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("Whisper requested CUDA but Torch cannot see the GPU")
    torch.set_num_threads(4)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    dims = ModelDimensions(
        n_mels=config["num_mel_bins"],
        n_audio_ctx=config["max_source_positions"],
        n_audio_state=config["d_model"],
        n_audio_head=config["encoder_attention_heads"],
        n_audio_layer=config["encoder_layers"],
        n_vocab=config["vocab_size"],
        n_text_ctx=config["max_target_positions"],
        n_text_state=config["d_model"],
        n_text_head=config["decoder_attention_heads"],
        n_text_layer=config["decoder_layers"],
    )
    model = Whisper(dims)

    def openai_key(key: str) -> str:
        exact = {
            "model.encoder.embed_positions.weight": "encoder.positional_embedding",
            "model.encoder.layer_norm.weight": "encoder.ln_post.weight",
            "model.encoder.layer_norm.bias": "encoder.ln_post.bias",
            "model.decoder.embed_positions.weight": "decoder.positional_embedding",
            "model.decoder.embed_tokens.weight": "decoder.token_embedding.weight",
            "model.decoder.layer_norm.weight": "decoder.ln.weight",
            "model.decoder.layer_norm.bias": "decoder.ln.bias",
        }
        if key in exact:
            return exact[key]
        key = key.replace("model.encoder.conv", "encoder.conv")
        key = key.replace("model.encoder.layers.", "encoder.blocks.")
        key = key.replace("model.decoder.layers.", "decoder.blocks.")
        key = key.replace(".self_attn_layer_norm.", ".attn_ln.")
        key = key.replace(".encoder_attn_layer_norm.", ".cross_attn_ln.")
        key = key.replace(".self_attn.q_proj.", ".attn.query.")
        key = key.replace(".self_attn.k_proj.", ".attn.key.")
        key = key.replace(".self_attn.v_proj.", ".attn.value.")
        key = key.replace(".self_attn.out_proj.", ".attn.out.")
        key = key.replace(".encoder_attn.q_proj.", ".cross_attn.query.")
        key = key.replace(".encoder_attn.k_proj.", ".cross_attn.key.")
        key = key.replace(".encoder_attn.v_proj.", ".cross_attn.value.")
        key = key.replace(".encoder_attn.out_proj.", ".cross_attn.out.")
        key = key.replace(".final_layer_norm.", ".mlp_ln.")
        key = key.replace(".fc1.", ".mlp.0.")
        key = key.replace(".fc2.", ".mlp.2.")
        return key

    converted = {openai_key(k): v for k, v in
                 load_file(str(model_dir / "model.safetensors"), device="cpu").items()}
    expected = set(model.state_dict())
    actual = set(converted)
    if expected != actual:
        raise SystemExit(json.dumps({
            "error": "Whisper tensor map mismatch",
            "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected),
        }))
    model.load_state_dict(converted, strict=True)
    model.to(device)
    model.eval()
    result = whisper.transcribe(
        model, str(audio_path), language="en", task="transcribe",
        fp16=(device == "cuda"), temperature=0, verbose=False,
    )
    segments = [{"start": round(float(s["start"]), 3),
                 "end": round(float(s["end"]), 3),
                 "text": str(s["text"]).strip()}
                for s in result.get("segments", []) if str(s.get("text", "")).strip()]
    duration = 0.0
    if segments:
        duration = max(float(s["end"]) for s in segments)

    print(json.dumps({
        "engine": f"ComfyUI Whisper tiny (OpenAI cached decoder, {device})",
        "model": str(model_dir),
        "language": "en",
        "duration": round(duration, 3),
        "segments": segments,
        "transcript": str(result.get("text") or "").strip(),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
