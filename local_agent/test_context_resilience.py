#!/usr/bin/env python3
"""Regression checks for cross-chat operating memory and context compaction."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import router
import tools


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    prompt = agent.system_prompt([{"role": "user", "content": "hello"}])
    check("Local-agent operating memory" in prompt,
          "new chats are missing reviewed operating memory")
    check("historic 20 GB" in prompt,
          "32B role correction is missing from cross-chat memory")
    base_tokens = router.estimate_context_tokens(
        [{"role": "system", "content": prompt}], tools.schemas())
    check(base_tokens < router.CPU_OPTIONS["num_ctx"],
          "CPU context cannot fit the required policy and native tool schemas")

    # This is a deterministic regression suite, not a model benchmark. The
    # exact CPU helper is separately validated by test_context_compactor.py and
    # a controlled live check. Never make routine CI/regression runs load it.
    original_summarize = agent.context_compactor.summarize_old_messages
    agent.context_compactor.summarize_old_messages = lambda _messages: {
        "goal": "preserve active conversation continuity",
        "decisions": [], "open_questions": [], "tool_state": [],
        "hard_constraints": [], "notable_files": [],
    }

    history = [{"role": "system", "content": "system"},
               {"role": "user", "content": "A" * 12000},
               {"role": "assistant", "content": "old response"},
               {"role": "user", "content": "keep the VLM lazy"},
               {"role": "assistant", "content": "acknowledged"},
               {"role": "user", "content": "what model is active now?"}]
    notes: list[str] = []
    compact = agent._trim_context(history, 1500, [],
                                  lambda kind, text: notes.append(text))
    joined = "\n".join(str(m.get("content", "")) for m in compact)
    check("A" * 1000 not in joined,
          "giant opening paste is still pinned forever")
    check("Conversation continuity" in joined,
          "older user intent was dropped instead of compacted")
    check("what model is active now?" in joined,
          "latest operator request was not preserved")
    check(any("context compacted" in note for note in notes),
          "context compaction was not reported")
    check(not any("use a larger context" in note for note in notes),
          "context compaction still tells the operator to fix an internal budget")

    tool_tail = [{"role": "system", "content": "system"},
                 {"role": "user", "content": "old question"},
                 {"role": "assistant", "content": "", "tool_calls": [
                     {"function": {"name": "project_state", "arguments": {}}}]},
                 {"role": "tool", "name": "project_state", "content": "state"},
                 {"role": "user", "content": "answer now"}]
    preserved = agent._trim_context(tool_tail, 9999, [], lambda *_: None)
    check(any(m.get("tool_calls") for m in preserved),
          "native tool-call message was split from its result")
    check(any(m.get("role") == "tool" for m in preserved),
          "native tool result was lost during compaction")

    # A single multi-tool hop must fit the CPU fallback after deterministic
    # evidence clipping. The policy + schemas themselves need just under 10k,
    # which is why the CPU route uses a 16k context rather than 8k.
    large_tool_tail = [{"role": "system", "content": "system"},
                       {"role": "user", "content": "inspect this"},
                       {"role": "assistant", "content": "", "tool_calls": [
                           {"function": {"name": "list_dir", "arguments": {}}}]},
                       {"role": "tool", "name": "list_dir", "content": "X" * 18000},
                       {"role": "user", "content": "summarize the evidence"}]
    fitted = agent._trim_context(large_tool_tail, 2500, [], lambda *_: None)
    tool_text = next(m["content"] for m in fitted if m.get("role") == "tool")
    check(len(tool_text) <= 900,
          "large tool evidence was not clipped for the CPU-safe context")
    agent.context_compactor.summarize_old_messages = original_summarize
    print("PASS operating memory reaches a new chat")
    print("PASS CPU context fits policy plus native tool schemas")
    print("PASS giant opening paste no longer pins the context")
    print("PASS active native tool exchange remains intact")
    print("PASS large tool evidence is compacted for CPU fallback")


if __name__ == "__main__":
    main()
