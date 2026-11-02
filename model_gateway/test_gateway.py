#!/usr/bin/env python3
"""Live verification of the hybrid router. Needs real servers; nothing is mocked.

    python model_gateway/test_gateway.py              # all three checks
    python model_gateway/test_gateway.py --skip-cloud # only the local checks
    python model_gateway/test_gateway.py --skip-local

Checks (each prints PASS / FAIL / SKIP and the script exits non-zero on FAIL):

  A  local      a short prompt answered by the CPU Ollama tier (11435) through
                ollama_client, with the GPU server's /api/ps unchanged
  B  cloud      a heavy-reasoning prompt: router.decide() must pick the
                Anthropic backend, the stream must complete through
                ollama_client, and no request may reach 11434 /api/chat
                (GPU /api/ps is compared before and after as well)
  C  tools      the same tool schema and the same JSON schema sent to both
                targets; the returned arguments / JSON are validated against
                the schema with a small stdlib validator

Set MODEL_GATEWAY_CLOUD=1 and ANTHROPIC_API_KEY (model_gateway/.env) for B/C-cloud.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

import model_gateway as gw  # noqa: E402
import router  # noqa: E402
import ollama_client as oll  # noqa: E402

LOGIC_PROMPT = (
    "Architect a plan to refactor a local AI agent's routing layer so it can "
    "debug multi-step tool failures end-to-end. Compare two approaches, list the "
    "integration risks, and give a three-step implementation plan. Keep it under "
    "150 words."
)
SIMPLE_PROMPT = "Reply with exactly one short sentence: what is 7 times 6?"

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["city", "unit"],
        },
    },
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "needs_operator_decision": {"type": "boolean"},
    },
    "required": ["goal", "steps", "needs_operator_decision"],
    "additionalProperties": False,
}

_TYPES = {"string": str, "boolean": bool, "integer": int, "number": (int, float),
          "array": list, "object": dict}


def validate(value, schema: dict, path: str = "$") -> list[str]:
    """Tiny JSON-schema subset validator: type, required, enum, items, minItems,
    properties, additionalProperties. Enough for this project's tool schemas."""
    errors: list[str] = []
    t = schema.get("type")
    if t and t in _TYPES:
        expected = _TYPES[t]
        ok = isinstance(value, expected) and not (t in ("integer", "number") and isinstance(value, bool))
        if not ok:
            return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, sub in value.items():
            if key in props:
                errors.extend(validate(sub, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: additional property")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return errors


def gpu_resident() -> list[str] | None:
    return router._running_models(router.GPU_HOST) if router.up(router.GPU_HOST) else None


class Guard:
    """Fails the run if anything posts to the GPU server's /api/chat."""

    def __init__(self):
        self.hits: list[str] = []
        self._orig = urllib.request.urlopen

    def __enter__(self):
        def wrapped(req, *a, **kw):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if router.GPU_HOST in url and url.endswith("/api/chat"):
                self.hits.append(url)
            return self._orig(req, *a, **kw)
        urllib.request.urlopen = wrapped
        oll.urllib.request.urlopen = wrapped
        return self

    def __exit__(self, *exc):
        urllib.request.urlopen = self._orig
        oll.urllib.request.urlopen = self._orig


def run_stream(route, messages, tools=None):
    text, calls, end = [], [], None
    for piece in oll.chat_stream(messages, model=route.model, options=route.options(),
                                 host=route.host, tools=tools, keep_alive="0"):
        if isinstance(piece, oll.ToolCall):
            calls = piece.calls
        elif isinstance(piece, oll.StreamEnd):
            end = piece
        elif isinstance(piece, str):
            text.append(piece)
    return "".join(text), calls, end


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, name: str, status: str, note: str = ""):
        self.rows.append((name, status, note))
        print(f"  [{status:<4}] {name}{(': ' + note) if note else ''}", flush=True)

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for _, s, _ in self.rows)


