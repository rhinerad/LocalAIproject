# 2026-09-25q — A queued analysis followed by a silent model now ends in an honest progress report (with a way to fetch the queued result); reference-video motion transfer investigated, routed honestly, planned read-only, stage 1 proven

Two parts. Part 1 is a narrow honesty fix for a live dead end. Part 2 is an
investigation-and-build for a capability that does not exist in this tree;
it lands the honest plumbing and a verified first stage, not a generation
path. Id `q` was claimed by `scripts/next_changelog_id.py` at session start;
a second call during the session claimed `s` by mistake (no release option
exists), so `s` is an unused gap — `r` belongs to another session.

## Part 1 — live reproduction

`local_agent/chats/1f0e3e61bdb0487a.json` msgs 0–1 (the operator later deleted
the chat; the file is preserved at `chats/_deleted/1f0e3e61bdb0487a.1790369686.json`
and `runtime/agentic_tasks/1f0e3e61bdb0487a.json`). Timestamps UTC from `at`:

| msg | at | what happened |
|---|---|---|
| 0 user | 18:56:34Z | reference video + character image attached; "use this video for a visual/action ref for minimax … the character should be switched out with the character image ref" |
| 1 assistant, hop 0 | — | `analyze_video` → `{"queued": true, "reason": "exact Qwen2.5-VL Caption V4 runtime is not active", "job_id": "9603cd9abe114ed1", …}` (a real queued state, not an error) |
| hop 1, hop 2 | — | model stream: `eval_count` 275, `raw_content_chars` 0, no tool call, twice (the second is the built-in one-shot retry) |
| 1 assistant, stored | 19:00:35Z | the raw `_EMPTY_CONTENT_NONEMPTY_EVAL_REPLY` diagnostic ("… every streamed message.content field was empty …") |

The attached image was never analysed. The operator was never told which job
to ask about.

### What was actually wrong (four things)

1. **The empty-completion branch ignored tool evidence.** `agent.py` retried
   once, then chose one of three raw diagnostics purely from the stream
   telemetry (`unclosed_think_chars` / `raw_content_chars` / neither) with no
   look at `recent_tool_attempts`. The sibling guards in the same loop
   (write_file ERROR, batch-folder, batch-render, current-chat-render, 25p's
   scope block) all return a fixed truthful reply for exactly this reason.
2. **The queued job did complete; nothing could bring the result back.**
   `media_queue/done/9603cd9abe114ed1.json`: `queued_at` 19:00:19Z,
   `claimed_at` 19:02:14Z, `done_at` 19:11:32Z, 72 per-second observations.
   The watcher works (`media_watcher.py` claims `analyze_video` jobs,
   `_run_analyze_video_job`). But `agent.py` never consults `media_queue`,
   no tool could fetch a job by id, and `enqueue()` coalesces only against
   `pending/processing` — so re-attaching the same file re-ran the whole
   eleven-minute analysis. `media_job_status` by path shows **seven** jobs
   for this one video (four done, two failed, one cancelled). The chat GUI's
   `reconcile_queued_activity` restamps the activity card only; the stored
   assistant text stays the raw error. The task note "no completed result
   anywhere under work/runtime" is because the queue lives under
   `local_agent/media_queue/`, not `work/runtime`.
3. **The model was told to call tools that do not exist.** `server.py`'s
   attachment note said "Call analyze_image on this path now" / "Call
   measure_audio …" and the system prompt (`agent.py` ~715/727) named
   `analyze_image` and `measure_audio`. `tools.call("analyze_image", …)` →
   `ERROR: no tool 'analyze_image'`. The real tools are `see_image` and
   `audio_measure`.
4. Not a bug, but relevant: the blank stream itself is the known
   `huihui_ai/qwen3-abliterated:14b` tool-heavy-turn failure already
   diagnosed on 2026-09-06 (`raw_content_chars` telemetry). It is handled —
   the handling just threw away everything the turn had learned.

