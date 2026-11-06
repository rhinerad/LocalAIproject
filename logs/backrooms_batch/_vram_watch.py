#!/usr/bin/env python3
import json, subprocess, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).with_name("vram_phase4.jsonl")
peak = 0
trip = False
print("vram watch start", flush=True)
while True:
    try:
        used = int(float(subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
        ).splitlines()[0].strip()))
    except Exception:
        used = None
    if used is not None:
        peak = max(peak, used)
        print(f"vram used={used} MiB peak={peak} MiB", flush=True)
        LOG.open("a", encoding="utf-8").write(
            json.dumps({"t": datetime.now(timezone.utc).isoformat(), "used": used, "peak": peak}) + "\n"
        )
        if used > 15500 and not trip:
            trip = True
            print(f"VRAM TRIP {used}", flush=True)
            body = json.dumps({"unload_models": True, "free_memory": True}).encode()
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "http://127.0.0.1:8188/interrupt", data=b"{}",
                    headers={"Content-Type": "application/json"}, method="POST",
                ), timeout=5).read()
                urllib.request.urlopen(urllib.request.Request(
                    "http://127.0.0.1:8188/free", data=body,
                    headers={"Content-Type": "application/json"}, method="POST",
                ), timeout=10).read()
            except Exception as exc:
                print("trip fail", exc, flush=True)
    time.sleep(2)
