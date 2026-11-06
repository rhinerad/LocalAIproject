#!/usr/bin/env python3
"""Operator-approved evaluation cases for the local-agent harness.

Intake, deterministic scoring, and captured-run persistence are model-free.
A CPU LLM-as-judge pre-score lives in ``judge_eval.py`` and is never mixed
into ``passed`` or ``operator.quality_score``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_io import atomic_write_json

HERE = Path(__file__).resolve().parent
ROOT = HERE / "eval_cases"
PENDING = ROOT / "pending"
APPROVED = ROOT / "approved"
RESULTS = ROOT / "results"

KINDS = {"tool_choice", "grounded_answer", "recovery", "planning"}
RESULT_SCHEMA = "operator-eval-result-v1"
ANSWER_CHAR_CAP = 16_000
_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]|[\\/]Users[\\/]|[\\/]home[\\/])", re.I)
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")


class EvalCaseError(ValueError):
    """A case is not safe or structurally valid for the review queue."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dirs(root: Path = ROOT) -> tuple[Path, Path, Path]:
    pending, approved, results = root / "pending", root / "approved", root / "results"
    judge, reports = root / "judge", root / "reports"
    for directory in (pending, approved, results, judge, reports):
        directory.mkdir(parents=True, exist_ok=True)
    return pending, approved, results


def _unsafe_text(value: str) -> bool:
    return bool(_PATH.search(value) or _EMAIL.search(value))


def _quality_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in range(6):
        raise EvalCaseError("operator.quality_score must be an integer 0-5")
    return value


def validate_case(case: dict[str, Any], *, tool_names: set[str] | None = None) -> dict[str, Any]:
    """Validate an explicit, anonymized evaluation case without writing it."""
    if not isinstance(case, dict):
        raise EvalCaseError("evaluation case must be a JSON object")
    title = str(case.get("title", "")).strip()
    prompt = str(case.get("prompt", "")).strip()
    kind = str(case.get("kind", "")).strip()
    if not title or len(title) > 120:
        raise EvalCaseError("title is required and must be at most 120 characters")
    if not prompt or len(prompt) > 4000:
        raise EvalCaseError("prompt is required and must be at most 4000 characters")
    if kind not in KINDS:
        raise EvalCaseError(f"kind must be one of {sorted(KINDS)}")
    if _unsafe_text(title) or _unsafe_text(prompt):
        raise EvalCaseError("case text must be anonymized: remove absolute paths and email addresses")

    acceptance = case.get("acceptance", {})
    if not isinstance(acceptance, dict):
        raise EvalCaseError("acceptance must be an object")
    for key in ("required_tools", "forbidden_tools", "must_contain"):
        value = acceptance.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise EvalCaseError(f"acceptance.{key} must be a list of non-empty strings")
    if tool_names is not None:
        invalid = set(acceptance.get("required_tools", [])) | set(acceptance.get("forbidden_tools", []))
        invalid -= tool_names
        if invalid:
            raise EvalCaseError(f"acceptance names unknown tools: {sorted(invalid)}")
    if set(acceptance.get("required_tools", [])) & set(acceptance.get("forbidden_tools", [])):
        raise EvalCaseError("a tool cannot be both required and forbidden")

    normalized = {
        "title": title,
        "prompt": prompt,
        "kind": kind,
        "acceptance": {
            "required_tools": list(dict.fromkeys(acceptance.get("required_tools", []))),
            "forbidden_tools": list(dict.fromkeys(acceptance.get("forbidden_tools", []))),
            "must_contain": list(dict.fromkeys(acceptance.get("must_contain", []))),
        },
        "operator_notes": str(case.get("operator_notes", "")).strip(),
    }
    if _unsafe_text(normalized["operator_notes"]):
        raise EvalCaseError("operator_notes must be anonymized: remove paths and email addresses")
    return normalized