### Change — `local_agent/agent.py` (CRLF preserved, 3490 → 3666 lines; edit script `runtime/queued_honesty_20260925/_edit_part1.py`, 12 exact anchors, refuses a second run)

- `_QUEUED_RESULT_FOLLOWUP`, `_ATTACHMENT_RE`, `_SENSORY_ANALYSIS_TOOLS`;
  helpers `_attachments_in_text` (parses exactly the `--- attached <kind>:
  <name> ---` / `local path:` block server.py writes), `_norm_path`,
  `_args_paths`, `_args_source_name`, `_queued_tool_result` (a non-ERROR
  result whose JSON has `"queued": true`), `_tool_progress_empty_reply`.
- Turn-local `tool_log` (every call: name, is_error, queued info, paths,
  source name, error text) beside the untouched `recent_tool_attempts`;
  per-hop `hop_queued_ids`.
- Empty-completion branch: each of the three shapes now sets a short
  `cause`; if `tool_log` is non-empty the reply is
  `_tool_progress_empty_reply(latest_user, tool_log, cause)` — fixed text,
  never model prose: what is queued (tool, operator's attachment name, job
  id, reason, "nothing from that file has been analysed yet"), what
  completed, what failed, which attached files never had a sensory tool
  called, "Nothing was rendered, generated, or started by this turn", and the
  exact next step (ask for media job `<id>` / ask again). Note event:
  "empty completion after tool activity: returning the fixed tool-progress
  reply (N tool call(s), M queued job(s)) instead of the raw model
  diagnostic". Trace attr `tool_progress_reply`. Turns with **no** tool
  activity keep the three raw diagnostics exactly as before.
- Hop follow-up: when the hop's results included a queued job, the standard
  "If you now have everything needed…" prompt gains `_QUEUED_RESULT_FOLLOWUP`
  naming the job id(s): do not wait/poll/describe the media; call the
  sensory tool for any other attachment; otherwise report what is queued.
- System prompt names `see_image` / `audio_measure`.

Replay of the real msg 0 through the patched loop with the live tool JSON
and the live blank stream shape
(`runtime/queued_honesty_20260925/replay_live_chat_after.py`, output in
`replay_after.txt`): 3 hops (retry still happens), reply:

> I could not finish this turn: the local model returned no text after the tool step (Ollama reported a real generation but returned blank content). Here is exactly where things stand.
> - Queued, not complete: analyze_video on joss-miss-and-bja-pov-sulbas3d_1080p.mp4 was queued as media job 9603cd9abe114ed1 because exact Qwen2.5-VL Caption V4 runtime is not active. The background watcher runs it when the GPU is free; nothing from that file has been analysed yet.
> - Not analysed yet: attached image 5b0e03cb1ee24a14b5d5e259d8bce550-1200688d4edb9c5f.png (no sensory tool was called on it).
> Nothing was rendered, generated, or started by this turn.
> To continue: ask me to check media job 9603cd9abe114ed1 once it has had a few minutes; or ask again and I will continue from here.

### Change — `local_agent/tools.py` (LF, 4922 → 5017 → 5107 lines), `media_queue.py`, `media_tools.py`, `server.py`, `remote_security.py`

- **`media_job_status`** (new, read-only, in `CONCURRENCY_SAFE_TOOLS`,
  category sensory, `REMOTE_DEFAULT_TOOLS`): `{"job_id"}` → state
  pending/processing/done/failed/cancelled, progress, timestamps, source,
  and for done the full parsed result (what the original tool would have
  returned); `{"path"}` → every job for that file newest first plus
  `latest_done` in full. Unknown id / no args → ERROR. Live:
  `media_job_status {"job_id": "9603cd9abe114ed1"}` returns the 72-frame
  result.
- **`_TOOL_ALIASES`** in `tools.call()`: `analyze_image → see_image`,
  `measure_audio → audio_measure`. `server.py` attachment notes now name the
  real tools.
