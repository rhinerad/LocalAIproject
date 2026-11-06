#!/usr/bin/env python3
"""SKETCH from a prior Grok session — not the production dump/train path.

Production ReluLLaMA calibration uses:
  tools/powerinfer/dump_activations.py
  tools/powerinfer/train_predictor_layer.py
  tools/powerinfer/assemble_predictor.py

This file is kept because Rhine asked the batch suite to retain it. The
production orchestrator (batch_suite.ps1) does NOT call it unless
-UseSketchPredictor is passed. Known issues vs the live pipeline:
  * ReluMLP.forward already applies ReLU, then training uses
    binary_cross_entropy_with_logits (expects raw logits).
  * Samples/seq-len/epochs here are far smaller than dump_activations
    (400k) + train_predictor_layer (25k/rank-256/2-epoch overnight run).
  * PowerInfer convert.py wants assembled predictor/ + activation_{L}.pt
    histograms from dump_activations, not this sketch's layout alone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig
from datasets import load_dataset
from tqdm import tqdm


class ReluMLP(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim, bias=False)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(hidden_dim, output_dim, bias=False)

    def forward(self, x):
        return self.fc2(self.relu(self.fc1(x)))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--out-predictors", required=True)
    p.add_argument("--out-activation", required=True)
    p.add_argument("--hidden-dim", type=int, default=1024)
    p.add_argument("--samples", type=int, default=512)
    p.add_argument("--seq-len", type=int, default=256)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--skip-train", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cfg = AutoConfig.from_pretrained(args.model)
    n_layers = cfg.num_hidden_layers
    hidden = cfg.hidden_size
    intermediate = cfg.intermediate_size

    tok = AutoTokenizer.from_pretrained(args.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    try:
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
        model = AutoModelForCausalLM.from_pretrained(
            args.model, quantization_config=bnb, device_map="auto", trust_remote_code=True
        )
    except Exception:
        model = AutoModelForCausalLM.from_pretrained(
            args.model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
        )
    model.eval()

    captured = {i: {"x": [], "y": []} for i in range(n_layers)}
    hooks = []

    def make_hook(idx):
        def hook(module, inp, out):
            x = inp[0].detach()
            gate = module.gate_proj(x)
            act = torch.relu(gate)
            captured[idx]["x"].append(x.reshape(-1, x.shape[-1]).float().cpu())
            captured[idx]["y"].append(act.reshape(-1, act.shape[-1]).float().cpu())
        return hook

    for i, layer in enumerate(model.model.layers):
        hooks.append(layer.mlp.register_forward_hook(make_hook(i)))

    ds = load_dataset("wikitext", "wikitext-2-raw-v1", split="train")
    texts = [t for t in ds["text"] if t and t.strip()][: args.samples]
    for t in tqdm(texts, desc="profile"):
        batch = tok(t, return_tensors="pt", truncation=True, max_length=args.seq_len)
        batch = {k: v.to(model.device) for k, v in batch.items()}
        with torch.no_grad():
            model(**batch)

    for h in hooks:
        h.remove()

    pred_dir = Path(args.out_predictors)
    pred_dir.mkdir(parents=True, exist_ok=True)
    act_dir = Path(args.out_activation)
    act_dir.mkdir(parents=True, exist_ok=True)

    for i in range(n_layers):
        X = torch.cat(captured[i]["x"], dim=0)
        Y = torch.cat(captured[i]["y"], dim=0)
        freq = Y.mean(dim=0)
        torch.save(freq, act_dir / f"activation_{i}.pt")

        if args.skip_train:
            continue

        labels = (Y > 0).float()
        n = min(len(X), 20000)
        perm = torch.randperm(len(X))[:n]
        loader = DataLoader(TensorDataset(X[perm], labels[perm]), batch_size=256, shuffle=True)
        mlp = ReluMLP(hidden, args.hidden_dim, intermediate).to(device)
        opt = torch.optim.AdamW(mlp.parameters(), lr=args.lr)
        for _ in range(args.epochs):
            for xb, yb in loader:
                xb, yb = xb.to(device), yb.to(device)
                pos = yb.mean() + 0.005
                w = yb * (1 - pos) + pos
                loss = nn.functional.binary_cross_entropy_with_logits(mlp(xb), yb, weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
        torch.save(mlp.cpu().state_dict(), pred_dir / f"model_{i}.pt")

    (pred_dir / "config.json").write_text(json.dumps({"sparse_threshold": 0.0}, indent=2))


if __name__ == "__main__":
    main()
