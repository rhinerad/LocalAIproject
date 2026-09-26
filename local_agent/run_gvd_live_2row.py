#!/usr/bin/env python3
"""Owned live proof: 2-row Beta slice, 1 MIPRO trial, VRAM flip-flop log.

Boots Rockernow ComfyUI only if :8188 is down. Refuses if a stranger already
owns :8188 or :11436. Does not overwrite temporal_physics_v1.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SLICE_IDS = ("GVD-B01", "GVD-D01")
SAVE = ROOT / "models" / "dspy_compiled" / "generalized_video_director_mipro_2row.json"
HISTORY = HERE / "runtime" / "dspy_opt" / "gvd_live_metric_history.jsonl"
REPORT = HERE / "runtime" / "dspy_opt" / "gvd_live_2row_report.json"
VRAM_LOG = HERE / "runtime" / "dspy_opt" / "gvd_live_2row_vram.jsonl"


def _smi() -> dict:
    import subprocess

    raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.free,memory.total,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=5,
    )
    used, free, total, temp, util = [p.strip() for p in raw.strip().splitlines()[0].split(",")]
    return {
        "used_mib": int(float(used)),
        "free_mib": int(float(free)),
        "total_mib": int(float(total)),
        "temp_c": float(temp),
        "util": float(util),
        "ts": time.time(),
    }


def _port(port: int) -> bool:
    import socket

    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def preflight() -> dict:
    qwen_live = _port(11436)
    comfy_live = _port(8188)
    ollama_live = _port(11434)
    smi = _smi()
    report = {
        "comfy_8188": comfy_live,
        "qwen_11436": qwen_live,
        "ollama_11434": ollama_live,
        "vram": smi,
    }
    if qwen_live:
        raise RuntimeError("rogue Qwen on :11436; refusing live Wan load")
    if not ollama_live:
        raise RuntimeError("Ollama is not on :11434; student LM cannot compile")
    return report


def main() -> int:
    print("=== GVD live 2-row preflight ===", flush=True)
    pf = preflight()
    print(json.dumps(pf, indent=2), flush=True)

    watch = None
    if not pf["comfy_8188"]:
        print("ComfyUI :8188 is down. Booting owned Rockernow backend.", flush=True)
        from backrooms_watch import BackroomsWatch

        watch = BackroomsWatch()
        watch.acquire()
        watch.restart("gvd_live_2row")
        pf = preflight()
        print("backend ready", json.dumps(pf["vram"]), flush=True)
    else:
        print("ComfyUI already on :8188; using existing backend.", flush=True)

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text("", encoding="utf-8")
    traces = ROOT / "logs" / "run_traces"
    traces.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    compile_log = traces / f"gvd_run_rows2_{stamp}.log"
    vram_trace = traces / f"gvd_run_rows2_{stamp}_vram.jsonl"
    print(f"cli: python local_agent/dspy_orchestrator.py --run --rows 2", flush=True)
    print(f"compile log: {compile_log}", flush=True)

    import subprocess
    import threading

    stop_vram = threading.Event()

    def _vram_loop():
        while not stop_vram.wait(5):
            sample = _smi()
            sample.update({"comfy": _port(8188), "qwen": _port(11436)})
            with vram_trace.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(sample) + "\n")

    vram_thread = threading.Thread(target=_vram_loop, daemon=True)
    vram_thread.start()

    t0 = time.time()
    code = 1
    err = None
    try:
        cmd = [
            sys.executable, "-u", str(HERE / "dspy_orchestrator.py"),
            "--run", "--rows", "2",
            "--trials", "1", "--candidates", "1",
            "--save", str(SAVE),
        ]
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        with compile_log.open("w", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                cmd, cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT, env=env,
            )
            code = int(proc.wait())
        if code != 0:
            err = f"orchestrator exit {code}"
            print(f"COMPILE FAILED: {err}", flush=True)
        else:
            print(f"compile saved {SAVE}", flush=True)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        print(f"COMPILE FAILED: {err}", flush=True)
        code = 1
    finally:
        stop_vram.set()
        final_vram = _smi()
        history = []
        if HISTORY.exists():
            for line in HISTORY.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    history.append(json.loads(line))
        b01 = [row for row in history if row.get("clip_id") == "GVD-B01"]
        report = {
            "elapsed_s": round(time.time() - t0, 1),
            "exit_code": code,
            "error": err,
            "slice": list(SLICE_IDS),
            "saved": str(SAVE),
            "preflight": pf,
            "final_vram": final_vram,
            "history": history,
            "gvd_b01": b01[-1] if b01 else None,
            "gvd_b01_n": len(b01),
        }
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        (traces / f"gvd_run_rows2_{stamp}_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8",
        )
        print("=== REPORT ===", flush=True)
        print(json.dumps({
            "elapsed_s": report["elapsed_s"],
            "exit_code": code,
            "error": err,
            "final_vram": final_vram,
            "gvd_b01_n": len(b01),
            "gvd_b01": b01[-1] if b01 else None,
        }, indent=2), flush=True)
        if watch is not None:
            print("Stopping owned ComfyUI backend.", flush=True)
            try:
                watch.close()
            except Exception as exc:
                print(f"watch.close warning: {exc}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
