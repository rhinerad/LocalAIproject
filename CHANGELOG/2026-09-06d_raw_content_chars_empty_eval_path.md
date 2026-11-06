# 2026-09-06d — `raw_content_chars` telemetry + empty-content/nonzero-eval operator path (sibling of ec/ed/ee)

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06d**
(earlier a/b/c claims were burned by probe calls; this is the written entry).

`APP_REVISION`: `2026-09-06-raw-content-telemetry-r86`.

Sibling of `2026-09-05ec` / `2026-09-05ed` / `2026-09-05ee` — same failure
family on chat `b2542251e7814926` (story-image planning prompt + two reference
sheets, pinned `huihui_ai/qwen3-abliterated:14b`): operator sees the generic
empty-completion reply. After those three filter/routing fixes, live traces
still showed `visible_chars=0 thinking_chars=0 unclosed_think_chars=0
tool_call_count=0` with `tokens_out`/`eval_count=275`.

## Live restart confirmation

1. Pre-existing process already had `app_revision=2026-09-05-image-intent-r84`
   (ec) and had loaded `ollama_client.py` mtime after ee
   (`__pycache__/ollama_client.cpython-312.pyc` 2026-09-06 12:12:01 AM,
   process start 12:12:00 AM). Post-ee 14B retries on
   `b2542251e7814926` / `736f03667e1d4b09` still telemetered all-zero chars
   with `tokens_out=275` — **not a restart miss**.
2. Relaunch via `START_LOCAL_AGENT_GUI.ps1` after this patch:
   `app_revision=2026-09-06-raw-content-telemetry-r85` then bumped to **r86**.
   ExpectedAgentRevision in the start script was stale at
   `2026-09-05-auto-farm-r83`; updated to match.

## What the new telemetry proved

`StreamEnd.raw_content_chars` counts `message.content` **before**
`_VisibleTextFilter`. Live r85 regenerate on `b2542251e7814926` (GPU reserved
→ Huihui 8B CPU fallback because a backend was listening on :8188):

| field | value |
| --- | --- |
| model | `huihui_ai/qwen3-abliterated:8b` |
| tokens_in | 3832 |
| tokens_out / eval_count | **275** |
| visible_chars | 0 |
| thinking_chars | 0 |
| unclosed_think_chars | 0 |
| **raw_content_chars** | **0** |
| tool_call_count | 0 |

So ee's whitespace-prefix swallow is **not** what is happening on these
retries: Ollama streamed empty/null `content` for the whole generation while
still reporting `eval_count=275`. Filter finish/flush cannot recover text that
never arrived.

## Job 3 trim test

Trimmed the same chat to PRE01-only (+ two sheet attachments) via `/api/send`
→ conversation `7b5f84a9176e42f3`. Same shape on 8B CPU fallback:
`tin=3207 tout=275 raw_content_chars=0` all other char counters 0, no tool
calls. **Not** a "30-image single-turn capacity ceiling" — shrinking the
story text alone does not fix it while the full ~68-tool catalog is still
advertised.

Controls that *do* work on the same host/model:

- Bare non-tool ping (`Reply with exactly the word PONG.`) → content `PONG`,
  `eval_count=3`.
- Direct Ollama `/api/chat` with **one** tool (`plan_story_image`) and a short
  plan ask → native `tool_calls` populated, `eval_count=27`, empty content
  (normal for tool-only turns).

Matches the earlier catalog-drowning note already on file for DeepSeek
(`TODO.md` / `2026-09-05at`): narrow schema fires; full catalog does not.

## What changed

`local_agent/ollama_client.py`:

1. `StreamEnd.raw_content_chars` (default 0).
2. `chat_stream` counts content with `msg.get("content") or ""` (null-safe).
3. `_VisibleTextFilter.finish()` flushes a leftover `"prefix"` hold at
   stream-end / cooperative stop (short partial-tag hold can no longer vanish
   silently).
4. Stderr breadcrumb when `eval_count>0` and raw/visible/thinking/tools are
   all empty.

`local_agent/agent.py`:

5. `reason_span` records `raw_content_chars`.
6. After empty-completion retry exhausts: if `unclosed_think_chars==0`,
   `thinking_chars==0`, `raw_content_chars==0`, and `eval_count>0`, operator
   reply is `_EMPTY_CONTENT_NONEMPTY_EVAL_REPLY` (names the Ollama empty-content
   shape; does not claim a filter bug).

`local_agent/server.py` / `START_LOCAL_AGENT_GUI.ps1`: `APP_REVISION` /
`ExpectedAgentRevision` → `2026-09-06-raw-content-telemetry-r86`.

## Tests

```
python -m unittest local_agent.test_ollama_chat_telemetry -q
python -m unittest local_agent.test_native_tool_calling local_agent.test_agent_tracing -q
```

`test_ollama_chat_telemetry`: **19/19** passed (15 pre-ee-suite + finish/raw
cases). Combined native+tracing+telemetry: **123/123** passed after fixing
branch order so native `thinking_chars>0` empties still use the generic
reply (pre-existing `test_agent_tracing` fixtures).

New cases:

- `test_visible_text_filter_finish_flushes_leftover_prefix`
- `test_visible_text_filter_finish_leaves_hidden_alone`
- `test_chat_stream_raw_content_chars_counts_before_filter`
- `test_chat_stream_empty_content_nonzero_eval_raw_zero`

## Live verification status

- **FAIL** for the original goal (tool calls / `plan_story_image` on the
  story-image planning chat): full and trimmed agent-path turns still end
  empty with `eval_count=275` and `raw_content_chars=0`.
- **PASS** for diagnosis: post-ee restart confirmed; shape is empty Ollama
  content under the full tool catalog, not another `_VisibleTextFilter`
  swallow; trim alone does not help.
- Hard constraint during r85/r86 live retries: GPU remained reserved
  (`:8188` listening), so pinned-14B hops demoted to Huihui 8B CPU. The
  pre-r85 14B traces (`tokens_out=275`, all char counters 0) already showed
  the same mechanical shape on GPU PRIMARY.

## Not changed / next fix direction

- No `router.py` edit.
- No GPU render work; did not stop the listening `:8188` backend.
- Likely next harness fix (not done here): an image-capability / story-image
  **reduced tool profile** (catalog drowning), analogous to `gpu_core` and to
  the DeepSeek read_file-only finding — then re-test on free GPU with 14B.

## Files

- `local_agent/ollama_client.py`
- `local_agent/agent.py`
- `local_agent/server.py`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_ollama_chat_telemetry.py`
- `CHANGELOG/2026-09-06d_raw_content_chars_empty_eval_path.md`
- `TODO.md`
- `GROK_STATUS.md`