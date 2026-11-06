# 2026-09-05ce — Instructor library eval: skip for local_agent

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05ce**.

Research only. No `router.py` / `tools.py` / `agent.py` edits. No
install. Library: [jxnl/instructor](https://github.com/jxnl/instructor)
(now 567-labs/instructor, v1.16.1).

**Recommendation: skip-because** catalog drowning and wrong-tool
selection are advertisement/routing problems, not missing Pydantic
extraction; Instructor overlaps what we already do on the native Ollama
path; and the install pulls a second HTTP stack (`openai>=2`) that does
not match `ollama_client.py`.

## What Instructor actually does

It patches an **OpenAI-compatible** `chat.completions.create` so
`response_model=SomePydanticModel` returns a validated instance. On
schema miss it **retries** the LLM with the validation error. Ollama
support is documented (`from_provider("ollama/llama3.2")` or
`OpenAI(base_url="http://localhost:11434/v1")` + `Mode.JSON` /
`Mode.TOOLS`). That is **output extraction** (turn prose/JSON into a
typed object). It is not a tool-catalog curator and not a router.

Official Ollama path still depends on the OpenAI Python SDK
(`openai>=2.0.0,<3` is a hard requirement in `pyproject.toml` even when
talking to localhost). Also: pydantic 2.8+, tenacity, rich, typer,
jinja2, aiohttp, jiter, docstring-parser. No optional extra is needed
for Ollama, but the OpenAI client is not optional.

Their own README: “Use Instructor for fast extraction, reach for
PydanticAI when you need agents.”

## Catalog drowning / wrong tool (2026-09-05bc / bn)

bc measured Huihui-14B / Coder picking **`fetch_url`** (or DeepSeek
**`see_image`**) for “first markdown heading in
`local_agent/README.md`” when advertised **68** tools. gpt-oss-20b
picked `read_file`. The failure is **which function the model selects
from a drowning catalog**, not malformed JSON after the fact.

bn’s fix was:

1. Advertise `gpu_core` (`CORE_DIRECT_TOOLS`, plus `comfy_*` only on
   Comfy prompts) on farm-down tool GPU fallback.
2. Stop estimating schema cost as `len(json)/3.4`; use measured 60
   tokens/schema so 14B is not falsely demoted to 8B.

Live: Huihui-14B then called `read_file` (case 1a) and
`comfy_workflow` (case 4).

Instructor cannot shrink the advertised list, cannot fix the 16k
estimator, and `Mode.TOOLS` would still present whatever catalog we
hand it — via `/v1` instead of native `/api/chat` `tools`. Wrapping
the hop in Pydantic would not have stopped `fetch_url` with a
non-HTTP `url`; that call was schema-valid.

## Overlap with `parse_content_json_tool` and `tools.py`

`agent.parse_content_json_tool` (`2026-09-05t`/`u`) is a **strict
promoter**: whole-message JSON, advertised name, required keys, no
prose. It repairs Coder emitting `{name, arguments}` in `content`
instead of native `tool_calls`. Instructor would retry a completion
until a Pydantic model parses — a different loop, and it would not
plug into the existing hop that already has native `tool_calls` plus
this promoter.

`tools.py` validates **after** selection (`path is required`, action
enums, `ToolError`). That is execution-time checking of one chosen
tool. Instructor validates **model output shape** before we would
even call `tools.call`. We already refuse missing required keys in
the promoter; extra keys like Qwen3.8’s `limit` vs `max_chars`
(`2026-09-05bm`) are ignored by the tool. A Pydantic retry would
spend GPU/CPU tokens to re-ask for the same `read_file`.

Internal structured JSON already uses Ollama native `format` /
`response_format` (`ollama_client.chat`, `context_compactor`,
`judge_eval`, `semantic_judge`). Instructor’s retry-on-invalid is the
one extra; those callers already treat parse failure as
`parse_ok: false` / `None` without a second generation, which is the
right thermal default.

## Router capability classification

`router.classify_capability` is a **model picker**: pin → code-signal
regex → `difficulty.needs_escalation` → default `CAP_TOOL`. It does
not parse a JSON object from the chat model. Using Instructor here
would mean a **second** LLM call (structured `{capability: tool|logic|code}`)
before `decide()`. That is slower, needs a resident model, and is a
different problem than schema-validated extraction of a user-facing
reply. Skip.

## Ollama fit vs current stack

`ollama_client.py` posts **`/api/chat`** with `options` (`num_gpu`,
`num_thread`, `num_ctx`), `keep_alive`, native `tools`, `format`, and
copies `eval_count` / `prompt_eval_count` onto `ChatResult.telemetry`.
Farm offload, Qwythos `keep_alive=30m`, and CPU `:11435` all go through
that. Instructor’s Ollama integration speaks **`/v1`** through the
OpenAI SDK. Options, keep_alive, PowerInfer proxy, and telemetry would
have to be re-solved or dropped. Two clients for one daemon is the
failure mode `ollama_client` was written to avoid.

## Install footprint

`pip install instructor` (1.16.1): OpenAI SDK 2.x, Pydantic 2.8+,
tenacity, rich, typer, jinja2, aiohttp, requests, jiter, plus a CLI
entrypoint. local_agent’s live path is stdlib `urllib` + hand JSON
schema. Pydantic is not a current runtime dependency of the agent
loop. Weight is unjustified for a library that does not touch the
bc/bn failure.

## Recommendation

**skip-because** Instructor solves “make this completion a typed
object, retry if invalid.” Today’s wrong-tool bug was “the model
chose the wrong function from a 68-tool list,” fixed by advertising
fewer tools and counting schema tokens honestly. Output validation
already exists (`parse_content_json_tool`, per-tool `ToolError`,
Ollama `format`). Capability routing is heuristic model selection,
not extraction. Adopting Instructor would add the OpenAI SDK and a
`/v1` transport beside `/api/chat` without shrinking the catalog.

Not “adopt later if we want retries on judge JSON”: if that ever
matters, a bounded retry around existing `response_format` is a few
lines in `judge_eval` / `semantic_judge`, not a new client.

No code, no install, GPU unused.
