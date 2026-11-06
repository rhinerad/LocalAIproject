#!/usr/bin/env python3
"""Bounded, durable task checkpoints for the local agent.

This module stores an *operator-visible working record*, not private model
reasoning.  It is deliberately stdlib-only and only records goals, explicit
checklist steps, and tool observations.  The actual authority remains in
``tools.py``; a checkpoint can never execute an action or bypass validation.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from atomic_io import atomic_write_text

import managed_prompt_pack

DIR = Path(__file__).resolve().parent / "runtime" / "agentic_tasks"
_CID_RE = re.compile(r"[A-Za-z0-9_-]{4,40}$")
_SPLIT_RE = re.compile(r"(?:\n\s*(?:\d+[.)]|[-*])\s+|\s*;\s+)")
_COMPLEX_RE = re.compile(
    r"\b(?:implement|build|fix|debug|investigate|compare|audit|verify|"
    r"refactor|update|create|render|install|test|plan|then|and)\b", re.I)
_WAITING_RE = re.compile(r"\b(?:please provide|need (?:the|a|an)|cannot|"
                         r"unable|blocked|failed|error)\b", re.I)
_FOLLOW_UP_RE = re.compile(r"^\s*(?:continue|proceed|keep\s+going|go ahead|next|then|also|and|"
                           r"now|please|resume|finish(?:\s+it)?|what about|how about)\b", re.I)
_DOC_RE = re.compile(
    r"\b(?:documentation|docs?|changelog|operating memory|persistent memory|"
    r"project (?:rule|history|decision|status)|why (?:is|was|does)|"
    r"what (?:does|did) (?:the|our) (?:rule|documentation)|according to|"
    r"current (?:rule|policy|configuration|setup)|supersed(?:e|ed|ing))\b", re.I)
_TERM_RE = re.compile(r"[a-z0-9]{3,}", re.I)
_TERMS_SKIP = frozenset({"the", "and", "that", "this", "with", "from", "for", "into",
                         "then", "please", "about", "current", "project", "agent"})


def _path(cid: str) -> Path:
    if not _CID_RE.fullmatch(str(cid or "")):
        raise ValueError(f"bad conversation id {cid!r}")
    return DIR / f"{cid}.json"


def load(cid: str) -> dict | None:
    try:
        p = _path(cid)
        raw = json.loads(p.read_text(encoding="utf8")) if p.is_file() else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _save(state: dict) -> dict:
    state["updated"] = time.time()
    p = _path(state["conversation_id"])
    atomic_write_text(p, json.dumps(state, indent=2, ensure_ascii=False))
    return state


def _short(text: object, limit: int = 360) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit] + ("…" if len(value) > limit else "")


def _is_complex(text: str) -> bool:
    clean = " ".join((text or "").split())
    return (len(clean) >= 120 or bool(_SPLIT_RE.search(clean)) or
            (len(clean.split()) >= 8 and len(_COMPLEX_RE.findall(clean)) >= 2))


def _terms(text: str) -> set[str]:
    return {term.lower() for term in _TERM_RE.findall(text or "")
            if term.lower() not in _TERMS_SKIP}


def _continues(state: dict | None, text: str) -> bool:
    """Whether a new substantive message advances the existing task.

    This is deliberately conservative: a short explicit follow-up continues,
    or a longer request needs meaningful vocabulary overlap with the saved goal.
    A separate task therefore replaces stale state instead of contaminating it.
    """
    if not state or state.get("status") in {"completed", "stopped", "superseded"}:
        return False
    if _FOLLOW_UP_RE.search(text or ""):
        return True
    old, new = _terms(str(state.get("goal", ""))), _terms(text)
    return bool(old and new and len(old & new) >= 2)


def _prior_task(state: dict) -> dict:
    """Keep a bounded, non-destructive record when a chat changes subject."""
    return {
        "goal": _short(state.get("goal"), 900),
        "status": str(state.get("status", "active")),
        "updated": state.get("updated"),
        "superseded_at": time.time(),
    }


def _supersede_short_request(state: dict, operator_text: str) -> None:
    """Close stale work rather than injecting it into an unrelated short turn."""
    state["status"] = "superseded"
    state["superseded_by"] = _short(operator_text, 360)
    state["superseded_at"] = time.time()
    _save(state)


def _steps(text: str) -> list[dict]:
    pieces = [_short(part, 160) for part in _SPLIT_RE.split(text) if part.strip()]
    if len(pieces) < 2:
        pieces = ["Inspect the relevant evidence and constraints",
                  "Carry out only permitted actions and verify the result",
                  "Report the outcome or the exact remaining decision"]
    return [{"id": index + 1, "title": title, "status": "pending"}
            for index, title in enumerate(pieces[:6])]


def begin_turn(cid: str, operator_text: str) -> dict | None:
    """Create/update a checkpoint when an operator has a multi-step goal.

    Casual chat does not create a plan.  A short follow-up keeps the current
    checkpoint, while a new substantial request replaces it rather than leaking
    an unrelated old task into a new topic.
    """
    if not cid:
        return None
    state = load(cid)
    text = _short(operator_text, 900)
    # An explicit continuation is meaningful even when it is a short sentence.
    # Handle it before the complexity threshold so “Continue with the checks”
    # advances the current task instead of being treated as casual chat.
    if _continues(state, operator_text):
        state["last_operator_request"] = text
        state["status"] = "active"
        blocked = next((step for step in state.get("plan", [])
                        if step.get("status") == "blocked"), None)
        if blocked:
            blocked["status"] = "pending"
        state.setdefault("updates", []).append(_short(operator_text, 260))
        state["updates"] = state["updates"][-4:]
        # Unlock render only when continue text explicitly asks to render.
        if state.get("kind") == "prompt_pack" and managed_prompt_pack.wants_explicit_render(operator_text):
            try:
                managed_prompt_pack.ingest(cid, allow_render=True)
                state.setdefault("prompt_pack", {})["allow_render"] = True
            except Exception:
                pass
        return _save(state)
    # Large creative/storyboard prompt packs: persist full source before the
    # 900-char goal truncation, chunk clips, and expose exact paths so
    # continue/compaction cannot lose the operator pack.
    pack_progress = None
    if managed_prompt_pack.is_prompt_pack(operator_text):
        try:
            pack_progress = managed_prompt_pack.ingest(
                cid, operator_text,
                allow_render=managed_prompt_pack.wants_explicit_render(operator_text),
            )
        except Exception as exc:
            pack_progress = {"error": str(exc)}

    if not _is_complex(operator_text) and not pack_progress:
        # A direct question, attachment request, or other short new subject must
        # never inherit an old active plan.  The old checkpoint remains on disk
        # as superseded evidence, but is not sent to the model this turn.
        if state:
            _supersede_short_request(state, operator_text)
        return None
    prior_tasks = list(state.get("prior_tasks", []))[-3:] if state else []
    if state:
        prior_tasks.append(_prior_task(state))
    if pack_progress and not pack_progress.get("error"):
        plan = [
            {"id": 1, "title": "Persist full prompt-pack source as managed artifact",
             "status": "completed"},
            {"id": 2, "title": "Chunk clips and write durable progress",
             "status": "working"},
            {"id": 3, "title": "Export per-clip output files to the pack folder",
             "status": "pending"},
            {"id": 4, "title": "Resume from progress on continue/proceed (no re-paste)",
             "status": "pending"},
            {"id": 5, "title": "Do not render unless operator explicitly asks",
             "status": "pending"},
        ]
        goal = _short(
            f"Managed prompt pack: {pack_progress.get('title') or 'prompt_pack'} "
            f"({pack_progress.get('clip_count', 0)} clips). "
            f"Source: {pack_progress.get('source_path')}",
            900,
        )
        kind = "prompt_pack"
    else:
        plan = _steps(operator_text)
        goal = text
        kind = "general"
    state = {
        "version": 1,
        "conversation_id": cid,
        "goal": goal,
        "status": "active",
        "kind": kind,
        "plan": plan,
        "observations": [],
        "last_operator_request": text,
        "updated": time.time(),
    }
    if pack_progress and not pack_progress.get("error"):
        state["prompt_pack"] = {
            "source_path": pack_progress.get("source_path"),
            "output_dir": pack_progress.get("output_dir"),
            "progress_path": pack_progress.get("progress_path"),
            "clip_count": pack_progress.get("clip_count"),
            "allow_render": pack_progress.get("allow_render"),
        }
        state["active_files"] = [
            {"path": pack_progress.get("source_path"), "tool": "ingest_prompt_pack",
             "outcome": "observed"},
            {"path": pack_progress.get("output_dir"), "tool": "ingest_prompt_pack",
             "outcome": "observed"},
            {"path": pack_progress.get("progress_path"), "tool": "ingest_prompt_pack",
             "outcome": "observed"},
        ]
    if prior_tasks:
        state["prior_tasks"] = prior_tasks[-4:]
    saved = _save(state)
    # This marker is intentionally return-only. It lets the harness ask for one
    # structured plan proposal for a newly-created substantive goal without
    # storing a transient implementation detail in the durable checkpoint.
    returned = dict(saved)
    returned["_new_task"] = True
    if kind == "prompt_pack":
        returned["_prompt_pack"] = True
    return returned


def apply_proposed_plan(cid: str, proposal: dict) -> dict | None:
    """Replace only the inert checklist after strict planner validation.

    The proposal is never an executable instruction. Tool choice and argument
    validation remain exclusively in ``agent.py`` / ``tools.py``.
    """
    state = load(cid)
    if not state or not isinstance(proposal, dict):
        return None
    raw_steps = proposal.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None
    steps = []
    for index, item in enumerate(raw_steps[:6], 1):
        if not isinstance(item, dict):
            return None
        title = _short(item.get("title"), 180)
        success = _short(item.get("success_condition"), 180)
        if not title or not success:
            return None
        steps.append({"id": index, "title": title, "success_condition": success,
                      "status": "pending"})
    # The operator's request is the durable task identity.  A planner is only
    # allowed to improve the inert checklist: accepting its paraphrased ``goal``
    # used to let a confused model silently replace the real task after context
    # compaction (for example, turning PowerInfer calibration work into a render
    # recovery task).  Keep the original operator goal verbatim/bounded instead.
    state["goal"] = _short(state.get("goal"), 900)
    state["plan"] = steps
    state["plan_source"] = "structured_local_model"
    state["needs_operator_decision"] = bool(proposal.get("needs_operator_decision", False))
    return _save(state)


def retrieval_query(operator_text: str) -> str | None:
    """Return a bounded local-doc query only when project evidence is requested.

    This is the retrieve-decision part of the harness. It never searches the
    web and never replaces the model's normal ability to call ``search_docs``.
    It only prefetches safe local evidence for questions that explicitly ask
    about project policy, history, configuration, or documentation.
    """
    if not _DOC_RE.search(operator_text or ""):
        return None
    return _short(operator_text, 480)


def observe_tool(cid: str, name: str, args: object, result: object) -> dict | None:
    """Record one bounded evidence observation after the normal tool boundary."""
    state = load(cid)
    if not state:
        return None
    summary = _short(result, 520)
    failed = summary.upper().startswith("ERROR:") or "\"error\"" in summary.lower()
    observation = {
        "at": time.time(), "tool": _short(name, 80),
        "arguments": _short(json.dumps(args, sort_keys=True, default=str), 220),
        "summary": summary, "outcome": "failed" if failed else "observed",
    }
    state.setdefault("observations", []).append(observation)
    state["observations"] = state["observations"][-8:]
    # A real path returned to the agent is operational evidence, not a model
    # suggestion. Keep a tiny per-chat working set so context compaction cannot
    # turn it into an invented ellipsis or a documentation example on the next
    # follow-up. This is not long-term memory and never gives the path authority
    # to run a tool by itself.
    path_values: list[str] = []
    if isinstance(args, dict):
        candidate = args.get("path")
        if isinstance(candidate, str) and candidate.strip():
            path_values.append(candidate.strip())
    try:
        payload = json.loads(str(result))
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        candidate = payload.get("path")
        if isinstance(candidate, str) and candidate.strip():
            path_values.append(candidate.strip())
    if path_values:
        active_files = list(state.get("active_files", []))
        for value in path_values:
            active_files = [item for item in active_files if item.get("path") != value]
            active_files.append({"path": _short(value, 520), "tool": _short(name, 80),
                                 "outcome": "failed" if failed else "observed"})
        state["active_files"] = active_files[-4:]
    plan = state.get("plan") or []
    active = next((step for step in plan if step.get("status") in {"pending", "working"}), None)
    if active:
        active["status"] = "blocked" if failed else "working"
    state["status"] = "blocked" if failed else "active"
    return _save(state)


def finish_turn(cid: str, reply: str, stopped: bool = False) -> dict | None:
    state = load(cid)
    if not state:
        return None
    state["last_reply"] = _short(reply, 600)
    if stopped:
        state["status"] = "stopped"
    elif _WAITING_RE.search(reply):
        state["status"] = "awaiting_operator"
    elif state.get("status") == "active":
        active = next((step for step in state.get("plan", [])
                       if step.get("status") == "working"), None)
        if active:
            active["status"] = "completed"
        if not any(step.get("status") in {"pending", "working"}
                   for step in state.get("plan", [])):
            state["status"] = "completed"
    return _save(state)


def prompt_block(cid: str) -> str:
    """Return compact trusted task state for the next model call, if any."""
    state = load(cid)
    if not state or state.get("status") == "superseded":
        return ""
    plan = "; ".join(f"{step.get('id')}. {step.get('status')}: {step.get('title')}"
                     for step in state.get("plan", [])[:6])
    evidence = "; ".join(f"{item.get('tool')}: {item.get('summary')}"
                           for item in state.get("observations", [])[-3:])
    active_files = "; ".join(
        f"{item.get('path')} ({item.get('tool')}, {item.get('outcome')})"
        for item in state.get("active_files", [])[-4:])
    base = (
        "Trusted task checkpoint (operator-visible; not hidden reasoning).\n"
        f"Goal: {state.get('goal', '')}\nStatus: {state.get('status', 'active')}\n"
        f"Plan: {plan or 'none'}\nRecent evidence: {evidence or 'none yet'}\n"
        f"Exact active file paths: {active_files or 'none yet'}\n"
        "Use observations only as evidence for factual state claims. If evidence is "
        "missing or conflicting, say it is unverified and use an appropriate allowed tool."
    )
    pack = managed_prompt_pack.prompt_block(cid)
    if pack:
        return base + "\n\n" + pack
    return base
