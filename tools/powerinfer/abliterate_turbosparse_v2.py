"""Projected Abliteration for Tiiny/TurboSparse-Mistral-Instruct (streaming loader).

Same math as ``abliterate_turbosparse.py``:

    r = mu_harmful - mu_harmless
    projection_scalar = dot(r, normalize(mu_harmless))
    refined = r - projection_scalar * normalize(mu_harmless)
    refined_direction = normalize(refined)

Only shape-compatible residual-stream ``o_proj.weight`` matrices are edited, with
Frobenius-norm preservation. The 4-bit copy is measurement-only. Full-precision
edits are applied on CPU from streamed safetensors; the source directory is never
written.

This version does **not** call ``from_pretrained(..., quantization_config=...,
device_map={"": "cuda:0"})``. That path stalls on this host while loading shard
2/4 because Transformers 4.41 materializes each 4.5 GiB shard in RAM before
bitsandbytes quantization.

Example (no download, GPU must be free):

  python abliterate_turbosparse_v2.py --smoke --trust-remote-code

  python abliterate_turbosparse_v2.py \\
    --model Tiiny/TurboSparse-Mistral-Instruct \\
    --pairs calibration_pairs.synthetic.jsonl \\
    --output D:/PowerInferStaging/turbosparse-mistral-abliterated-projected \\
    --trust-remote-code
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_CACHE_ROOT = Path(__file__).resolve().parent / ".hf_cache"
os.environ.setdefault("HF_HOME", str(_CACHE_ROOT))
os.environ.setdefault("HF_MODULES_CACHE", str(_CACHE_ROOT / "modules"))
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from transformers import AutoTokenizer, dynamic_module_utils

from abliterate_loader import (
    DEFAULT_LOCAL_TURBOSPARSE,
    Deadline,
    edit_shards_cpu,
    load_measurement_model,
    resolve_local_model,
)
from abliterate_turbosparse import (
    TARGET_RE,
    projected_refusal_direction,
    read_pairs,
    sha256_tree,
)
from validate_approved_calibration_pairs import validate as validate_approved_pairs

dynamic_module_utils.check_imports = lambda _filename: []


def _log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(DEFAULT_LOCAL_TURBOSPARSE))
    ap.add_argument("--pairs", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--pair-limit", type=int, default=64)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--revision", default=None)
    ap.add_argument("--trust-remote-code", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="1-layer measurement only; never writes a checkpoint")
    ap.add_argument("--max-seconds", type=float, default=None)
    args = ap.parse_args()
    if args.revision:
        raise SystemExit("local snapshot only; --revision would imply a Hub fetch")
    if not 0.0 < args.strength <= 1.0:
        raise SystemExit("--strength must be in (0, 1]")
    if not args.trust_remote_code:
        raise SystemExit("Bamboo remote code is required; pass --trust-remote-code")

    source = resolve_local_model(args.model)
    if args.smoke:
        max_seconds = args.max_seconds if args.max_seconds is not None else 180.0
        layers = 1
        pairs_path = args.pairs or (Path(__file__).resolve().parent / "calibration_pairs.synthetic.jsonl")
        approval = {"status": "smoke_only", "approved_input": False}
    else:
        max_seconds = args.max_seconds if args.max_seconds is not None else 1800.0
        layers = None
        if args.pairs is None or args.output is None:
            raise SystemExit("full run requires --pairs and --output")
        pairs_path = args.pairs
        if args.output.exists() and any(args.output.iterdir()):
            raise SystemExit("output exists and is non-empty; choose a new immutable staging directory")
        # The eight-row synthetic fixture may exercise the loader/math smoke path,
        # but it can never authorize a full checkpoint edit or later GPU stages.
        approval = validate_approved_pairs(pairs_path)

    deadline = Deadline(max_seconds)
    pairs = read_pairs(pairs_path, args.pair_limit)
    tokenizer = AutoTokenizer.from_pretrained(
        str(source), local_files_only=True, trust_remote_code=args.trust_remote_code
    )

    cfg, measured, stats = load_measurement_model(
        source,
        trust_remote_code=args.trust_remote_code,
        deadline=deadline,
        num_hidden_layers=layers,
        log=_log,
    )
    hidden_act = getattr(cfg, "hidden_act", None)
    if hidden_act not in {"relu", "reglu", "squared_relu"}:
        raise SystemExit(f"refusing non-ReLU architecture: hidden_act={hidden_act!r}")

    direction, projection_scalar = projected_refusal_direction(
        measured, tokenizer, pairs, str(next(p for p in measured.parameters() if p.device.type != "meta").device)
    )
    _log(json.dumps({"projection_scalar": projection_scalar, "direction_dim": int(direction.numel())}))

    import torch

    del measured
    gc = __import__("gc")
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    if args.smoke:
        _log(
            json.dumps(
                {
                    "status": "smoke-ok",
                    "source": str(source),
                    "layers": layers,
                    "pairs": len(pairs),
                    "calibration_gate": approval,
                    "load_stats": stats,
                    "wrote_checkpoint": False,
                },
                indent=2,
            )
        )
        return 0

    changed = edit_shards_cpu(
        source,
        args.output,
        direction,
        args.strength,
        TARGET_RE,
        deadline=deadline,
        log=_log,
    )
    shutil = __import__("shutil")
    shutil.copy2(pairs_path, args.output / "calibration_pairs.jsonl")
    tokenizer.save_pretrained(args.output)
    manifest = {
        "source_model": "Tiiny/TurboSparse-Mistral-Instruct",
        "source_path": str(source),
        "revision": None,
        "architecture": getattr(cfg, "model_type", None),
        "hidden_act": hidden_act,
        "method": (
            "Projected Abliteration: harmful-harmless; harmless-mean orthogonal "
            "refinement; norm-preserving o_proj projection"
        ),
        "loader": "streamed safetensors + NF4 measurement; CPU shard edit of o_proj only",
        "projection_scalar": projection_scalar,
        "strength": args.strength,
        "pairs": len(pairs),
        "calibration_gate": approval,
        "changed_parameter_count": len(changed),
        "changed_parameters": changed,
        "requires_powerinfer_reprofiling": True,
        "warning": "Do not reuse source predictors/activations; regenerate and revalidate after this edit.",
    }
    (args.output / "abliteration_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["sha256"] = sha256_tree(args.output)
    (args.output / "abliteration_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _log(json.dumps({"output": str(args.output), "changed": len(changed), "status": "staged"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
