#!/usr/bin/env python3
"""Current-turn action-resolution layer.

classify(text, history, cid, pending_calibration_path_fn, specialist_scope)
    -> ActionPlan | None

Returns an ActionPlan for direct requests that map to known safe tools.
Returns None to fall through to the normal model turn.

SCOPE: current-turn only.  Same-chat tool evidence is consulted only to
recover paths the operator is explicitly referring back to.  Old specialist
context (H3, ComfyUI, Equal Shares) is never activated by this module unless
the current message explicitly opens it.

GUARDS: all guards in tools.py and agent.py are preserved.  This module
maps requests to tool names and arguments only; the actual tool call, with
all its protected-file, phone-identity, GPU-gateway, and render-preflight
guards, still goes through agent.py's existing execution path.

ADDING INTENTS: add a pattern constant, add a classify branch (keep them in
priority order: safety first, then evidence-required intents, then open
file/folder intents, then CPU-only extras), and add a regression test in
test_action_resolver.py. Extra CPU/farm intents must take profile="cpu" and
must not fire on the default GPU profile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import managed_prompt_pack

# ── Intent match patterns ──────────────────────────────────────────────────────

# Matches emphatic or direct repair/fix requests, including
#   "fix it", "fix the formatting error", "you were supposed to fix it",
#   "repair the JSONL", "correct this", "reformat the file"
_JSONL_REPAIR_RE = re.compile(
    r"\b(?:fix|repair|correct|reformat|format)\b"
    r"(?:.{0,120}\b(?:it|this|file|jsonl|format(?:ting)?|error)\b)?",
    re.I | re.S,
)

# Mirrors agent._STOP_COMFYUI_RE exactly so the resolver owns this branch.
_COMFYUI_STOP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:stop|kill|abort|cancel|shut\s+down)"
    r"(?:\s+(?:all|the))?\s+(?:current\s+)?(?:batch\s+)?"
    r"(?:comfyui|comfy|render(?:s|ing)?)(?:\s+(?:now|please))?[.!?\s]*$",
    re.I,
)

# Matches "show/list/browse/open … folder/directory/files/contents"
# or "what's in … folder/dir"
_LIST_DIR_RE = re.compile(
    r"\b(?:show|list|browse|open)\b.{0,80}\b(?:folder|directory|dir|files?|contents?)\b"
    r"|\bwhat(?:'?s|\s+is)\s+in\b.{0,80}\b(?:folder|directory|dir)\b",
    re.I,
)

# Matches "read/open/show/view/display … file/document/text"
_READ_FILE_RE = re.compile(
    r"\b(?:read|open|show|view|display|print)\b.{0,80}\b(?:file|document|text)\b",
    re.I,
)

# Matches calibration-continuation intent:
#   "continue with the PowerInfer project using the JSON I approved"
#   "proceed with the approved JSON"
#   "use the calibration JSON"
_CALIBRATION_CONTINUE_RE = re.compile(
    r"\b(?:continue|proceed|go\s+ahead|use|apply)\b.{0,120}"
    r"\b(?:json(?:l)?|calibration|approved|powerinfer|sparse)\b"
    r"|\b(?:json(?:l)?|calibration|approved)\b.{0,120}\b(?:continue|use|apply)\b",
    re.I | re.S,
)

# Extracts the first Windows or Unix-style path from a message.
# Handles: C:\…, A:\…, ./…, /something, but not bare relative names.
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/])[^\s\"'<>|?*;,\n]+"
    r"|(?:\.[\\/])[^\s\"'<>|?*;,\n]+"
    r"|(?:/(?:[^\s\"'<>|?*;,\n]+))",
    re.I,
)

# CPU/farm-only extras (Layer B). High precision; still None on ambiguity.
# These run only when classify(..., profile="cpu") after the five global
# intents. GPU free-form tool selection must not gain these regexes.

# Explicit web search. "search" alone is too broad (docs, files). A URL in
# the message is fetch_url's job, not web_search.
_WEB_SEARCH_RE = re.compile(
    r"\b(?:search\s+(?:the\s+)?web|web\s+search|google|look\s+up)\b",
    re.I,
)
_WEB_SEARCH_QUERY_RE = re.compile(
    r"(?:search\s+(?:the\s+)?web|web\s+search|google|look\s+up)"
    r"(?:\s+(?:for|about))?\s*[:\-]?\s*(.+)$",
    re.I | re.S,
)
_URL_IN_TEXT_RE = re.compile(r"https?://", re.I)

# Sensory/tool inventory. Do not match the bare word "capabilities"
# (GPU tests and inspect-capabilities prose must still reach the model).
_CAPABILITIES_RE = re.compile(
    r"\bwhat\s+(?:can|do)\s+you\s+(?:see|hear|transcribe)\b"
    r"|\bwhat\s+tools?\s+do\s+you\s+have\b"
    r"|\bwhat\s+(?:are\s+)?your\s+(?:tools|capabilities)\b"
    r"|\bcan\s+you\s+(?:see|hear|transcribe)\b",
    re.I,
)

# Persistent-memory listing. Prefetch already handles "persistent memory";
# this is the compact-path short-circuit for the same operator ask.
_LIST_MEMORY_RE = re.compile(
    r"\bwhat\s+do\s+you\s+remember\b"
    r"|\blist\s+(?:the\s+)?(?:remembered\s+)?facts\b"
    r"|\blist\s+remembered\s+facts\b",
    re.I,
)

# Bare relative folder after list_dir matched but alias/abs-path failed.
# Live 2026-09-04o compact Qwythos burned hops on
# "list the files in the local_agent folder" because _PATH_RE rejects
# un-rooted names.
_RELATIVE_FOLDER_RE = re.compile(
    r"\b(?:in|of|inside)\s+(?:the\s+)?[`'\"]?"
    r"([A-Za-z0-9._][A-Za-z0-9._/-]*)"
    r"[`'\"]?\s+(?:folder|directory|dir)\b"
    r"|\b(?:folder|directory|dir|path)\s+(?:is|named)\s+[`'\"]?"
    r"([A-Za-z0-9._][A-Za-z0-9._/-]*)"
    r"[`'\"]?",
    re.I,
)
_RELATIVE_FOLDER_STOPWORDS = frozenset({
    "the", "a", "an", "this", "that", "my", "our", "your", "current",
    "same", "folder", "directory", "dir", "files", "file", "contents",
    "here", "there", "it", "them",
})

# Short-name aliases for folders an operator often names without a full path.
# Keys are lower-case substrings to search for; values are repo-relative paths
# suitable for tools.list_dir / tools.read_file.
_FOLDER_ALIASES: dict[str, str] = {
    "prompts_native_r2v":     "outputs/equal_shares/prompts_native_r2v",
    "native prompts":         "outputs/equal_shares/prompts_native_r2v",
    "native prompt":          "outputs/equal_shares/prompts_native_r2v",
    # bare "prompts" alias: only match when near "folder", "with", or "the"
    # to avoid clashing with "change my prompt" or "what's my prompt".
    "the prompts":            "outputs/equal_shares/prompts_native_r2v",
    "with the prompts":       "outputs/equal_shares/prompts_native_r2v",
    "prompts folder":         "outputs/equal_shares/prompts_native_r2v",
    "equal shares":           "outputs/equal_shares",
}


# ── Public interface ───────────────────────────────────────────────────────────

@dataclass
class ActionPlan:
    """A resolved direct operator request.

    ``intent``  — human-readable name, used for logging, formatting, and tests.
    ``steps``   — ordered list of (tool_name, args) pairs.  Each step is
                  executed by agent._execute_plan() in the order given; all
                  guards in tools.call() still apply.
    """
    intent: str
    steps: list[tuple[str, dict]] = field(default_factory=list)


def classify(
    latest_user: str,
    history: list[dict],
    cid: str,
    *,
    pending_calibration_path_fn: Callable[[list[dict], str], "str | None"],
    specialist_scope: bool,
    profile: str = "gpu",
) -> "ActionPlan | None":
    """Classify a direct operator request into a deterministic action plan.

    Returns an ActionPlan when the request maps unambiguously to a known safe
    tool or sequence of tools.  Returns None when the request should fall
    through to the normal model turn.

    Priority order (checked top to bottom; first match wins):
      1. ComfyUI stop      — safety action, always resolved
      2. JSONL repair      — evidence-required, catches emphatic "fix" requests
      3. Calibration cont. — evidence-required, routes to validator not batch
      4. List directory    — open file request with target identified
      5. Read file         — open file request with explicit path token
      6–9 (profile="cpu" only): relative list_dir, web_search, capabilities,
          list_memory

    Args:
        latest_user: the operator's current message (stripped).
        history: full conversation history including the current user message.
        cid: conversation id; empty string for ad-hoc (non-saved) turns.
        pending_calibration_path_fn: from agent.py — returns the exact JSONL
            path of the most recently failed/active calibration intake from
            same-chat tool evidence.  Signature: (history, cid) -> str | None.
        specialist_scope: True when the current message explicitly asks about
            ComfyUI/H3/Equal Shares specialist work.  Prevents calibration-
            continuation routing from triggering on a render-context turn.
        profile: "gpu" (default) or "cpu". Extra intents 6–9 run only on
            "cpu" (CPU-served or farm compact harness). GPU free-form is
            unchanged.
    """
    text = (latest_user or "").strip()
    if not text:
        return None

    # ── 1. ComfyUI / render stop ───────────────────────────────────────────
    # Safety action: no evidence required, no scope restriction.
    if _COMFYUI_STOP_RE.fullmatch(text):
        return ActionPlan(
            intent="comfyui_stop",
            steps=[("stop_all_comfyui", {})],
        )

    # ── 1b. Large creative/storyboard prompt packs (Backrooms-style) ───────
    # Deterministic ingest+export so the model cannot fall into CAP_IMAGE
    # render_story_image_batch with invented placeholders.
    import prompt_pack_production
    pack_source = text
    pack_path = prompt_pack_production.extract_pack_path(latest_user or text)
    if cid and pack_path and not managed_prompt_pack.is_prompt_pack(text):
        pack_source = pack_path.read_text(encoding="utf-8")
    full_prod = bool(cid and prompt_pack_production.wants_full_production(latest_user or ""))
    if cid and managed_prompt_pack.is_prompt_pack(pack_source):
        steps = [
            ("ingest_prompt_pack",
             {"text": pack_source, "allow_render": True} if full_prod else {"text": pack_source}),
            ("export_prompt_pack_outputs", {"export_all": True, "chunk_size": 24}),
        ]
        if full_prod:
            steps.append(("run_prompt_pack_production", {"operator_text": latest_user or ""}))
            return ActionPlan(intent="prompt_pack_production", steps=steps)
        return ActionPlan(intent="prompt_pack_ingest_export", steps=steps)
    if cid and full_prod:
        progress = managed_prompt_pack.load_progress(cid)
        if progress and progress.get("kind") == "prompt_pack":
            steps = []
            if managed_prompt_pack.has_incomplete_export(cid):
                steps.append(("export_prompt_pack_outputs", {"export_all": True, "chunk_size": 24}))
            steps.append(("run_prompt_pack_production", {"operator_text": latest_user or ""}))
            return ActionPlan(intent="prompt_pack_production", steps=steps)
    if cid and managed_prompt_pack.wants_explicit_render(text):
        progress = managed_prompt_pack.load_progress(cid)
        if progress and progress.get('kind') == 'prompt_pack' and not managed_prompt_pack.has_incomplete_export(cid):
            job = managed_prompt_pack.initial_frame_job(cid)
            receipt = managed_prompt_pack.anchor_receipt_path(cid)
            if receipt.is_file() and not re.search(r'\b(?:retry|again|regenerate)\b', text, re.I):
                import json
                prior = json.loads(receipt.read_text(encoding='utf-8'))
                return ActionPlan(intent='prompt_pack_render', steps=[
                    ('story_image_job_status', {k: prior[k] for k in ('story', 'pid', 'log') if k in prior}),
                ])
            if receipt.is_file():
                import json
                prior = json.loads(receipt.read_text(encoding='utf-8'))
                job['story'] += '_retry_' + str(prior['pid'])
                job['seed'] = 2
            return ActionPlan(intent='prompt_pack_render', steps=[
                ('ingest_prompt_pack', {'allow_render': True}),
                ('render_story_image', job),
            ])
    if cid and managed_prompt_pack.is_follow_up(text):
        progress = managed_prompt_pack.load_progress(cid)
        if progress and progress.get("kind") == "prompt_pack":
            import json
            prod = prompt_pack_production.load_production(cid)
            if prod and prod.get("status") in {"running", "queued", "error"}:
                return ActionPlan(intent="prompt_pack_production", steps=[
                    ("run_prompt_pack_production", {"operator_text": latest_user or ""}),
                ])
            steps: list[tuple[str, dict]] = []
            receipt = managed_prompt_pack.anchor_receipt_path(cid)
            if receipt.is_file() and not (prod and prod.get("status") == "complete"):
                prior = json.loads(receipt.read_text(encoding='utf-8'))
                return ActionPlan(intent='prompt_pack_render', steps=[
                    ('story_image_job_status', {k: prior[k] for k in ('story', 'pid', 'log') if k in prior}),
                ])
            if managed_prompt_pack.wants_explicit_render(text):
                steps.append(("ingest_prompt_pack", {"allow_render": True}))
            if managed_prompt_pack.has_incomplete_export(cid):
                steps.append(
                    ("export_prompt_pack_outputs",
                     {"export_all": True, "chunk_size": 24}),
                )
            else:
                steps.append(("prompt_pack_status", {}))
            return ActionPlan(intent="prompt_pack_continue", steps=steps)
    # ── 2. JSONL repair after a failed validation intake ───────────────────
    # Catches emphatic or direct repair phrasings ("fix it", "fix the
    # formatting error", "you were supposed to fix it — why didn't you?").
    # Requires a pending failed path in same-chat evidence; never guesses.
    if _JSONL_REPAIR_RE.search(text):
        path = pending_calibration_path_fn(history, cid)
        if path:
            return ActionPlan(
                intent="jsonl_repair",
                steps=[
                    ("repair_jsonl_format", {"path": path}),
                    ("validate_powerinfer_calibration", {"path": path}),
                ],
            )

    # ── 3. Calibration continuation using approved same-chat evidence ──────
    # "continue with the PowerInfer project using the JSON I approved" and
    # similar.  Routes to the calibration validator rather than batch/render
    # tools.  Requires evidence of a path; restricted to non-specialist turns
    # so a render-context continuation is not incorrectly routed here.
    if _CALIBRATION_CONTINUE_RE.search(text) and not specialist_scope:
        path = pending_calibration_path_fn(history, cid)
        if path:
            return ActionPlan(
                intent="calibration_continue",
                steps=[("validate_powerinfer_calibration", {"path": path})],
            )

    # ── 4. List directory ──────────────────────────────────────────────────
    # "show me the folder with the prompts", "list the files in X", etc.
    # Only resolves when a concrete target can be determined (alias or path).
    if _LIST_DIR_RE.search(text):
        folder = _resolve_folder(text)
        if folder:
            return ActionPlan(
                intent="list_dir",
                steps=[("list_dir", {"path": folder})],
            )

    # ── 5. Read file ───────────────────────────────────────────────────────
    # "read the file at X", "open C:\path\notes.txt", etc.
    # Only resolves when an explicit path token is present in the message.
    if _READ_FILE_RE.search(text):
        path = _extract_explicit_path(text)
        if path:
            return ActionPlan(
                intent="read_file",
                steps=[("read_file", {"path": path})],
            )

    # ── 6–9. CPU/farm-only extras (Layer B) ────────────────────────────────
    # After the five globals. Evidence-or-path still required. None on
    # ambiguity. Never write_file / run_code / start_batch_render /
    # render_story_image.
    if (profile or "gpu").strip().lower() == "cpu":
        # 6. Relative list_dir — compact 2026-09-04o missed this and spent
        # hops on list_tools(category="file_operations") before list_dir.
        if _LIST_DIR_RE.search(text):
            folder = _extract_relative_folder(text)
            if folder:
                return ActionPlan(
                    intent="list_dir",
                    steps=[("list_dir", {"path": folder})],
                )

        # 7. web_search — explicit "search the web / look up / google", no URL.
        if _WEB_SEARCH_RE.search(text) and not _URL_IN_TEXT_RE.search(text):
            query = _extract_web_search_query(text)
            if query:
                return ActionPlan(
                    intent="web_search",
                    steps=[("web_search", {"query": query})],
                )

        # 8. capabilities — sensory/tool inventory, no arguments.
        if _CAPABILITIES_RE.search(text):
            return ActionPlan(
                intent="capabilities",
                steps=[("capabilities", {})],
            )

        # 9. list_memory — remembered facts, no arguments.
        if _LIST_MEMORY_RE.search(text):
            return ActionPlan(
                intent="list_memory",
                steps=[("list_memory", {})],
            )

    return None


# ── Internal helpers ───────────────────────────────────────────────────────────

def _resolve_folder(text: str) -> "str | None":
    """Find a folder target from the operator message.

    Checks short-name aliases first (lower-case substring match), then falls
    back to an explicit path token.  Returns None if neither is found.
    """
    text_lower = text.lower()
    for alias, folder in _FOLDER_ALIASES.items():
        if alias in text_lower:
            return folder
    return _extract_explicit_path(text)


def _extract_explicit_path(text: str) -> "str | None":
    """Pull the first absolute- or dot-relative path token from the message."""
    m = _PATH_RE.search(text)
    if not m:
        return None
    p = m.group(0).rstrip(".,;:!?)")
    return p or None


def _extract_relative_folder(text: str) -> "str | None":
    """Bare folder name from a list-dir phrasing. None if ambiguous or unsafe."""
    m = _RELATIVE_FOLDER_RE.search(text or "")
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").strip().strip("`'\"").rstrip(".,;:!?")
    if not raw:
        return None
    if ".." in raw.replace("\\", "/").split("/"):
        return None
    if raw.lower() in _RELATIVE_FOLDER_STOPWORDS:
        return None
    return raw


def _extract_web_search_query(text: str) -> "str | None":
    """Query after an explicit web-search trigger. None if empty/ambiguous."""
    m = _WEB_SEARCH_QUERY_RE.search(text or "")
    if not m:
        return None
    query = " ".join((m.group(1) or "").split()).strip(" .,:;!?\"'")
    if not query or len(query) > 200:
        return None
    return query
