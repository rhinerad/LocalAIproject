# Current handoff

This is the one undated handoff file. Overwrite it when the current job
changes; the dated originals it was built from stay in `docs/backrooms/` and
`archive/handoffs/`. Last rewritten 2026-11-06 from
`docs/backrooms/motion-transfer-chaining-handoff-26l.md` (HEAD of the
2026-09-26 work) and `docs/backrooms/pipeline-completion-roadmap-2026-09-26.md`.

## State of the project (2026-11-06)

- **Equal Shares** (124-clip MiniMax H3 film) is paused since 2026-08-30. Do not
  resume its audio pass or touch its evidence unless explicitly asked.
- **The local assistant** (`local_agent/`) is the live product. `APP_REVISION`
  in `local_agent/server.py` is the authoritative build label.
- **The Backrooms sitcom / GVD batch pipeline** restarted from C001 on
  2026-09-22 (`CHANGELOG/2026-09-22j_restart_all_generations.md`). Runner chain:
  `gvd_watcher_keepalive.ps1` → `gvd_watcher.py` → `batch_run_backrooms_gvd.py`
  → `generate_video.py`, with `local_agent/gvd_qa/` judging.
- **Motion transfer** (`render_video_from_reference`,
  `local_agent/motion_transfer_render.py`) ships single-job only, bounded to 180
  frames; segment chaining is opt-in and marked EXPERIMENTAL because the
  held-frame seam measures as a hard cut (f2f 25.6 vs 2.28 median). The
  img2img init scheme measured 9.44 vs 2.47 median on a 2-segment run and is
  the lead candidate; it was not promoted because the 3-segment run has not
  been done.
- **2026-11 audit remediation is COMPLETE in code** on
  `claude/epic-hypatia-6mrayy`. Every finding in `AUDIT_2026-11-02.md` now
  has a status (the "Remediation status" section at the top of that file);
  what remains is operator-only work (listed at the end of this file) and
  the monolith refactors, which were never in scope. `ruff check .` is clean.
  Evidence: `CHANGELOG/2026-11-06a_audit_remediation_part1.md` and
  `CHANGELOG/2026-11-06b_audit_remediation_part2.md`. Unit tests only; no
  render was run, so per CLAUDE.md §3 nothing here is render-verified.
  **Before the first pull on the workstation, read the "Pulling this branch"
  section below.**

## Pulling this branch on the workstation

Older commits track `local_agent/chats/`, `uploads/`, `logs/` and the
Reticulum identity; this branch does not. A plain `git switch`/`git pull` would
therefore delete those files from the working tree. Do this instead:

1. Copy `local_agent/chats`, `local_agent/uploads`, `local_agent/render_jobs`,
   `logs` and `local_agent/rns_wifi/storage` somewhere outside the repo.
2. Pull with the updated `scripts/sync_down.ps1` (it snapshots those paths and
   restores anything git removed), or restore from your copy afterwards.
3. Run `scripts/untrack_private_data.ps1` once, then `sync_up.ps1` as usual.
4. Delete `local_agent/rns_wifi/storage/transport_identity` so RNS mints a
   fresh identity (the old one is public), re-pair the phone, and rotate the
   Mac worker's Redis password (`Add-Phase1SecondaryWorkerCredential.ps1`).
5. Copy `work/thermal_guard.py`, `work/image_render.py`, `work/scene_reasoner.py`
   and the other `work/*.py` modules into the clone, then commit them.
   `.gitignore` now allows them (only `work/runtime/` is ignored), but as of
   2026-11-06b **no `work/*.py` file is actually in git** (`git ls-files work`
   is empty), so a fresh clone still has no thermal guard. The code fails
   closed without it (GPU work is refused, never started blindly), and 27+
   tests skip or fail until the files are committed.

## Do next, in order (motion transfer, carried from 26l)

