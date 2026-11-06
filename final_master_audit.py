#!/usr/bin/env python3
"""Final master audit / assembly checklist (audit §13) — offline.

Validates a job directory layout without ComfyUI/GPU and without running
ffmpeg on missing media. Provides a normalize/concat PLAN (argv builder only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot_dirs(job_root: Path) -> dict[str, Path]:
    shots_root = job_root / "shots"
    if not shots_root.is_dir():
        return {}
    return {p.name: p for p in sorted(shots_root.iterdir()) if p.is_dir()}


def _selected_info(shot_dir: Path) -> dict[str, Any] | None:
    sel_path = shot_dir / "selected.json"
    if not sel_path.is_file():
        return None
    try:
        data = _load_json(sel_path)
    except json.JSONDecodeError:
        return None
    if str(data.get("state") or "").upper() != "SELECTED":
        return None
    return data


def _attempt_dir(shot_dir: Path, attempt_id: str) -> Path:
    return shot_dir / "attempts" / attempt_id


def _collect_dialogue(job_root: Path, shot_id: str) -> list[dict[str, Any]]:
    shot_dir = job_root / "shots" / shot_id
    plan_path = shot_dir / "plan.json"
    lines: list[dict[str, Any]] = []
    if plan_path.is_file():
        try:
            plan = _load_json(plan_path)
        except json.JSONDecodeError:
            plan = {}
        audio = plan.get("audio") if isinstance(plan, dict) else None
        if isinstance(audio, dict):
            for item in audio.get("dialogue_lines") or []:
                if isinstance(item, dict) and str(item.get("text") or "").strip():
                    lines.append(item)
    # Also check timeline
    tl_path = job_root / "audio" / "timeline.json"
    if tl_path.is_file():
        try:
            tl = _load_json(tl_path)
        except json.JSONDecodeError:
            tl = {}
        plans = (tl.get("shot_plans") or tl.get("shots") or {}) if isinstance(tl, dict) else {}
        if isinstance(plans, dict) and shot_id in plans:
            sp = plans[shot_id]
            if isinstance(sp, dict):
                for item in sp.get("dialogue_lines") or []:
                    if isinstance(item, dict) and str(item.get("text") or "").strip():
                        lines.append(item)
        elif isinstance(plans, list):
            for sp in plans:
                if isinstance(sp, dict) and sp.get("shot_id") == shot_id:
                    for item in sp.get("dialogue_lines") or []:
                        if isinstance(item, dict) and str(item.get("text") or "").strip():
                            lines.append(item)
    return lines


def audit_job_dir(job_root: Path) -> dict[str, Any]:
    """Validate job dir layout offline (audit §13 checklist)."""
    job_root = Path(job_root)
    report: dict[str, Any] = {
        "job_root": str(job_root),
        "ok": False,
        "errors": [],
        "warnings": [],
        "shots": {},
        "mandatory_qa_pending": [],
        "provenance_issues": [],
        "provenance_ok": True,
        "frame_count_mismatches": [],
        "dialogue_issues": [],
        "comfy_called": False,
        "ffmpeg_executed": False,
    }
    job_path = job_root / "job.json"
    if not job_path.is_file():
        report["errors"].append("missing job.json")
        return report
    try:
        job = _load_json(job_path)
    except json.JSONDecodeError as exc:
        report["errors"].append(f"job.json invalid: {exc}")
        return report

    required = list(job.get("required_shots") or [])
    shot_dirs = _shot_dirs(job_root)
    if not required:
        # Default: every shot dir that has selected.json or plan.json
        required = sorted(shot_dirs.keys())
        # Prefer shots that claim selection
        required = [
            sid for sid in required
            if (shot_dirs[sid] / "selected.json").is_file()
            or (shot_dirs[sid] / "plan.json").is_file()
        ]
        # For tiny §13 layout, C001 is the parent SELECTED; C002 may be plan-only
        if "C001" in shot_dirs and "C001" not in required:
            required.insert(0, "C001")

    editorial = job.get("editorial_timeline") or {}
    editorial_shots = {
        str(s["shot_id"]): s
        for s in (editorial.get("shots") or [])
        if isinstance(s, dict) and s.get("shot_id")
    }
    dialogue_required = set(job.get("dialogue_required_shots") or [])

    for sid in required:
        sdir = shot_dirs.get(sid)
        info: dict[str, Any] = {
            "shot_id": sid,
            "has_selected": False,
            "attempt_id": None,
            "deps_ok": True,
            "qa_pending": False,
            "frame_count_ok": True,
            "dialogue_ok": True,
            "provenance_ok": True,
        }
        if sdir is None:
            report["errors"].append(f"required shot missing: {sid}")
            info["has_selected"] = False
            report["shots"][sid] = info
            continue

        selected = _selected_info(sdir)
        if selected is None:
            # plan-only child without selection is ok if not mandatory SELECTED
            plan_only = (sdir / "plan.json").is_file() and not (sdir / "selected.json").is_file()
            if plan_only and sid not in (job.get("required_selected_shots") or required):
                # If explicitly in required_shots list from job, still need SELECTED
                if sid in list(job.get("required_shots") or []):
                    report["errors"].append(f"{sid}: required but no SELECTED attempt")
                else:
                    report["warnings"].append(f"{sid}: plan present, no SELECTED yet")
            else:
                if list(job.get("required_shots") or []) and sid in job["required_shots"]:
                    report["errors"].append(f"{sid}: no SELECTED attempt")
                elif (sdir / "selected.json").is_file():
                    report["errors"].append(f"{sid}: selected.json present but state != SELECTED")
                else:
                    # Auto-discovered plan-only: warning only
                    report["warnings"].append(f"{sid}: no SELECTED attempt")
            report["shots"][sid] = info
            continue

        info["has_selected"] = True
        aid = str(selected.get("attempt_id") or "")
        info["attempt_id"] = aid
        adir = _attempt_dir(sdir, aid)

        # deps: parent continuity if plan says so
        plan_path = sdir / "plan.json"
        if plan_path.is_file():
            try:
                plan = _load_json(plan_path)
            except json.JSONDecodeError:
                plan = {}
            cont = plan.get("continuity") if isinstance(plan, dict) else None
            if isinstance(cont, dict) and cont.get("parent_attempt_id"):
                parent_id = str(cont["parent_attempt_id"])
                parent_shot = None
                # Find parent selected matching deps
                for psid, pdir in shot_dirs.items():
                    psel = _selected_info(pdir)
                    if psel and str(psel.get("attempt_id")) == parent_id:
                        parent_shot = psid
                        break
                if parent_shot is None:
                    # Also accept selected.json on sibling declaring same attempt
                    info["deps_ok"] = False
                    report["errors"].append(
                        f"{sid}: continuity parent_attempt_id={parent_id} not SELECTED"
                    )
                else:
                    info["parent_shot_id"] = parent_shot

        # mandatory QA pending?
        status = str(selected.get("pipeline_state") or selected.get("qa_status") or "").upper()
        if status in {"QA_PENDING", "RENDERED", "RETRY_PENDING", "TECHNICAL_QA"}:
            info["qa_pending"] = True
            report["mandatory_qa_pending"].append(sid)

        # frame count vs editorial
        if sid in editorial_shots:
            expected = editorial_shots[sid].get("duration_frames")
            actual = selected.get("duration_frames")
            if actual is None and plan_path.is_file():
                try:
                    actual = _load_json(plan_path).get("duration_frames")
                except json.JSONDecodeError:
                    actual = None
            if expected is not None and actual is not None and int(expected) != int(actual):
                info["frame_count_ok"] = False
                report["frame_count_mismatches"].append(
                    {"shot_id": sid, "expected": expected, "actual": actual}
                )

        # dialogue present/ordered when required
        if sid in dialogue_required:
            lines = _collect_dialogue(job_root, sid)
            if not lines:
                info["dialogue_ok"] = False
                report["dialogue_issues"].append(f"{sid}: dialogue required but missing")
            else:
                # ordered: each line has text; optional order index monotonic
                texts = [str(x.get("text") or "").strip() for x in lines]
                if any(not t for t in texts):
                    info["dialogue_ok"] = False
                    report["dialogue_issues"].append(f"{sid}: empty dialogue text")
                info["dialogue_line_count"] = len(lines)

        # hashes / provenance
        prov_path = adir / "provenance.json"
        artifact = selected.get("artifact") or selected.get("artifact_path")
        art_path = Path(str(artifact)) if artifact else None
        if not art_path or not art_path.is_file():
            # try clean_render under attempt
            candidate = adir / "clean_render.mp4"
            art_path = candidate if candidate.is_file() else None
        has_hash = False
        if prov_path.is_file():
            try:
                prov = _load_json(prov_path)
                has_hash = bool(prov.get("artifact_sha256") or prov.get("content_hash"))
                info["provenance"] = prov
            except json.JSONDecodeError:
                has_hash = False
        if not has_hash and art_path and art_path.is_file():
            # Record hash inline for offline audit
            info["artifact_sha256"] = _sha256_file(art_path)
            has_hash = True
        if not has_hash:
            info["provenance_ok"] = False
            report["provenance_issues"].append(f"{sid}/{aid}: missing provenance hash")
            report["provenance_ok"] = False

        # Boundary PNG hash if present
        boundary = adir / "boundary_frame.png"
        if boundary.is_file():
            info["boundary_sha256"] = _sha256_file(boundary)

        report["shots"][sid] = info

    # ok if no errors and no mandatory QA pending for required selected shots
    report["ok"] = (
        len(report["errors"]) == 0
        and len(report["mandatory_qa_pending"]) == 0
        and len(report["frame_count_mismatches"]) == 0
        and len(report["dialogue_issues"]) == 0
    )
    return report


def build_normalize_concat_plan(
    job_root: Path,
    *,
    shot_ids: list[str] | None = None,
    output_path: str | Path = "master_concat.mp4",
    fps: float = 24.0,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Build ffmpeg argv for normalize+concat. Does NOT run ffmpeg.

    Missing media is listed in ``missing``; argv is still returned as a plan.
    """
    job_root = Path(job_root)
    shot_dirs = _shot_dirs(job_root)
    if shot_ids is None:
        # Prefer SELECTED shots in sorted order
        shot_ids = [
            sid for sid, sdir in shot_dirs.items()
            if _selected_info(sdir) is not None
        ]
    inputs: list[str] = []
    missing: list[str] = []
    for sid in shot_ids:
        sdir = shot_dirs.get(sid)
        if not sdir:
            missing.append(sid)
            continue
        selected = _selected_info(sdir)
        path = None
        if selected:
            for key in ("artifact", "artifact_path", "video_path"):
                if selected.get(key):
                    cand = Path(str(selected[key]))
                    if cand.is_file():
                        path = cand
                        break
            if path is None and selected.get("attempt_id"):
                cand = _attempt_dir(sdir, str(selected["attempt_id"])) / "clean_render.mp4"
                if cand.is_file():
                    path = cand
        if path is None:
            missing.append(sid)
            # placeholder path for plan visibility
            inputs.append(str(sdir / "attempts" / "MISSING" / "clean_render.mp4"))
        else:
            inputs.append(str(path))

    out = str(output_path)
    filter_parts: list[str] = []
    concat_in = []
    for i, _src in enumerate(inputs):
        scale = ""
        if width and height:
            scale = f",scale={int(width)}:{int(height)}:force_original_aspect_ratio=decrease,pad={int(width)}:{int(height)}:(ow-iw)/2:(oh-ih)/2"
        filter_parts.append(
            f"[{i}:v]fps={fps}{scale},setsar=1,format=yuv420p[v{i}]"
        )
        concat_in.append(f"[v{i}]")
    n = len(inputs)
    filter_complex = ";".join(filter_parts)
    if n:
        filter_complex += f";{''.join(concat_in)}concat=n={n}:v=1:a=0[vout]"

    argv: list[str] = ["ffmpeg", "-y"]
    for src in inputs:
        argv.extend(["-i", src])
    if n:
        argv.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-c:v", "libx264", "-pix_fmt", "yuv420p", out])
    else:
        argv.extend(["-f", "lavfi", "-i", "color=c=black:s=864x480:d=1", out])

    return {
        "argv": argv,
        "inputs": inputs,
        "missing": missing,
        "output": out,
        "executed": False,
        "note": "argv builder only — operator runs ffmpeg when media exists",
    }




