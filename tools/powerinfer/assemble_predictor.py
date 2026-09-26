#!/usr/bin/env python3
"""Write convert.py predictor dir: model_{L}.pt plus config.json sparse_threshold."""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline_lib import sha256_tree, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, help="directory containing model_{L}.pt")
    parser.add_argument("--dst", required=True)
    parser.add_argument("--layers", type=int, required=True)
    parser.add_argument("--sparse-threshold", type=float, default=0.0)
    args = parser.parse_args()
    src = Path(args.src)
    dst = Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)
    missing = []
    for layer in range(args.layers):
        path = src / f"model_{layer}.pt"
        if not path.is_file():
            missing.append(str(path))
            continue
        target = dst / f"model_{layer}.pt"
        if path.resolve() != target.resolve():
            target.write_bytes(path.read_bytes())
    if missing:
        raise SystemExit("missing predictor layers:\n" + "\n".join(missing))
    write_json(dst / "config.json", {"sparse_threshold": args.sparse_threshold})
    write_json(dst / "HASHES.json", sha256_tree(dst, glob="*"))
    print("assembled", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
