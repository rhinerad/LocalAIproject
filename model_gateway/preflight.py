#!/usr/bin/env python3
"""Gateway preflight: is every tier reachable, and is the cloud tier armed?

Read-only. Probes the two Ollama servers and port 8188 the way router.py
does (TCP + /api/tags + /api/ps), checks the SDK and credential presence,
and prints the environment block for pointing Claude Code at a local model.
Never starts a server, never loads a model, never downloads anything.

    python model_gateway/preflight.py            # report
    python model_gateway/preflight.py --strict   # exit 1 if the cloud tier is armed but broken
    python model_gateway/preflight.py --cloud-check   # one 8-token round trip (costs tokens)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import model_gateway as gw  # noqa: E402

GPU_HOST = os.environ.get("EQUAL_SHARES_GPU_HOST", "127.0.0.1:11434")
CPU_HOST = os.environ.get("EQUAL_SHARES_CPU_HOST", "127.0.0.1:11435")
COMFY_PORT = 8188


def _tcp(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _get_json(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)[:120]}


def _ollama(host: str) -> dict:
    h, _, p = host.partition(":")
    up = _tcp(h, int(p or 11434))
    tags = _get_json(f"http://{host}/api/tags") if up else {}
    ps = _get_json(f"http://{host}/api/ps") if up else {}
    return {
        "host": host,
        "up": up,
        "models": sorted(m.get("name", "?") for m in (tags.get("models") or [])) if up else [],
        "resident": sorted(m.get("name", "?") for m in (ps.get("models") or [])) if up else [],
        "anthropic_endpoint": f"http://{host}/v1/messages",
    }


def _cloud_check(cfg: gw.GatewayConfig) -> dict:
    from model_gateway.adapters import get_backend
    backend = get_backend("anthropic", cfg)
    pieces = list(backend.stream(model=cfg.fast.model,
                                 messages=[{"role": "user", "content": "Reply with the single word: ready"}],
                                 options={"max_tokens": 16, "effort": "low"}))
    text = "".join(p.text for p in pieces if isinstance(p, gw.TextDelta)).strip()
    done = next((p for p in pieces if isinstance(p, gw.Done)), None)
    return {"ok": True, "model": done.model if done else cfg.fast.model, "reply": text[:60],
            "usage": (done.telemetry.get("gateway") if done else {})}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="exit 1 when the cloud tier is enabled but unusable")
    ap.add_argument("--cloud-check", action="store_true", help="send one tiny request to the fast tier")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    cfg = gw.load_config()
    report = {
        "gateway": cfg.public_dict(),
        "health": gw.status_snapshot(cfg).get("health"),
        "gpu_ollama": _ollama(GPU_HOST),
        "cpu_ollama": _ollama(CPU_HOST),
        "comfy_8188_listening": _tcp("127.0.0.1", COMFY_PORT),
        "python": sys.version.split()[0],
    }
    problems: list[str] = []
    if cfg.cloud_enabled:
        if not cfg.credential_present:
            problems.append("MODEL_GATEWAY_CLOUD=1 but no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN")
        if not (report["health"] or {}).get("sdk_installed"):
            problems.append("anthropic SDK not importable: pip install -r model_gateway/requirements.txt")
    if not report["cpu_ollama"]["up"]:
        problems.append(f"CPU Ollama {CPU_HOST} is down (compaction/memory/plans need it)")
    if args.cloud_check and cfg.cloud_enabled and not problems:
        try:
            report["cloud_check"] = _cloud_check(cfg)
        except gw.CloudUnavailable as exc:
            report["cloud_check"] = {"ok": False, "kind": exc.kind, "detail": exc.detail}
            problems.append(f"cloud check failed: {exc.kind}: {exc.detail}")
    report["problems"] = problems

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        g = report["gateway"]
        print("model_gateway preflight")
        print(f"  cloud tier      : {'ENABLED' if g['cloud_enabled'] else 'off'}  "
              f"(credential {'present via ' + g['credential_source'] if g['credential_present'] else 'MISSING'})")
        print(f"  endpoint        : {g['base_url']}  {'(official)' if g['official_endpoint'] else '(custom base URL)'}")
        print(f"  heavy tier      : {g['heavy']['model']}  effort={g['heavy']['effort']}")
        print(f"  fast tier       : {g['fast']['model']}  effort={g['fast']['effort']}  "
              f"(busy-GPU turns {'on' if g['busy_tier_enabled'] else 'off'})")
        h = report["health"] or {}
        print(f"  anthropic SDK   : {'v' + str(h.get('sdk_version')) if h.get('sdk_installed') else 'not installed'}")
        for key in ("gpu_ollama", "cpu_ollama"):
            o = report[key]
            print(f"  {key:<15} : {o['host']}  {'UP' if o['up'] else 'DOWN'}  "
                  f"models={len(o['models'])}  resident={o['resident'] or '[]'}")
        print(f"  ComfyUI :8188   : {'LISTENING (GPU busy -> fast tier / CPU)' if report['comfy_8188_listening'] else 'closed'}")
        if "cloud_check" in report:
            c = report["cloud_check"]
            print(f"  cloud check     : {'OK ' + str(c.get('model')) + ' -> ' + repr(c.get('reply')) if c.get('ok') else 'FAILED ' + str(c)}")
        print()
        print("Claude Code against a local model (goal 2; no gateway process needed):")
        print(f"  $env:ANTHROPIC_BASE_URL   = \"http://{CPU_HOST}\"   # or {GPU_HOST} when 8188 is closed")
        print("  $env:ANTHROPIC_AUTH_TOKEN = \"ollama\"               # accepted, not validated")
        print("  $env:ANTHROPIC_MODEL      = \"<an installed Ollama tag>\"")
        print("  claude")
        if problems:
            print()
            for p in problems:
                print(f"  PROBLEM: {p}")
    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
