#!/usr/bin/env python3
"""Offline tests: production integration seams for store/SELECTED/graph/final master."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_store as ps
from final_master_audit import audit_job_dir, build_normalize_concat_plan


def test_generate_video_lacks_autogrow_emission_documented():
    text = (ROOT / "generate_video.py").read_text(encoding="utf-8", errors="ignore")
    assert "ref_images.ref_image" not in text
    assert (ROOT / "gvd_graph_builder.py").is_file()


def test_minimax_ref2vid_uses_or_imports_graph_builder():
    text = (ROOT / "local_agent" / "minimax_ref2vid.py").read_text(encoding="utf-8", errors="ignore")
    assert ("gvd_graph_builder" in text) or ("ref_images.ref_image_0" in text)


def test_selected_only_final_master_rejects_rendered():
    fault = ROOT / "live_jobs" / "remaining_20260918_111727" / "fault_job"
    if not fault.is_dir():
        print("SKIP fault_job missing")
        return
    report = audit_job_dir(fault)
    assert report["ok"] is False


def test_concat_plan_does_not_silently_execute():
    fake = ROOT / "ref_outputs" / "fake_job_section13"
    if not fake.is_dir():
        print("SKIP fake_job_section13 missing")
        return
    plan = build_normalize_concat_plan(fake)
    assert plan.get("executed") in (False, None)


def test_store_resume_gates_exist():
    assert hasattr(ps, "resume_should_skip_attempt")
    assert hasattr(ps, "select_attempt")
    assert hasattr(ps, "prepare_vram_or_raise")


def main() -> int:
    tests = [
        test_generate_video_lacks_autogrow_emission_documented,
        test_minimax_ref2vid_uses_or_imports_graph_builder,
        test_selected_only_final_master_rejects_rendered,
        test_concat_plan_does_not_silently_execute,
        test_store_resume_gates_exist,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", fn.__name__, e)
    print("summary", {"ok": failed == 0, "failed": failed, "total": len(tests)})
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
