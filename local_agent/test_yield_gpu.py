#!/usr/bin/env python3
"""Tests for the Yield GPU endpoint (UPGRADE 08, Feature 2).

Run:  python local_agent/test_yield_gpu.py

These tests use unittest.mock to avoid needing a live Ollama server.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import server
import router


def _check(description: str, got, want) -> bool:
    if got == want:
        print(f"  ok  {description}")
        return True
    print(f"  FAIL {description}: got {got!r}, want {want!r}")
    return False


def test_yield_gpu_when_server_down() -> int:
    failures = 0
    with patch.object(router, "up", return_value=False):
        result = server.yield_gpu()
        if not _check("freed is empty when server down",
                      result["freed"], []):
            failures += 1
        if not _check("vram_mb is None when server down",
                      result["vram_mb"], None):
            failures += 1
        if not _check("message mentions unreachable",
                      "not reachable" in result["message"], True):
            failures += 1
    return failures


def test_yield_gpu_unloads_resident() -> int:
    failures = 0
    resident_model = "huihui_ai/qwen3-abliterated:14b"
    unloaded = []

    def fake_unload(host, model):
        unloaded.append(model)

    with patch.object(router, "up", return_value=True), \
         patch.object(router, "_tags", return_value=[resident_model]), \
         patch.object(router, "_running_models", return_value=[resident_model]), \
         patch.object(router, "_pick", return_value=resident_model), \
         patch.object(router, "gpu_memory", return_value=(2048, ["ollama"])), \
         patch.object(router, "unload", side_effect=fake_unload):
        result = server.yield_gpu()

    if not _check("unload called once for resident model",
                  len(unloaded), 1):
        failures += 1
    if not _check("freed contains the resident model",
                  result["freed"], [resident_model]):
        failures += 1
    if not _check("vram_mb is reported",
                  result["vram_mb"], 2048):
        failures += 1
    return failures


def test_yield_gpu_nothing_to_free() -> int:
    failures = 0
    unloaded = []

    def fake_unload(host, model):
        unloaded.append(model)

    # Nothing resident, no preferred model installed
    with patch.object(router, "up", return_value=True), \
         patch.object(router, "_tags", return_value=[]), \
         patch.object(router, "_running_models", return_value=[]), \
         patch.object(router, "_pick", return_value=None), \
         patch.object(router, "gpu_memory", return_value=(0, [])), \
         patch.object(router, "unload", side_effect=fake_unload):
        result = server.yield_gpu()

    if not _check("unload never called when nothing resident",
                  len(unloaded), 0):
        failures += 1
    if not _check("freed is empty",
                  result["freed"], []):
        failures += 1
    if not _check("message says nothing was resident",
                  "Nothing" in result["message"] or "nothing" in result["message"], True):
        failures += 1
    return failures


def main() -> int:
    total = 0
    print("test_yield_gpu_when_server_down")
    total += test_yield_gpu_when_server_down()
    print("test_yield_gpu_unloads_resident")
    total += test_yield_gpu_unloads_resident()
    print("test_yield_gpu_nothing_to_free")
    total += test_yield_gpu_nothing_to_free()
    if total:
        print(f"\n{total} failure(s)")
    else:
        print("\nAll OK")
    return total


if __name__ == "__main__":
    raise SystemExit(main())
