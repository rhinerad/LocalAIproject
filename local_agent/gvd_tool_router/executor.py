"""ComfyUI API adapter. A successful queue response is not a successful render."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .binder import BinderError, bind, is_ui_workflow, prompt_payload
from .paths import GvdLayout
from .schema import ExecutionResult, ToolImplementation, WorkflowStage, require_sha256
from .store import (
    add_attempt,
    find_open_attempt,
    record_prompt_id,
    set_attempt_status,
)

CLIENT_ID = "gvd-tool-router"
DEFAULT_TIMEOUT_S = 30.0


class ExecutorError(RuntimeError):
    pass


HttpFn = Callable[[str, dict[str, Any] | None, str, float], dict[str, Any]]


def default_http(url: str, payload: dict[str, Any] | None, method: str, timeout: float) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ExecutorError(f"HTTP {exc.code} {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ExecutorError(f"unreachable {url}: {exc}") from exc


def load_approved_graph(layout: GvdLayout, template_sha: str) -> dict[str, Any]:
    path = layout.workflow_dir(require_sha256(template_sha)) / "workflow.api.json"
    if not path.is_file():
        raise ExecutorError(f"approved workflow missing: {path}")
    graph = json.loads(path.read_text(encoding="utf-8"))
    if is_ui_workflow(graph):
        raise ExecutorError("UI workflow staged for export; refusing API submit")
    return graph


def submit_stage(
    *,
    layout: GvdLayout,
    conn,
    impl: ToolImplementation,
    stage: WorkflowStage,
    shot_id: str,
    registry_digest: str,
    profile_id: str,
    values: dict[str, Any],
    comfy_url: str,
    lease_generation: int | None,
    http: HttpFn | None = None,
    object_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if http is None:
        http = default_http
    existing = find_open_attempt(conn, shot_id, impl.implementation_id)
    if existing and existing["prompt_id"] and existing["status"] in {"SUBMITTING", "QUEUED", "RUNNING"}:
        return reconcile(http, comfy_url, existing["prompt_id"], existing["attempt_id"], conn)

    attempt_id = add_attempt(
        conn,
        shot_id=shot_id,
        implementation_id=impl.implementation_id,
        registry_digest=registry_digest,
        profile_id=profile_id,
        lease_generation=lease_generation,
        extra={"stage_id": stage.stage_id},
    )
    graph = load_approved_graph(layout, stage.template.sha256)
    try:
        bound = bind(stage.template, graph, values, object_info=object_info)
    except BinderError as exc:
        set_attempt_status(conn, attempt_id, "FAILED_BUDGET")
        raise ExecutorError(str(exc)) from exc

    set_attempt_status(conn, attempt_id, "SUBMITTING")
    payload = prompt_payload(bound, client_id=CLIENT_ID, attempt_id=attempt_id)
    try:
        queued = http(f"{comfy_url.rstrip('/')}/prompt", payload, "POST", DEFAULT_TIMEOUT_S)
    except ExecutorError:
        # Ambiguous timeout: reconcile by attempt metadata before resubmitting.
        set_attempt_status(conn, attempt_id, "RETRY_PENDING")
        raise
    except Exception as exc:
        set_attempt_status(conn, attempt_id, "FAILED")
        raise ExecutorError(f"submission failed before queueing: {exc}") from exc
    prompt_id = str(queued.get("prompt_id") or queued.get("node_errors") and "")
    if not queued.get("prompt_id"):
        set_attempt_status(conn, attempt_id, "FAILED_BUDGET")
        raise ExecutorError(f"queue rejected: {queued}")
    record_prompt_id(conn, attempt_id, str(queued["prompt_id"]))
    job_dir = layout.job_dir("default", shot_id, attempt_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "request.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (job_dir / "queue.json").write_text(json.dumps(queued, indent=2), encoding="utf-8")
    return {"attempt_id": attempt_id, "prompt_id": queued["prompt_id"], "status": "QUEUED"}


def _queue_membership(queue: Any, prompt_id: str) -> str | bool | None:
    """Where prompt_id sits in a /queue response.

    Returns "running" if it is in queue_running, True if it is queued
    (queue_pending), False if the queue was read successfully and the
    prompt is in neither, or None if the response shape could not be
    parsed (so membership genuinely could not be determined).
    """
    if not isinstance(queue, dict):
        return None
    running = queue.get("queue_running")
    pending = queue.get("queue_pending")
    if not isinstance(running, list) and not isinstance(pending, list):
        return None

    def _ids(rows: Any) -> set[str]:
        out: set[str] = set()
        for row in (rows or []):
            if isinstance(row, (list, tuple)) and len(row) > 1:
                out.add(str(row[1]))
            elif isinstance(row, dict) and row.get("prompt_id"):
                out.add(str(row["prompt_id"]))
        return out

    if str(prompt_id) in _ids(running):
        return "running"
    if str(prompt_id) in _ids(pending):
        return True
    return False


def reconcile(
    http: HttpFn,
    comfy_url: str,
    prompt_id: str,
    attempt_id: str,
    conn,
) -> dict[str, Any]:
    """Reconcile an in-flight attempt against ComfyUI's /history and /queue.

    Fix 2026-09-23 (readiness-audit finding 1.4): this previously had no
    terminal-error branch at all -- anything that was not
    completed-with-outputs was unconditionally reported "RUNNING", so a
    genuinely failed render (status_str == "error") and a vanished prompt_id
    that ComfyUI no longer knows about (restart, cancellation, history
    eviction) were both indistinguishable from one still legitimately in
    progress, forever. This adds a real terminal-error branch and a
    best-effort /queue cross-check before ever giving up on a prompt_id
    that is simply absent from /history, so a transient gap does not get
    misreported as failed -- and a genuinely lost job does not get reported
    as RUNNING forever either.
    """
    history = http(f"{comfy_url.rstrip('/')}/history/{prompt_id}", None, "GET", DEFAULT_TIMEOUT_S)
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if isinstance(entry, dict):
        status_info = entry.get("status") or {}
        status_str = str(status_info.get("status_str") or "").lower()
        completed = bool(status_info.get("completed")) or bool(entry.get("outputs"))
        if completed:
            set_attempt_status(conn, attempt_id, "RENDERED")
            return {"attempt_id": attempt_id, "prompt_id": prompt_id, "status": "RENDERED", "history": entry}
        if status_str == "error":
            set_attempt_status(conn, attempt_id, "FAILED")
            return {
                "attempt_id": attempt_id, "prompt_id": prompt_id, "status": "FAILED",
                "history": entry, "reason": "comfyui_status_error",
            }
        set_attempt_status(conn, attempt_id, "RUNNING")
        return {"attempt_id": attempt_id, "prompt_id": prompt_id, "status": "RUNNING"}

    # No history entry for this prompt_id at all. Before assuming it
    # vanished, check whether ComfyUI still has it queued or running.
    try:
        queue = http(f"{comfy_url.rstrip('/')}/queue", None, "GET", DEFAULT_TIMEOUT_S)
    except ExecutorError:
        queue = None
    membership = _queue_membership(queue, prompt_id)
    if membership == "running":
        set_attempt_status(conn, attempt_id, "RUNNING")
        return {"attempt_id": attempt_id, "prompt_id": prompt_id, "status": "RUNNING"}
    if membership is True:
        set_attempt_status(conn, attempt_id, "QUEUED")
        return {"attempt_id": attempt_id, "prompt_id": prompt_id, "status": "QUEUED"}
    if membership is False:
        # Positively absent from both /history and /queue: the job is
        # lost, not merely slow. Must not be reported as RUNNING forever.
        set_attempt_status(conn, attempt_id, "FAILED")
        return {
            "attempt_id": attempt_id, "prompt_id": prompt_id, "status": "FAILED",
            "reason": "prompt_id absent from both history and queue",
        }
    # /queue itself was unreadable or unparseable (membership is None):
    # stay conservative rather than guess a false terminal failure while
    # ComfyUI might just be briefly unreachable for this one poll.
    set_attempt_status(conn, attempt_id, "RUNNING")
    return {
        "attempt_id": attempt_id, "prompt_id": prompt_id, "status": "RUNNING",
        "note": "queue state unknown; history had no entry",
    }


def request_free(http: HttpFn, comfy_url: str) -> dict[str, Any]:
    """Memory-release request. Not proof that CUDA allocations are gone."""
    return http(
        f"{comfy_url.rstrip('/')}/free",
        {"unload_models": True, "free_memory": True},
        "POST",
        DEFAULT_TIMEOUT_S,
    )


def execution_blocked(shot_id: str, reasons: tuple[str, ...], registry_digest: str) -> ExecutionResult:
    return ExecutionResult(
        shot_id=shot_id,
        attempt_id="",
        registry_digest=registry_digest if len(registry_digest) == 64 else "0" * 64,
        implementation_id="",
        profile_id="",
        prompt_ids=(),
        status="blocked",
        artifacts=(),
        actual_frames=0,
        actual_fps_num=0,
        actual_fps_den=1,
        quality_report="",
        reason_codes=reasons,
    )
