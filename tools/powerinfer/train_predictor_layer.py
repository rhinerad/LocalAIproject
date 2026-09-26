#!/usr/bin/env python3
"""Train one DejaVu-style FFN activation predictor. Saves fc1.weight/fc2.weight."""
from __future__ import annotations

import argparse
import copy
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

from pipeline_lib import write_json


def save_checkpoint_once(payload: dict[str, torch.Tensor], target: Path, *, attempts: int = 3) -> None:
    """Persist a new checkpoint without overwriting evidence.

    Windows backup/indexing scanners can transiently deny a new checkpoint
    handle. Retry only while the target remains absent. If a failed write left
    anything behind, preserve it and fail closed instead of replacing it.
    """
    if target.exists():
        raise FileExistsError(f"refusing to overwrite checkpoint evidence: {target}")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            torch.save(payload, target)
            return
        except (PermissionError, RuntimeError) as exc:
            last_error = exc
            if target.exists() or attempt == attempts:
                raise
            time.sleep(float(attempt * 2))
    assert last_error is not None
    raise last_error


class MmapPair(Dataset):
    def __init__(self, x: np.memmap, y: np.memmap, start: int, stop: int, train: bool):
        self.x = x
        self.y = y
        self.start = start
        self.stop = stop
        self.train = train

    def __len__(self) -> int:
        return self.stop - self.start

    def __getitem__(self, idx: int):
        if self.train:
            loc = self.start + idx
        else:
            loc = self.stop - 1 - idx
        return (
            torch.from_numpy(np.array(self.x[loc], dtype=np.float32)),
            torch.from_numpy(np.array(self.y[loc], dtype=np.float32)),
        )


def evaluate(model, loader, device, max_batches: int | None = None) -> dict[str, float]:
    model.eval()
    stats = {"Loss": [], "Recall": [], "Classifier Sparsity": [], "True Sparsity": []}
    with torch.no_grad():
        for batch_idx, (x, y) in enumerate(loader):
            y = (y.to(device) > 0).float()
            probs = model(x.to(device)).sigmoid()
            preds = probs >= 0.5
            miss = (y.int() - preds.int()) > 0
            weight = (y.sum() / y.numel()) + 0.005
            loss_weight = y * (1 - weight) + weight
            stats["Loss"].append(
                torch.nn.functional.binary_cross_entropy(probs, y, weight=loss_weight).item()
            )
            stats["Recall"].append((y.sum(dim=1).float() - miss.sum(dim=1).float()).mean().item())
            stats["True Sparsity"].append(y.sum(dim=1).float().mean().item())
            stats["Classifier Sparsity"].append(preds.sum(dim=1).float().mean().item())
            if max_batches is not None and batch_idx >= max_batches:
                break
    out = {k: float(np.mean(v)) for k, v in stats.items()}
    out["Recall"] = out["Recall"] / max(out["True Sparsity"], 1e-6)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True, help="predictor directory")
    parser.add_argument("--L", type=int, required=True)
    parser.add_argument("--hidden-size", type=int, required=True)
    parser.add_argument("--intermediate-size", type=int, required=True)
    parser.add_argument("--N", type=int, default=400_000)
    parser.add_argument("--D", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=0.001)
    args = parser.parse_args()

    data = Path(args.dataset)
    x_path = data / f"mlp_sp_x_{args.L}.mmap"
    y_path = data / f"mlp_label_{args.L}.mmap"
    x = np.memmap(x_path, dtype="float16", mode="r", shape=(args.N, args.hidden_size))
    y = np.memmap(y_path, dtype="float16", mode="r", shape=(args.N, args.intermediate_size))
    n_train = int(0.95 * args.N)
    train_loader = DataLoader(
        MmapPair(x, y, 0, n_train, True),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        MmapPair(x, y, n_train, args.N, False),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = torch.nn.Sequential(
        torch.nn.Linear(args.hidden_size, args.D, bias=False),
        torch.nn.ReLU(),
        torch.nn.Linear(args.D, args.intermediate_size, bias=False),
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), args.lr, weight_decay=0.01)
    best = copy.deepcopy(model.state_dict())
    best_eval = evaluate(model, val_loader, device, max_batches=20)
    base_acc = best_eval["Recall"]
    no_improve = 0

    print(f"[start] layer {args.L} device={device} {best_eval}")
    for epoch in range(args.epochs):
        model.train()
        for x_b, y_b in tqdm(train_loader, desc=f"L{args.L} e{epoch+1}"):
            y_b = (y_b.to(device) > 0).float()
            optimizer.zero_grad(set_to_none=True)
            probs = model(x_b.to(device)).sigmoid()
            weight = (y_b.sum() / y_b.numel()) + 0.005
            loss_weight = y_b * (1 - weight) + weight
            loss = torch.nn.functional.binary_cross_entropy(probs, y_b, weight=loss_weight)
            loss.backward()
            optimizer.step()
        epoch_eval = evaluate(model, val_loader, device)
        print(f"[epoch {epoch+1}] {epoch_eval}")
        if epoch_eval["Recall"] > base_acc:
            base_acc = epoch_eval["Recall"]
            best_eval = epoch_eval
            best = copy.deepcopy(model.cpu().state_dict())
            model.to(device)
            no_improve = 0
        else:
            no_improve += 1
        if no_improve >= 5 or base_acc > 0.99:
            break

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"fc1.weight": best["0.weight"].cpu(), "fc2.weight": best["2.weight"].cpu()}
    stem = f"layer{args.L}-{best_eval['Recall']:.4f}-{best_eval['Classifier Sparsity']:.0f}.pt"
    save_checkpoint_once(payload, out / stem)
    save_checkpoint_once(payload, out / f"model_{args.L}.pt")
    write_json(
        out / f"layer{args.L}.metrics.json",
        {"layer": args.L, "file": stem, **{k: float(v) for k, v in best_eval.items()}},
    )
    print("wrote", out / f"model_{args.L}.pt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
