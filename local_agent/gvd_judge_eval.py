"""Score the labeled GVD judge set with a judge variant and report its errors.

Existing renders only: this never starts ComfyUI and never renders. It loads
the Qwen2.5-VL judge (llama.cpp) once, scores every labeled clip, releases it.

    python gvd_judge_eval.py run --variant baseline      # judge as of 2026-09-24 before the fix
    python gvd_judge_eval.py run --variant production    # whatever dspy_orchestrator judges with now
    python gvd_judge_eval.py report runtime/dspy_opt/judge_eval/results_<variant>.jsonl

Labels: runtime/dspy_opt/judge_eval/gvd_judge_labels.json (human-reviewed).
The VLM score ranks clips; it does not accept them.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVAL_DIR = HERE / "runtime" / "dspy_opt" / "judge_eval"
LABELS = EVAL_DIR / "gvd_judge_labels.json"
OWNER = ROOT / "batch_render_queue_owner.json"
AXES = ("text_video_alignment", "temporal_consistency", "aesthetic_quality")
# Curriculum iteration 0 (0.60) and the strict bar (0.80 since 2026-09-24,
# was 0.85). 0.85 is kept in the report so the old bar stays comparable.
THRESHOLDS = (0.60, 0.80, 0.85)


def load_labels(path: Path = LABELS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def embedded_prompts(video: Path) -> tuple[str, str]:
    """FLUX (node 6) and MiniMax (node 20) text from the MP4's embedded workflow."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=prompt", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout
    graph = json.loads(json.loads(out)["format"]["tags"]["prompt"])
    return (str(graph["6"]["inputs"]["text"]), str(graph["20"]["inputs"]["prompt"]))


def case_for(item: dict, video_dir: Path) -> dict:
    """Example/pred-shaped inputs for one labeled clip."""
    import generalized_video_director as gvd

    video = video_dir / f"{item['clip']}_00001_.mp4"
    start, motion = embedded_prompts(video)
    clip_id = item["clip"].split("_")[1]           # GVD-D01 / c005
    row = next((r for r in gvd.BETA_SET if r.get("id") == clip_id), None)
    if row is not None:
        intent, constraints = str(row.get("user_intent") or ""), str(row.get("constraints") or "")
    else:  # Backrooms batch clip: its brief is the prompt pair the operator approved
        intent, constraints = f"{start} {motion}".strip(), ""
    return {"id": clip_id, "video": video, "start_prompt": start, "video_prompt": motion,
            "user_intent": intent, "constraints": constraints}


# ---------------------------------------------------------------- variants

def judge_baseline(case: dict) -> dict:
    """Verbatim copy of evaluate_live_candidate's judging block as of 2026-09-24
    (before the judge fix): 8 uniform frames, student prompts only, holistic
    scores emitted before the rationale."""
    import dspy_orchestrator as dso
    from media_accuracy_gate import build_video_director_vlm_system_prompt, build_vlm_user_prompt

    frames = dso.extract_eval_frames(Path(case["video"]))
    system = build_video_director_vlm_system_prompt(literal_mode=False, literal_rule=None)
    user = build_vlm_user_prompt(start_prompt=case["start_prompt"], video_prompt=case["video_prompt"],
                                 literal_mode=False, expected_scene=case["start_prompt"])
    return dso.run_qwen_director_scores(frames, user, system_prompt=system)


def judge_production(case: dict) -> dict:
    """The judge the live metric uses now."""
    import dspy_orchestrator as dso

    example = {"id": case["id"], "user_intent": case["user_intent"], "constraints": case["constraints"]}
    return dso.judge_rendered_clip(example, Path(case["video"]), start_prompt=case["start_prompt"],
                                   motion_prompt=case["video_prompt"])


def _judge_with_frames(case: dict, frames: list[Path]) -> dict:
    import dspy_orchestrator as dso

    example = {"id": case["id"], "user_intent": case["user_intent"], "constraints": case["constraints"]}
    return dso.judge_rendered_clip(example, Path(case["video"]), start_prompt=case["start_prompt"],
                                   motion_prompt=case["video_prompt"], extract=lambda _p: frames)


def judge_f12(case: dict) -> dict:
    """Fixed judge with 12 uniform frames (extract_eval_frames' upper clamp)."""
    import dspy_optimizer

    return _judge_with_frames(case, dspy_optimizer.extract_eval_frames(Path(case["video"]), count=12))


def judge_f8c(case: dict) -> dict:
    """Fixed judge with the 8 uniform frames plus up to 4 frames just after the
    largest picture changes (same 12-frame budget as f12)."""
    import dspy_optimizer
    import video_judge as vj

    video = Path(case["video"])
    uniform = dspy_optimizer.extract_eval_frames(video, count=8)
    times = vj.frame_times_from_names(uniform) or []
    extra_t = vj.change_times(vj._decode_small(video), 24.0, k=4, avoid_s=times)
    extra = vj.extract_frames_at(video, extra_t, uniform[0].parent) if extra_t else []
    frames = sorted(uniform + extra, key=lambda p: vj.frame_times_from_names([p])[0])
    return _judge_with_frames(case, frames)


