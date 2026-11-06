# 2026-09-24e — local_agent: refuse still jobs whose prompt truncates an operator-pasted prompt

## Symptom

Chat `local_agent/chats/1d4a42d3b5834081.json` (Backrooms Sitcom Audition pack
pasted as message 0). Manifest
`outputs/stories/Backrooms-Sitcom-Audition-Prompt-Pack/manifests/image_f02381ec-….json`
(created 04:20:34Z) rendered with prompt = only the first sentence of
"Scene Start Image 1" (120 chars, "…for a sitcom casting tape"). The result,
`_comfy_output/…/renders/fd51e60dfcda49ef8ac0fa8c9b1c860f_00001_.png`, is an
empty living room with no actor. The earlier manifest `image_62e576a9-….json`
(03:53:51Z) had the full prompt.

## Where the truncation happened — the model, primed by our own tool output

Evidence, all read-only:

- `knowledge/traces.db`, trace `54751f9e…`, tool span `render_story_image_batch`
  at 04:08:10Z: `arg_sha256=5448b458…`, `arg_json_bytes=360`. The span is
  recorded in `agent._trace_tool_call`, whose args are the Ollama native
  `tool_calls` arguments plus only the server-injected `__conversation_id`.
- **The hash reproduces exactly** from
  `{"__conversation_id":"1d4a42d3b5834081","flux":true,"jobs":[{"model_profile":"realpro_flux","prompt":"<first sentence>","story":"Backrooms Sitcom Audition Prompt Pack"}],"model_profile":"realpro_flux","stop_on_failure":true,"timeout_s":900}`
  (`json.dumps(sort_keys=True, ensure_ascii=False)`, as `tracing.summarize_tool_args`).
  The 03:41:46Z call's hash `3eef75f4…` (751 bytes) reproduces from the same
  dict with the **full** prompt. So the two calls are identical except the prompt.
- The turn went through the native tool-call path (review → decide → tool_call),
  not `action_resolver` (which short-circuits the turn), not the managed prompt-pack
  plans, and not the Backrooms adapters. `ollama_client.chat_stream` and
  `tools.parse_call_tool_args` do not alter string values. `tools._normalize_batch_job`
  only `.strip()`s, and it runs after the span was hashed anyway.
- Why the model sent that string: `tools.render_story_image_batch` labels
  each job `"prompt_preview": job["prompt"][:120]`. For this prompt, 120 chars
  ends **exactly** at the first period, so the preview reads as a whole
  prompt. `agentic_state.observe_tool` keeps the first 520 chars of each result
  as trusted task-state evidence. All three prior batch observations for this
  chat (`runtime/agentic_tasks/1d4a42d3b5834081.json`) contain that exact
  120-char preview. The 8B model (`huihui_ai/qwen3-abliterated:8b`) copied it
  back as the job prompt.

Also noted (already fixed earlier, not changed here): the 04:08 call returned
`completed` after 2.5 s with the *previous* 03:53 manifest. That was the stale
manifest bug fixed in `2026-09-24b` (launch-time manifest filter), which landed
after this incident (the `tools.py.bak_inlinemedia_20260924T002509` backup lacks
`_story_job_started_at`). The invented "QA passed / SELECTED" replies in this chat
are covered by `test_native_tool_calling.test_fabricated_qa_selected_claim_after_batch_render_is_corrected`.

## Change

- `local_agent/agent.py`: new `_truncated_operator_prompt()` /
  `_truncated_render_prompt_refusal()`, checked in `run_one()` for
  `render_story_image_batch` (every job), `render_story_image`, and
  `plan_story_image`. A prompt (≥40 chars, whitespace-normalised, trailing
  punctuation ignored) that occurs in an **operator** message line followed
  by ≥20 more characters on the same line, and never occurs complete, is refused
  before `tools.call`. The error names the job field and the dropped
  continuation, and tells the model to resend the text verbatim. Reworded prompts
  (not found verbatim) are not judged.
- `local_agent/tools.py` `render_story_image_batch`: `prompt_preview` now ends
  in `…` when cut, and each label carries `prompt_chars`, so the preview no
  longer reads as a complete prompt.

Backups: `agent.py.bak_promptprefix_20260924T012949`,
`tools.py.bak_promptprefix_20260924T012949`.

## Verification

- New `local_agent/test_truncated_prompt_guard.py`, 9 tests, all pass. They
  include a replay of the live chat's message 0 (the exact 120-char prompt
  is flagged, with continuation "An adult male actor in his late 20s…"), and an
  `answer()`-path test in which the model's truncated batch call never reaches
  `tools.call`. **That test fails with the guard stubbed out**, confirmed.
- Still green: `test_native_tool_calling`, `test_render_story_image`,
  `test_story_stills_batch_review`, `test_render_media_announce`,
  `test_managed_prompt_pack`, `test_story_image_reveal`, `test_story_image_plan`.
- **Not live-verified**: no GPU render was started, and the running local-agent
  server has not been restarted, so it still runs the old code until the
  operator restarts it.