- **Completed-result reuse** (`media_tools._completed_reuse`, consulted only
  on the queue path): an identical request (same kind, same public args,
  same unchanged file) returns the stored done result with a
  `reused_completed_job` marker instead of a second multi-minute queue wait.
  Never reused: results containing `"analysis_status": "unavailable"` or
  `"available": false` (a run the VLM abandoned part-way), failed/cancelled
  jobs. `media_queue.enqueue(..., source=)` records `source_stat`
  (size + mtime_ns); `find_completed` requires an exact stat match, and for
  legacy done jobs without it (like `9603cd9abe114ed1`) requires the file's
  mtime to be no later than the second the job was queued. `find_for_path`
  added. A queue module without the lookup (test stub, or a long-running
  server that imported the old module) simply gets no reuse.
- No queue file, chat file, or evidence was edited or deleted.

### Tests

- New `local_agent/test_queued_analysis_honesty.py` — **22 OK** (attachment
  parsing incl. CRLF; queued detection; the live msg-0 + queued + blank×2
  end-to-end reply and follow-up prompt; queued + `see_image` result + blank;
  blank with no tools keeps the raw diagnostic; tool error + blank; unclosed
  think after a queued result; `media_job_status` shapes for every state,
  by path, unknown; aliases; prompt/server name the real tools; reuse for an
  unchanged file, not for changed file / different args / partial result;
  legacy job mtime rule; `see_image` path records `source_stat`).
- `test_native_tool_calling`: 118 OK before (`runtime/queued_honesty_20260925/before_native.log`)
  → 118 OK after (in `after_targeted.log`).
- Full non-live suite, `python -m unittest $(ls test_*.py | grep -v _live |
  sed 's/\.py$//')` from `local_agent/`, system Python 3.12.10:
  **before: 1591 OK (2 skipped), 263 s, exit 0** (`before_full.log`).
  First run after Part 1 (`after_full.log`, 688 s): 1613 tests, 5 errors +
  1 failure — the 5 errors were the queue-gate tests in `test_media_gpu_queue`
  / `test_media_analysis` whose `media_queue` stub lacks `find_completed`
  (fixed with the `getattr` guard above; those two modules + the new one then
  **71 OK**, `after_gates_refix.log`); the failure was
  `test_existing_whisper_capability_routes_transcription_without_loading_a_model`,
  the run-order case 25p already recorded (passes in isolation and in the
  targeted run). **Final run after every Part 1 + Part 2 edit
  (`runtime/queued_honesty_20260925/final_full.log`): Ran 1631 tests in
  278 s, OK (skipped=2), exit 0** — +40 tests over the 1591 baseline (22
  Part 1 + 18 Part 2), zero failures, the whisper run-order case included.

## Part 2 — reference-video motion transfer with character replacement

Full report: **`docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md`** (what
exists, what is missing with sizes and locations, the three approaches,
frame plans for the actual clip, the path to yes, what a real tool still
needs). Operator decision recorded in `TODO.md` (last section). Summary:

- **Nothing existing does it.** Every video path takes still frames
  (FLF2V / prompt-pack), MiniMax H3 has no motion-clip input, `comfy_generate`
  composes comfyui-mcp's own graphs, `analyze_video` is analysis. The GVD
  router had no such capability; it answered a generic `UNAVAILABLE_CAPABILITY`.
- **Content.** The reference is sexually explicit 3D animation (72 VLM
  observations in the done job); the character still is an AI-generated nude
  turnaround of Bulma, a fictional adult anime character, 1280×720. All
  verification here used a benign Equal Shares Stage-1 clip. A real person's
  likeness must never go into sexual content with these tools; the planner
  does not check inputs for that (TODO item).
- **Installed** (`A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI`, live
  `object_info` 3 735 nodes): WanVideoWrapper (Animate / VACE / Uni3C node
  code), controlnet_aux with DWPose + Depth-Anything-V2-Large **cached**,
  AnimateDiff-Evolved + SDXL motion modules, IP-Adapter Plus Face SDXL +
  CLIP-ViT-H, SDXL union ControlNet promax, VideoHelperSuite, ProPainter
  nodes **with** weights (its GVD block is a VRAM-profile gate, not a missing
  install), SAM2, LivePortrait. RTX 5080 16 GB.
