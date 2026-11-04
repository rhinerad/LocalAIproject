#!/usr/bin/env python3
"""Live verification of the plan-only gateway. Needs real servers; nothing is mocked.

    python model_gateway/test_gateway.py              # all three checks
    python model_gateway/test_gateway.py --skip-cloud # only the local checks
    python model_gateway/test_gateway.py --skip-local

Checks (each prints PASS / FAIL / SKIP and the script exits non-zero on FAIL):

  A  local      a short prompt answered by the CPU Ollama tier (11435) through
                ollama_client, with the GPU server's /api/ps unchanged
  B  plan       a heavy-reasoning prompt: router.decide() must return a LOCAL
                Decision (backend ollama) flagged needs_cloud_plan;
                model_gateway.request_plan() must return non-empty text with
                zero tool calls in the cloud response; GPU /api/ps compared as
                a set before/after; no request may reach 11434 /api/chat
  C  tools      the local tier only: a tool-calling prompt and a JSON-schema
                prompt, validated against the schema with a small validator

Set MODEL_GATEWAY_CLOUD=1 and ANTHROPIC_API_KEY (model_gateway/.env) for B.
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


def gpu_resident() -> set[str] | None:
    """Resident GPU models as a set: Ollama's /api/ps order is not stable."""
    if not router.up(router.GPU_HOST):
        return None
    names = router._running_models(router.GPU_HOST)
    return None if names is None else set(names)


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


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, name: str, status: str, note: str = ""):
        self.rows.append((name, status, note))
        print(f"  [{status:<4}] {name}{(': ' + note) if note else ''}", flush=True)

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for _, s, _ in self.rows)


def _cpu_model(cpu_model: str | None) -> str | None:
    have = router._tags(router.CPU_HOST)
    return cpu_model or router._installed_variant(have, router.FALLBACK_REASONING_MODEL) \
        or (have[0] if have else None)


def check_local(rep: Report, cpu_model: str | None) -> None:
    print("\nA. local tier (CPU Ollama)")
    if not router.up(router.CPU_HOST):
        rep.add("A local", "SKIP", f"CPU Ollama {router.CPU_HOST} is down")
        return
    model = _cpu_model(cpu_model)
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
    rep.add("A local answer", "PASS" if text.strip() else "FAIL",
            f"{model} on {router.CPU_HOST} in {time.time() - t0:.1f}s -> {text.strip()[:60]!r}")
    rep.add("A GPU /api/ps unchanged", "PASS" if before == after else "FAIL", f"{before} -> {after}")


def check_plan(rep: Report) -> None:
    print("\nB. plan-only cloud gateway (router.decide flag + request_plan)")
    cfg = gw.load_config()
    if not cfg.planning_available:
        rep.add("B plan", "SKIP", "set MODEL_GATEWAY_CLOUD=1 and ANTHROPIC_API_KEY")
        return
    before = gpu_resident()
    route = router.decide("auto", prompt=LOGIC_PROMPT, ensure_gpu_evicted=False)
    local_ok = route.backend in ("ollama", "powerinfer", "farm") and route.tier in ("gpu", "cpu", "farm")
    rep.add("B decide stays local", "PASS" if local_ok else "FAIL",
            f"tier={route.tier} backend={route.backend} model={route.model} — {route.reason[:70]}")
    flagged = bool((route.detail or {}).get("needs_cloud_plan"))
    rep.add("B decide flags needs_cloud_plan", "PASS" if flagged else "FAIL",
            json.dumps((route.detail or {}).get("cloud_plan") or {}))
    if not flagged:
        return
    t0 = time.time()
    with Guard() as guard:
        plan = gw.request_plan(LOGIC_PROMPT, "", ["read_file", "list_dir", "search_docs"])
    after = gpu_resident()
    snap = gw.status_snapshot(cfg)
    last = snap.get("last_plan") or {}
    tel = last.get("telemetry") or {}
    if plan:
        rep.add("B request_plan returns text", "PASS",
                f"{last.get('model')} {time.time() - t0:.1f}s chars={len(plan)} "
                f"in={tel.get('input_tokens')} out={tel.get('output_tokens')} "
                f"stop={last.get('stop_reason')}")
        rep.add("B no tool calls in cloud response",
                "PASS" if int(last.get("tool_calls") or 0) == 0 else "FAIL",
                str(last.get("tool_calls")))
        print("      plan preview: " + plan.replace("\n", " | ")[:160])
    else:
        fb = snap.get("last_fallback") or {}
        rep.add("B request_plan returns text", "FAIL",
                f"None ({fb.get('kind')}: {fb.get('detail')}) — the turn would continue locally")
    rep.add("B no /api/chat to GPU host", "PASS" if not guard.hits else "FAIL", str(guard.hits))
    rep.add("B GPU /api/ps unchanged (set compare)", "PASS" if before == after else "FAIL",
            f"{before} -> {after}")


