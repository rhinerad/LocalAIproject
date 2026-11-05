from pathlib import Path

p = Path("local_agent/agent.py")
text = p.read_text(encoding="utf-8")

old_re = """_SPECIALIST_CONTINUATION_OFFER_RE = re.compile(
    r\"\\b(?:would\\s+you\\s+like|do\\s+you\\s+want|shall\\s+i|ready\\s+to\\s+(?:be\\s+)?render|\"
    r\"i\\s+can\\s+start|let\\s+me\\s+know\\s+if|proceed\\s+with|ready\\s+for\\s+rendering|\"
    r\"(?:plans?|images?)\\s+(?:are|is)\\s+(?:now\\s+)?ready)\\b\",
    re.I)"""

new_re = """_SPECIALIST_CONTINUATION_OFFER_RE = re.compile(
    r\"\\b(?:would\\s+you\\s+like|do\\s+you\\s+want|shall\\s+i|ready\\s+to\\s+(?:be\\s+)?render|\"
    r\"i\\s+can\\s+start|let\\s+me\\s+know\\s+if|proceed\\s+with|ready\\s+for\\s+rendering|\"
    r\"(?:plans?|images?)\\s+(?:are|is)\\s+(?:now\\s+)?ready|\"
    r\"i\\s+have\\s+prepared|prepared\\s+(?:an?\\s+)?(?:inspectable\\s+)?(?:[^.\\n]{0,80}\\s)?(?:plan|graph)|\"
    r\"i\\s+will\\s+proceed\\s+to\\s+(?:generate|render)|\"
    r\"plan_story_image|call\\s+render_story_image)\\b\",
    re.I)"""

if old_re not in text:
    raise SystemExit("offer regex block not found")
text = text.replace(old_re, new_re, 1)

old_fn = '''def _pending_specialist_continuation(history: list[dict] | None) -> bool:
    """Whether the assistant's immediately-previous turn left an open,
    undeclined invitation to continue specialist (render/image) work.

    Deliberately narrower than "did any earlier turn in this conversation
    ever mention render/image" -- that broader check would also swallow the
    legitimate `test_stale_h3_render_reply_is_discarded_on_unrelated_turn`
    case, where an earlier render was explicitly *declined* ("No render was
    started...") and the operator then moved to a genuinely different topic;
    a later hallucinated render reply there must still be caught. Only an
    active, un-declined offer in the immediately preceding assistant turn
    (e.g. "these plans are ready -- would you like me to proceed?") should
    let a short confirmation reply like "yes, go ahead" stay in scope
    without having to restate the whole topic.
    """
    if not history:
        return False
    last_assistant = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
    if not last_assistant:
        return False
    text = str(last_assistant.get("content", ""))
    if not _requests_specialist_project_context(text):
        return False
    return bool(_SPECIALIST_CONTINUATION_OFFER_RE.search(text))'''

new_fn = '''def _assistant_planned_story_image(message: dict | None) -> bool:
    """True when this assistant message already ran a successful plan_story_image.

    Live chats persist tool_evidence / activity on the assistant turn. A
    successful plan is an active, undeclined invitation to continue with
    render_story_image even when the prose said "I will proceed" instead of
    an explicit "would you like" offer.
    """
    if not isinstance(message, dict):
        return False
    for row in message.get("tool_evidence") or []:
        if not isinstance(row, dict):
            continue
        if row.get("tool") == "plan_story_image" and str(row.get("outcome") or "") != "error":
            return True
    for row in message.get("activity") or []:
        if not isinstance(row, dict):
            continue
        if (row.get("tool") == "plan_story_image"
                and row.get("kind") in {"tool_result", "tool_call"}
                and str(row.get("outcome") or row.get("state") or "") != "error"):
            return True
    return False


def _pending_specialist_continuation(history: list[dict] | None) -> bool:
    """Whether the assistant's immediately-previous turn left an open,
    undeclined invitation to continue specialist (render/image) work.

    Deliberately narrower than "did any earlier turn in this conversation
    ever mention render/image" -- that broader check would also swallow the
    legitimate `test_stale_h3_render_reply_is_discarded_on_unrelated_turn`
    case, where an earlier render was explicitly *declined* ("No render was
    started...") and the operator then moved to a genuinely different topic;
    a later hallucinated render reply there must still be caught. Only an
    active, un-declined offer / successful plan_story_image in the
    immediately preceding assistant turn (e.g. "these plans are ready --
    would you like me to proceed?" or tool_evidence for plan_story_image)
    should let a short confirmation reply like "yes, go ahead" / "proceed"
    stay in scope without having to restate the whole topic.
    """
    if not history:
        return False
    last_assistant = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
    if not last_assistant:
        return False
    if _assistant_planned_story_image(last_assistant):
        return True
    text = str(last_assistant.get("content", ""))
    if not _requests_specialist_project_context(text):
        return False
    return bool(_SPECIALIST_CONTINUATION_OFFER_RE.search(text))'''

if old_fn not in text:
    raise SystemExit("pending fn not found")
text = text.replace(old_fn, new_fn, 1)

old_scope = "        specialist_scope = _requests_specialist_project_context(latest_user)"
new_scope = """        specialist_scope = (
            _requests_specialist_project_context(latest_user)
            or _pending_specialist_continuation(history)
        )"""
if old_scope not in text:
    raise SystemExit("specialist_scope assignment not found")
text = text.replace(old_scope, new_scope, 1)

p.write_text(text, encoding="utf-8")
print("agent.py updated OK")
