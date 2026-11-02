"""Ollama ``/api/chat`` shapes  <->  Anthropic Messages API shapes. Pure functions.

Covers the table in the 2026-11-02 audit:

* ``messages[role=system]``            -> top-level ``system`` (first one; later
                                          system notes become user text blocks so
                                          the transcript stays append-only)
* ``tools[].function``                 -> ``tools[].{name,description,input_schema}``
* assistant ``tool_calls`` (no id)     -> ``tool_use`` blocks with minted ids
* N x ``{"role":"tool"}`` messages     -> one user message of ``tool_result`` blocks
* ``format`` (json / schema)           -> ``output_config.format`` / system note
* ``options.*``, ``keep_alive``, ``think`` -> dropped (handled by the adapter)
* ``usage``                            -> Ollama telemetry keys

Nothing here imports the SDK, so these functions are unit-tested offline.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections import OrderedDict
from typing import Any

MINTED_ID_PREFIX = "toolu_gw_"
_RAW_BLOCK_CACHE_MAX = 64

# tool_use id -> the assistant content blocks (thinking + text + tool_use) the
# provider actually returned. Replayed verbatim for the assistant turn that is
# still waiting on its tool results, which is the one case where the API
# requires the original thinking blocks. Older turns are replayed as text +
# tool_use only, which is the "drop a leading run of thinking blocks" shape
# the API accepts.
_RAW_BLOCKS: "OrderedDict[str, list[dict]]" = OrderedDict()


def remember_raw_blocks(tool_use_ids: list[str], blocks: list[dict]) -> None:
    if not tool_use_ids or not blocks:
        return
    key = tool_use_ids[0]
    _RAW_BLOCKS[key] = [dict(b) for b in blocks]
    _RAW_BLOCKS.move_to_end(key)
    while len(_RAW_BLOCKS) > _RAW_BLOCK_CACHE_MAX:
        _RAW_BLOCKS.popitem(last=False)


def forget_raw_blocks() -> None:
    _RAW_BLOCKS.clear()


def mint_tool_use_id(message_index: int, call_index: int, name: str, arguments: Any) -> str:
    """Deterministic id for a call Ollama recorded without one."""
    seed = json.dumps([message_index, call_index, name, arguments],
                      sort_keys=True, default=str, ensure_ascii=False)
    return MINTED_ID_PREFIX + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


# ── tools ────────────────────────────────────────────────────────────────────────

def ollama_tools_to_anthropic(tools: list[dict] | None, *, cache_last: bool = False) -> list[dict]:
    out: list[dict] = []
    for tool in tools or []:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        schema = fn.get("parameters")
        if not isinstance(schema, dict) or not schema:
            schema = {"type": "object", "properties": {}}
        entry = {
            "name": str(fn["name"]),
            "description": str(fn.get("description") or "")[:4096],
            "input_schema": schema,
        }
        out.append(entry)
    if cache_last and out:
        out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


# ── messages ────────────────────────────────────────────────────────────────────

def _sniff_image_media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _image_blocks(images: Any) -> list[dict]:
    blocks: list[dict] = []
    for item in images or []:
        if isinstance(item, (bytes, bytearray)):
            raw = bytes(item)
            b64 = base64.b64encode(raw).decode("ascii")
        elif isinstance(item, str):
            b64 = item.strip()
            try:
                raw = base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4), validate=False)
            except Exception:
                raw = b""
        else:
            continue
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": _sniff_image_media_type(raw), "data": b64},
        })
    return blocks


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _call_parts(call: dict) -> tuple[str, dict, str | None]:
    fn = call.get("function") if isinstance(call, dict) else None
    if not isinstance(fn, dict):
        fn = {}
    name = str(fn.get("name") or "")
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"__invalid_tool_arguments__": args}
    if not isinstance(args, dict):
        args = {"__invalid_tool_arguments__": repr(args)}
    cid = call.get("id") if isinstance(call, dict) else None
    return name, args, (str(cid) if cid else None)


def _tool_result_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:
        return str(content)


def split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Lift the leading system message(s) out; keep the rest in order."""
    system_parts: list[str] = []
    rest: list[dict] = []
    leading = True
    for msg in messages or []:
        role = str(msg.get("role", ""))
        if role == "system" and leading:
            text = str(msg.get("content") or "")
            if text.strip():
                system_parts.append(text)
            continue
        leading = False
        rest.append(msg)
    return "\n\n".join(system_parts), rest


