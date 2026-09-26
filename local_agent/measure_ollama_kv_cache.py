#!/usr/bin/env python3
"""Measure one GPU Ollama KV-cache configuration without touching ComfyUI.

This is deliberately a *measurement harness*, not an automatic optimization.
The GPU Ollama service must already have been started with the configuration
being measured (for example its normal f16 cache or the opt-in Flash Attention
+ q8_0 cache).  The script refuses if a render owns the GPU and only sends a
model request when ``--run`` is supplied.

Run this once for each manually selected server configuration, with the same
model and context size, then compare the JSON reports.  It does not install a
package, start ComfyUI, change a server environment, or start a render.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

import router

DEFAULT_HOST = router.GPU_HOST
DEFAULT_MODEL = router.PRIMARY_REASONING_MODEL
DEFAULT_CONTEXT = 20_480

# Inverse of the router's JSON-wire *estimator* (`_MESSAGE_CHARS_PER_TOKEN = 3.4`).
# That constant converts chars → tokens for routing and is deliberately
# conservative (over-counts). Using it as chars = tokens * 3.4 to *build* a
# filler silently under-fills denser tokenizers: Qwen3.8-27B on this exact
# sentence (2026-09-05bm) produced prompt_eval_count 9375 from an 18000-token
# request (~6.5 chars/token). Fill generation must use a measured ratio.
#
# Fallback is that measured value for *this repetitive filler*, not English
# prose. Live paths (run_once / sized_probe_prompt) calibrate from
# prompt_eval_count instead of trusting the fallback.
FALLBACK_FILL_CHARS_PER_TOKEN = 6.5
CALIBRATE_SAMPLE_TOKENS = 1_024

_FILLER = "The cache test sentence is deliberately repetitive and harmless. "
_PREFIX = (
    "Read the supplied text. Reply with exactly: KV_CACHE_OK\n\n"
    "--- begin deterministic cache payload ---\n")
_SUFFIX = "\n--- end payload ---"


def _post(host: str, path: str, payload: dict, *, timeout: int = 900) -> dict:
    request = urllib.request.Request(
        f"http://{host}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _installed(host: str) -> list[str]:
    return router._tags(host)


def preflight(host: str, model: str) -> dict:
    """Return only facts needed to decide whether a live benchmark is safe."""
    busy, reason, detail = router.gpu_busy()
    if busy:
        raise RuntimeError(f"refused: GPU is not available for a benchmark: {reason}")
    installed = _installed(host)
    actual = router._installed_variant(installed, model)
    if not actual:
        raise RuntimeError(f"refused: {model!r} is not installed on GPU server {host}")
    return {
        "host": host,
        "requested_model": model,
        "model": actual,
        "gpu_check": {"reason": reason, "detail": detail},
    }


def probe_prompt(context_tokens: int, *, chars_per_token: float | None = None) -> str:
    """A deterministic, innocuous prompt sized for approximately ``context_tokens``.

    ``chars_per_token`` is the tokenizer's chars/token on *this filler*, not
    the router's 3.4 JSON-wire estimator. Omit it only in offline tests; live
    callers should pass a value from ``calibrate_fill_chars_per_token``.
    """
    if context_tokens < 1_024:
        raise ValueError("context_tokens must be at least 1024")
    cpt = (FALLBACK_FILL_CHARS_PER_TOKEN if chars_per_token is None
           else float(chars_per_token))
    if cpt <= 0:
        raise ValueError("chars_per_token must be positive")
    overhead = len(_PREFIX) + len(_SUFFIX)
    target_body = max(len(_FILLER), int(context_tokens * cpt) - overhead)
    body = (_FILLER * ((target_body // len(_FILLER)) + 1))[:target_body]
    return f"{_PREFIX}{body}{_SUFFIX}"


def chars_per_token_from_eval(prompt: str, prompt_eval_count: int) -> float:
    """Derive filler chars/token from a live ``prompt_eval_count``."""
    pec = int(prompt_eval_count or 0)
    if pec < 1:
        raise ValueError("prompt_eval_count must be a positive live measurement")
    if not prompt:
        raise ValueError("prompt is empty")
    return len(prompt) / pec


def calibrate_fill_chars_per_token(
        host: str, model: str, *, sample_tokens: int = CALIBRATE_SAMPLE_TOKENS) -> float:
    """One short live request; return chars / prompt_eval_count for this filler."""
    prompt = probe_prompt(sample_tokens, chars_per_token=FALLBACK_FILL_CHARS_PER_TOKEN)
    result = _post(host, "/api/chat", {
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": "1m",
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "num_gpu": 99,
            "num_ctx": max(2_048, sample_tokens + 256),
            "num_predict": 1,
            "temperature": 0,
            "top_p": 1,
        },
    }, timeout=300)
    return chars_per_token_from_eval(prompt, int(result.get("prompt_eval_count") or 0))


def sized_probe_prompt(host: str, model: str, context_tokens: int) -> tuple[str, float]:
    """Calibrate on ``model``, then build a filler aimed at ``context_tokens``."""
    chars_per_token = calibrate_fill_chars_per_token(host, model)
    return probe_prompt(context_tokens, chars_per_token=chars_per_token), chars_per_token


def run_once(host: str, model: str, context_tokens: int,
             *, chars_per_token: float | None = None) -> dict:
    """Run exactly one non-streaming request and return reproducible metrics.

    When ``chars_per_token`` is omitted, a short calibration request measures
    this model's filler density first so the timed request is actually near
    ``context_tokens`` rather than ``context_tokens * 3.4 / real_cpt``.
    """
    before_mb, _ = router.gpu_memory()
    calibrated = chars_per_token is None
    if calibrated:
        chars_per_token = calibrate_fill_chars_per_token(host, model)
    prompt = probe_prompt(context_tokens, chars_per_token=chars_per_token)
    started = time.monotonic()
    result = _post(host, "/api/chat", {
        "model": model,
        "stream": False,
        # Qwen's optional thinking stream is useful in an ordinary chat but it
        # changes a fixed-output cache probe into a reasoning task.  Keep the
        # benchmark deterministic and do not persist any hidden reasoning.
        "think": False,
        "keep_alive": "1m",
        "messages": [{"role": "user", "content": prompt}],
        "options": {
            "num_gpu": 99,
            "num_ctx": context_tokens,
            "temperature": 0,
            "top_p": 1,
        },
    })
    elapsed = time.monotonic() - started
    after_mb, _ = router.gpu_memory()
    reply = str((result.get("message") or {}).get("content") or "")
    reply_normalized = reply.strip()
    eval_count = int(result.get("eval_count") or 0)
    eval_duration_ns = int(result.get("eval_duration") or 0)
    pec = result.get("prompt_eval_count")
    fill_error = None
    if pec:
        fill_error = abs(int(pec) - context_tokens) / context_tokens
    return {
        "context_tokens_requested": context_tokens,
        "fill_chars_per_token": round(float(chars_per_token), 4),
        "fill_calibrated": calibrated,
        "fill_prompt_chars": len(prompt),
        "fill_rel_error": round(fill_error, 4) if fill_error is not None else None,
        "elapsed_seconds": round(elapsed, 3),
        "vram_before_mb": before_mb,
        "vram_after_mb": after_mb,
        "prompt_eval_count": pec,
        "eval_count": eval_count,
        "eval_duration_ns": eval_duration_ns,
        "decode_tokens_per_second": round(
            eval_count / (eval_duration_ns / 1_000_000_000), 3) if eval_duration_ns else None,
        "reply_exact": reply_normalized == "KV_CACHE_OK",
        "reply_expected_token_seen": "KV_CACHE_OK" in reply_normalized,
        "reply_sha256": hashlib.sha256(reply.encode("utf-8")).hexdigest(),
        "response_load_duration_ns": result.get("load_duration"),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--context", type=int, default=DEFAULT_CONTEXT)
    parser.add_argument("--label", default="unlabelled")
    parser.add_argument("--run", action="store_true",
                        help="send the one benchmark request after a clean preflight")
    parser.add_argument("--out", type=Path,
                        help="write a JSON report; required with --run")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        report = {"preflight": preflight(args.host, args.model), "label": args.label}
        if not args.run:
            report["status"] = "preflight_only"
            print(json.dumps(report, indent=2))
            return 0
        if args.out is None:
            raise RuntimeError("--out is required with --run so the evidence is preserved")
        report["measurement"] = run_once(
            args.host, report["preflight"]["model"], args.context)
        report["status"] = "measured"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except (RuntimeError, ValueError, OSError, urllib.error.URLError) as exc:
        print(f"KV cache measurement: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