- **Missing:** every Wan-Animate / VACE / Fun-Control / Uni3C weight.
  Path to yes: Wan 2.2 Animate 14B ~17 GB fp8 (+0.6 GB relight LoRA) —
  best fit; or Wan 2.1 VACE 1.3B module ~1.2 GB (base 1.3B T2V already on
  disk) — cheapest real v2v; or the fully-installed AnimateDiff-SDXL stack
  (lowest quality, no download). **Operator decision needed; nothing was
  downloaded.**

### Change — `local_agent/gvd_tool_router/` (LF; `runtime/motion_transfer_20260925/_edit_gvd.py`, 11 anchors + one import fix)

- `schema.py`: `CAPABILITY_MOTION_REFERENCE = "motion_reference"`,
  `ShotManifest.motion_reference_video: ArtifactRef | None`,
  `shot_from_dict` parses it.
- `router.py`: `required_capabilities` adds `motion_reference` when the
  manifest carries one, plus `identity_reference` when a character is named.
- `service.py`: blocked `route_shot` results gain `missing_capabilities`
  (required minus everything the active set offers) and `blocked_candidates`
  (catalog rows plus seed rows not yet in the catalog that cover a missing
  capability: id, tool, status, `covers`, `disabled_reason`, provenance,
  `source: catalog|seed`). Selected routes are unchanged.
- `catalog_seed.py`: three disabled `execute_narrative_scene` rows —
  `wan22_animate_14b_unvalidated`, `wan21_vace_1_3b_unvalidated`,
  `animatediff_sdxl_pose_ipadapter_unvalidated` — each `disabled_reason`
  names the exact missing file and size, or "every node and weight is
  installed … no pinned API template and no local VRAM profile yet".
  `discovery.ALLOWED_CAPABILITIES` += `motion_reference`. The live
  `runtime/gvd_tool_router/registry/catalog.json` is untouched (seed rows
  surface through `blocked_candidates` with `source: seed`).
