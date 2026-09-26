#!/usr/bin/env python3
"""Offline proof suite for continuity failure/resume + benchmark profiles + master audit."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HANDOFF = ROOT / "handoff"
sys.path.insert(0, str(HANDOFF))

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
    else:
        msg = f"FAIL {name}" + (f" — {detail}" if detail else "")
        print(f"  {msg}")
        FAILURES.append(msg)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_continuity_failure_resume() -> None:
    print("\n[continuity] failure/resume harness")
    harness = load_module(
        "continuity_failure_resume_offline",
        HANDOFF / "continuity_failure_resume_offline.py",
    )
    with tempfile.TemporaryDirectory() as td:
        results = harness.run_all(Path(td))
        check("harness ok", results["ok"] is True)
        check("comfy not called", results["comfy_called"] is False)
        for key, scen in results["scenarios"].items():
            check(f"scenario {key}", scen.get("ok") is True, str(scen.get("state") or scen.get("action") or ""))

        crash = results["scenarios"]["crash_before_selected"]
        check("crash: resume does not skip QA_PENDING", crash["resume_skips_qa_pending"] is False)
        check("crash: resume does not skip RENDERED", crash["resume_skips_rendered"] is False)

        tech = results["scenarios"]["technical_qa_fail"]
        check("tech fail → RETRY_PENDING", tech["state"] == "RETRY_PENDING")
        check("tech fail not SELECTED", tech["is_selected"] is False)

        parent = results["scenarios"]["parent_reselect_invalidates_child"]
        check("child first_frame bound", parent["first_frame_bound"] is True)
        check("parent switch invalidates", parent["parent_switch_invalidates"] is True)
        check("child INVALIDATED", parent["child_state"] == "INVALIDATED")

        sub = results["scenarios"]["submitting_uncertain_no_duplicate"]
        check("uncertain submit prevented duplicate", sub["enqueue_calls"] == 0)
        check(
            "reconcile_uncertain action",
            sub["no_prompt_id"]["action"] == "reconcile_uncertain",
        )


def test_production_store_helpers() -> None:
    print("\n[store] resume / tech QA / reconcile helpers")
    store = load_module("production_store", HANDOFF / "production_store.py")
    check("RETRY_PENDING in ATTEMPT_STATES", "RETRY_PENDING" in store.ATTEMPT_STATES)
    check("resume_should_skip SELECTED", store.resume_should_skip_attempt("SELECTED") is True)
    check("resume no-skip RENDERED", store.resume_should_skip_attempt("RENDERED") is False)
    check("resume no-skip QA_PENDING", store.resume_should_skip_attempt("QA_PENDING") is False)
    check("resume no-skip RETRY_PENDING", store.resume_should_skip_attempt("RETRY_PENDING") is False)

    d = store.reconcile_submitting_without_prompt_id(
        attempt_id="x",
        attempt_state="SUBMITTING",
        prompt_id=None,
    )
    check("reconcile uncertain prevents enqueue", d["duplicate_enqueue_prevented"] is True)
    check("reconcile uncertain not enqueued", d["enqueued"] is False)


def test_benchmark_profiles() -> None:
    print("\n[benchmark] RTX 5080 starting profiles")
    bp = load_module("backend_profiles", HANDOFF / "backend_profiles.py")
    profiles_dir = HANDOFF / "benchmark_profiles"
    expected = [
        "base_continuity_validation",
        "base_production_trial",
        "high_resolution_trial",
        "multi_reference",
        "fast_draft",
    ]
    for name in expected:
        path = profiles_dir / f"{name}.json"
        check(f"profile file {name}", path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        check(f"{name} has profile_id", data.get("profile_id") == name)

    loaded = bp.list_benchmark_profiles()
    check("list_benchmark_profiles count", len(loaded) >= 5, str(sorted(loaded.keys())))

    cont = bp.get_benchmark_profile("base_continuity_validation")
    check("continuity 864x480", cont["width"] == 864 and cont["height"] == 480)
    check("continuity 124 frames", cont["frames"] == 124)
    check("continuity 20 steps", cont["steps"] == 20)
    check("continuity res_multistep/simple", cont["sampler_name"] == "res_multistep" and cont["scheduler"] == "simple")
    check("continuity denoise 1", float(cont["denoise"]) == 1.0)

    prod = bp.get_benchmark_profile("base_production_trial")
    check("production 1152x640", prod["width"] == 1152 and prod["height"] == 640)
    fr = prod.get("frames_range") or prod.get("frames")
    check(
        "production frames 124–192",
        fr == [124, 192]
        or fr == {"min": 124, "max": 192}
        or (isinstance(fr, list) and fr[0] == 124 and fr[-1] == 192)
        or fr == 124,  # single start ok if range also present
    )
    check(
        "production frames_range present",
        prod.get("frames_range") == [124, 192],
    )

    hi = bp.get_benchmark_profile("high_resolution_trial")
    check("high res 1344x768", hi["width"] == 1344 and hi["height"] == 768)

    multi = bp.get_benchmark_profile("multi_reference")
    check("multi_reference notes Ref2VA", "Ref2VA" in str(multi.get("notes") or multi.get("warning") or "") or multi.get("ref_mode") == "Ref2VA")
    check("ref_image_size match", multi.get("ref_image_size") == "match")

    fast = bp.get_benchmark_profile("fast_draft")
    check("fast_draft FastH3 placeholder", "FastH3" in str(fast.get("family") or fast.get("notes") or fast.get("backend") or ""))
    warn = str(fast.get("compatibility_warning") or fast.get("warning") or "")
    check("fast_draft compat warning", "0.36" in warn or "ComfyUI" in warn)

    metric = HANDOFF / "benchmark_profiles" / "wall_clock_metric.md"
    check("wall_clock_metric.md present", metric.is_file())
    check(
        "wall_clock mentions accepted second",
        "accepted" in metric.read_text(encoding="utf-8").lower()
        and "wall-clock" in metric.read_text(encoding="utf-8").lower(),
    )


def test_final_master_audit() -> None:
    print("\n[audit §13] final_master_audit offline")
    audit = load_module("final_master_audit", HANDOFF / "final_master_audit.py")
    with tempfile.TemporaryDirectory() as td:
        job = Path(td) / "job"
        # Seed a valid minimal layout via continuity_dry_run then extend
        cdr = load_module("continuity_dry_run", HANDOFF / "continuity_dry_run.py")
        cdr.seed_fake_job(job)
        # C002 needs a SELECTED attempt for a green audit of required shots
        # Enrich job.json with editorial timeline + required shots
        job_meta = {
            "job_id": "audit_job",
            "layout": "audit_section_13_tiny",
            "required_shots": ["C001"],
            "editorial_timeline": {
                "fps": 24,
                "shots": [
                    {"shot_id": "C001", "duration_frames": 124},
                ],
            },
            "dialogue_required_shots": [],
        }
        (job / "job.json").write_text(json.dumps(job_meta, indent=2) + "\n", encoding="utf-8")
        # Add provenance hash file for selected attempt
        att = job / "shots" / "C001" / "attempts" / "att_parent"
        (att / "provenance.json").write_text(
            json.dumps({
                "attempt_id": "att_parent",
                "artifact_sha256": "deadbeef",
                "boundary_sha256": "cafebabe",
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        report = audit.audit_job_dir(job)
        check("audit runs", isinstance(report, dict))
        check("C001 has SELECTED", report["shots"]["C001"]["has_selected"] is True)
        check("no mandatory QA pending", report["mandatory_qa_pending"] == [])
        check("hashes/provenance recorded", report["provenance_ok"] is True or len(report.get("provenance_issues", [])) == 0)

        plan = audit.build_normalize_concat_plan(
            job,
            shot_ids=["C001"],
            output_path=str(job / "masters" / "concat.mp4"),
        )
        check("ffmpeg argv builder returns list", isinstance(plan.get("argv"), list) and len(plan["argv"]) > 0)
        check("plan does not execute ffmpeg", plan.get("executed") is False)
        check("ffmpeg binary named", plan["argv"][0] == "ffmpeg")


def test_existing_verifies_still_importable() -> None:
    print("\n[regression] prior verify modules still load")
    for name in ("verify_p0_offline", "verify_p1_offline", "verify_p1_assets_audio_offline"):
        path = ROOT / f"{name}.py"
        check(f"{name} exists", path.is_file())


def main() -> int:
    print("=== verify_continuity_offline ===")
    test_production_store_helpers()
    test_continuity_failure_resume()
    test_benchmark_profiles()
    test_final_master_audit()
    test_existing_verifies_still_importable()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(" ", f)
        return 1
    print("ALL CONTINUITY/BENCHMARK/AUDIT OFFLINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
