#!/usr/bin/env python3
"""Turn-1 template-mismatch probes for TurboSparse Q4 (diagnostic only).

Does not start the server, does not flip accepted, does not write the registry.
Pass = parsed JSON exactly equals EXPECTED_ONE from turbosparse_agentic_quality_gate.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import turbosparse_agentic_quality_gate as g

SYSTEM = g.SYSTEM
TURN1 = g.TURN1_USER
EXPECTED = g.EXPECTED_ONE
EXPECTED_COMPACT = json.dumps(EXPECTED, separators=(",", ":"))

# Exact payload GBNF (forbids empty {}). Diagnostic only, not a registry cheat.
EXACT_TOOL_CALLS_GBNF = (
    'root ::= exact\n'
    'exact ::= "{\\"tool_calls\\":[{\\"name\\":\\"search_files\\",\\"arguments\\":{\\"path\\":\\".\\",\\"query\\":\\"*.py\\"}}]}"\n'
)

STOP = ["<|im_end|>", "</s>", "<|im_start|>", "[INST]", "[/INST]"]

DEFAULT_OUT = Path(
    r"A:\PowerInferModels\turbosparse-mistral-instruct"
    r"\turbosparse-approved-20260902-182522\validation"
    r"\template_mismatch_probes.2026-09-03.json"
)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chatml_prompt() -> str:
    return g.render([("system", SYSTEM), ("user", TURN1)])


def mistral_prompt() -> str:
    return f"[INST]<<SYS>>{SYSTEM}<</SYS>>\n\n{TURN1} [/INST]"


def mistral_fewshot_prompt() -> str:
    return (
        f"[INST]<<SYS>>{SYSTEM}<</SYS>>\n\n{TURN1} [/INST] {EXPECTED_COMPACT} "
        f"</s>[INST] {TURN1} [/INST]"
    )


def completion(endpoint: str, prompt: str, grammar: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "prompt": prompt,
        "n_predict": 256,
        "temperature": 0,
        "top_p": 1,
        "cache_prompt": False,
        "stream": False,
        "stop": STOP,
    }
    if grammar:
        body["grammar"] = grammar
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/completion",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    content = str(parsed.get("content", ""))
    eval_ = g.check_exact(content, EXPECTED)
    return {
        "content": content,
        "evaluation": eval_,
        "passed": bool(eval_.get("passed")),
        "stop_reason": parsed.get("stop"),
        "tokens_predicted": parsed.get("tokens_predicted"),
        "tokens_evaluated": parsed.get("tokens_evaluated"),
        "timings": parsed.get("timings"),
    }


def write_once(path: Path, value: dict[str, Any]) -> Path:
    if path.exists():
        alt = path.with_name(path.stem + ".b" + path.suffix)
        if alt.exists():
            raise FileExistsError(f"refusing to overwrite {path} or {alt}")
        path = alt
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8080")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--include-c5", action="store_true", default=True)
    args = parser.parse_args()

    probes = [
        {
            "id": "C1",
            "name": "official_chatml_no_grammar",
            "prompt": chatml_prompt(),
            "grammar": None,
            "note": "control: official ChatML SYSTEM+TURN1, no grammar",
        },
        {
            "id": "C2",
            "name": "mistral_inst_no_grammar",
            "prompt": mistral_prompt(),
            "grammar": None,
            "note": "Mistral [INST]<<SYS>>SYSTEM<</SYS>>\\n\\nTURN1 [/INST], no grammar",
        },
        {
            "id": "C3",
            "name": "mistral_inst_exact_tool_calls_gbnf",
            "prompt": mistral_prompt(),
            "grammar": EXACT_TOOL_CALLS_GBNF,
            "note": "same as C2 with exact-tool_calls GBNF requiring EXPECTED compact JSON; forbids {}; diagnostic only, not registry cheat",
        },
        {
            "id": "C4",
            "name": "mistral_fewshot_exact_json_no_grammar",
            "prompt": mistral_fewshot_prompt(),
            "grammar": None,
            "note": "Mistral few-shot with exact EXPECTED JSON as assistant example then TURN1, no grammar",
        },
    ]
    if args.include_c5:
        probes.append(
            {
                "id": "C5",
                "name": "official_chatml_exact_tool_calls_gbnf",
                "prompt": chatml_prompt(),
                "grammar": EXACT_TOOL_CALLS_GBNF,
                "note": "optional: official ChatML + exact-tool_calls GBNF",
            }
        )

    results = []
    for spec in probes:
        record: dict[str, Any] = {
            "id": spec["id"],
            "name": spec["name"],
            "note": spec["note"],
            "prompt": spec["prompt"],
            "grammar": spec["grammar"],
            "temperature": 0,
            "n_predict": 256,
            "stop": STOP,
        }
        try:
            got = completion(args.endpoint, spec["prompt"], spec["grammar"])
            record.update(got)
        except Exception as exc:
            record["passed"] = False
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["evaluation"] = {"passed": False, "reason": "request_failed"}
        results.append(record)
        print(json.dumps({
            "id": record["id"],
            "passed": record.get("passed"),
            "eval": record.get("evaluation"),
            "snippet": (record.get("content") or record.get("error") or "")[:240],
        }, ensure_ascii=False))

    any_pass = any(r.get("passed") for r in results)
    c3_pass = next((r.get("passed") for r in results if r["id"] == "C3"), False)
    c4_pass = next((r.get("passed") for r in results if r["id"] == "C4"), False)
    payload = {
        "schema": "turbosparse-template-mismatch-probes-v1",
        "created_at": now(),
        "endpoint": args.endpoint,
        "expected": EXPECTED,
        "expected_compact": EXPECTED_COMPACT,
        "pass_rule": "parsed JSON exactly equals EXPECTED_ONE",
        "any_pass": any_pass,
        "c3_pass": c3_pass,
        "c4_pass": c4_pass,
        "probes": results,
        "notes": [
            "C3 exact GBNF is diagnostic only and is not a registry cheat.",
            "Prior official GBNF was generic JSON allowing empty {}.",
            "Baked template is ChatML, not [INST].",
            "Did not write production_models.json. Did not flip accepted.",
            "20260830b parked: untouched.",
        ],
    }
    written = write_once(args.out, payload)
    print(json.dumps({"out": str(written), "any_pass": any_pass, "c3_pass": c3_pass, "c4_pass": c4_pass}, indent=2))
    return 0 if any_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
