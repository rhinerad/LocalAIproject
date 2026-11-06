#!/usr/bin/env python3
"""Opt-in, read-only maintenance loops for the local agent.

This controller deliberately has less authority than the chat agent.  It can
create durable operator goals, run one command from a fixed regression registry,
and — only after a failure plus an explicit operator request — produce a
non-mutating unified-diff proposal through the existing protected tool boundary.
It cannot load a model, access the network, edit project files, or operate
ComfyUI. A failed check is an operator-review event, never a repair attempt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE / "runtime" / "loop_engineering"
GOALS = ROOT / "goals"
RUNS = ROOT / "runs"
CONFIG = ROOT / "loop_config.json"
TRIAGE = ROOT / "triage.jsonl"
REVIEW = ROOT / "review_queue.json"
STATUS = ROOT / "LOOP_STATUS.md"

CHECKS: dict[str, tuple[str, ...]] = {
    "general_scope": ("test_general_assistant.py",),
    "native_tool_calls": ("test_native_tool_calling.py",),
    "context_resilience": ("test_context_resilience.py",),
    "agentic_eval": ("agentic_eval.py",),
    "operator_eval": ("test_operator_eval.py",),
    "h3_prompt_validation": ("validate_h3_prompt.py", "--dir", "outputs/equal_shares/prompts_native_r2v"),
}
_ID = re.compile(r"loop_[a-z0-9_]{8,80}$")
_DRIVE_PATH = re.compile(r"(?i)(?:[a-z]:\\[^\s\"']+|/(?:Users|home)/[^\s\"']+)")
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_TOKEN = re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[=:]\s*[^\s,;]+")


class LoopError(ValueError):
    """The requested loop operation is outside its deliberately narrow scope."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dirs(root: Path = ROOT) -> None:
    for path in (root, root / "goals", root / "runs"):
        path.mkdir(parents=True, exist_ok=True)


def _redact(value: object, limit: int = 1600) -> str:
    text = str(value or "")
    text = _DRIVE_PATH.sub("<LOCAL_PATH>", text)
    text = _EMAIL.sub("<EMAIL>", text)
    text = _TOKEN.sub("<REDACTED_CREDENTIAL>", text)
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _atomic_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _goal_path(goal_id: str, root: Path = ROOT) -> Path:
    if not _ID.fullmatch(str(goal_id or "")):
        raise LoopError("invalid loop goal id")
    return root / "goals" / f"{goal_id}.json"


def config(root: Path = ROOT) -> dict[str, Any]:
    _dirs(root)
    path = root / "loop_config.json"
    default = {"version": 1, "loop_enabled": False, "updated_at": _now()}
    if not path.is_file():
        _atomic_json(path, default)
        return default
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return {**default, **(loaded if isinstance(loaded, dict) else {})}


def set_enabled(enabled: bool, root: Path = ROOT) -> dict[str, Any]:
    record = config(root)
    record["loop_enabled"] = bool(enabled)
    record["updated_at"] = _now()
    _atomic_json(root / "loop_config.json", record)
    write_status(root)
    return record


