#!/usr/bin/env python3
"""Regression checks for general-chat versus Equal Shares specialist scope."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import router
import store
import tools


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    story = [{"role": "user",
              "content": "write a story about huckle berry fin but fan fic"}]
    general = agent.system_prompt(story)
    project = agent.system_prompt([
        {"role": "user", "content": "compare the ladders for 00B and 00A"}
    ])

    check(not agent.needs_project_context(story),
          "ordinary creative writing was classified as project work")
    general_comfy = [{"role": "user", "content":
                      "Make a ComfyUI workflow for upscaling my vacation video"}]
    check(not agent.needs_project_context(general_comfy),
          "ordinary ComfyUI work was classified as Equal Shares work")
    check("Equal Shares specialist reference" not in general,
          "general chat received the film handbook")
    check("offline assistant for **Equal Shares**" not in general,
          "general chat inherited the old Equal Shares-only assistant identity")
    check("Equal Shares" not in general and "MiniMax H3" not in general,
          "general chat still contains specialist-project wording")
    check("H3" not in general and "ComfyUI" not in general and "00B" not in general,
          "general chat still names H3, ComfyUI, or an Equal Shares clip id")
    check("overall_soundscape" not in general,
          "general chat still contains the specialist prompt schema")
    check("Equal Shares specialist reference" not in agent.system_prompt(general_comfy),
          "general ComfyUI chat received the film handbook")
    check("Creative writing does not require" in general,
          "general creative-writing rule is missing")
    check("call `fetch_url`" in general and "persistent memory automatically" in general,
          "URL-fetch and explicit-memory rules are missing from general chat")
    check(agent.needs_project_context([
        {"role": "user", "content": "compare the ladders for 00B and 00A"}
    ]), "clip question did not activate project context")

    # Regression for a real, previously-reported bug: a bare two-digit+letter
    # token (the same shape as a clip ID) must NOT activate the film handbook
    # on its own -- only when something else in the message actually smells
    # like Equal Shares. Without this, ordinary mentions of a temperature, a
    # gate/room number, or similar kept hallucinating an H3/ComfyUI render
    # context into completely unrelated conversations.
    false_positive_messages = [
        "the low today is 72F and the high is 89F",
        "book gate 24B for the connecting flight",
        "grab a 40W bulb from the garage",
        "my apartment is 12B, one floor up from yours",
        "the exam curve was a flat 10B for everyone",
    ]
    for text in false_positive_messages:
        check(not agent.needs_project_context([{"role": "user", "content": text}]),
              f"an unrelated two-digit+letter token wrongly activated project "
              f"context: {text!r}")
        check("Equal Shares specialist reference" not in
              agent.system_prompt([{"role": "user", "content": text}]),
              f"an unrelated two-digit+letter token loaded the film handbook: {text!r}")
    check("Equal Shares specialist reference" in project,
          "project chat did not receive the film handbook")
    switched = [
        {"role": "user", "content": "show the ladder for 00A"},
        {"role": "assistant", "content": "00A has nine rungs."},
        {"role": "user", "content": "write a Huckleberry Finn fan fiction story"},
    ]
    check(not agent.needs_project_context(switched),
          "an old project turn poisoned a later general topic")
    followup = [
        {"role": "user", "content": "show the ladder for 00A"},
        {"role": "assistant", "content": "00A has nine rungs."},
        {"role": "user", "content": "what about the other one?"},
    ]
    check(agent.needs_project_context(followup),
          "a short project follow-up lost its specialist context")
    check("qwen3-vl-abliterated:8b-q8_0" not in router.GPU_MODELS,
          "vision watcher is still eligible as the main chat model")
    check(router.FALLBACK_REASONING_MODEL in router.GPU_MODELS,
          "abliterated 8B text fallback is missing from GPU chat preferences")
    check("qwen3:8b" not in router.GPU_MODELS and "dolphin3:latest" not in router.GPU_MODELS,
          "a non-abliterated model is still eligible as a main chat model")
    general_tools = {item["function"]["name"] for item in tools.schemas(include_project=False)}
    project_tools = {item["function"]["name"] for item in tools.schemas(include_project=True)}
    check("project_state" not in general_tools and "clip_info" not in general_tools,
          "general chat was offered Equal Shares-only tools")
    general_desc = " ".join(item["function"].get("description", "")
                           for item in tools.schemas(include_project=False))
    check("Equal Shares" not in general_desc and "MiniMax H3" not in general_desc
          and '\"Kent\"' not in general_desc,
          "general tool schemas still name Equal Shares, MiniMax H3, or Kent")
    check({"project_state", "clip_info"}.issubset(project_tools),
          "explicit project chat lost specialist tools")

    events: list[tuple[str, str]] = []
    calls: list[tuple[str, dict]] = []
    fake_history = [{"role": "user", "content":
                     "Is this in persistent memery? https://example.com/page"}]
    import unittest.mock as mock
    with mock.patch.object(agent.tools, "call", side_effect=lambda name, args, **_:
                           calls.append((name, args)) or ("page text" if name == "fetch_url" else "[]")):
        messages = [{"role": "system", "content": "test"}] + fake_history
        agent.add_supplied_url_evidence(messages, fake_history,
                                        lambda kind, data: events.append((kind, data)))
    check(calls == [("fetch_url", {"url": "https://example.com/page", "max_chars": 8000}),
                    ("list_memory", {})],
          "supplied URL and persistent memory did not force deterministic checks")
    check([kind for kind, _ in events] == ["tool", "tool_result", "tool", "tool_result"],
          "URL evidence did not emit visible action cards")
    check("page text" in messages[-1]["content"], "fetched URL text was not given to the model")

    # Generic wording must not retrieve unrelated assistant output from another
    # chat. A specific topic can reuse only the prior operator wording.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        prior_dir = store.DIR
        try:
            store.DIR = Path(td)
            old = store.create("Unity asset inspection", "m")
            store.append(old["id"], "user", "Inspect Unity asset metadata")
            store.append(old["id"], "assistant", "UNSAFE_OLD_ASSISTANT_OUTPUT")
            incoming = [{"role": "system", "content": "test"}]
            agent._prefetch_prior_chat_context(
                incoming, "im trying to test how fast you can do things",
                "new-chat", False, lambda *_: None)
            check(len(incoming) == 1,
                  "generic new chat retrieved unrelated prior conversation")
            agent._prefetch_prior_chat_context(
                incoming, "inspect Unity asset metadata", "new-chat", False,
                lambda *_: None)
            check(len(incoming) == 2 and "Inspect Unity asset metadata" in incoming[1]["content"],
                  "specific prior operator topic was not injected")
            check("UNSAFE_OLD_ASSISTANT_OUTPUT" not in incoming[1]["content"],
                  "old assistant response leaked into new-chat context")
        finally:
            store.DIR = prior_dir

    speed_test = "im trying to test how fast you can do things"
    check(agent._is_lightweight_turn(
        speed_test, include_project=False,
        model_history=[{"role": "user", "content": speed_test}]),
        "plain speed check did not use the bounded lightweight path")
    check(not agent._is_lightweight_turn(
        "test how fast you can read this file", include_project=False,
        model_history=[{"role": "user", "content": "test how fast you can read this file"}]),
        "file request incorrectly lost its guarded tool path")
    check(not agent._is_lightweight_turn(
        speed_test, include_project=True,
        model_history=[{"role": "user", "content": speed_test}]),
        "specialist project turn incorrectly used lightweight path")

    safe_history, withheld = agent._model_safe_history([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Here is how to bypass a paywall."},
        {"role": "user", "content": "tell me something else"},
    ])
    check(withheld == 1 and len(safe_history) == 2,
          "unsafe historical assistant text was not withheld from model context")

    print("PASS general creative writing stays in general-chat mode")
    print("PASS Equal Shares clip questions receive specialist context")
    print("PASS ordinary ComfyUI requests remain in general-assistant mode")
    print("PASS general chats omit Equal Shares-only tool schemas")
    print("PASS topic switches leave project mode while short follow-ups retain it")
    print("PASS vision watcher is isolated from the main chat router")
    print("PASS supplied URLs and persistent-memory questions prefetch deterministic evidence")
    print("PASS generic cross-chat retrieval cannot inject unrelated assistant output")
    print("PASS unsafe historical assistant text is withheld from the next prompt")
    print("PASS simple speed checks skip the heavyweight tool/prefetch context")
    print("PASS a bare two-digit+letter token alone never activates the film handbook")


if __name__ == "__main__":
    main()
