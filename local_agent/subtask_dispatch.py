#!/usr/bin/env python3
"""Bounded coordinator/worker fan-out for independent sub-questions.

This is the one deliberately narrow "multi-agent" primitive in this
codebase. The primary chat model (the coordinator) can break a task into a
handful of genuinely independent sub-questions and get all of them answered
concurrently instead of one at a time through the main hop loop.

Scope is kept small on purpose:

- Workers are plain text-in/text-out CPU calls with NO tool access, so a
  worker cannot itself recurse into rendering, file writes, scheduling, or
  another dispatch call. This avoids the safety and debugging complexity of
  a general recursive sub-agent framework.
- Workers always run on the CPU host with the same thermal thread cap as
  every other CPU-side helper in this codebase (router.CPU_THREAD_CAP),
  never routed through router.decide(). A render or the primary model may
  already be using idle GPU capacity; concurrently loading a second model
  onto the GPU from several background workers at once is exactly the kind
  of race this project's "one backend, ever" rule exists to prevent, so
  these workers are hardcoded off the GPU entirely rather than trusting a
  per-worker gate to serialize correctly under concurrency.
- Bounded: at most MAX_SUBTASKS sub-questions, MAX_SUBTASK_CHARS each, with
  a per-worker timeout, so a coordinator cannot fan out into a large batch
  job through what is meant to be a quick research-splitting primitive.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import context_compactor
import ollama_client as oll
import router

MAX_SUBTASKS = 5
MAX_SUBTASK_CHARS = 500
WORKER_TIMEOUT_S = 60
MODEL = context_compactor.MODEL  # the same small CPU helper model, already
                                  # verified installed by context_compactor

_WORKER_SYSTEM_PROMPT = (
    "Answer this one question directly and concisely from your own "
    "knowledge only. You have no tools, cannot browse the web, read files, "
    "or take any action. If the question genuinely requires one of those, "
    "say so plainly instead of guessing or inventing an answer."
)


class DispatchError(RuntimeError):
    pass


def _installed() -> bool:
    try:
        return any(str(tag).split(":")[0] == MODEL.split(":")[0]
                   for tag in router._tags(router.CPU_HOST))
    except Exception:
        return False


def _run_one(question: str) -> str:
    try:
        text, _calls = oll.chat(
            [{"role": "system", "content": _WORKER_SYSTEM_PROMPT},
             {"role": "user", "content": question}],
            model=MODEL, host=router.CPU_HOST, timeout=WORKER_TIMEOUT_S,
            keep_alive="0",
            options={"num_gpu": 0, "num_thread": router.CPU_THREAD_CAP,
                     "num_ctx": 4096, "temperature": 0.2},
        )
        return (text or "").strip() or "(worker returned no text)"
    except Exception as exc:
        return f"ERROR: worker failed: {type(exc).__name__}: {exc}"


def dispatch(tasks: list) -> list[dict]:
    """Answer each of ``tasks`` concurrently. Returns [{"task", "answer"}, ...]
    in the same order the tasks were given, regardless of completion order."""
    if not isinstance(tasks, list) or not tasks:
        raise DispatchError("tasks must be a non-empty list of short, independent questions")
    if len(tasks) > MAX_SUBTASKS:
        raise DispatchError(f"at most {MAX_SUBTASKS} subtasks per call, got {len(tasks)}")
    if not _installed():
        raise DispatchError(
            f"the {MODEL} CPU worker model is not installed; "
            f"run: ollama pull {MODEL}")

    cleaned: list[str] = []
    for raw in tasks:
        t = str(raw or "").strip()
        if not t:
            raise DispatchError("each subtask must be non-empty text")
        cleaned.append(t[:MAX_SUBTASK_CHARS])

    with ThreadPoolExecutor(max_workers=len(cleaned)) as executor:
        answers = list(executor.map(_run_one, cleaned))

    return [{"task": t, "answer": a} for t, a in zip(cleaned, answers)]


def dispatch_json(args: dict) -> str:
    result = dispatch(args.get("tasks"))
    return json.dumps(result, indent=2)