def ollama_messages_to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """Return ``(system_text, anthropic_messages)``.

    Rules:
    * consecutive same-role messages are merged into one message (content list)
    * mid-conversation ``system`` messages become ``[Operator note]`` user text
    * assistant ``tool_calls`` become ``tool_use`` blocks; ids are kept when the
      call carries one, minted otherwise
    * following ``role: tool`` messages are paired *in order* with those calls
      and emitted as ``tool_result`` blocks inside a single user message; a
      stray tool message with nothing to pair to becomes plain user text
    * the last assistant turn that still awaits tool results is replayed from
      the raw provider blocks when they are cached (thinking preserved)
    """
    system_text, rest = split_system(messages)
    out: list[dict] = []
    pending_ids: list[str] = []          # tool_use ids awaiting results, in order
    last_assistant_with_calls = -1       # index into ``rest``
    for idx, msg in enumerate(rest):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            last_assistant_with_calls = idx

    def _append(role: str, blocks: list[dict]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for idx, msg in enumerate(rest):
        role = str(msg.get("role", ""))
        content = msg.get("content")
        text = content if isinstance(content, str) else _tool_result_content(content) if content is not None else ""

        if role == "system":
            if text.strip():
                _append("user", [_text_block("[Operator note]\n" + text)])
            continue

        if role == "user":
            blocks = _image_blocks(msg.get("images"))
            if text.strip():
                blocks.append(_text_block(text))
            elif not blocks:
                continue
            pending_ids = []
            _append("user", blocks)
            continue

        if role == "assistant":
            calls = msg.get("tool_calls") or []
            ids: list[str] = []
            blocks: list[dict] = []
            if text.strip():
                blocks.append(_text_block(text.rstrip()))
            for cidx, call in enumerate(calls):
                name, args, cid = _call_parts(call)
                if not name:
                    continue
                cid = cid or mint_tool_use_id(idx, cidx, name, args)
                ids.append(cid)
                blocks.append({"type": "tool_use", "id": cid, "name": name, "input": args})
            if ids and idx == last_assistant_with_calls:
                raw = _RAW_BLOCKS.get(ids[0])
                if raw and _raw_matches(raw, ids):
                    blocks = [dict(b) for b in raw]
            pending_ids = list(ids)
            _append("assistant", blocks)
            continue

        if role == "tool":
            if pending_ids:
                cid = pending_ids.pop(0)
                _append("user", [{"type": "tool_result", "tool_use_id": cid,
                                  "content": text if text else "(empty result)"}])
            else:
                label = str(msg.get("name") or "tool")
                _append("user", [_text_block(f"[Result of {label}]\n{text}")])
            continue

        # Unknown role: keep the text as a user note rather than dropping it.
        if text.strip():
            _append("user", [_text_block(text)])

    # Strip empty text blocks and drop messages that ended up empty.
    cleaned: list[dict] = []
    for msg in out:
        blocks = [b for b in msg["content"]
                  if not (b.get("type") == "text" and not str(b.get("text", "")).strip())]
        if blocks:
            cleaned.append({"role": msg["role"], "content": blocks})
    if cleaned and cleaned[-1]["role"] == "assistant":
        raise ValueError("conversation ends with an assistant turn; the Messages API "
                         "does not accept assistant prefill")
    return system_text, cleaned


def _raw_matches(raw: list[dict], ids: list[str]) -> bool:
    raw_ids = [b.get("id") for b in raw if b.get("type") == "tool_use"]
    return raw_ids == ids


# ── structured output ────────────────────────────────────────────────────────────

def response_format_to_output_config(response_format: dict | str | None) -> tuple[dict | None, str]:
    """Return ``(output_config_or_None, extra_system_note)``."""
    if not response_format:
        return None, ""
    if isinstance(response_format, dict):
        return {"format": {"type": "json_schema", "schema": response_format}}, ""
    if str(response_format).lower() == "json":
        return None, "Respond with a single JSON object and nothing else."
    return None, ""


# ── response ─────────────────────────────────────────────────────────────────────

def blocks_to_ollama_calls(blocks: list[Any]) -> list[dict]:
    calls: list[dict] = []
    for block in blocks or []:
        btype = _get(block, "type")
        if btype != "tool_use":
            continue
        args = _get(block, "input")
        if not isinstance(args, dict):
            args = {"__invalid_tool_arguments__": repr(args)}
        calls.append({"id": str(_get(block, "id") or ""),
                      "function": {"name": str(_get(block, "name") or ""), "arguments": args}})
    return calls


def blocks_to_text(blocks: list[Any]) -> str:
    return "".join(str(_get(b, "text") or "") for b in blocks or [] if _get(b, "type") == "text")


def usage_to_telemetry(usage: Any, *, total_ns: int, eval_ns: int, model: str,
                       stop_reason: str | None) -> dict:
    inp = int(_get(usage, "input_tokens") or 0)
    cache_read = int(_get(usage, "cache_read_input_tokens") or 0)
    cache_write = int(_get(usage, "cache_creation_input_tokens") or 0)
    out = int(_get(usage, "output_tokens") or 0)
    return {
        "eval_count": out,
        "prompt_eval_count": inp + cache_read + cache_write,
        "total_duration": int(total_ns),
        "eval_duration": int(eval_ns),
        "gateway": {
            "model": model,
            "stop_reason": stop_reason,
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
        },
    }


def serialize_blocks(blocks: list[Any]) -> list[dict]:
    """SDK content blocks -> plain dicts safe to replay as request params."""
    out: list[dict] = []
    for block in blocks or []:
        if isinstance(block, dict):
            out.append(dict(block))
            continue
        dump = getattr(block, "model_dump", None)
        if callable(dump):
            try:
                out.append(dump(exclude_none=True))
                continue
            except Exception:
                pass
        out.append({k: v for k, v in vars(block).items() if not k.startswith("_")})
    return out


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
