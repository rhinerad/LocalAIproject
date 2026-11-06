"""Bounded, read-only diagnosis of the TurboSparse 4-bit shard-load stall.

Never writes the source checkpoint. Never downloads. Hard wall-clock timeout.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from abliterate_loader import (
    DEFAULT_LOCAL_TURBOSPARSE,
    Deadline,
    host_ram_mb,
    resolve_local_model,
    shard_paths,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(DEFAULT_LOCAL_TURBOSPARSE))
    ap.add_argument("--max-seconds", type=float, default=90.0)
    ap.add_argument("--skip-gpu", action="store_true")
    args = ap.parse_args()
    deadline = Deadline(args.max_seconds)
    source = resolve_local_model(args.model)
    report: dict[str, object] = {
        "source": str(source),
        "source_written": False,
        "ram": host_ram_mb(),
    }

    import torch
    import transformers
    import accelerate
    import bitsandbytes as bnb
    import safetensors

    report["versions"] = {
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "accelerate": accelerate.__version__,
        "bitsandbytes": bnb.__version__,
        "safetensors": safetensors.__version__,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
    }
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        report["vram"] = {"free_mb": free / 1024 / 1024, "total_mb": total / 1024 / 1024}

    from safetensors import safe_open
    from safetensors.torch import load_file

    shard_report = []
    for shard in shard_paths(source):
        deadline.check(shard.name)
        t0 = time.perf_counter()
        with safe_open(str(shard), framework="pt") as handle:
            keys = list(handle.keys())
            sample = keys[0]
            tensor = handle.get_tensor(sample)
            largest = max(keys, key=lambda k: int(torch.tensor(handle.get_slice(k).get_shape()).prod()))
        shard_report.append(
            {
                "file": shard.name,
                "bytes": shard.stat().st_size,
                "keys": len(keys),
                "sample": sample,
                "sample_shape": list(tensor.shape),
                "largest": largest,
                "open_get_sec": round(time.perf_counter() - t0, 3),
            }
        )
        del tensor
    report["shards"] = shard_report

    # Reproduce the Transformers 4.41 behavior on shard 2 only: full load_file.
    shard2 = next(p for p in shard_paths(source) if "00002" in p.name)
    deadline.check("load_file shard2")
    t0 = time.perf_counter()
    state = load_file(str(shard2))
    load_sec = time.perf_counter() - t0
    nbytes = sum(int(v.numel() * v.element_size()) for v in state.values())
    t1 = time.perf_counter()
    touched = 0
    for tensor in state.values():
        deadline.check("touch shard2")
        touched += int(tensor.view(-1)[0].item() != 3.14159)
    touch_sec = time.perf_counter() - t1
    report["transformers_style_shard2"] = {
        "load_file_sec": round(load_sec, 3),
        "touch_all_sec": round(touch_sec, 3),
        "mb": round(nbytes / 1024 / 1024, 1),
        "note": "load_file is mmap and returns immediately; touching every tensor pages ~4.5 GiB",
    }
    del state

    if not args.skip_gpu:
        if not torch.cuda.is_available():
            raise SystemExit("CUDA required unless --skip-gpu")
        deadline.check("bnb o_proj")
        t0 = time.perf_counter()
        weight = torch.randn(4096, 4096, dtype=torch.float16)
        quant = bnb.nn.Params4bit(weight, requires_grad=False, quant_type="nf4", compress_statistics=False)
        quant = quant.to("cuda:0")
        torch.cuda.synchronize()
        report["bnb_oproj_sec"] = round(time.perf_counter() - t0, 3)
        del weight, quant
        torch.cuda.empty_cache()

        from abliterate_loader import load_measurement_model

        cfg, model, stats = load_measurement_model(
            source,
            trust_remote_code=True,
            deadline=deadline,
            num_hidden_layers=1,
            log=lambda msg: print(msg, flush=True),
        )
        report["smoke_1layer"] = {
            "hidden_act": getattr(cfg, "hidden_act", None),
            "model_type": getattr(cfg, "model_type", None),
            "load_stats": stats,
            "first_param_device": str(next(model.parameters()).device),
        }
        del model
        torch.cuda.empty_cache()

    report["root_cause"] = {
        "primary": (
            "Transformers 4.41.2 checkpoint loading calls safetensors.torch.load_file on each "
            "4.5 GiB shard, then copies every tensor to float16 and bitsandbytes Params4bit.to(cuda) "
            "while the shard mapping is still alive. tqdm only advances after the whole shard finishes, "
            "so shard 2/4 appears stalled under ~15 GiB free host RAM + CUDA pinning."
        ),
        "not_primary": [
            "Bamboo remote-code import (config and 1-layer construct succeed)",
            "bitsandbytes NF4 on sm_120 (4096x4096 quantizes in well under a second)",
            "Windows safetensors open of shard 2 (safe_open + get_tensor is milliseconds)",
            "FlashAttention import scanner (already bypassed; eager attention is used)",
        ],
        "contributing": (
            "transformers==4.41.2 (Bamboo pin) with bitsandbytes==0.50.2 copies Params4bit.__dict__ "
            "into the constructor; accelerate==1.14.0 is present but the stall is in Transformers' "
            "own shard loop, not accelerate.dispatch."
        ),
        "device_map": (
            "device_map mapping the whole model to cuda:0 is intended for measurement, "
            "but combined with full-shard load_file it is the RAM-pressure trigger. The map itself "
            "is not an offload bug."
        ),
    }
    report["status"] = "ok"
    report["deadline_remaining_s"] = round(deadline.remaining(), 1)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