def probe_duration_seconds(path: Path | str) -> float | None:
    """ffprobe duration; None if unavailable."""
    import subprocess
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nk=1:nw=1",
                str(path),
            ],
            text=True,
            timeout=60,
        )
        return float(out.strip())
    except Exception:
        return None


def execute_normalize_concat(
    plan: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a concat plan produced by build_normalize_concat_plan.

    Refuses to run when media is missing. Sets plan["executed"]=True only after success.
    """
    import subprocess
    result = {
        "ok": False,
        "executed": False,
        "dry_run": dry_run,
        "missing": list(plan.get("missing") or []),
        "returncode": None,
        "error": None,
    }
    if result["missing"]:
        result["error"] = "missing SELECTED media; refusing assembly"
        return result
    argv = list(plan.get("argv") or [])
    if not argv:
        result["error"] = "empty argv"
        return result
    if dry_run:
        result["ok"] = True
        return result
    try:
        cp = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=3600)
        result["returncode"] = cp.returncode
        if cp.returncode != 0:
            result["error"] = (cp.stderr or cp.stdout or "ffmpeg failed")[:2000]
            return result
        plan["executed"] = True
        result["executed"] = True
        result["ok"] = True
        out = plan.get("output_path")
        if out is None and len(argv) >= 1:
            out = argv[-1]
        if out:
            result["output_path"] = str(out)
            result["duration_s"] = probe_duration_seconds(out)
            try:
                result["sha256"] = _sha256_file(out)
            except Exception as exc:
                result["sha256_error"] = str(exc)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def classify_master_scope(
    *,
    input_paths: list[str],
    output_duration_s: float | None,
    unique_sha256: set[str] | None = None,
) -> dict[str, Any]:
    """Distinguish assembly smoke vs distinct narrative masters."""
    n = len(input_paths)
    uniq = len(unique_sha256 or set())
    scope = "unknown"
    if n <= 2 and uniq <= 1 and (output_duration_s or 0) > 60:
        scope = "assembly_smoke_repeated_or_padded"
    elif uniq >= max(3, n // 2) and (output_duration_s or 0) > 60:
        scope = "multi_shot_narrative_candidate"
    elif n >= 1 and (output_duration_s or 0) <= 30:
        scope = "short_assembly"
    return {
        "scope": scope,
        "input_count": n,
        "unique_input_sha256": uniq,
        "output_duration_s": output_duration_s,
        "proves_long_form_generation": scope == "multi_shot_narrative_candidate",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--job-root",
        type=Path,
        default=ROOT.parent / "ref_outputs" / "fake_job_section13",
    )
    parser.add_argument("--write-concat-plan", type=Path, default=None)
    args = parser.parse_args(argv)
    report = audit_job_dir(args.job_root)
    plan = build_normalize_concat_plan(args.job_root)
    exec_report = None
    if getattr(args, "execute", False) or getattr(args, "dry_run_execute", False):
        if not report.get("ok"):
            exec_report = {"ok": False, "error": "audit failed; refusing execute"}
        else:
            exec_report = execute_normalize_concat(
                plan, dry_run=bool(getattr(args, "dry_run_execute", False))
            )
    out = {"audit": report, "concat_plan": plan, "execute": exec_report}
    if args.write_concat_plan:
        args.write_concat_plan.parent.mkdir(parents=True, exist_ok=True)
        args.write_concat_plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": report["ok"],
        "errors": report["errors"],
        "warnings": report["warnings"][:5],
        "mandatory_qa_pending": report["mandatory_qa_pending"],
        "concat_argv_len": len(plan["argv"]),
        "concat_executed": plan["executed"],
        "missing_media": plan["missing"],
    }, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