def stage(case: dict[str, Any], *, root: Path = ROOT, tool_names: set[str] | None = None) -> dict[str, Any]:
    """Place one explicit operator-provided case in pending review."""
    normalized = validate_case(case, tool_names=tool_names)
    digest = hashlib.sha256(
        f"{normalized['title']}\n{normalized['prompt']}".encode("utf-8")
    ).hexdigest()[:12]
    record = {
        "id": f"eval_{normalized['kind']}_{digest}",
        "created_at": _now(),
        "status": "pending",
        **normalized,
    }
    pending, _, _ = _dirs(root)
    path = pending / f"{record['id']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def approve(case_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Move a reviewed pending case to the approved evaluation set."""
    pending, approved, _ = _dirs(root)
    source = pending / f"{case_id}.json"
    if not source.is_file():
        raise EvalCaseError("pending evaluation case not found")
    record = json.loads(source.read_text(encoding="utf-8"))
    record["status"] = "approved"
    record["approved_at"] = _now()
    target = approved / source.name
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    source.unlink()
    return record


def score(case: dict[str, Any], *, answer: str, tools_called: list[str]) -> dict[str, Any]:
    """Deterministically score a captured response and tool trace.

    This evaluates only operator-specified assertions. It intentionally cannot
    decide truthfulness beyond explicit expected phrases; the operator remains
    the authority for nuanced correctness. This function does not write files
    and does not call a model.
    """
    acceptance = case["acceptance"]
    called = set(tools_called)
    required = set(acceptance["required_tools"])
    forbidden = set(acceptance["forbidden_tools"])
    missing_tools = sorted(required - called)
    forbidden_used = sorted(forbidden & called)
    missing_text = [phrase for phrase in acceptance["must_contain"]
                    if phrase.casefold() not in answer.casefold()]
    passed = not (missing_tools or forbidden_used or missing_text)
    return {
        "case_id": case["id"], "scored_at": _now(), "passed": passed,
        "tools_called": list(tools_called), "missing_required_tools": missing_tools,
        "forbidden_tools_called": forbidden_used, "missing_required_text": missing_text,
        "note": "Deterministic acceptance only; operator reviews factual quality.",
    }


