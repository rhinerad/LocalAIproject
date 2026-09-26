#!/usr/bin/env python3
"""Submit PromptTester + GVDPromptPlan to live Comfy. CPU node, no diffusion."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMFY = "http://127.0.0.1:8188"
PROMPT = (
    "empty yellow carpet hallway receding into the distance, yellow curtain "
    "at the far end, white walls, fluorescent lights, camcorder still, no people"
)
OUT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "smoke_prompttester_comfy.json"


def post(path: str, payload: dict, timeout=30):
    req = urllib.request.Request(
        COMFY + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str, timeout=60):
    with urllib.request.urlopen(COMFY + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    report = {"utc": datetime.now(timezone.utc).isoformat()}
    info = get("/object_info")
    missing = [c for c in ("PromptTester", "GVDPromptPlan") if c not in info]
    if missing:
        report["status"] = "blocked"
        report["missing"] = missing
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    graph = {
        "1": {"class_type": "PromptTester", "inputs": {
            "prompt": PROMPT, "delimiter": ",", "include_baseline": True}},
        "61": {"class_type": "GVDPromptPlan", "inputs": {
            "prompts": ["1", 0], "labels": ["1", 1]}},
    }
    queued = get("/queue")
    if queued.get("queue_running") or queued.get("queue_pending"):
        report["status"] = "blocked"
        report["reason"] = "comfy busy"
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    data = post("/prompt", {"prompt": graph, "client_id": uuid.uuid4().hex})
    pid = data.get("prompt_id")
    report["prompt_id"] = pid
    if not pid:
        report["status"] = "error"
        report["submit"] = data
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1
    deadline = time.time() + 60
    history = None
    while time.time() < deadline:
        hist = get("/history/" + pid)
        item = hist.get(pid)
        if item and item.get("status", {}).get("completed"):
            history = item
            break
        time.sleep(0.3)
    report["history_outputs"] = (history or {}).get("outputs")
    report["history_ui"] = (history or {}).get("status")
    variants = None
    if history:
        node = (history.get("outputs") or {}).get("61") or {}
        variants = node.get("gvd_variants") or node.get("ui")
    report["variants"] = variants
    report["status"] = "ok" if history else "timeout"
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "prompt_id": pid,
                      "has_variants": bool(variants)}, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
