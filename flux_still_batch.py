#!/usr/bin/env python3
"""Generate/approve Backrooms Flux boundary stills using qualified 4:3 canvas.

Pilot-friendly: --only C001 C002 or --limit N. Shared-boundary aliases copy
approved last-frame of N as start of N+1 when configured.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

import backrooms_still_contract as bsc
import creative_still_qa
from creative_still_qa import empty_pov_prompt_boost, infer_visibility_expectation

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
SHARED_INPUT = Path(os.environ.get("COMFY_INPUT", r"A:\Users\rhine\ComfyUI-Shared\input"))
SHARED_OUTPUT = Path(os.environ.get("COMFY_OUTPUT", r"A:\Users\rhine\ComfyUI-Shared\output"))
POLICY_PATH = ROOT / "live_jobs" / "flux_canvas_qualify_20260918" / "flux_canvas_policy.json"
COMPILED = ROOT / "outputs_compile" / "clips_compiled.json"
STILL_ROOT = SHARED_INPUT / "astra_backrooms_stills"
JOB_DIR = ROOT / "live_jobs" / "flux_stills_batch_20260918"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def http_json(method, path, body=None, timeout=180.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{COMFY}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:2000]}") from e


def free():
    try:
        http_json("POST", "/free", {"unload_models": True, "free_memory": True})
        time.sleep(2)
    except Exception as e:
        return str(e)
    return "ok"


def nvidia_used():
    try:
        o = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        )
        return int(o.strip().splitlines()[0])
    except Exception:
        return None


class Peak:
    def __init__(self):
        self.peak = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()
        self._t.join(5)
        return self.peak

    def _run(self):
        while not self._stop.is_set():
            v = nvidia_used()
            if v is not None:
                self.peak = max(self.peak, v)
            self._stop.wait(1.0)


def wait(pid, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = http_json("GET", f"/history/{pid}")
        if pid in h:
            return h[pid]
        time.sleep(3)
    raise TimeoutError(pid)


def load_policy() -> dict:
    if not POLICY_PATH.is_file():
        raise FileNotFoundError(f"missing canvas policy: {POLICY_PATH}; run flux_canvas_qualify.py first")
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not policy.get("qualified"):
        raise RuntimeError("canvas policy not qualified")
    return policy


def build_flux_graph(*, prompt: str, negative: str, policy: dict, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": policy["checkpoint"]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or "blurry, watermark, text, logo", "clip": ["1", 1]}},
        "4": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": float(policy.get("guidance", 3.5))}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": int(policy["width"]),
                "height": int(policy["height"]),
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "ModelSamplingFlux",
            "inputs": {
                "model": ["1", 0],
                "max_shift": 1.15,
                "base_shift": 0.5,
                "width": int(policy["width"]),
                "height": int(policy["height"]),
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["6", 0],
                "seed": seed,
                "steps": int(policy.get("steps_default", 20)),
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["4", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0],
                "denoise": 1.0,
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def find_png(hist_outputs, subfolder_hint: str) -> Path:
    if isinstance(hist_outputs, dict):
        for node_out in hist_outputs.values():
            if not isinstance(node_out, dict):
                continue
            for item in node_out.get("images") or []:
                if not isinstance(item, dict):
                    continue
                fn = item.get("filename")
                sub = item.get("subfolder") or ""
                if fn:
                    p = SHARED_OUTPUT / sub / fn
                    if p.is_file():
                        return p
    folder = SHARED_OUTPUT / subfolder_hint
    pngs = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        raise FileNotFoundError(subfolder_hint)
    return pngs[0]


def auto_approve(
    path: Path,
    policy: dict,
    *,
    prompt: str = "",
    anchor: Path | None = None,
    clip: dict | None = None,
    kind: str = "last",
    creative: bool = True,
) -> tuple[bool, list[str], dict]:
    """Technical size/aspect gate + optional prompt-aware creative continuity QA."""
    reasons: list[str] = []
    report: dict = {"technical": {}, "creative": None}
    try:
        from PIL import Image

        im = Image.open(path)
        w, h = im.size
    except Exception as e:
        return False, [f"open_failed:{e}"], report
    report["technical"] = {"width": w, "height": h}
    if w != int(policy["width"]) or h != int(policy["height"]):
        reasons.append(f"size_{w}x{h}_expected_{policy['width']}x{policy['height']}")
    if abs((w / h) - (4 / 3)) > 0.02:
        reasons.append(f"aspect_{w/h:.4f}_not_4_3")
    if path.stat().st_size < 10_000:
        reasons.append("file_too_small")
    if reasons:
        return False, reasons, report
    if creative and prompt:
        ok_c, creasons, crep = creative_still_qa.creative_approve(
            path, prompt=prompt, anchor=anchor, clip=clip, kind=kind
        )
        report["creative"] = crep
        if not ok_c:
            reasons.extend([f"creative:{r}" for r in creasons])
            return False, reasons, report
    return True, reasons, report


def render_one(*, clip_id: str, kind: str, prompt: str, negative: str, policy: dict, seed: int, clip: dict | None = None, anchor: Path | None = None, creative: bool = True) -> dict:
    prefix = f"astra_backrooms_stills/{clip_id}_{kind}"
    g = build_flux_graph(prompt=prompt, negative=negative, policy=policy, seed=seed, prefix=prefix)
    free()
    mon = Peak()
    mon.start()
    t0 = time.time()
    resp = http_json("POST", "/prompt", {"prompt": g, "client_id": f"astra-still-{clip_id}-{kind}"})
    pid = resp.get("prompt_id")
    if not pid:
        raise RuntimeError(str(resp))
    print(f"SUBMIT {clip_id}_{kind} prompt_id={pid}", flush=True)
    hist = wait(pid)
    st = hist.get("status") or {}
    if st.get("status_str") == "error":
        raise RuntimeError(str(st.get("messages"))[:1500])
    peak = mon.stop()
    png = find_png(hist.get("outputs"), "astra_backrooms_stills")
    # Move/copy into stable input asset path
    asset_name = f"{clip_id}_{kind}.png"
    dest = STILL_ROOT / asset_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(png, dest)
    ok, reasons, qa_report = auto_approve(
        dest,
        policy,
        prompt=prompt,
        anchor=anchor,
        clip=clip,
        kind=kind,
        creative=creative,
    )
    rec = {
        "clip_id": clip_id,
        "kind": kind,
        "asset_id": f"{clip_id}_approved_{kind}_frame",
        "comfy_output": str(png),
        "path": str(dest),
        "sha256": sha256_file(dest),
        "approved": ok,
        "reject_reasons": reasons,
        "qa": qa_report,
        "prompt_id": pid,
        "wall_clock_s": round(time.time() - t0, 2),
        "peak_mib": peak,
        "seed": seed,
    }
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=[], help="Clip ids e.g. C001 C002")
    ap.add_argument("--limit", type=int, default=None, help="Max stills to generate this run")
    ap.add_argument("--kinds", nargs="*", default=["start", "last"], help="start and/or last")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed-offset", type=int, default=0, help="Add to per-clip seeds for regen")
    ap.add_argument("--max-creative-retries", type=int, default=3, help="Retries when creative QA rejects")
    args = ap.parse_args()

    JOB_DIR.mkdir(parents=True, exist_ok=True)
    policy = load_policy()
    if args.steps:
        policy = dict(policy)
        policy["steps_default"] = args.steps

    compiled = json.loads(COMPILED.read_text(encoding="utf-8"))
    clips = compiled["clips"] if isinstance(compiled, dict) else compiled
    by_id = {c["id"]: c for c in clips}

    # Load or init approvals registry
    registry_path = JOB_DIR / "stills_approved.json"
    if registry_path.is_file():
        approved = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        approved = {}

    targets: list[tuple[str, str]] = []
    only = {x.upper() for x in args.only} if args.only else None
    for c in clips:
        cid = c["id"]
        if only and cid not in only:
            continue
        for kind in args.kinds:
            targets.append((cid, kind))
    if args.limit is not None:
        targets = targets[: args.limit]

    results = []
    for idx, (cid, kind) in enumerate(targets):
        c = by_id[cid]
        field = "start_frame" if kind == "start" else "last_frame"
        prompt = str(c.get(field) or "").strip()
        negative = str(c.get(f"{field}_negative") or "").strip()
        if not prompt:
            results.append({"clip_id": cid, "kind": kind, "ok": False, "error": "empty_prompt"})
            continue
        # Shared-boundary alias: start of N+1 may reuse approved last of N
        refs = c.get("references") or {}
        if kind == "start" and cid != "C001":
            prev_num = int(cid[1:]) - 1
            prev_id = f"C{prev_num:03d}"
            prev_asset = f"{prev_id}_approved_last_frame"
            if prev_asset in approved and approved[prev_asset].get("approved"):
                src = Path(approved[prev_asset]["path"])
                if src.is_file():
                    dest = STILL_ROOT / f"{cid}_start.png"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    registry_key = f"{cid}_approved_start_frame"
                    compile_start_id = refs.get("start") or registry_key
                    asset_id = registry_key  # never use refs.start as registry key
                    rec = {
                        "clip_id": cid,
                        "kind": "start",
                        "asset_id": asset_id,
                        "path": str(dest),
                        "sha256": sha256_file(dest),
                        "approved": True,
                        "aliased_from": prev_asset,
                        "compile_ref_id": compile_start_id,
                        "reject_reasons": [],
                    }
                    approved[registry_key] = rec
                    results.append(rec)
                    print(f"ALIAS {cid}_start <- {prev_asset}", flush=True)
                    continue

        if args.dry_run:
            results.append({"clip_id": cid, "kind": kind, "dry_run": True, "prompt_chars": len(prompt)})
            continue

        seed = 1000 + int(cid[1:]) * 10 + (0 if kind == "start" else 1) + int(getattr(args, "seed_offset", 0))
        try:
            # Continuity anchor: previous approved last (or C001 last for C001 start).
            anchor = None
            if kind == "last":
                prev_num = int(cid[1:]) - 1
                if prev_num >= 1:
                    prev_key = f"C{prev_num:03d}_approved_last_frame"
                    if prev_key in approved and approved[prev_key].get("approved"):
                        anchor = Path(approved[prev_key]["path"])
                # also compare last against this clip start when present
                start_key = f"{cid}_approved_start_frame"
                if start_key in approved and approved[start_key].get("approved"):
                    anchor = Path(approved[start_key]["path"])
                elif cid == "C001" and (STILL_ROOT / "C001_start.png").is_file():
                    anchor = STILL_ROOT / "C001_start.png"
            elif kind == "start" and cid != "C001":
                prev_num = int(cid[1:]) - 1
                prev_key = f"C{prev_num:03d}_approved_last_frame"
                if prev_key in approved and approved[prev_key].get("approved"):
                    anchor = Path(approved[prev_key]["path"])
            registry_key = f"{cid}_approved_{kind}_frame"
            compile_ref_id = refs.get(kind) or registry_key
            rec = None
            attempts = max(1, int(getattr(args, "max_creative_retries", 3)))
            # Harden empty-POV generations once per clip (not per retry).
            try:
                _exp = infer_visibility_expectation(prompt=prompt, clip=c, kind=kind)
                if _exp.expect_empty_of_people:
                    prompt, _neg_boost = empty_pov_prompt_boost(prompt)
                    if _neg_boost not in (negative or ''):
                        negative = ((negative + ', ') if negative else '') + _neg_boost
            except Exception as _e:
                print(f'WARN empty_pov_prompt_boost failed: {_e}', flush=True)
            for attempt in range(attempts):
                attempt_seed = seed + attempt * 97
                rec = render_one(
                    clip_id=cid,
                    kind=kind,
                    prompt=prompt,
                    negative=negative,
                    policy=policy,
                    seed=attempt_seed,
                    clip=c,
                    anchor=anchor,
                    creative=True,
                )
                rec["asset_id"] = registry_key
                rec["compile_ref_id"] = compile_ref_id
                rec["attempt"] = attempt
                if rec.get("approved"):
                    break
                print(f"CREATIVE_REJECT {cid}_{kind} attempt={attempt} reasons={rec.get('reject_reasons')}", flush=True)
            if rec and rec.get("approved"):
                approved[registry_key] = {
                    "asset_id": registry_key,
                    "compile_ref_id": compile_ref_id,
                    "path": rec["path"],
                    "sha256": rec["sha256"],
                    "approved": True,
                    "clip_id": cid,
                    "kind": kind,
                    "empty_pov": True,
                }
                if cid == "C001" and kind == "start" and compile_ref_id == "generate_initial_anchor":
                    approved["generate_initial_anchor"] = dict(approved[registry_key])
                    approved["generate_initial_anchor"]["asset_id"] = "generate_initial_anchor"
            results.append(rec if rec is not None else {"clip_id": cid, "kind": kind, "approved": False, "error": "no_rec"})
        except Exception as e:
            results.append({"clip_id": cid, "kind": kind, "ok": False, "error": str(e)[:1500]})

        registry_path.write_text(json.dumps(approved, indent=2), encoding="utf-8")

    # Contract check on generated subset
    contract_ok = True
    contract_errors = []
    for cid in sorted({r.get("clip_id") for r in results if r.get("clip_id")}):
        c = dict(by_id[cid])
        try:
            bsc.assert_stills_approved_for_animation(c, approved)
        except Exception as e:
            # expected until both start+last approved
            contract_errors.append(f"{cid}:{e}")
            contract_ok = False

    report = {
        "ok": all(r.get("approved") or r.get("aliased_from") or r.get("dry_run") for r in results if "error" not in r)
        and not any(r.get("error") for r in results),
        "policy": {k: policy[k] for k in ("checkpoint", "resolution_label", "width", "height", "aspect_ratio")},
        "generated": len(results),
        "approved_registry_count": sum(1 for v in approved.values() if v.get("approved")),
        "results": results,
        "contract_subset_ok": contract_ok,
        "contract_errors": contract_errors[:20],
    }
    out = JOB_DIR / "batch_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    registry_path.write_text(json.dumps(approved, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "results"}, indent=2), flush=True)
    print(json.dumps(results, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
