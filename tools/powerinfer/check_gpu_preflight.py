#!/usr/bin/env python3
"""Refuse dump/train/bench when ComfyUI or another render owner is on the GPU."""
from __future__ import annotations

import json

from pipeline_lib import blocking_gpu_owners, gpu_snapshot, host_ram_snapshot


def main() -> int:
    snapshot = gpu_snapshot()
    owners = blocking_gpu_owners(snapshot)
    report = {"gpu": snapshot, "ram": host_ram_snapshot(), "owners": owners}
    print(json.dumps(report, indent=2))
    if owners:
        raise SystemExit(f"GPU appears owned by {owners}; stop ComfyUI/VLM/render first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
