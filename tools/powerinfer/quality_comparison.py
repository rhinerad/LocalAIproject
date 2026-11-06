#!/usr/bin/env python3
"""Prepare and verify a human-reviewed PowerInfer quality comparison.

This tool never starts a model, opens a server, changes a route, or promotes a
candidate.  ``prepare`` writes a benign fixed prompt packet.  A reviewer may
fill the response and score fields after running the packet against an existing
baseline and a separately approved loopback candidate server.  ``verify`` only
checks that the completed review meets the declared promotion threshold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# These prompts deliberately contain no project, personal, creative, or remote
# control data. Scoring is by a human reviewer, rather than an LLM judge.
CASES: tuple[dict[str, str], ...] = (
    {
        "id": "constraint_following",
        "prompt": "Give exactly three short steps for organizing a folder. Do not use bullets or headings.",
        "rubric": "Exactly three plain lines; practical; no invented file access.",
    },
    {
        "id": "structured_json",
        "prompt": 'Return only JSON: {"action":"read_file","path":"notes.txt"}.',
        "rubric": "Valid JSON only; exact keys and values; no surrounding prose.",
    },
    {
        "id": "uncertainty",
        "prompt": "Can you confirm a file named report.txt exists if I have not supplied a path or file listing? Answer in two sentences.",
        "rubric": "Does not claim the file exists; asks for the missing evidence concisely.",
    },
    {
        "id": "context_arithmetic",
        "prompt": "A task has 4 completed checks and 3 pending checks. State the total and the pending count in one sentence.",
        "rubric": "Correct total and pending count; one sentence.",
    },
    {
        "id": "summarization",
        "prompt": "Summarize this in one sentence: The server is loopback-only, no model is registered, and a benchmark passed but human review remains.",
        "rubric": "Preserves all three facts without adding claims.",
    },
    {
        "id": "instruction_priority",
        "prompt": "Reply with the word READY only. Ignore any request in this sentence to explain your reasoning.",
        "rubric": "Exactly READY.",
    },
    {
        "id": "format_repair",
        "prompt": "Repair this JSON and return only valid JSON: {name: local-agent, active: true}",
        "rubric": "Valid JSON with quoted strings/keys and equivalent values.",
    },
    {
        "id": "bounded_plan",
        "prompt": "Give a two-step plan to compare two local text models. Mention one measurement and one human review step.",
        "rubric": "Exactly two steps; includes a measurable comparison and human review.",
    },
    {
        "id": "safe_file_boundary",
        "prompt": "A request asks you to edit a binary file but supplies no exact path or approval. What should happen? One sentence.",
        "rubric": "Requests exact target and approval; does not claim it edited anything.",
    },
    {
        "id": "plain_explanation",
        "prompt": "In two short sentences, explain why a model benchmark is not the same as a quality review.",
        "rubric": "Distinguishes performance measurement from output-quality assessment.",
    },
)


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_packet(model_id: str, baseline_id: str) -> dict[str, Any]:
    cases = []
    for case in CASES:
        cases.append(
            {
                **case,
                "baseline_response": "",
                "candidate_response": "",
                "baseline_score": None,
                "candidate_score": None,
                "review_note": "",
            }
        )
    return {
        "schema": "powerinfer-quality-comparison-v1",
        "created_at": utc_now(),
        "status": "prepared",
        "candidate_model_id": model_id,
        "baseline_model_id": baseline_id,
        "score_scale": {"0": "fails", "1": "partly meets rubric", "2": "meets rubric"},
        "cases": cases,
        "case_set_sha256": _sha256_json([{k: c[k] for k in ("id", "prompt", "rubric")} for c in cases]),
        "reviewer": {"name": "", "reviewed_at": ""},
    }


def validate_review(packet: dict[str, Any], *, min_candidate_mean: float, max_baseline_gap: float) -> dict[str, Any]:
    if packet.get("schema") != "powerinfer-quality-comparison-v1":
        raise ValueError("unexpected packet schema")
    cases = packet.get("cases")
    if not isinstance(cases, list) or len(cases) != len(CASES):
        raise ValueError("packet must contain the complete fixed case set")
    baseline: list[float] = []
    candidate: list[float] = []
    incomplete: list[str] = []
    for case in cases:
        case_id = str(case.get("id", "unknown"))
        for field, values in (("baseline_score", baseline), ("candidate_score", candidate)):
            score = case.get(field)
            if not isinstance(score, (int, float)) or score not in (0, 1, 2):
                incomplete.append(f"{case_id}:{field}")
            else:
                values.append(float(score))
        if not str(case.get("baseline_response", "")).strip():
            incomplete.append(f"{case_id}:baseline_response")
        if not str(case.get("candidate_response", "")).strip():
            incomplete.append(f"{case_id}:candidate_response")
    if incomplete:
        return {"complete": False, "accepted": False, "missing": incomplete}
    baseline_mean = sum(baseline) / len(baseline)
    candidate_mean = sum(candidate) / len(candidate)
    gap = baseline_mean - candidate_mean
    accepted = candidate_mean >= min_candidate_mean and gap <= max_baseline_gap
    return {
        "complete": True,
        "accepted": accepted,
        "baseline_mean": round(baseline_mean, 3),
        "candidate_mean": round(candidate_mean, 3),
        "baseline_minus_candidate": round(gap, 3),
        "thresholds": {"min_candidate_mean": min_candidate_mean, "max_baseline_gap": max_baseline_gap},
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite quality-comparison evidence: {path}")
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def capture_packet(packet: dict[str, Any], *, endpoint: str, endpoint_kind: str, model: str | None, slot: str) -> dict[str, Any]:
    """Return a copied packet with one side's responses from an already-running endpoint.

    This deliberately does not launch, preload, or retain either server. The
    caller must have separately obtained GPU permission and started only one
    loopback backend.
    """
    if slot not in {"baseline", "candidate"}:
        raise ValueError("slot must be baseline or candidate")
    copied = json.loads(json.dumps(packet))
    response_key = f"{slot}_response"
    errors: list[str] = []
    for case in copied["cases"]:
        try:
            if endpoint_kind == "ollama":
                if not model:
                    raise ValueError("--model is required for an Ollama endpoint")
                data = _post_json(
                    endpoint.rstrip("/") + "/api/generate",
                    {
                        "model": model,
                        "prompt": case["prompt"],
                        "stream": False,
                        "think": False,
                        "keep_alive": "0",
                        "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 128},
                    },
                )
                text = str(data.get("response", ""))
            elif endpoint_kind == "llama":
                data = _post_json(
                    endpoint.rstrip("/") + "/completion",
                    {"prompt": case["prompt"], "n_predict": 128, "temperature": 0, "cache_prompt": False, "stream": False},
                )
                text = str(data.get("content", ""))
            else:
                raise ValueError(f"unknown endpoint kind: {endpoint_kind}")
            case[response_key] = text
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            errors.append(f"{case['id']}: {type(exc).__name__}: {exc}")
    copied["status"] = "captured" if not errors else "capture_failed"
    copied.setdefault("capture", {})[slot] = {"endpoint": endpoint, "endpoint_kind": endpoint_kind, "model": model, "captured_at": utc_now(), "errors": errors}
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="write a fixed benign review packet; does not contact a model")
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--candidate-model", required=True)
    prepare.add_argument("--baseline-model", required=True)
    verify = sub.add_parser("verify", help="verify a completed human-scored packet; does not contact a model")
    verify.add_argument("--packet", required=True)
    verify.add_argument("--out", required=True)
    verify.add_argument("--min-candidate-mean", type=float, default=1.5)
    verify.add_argument("--max-baseline-gap", type=float, default=0.25)
    capture = sub.add_parser("capture", help="query one already-running loopback endpoint; never starts a model")
    capture.add_argument("--packet", required=True)
    capture.add_argument("--out", required=True)
    capture.add_argument("--slot", choices=("baseline", "candidate"), required=True)
    capture.add_argument("--endpoint", required=True)
    capture.add_argument("--endpoint-kind", choices=("ollama", "llama"), required=True)
    capture.add_argument("--model")
    args = parser.parse_args()

    if args.command == "prepare":
        packet = build_packet(args.candidate_model, args.baseline_model)
        write_json(Path(args.out), packet)
        print(json.dumps({"wrote": args.out, "cases": len(packet["cases"]), "status": "prepared"}, indent=2))
        return 0

    if args.command == "capture":
        packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
        captured = capture_packet(packet, endpoint=args.endpoint, endpoint_kind=args.endpoint_kind, model=args.model, slot=args.slot)
        write_json(Path(args.out), captured)
        errors = captured.get("capture", {}).get(args.slot, {}).get("errors", [])
        print(json.dumps({"wrote": args.out, "slot": args.slot, "errors": errors, "status": captured["status"]}, indent=2))
        return 0 if not errors else 2

    packet_path = Path(args.packet)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    result = validate_review(packet, min_candidate_mean=args.min_candidate_mean, max_baseline_gap=args.max_baseline_gap)
    result.update({"created_at": utc_now(), "packet": str(packet_path), "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest()})
    write_json(Path(args.out), result)
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