VARIANTS = {"baseline": judge_baseline, "production": judge_production,
            "f12": judge_f12, "f8c": judge_f8c}


# ---------------------------------------------------------------- safety

def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def preflight(emit=print) -> None:
    import router
    sys.path.insert(0, str(ROOT / "work"))
    import thermal_guard

    if _port_open(8188):
        raise SystemExit("port 8188 is listening; refusing to load the VLM beside ComfyUI")
    idle, why = router._owners_idle_for_timeshare()
    if not idle:
        raise SystemExit(f"a render queue owner is live: {why}")
    sample = thermal_guard.sample_gpu()
    if sample.temperature_c > thermal_guard.START_MAX_C:
        raise SystemExit(f"GPU {sample.temperature_c} C > {thermal_guard.START_MAX_C} C start ceiling")
    emit(f"preflight ok: 8188 closed, owners idle, GPU {sample.temperature_c} C")


def _launch_logged_vlm(log_path: Path) -> None:
    """Start the owned Qwen2.5-VL llama-server exactly as dspy_optimizer does,
    but with its output in a log (the production launch discards it, so a
    crash leaves no trace). Registered as the owned process, so the normal
    release_after_vlm stops it."""
    import capabilities
    import dspy_optimizer
    import llama_cpp_client

    if llama_cpp_client.up(capabilities.QWEN25_VL_RUNTIME_HOST):
        raise SystemExit("a Qwen2.5-VL server is already listening; not starting a second one")
    host = capabilities.QWEN25_VL_RUNTIME_HOST
    args = [str(capabilities.QWEN25_VL_LLAMA_SERVER), "--model", str(capabilities.QWEN25_VL_GGUF),
            "--mmproj", str(capabilities.QWEN25_VL_MMPROJ), "--host", host.rsplit(":", 1)[0],
            "--port", host.rsplit(":", 1)[1], "--ctx-size", "32768", "--n-gpu-layers", "99",
            "--image-min-tokens", "1024", "--flash-attn", "auto", "--no-webui"]
    proc = subprocess.Popen(args, stdout=log_path.open("ab"), stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    dspy_optimizer._QWEN25_VL_PROC = proc
    capabilities._write_qwen25_vl_runtime_state(proc.pid)
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"llama-server exited rc={proc.returncode}; see {log_path}")
        if llama_cpp_client.up(host):
            return
        time.sleep(1)
    raise SystemExit("llama-server did not become healthy in 420 s")


def _connection_error(err: str | None) -> bool:
    return bool(err) and any(k in err for k in ("ConnectionResetError", "ConnectionRefusedError",
                                                "RemoteDisconnected", "ConnectionAbortedError"))


def run(variant: str, out: Path, only: list[str] | None = None, retry_errors: bool = False,
        labels_path: Path = LABELS) -> Path:
    import psutil
    import vram_controller
    sys.path.insert(0, str(ROOT / "work"))
    import thermal_guard

    labels = load_labels(labels_path)
    video_dir = Path(labels["video_dir"])
    judge = VARIANTS[variant]
    done = set()
    if out.exists():
        latest = {r["clip"]: r for r in load_records(out, latest=False)}
        done = {c for c, r in latest.items() if not (retry_errors and r.get("error"))}
    todo = [i for i in labels["items"] if i["clip"] not in done and (not only or i["clip"] in only)]
    print(f"{variant}: {len(todo)} to score, {len(done)} already in {out.name}", flush=True)
    if not todo:
        return out
    preflight()
    owner = json.loads(OWNER.read_text()) if OWNER.exists() else {}
    if owner.get("pid") and psutil.pid_exists(int(owner["pid"])):
        raise SystemExit(f"queue owned: {owner}")
    OWNER.write_text(json.dumps({"pid": os.getpid(), "purpose": f"GVD judge eval ({variant}), VLM only",
                                 "since": time.time()}), encoding="utf-8")
    try:
        vram_controller.prepare_for_vlm(reason=f"GVD judge eval {variant}")
        server_log = out.with_suffix(".llama_server.log")
        _launch_logged_vlm(server_log)
        for n, item in enumerate(todo, 1):
            thermal_guard.check_running_ceiling(print, item["clip"])
            case = case_for(item, video_dir)
            t0 = time.time()
            retried = None
            for attempt in (1, 2):
                try:
                    parsed = judge(case)
                    err = None
                except Exception as exc:  # recorded, scored as a fail
                    parsed, err = {}, f"{type(exc).__name__}: {exc}"
                if not _connection_error(err) or attempt == 2:
                    break
                # Server died mid-request; the owned-runtime check relaunches it.
                print(f"  {item['clip']}: {err}; server log {server_log}; retrying once", flush=True)
                thermal_guard.check_running_ceiling(print, item["clip"])
                retried = err
            rec = {"clip": item["clip"], "label": item["label"], "confidence": item["confidence"],
                   "variant": variant, "seconds": round(time.time() - t0, 1), "error": err,
                   "retried_after": retried,
                   "status": parsed.get("status"), "scores": parsed.get("scores"),
                   "scores_vlm": parsed.get("scores_vlm"), "signals": parsed.get("signals"),
                   "minimum": parsed.get("minimum"), "mean": parsed.get("mean"),
                   "reasons": parsed.get("reasons"), "checks": parsed.get("checks"),
                   "caps": parsed.get("caps"), "retry": parsed.get("retry"),
                   "raw": (parsed.get("raw") or "")[:6000]}
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[{n}/{len(todo)}] {item['label']:7s} {item['clip']:26s} "
                  f"min={rec['minimum']} scores={rec['scores']} "
                  f"{'retried ' if rec['retry'] else ''}{err or ''}", flush=True)
    finally:
        try:
            vram_controller.release_after_vlm(reason=f"GVD judge eval {variant} complete")
        finally:
            OWNER.write_text(json.dumps({"pid": 0, "purpose": "released (GVD judge eval)",
                                         "released_at": time.time()}), encoding="utf-8")
        thermal_guard.wait_after_render(print)
    return out


