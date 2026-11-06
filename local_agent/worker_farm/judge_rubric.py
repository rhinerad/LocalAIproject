"""Deterministic, mechanical audit rules over a saved local-agent chat
transcript. No model call, no GPU, no network access -- pure pattern
matching over already-saved text. Every finding is advisory and
`review_required`; nothing here edits agent.py, memory, or any file the
interactive agent reads or acts on.

Built for the judge_evaluation worker-farm workflow (see
docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md and
CHANGELOG/2026-09-02c_judge_evaluation_workflow.md) so idle machines can
continuously audit real conversation history for the exact failure patterns
the operator has reported this session: claiming an action happened with no
evidence, telling the operator to do something a tool could have done,
leaking Equal Shares/H3/ComfyUI content into unrelated turns, and not
executing a direct, actionable request.

Known limitation: saved chat JSON (local_agent/store.py's format) only
records `role` (user/assistant) and `content` text -- it does not persist
per-turn tool_result evidence the way the live in-process agent.py does.
Rules here work from text content alone and are therefore a coarser,
higher-recall/lower-precision net than agent.py's own live checks (e.g.
`_UNVERIFIED_EXECUTION_RE`). A finding here is a prompt for human review,
never a proven conclusion -- explicitly labelled `review_required`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_EXCERPT = 220

_COMPLETION_CLAIM_RE = re.compile(
    r"(?i)\b(?:i(?:'ve| have) (?:already )?(?:created|generated|written|"
    r"fixed|updated|saved|rendered|downloaded|installed|deployed|sent|"
    r"uploaded|built|configured)|i just (?:created|generated|fixed|saved|"
    r"rendered|sent)|this has (?:now )?been (?:created|generated|fixed|"
    r"saved|rendered|sent|updated)|has now been (?:created|generated|"
    r"fixed|saved|rendered|sent|updated))\b"
)

_SPECIALIST_LEAK_RE = re.compile(
    r"(?i)\b(?:ComfyUI|MiniMax\s*H3|Equal\s+Shares|duration\s+ladder|"
    r"voice[- ]lock|soundtrack\s+pass|native\s+R2V|overall_soundscape)\b"
)

_PROJECT_INVOKE_RE = re.compile(
    r"(?i)\b(?:Equal\s+Shares|MiniMax\s*H3|clip|shot|render|ComfyUI|voice|"
    r"soundtrack|ladder|duration|take|dialogue|prompt|frame|scene)\b"
)

_DUMPS_WORK_RE = re.compile(
    r"(?i)\b(?:you(?:'ll| will) need to|you should run|you can run|"
    r"please (?:open|run|check|go to)|you'll have to|go to the|"
    r"open (?:the )?(?:terminal|powershell|file explorer))\b"
)

_ACTION_REQUEST_RE = re.compile(
    r"(?i)^\s*(?:read|open|list|show|fetch|download|write|create|check|"
    r"run|start|stop)\b"
)


@dataclass
class Finding:
    rule_id: str
    severity: str
    message_index: int
    excerpt: str
    note: str


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text[:MAX_EXCERPT] + ("…" if len(text) > MAX_EXCERPT else "")


def evaluate(messages: list[dict]) -> list[Finding]:
    """Run every rule over one chat's message list. Pure function, no I/O."""
    findings: list[Finding] = []
    for i, msg in enumerate(messages):
        role = msg.get("role")
        content = str(msg.get("content") or "")
        if not content:
            continue

        if role == "assistant":
            if _COMPLETION_CLAIM_RE.search(content):
                findings.append(Finding(
                    rule_id="unverified_completion_claim", severity="review",
                    message_index=i, excerpt=_excerpt(content),
                    note="Assistant claims an action was completed; the saved "
                         "transcript has no tool-result field to verify "
                         "against here. Cross-check server-side evidence "
                         "(artifact registry / agentic_state) before trusting."))
            if _DUMPS_WORK_RE.search(content):
                findings.append(Finding(
                    rule_id="possible_work_dumped_on_operator", severity="review",
                    message_index=i, excerpt=_excerpt(content),
                    note="Assistant may be asking the operator to perform an "
                         "action manually. Check whether an available tool "
                         "could have done this directly instead."))
            prior_user = next(
                (str(m.get("content") or "") for m in reversed(messages[:i])
                 if m.get("role") == "user"), "")
            if _SPECIALIST_LEAK_RE.search(content) and not _PROJECT_INVOKE_RE.search(prior_user):
                findings.append(Finding(
                    rule_id="specialist_project_leak", severity="high",
                    message_index=i, excerpt=_excerpt(content),
                    note="Assistant mentions Equal Shares/H3/ComfyUI-specific "
                         "content; the preceding user turn does not appear to "
                         "have invoked that project."))
        elif role == "user" and _ACTION_REQUEST_RE.search(content):
            reply = next(
                (str(m.get("content") or "") for m in messages[i + 1:i + 2]
                 if m.get("role") == "assistant"), "")
            if reply and _DUMPS_WORK_RE.search(reply):
                findings.append(Finding(
                    rule_id="direct_action_request_not_executed", severity="review",
                    message_index=i, excerpt=_excerpt(content),
                    note="Message reads like a direct action request; the "
                         "next assistant turn reads like instructions rather "
                         "than a performed action."))
    return findings


def summarize(chat_id: str, messages: list[dict]) -> dict:
    """JSON-serializable summary -- this is what the Celery task returns."""
    findings = evaluate(messages)
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
    return {
        "chat_id": chat_id,
        "message_count": len(messages),
        "finding_count": len(findings),
        "by_rule": by_rule,
        "findings": [f.__dict__ for f in findings],
        "status": "review_required" if findings else "no_findings",
    }
