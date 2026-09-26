# 2026-09-06e — capability=image reduced tool profile (gpu_image)

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06e**.

`APP_REVISION`: `2026-09-06-image-tool-profile-r87`.

Sibling of `2026-09-05ec` / `2026-09-05ed` / `2026-09-05ee` /
`2026-09-06d` — same live empty-completion family on chat
`b2542251e7814926`. After raw_content_chars proved Ollama returned empty
`message.content` with `eval_count=275` under the full ~68-tool catalog,
while a direct 1-tool `plan_story_image` probe produced native
`tool_calls`, the next fix is catalog narrowing for `capability=image`.

## What changed

`local_agent/tools.py`:

1. `IMAGE_DIRECT_TOOLS` = `plan_story_image`, `render_story_image`,
   `story_image_job_status`.
2. New schema profile `gpu_image` filters `schemas()` to that allowlist.
3. `profile_for(decision)` returns `gpu_image` when
   `detail["capability"] == "image"`, including CPU-tier busy-GPU Huihui
   8B fallback (so image hops do not collapse to the three meta-tools).
   Farm backend still returns `cpu` first.

`local_agent/agent.py`:

- `apply_hop_profile` emits a `gpu image schema (N tools): ...` note
  (same style as `gpu_core`).

`local_agent/server.py` + `START_LOCAL_AGENT_GUI.ps1`:

- `APP_REVISION` / `ExpectedAgentRevision` ->
  `2026-09-06-image-tool-profile-r87`.

## Tests

```
python -m unittest local_agent.test_capability_routing.GpuImageProfileTests \
  local_agent.test_native_tool_calling.NativeToolTests.test_image_capability_sends_gpu_image_schemas_to_chat_stream \
  local_agent.test_capability_routing.GpuToolFallbackSchemaTests -v
```

-> **13/13 OK** (5 new GpuImageProfileTests + 1 native stream assert +
6 existing gpu_core regression).

```
python -m unittest local_agent.test_capability_routing \
  local_agent.test_native_tool_calling \
  local_agent.test_ollama_chat_telemetry \
  local_agent.test_agent_tracing -q
```

-> **163/163 OK**.

## Live verification

Restart via `START_LOCAL_AGENT_GUI.ps1` confirmed
`app_revision=2026-09-06-image-tool-profile-r87`.

`POST /api/regenerate` on chat `b2542251e7814926` (pinned 14B; GPU busy so
paired CPU fallback `huihui_ai/qwen3-abliterated:8b`):

| span | hop | model | profile | tin | tout | tool_call_count | raw/vis |
| --- | --- | --- | --- | --- | --- | --- | --- |
| router.decide | - | 8b | **gpu_image** | - | - | - | capability=image |
| ollama.chat_stream | 0 | 8b | - | 10323 | 1917 | **14** | 0/0 |
| plan_story_image x14 | 0 | - | - | - | - | - | planned:true |
| ollama.chat_stream | 1 | 8b | gpu_image | 13039 | 94 | 0 | 485/485 |

Pre-fix (r86) same chat under full catalog / cpu meta profile:
`tool_call_count=0`, `raw_content_chars=0`, `eval_count=275`.

**SUCCESS:** hop 0 native tool_calls are real `plan_story_image` plans
(story=`Bulma-and-18-beach-scene`, realvisxl, t2i). No render started
(GPU still reserved by listening backend on :8188; left alone).