def _read_goal(goal_id: str, root: Path = ROOT) -> dict[str, Any]:
    path = _goal_path(goal_id, root)
    if not path.is_file():
        raise LoopError("loop goal not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopError("loop goal cannot be read") from exc
    if not isinstance(data, dict):
        raise LoopError("loop goal is malformed")
    return data


def _save_goal(goal: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    goal["updated_at"] = _now()
    _atomic_json(_goal_path(goal["id"], root), goal)
    write_status(root)
    return goal


def create_goal(title: str, objective: str, checks: list[str], *,
                max_runs: int = 6, max_seconds: int = 120, root: Path = ROOT) -> dict[str, Any]:
    """Create one explicitly requested verification goal.

    The only stop condition is fixed: every named registry check passes.  This
    prevents text goals from becoming shell instructions or autonomous work.
    """
    clean_title, clean_objective = _redact(title, 140), _redact(objective, 600)
    if not clean_title or not clean_objective:
        raise LoopError("title and objective are required")
    unique_checks = list(dict.fromkeys(str(item) for item in checks))
    if not unique_checks or any(item not in CHECKS for item in unique_checks):
        raise LoopError(f"checks must be selected from: {', '.join(CHECKS)}")
    if not 1 <= int(max_runs) <= 20 or not 15 <= int(max_seconds) <= 600:
        raise LoopError("max_runs must be 1..20 and max_seconds must be 15..600")
    digest = hashlib.sha256(f"{clean_title}\n{clean_objective}\n{','.join(unique_checks)}".encode()).hexdigest()[:12]
    goal_id = f"loop_{int(time.time())}_{digest}"
    goal = {
        "version": 1, "id": goal_id, "operator_created": True,
        "created_at": _now(), "updated_at": _now(), "title": clean_title,
        "objective": clean_objective, "stop_condition": "all_checks_pass",
        "checks": [{"name": name, "status": "pending"} for name in unique_checks],
        "budget": {"max_runs": int(max_runs), "max_seconds": int(max_seconds)},
        "run_count": 0, "failure_count": 0, "status": "active",
    }
    _dirs(root)
    _atomic_json(_goal_path(goal_id, root), goal)
    _append_triage({"at": _now(), "goal_id": goal_id, "event": "created",
                    "reason": "operator-created bounded verification goal"}, root)
    write_status(root)
    return goal


def _append_triage(record: dict[str, Any], root: Path = ROOT) -> None:
    _dirs(root)
    safe = {str(k): _redact(v, 600) for k, v in record.items()}
    with (root / "triage.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe, ensure_ascii=False) + "\n")


def _review(goal: dict[str, Any], reason: str, *, evidence: str = "", root: Path = ROOT) -> None:
    _dirs(root)
    path = root / "review_queue.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError, json.JSONDecodeError):
        items = []
    if not isinstance(items, list):
        items = []
    key = f"{goal['id']}:{reason}"
    if not any(isinstance(item, dict) and item.get("key") == key for item in items):
        items.append({"key": key, "goal_id": goal["id"], "title": _redact(goal["title"], 140),
                      "created_at": _now(), "reason": _redact(reason, 400),
                      "evidence": _redact(evidence, 1000), "status": "needs_operator"})
        _atomic_json(path, items[-100:])


def list_goals(root: Path = ROOT) -> list[dict[str, Any]]:
    _dirs(root)
    result = []
    for path in sorted((root / "goals").glob("loop_*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                result.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return result


def discover(root: Path = ROOT) -> dict[str, Any]:
    """Read-only triage inputs. Discovery never runs a test or edits project files."""
    _dirs(root)
    upgrades = HERE / "UPGRADE"
    pending = 0
    for path in upgrades.glob("*.md") if upgrades.is_dir() else []:
        try:
            pending += path.read_text(encoding="utf-8", errors="replace").count("- [ ]")
        except OSError:
            continue
    changelog = HERE.parent / "CHANGELOG"
    newest = max(changelog.glob("*.md"), key=lambda item: item.stat().st_mtime, default=None) if changelog.is_dir() else None
    checkpoints = HERE / "runtime" / "agentic_tasks"
    stale = 0
    if checkpoints.is_dir():
        for path in checkpoints.glob("*.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                stale += int(isinstance(state, dict) and state.get("status") in {"active", "blocked", "awaiting_operator"})
            except (OSError, json.JSONDecodeError):
                continue
    result = {"known_checks": sorted(CHECKS), "pending_upgrade_items": pending,
              "active_or_blocked_chat_checkpoints": stale,
              "newest_changelog": newest.name if newest else None,
              "discovered_at": _now()}
    _append_triage({"at": _now(), "event": "discovery", "reason": json.dumps(result)}, root)
    return result


def _run_check(name: str, timeout: int) -> dict[str, Any]:
    args = [sys.executable, str(HERE / CHECKS[name][0]), *CHECKS[name][1:]]
    started = time.monotonic()
    try:
        process = subprocess.run(args, cwd=HERE.parent, shell=False, text=True,
                                 capture_output=True, timeout=timeout, check=False)
        output = _redact((process.stdout or "") + "\n" + (process.stderr or ""), 1600)
        return {"check": name, "passed": process.returncode == 0, "returncode": process.returncode,
                "duration_seconds": round(time.monotonic() - started, 3), "output": output}
    except subprocess.TimeoutExpired:
        return {"check": name, "passed": False, "returncode": None,
                "duration_seconds": round(time.monotonic() - started, 3), "output": "check timed out"}
    except OSError as exc:
        return {"check": name, "passed": False, "returncode": None,
                "duration_seconds": round(time.monotonic() - started, 3), "output": _redact(exc)}


def run_once(goal_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Run exactly one fixed, non-rendering verification check, then stop."""
    if not config(root).get("loop_enabled"):
        raise LoopError("loop controller is disabled; enable it explicitly before running a check")
    goal = _read_goal(goal_id, root)
    if goal.get("status") != "active":
        raise LoopError(f"goal is {goal.get('status')}; create or review a new goal instead")
    if int(goal.get("run_count", 0)) >= int(goal["budget"]["max_runs"]):
        goal["status"] = "needs_operator"
        _review(goal, "run budget reached", root=root)
        _save_goal(goal, root)
        raise LoopError("run budget reached; review is required")
    pending = next((item for item in goal.get("checks", []) if item.get("status") == "pending"), None)
    if pending is None:
        goal["status"] = "complete" if all(item.get("status") == "passed" for item in goal.get("checks", [])) else "needs_operator"
        _save_goal(goal, root)
        return {"goal": goal, "result": None}
    result = _run_check(pending["name"], int(goal["budget"]["max_seconds"]))
    # The registry implementation already redacts process output.  Enforce the
    # boundary again here so a future adapter (or a test double) cannot leak a
    # local path or credential through the durable audit record.
    result["output"] = _redact(result.get("output"), 1600)
    pending["status"] = "passed" if result["passed"] else "failed"
    pending["last_result"] = {key: result[key] for key in ("passed", "returncode", "duration_seconds", "output")}
    goal["run_count"] = int(goal.get("run_count", 0)) + 1
    if result["passed"]:
        goal["status"] = "complete" if all(item.get("status") == "passed" for item in goal["checks"]) else "active"
    else:
        goal["failure_count"] = int(goal.get("failure_count", 0)) + 1
        goal["status"] = "needs_operator"
        _review(goal, f"verification check failed: {pending['name']}", evidence=result["output"], root=root)
    run_path = root / "runs" / f"{goal_id}.jsonl"
    with run_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": _now(), "goal_id": goal_id, **result}, ensure_ascii=False) + "\n")
    _append_triage({"at": _now(), "goal_id": goal_id, "event": "check",
                    "reason": f"{pending['name']}: {'passed' if result['passed'] else 'failed'}"}, root)
    _save_goal(goal, root)
    return {"goal": goal, "result": result}


def propose_repair(goal_id: str, path: str, content: str, target_check: str, *,
                   root: Path = ROOT) -> dict[str, Any]:
    """Create a review-only diff for one failed goal check.

    The operator supplies the exact replacement text. This function calls the
    existing non-writing ``propose_file_diff`` boundary, then queues that exact
    content in the ordinary one-shot sidebar gate. Applying any change remains
    an entirely separate chat/sidebar write workflow; this controller never
    calls ``write_file`` or writes project content itself.
    """
    if not config(root).get("loop_enabled"):
        raise LoopError("loop controller is disabled; enable it explicitly before requesting a proposal")
    goal = _read_goal(goal_id, root)
    failed = {item.get("name") for item in goal.get("checks", []) if item.get("status") == "failed"}
    if goal.get("status") != "needs_operator" or target_check not in failed:
        raise LoopError("a repair proposal requires an operator-reviewed failed check from this goal")
    if target_check not in CHECKS:
        raise LoopError("proposal target check is not in the fixed registry")
    import tools  # delayed: Phase 1 remains stdlib-only and tool-free
    try:
        diff = tools.propose_file_diff({"path": str(path), "content": str(content)})
    except Exception as exc:
        raise LoopError(f"proposal refused by the protected file boundary: {_redact(exc, 300)}") from exc
    if diff.startswith("ERROR:") or "protected project file" in diff:
        raise LoopError(f"proposal refused by the protected file boundary: {_redact(diff, 300)}")
    digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    import file_edit_gate
    resolved = Path(path).resolve()
    approval = file_edit_gate.request(resolved, str(content), metadata={
        "source": "loop_engineering", "goal_id": goal_id,
        "target_check": target_check, "kind": "approved repair proposal",
    }, consume=False)
    approval_key = str(approval.get("key") or file_edit_gate.key(resolved, str(content)))
    previous_repair = goal.get("repair") if isinstance(goal.get("repair"), dict) else {}
    goal["repair"] = {
        "status": "awaiting_exact_edit",
        "target_check": target_check,
        "path": str(resolved),
        "content_sha256": hashlib.sha256(str(content).encode("utf-8")).hexdigest(),
        "diff_sha256": digest,
        "approval_key": approval_key,
        "approval_request_id": (approval.get("request") or {}).get("id"),
        # Carry only failure fingerprints for this same check across revised
        # proposed contents.  Otherwise a loop could evade the two-identical-
        # failure stop merely by submitting another exact diff.
        "failure_fingerprints": list(previous_repair.get("failure_fingerprints", [])) if previous_repair.get("target_check") == target_check else [],
        "identical_failure_count": int(previous_repair.get("identical_failure_count", 0)) if previous_repair.get("target_check") == target_check else 0,
    }
    _save_goal(goal, root)
    _review(goal, f"operator-requested repair proposal for failed check: {target_check}",
            evidence=f"unified diff sha256={digest}; exact edit is pending in the existing sidebar gate", root=root)
    _append_triage({"at": _now(), "goal_id": goal_id, "event": "repair_proposal",
                    "reason": f"{target_check}; unified diff sha256={digest}"}, root)
    return {"goal_id": goal_id, "target_check": target_check, "diff_sha256": digest,
            "requires_existing_file_edit_approval": True,
            "file_edit_request": approval.get("request"), "approval_available": bool(approval.get("granted")),
            "diff": diff}


def _approved_exact_edit(repair: dict[str, Any]) -> bool:
    """Return true only after the existing gate recorded this exact approval."""
    import file_edit_gate
    for item in file_edit_gate.snapshot().get("history", []):
        if (isinstance(item, dict) and item.get("decision") == "approved"
                and item.get("key") == repair.get("approval_key")):
            return True
    return False


def verify_approved_repair(goal_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Rerun the named fixed check after an independently approved exact edit.

    This is deliberately not an apply operation.  The controller checks the
    sidebar's audit history and the on-disk content digest, then runs one fixed
    registry test.  Two identical post-repair failures halt future retries and
    queue an operator review.
    """
    if not config(root).get("loop_enabled"):
        raise LoopError("loop controller is disabled; enable it explicitly before verifying a repair")
    goal = _read_goal(goal_id, root)
    repair = goal.get("repair") if isinstance(goal.get("repair"), dict) else None
    if goal.get("status") != "needs_operator" or not repair or repair.get("status") != "awaiting_exact_edit":
        raise LoopError("there is no pending approved repair to verify")
    target_check = str(repair.get("target_check", ""))
    if target_check not in CHECKS or target_check not in {item.get("name") for item in goal.get("checks", []) if item.get("status") == "failed"}:
        raise LoopError("repair target no longer matches this failed fixed check")
    if not _approved_exact_edit(repair):
        raise LoopError("the exact edit has not been approved in the sidebar")
    try:
        current = Path(str(repair["path"])).read_text(encoding="utf-8")
    except (KeyError, OSError) as exc:
        raise LoopError("the approved repair file cannot be read") from exc
    if hashlib.sha256(current.encode("utf-8")).hexdigest() != repair.get("content_sha256"):
        raise LoopError("the approved content is not present; apply the exact sidebar-approved edit before verifying")
    for item in goal["checks"]:
        if item.get("name") == target_check:
            item["status"] = "pending"
            break
    repair["status"] = "verifying"
    goal["status"] = "active"
    _save_goal(goal, root)
    record = run_once(goal_id, root=root)
    result = record.get("result") or {}
    goal = record["goal"]
    repair = goal.get("repair", {})
    if result.get("passed"):
        repair["status"] = "passed"
    else:
        fingerprint = hashlib.sha256(json.dumps({
            "check": target_check, "returncode": result.get("returncode"), "output": result.get("output", ""),
        }, sort_keys=True).encode("utf-8")).hexdigest()
        previous = list(repair.get("failure_fingerprints", []))
        count = int(repair.get("identical_failure_count", 0)) + 1 if fingerprint in previous else 1
        repair["failure_fingerprints"] = (previous + [fingerprint])[-4:]
        repair["identical_failure_count"] = count
        if count >= 2:
            repair["status"] = "halted_identical_failure"
            _review(goal, "same verification failure repeated after two approved repairs",
                    evidence=f"check={target_check}; failure_fingerprint={fingerprint}", root=root)
        else:
            repair["status"] = "needs_new_proposal"
    _save_goal(goal, root)
    return {"goal": goal, "result": result, "repair": repair}


def snapshot(root: Path = ROOT) -> dict[str, Any]:
    items = list_goals(root)
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return {"enabled": bool(config(root).get("loop_enabled")), "goals": len(items),
            "by_status": counts, "safe_checks": sorted(CHECKS)}


def write_status(root: Path = ROOT) -> None:
    data = snapshot(root)
    lines = ["# Local Agent Loop Engineering Status", "", f"- Enabled: `{data['enabled']}`",
             f"- Durable goals: `{data['goals']}`", f"- Status counts: `{json.dumps(data['by_status'], sort_keys=True)}`",
             "- Authority: fixed read-only verification checks only; no tools, renders, downloads, models, or project edits.",
             "- Enablement is explicit and each run executes one check then stops."]
    (root / "LOOP_STATUS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Opt-in, read-only local-agent verification loops.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("discover")
    switch = sub.add_parser("set-enabled")
    switch.add_argument("value", choices=("true", "false"))
    create = sub.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--check", action="append", required=True, choices=sorted(CHECKS))
    create.add_argument("--max-runs", type=int, default=6)
    create.add_argument("--max-seconds", type=int, default=120)
    run = sub.add_parser("run-once")
    run.add_argument("goal_id")
    proposal = sub.add_parser("propose-repair", help="create a review-only diff for one failed check")
    proposal.add_argument("goal_id")
    proposal.add_argument("--path", required=True)
    proposal.add_argument("--content-file", type=Path, required=True)
    proposal.add_argument("--check", required=True, choices=sorted(CHECKS))
    verify = sub.add_parser("verify-approved-repair", help="rerun one fixed check after an exact sidebar-approved edit")
    verify.add_argument("goal_id")
    args = parser.parse_args()
    try:
        if args.command == "status": result = snapshot()
        elif args.command == "discover": result = discover()
        elif args.command == "set-enabled": result = set_enabled(args.value == "true")
        elif args.command == "create": result = create_goal(args.title, args.objective, args.check, max_runs=args.max_runs, max_seconds=args.max_seconds)
        elif args.command == "propose-repair": result = propose_repair(
            args.goal_id, args.path, args.content_file.read_text(encoding="utf-8"), args.check)
        elif args.command == "verify-approved-repair": result = verify_approved_repair(args.goal_id)
        else: result = run_once(args.goal_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except LoopError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
