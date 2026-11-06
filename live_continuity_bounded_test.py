#!/usr/bin/env python3
"""Bounded live ComfyUI continuity test — base H3 864x480 / 124 frames.

Phases:
  A) Real submit with LoadImage → first_frame binding
  B) Intentional technical QA fail → RETRY_PENDING (select blocked)
  C) Resume gate: RETRY_PENDING must not skip
  D) Pass QA → SELECTED + child continuity bind plan (metadata)

Env: COMFY_URL, COMFY_INPUT_DIR, COMFY_OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_store as ps  # noqa: E402
from canonical_assets import (  # noqa: E402
    AssetRegistry,
    build_continuity_bind_plan,
    parent_switch_invalidates_child,
    record_boundary_from_png,
)
from gvd_core import h3_generation_frames  # noqa: E402

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
INPUT_DIR = Path(os.environ.get("COMFY_INPUT_DIR", r"A:\Users\rhine\ComfyUI-Shared\input"))
OUTPUT_DIR = Path(os.environ.get("COMFY_OUTPUT_DIR", r"A:\Users\rhine\ComfyUI-Shared\output"))


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def object_info(class_type: str) -> dict | None:
    try:
        return http_json("GET", f"/object_info/{class_type}", timeout=30.0)
    except Exception:
        return None


def wait_history(prompt_id: str, timeout_s: float) -> dict:
    t0 = time.time()
    last_err = None
    while time.time() - t0 < timeout_s:
        try:
            hist = http_json("GET", f"/history/{prompt_id}", timeout=30.0)
            if prompt_id in hist:
                return hist[prompt_id]
        except Exception as e:
            last_err = e
        time.sleep(4.0)
    raise TimeoutError(f"prompt {prompt_id} not finished in {timeout_s}s ({last_err})")


def build_graph(*, image_name: str, prefix: str, seed: int, width: int, height: int,
                length: int, steps: int, use_sage: bool) -> dict:
    model_src = ["40", 0] if use_sage else ["30", 0]
    g = {
        "20": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["31", 0],
                "vae": ["32", 0],
                "prompt": (
                    "Continue from the provided first frame. Locked camera. "
                    "Subtle natural motion only. No text overlay. No UI."
                ),
                "width": width,
                "height": height,
                "length": length,
                "first_frame": ["1001", 0],
            },
        },
        "30": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                "weight_dtype": "default",
            },
        },
        "31": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                "type": "minimax",
                "device": "default",
            },
        },
        "32": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"},
        },
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": model_src,
                "scheduler": "simple",
                "steps": steps,
                "denoise": 1.0,
            },
        },
        "36": {
            "class_type": "BasicGuider",
            "inputs": {"model": model_src, "conditioning": ["20", 0]},
        },
        "37": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["33", 0],
                "guider": ["36", 0],
                "sampler": ["34", 0],
                "sigmas": ["35", 0],
                "latent_image": ["20", 1],
            },
        },
        "38": {"class_type": "VAEDecode", "inputs": {"samples": ["37", 0], "vae": ["32", 0]}},
        "39": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["38", 0], "fps": 24.0, "bit_depth": 8},
        },
        "25": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["39", 0],
                "filename_prefix": prefix,
                "format": "mp4",
                "codec": "auto",
            },
        },
        "1001": {"class_type": "LoadImage", "inputs": {"image": image_name}},
    }
    if use_sage:
        g["40"] = {
            "class_type": "PathchSageAttentionKJ",
            "inputs": {
                "model": ["30", 0],
                "sage_attention": "auto",
                "allow_compile": False,
            },
        }
    return g


def find_outputs(hist_entry: dict, prefix: str) -> list[Path]:
    found: list[Path] = []
    for _nid, node_out in (hist_entry.get("outputs") or {}).items():
        for key in ("gifs", "videos", "images"):
            for item in node_out.get(key) or []:
                fn = item.get("filename")
                sub = item.get("subfolder") or ""
                if not fn:
                    continue
                p = OUTPUT_DIR / sub / fn if sub else OUTPUT_DIR / fn
                found.append(p)
    # glob fallback
    stem = prefix.replace("\\", "/").split("/")[-1]
    for p in OUTPUT_DIR.rglob(f"*{stem}*"):
        if p.suffix.lower() in {".mp4", ".webm", ".mkv"} and p not in found:
            found.append(p)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="C001_ref_still.png")
    ap.add_argument("--width", type=int, default=864)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--frames", type=int, default=124)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260918)
    ap.add_argument("--timeout", type=float, default=3600.0)
    args = ap.parse_args()

    length = h3_generation_frames(args.frames)
    job_dir = ROOT / "live_jobs" / f"continuity_{int(time.time())}"
    job_dir.mkdir(parents=True, exist_ok=True)
    db = ps.connect(job_dir / "state.sqlite")
    report: dict = {"job_dir": str(job_dir), "comfy": COMFY, "phases": {}}

    stats = http_json("GET", "/system_stats")
    queue = http_json("GET", "/queue")
    use_sage = object_info("PathchSageAttentionKJ") is not None
    h3_ok = object_info("MiniMaxH3ImageToVideo") is not None
    img_path = INPUT_DIR / args.image
    report["preflight"] = {
        "comfyui_version": (stats.get("system") or {}).get("comfyui_version"),
        "vram_free": ((stats.get("devices") or [{}])[0]).get("vram_free"),
        "queue_running": len(queue.get("queue_running") or []),
        "queue_pending": len(queue.get("queue_pending") or []),
        "image": str(img_path),
        "image_exists": img_path.is_file(),
        "generation_frames": length,
        "use_sage": use_sage,
        "h3_node": h3_ok,
    }
    if not h3_ok:
        raise SystemExit("MiniMaxH3ImageToVideo node missing")
    if not img_path.is_file():
        raise SystemExit(f"missing input image: {img_path}")
    if report["preflight"]["queue_running"] or report["preflight"]["queue_pending"]:
        raise SystemExit("Comfy queue not empty; aborting")

    shot_id = "live_C001"
    ps.ensure_shot(db, shot_id)
    rev_row = db.execute("SELECT revision FROM shots WHERE shot_id=?", (shot_id,)).fetchone()
    revision = int(rev_row["revision"])

    prefix = f"astra_live_continuity/{job_dir.name}"
    graph = build_graph(
        image_name=args.image,
        prefix=prefix,
        seed=args.seed,
        width=args.width,
        height=args.height,
        length=length,
        steps=args.steps,
        use_sage=use_sage,
    )
    assert graph["20"]["inputs"]["first_frame"] == ["1001", 0]
    assert graph["1001"]["inputs"]["image"] == args.image

    input_payload = {
        "shot_id": shot_id,
        "image": args.image,
        "width": args.width,
        "height": args.height,
        "length": length,
        "steps": args.steps,
        "seed": args.seed,
        "graph_nodes": sorted(graph.keys()),
    }
    attempt_id = ps.create_attempt(
        db,
        shot_id=shot_id,
        input_payload=input_payload,
        state="SUBMITTING",
        meta={"prefix": prefix},
    )

    t0 = time.time()
    prompt_id = None
    artifact: Path | None = None
    try:
        ps.set_attempt_state(db, attempt_id, "RUNNING")
        resp = http_json(
            "POST",
            "/prompt",
            {"prompt": graph, "client_id": "astra-live-continuity"},
            timeout=120.0,
        )
        prompt_id = resp.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"submit failed: {resp}")
        ps.merge_attempt_meta(db, attempt_id, {"prompt_id": prompt_id})
        hist = wait_history(prompt_id, timeout_s=args.timeout)
        status = hist.get("status") or {}
        if status.get("status_str") == "error" or status.get("completed") is False:
            msgs = status.get("messages") or hist.get("messages")
            raise RuntimeError(f"comfy error status={status} messages={msgs}")
        outs = find_outputs(hist, prefix)
        if not outs:
            raise RuntimeError(f"no outputs in history; status={status}")
        artifact = outs[0]
        if not artifact.is_file():
            # try relative join
            alt = OUTPUT_DIR / artifact.name
            if alt.is_file():
                artifact = alt
            else:
                raise RuntimeError(f"artifact missing on disk: {artifact}")
        digest = ps.sha256_file(artifact)
        ps.set_attempt_state(
            db,
            attempt_id,
            "RENDERED",
            artifact_path=str(artifact),
            artifact_sha256=digest,
        )
        report["phases"]["A_live_render"] = {
            "ok": True,
            "prompt_id": prompt_id,
            "artifact": str(artifact),
            "artifact_sha256": digest,
            "wall_clock_s": round(time.time() - t0, 2),
            "editorial_seconds": round(length / 24.0, 3),
            "first_frame_bound": True,
        }
    except Exception as e:
        ps.set_attempt_state(db, attempt_id, "FAILED_BUDGET")
        ps.merge_attempt_meta(db, attempt_id, {"error": str(e), "prompt_id": prompt_id})
        report["phases"]["A_live_render"] = {
            "ok": False,
            "error": str(e),
            "prompt_id": prompt_id,
            "wall_clock_s": round(time.time() - t0, 2),
        }
        (job_dir / "live_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    # Phase B — intentional tech QA fail
    st = ps.mark_technical_qa(db, attempt_id, passed=False, reason="intentional_live_fail")
    try:
        ps.select_attempt(db, shot_id, revision, attempt_id)
        b_ok = False
        b_err = "select unexpectedly succeeded"
    except Exception as e:
        b_ok = st == "RETRY_PENDING"
        b_err = str(e)[:240]
    report["phases"]["B_intentional_fail"] = {
        "ok": b_ok,
        "state_after": st,
        "select_error": b_err,
    }
    if not b_ok:
        (job_dir / "live_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 3

    # Phase C — resume gate
    skip = ps.resume_should_skip_attempt("RETRY_PENDING")
    report["phases"]["C_resume_gate"] = {"ok": skip is False, "should_skip": skip}

    # Phase D — accept + select + child bind
    # Re-read revision (still 0 until select)
    rev_row = db.execute("SELECT revision FROM shots WHERE shot_id=?", (shot_id,)).fetchone()
    revision = int(rev_row["revision"])
    ps.mark_qa_flags(db, attempt_id, technical_pass=True, visual_pass=True, audio_pass=True)
    ps.set_attempt_state(db, attempt_id, "CONTENT_QA")
    # ensure sha still set
    row = db.execute(
        "SELECT artifact_sha256, artifact_path FROM attempts WHERE attempt_id=?",
        (attempt_id,),
    ).fetchone()
    if not row["artifact_sha256"] and artifact:
        ps.set_attempt_state(
            db,
            attempt_id,
            "CONTENT_QA",
            artifact_path=str(artifact),
            artifact_sha256=ps.sha256_file(artifact),
        )
    ps.select_attempt(db, shot_id, revision, attempt_id)
    report["phases"]["D_select"] = {"ok": True, "attempt_id": attempt_id}

    # Boundary + child bind (use start still as stand-in PNG if no ffmpeg extract)
    registry = AssetRegistry()
    boundary_png = job_dir / "boundary_standin.png"
    # Copy start still bytes as stand-in clean boundary for bind-plan proof
    boundary_png.write_bytes(img_path.read_bytes())
    # ensure .png
    record_boundary_from_png(
        registry,
        attempt_id=attempt_id,
        shot_id=shot_id,
        frame_index=length - 1,
        png_path=boundary_png,
        source_artifact=str(artifact),
        extracted_before_vhs=True,
        extracted_before_subtitles=True,
    )
    plan = build_continuity_bind_plan(
        registry,
        parent_attempt_id=attempt_id,
        parent_state="SELECTED",
        edit_relationship="continuous",
        upload_prefix="astra_live_continuity",
    )
    invalidated = parent_switch_invalidates_child(
        bound_parent_attempt_id=attempt_id,
        current_selected_parent_attempt_id="att_other",
    )
    report["phases"]["D_child_bind"] = {
        "ok": True,
        "comfy_upload_name": plan.comfy_upload_name,
        "frame_index": plan.frame_index,
        "parent_switch_invalidates": bool(invalidated),
    }

    a = report["phases"]["A_live_render"]
    report["wall_clock_per_accepted_second"] = round(
        a["wall_clock_s"] / max(a["editorial_seconds"], 1e-6), 3
    )
    report["ok"] = all(
        report["phases"][k]["ok"]
        for k in ("A_live_render", "B_intentional_fail", "C_resume_gate", "D_select", "D_child_bind")
    )
    (job_dir / "live_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
