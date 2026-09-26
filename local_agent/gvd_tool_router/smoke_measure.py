#!/usr/bin/env python3
"""Live GPU smoke: submit one API graph, sample nvidia-smi, write a local profile.

Does not start or kill ComfyUI. Refuses if the queue is busy or Qwen :11436 is live.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from gvd_tool_router.executor import default_http, prompt_payload
from gvd_tool_router.gpu_lease import acquire
from gvd_tool_router.paths import GvdLayout
from gvd_tool_router.schema import sha256_bytes, sha256_json

COMFY = "http://127.0.0.1:8188"


def _port(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def _smi() -> dict:
    raw = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total,temperature.gpu",
         "--format=csv,noheader,nounits"],
        text=True, timeout=5,
    )
    used, free, total, temp = [p.strip() for p in raw.strip().splitlines()[0].split(",")]
    return {
        "used_mib": int(float(used)),
        "free_mib": int(float(free)),
        "total_mib": int(float(total)),
        "temp_c": int(float(temp)),
        "ts": time.time(),
    }


def _http(path: str, payload=None, method="GET", timeout=30.0):
    return default_http(f"{COMFY}{path}", payload, method, timeout)


def preflight() -> None:
    if not _port(8188):
        raise SystemExit("ComfyUI :8188 is down; this smoke uses the existing backend only")
    if _port(11436):
        raise SystemExit("Qwen :11436 is live; refuse overlapping GPU")
    queue = _http("/queue")
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise SystemExit(f"Comfy queue is busy: {queue}")


def run_one(graph: dict, *, family: str, layout: GvdLayout, timeout_s: float, poll_s: float) -> dict:
    samples = []
    idle = _smi()
    samples.append({"phase": "idle_before", **idle})
    _http("/free", {"unload_models": True, "free_memory": True}, "POST", 60.0)
    time.sleep(2)
    baseline = _smi()
    samples.append({"phase": "after_free", **baseline})
    payload = prompt_payload(graph, client_id="gvd-smoke", attempt_id=family)
    try:
        queued = _http("/prompt", payload, "POST", 60.0)
    except Exception as exc:
        return {
            "status": "queue_rejected",
            "queued": {"error": str(exc)},
            "samples": samples,
            "baseline": baseline,
        }
    if not queued.get("prompt_id"):
        return {"status": "queue_rejected", "queued": queued, "samples": samples, "baseline": baseline}
    prompt_id = queued["prompt_id"]
    deadline = time.time() + timeout_s
    peak_used = baseline["used_mib"]
    last_hist = {}
    while time.time() < deadline:
        mem = _smi()
        mem["phase"] = "running"
        samples.append(mem)
        peak_used = max(peak_used, mem["used_mib"])
        try:
            last_hist = _http(f"/history/{prompt_id}", None, "GET", 15.0)
        except Exception as exc:
            last_hist = {"error": type(exc).__name__}
        entry = last_hist.get(prompt_id) or {}
        status = (entry.get("status") or {}) if isinstance(entry, dict) else {}
        if status.get("completed") or entry.get("outputs"):
            after = _smi()
            samples.append({"phase": "completed", **after})
            extra = peak_used - baseline["used_mib"]
            return {
                "status": "accepted",
                "prompt_id": prompt_id,
                "baseline_used_mib": baseline["used_mib"],
                "peak_used_mib": peak_used,
                "peak_gpu_mib": extra,
                "after_used_mib": after["used_mib"],
                "outputs": entry.get("outputs"),
                "samples": samples,
            }
        msgs = status.get("messages") or []
        for msg in msgs:
            if isinstance(msg, list) and msg and str(msg[0]).lower() in {"error", "execution_error"}:
                return {
                    "status": "failed",
                    "prompt_id": prompt_id,
                    "history": entry,
                    "peak_used_mib": peak_used,
                    "baseline_used_mib": baseline["used_mib"],
                    "peak_gpu_mib": peak_used - baseline["used_mib"],
                    "samples": samples,
                }
        time.sleep(poll_s)
    return {
        "status": "timeout",
        "prompt_id": prompt_id,
        "peak_used_mib": peak_used,
        "baseline_used_mib": baseline["used_mib"],
        "peak_gpu_mib": peak_used - baseline["used_mib"],
        "samples": samples[-8:],
        "history_tail": last_hist,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=["still", "ltx", "ipadapter", "wan", "h3", "montage", "tiled", "propainter", "f5", "musetalk", "wan_dual", "longcat", "h3v2", "wan8", "tile_video"], required=True)
    parser.add_argument("--timeout", type=float, default=1200)
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()
    preflight()
    layout = GvdLayout.from_env()
    layout.ensure()
    graphs = {
        "still": HERE / "fixtures" / "known_good_still.api.json",
        "ltx": HERE / "fixtures" / "ltx23_smoke.api.json",
        "ipadapter": HERE / "fixtures" / "ipadapter_smoke.api.json",
        "wan": HERE / "fixtures" / "wan_i2v_smoke.api.json",
        "h3": HERE / "fixtures" / "h3_fasth3_smoke.api.json",
        "montage": HERE / "fixtures" / "animatediff_fizz_smoke.api.json",
        "tiled": HERE / "fixtures" / "tiled_diffusion_smoke.api.json",
        "propainter": HERE / "fixtures" / "propainter_smoke.api.json",
        "f5": HERE / "fixtures" / "f5tts_smoke.api.json",
        "musetalk": HERE / "fixtures" / "musetalk_smoke.api.json",
        "wan_dual": HERE / "fixtures" / "wan_dual_moe_smoke.api.json",
        "longcat": HERE / "fixtures" / "longcat_ti2v_smoke.api.json",
        "h3v2": HERE / "fixtures" / "h3_fasth3_v2_smoke.api.json",
        "wan8": HERE / "fixtures" / "wan_i2v_8step_smoke.api.json",
        "tile_video": HERE / "fixtures" / "wan_tile_video_smoke.api.json",
    }
    graph_path = graphs[args.family]
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = layout.validation / args.family / stamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.api.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    with acquire(layout, job_id=f"smoke-{args.family}", attempt_id=stamp, family_key=args.family):
        result = run_one(graph, family=args.family, layout=layout, timeout_s=args.timeout, poll_s=args.poll)
    result["family"] = args.family
    result["graph_sha256"] = sha256_bytes(graph_path.read_bytes())
    result["collected_at"] = datetime.now(timezone.utc).isoformat()
    result["evidence"] = "local" if result.get("status") == "accepted" else "unknown"
    (out / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "family": args.family,
        "peak_gpu_mib": result.get("peak_gpu_mib"),
        "peak_used_mib": result.get("peak_used_mib"),
        "baseline_used_mib": result.get("baseline_used_mib"),
        "report": str(out / "report.json"),
        "prompt_id": result.get("prompt_id"),
    }, indent=2))
    return 0 if result.get("status") == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
