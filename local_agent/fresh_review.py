#!/usr/bin/env python3
"""Fresh per-clip still -> full QA (CLIP + WD14 + Caption V4) -> review receipt.

Mirrors gvd_qa/smoke_generate_until_accepted.py but is parameterized over the
Backrooms clip list. Retries a fresh seed when Caption V4 is uncertain, and
surfaces unjudgeable stills for operator review instead of hard-erroring.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent          # local_agent/
ROOT = HERE.parent                               # project root
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from gvd_qa.caption_v4 import caption_v4_checklist
from gvd_qa.evidence import connect_evidence, insert_evidence
from gvd_qa.local_client import cpu_local_client
from gvd_qa.local_phases import HybridPhaseController, nvidia
from gvd_qa.pipeline import bind_fast, bind_qwen, bind_reward, load_policy

CLIPS = ROOT / "backrooms_24_clips.json"
GRAPH = HERE / "gvd_tool_router" / "fixtures" / "known_good_still.api.json"
OUT = HERE / "runtime" / "gvd_qa" / "fresh_review"


def load_clip(cid: str) -> dict:
    data = json.loads(CLIPS.read_text(encoding="utf-8"))
    for clip in data["clips"]:
        if clip["id"] == cid:
            return clip
    raise SystemExit(f"clip {cid} not found in {CLIPS}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", required=True)
    parser.add_argument("--side", choices=["start", "end"], required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--caption", default="", help="audit caption for reward binding")
    parser.add_argument("--base-seed", type=int, default=17)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("_gvd_qa_runner", ROOT / "gvd_qa.py")
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_qa_runner", runner)
    spec.loader.exec_module(runner)

    clip = load_clip(args.clip)
    prompt = str(clip[args.side])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_job_dir = OUT / "jobs" / f"{args.clip}_{args.side}_{stamp}"
    dest = OUT / f"review_{args.clip}_{args.side}_{stamp}.json"
    OUT.mkdir(parents=True, exist_ok=True)

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    graph["2"]["inputs"]["text"] = prompt
    graph["5"]["inputs"]["steps"] = 8
    policy = load_policy(Path(args.policy))
    requirements_json = Path(args.rubric).read_text(encoding="utf-8")
    caption = args.caption or prompt

    qa = cpu_local_client(
        audit_caption=caption,
        checklist_fn=lambda blob, reqs: caption_v4_checklist(blob, reqs),
    )
    phases = HybridPhaseController(qa)
    db = connect_evidence(OUT / "qa_evidence.sqlite")

    def _latest_candidate() -> str | None:
        cands = sorted(base_job_dir.glob("**/candidate.png"))
        return str(cands[-1]) if cands else None

    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "clip": args.clip,
        "side": args.side,
        "job_dir": str(base_job_dir),
        "prompt": prompt,
        "vram_before": nvidia(),
    }
    uncertain_attempts: list[dict] = []
    accepted = False
    for retry in range(args.retries):
        seed = args.base_seed + retry
        job_dir = base_job_dir / f"r{retry}"

        def record(**kwargs):
            insert_evidence(db, job_id=job_dir.name, verdict=kwargs["verdict"],
                            rubric_sha256=kwargs["rubric_sha256"])

        try:
            receipt = runner.generate_until_accepted(
                generation_graph=graph,
                seed_bindings=(("5", "seed"),),
                generation_save_node="7",
                base_seed=seed,
                expected_size=(512, 512),
                policy=policy,
                requirements_json=requirements_json,
                make_fast_graph=lambda n, a, d: bind_fast(n, a, d, policy, None, local=True),
                make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, policy, requirements_json, local=True),
                make_reward_graph=lambda n, a, d: bind_reward(n, a, d, policy, caption, local=True),
                phases=phases,
                job_dir=job_dir,
                record_evidence=record,
            )
            verdict = json.loads(receipt.read_text(encoding="utf-8"))
            report.update(
                status="ok",
                receipt=str(receipt),
                accepted=verdict.get("accepted"),
                scores=verdict.get("scores"),
                qwen_checks=verdict.get("qwen_checks"),
                reasons=verdict.get("reasons"),
                seed=seed,
            )
            accepted = True
            break
        except runner.Rejected as exc:
            report["status"] = "rejected"
            report["error"] = str(exc)
            report["seed"] = seed
            blocked = job_dir / "blocked.json"
            if blocked.is_file():
                report["blocked_payload"] = json.loads(blocked.read_text(encoding="utf-8"))
            break
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            try:
                phases.idle()
            except Exception:
                pass
            if "Uncertain visual evidence" in msg:
                uncertain_attempts.append({"seed": seed, "error": msg})
                continue
            report["status"] = "error"
            report["error"] = msg
            dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(json.dumps(report, indent=2, default=str))
            return 1
    if not accepted and report.get("status") != "rejected":
        report["status"] = "hold_review"
        report["uncertain_attempts"] = uncertain_attempts
        report["candidate_path"] = _latest_candidate()
        report["note"] = "Caption V4 could not judge the still (uncertain/blurry); operator review required."
    report["vlm_vram"] = phases.peak
    report["vram_after"] = nvidia()
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {k: report.get(k) for k in ("status", "accepted", "reasons", "scores", "seed",
                                    "qwen_checks", "candidate_path", "receipt", "job_dir", "vram_after")},
        indent=2, default=str))
    return 0 if report.get("status") in {"ok", "rejected", "hold_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