- Live: `gvd_route_shot` for the operator's clip now returns `status:
  blocked`, `missing_capabilities: ["motion_reference"]`, and the three
  candidates with reasons.

### Change — `local_agent/motion_transfer.py` (new), `tools.py`, `remote_security.py` (`_edit_tools.py`, 6 anchors)

- **`plan_video_from_reference`** — read-only, `CONCURRENCY_SAFE_TOOLS`,
  category gvd, `REMOTE_DEFAULT_TOOLS`. Inputs: reference video + character
  still (+ optional `target_fps`). Output: ffprobe facts and sha256 of both,
  per approach `feasible_now`, `installed`, `missing` (accepted filenames,
  folder, ~GB, download location), `download_gb_to_enable`, `frame_plan`
  (fps, frames, window, overlap, windows), `recommended_now`,
  `best_with_download`, `operator_decisions_needed`, `gvd_route`, and a
  note that nothing was rendered/downloaded/loaded. Presence via
  `work/image_render.model_file_on_configured_paths` (same YAML the still
  renderer uses) + the checkout's `custom_nodes/`.
- Live on the operator's inputs (`runtime/motion_transfer_20260925/plan_live.json`):
  70.767 s, 60 fps, 1920×1080, 4 246 frames; image 1280×720;
  `animatediff_sdxl_pose_ipadapter` feasible now (11 installed, 0 missing;
  567 frames / 47 windows @ 8 fps); `wan22_animate_14b` missing the ~17 GB
  model (1 133 frames / 15 windows @ 16 fps); `wan21_vace_1_3b` missing the
  ~1.2 GB module.

### Verified for real — stage 1 (pose maps from a benign clip, owned backend)

`runtime/motion_transfer_20260925/pose_extract_poc.py`, evidence in
`pose_poc_manifest.json` and `pose_poc.log`. Same lifecycle as
`work/image_render.py`: `preflight_execute` (owner file, port 8188, thermal
31 C), `_write_owner`, `_start_owned_backend(face_detail=True)` (custom nodes
on; ready in 2 min 52 s, pid 14860), `_post_prompt`, `_wait_for_outputs`,
`_stop_owned_backend`, `_release_owner` (owner file shows `released_at`
21:30:43Z; `comfy_listening` False afterwards; GPU 31 C before and after).

- Input: `A:\Users\rhine\ComfyUI-Shared\output\story\02A\attempt_1_00001_.mp4`
  (read only; sha256 `dd105c22864cd616…`, 8 s, 24 fps, 736×416; two people
  at a bedside), loaded by `VHS_LoadVideoPath` at `force_rate` 8,
  `frame_load_cap` 24 → `DWPreprocessor` (`yolox_l.onnx` bbox,
  `dw-ll_ucoco_384_bs5.torchscript.pt` pose, hands+body+face, res 512) →
  `SaveImage`; the source frames saved beside them.
- prompt_id `c6737c84-3706-4771-ae5c-90a125b32bda`, history
  `status_str: success`, 47.3 s; **48 output files, all present with sha256
  in the manifest**: 24 × `pose_%05d_.png` (e.g. `pose_00001_.png` 45 050 B
  sha `824646511a44…`) and 24 × `src_%05d_.png` under
  `outputs/stories/_comfy_output/mcp_test/pose_poc_20260925/`. Backend log:
  "DWPose: Bbox ~1 330 ms, Pose ~60 ms on 4 people" per frame — no
  download, the cached weights were used.
- Visual check (frame 1, native size): the pose map holds two body
  skeletons matching the man leaning in from the left and the woman
  reclining right-of-centre, with face and hand keypoints; one tiny
  spurious skeleton at far right where DWPose read the framed family photo
  on the nightstand. So: pose extraction is real and correct on this
  install, and small pictures-within-the-picture will need masking or a
  bbox size floor in a real template.
- Not done: the depth pass (`DepthAnythingV2Preprocessor` is present in
  live `object_info`; the runner skipped it because that node keeps
  `ckpt_name` under `optional`, fixed in the runner after the run but not
  re-run). No generation. No template, no VRAM profile, no promotion.

### Tests

- New `local_agent/test_motion_transfer_plan.py` + `test_gvd_tool_router`:
  **67 OK** (`runtime/motion_transfer_20260925/tests_part2.log`): manifest
  field and required capabilities; blocked route names the capability and
  the three candidates with reasons; selected routes carry no blocked
  report; seed rows disabled/narrative/motion; discovery allowlist;
  inventory against a fake ComfyUI tree (empty → all missing; full
  AnimateDiff stack → feasible; Wan paths flip on exactly the named weight;
  optional LoRA not counted); frame-plan arithmetic (1 133 frames / 15
  windows for the real clip); whole plan; wrapper errors/JSON/target_fps;
  this-machine smoke.

## Not changed, on purpose

- The one-shot empty-completion retry, `_EMPTY_*_REPLY` texts, and the
  hop-limit path (`_HOP_LIMIT_EMPTY_REPLY`) are unchanged; only turns with
  tool activity get the progress reply.
- `enqueue()`'s pending/processing coalescing; the watcher; the GUI
  restamp; `runtime/gvd_tool_router/registry/{catalog,active}.json`.
- `server.py` `APP_REVISION` not bumped (as 24a/24e/24g/25p). A GUI server
  already running imported the old `agent.py` / `tools.py` / `media_*`;
  restart `START_LOCAL_AGENT_GUI.ps1` to get all of this (the watcher too,
  for `source_stat` on new jobs).
- Chat files, queue files, Equal Shares evidence: untouched.

## Open

- `_ATTACHMENT_RE` matches only server.py's exact attachment block; a phone
  (LXMF) attachment path that inlines differently would show as "not
  analysed" only if the model also never called a tool on it — check the
  bridge's inline format before relying on that line for phone chats.
- The `s` id claim above.
- Everything in `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` §7.
