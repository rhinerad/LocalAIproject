#!/usr/bin/env python3
"""Ping local Ollama and run compiled temporal-physics DSPy inference.

Does not submit ComfyUI jobs. Falls back silently if 11434 is down.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

from local_agent import temporal_physics as tp  # noqa: E402

TEST_PROMPT = "A yellow hallway with flickering fluorescent lights"


def main() -> int:
    installed = tp.ping_ollama()
    if not installed:
        print("Ollama is not answering on http://127.0.0.1:11434 — using fallback.")
        text = tp.runtime_inject_temporal_physics(TEST_PROMPT, style="backrooms")
        print(json.dumps({"source": tp.LAST_INJECT_META, "prompt": text}, indent=2))
        return 2
    print(f"Ollama models: {installed[:12]}")
    ok = tp.configure_local_dspy_lm()
    print(f"configure_local_dspy_lm={ok} dspy_lm={tp._dspy_lm_available()}")
    started = time.monotonic()
    text = tp.runtime_inject_temporal_physics(TEST_PROMPT, style="backrooms")
    elapsed = time.monotonic() - started
    meta = dict(tp.LAST_INJECT_META)
    print(f"source={meta.get('source')} model={meta.get('model')} seconds={elapsed:.2f}")
    print("--- injected prompt ---")
    print(text)
    if meta.get("source") != "compiled":
        print("WARNING: compiled module did not run; used deterministic fallback.")
        return 1
    if "vhs" not in text.lower() and "1990s" not in text.lower() and "camcorder" not in text.lower():
        print("WARNING: compiled output missing Backrooms aesthetics.")
        return 1
    print("compiled DSPy inference OK (few-shot CoT via Ollama).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