# ---------------------------------------------------------------- report

def _passes(rec: dict, threshold: float) -> bool:
    return (rec.get("status") == "pass" and rec.get("minimum") is not None
            and float(rec["minimum"]) >= threshold)


def _scalar(rec: dict) -> float:
    if rec.get("status") != "pass" or rec.get("minimum") is None:
        return 0.0
    return 0.7 * float(rec["minimum"]) + 0.3 * float(rec["mean"])


def summarize(records: list[dict], labels: dict | None = None) -> dict:
    labels = labels or load_labels()
    faults = {i["clip"]: i["faults"] for i in labels["items"]}
    triples = Counter(tuple((r.get("scores") or {}).get(a) for a in AXES)
                      for r in records if r.get("scores"))
    scored = sum(triples.values())
    rep: dict = {"n": len(records), "scored": scored, "distinct_triples": len(triples),
                 "top_triples": [[list(t), c] for t, c in triples.most_common(3)],
                 "top_triple_share": round(triples.most_common(1)[0][1] / scored, 3) if scored else None}
    for th in THRESHOLDS:
        key = f"{th:.2f}"
        for subset, keep in (("all", lambda r: True), ("high_conf", lambda r: r["confidence"] == "high")):
            rs = [r for r in records if keep(r)]
            rej = [r for r in rs if r["label"] == "reject"]
            good = [r for r in rs if r["label"] == "good"]
            part = [r for r in rs if r["label"] == "partial"]
            fp = [r["clip"] for r in rej if _passes(r, th)]
            ff = [r["clip"] for r in good if not _passes(r, th)]
            rep[f"@{key}_{subset}"] = {
                "false_pass": f"{len(fp)}/{len(rej)}", "false_pass_rate": round(len(fp) / len(rej), 3) if rej else None,
                "false_fail": f"{len(ff)}/{len(good)}", "false_fail_rate": round(len(ff) / len(good), 3) if good else None,
                "partial_pass": f"{sum(_passes(r, th) for r in part)}/{len(part)}",
                "false_pass_clips": fp, "false_fail_clips": ff,
            }
    goods = [_scalar(r) for r in records if r["label"] == "good"]
    rejs = [_scalar(r) for r in records if r["label"] == "reject"]
    if goods and rejs:
        wins = sum((g > b) + 0.5 * (g == b) for g in goods for b in rejs)
        rep["auc_good_vs_reject"] = round(wins / (len(goods) * len(rejs)), 3)
    missed = Counter()
    total = Counter()
    for r in records:
        if r["label"] != "reject":
            continue
        for f in faults.get(r["clip"], []):
            total[f] += 1
            if _passes(r, THRESHOLDS[0]):
                missed[f] += 1
    rep["reject_faults_passed@0.60"] = {f: f"{missed[f]}/{total[f]}" for f in sorted(total)}
    rep["errors"] = [r["clip"] for r in records if r.get("error") or r.get("status") != "pass"]
    # 2026-09-25k: clips whose first answer had no scores and were asked again.
    rep["retried"] = [r["clip"] for r in records if r.get("retry")]
    rep["retry_recovered"] = [r["clip"] for r in records if (r.get("retry") or {}).get("recovered")]
    return rep


def load_records(path: Path, latest: bool = True) -> list[dict]:
    """All records, or (latest=True) the last record per clip (a retried error is superseded)."""
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not latest:
        return records
    return list({r["clip"]: r for r in records}.values())


def report(path: Path, labels_path: Path = LABELS) -> dict:
    records = load_records(path)
    rep = summarize(records, load_labels(labels_path))
    print(json.dumps(rep, indent=1))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    r.add_argument("--out", type=Path)
    r.add_argument("--only", nargs="*")
    r.add_argument("--labels", type=Path, default=LABELS)
    r.add_argument("--retry-errors", action="store_true", help="re-score clips whose latest record is an error")
    p = sub.add_parser("report")
    p.add_argument("path", type=Path)
    p.add_argument("--labels", type=Path, default=LABELS)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        out = args.out or (EVAL_DIR / f"results_{args.variant}.jsonl")
        run(args.variant, out, args.only, args.retry_errors, args.labels)
        report(out, args.labels)
    else:
        report(args.path, args.labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