def load_approved(case_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    _, approved, _ = _dirs(root)
    path = approved / f"{case_id}.json"
    if not path.is_file():
        raise EvalCaseError("approved evaluation case not found")
    return json.loads(path.read_text(encoding="utf-8"))


def load_result(run_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    _, _, results = _dirs(root)
    path = results / f"{run_id}.json"
    if not path.is_file():
        raise EvalCaseError("evaluation result not found")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != RESULT_SCHEMA:
        raise EvalCaseError("unexpected evaluation result schema")
    return record


def authoritative_score(result: dict[str, Any]) -> int:
    """Return the operator's 0-5 quality score. Never reads a judge verdict."""
    if not isinstance(result, dict):
        raise EvalCaseError("result must be an object")
    if result.get("schema") in {
            "operator-eval-judge-verdict-v1",
            "farm-judge-semantic-verdict-v1"}:
        raise TypeError("authoritative_score does not accept a judge verdict")
    operator = result.get("operator")
    if not isinstance(operator, dict):
        raise EvalCaseError("result has no operator quality_score")
    return _quality_int(operator.get("quality_score"))


def _prepare_answer(answer: str) -> str:
    text = str(answer or "")
    if _unsafe_text(text):
        raise EvalCaseError("answer must be anonymized: remove absolute paths and email addresses")
    if len(text) > ANSWER_CHAR_CAP:
        import artifacts
        return artifacts.prune_large_text("eval_answer", text, limit=ANSWER_CHAR_CAP)
    return text


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nonce = hashlib.sha256(f"{stamp}:{time.time_ns()}".encode("utf-8")).hexdigest()[:4]
    return f"run_{stamp}_{nonce}"


def capture_run(case: dict[str, Any], *, answer: str, tools_called: list[str],
                quality_score: int | None = None, notes: str = "",
                root: Path = ROOT, source: str = "captured") -> dict[str, Any]:
    """Persist one captured (not live) run under ``results/{run_id}.json``.

    ``score()`` stays model-free and in-memory. This writes the operator
    record. It never stores a judge field.
    """
    if source != "captured":
        raise EvalCaseError("v1 only records captured answers; live replay is not built")
    if _unsafe_text(str(notes or "")):
        raise EvalCaseError("operator notes must be anonymized: remove paths and email addresses")
    prepared = _prepare_answer(answer)
    det = score(case, answer=prepared, tools_called=tools_called)
    run_id = _new_run_id()
    operator: dict[str, Any] = {
        "notes": str(notes or "").strip(),
        "scored_at": _now(),
    }
    if quality_score is not None:
        operator["quality_score"] = _quality_int(quality_score)
    record = {
        "schema": RESULT_SCHEMA,
        "run_id": run_id,
        "case_id": case["id"],
        "source": "captured",
        "captured_at": _now(),
        "answer": prepared,
        "tools_called": list(tools_called),
        "deterministic": {
            "passed": det["passed"],
            "missing_required_tools": det["missing_required_tools"],
            "forbidden_tools_called": det["forbidden_tools_called"],
            "missing_required_text": det["missing_required_text"],
            "note": det["note"],
        },
        "operator": operator,
    }
    _, _, results = _dirs(root)
    atomic_write_json(results / f"{run_id}.json", record)
    _recompute_after_pair(root, run_id)
    return record


def _recompute_after_pair(root: Path, run_id: str) -> None:
    try:
        import judge_eval
    except ImportError:
        return
    judge_eval.recompute_if_paired(root, run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and score anonymized local-agent evaluation cases.")
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    stage_p = sub.add_parser("stage", help="stage one operator-written case JSON file")
    stage_p.add_argument("file", type=Path)
    approve_p = sub.add_parser("approve", help="approve one pending case")
    approve_p.add_argument("case_id")
    score_p = sub.add_parser("score", help="score one approved case from a captured response")
    score_p.add_argument("case_id")
    score_p.add_argument("answer_file", type=Path)
    score_p.add_argument("--tool", action="append", default=[])
    score_p.add_argument("--quality", type=int, default=None,
                         help="operator quality score 0-5 (authoritative)")
    score_p.add_argument("--notes", default="")
    judge_p = sub.add_parser("judge", help="advisory CPU pre-score for one captured run")
    judge_p.add_argument("case_id")
    judge_p.add_argument("--run", required=True, dest="run_id")
    report_p = sub.add_parser("report", help="correlation of judge vs operator scores")
    report_p.add_argument("--all-runs", action="store_true")
    enable_p = sub.add_parser("judge-enable", help="enable or re-enable the advisory judge")
    enable_p.add_argument("--ack-report", type=Path, default=None)
    args = parser.parse_args()
    root = args.root
    try:
        if args.command == "stage":
            import tools
            record = stage(json.loads(args.file.read_text(encoding="utf-8")),
                           root=root, tool_names=set(tools.TOOLS))
        elif args.command == "approve":
            record = approve(args.case_id, root=root)
        elif args.command == "score":
            record = capture_run(
                load_approved(args.case_id, root=root),
                answer=args.answer_file.read_text(encoding="utf-8"),
                tools_called=args.tool,
                quality_score=args.quality,
                notes=args.notes,
                root=root,
            )
        elif args.command == "judge":
            import judge_eval
            record = judge_eval.judge_case(
                load_result(args.run_id, root=root),
                load_approved(args.case_id, root=root),
                root=root,
            )
            if record is None:
                print(json.dumps({"skipped": True, "run_id": args.run_id}, indent=2))
                return 0
        elif args.command == "report":
            import judge_eval
            record = judge_eval.write_report(root=root, all_runs=args.all_runs)
        else:
            import judge_eval
            record = judge_eval.judge_enable(root=root, ack_report=args.ack_report)
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, EvalCaseError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