Preflight for any GPU run: port 8188 closed, `work/runtime/image_render_owner.json`
released, the shared GPU lock free (`gpu_lock.py`), `nvidia-smi` idle, operator
chat idle, free RAM ≥ 16 GB (the backend alone needs ~13–15 GB).

1. **Run the 3-segment img2img chain** (`chain_investigate_26l.py long_img2img`,
   0–15 s at 12 fps, 60 | 4+60 | 4+60 frames, ~30 min) and compare seams at
   delivered frames 61 and 121 against the 26k single job (f2f median 2.76,
   p90 4.62, max 11.3). Confirm RAM flatness across segments.
2. **If seams stay ≤ ~10 and motion follows the source:** set
   `INIT_MODE_DEFAULT = "img2img"`, re-pin the chained template sha in the
   tests, drop the EXPERIMENTAL wording, and decide whether >180-frame requests
   chain automatically. If motion is damped, try denoise 0.8, then the hybrid
   init (4 held frames via noise mask + repeated last frame).
3. **If nothing reaches that bar:** record it with frame comparisons, keep
   chaining opt-in, and document the 180-frame bound until Wan 2.2 Animate
   (weights on disk since 26h) is wired in as a separate task.
4. **Refit the RAM guard**: `ram_needed_gb(frames) = ~12.5–13 GB fixed +
   ~0.012 GB/frame + margin`; update `test_ram_need_scales_with_length` and the
   tool description.
5. **Close out**: full unit run with no render active, restart
   `START_LOCAL_AGENT_GUI.ps1`, changelog entry, TODO update.

Do not touch the MiniMax/`dspy_orchestrator.py` chaining path; do not change
`template_sha256()`; never delete a job folder, raw frame or manifest.

## Roadmap (from 2026-09-26, still the plan)

- **A. Operator decisions** — mostly taken on 09-26d (FaceID Plus v2 + Wan 2.2
  Animate approved; motion-keyword table relaxed). Open: still-QA prompt-content
  axis; D02 judge-miss investigation.
- **B. Ready now** — GVD router honest-failure statuses reach the chat (done
  26f); fixture + receipt-gated smoke for `animatediff_pose`; worker adoption of
  per-frame masks.
- **C. Motion transfer as a reusable tool** — the steps above.
- **D. "Any prompt" versatility backlog** — catalog promotion flow, profile
  measurement, generic storyboard path.
- **E. Judge/quality loose ends** — brief-free object pass, labeled-set
  regressions.

## Open items from the audit (operator-only)

No agent should do these unasked; each needs the operator's credentials,
hardware or an irreversible decision.

1. **History rewrite on GitHub** to purge the committed Reticulum identity,
   chats and uploads. They are untracked going forward, but still in old
   commits (and `local_agent/chats/` plus `uploads/` are still in the index on
   this branch until step 2 runs). `AUDIT_2026-11-02.md` §6 step 1.
2. **On the workstation**, the "Pulling this branch" steps above: back up the
   private dirs, pull with `scripts/sync_down.ps1`, run
   `scripts/untrack_private_data.ps1`, delete
   `local_agent/rns_wifi/storage/transport_identity` so RNS mints a new one,
   re-pair the phone, rotate the Mac worker's Redis password.
3. **Commit `work/*.py`** from the workstation (see step 5 above).
4. **Move the private `distill` Celery queue** off the tunnelled Redis
   instance (db 0 is still shared; the secondary ACL keeps `~*` because
   Celery key names are unpredictable).
5. **Untrack `.claude/settings.local.json` and `.claude/launch.json`** if they
   should stay local (`untrack_private_data.ps1` covers them).

Test-environment notes for the workstation: `EQUAL_SHARES_PRIMARY_REASONING_MODEL`
is set in this machine's environment and changes `router.PRIMARY_REASONING_MODEL`
at import, which fails 11 `test_router_switching` tests that assume the default
Huihui primary; run the suite with that variable unset to compare with CI.
