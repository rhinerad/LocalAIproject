"""Bind I2V to an accepted still receipt. Used by generate_video before dry-run or submit."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _runner(root: Path):
    spec = importlib.util.spec_from_file_location("_gvd_qa_runner_i2v", root / "gvd_qa.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_qa_runner_i2v", mod)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(local_agent: Path):
    spec = importlib.util.spec_from_file_location(
        "gvd_qa_pipeline_i2v", local_agent / "gvd_qa" / "pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def apply_qa_gate(args: Any, *, root: Path, local_agent: Path) -> tuple[int | None, Path | None]:
    """Return (exit_code, accepted_still). exit_code None means continue to I2V/dry-run."""
    gated = (not getattr(args, "allow_ungated_i2v", False)) and getattr(args, "require_qa_receipt", True)
    if not gated:
        return None, None
    # Baseline runs must not open Caption V4 when it is offline or explicitly skipped.
    # An existing receipt is still hash-checked below; that path does not dial :11436.
    if getattr(args, "skip_visual_qa", False) and not getattr(args, "qa_receipt", None):
        print("VISUAL QA SKIPPED: not contacting 127.0.0.1:11436")
        return None, None
    gvd = _runner(root)
    receipt_path = Path(args.qa_receipt) if getattr(args, "qa_receipt", None) else None
    if getattr(args, "qa_candidate", None) and getattr(args, "qa_job_dir", None) \
            and getattr(args, "qa_policy_json", None) and getattr(args, "qa_requirements_json", None):
        pipe = _pipeline(local_agent)
        from gvd_qa.caption_v4 import caption_v4_checklist
        from gvd_qa.local_client import cpu_local_client
        from gvd_qa.local_phases import CaptionV4Phases
        png = Path(args.qa_candidate).read_bytes()
        qa = cpu_local_client(
            audit_caption=str(getattr(args, "qa_audit_caption", "") or ""),
            checklist_fn=lambda blob, reqs: caption_v4_checklist(blob, reqs),
        )
        receipt_path = pipe.run_persisted_still_qa(
            image=png,
            policy_path=Path(args.qa_policy_json),
            requirements_path=Path(args.qa_requirements_json),
            phases=CaptionV4Phases(qa),
            job_dir=Path(args.qa_job_dir),
            expected_size=None,
            audit_caption=str(getattr(args, "qa_audit_caption", "") or ""),
            local=True,
        )
        if receipt_path.name != "accepted.json":
            print(f"I2V blocked: persisted still QA wrote {receipt_path}")
            return 4, None
        policy = json.loads(Path(args.qa_policy_json).read_text(encoding="utf-8"))
        args.qa_policy_id = str(policy.get("policy_id") or getattr(args, "qa_policy_id", None))
    elif getattr(args, "qa_job_dir", None) and getattr(args, "qa_generation_graph", None) \
            and getattr(args, "qa_policy_json", None) and getattr(args, "qa_requirements_json", None):
        pipe = _pipeline(local_agent)
        ph_spec = importlib.util.spec_from_file_location(
            "gvd_qa_phases_i2v", local_agent / "gvd_qa" / "phases.py")
        ph = importlib.util.module_from_spec(ph_spec)
        assert ph_spec.loader is not None
        ph_spec.loader.exec_module(ph)
        graph = json.loads(Path(args.qa_generation_graph).read_text(encoding="utf-8"))
        graph = gvd.redirect_generation_save(
            graph, str(getattr(args, "qa_image_node", "8")), str(getattr(args, "qa_save_node", "9")))
        object_info = None
        if getattr(args, "qa_object_info", None):
            object_info = json.loads(Path(args.qa_object_info).read_text(encoding="utf-8"))
        receipt_path = pipe.run_still_qa(
            generation_graph=graph,
            seed_bindings=((str(getattr(args, "qa_seed_node", "3")),
                            str(getattr(args, "qa_seed_input", "seed"))),),
            generation_save_node=str(getattr(args, "qa_save_node", "9")),
            base_seed=int(getattr(args, "qa_seed", 1)),
            expected_size=(int(getattr(args, "qa_width", 1024)), int(getattr(args, "qa_height", 1024))),
            policy_path=Path(args.qa_policy_json),
            requirements_path=Path(args.qa_requirements_json),
            phases=ph.LeasePhaseController(skip_live_free=True),
            job_dir=Path(args.qa_job_dir),
            object_info=object_info,
            resume=bool(getattr(args, "qa_resume", False)),
            local=bool(getattr(args, "qa_local", False)),
        )
        policy = json.loads(Path(args.qa_policy_json).read_text(encoding="utf-8"))
        args.qa_policy_id = str(policy.get("policy_id") or getattr(args, "qa_policy_id", None))
    if receipt_path is None:
        print("I2V blocked: still QA receipt required (pass --qa-receipt, --qa-candidate, or --qa-job-dir, or --allow-ungated-i2v)")
        return 4, None
    if not getattr(args, "qa_policy_id", None) or not getattr(args, "qa_requirements_json", None):
        print("I2V blocked: --qa-policy-id and --qa-requirements-json are required with a receipt")
        return 4, None
    try:
        accepted_still = gvd.accepted_i2v_image(
            Path(receipt_path),
            str(args.qa_policy_id),
            gvd.sha256(Path(args.qa_requirements_json).read_bytes()),
        )
    except Exception as exc:
        print(f"I2V blocked: {exc}")
        return 4, None
    print(f"  QA receipt accepted still={accepted_still}")
    return None, accepted_still
