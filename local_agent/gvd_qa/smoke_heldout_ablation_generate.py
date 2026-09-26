#!/usr/bin/env python3
"""Held-out generate: omit the CLIP-sensitive hallway phrase. Do not promote."""
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
from gvd_qa.evidence import connect_evidence, insert_evidence, insert_experiment
from gvd_qa.local_client import cpu_local_client
from gvd_qa.local_phases import HybridPhaseController, nvidia
from gvd_qa.pipeline import bind_fast, bind_qwen, bind_reward, load_policy
from gvd_qa.scorers import clip_text_score

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"
GRAPH = ROOT / "local_agent" / "gvd_tool_router" / "fixtures" / "known_good_still.api.json"
POLICY = HERE / "profiles" / "provisional_loop_labels_v1.json"
RUBRIC = HERE / "profiles" / "br24_c017_end_rubric.json"
PARENT = (
    "empty yellow carpet hallway receding into the distance, yellow curtain "
    "at the far end, white walls, fluorescent lights, camcorder still, no people"
)
PROMPT = "yellow curtain at the far end,white walls,fluorescent lights,camcorder still,no people"
CAPTION = "yellow carpet hallway with a yellow curtain at the far end"


def main() -> int:
    import hashlib
    import importlib.util
    spec = importlib.util.spec_from_file_location("_gvd_qa_runner", ROOT / "gvd_qa.py")
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_qa_runner", runner)
    spec.loader.exec_module(runner)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_dir = OUT / "jobs" / f"heldout_omit_hallway_{stamp}"
    dest = OUT / "smoke_heldout_ablation_generate.json"
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "parent_prompt": PARENT,
        "held_out_prompt": PROMPT,
        "omitted": "empty yellow carpet hallway receding into the distance",
        "job_dir": str(job_dir),
        "vram_before": nvidia(),
        "note": "Held-out generate of the CLIP-sensitive omission. Do not promote.",
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
        report["reasons"] = verdict.get("reasons")
        png = Path(verdict["image_path"]).read_bytes()
        report["clip_vs_heldout_prompt"] = clip_text_score(png, PROMPT)
        report["clip_vs_parent_prompt"] = clip_text_score(png, PARENT)
        outcome = "accepted" if verdict.get("accepted") else "rejected"
        report["status"] = "ok"
    except runner.Rejected as exc:
        outcome = "rejected"
        report["status"] = "rejected"
        report["error"] = str(exc)
        blocked = job_dir / "blocked.json"
        if blocked.is_file():
            report["blocked"] = json.loads(blocked.read_text(encoding="utf-8"))
        verdict = report.get("blocked") or {}
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
    insert_experiment(db, {
        "parent_prompt_sha256": hashlib.sha256(PARENT.encode()).hexdigest(),
        "variant_index": 1,
        "variant_hash": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "seed": 17,
        "scores": report.get("scores") or {},
        "held_out_outcome": outcome,
        "label": "omit_yellow_carpet_hallway",
    })
    report["held_out_outcome"] = outcome
    report["vram_after"] = nvidia()
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in (
        "status", "accepted", "scores", "held_out_outcome",
        "clip_vs_heldout_prompt", "clip_vs_parent_prompt")}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