def check_local(rep: Report, cpu_model: str | None) -> None:
    print("\nA. local tier (CPU Ollama)")
    if not router.up(router.CPU_HOST):
        rep.add("A local", "SKIP", f"CPU Ollama {router.CPU_HOST} is down")
        return
    have = router._tags(router.CPU_HOST)
    model = cpu_model or router._installed_variant(have, router.FALLBACK_REASONING_MODEL) or (have[0] if have else None)
    if not model:
        rep.add("A local", "SKIP", "no model on the CPU tier")
        return
    before = gpu_resident()
    t0 = time.time()
    try:
        text, _ = oll.chat([{"role": "user", "content": SIMPLE_PROMPT}], model=model,
                           host=router.CPU_HOST, timeout=300, keep_alive="0",
                           options=dict(router.CPU_OPTIONS, num_ctx=4096))
    except Exception as exc:
        rep.add("A local", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
        return
    after = gpu_resident()
    ok = bool(text.strip())
    rep.add("A local answer", "PASS" if ok else "FAIL",
            f"{model} on {router.CPU_HOST} in {time.time() - t0:.1f}s -> {text.strip()[:60]!r}")
    rep.add("A GPU /api/ps unchanged", "PASS" if before == after else "FAIL", f"{before} -> {after}")


def check_cloud(rep: Report) -> None:
    print("\nB. cloud tier (Anthropic API via router.decide)")
    cfg = gw.load_config()
    if not cfg.cloud_enabled or not cfg.credential_present:
        rep.add("B cloud", "SKIP", "set MODEL_GATEWAY_CLOUD=1 and ANTHROPIC_API_KEY")
        return
    before = gpu_resident()
    route = router.decide("auto", prompt=LOGIC_PROMPT, ensure_gpu_evicted=False)
    if route.backend != "anthropic":
        rep.add("B decide picks anthropic", "FAIL", f"tier={route.tier} backend={route.backend}: {route.reason}")
        return
    rep.add("B decide picks anthropic", "PASS", f"{route.model} ({route.detail['gateway']['alias']}) — {route.reason[:80]}")
    t0 = time.time()
    with Guard() as guard:
        try:
            text, calls, end = run_stream(route, [
                {"role": "system", "content": "You are a concise systems architect."},
                {"role": "user", "content": LOGIC_PROMPT},
            ])
        except oll.OllamaModelFailure as exc:
            rep.add("B cloud stream", "FAIL", f"{str(exc)[:200]} (fallback would now run locally)")
            return
    after = gpu_resident()
    tel = (end.telemetry if end else {}).get("gateway", {})
    rep.add("B cloud stream", "PASS" if text.strip() else "FAIL",
            f"{tel.get('model')} {time.time() - t0:.1f}s in={tel.get('input_tokens')} "
            f"out={tel.get('output_tokens')} cache_read={tel.get('cache_read_input_tokens')} "
            f"stop={tel.get('stop_reason')}")
    rep.add("B no /api/chat to GPU host", "PASS" if not guard.hits else "FAIL", str(guard.hits))
    rep.add("B GPU /api/ps unchanged", "PASS" if before == after else "FAIL", f"{before} -> {after}")


def check_tools(rep: Report, cpu_model: str | None, skip_local: bool, skip_cloud: bool) -> None:
    print("\nC. tool calling + JSON schema on both targets")
    tool_prompt = "What is the weather in Lisbon right now? Use the tool; answer in celsius."
    json_prompt = ("Return a JSON plan for backing up a folder: goal, 2-3 steps, and whether an "
                   "operator decision is needed. JSON only.")
    targets: list[tuple[str, str, str, dict]] = []
    if not skip_local and router.up(router.CPU_HOST):
        have = router._tags(router.CPU_HOST)
        model = cpu_model or router._installed_variant(have, router.FALLBACK_REASONING_MODEL) or (have[0] if have else None)
        if model:
            targets.append(("local", router.CPU_HOST, model,
                            dict(router.CPU_OPTIONS, num_ctx=4096, temperature=0)))
    cfg = gw.load_config()
    if not skip_cloud and cfg.cloud_enabled and cfg.credential_present:
        targets.append(("cloud", cfg.host(), cfg.fast.model, {"effort": "low", "max_tokens": 1024}))
    if not targets:
        rep.add("C tools", "SKIP", "no target available")
        return
    for label, host, model, opts in targets:
        try:
            text, calls = oll.chat([{"role": "user", "content": tool_prompt}], model=model,
                                   host=host, options=opts, tools=[WEATHER_TOOL], timeout=300,
                                   keep_alive="0")
        except Exception as exc:
            rep.add(f"C {label} tool call", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
            continue
        if not calls:
            rep.add(f"C {label} tool call", "FAIL", f"no tool_calls; text={text[:80]!r}")
        else:
            args = calls[0]["function"]["arguments"]
            errs = validate(args, WEATHER_TOOL["function"]["parameters"])
            rep.add(f"C {label} tool call", "PASS" if not errs else "FAIL",
                    f"{calls[0]['function']['name']}({json.dumps(args)}) {errs or ''}")
        try:
            text, _ = oll.chat([{"role": "user", "content": json_prompt}], model=model,
                               host=host, options=opts, response_format=PLAN_SCHEMA, timeout=300,
                               keep_alive="0")
            data = json.loads(text)
            errs = validate(data, PLAN_SCHEMA)
            rep.add(f"C {label} json schema", "PASS" if not errs else "FAIL",
                    f"{json.dumps(data)[:100]} {errs or ''}")
        except Exception as exc:
            rep.add(f"C {label} json schema", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--skip-cloud", action="store_true")
    ap.add_argument("--cpu-model", default=None, help="Ollama tag on the CPU tier (default: Huihui 8B)")
    args = ap.parse_args(argv)
    print(f"model_gateway live test — GPU {router.GPU_HOST} / CPU {router.CPU_HOST} / "
          f"cloud {'on' if os.environ.get('MODEL_GATEWAY_CLOUD') == '1' else 'off'}")
    rep = Report()
    if not args.skip_local:
        check_local(rep, args.cpu_model)
    if not args.skip_cloud:
        check_cloud(rep)
    check_tools(rep, args.cpu_model, args.skip_local, args.skip_cloud)
    print("\nsummary:", "FAIL" if rep.failed else "OK",
          f"({sum(s == 'PASS' for _, s, _ in rep.rows)} pass, "
          f"{sum(s == 'FAIL' for _, s, _ in rep.rows)} fail, "
          f"{sum(s == 'SKIP' for _, s, _ in rep.rows)} skip)")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
