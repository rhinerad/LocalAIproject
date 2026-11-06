#!/usr/bin/env python3
"""Dump predictor mmaps and PowerInfer activation_{L}.pt histograms from a ReLU Llama."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from pipeline_lib import relu_gate, sha256_tree, utc_now, write_json


def _load_model(path: str, load_4bit: bool, trust_remote_code: bool):
    kw: dict = {"torch_dtype": torch.bfloat16, "device_map": "auto", "trust_remote_code": trust_remote_code}
    if load_4bit:
        from transformers import BitsAndBytesConfig

        kw = {
            "quantization_config": BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            ),
            "device_map": "auto",
            "trust_remote_code": trust_remote_code,
        }
    return AutoModelForCausalLM.from_pretrained(path, **kw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="HF directory of the ReLU checkpoint")
    parser.add_argument("--jsonl", required=True)
    parser.add_argument("--out", required=True, help="bundle directory")
    parser.add_argument("--max-samples", type=int, default=400_000)
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--hidden-size", type=int, required=True)
    parser.add_argument("--intermediate-size", type=int, required=True)
    parser.add_argument("--num-hidden-layers", type=int, required=True)
    parser.add_argument("--expected-act", default="relu")
    parser.add_argument("--load-4bit", action="store_true")
    parser.add_argument("--trust-remote-code", action="store_true",
                        help="Permit only the reviewed local checkpoint's custom model code.")
    parser.add_argument("--solver-batch", type=int, default=256)
    args = parser.parse_args()

    source = Path(args.model)
    gate = relu_gate(source, args.expected_act)
    if not gate["ok"]:
        raise SystemExit(gate["reason"])
    if int(gate["hidden_size"]) != args.hidden_size:
        raise SystemExit(f"hidden_size mismatch: config {gate['hidden_size']} vs {args.hidden_size}")
    if int(gate["intermediate_size"]) != args.intermediate_size:
        raise SystemExit(
            f"intermediate_size mismatch: config {gate['intermediate_size']} vs {args.intermediate_size}"
        )
    if args.intermediate_size % args.solver_batch != 0:
        raise SystemExit(
            f"intermediate_size {args.intermediate_size} is not divisible by solver batch {args.solver_batch}"
        )

    out = Path(args.out)
    pred_dir = out / "predictor_data"
    act_dir = out / "activation"
    pred_dir.mkdir(parents=True, exist_ok=True)
    act_dir.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(str(source), use_fast=True, trust_remote_code=args.trust_remote_code)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = _load_model(str(source), args.load_4bit, args.trust_remote_code)
    model.eval()
    n_layer, d, f = args.num_hidden_layers, args.hidden_size, args.intermediate_size
    if len(model.model.layers) != n_layer:
        raise SystemExit(f"layer count mismatch: model {len(model.model.layers)} vs {n_layer}")

    queries = [
        np.memmap(pred_dir / f"mlp_sp_x_{i}.mmap", dtype=np.float16, mode="w+", shape=(args.max_samples, d))
        for i in range(n_layer)
    ]
    labels = [
        np.memmap(pred_dir / f"mlp_label_{i}.mmap", dtype=np.float16, mode="w+", shape=(args.max_samples, f))
        for i in range(n_layer)
    ]
    freq = [torch.zeros(f, dtype=torch.float64) for _ in range(n_layer)]
    n_written = [0] * n_layer
    done = False

    def mlp_hook(layer_idx: int):
        def _hook(mod, inp, _out):
            if done:
                return
            remaining = args.max_samples - n_written[layer_idx]
            if remaining <= 0:
                return
            x = inp[0].detach()
            gate_act = torch.nn.functional.relu(mod.gate_proj(x))
            inter = gate_act * mod.up_proj(x)
            hs = x.reshape(-1, d)
            lab = inter.reshape(-1, f)
            n = min(remaining, hs.shape[0])
            sl = slice(n_written[layer_idx], n_written[layer_idx] + n)
            queries[layer_idx][sl] = hs[:n].half().cpu().numpy()
            labels[layer_idx][sl] = lab[:n].abs().half().cpu().numpy()
            n_written[layer_idx] += n
            freq[layer_idx] += (lab[:n] > 0).sum(dim=0).double().cpu()

        return _hook

    handles = [
        layer.mlp.register_forward_hook(mlp_hook(i))
        for i, layer in enumerate(model.model.layers)
    ]

    started = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None
    ended = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None
    if started is not None:
        started.record()
    wall0 = __import__("time").monotonic()

    with torch.no_grad(), open(args.jsonl, "r", encoding="utf-8") as handle:
        for lid, line in enumerate(handle):
            if min(n_written) >= args.max_samples:
                done = True
                break
            prompt = json.loads(line)["prompt"]
            batch = tok(
                prompt,
                truncation=True,
                max_length=args.max_length,
                return_tensors="pt",
            )
            device = next(model.parameters()).device
            batch = {k: v.to(device) for k, v in batch.items()}
            model(**batch, use_cache=False)
            print(f"\rdoc {lid} samples[0]={n_written[0]}", end="", flush=True)

    for hook in handles:
        hook.remove()
    if ended is not None:
        ended.record()
        torch.cuda.synchronize()
    wall = __import__("time").monotonic() - wall0
    print("\nflushing…")
    for i in range(n_layer):
        queries[i].flush()
        labels[i].flush()
        torch.save(freq[i].float(), act_dir / f"activation_{i}.pt")
        true_sparsity = float(1.0 - (freq[i] / max(n_written[i], 1)).mean().clamp(0, 1))
        print(f"layer {i}: {n_written[i]} samples  mean-sparsity~{true_sparsity:.3f}")

    write_json(
        out / "profile_meta.json",
        {
            "created_at": utc_now(),
            "source": str(source),
            "n_layer": n_layer,
            "hidden_size": d,
            "intermediate_size": f,
            "max_samples": args.max_samples,
            "max_length": args.max_length,
            "n_written": n_written,
            "wall_seconds": round(wall, 3),
            "relu_gate": gate,
            "activation": sha256_tree(act_dir, glob="activation_*.pt"),
        },
    )
    print("wrote", out / "profile_meta.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
