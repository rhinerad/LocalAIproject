#!/usr/bin/env python3
"""Prepare, capture, and verify a strict two-turn TurboSparse tool-call gate.

This utility never starts PowerInfer or Ollama and never executes the proposed
tool calls.  Capture talks only to an already-running loopback completion
endpoint.  The test fails closed on prose, Markdown, malformed JSON, invented
tool output, or a wrong next action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SYSTEM = """You are a local tool-using agent. Reply with exactly one valid JSON object and nothing else.
Do not use Markdown fences, prose, or explanations. Never invent a tool result.
Available tools:
- search_files: {\"path\": string, \"query\": string}
- read_file: {\"path\": string, \"max_lines\": integer}
For a request to search files, call search_files before claiming any result."""
TURN1_USER = "Search my local files for a Python script."
OBSERVATION = """TOOL_RESULT search_files:
A:\\workspace\\scripts\\cleanup.py
A:\\workspace\\local_agent\\agent.py
A:\\workspace\\README.md
WARNING: Access denied: A:\\workspace\\private"""
TURN2_USER = "Find the script most likely to be the main local agent entry point and inspect its first 80 lines."
EXPECTED_ONE = {"tool_calls": [{"name": "search_files", "arguments": {"path": ".", "query": "*.py"}}]}
EXPECTED_TWO = {"tool_calls": [{"name": "read_file", "arguments": {"path": "A:\\workspace\\local_agent\\agent.py", "max_lines": 80}}]}


# Generic JSON object GBNF (any keys/values). Not the expected tool_calls payload.
JSON_OBJECT_GBNF = (
    "root ::= object\n"
    'object ::= "{" ws pair (ws "," ws pair)* ws "}"\n'
    'pair ::= string ws ":" ws value\n'
    'array ::= "[" ws (value (ws "," ws value)*)? ws "]"\n'
    'value ::= object | array | string | number | "true" | "false" | "null"\n'
    'string ::= "\\"" ([^"\\\\\\n\\r] | "\\\\" ["\\\\/bfnrt])* "\\""\n'
    'number ::= "-"? [0-9]+ ("." [0-9]+)?\n'
    'ws ::= "" | " "\n'
)



def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def render(messages: list[tuple[str, str]]) -> str:
    """Render the exact verified local checkpoint ChatML contract."""
    out: list[str] = []
    for role, content in messages:
        if role == "system":
            out.append(f"<|im_start|>system\n{content}<|im_end|>\n")
        elif role == "user":
            out.append(f"<|im_start|>user\n{content}<|im_end|>\n<|im_start|>assistant\n")
        elif role == "assistant":
            out.append(f"{content}<|im_end|>\n")
        else:
            raise ValueError(f"unsupported role {role!r}")
    return "".join(out)


def check_exact(text: str, expected: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        return {"passed": False, "reason": f"invalid_json: {exc.msg}"}
    if value != expected:
        return {"passed": False, "reason": "wrong_tool_call", "parsed": value, "expected": expected}
    return {"passed": True, "parsed": value}


def load_prompt_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "turbosparse-prompt-contract-v1" or value.get("status") != "verified_local_contract":
        raise ValueError("prompt contract is not a verified TurboSparse receipt")
    digest = str(value.get("chat_template_sha256") or "")
    if len(digest) != 64:
        raise ValueError("prompt contract has no valid template SHA-256")
    return value


def packet(prompt_contract: dict[str, Any]) -> dict[str, Any]:
    first_prompt = render([("system", SYSTEM), ("user", TURN1_USER)])
    return {
        "schema": "turbosparse-agentic-quality-gate-v1",
        "created_at": now(),
        "status": "prepared",
        "prompt_contract_sha256": prompt_contract["chat_template_sha256"],
        "settings": {"temperature": 0, "top_p": 1, "n_predict": 256, "stop": ["<|im_end|>", "</s>", "<|im_start|>"], "grammar": JSON_OBJECT_GBNF},
        "turns": [
            {"id": "search_then_act", "prompt": first_prompt, "expected": EXPECTED_ONE, "response": "", "evaluation": None},
            {"id": "grounded_next_step", "prompt": "", "observation": OBSERVATION, "expected": EXPECTED_TWO, "response": "", "evaluation": None},
        ],
        "packet_sha256": hashlib.sha256(first_prompt.encode("utf-8")).hexdigest(),
    }


def completion(endpoint: str, prompt: str, settings: dict[str, Any]) -> str:
    body = {"prompt": prompt, "n_predict": settings["n_predict"], "temperature": settings["temperature"], "top_p": settings["top_p"], "cache_prompt": False, "stream": False, "stop": settings["stop"], "grammar": settings.get("grammar") or JSON_OBJECT_GBNF}
    request = urllib.request.Request(endpoint.rstrip("/") + "/completion", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    return str(parsed.get("content", ""))


def capture(value: dict[str, Any], endpoint: str) -> dict[str, Any]:
    result = json.loads(json.dumps(value))
    one = result["turns"][0]
    one["response"] = completion(endpoint, one["prompt"], result["settings"])
    one["evaluation"] = check_exact(one["response"], one["expected"])
    if not one["evaluation"]["passed"]:
        result["status"] = "failed_turn_1"
        return result
    two = result["turns"][1]
    two["prompt"] = render([("system", SYSTEM), ("user", TURN1_USER), ("assistant", one["response"].strip()), ("user", f"{OBSERVATION}\n\n{TURN2_USER}")])
    two["response"] = completion(endpoint, two["prompt"], result["settings"])
    two["evaluation"] = check_exact(two["response"], two["expected"])
    result["status"] = "passed" if two["evaluation"]["passed"] else "failed_turn_2"
    result["captured_at"] = now()
    result["endpoint"] = endpoint
    return result


def write_once(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite quality-gate evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--out", required=True, type=Path)
    prep.add_argument("--prompt-contract", required=True, type=Path)
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("--packet", required=True, type=Path)
    capture_parser.add_argument("--endpoint", required=True)
    capture_parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        value = packet(load_prompt_contract(args.prompt_contract))
    else:
        value = capture(json.loads(args.packet.read_text(encoding="utf-8")), args.endpoint)
    write_once(args.out, value)
    print(json.dumps({"status": value["status"], "out": str(args.out)}, indent=2))
    return 0 if value["status"] in {"prepared", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
