# 2026-09-06o — Stills batch queue + review gate before video

Date: 2026-09-06 (evening ET). Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-06o**.

## Operator goal

Easy flow: paste one CLIP start/end still sheet → agent **produces all stills**
(Flux / `realpro_flux`) → announces review-ready → **waits for approval** →
only then video. No more plan-only dumps or "owns the backend" dead-end turns
that abandon the queue (live chat `aa94a2212e19458e`).

## Changes

### A. `render_story_image_batch` + `await_story_image_job`

- New tool `render_story_image_batch`: accepts `jobs` list; runs
  **sequentially** (start `render_story_image` → await until complete/fail →
  next). Returns completed paths, failures, pending.
- New tool `await_story_image_job`: bounded poll of `story_image_job_status`
  (default 900s) so one hop can wait out a multi-minute owned-backend render.
- Flux sheets: `model_profile` / `flux=true` → `realpro_flux`.
- On full success + chat id: auto `present_story_stills_for_review`.

### B. Review gate

- Chat-scoped state under `work/runtime/story_stills_review/`.
- `present_story_stills_for_review` / `approve_story_stills` /
  `story_stills_review_status`.
- Hard block in `tools.call` (and agent hop guard) on
  `prepare_chat_render`, `start_current_chat_render`, and
  `comfy_generate` action=video while `pending_review`.
- Agent requires explicit approval utterance (`looks good` / `approved` /
  `go ahead with video`) before `approve_story_stills`; bare `continue` is
  **not** approval.

### C. Stale `pid_running` fix

- `tools._pid_is_live` uses Windows `tasklist` (same as `image_render._pid_alive`).
- `story_image_job_status` treats an explicitly **released** owner + dead PID /
  `:8188` down as not running (reports `owner_released`).

### D. Guidance

- `plan_story_image` / IMAGE tool text: CLIP sheet → batch render unique
  frames, then stop for review; do not dump many plan-only calls.
- `IMAGE_DIRECT_TOOLS` / gpu_image schema expanded with batch + review tools.
- `APP_REVISION=2026-09-06-stills-review-video-r93` (server + launcher).

## Tests

- New: `local_agent/test_story_stills_batch_review.py` (batch sequential,
  review gate, continue≠approval, stale pid).
- Updated: `test_capability_routing.GpuImageProfileTests` expected set.
- `test_render_story_image` + `test_launcher_revision` +
  `test_native_tool_calling` **103/103** OK.

## Live

Restart required to load new tools into the running agent (r92→r93). Smoke:
attempted / reported in GROK_STATUS after restart.

## Live smoke (honest)

- Restarted agent; /api/status -> 2026-09-06-stills-review-video-r93.
- Stale PID: story_image_job_status(clip15_start, pid=36964) -> finished_or_crashed, pid_running=false, owner_released=true.
- 2-frame render_story_image_batch (Flux/realpro_flux, 512, steps=4): first job launched (pid 24352), awaited to finished_or_crashed with log ERROR: model not visible to owned backend: realProV3_realProV3Unet.safetensors; queue stopped with pending_count=1. No PNGs (model visibility, not batch logic).