def check_tools(rep: Report, cpu_model: str | None) -> None:
    print("\nC. local tool calling + JSON schema (CPU Ollama)")
    if not router.up(router.CPU_HOST):
        rep.add("C tools", "SKIP", f"CPU Ollama {router.CPU_HOST} is down")
        return
    model = _cpu_model(cpu_model)
    if not model:
        rep.add("C tools", "SKIP", "no model on the CPU tier")
        return
    opts = dict(router.CPU_OPTIONS, num_ctx=4096, temperature=0)
    tool_prompt = "What is the weather in Lisbon right now? Use the tool; answer in celsius."
    json_prompt = ("Return a JSON plan for backing up a folder: goal, 2-3 steps, and whether an "
                   "operator decision is needed. JSON only.")
    try:
        text, calls = oll.chat([{"role": "user", "content": tool_prompt}], model=model,
                               host=router.CPU_HOST, options=opts, tools=[WEATHER_TOOL],
                               timeout=300, keep_alive="0")
        if not calls:
            rep.add("C local tool call", "FAIL", f"no tool_calls; text={text[:80]!r}")
        else:
            args = calls[0]["function"]["arguments"]
            errs = validate(args, WEATHER_TOOL["function"]["parameters"])
            rep.add("C local tool call", "PASS" if not errs else "FAIL",
                    f"{calls[0]['function']['name']}({json.dumps(args)}) {errs or ''}")
    except Exception as exc:
        rep.add("C local tool call", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
    try:
        text, _ = oll.chat([{"role": "user", "content": json_prompt}], model=model,
                           host=router.CPU_HOST, options=opts, response_format=PLAN_SCHEMA,
                           timeout=300, keep_alive="0")
        data = json.loads(text)
        errs = validate(data, PLAN_SCHEMA)
        rep.add("C local json schema", "PASS" if not errs else "FAIL",
                f"{json.dumps(data)[:100]} {errs or ''}")
    except Exception as exc:
        rep.add("C local json schema", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--skip-cloud", action="store_true")
    ap.add_argument("--cpu-model", default=None, help="Ollama tag on the CPU tier (default: Huihui 8B)")
    args = ap.parse_args(argv)
    cfg = gw.load_config()
    print(f"model_gateway live test (plan-only) — GPU {router.GPU_HOST} / CPU {router.CPU_HOST} / "
          f"cloud planning {'on' if cfg.planning_available else 'off'}")
    rep = Report()
    if not args.skip_local:
        check_local(rep, args.cpu_model)
    if not args.skip_cloud:
        check_plan(rep)
    if not args.skip_local:
        check_tools(rep, args.cpu_model)
    print("\nsummary:", "FAIL" if rep.failed else "OK",
          f"({sum(s == 'PASS' for _, s, _ in rep.rows)} pass, "
          f"{sum(s == 'FAIL' for _, s, _ in rep.rows)} fail, "
          f"{sum(s == 'SKIP' for _, s, _ in rep.rows)} skip)")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
