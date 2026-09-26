#!/usr/bin/env python3
"""SDXL still generate → CPU CLIP/WD14 → Caption V4 → receipt. One GPU owner."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.caption_v4 import caption_v4_checklist
from gvd_qa.evidence import connect_evidence, insert_evidence
from gvd_qa.local_client import cpu_local_client
from gvd_qa.local_phases import HybridPhaseController, nvidia
from gvd_qa.pipeline import bind_fast, bind_qwen, bind_reward, load_policy

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"
GRAPH = ROOT / "local_agent" / "gvd_tool_router" / "fixtures" / "known_good_still.api.json"
POLICY = HERE / "profiles" / "observed_5080_c017_end_reroll.json"
RUBRIC = HERE / "profiles" / "br24_c017_end_rubric.json"
PROMPT = (
    "empty yellow carpet hallway receding into the distance, yellow curtain "
    "at the far end, white walls, fluorescent lights, camcorder still, no people"
)
CAPTION = "yellow carpet hallway with a yellow curtain at the far end"


def main() -> int:
    import importlib.util
    spec = importlib.util.spec_from_file_location("_gvd_qa_runner", ROOT / "gvd_qa.py")
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_qa_runner", runner)
    spec.loader.exec_module(runner)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_dir = OUT / "jobs" / f"gen_c017_end_{stamp}"
    dest = OUT / "smoke_generate_until_accepted.json"
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "job_dir": str(job_dir),
        "vram_before": nvidia(),
        "prompt": PROMPT,
        "note": "SDXL 512x512 8-step generate then local QA. CLIP min 0. Not production calibration.",
    }
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    graph["2"]["inputs"]["text"] = PROMPT
    graph["5"]["inputs"]["steps"] = 8
    policy = load_policy(POLICY)
    requirements_json = RUBRIC.read_text(encoding="utf-8")
    qa = cpu_local_client(
        audit_caption=CAPTION,
        checklist_fn=lambda blob, reqs: caption_v4_checklist(blob, reqs),
    )
    phases = HybridPhaseController(qa)
    db = connect_evidence(OUT / "qa_evidence.sqlite")

    def record(**kwargs):
        insert_evidence(db, job_id=job_dir.name, verdict=kwargs["verdict"],
                        rubric_sha256=kwargs["rubric_sha256"])

    try:
        receipt = runner.generate_until_accepted(
            generation_graph=graph,
            seed_bindings=(("5", "seed"),),
            generation_save_node="7",
            base_seed=17,
            expected_size=(512, 512),
            policy=policy,
            requirements_json=requirements_json,
            make_fast_graph=lambda n, a, d: bind_fast(n, a, d, policy, None, local=True),
            make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, policy, requirements_json, local=True),
            make_reward_graph=lambda n, a, d: bind_reward(n, a, d, policy, CAPTION, local=True),
            phases=phases,
            job_dir=job_dir,
            record_evidence=record,
        )
        verdict = json.loads(receipt.read_text(encoding="utf-8"))
        report["receipt"] = str(receipt)
        report["accepted"] = verdict.get("accepted")
        report["scores"] = verdict.get("scores")
        report["qwen_checks"] = verdict.get("qwen_checks")
        report["reasons"] = verdict.get("reasons")
        report["status"] = "ok"
    except runner.Rejected as exc:
        blocked = job_dir / "blocked.json"
        report["status"] = "rejected"
        report["error"] = str(exc)
        report["blocked"] = str(blocked) if blocked.is_file() else None
        if blocked.is_file():
            report["blocked_payload"] = json.loads(blocked.read_text(encoding="utf-8"))
    except Exception as exc:
        try:
            phases.idle()
        except Exception:
            pass
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2, default=str))
        return 1
    report["vlm_vram"] = phases.peak
    report["vram_after"] = nvidia()
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in (
        "status", "accepted", "reasons", "scores", "qwen_checks", "receipt",
        "vram_before", "vram_after")}, indent=2, default=str))
    return 0 if report.get("status") in {"ok", "rejected"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
