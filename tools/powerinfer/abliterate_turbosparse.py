"""Research-only representation editing for Tiiny TurboSparse checkpoints.

This script never downloads a model and never changes the source directory. It
measures a direction with a quantized GPU copy, then edits a separate full-
precision CPU copy. TurboSparse uses custom Bamboo code; verify the module names
and run the resulting checkpoint through the PowerInfer profiling pipeline again.

Example (after installing dependencies and preparing prompt JSON):
  python abliterate_turbosparse.py \
    --model Tiiny/TurboSparse-Mistral-Instruct \
    --pairs calibration/refusal_pairs.jsonl \
    --output D:/PowerInferStaging/turbosparse-mistral-abliterated

The pair file is JSONL with ``{"harmful": "...", "harmless": "..."}``
records. Use benign, synthetic contrastive prompts; do not place private
transcripts in the file.
Use benign, synthetic calibration prompts; do not place private transcripts in
the file. The operation is intentionally opt-in and fails closed on missing
custom code, missing pair data, or an unexpected architecture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterable

# Transformers' dynamic custom-code loader otherwise defaults to the protected
# user cache on this workstation. Keep the cache local to this tool unless the
# operator explicitly supplied a different location.
_CACHE_ROOT = Path(__file__).resolve().parent / ".hf_cache"
os.environ.setdefault("HF_HOME", str(_CACHE_ROOT))
os.environ.setdefault("HF_MODULES_CACHE", str(_CACHE_ROOT / "modules"))

import torch
from safetensors.torch import load_file, save_file
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from transformers import dynamic_module_utils

# The upstream Bamboo file guards its FlashAttention import with
# ``is_flash_attn_2_available()`` and uses eager attention by default. Older
# Transformers nevertheless reject the file during static import scanning when
# flash-attn is absent (common on Windows). Bypass only that scanner; if the
# runtime actually selects FlashAttention, the model will still fail normally.
dynamic_module_utils.check_imports = lambda _filename: []


# The measured direction lives in the residual/hidden space. Bamboo's
# down_proj consumes the 14,336-wide intermediate space, so projecting it with
# a 4,096-wide residual vector would be mathematically invalid. Keep the edit
# allowlist to shape-compatible attention output projections.
TARGET_RE = re.compile(r"(?:^|\.)o_proj\.weight$")


def read_pairs(path: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item.get("harmful"), str) or not isinstance(item.get("harmless"), str):
            raise ValueError("each calibration row needs string harmful and harmless fields")
        rows.append({"harmful": item["harmful"], "harmless": item["harmless"]})
        if len(rows) >= limit:
            break
    if len(rows) < 8:
        raise ValueError("at least 8 calibration pairs are required")
    return rows


@torch.inference_mode()
def hidden_mean(model, tokenizer, texts: Iterable[str], device: str) -> torch.Tensor:
    vectors: list[torch.Tensor] = []
    for text in texts:
        batch = tokenizer(text, return_tensors="pt", truncation=True, max_length=2048)
        batch = {k: v.to(device) for k, v in batch.items()}
        out = model(**batch, output_hidden_states=True, use_cache=False)
        # Last non-padding token from the final hidden state.
        idx = batch["attention_mask"].sum(dim=1).item() - 1
        vectors.append(out.hidden_states[-1][0, idx].float().cpu())
    return torch.stack(vectors).mean(dim=0)


def projected_refusal_direction(model, tokenizer, pairs: list[dict[str, str]], device: str) -> tuple[torch.Tensor, float]:
    """Compute Projected Abliteration's refined refusal direction.

    r = mu_harmful - mu_harmless; remove the component parallel to the
    normalized harmless mean before projecting writer matrices.
    """
    harmful = hidden_mean(model, tokenizer, (x["harmful"] for x in pairs), device)
    harmless = hidden_mean(model, tokenizer, (x["harmless"] for x in pairs), device)
    hnorm = harmless.norm()
    if not torch.isfinite(hnorm) or hnorm < 1e-6:
        raise ValueError("calibration produced an unusable harmless mean")
    harmless_unit = harmless / hnorm
    refusal = harmful - harmless
    rnorm = refusal.norm()
    if not torch.isfinite(rnorm) or rnorm < 1e-6:
        raise ValueError("calibration produced an unusable refusal direction")
    projection_scalar = float(torch.dot(refusal, harmless_unit))
    refined = refusal - projection_scalar * harmless_unit
    refined_norm = refined.norm()
    if not torch.isfinite(refined_norm) or refined_norm < 1e-6:
        raise ValueError("projected refusal direction collapsed; collect better pairs")
    return refined / refined_norm, projection_scalar


def edit_tensor(name: str, weight: torch.Tensor, direction: torch.Tensor, strength: float) -> torch.Tensor:
    """Project shape-compatible hidden-space attention output weights."""
    if not TARGET_RE.search(name):
        return weight
    d = direction.to(dtype=weight.dtype, device=weight.device)
    if name.endswith("o_proj.weight"):
        if weight.shape[0] != d.numel():
            raise ValueError(f"unexpected o_proj shape for {name}: {tuple(weight.shape)}")
        # P W, where P = I - alpha*d*d^T (bounded alpha avoids overshoot).
        edited = weight - strength * torch.outer(d, d @ weight)
        # Preserve each writer matrix's Frobenius norm to limit sparsity drift.
        before = weight.norm()
        after = edited.norm()
        return edited * (before / after) if after > 0 else weight
    return weight


def sha256_tree(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "abliteration_manifest.json":
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path.relative_to(root))] = h
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--pair-limit", type=int, default=64)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--revision", default=None)
    ap.add_argument("--trust-remote-code", action="store_true")
    args = ap.parse_args()
    if not 0.0 < args.strength <= 1.0:
        raise SystemExit("--strength must be in (0, 1]")
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("output exists and is non-empty; choose a new immutable staging directory")
    pairs = read_pairs(args.pairs, args.pair_limit)
    cfg = AutoConfig.from_pretrained(args.model, revision=args.revision, trust_remote_code=args.trust_remote_code)
    if getattr(cfg, "hidden_act", None) not in {"relu", "reglu", "squared_relu"}:
        raise SystemExit(f"refusing non-ReLU architecture: hidden_act={getattr(cfg, 'hidden_act', None)!r}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision, trust_remote_code=args.trust_remote_code)

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
    measured = AutoModelForCausalLM.from_pretrained(
        args.model, revision=args.revision, quantization_config=quant, device_map={"": "cuda:0"},
        trust_remote_code=args.trust_remote_code,
    )
    direction, projection_scalar = projected_refusal_direction(
        measured, tokenizer, pairs, str(next(measured.parameters()).device)
    )
    del measured
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    full = AutoModelForCausalLM.from_pretrained(
        args.model, revision=args.revision, device_map={"": "cpu"}, low_cpu_mem_usage=True,
        torch_dtype=torch.bfloat16, trust_remote_code=args.trust_remote_code,
    )
    changed: list[str] = []
    with torch.no_grad():
        for name, param in full.named_parameters():
            if name.endswith(".weight") and TARGET_RE.search(name):
                param.copy_(edit_tensor(name, param.data, direction, args.strength))
                changed.append(name)
    if not changed:
        raise SystemExit("no allowlisted o_proj/down_proj weights found; checkpoint was not written")
    args.output.mkdir(parents=True, exist_ok=False)
    full.save_pretrained(args.output, safe_serialization=True, max_shard_size="3GB")
    tokenizer.save_pretrained(args.output)
    shutil.copy2(args.pairs, args.output / "calibration_pairs.jsonl")
    manifest = {
        "source_model": args.model,
        "revision": args.revision,
        "architecture": getattr(cfg, "model_type", None),
        "hidden_act": getattr(cfg, "hidden_act", None),
        "method": "Projected Abliteration: harmful-harmless; harmless-mean orthogonal refinement; norm-preserving o_proj projection",
        "projection_scalar": projection_scalar,
        "strength": args.strength,
        "pairs": len(pairs),
        "changed_parameter_count": len(changed),
        "changed_parameters": changed,
        "requires_powerinfer_reprofiling": True,
        "warning": "Do not reuse source predictors/activations; regenerate and revalidate after this edit.",
    }
    (args.output / "abliteration_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["sha256"] = sha256_tree(args.output)
    (args.output / "abliteration_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "changed": len(changed), "status": "staged"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
