#!/usr/bin/env python3
"""Receipt-gated Wan I2V: hash-locked still only, measured 480x256 5-frame graph."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.i2v_gate import apply_qa_gate
from gvd_tool_router.gpu_lease import acquire
from gvd_tool_router.paths import GvdLayout
from gvd_tool_router.smoke_measure import preflight, run_one

COMFY = "http://127.0.0.1:8188"
COMFY_INPUT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\input")
RECEIPT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "jobs" / "br24_C017_end_20260921T182819Z" / "accepted.json"
RUBRIC = HERE / "profiles" / "br24_c017_end_rubric.json"
GRAPH = ROOT / "local_agent" / "gvd_tool_router" / "fixtures" / "wan_i2v_smoke.api.json"
OUT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "smoke_i2v_from_receipt.json"


def bind_start_image(graph: dict, filename: str, prefix: str = "gvd_qa/i2v_from_receipt",
                     num_frames: int | None = None, steps: int | None = None) -> dict:
    graph = json.loads(json.dumps(graph))
    if "5" not in graph or graph["5"].get("class_type") != "LoadImage":
        raise RuntimeError("Wan I2V fixture missing LoadImage node 5")
    graph["5"]["inputs"]["image"] = filename
    graph["9"]["inputs"]["filename_prefix"] = prefix
    if num_frames is not None:
        graph["6"]["inputs"]["num_frames"] = int(num_frames)
    if steps is not None:
        graph["7"]["inputs"]["steps"] = int(steps)
    return graph


def upload_input_png(png: bytes, name: str) -> str:
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    dest = COMFY_INPUT / name
    dest.write_bytes(png)
    bound = uuid.uuid4().hex
    body = bytearray()
    def part(n: str, v: bytes, filename: str | None = None, ctype: str | None = None):
        body.extend(f"--{bound}\r\n".encode())
        disp = f'Content-Disposition: form-data; name="{n}"'
        if filename:
            disp += f'; filename="{filename}"'
        body.extend((disp + "\r\n").encode())
        if ctype:
            body.extend(f"Content-Type: {ctype}\r\n".encode())
        body.extend(b"\r\n")
        body.extend(v)
        body.extend(b"\r\n")
    part("image", png, name, "image/png")
    part("overwrite", b"true")
    part("type", b"input")
    body.extend(f"--{bound}--\r\n".encode())
    req = urllib.request.Request(
        COMFY + "/upload/image",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={bound}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return str(payload.get("name") or name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", default=str(RECEIPT))
    parser.add_argument("--rubric", default=str(RUBRIC))
    parser.add_argument("--policy-id", default="observed_5080_c017_end_v1")
    parser.add_argument("--report", default=str(OUT))
    parser.add_argument("--prefix", default="gvd_qa/i2v_from_receipt")
    parser.add_argument("--upload-name", default="gvd_qa_c017_end_accepted.png")
    parser.add_argument("--num-frames", type=int, default=None)
    parser.add_argument("--timeout-s", type=int, default=1200)
    parser.add_argument("--steps", type=int, default=None)
    args_cli = parser.parse_args()
    dest = Path(args_cli.report)
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "receipt": str(args_cli.receipt),
        "note": "Measured Wan I2V 480x256 5 frames 4 steps. Receipt-gated. Not a production length clip.",
    }
    args = SimpleNamespace(
        allow_ungated_i2v=False,
        require_qa_receipt=True,
        qa_receipt=str(args_cli.receipt),
        qa_candidate=None,
        qa_job_dir=None,
        qa_policy_json=None,
        qa_requirements_json=str(args_cli.rubric),
        qa_generation_graph=None,
        qa_policy_id=str(args_cli.policy_id),
    )
    code, still = apply_qa_gate(args, root=ROOT, local_agent=HERE.parent)
    if code is not None or still is None:
        report["status"] = "blocked"
        report["gate_exit"] = code
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 4
    report["accepted_still"] = str(still)
    png = Path(still).read_bytes()
    try:
        preflight()
        uploaded = upload_input_png(png, str(args_cli.upload_name))
        graph = bind_start_image(
            json.loads(GRAPH.read_text(encoding="utf-8")),
            uploaded,
            prefix=str(args_cli.prefix),
            num_frames=args_cli.num_frames,
            steps=args_cli.steps,
        )
        report["load_image"] = uploaded
        layout = GvdLayout.from_env()
        layout.ensure()
        with acquire(layout, job_id="gvd-qa-i2v-receipt", attempt_id="c017-end", family_key="wan"):
            result = run_one(graph, family="wan", layout=layout,
                             timeout_s=int(args_cli.timeout_s), poll_s=3.0)
        report.update(result)
        try:
            urllib.request.urlopen(urllib.request.Request(
                COMFY + "/free",
                data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            ), timeout=60)
        except Exception:
            pass
        report["status"] = result.get("status") or "error"
    except Exception as exc:
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": report.get("status"),
        "peak_used_mib": report.get("peak_used_mib"),
        "peak_gpu_mib": report.get("peak_gpu_mib"),
        "prompt_id": report.get("prompt_id"),
        "accepted_still": report.get("accepted_still"),
        "wrote": str(dest),
    }, indent=2))
    return 0 if report.get("status") == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
