# 2026-09-24t — Qwen2.5-VL llama-server output logged instead of DEVNULL

This closes the open item from `2026-09-24q`: "Production llama-server output
still goes to DEVNULL." In the 24q v2a run, four judge requests died with
`ConnectionResetError` when the server crashed mid-request. The cause is still
unknown, because the production launch discarded the server's output.

## Change

Both production launches of the Caption V4 server (`127.0.0.1:11436`) now
append stdout and stderr to
**`local_agent/runtime/logs/qwen25_vl_llama_server.log`**:

- `capabilities.ensure_qwen25_vl_runtime` (media watcher / vision batches)
- `dspy_optimizer._ensure_owned_qwen25_vl_runtime` (GVD live-metric judge,
  also the relaunch path in `gvd_judge_eval.py` after a connection reset)

New helpers in `capabilities.py`:
- `open_qwen25_vl_server_log(caller)`: returns an append handle and writes a
  `===== <time> llama-server launch by <caller> =====` header.
  - **Rotation:** once the log exceeds 20 MB
    (`QWEN25_VL_SERVER_LOG_MAX_BYTES`) it is rotated once to `.prev`. At most
    the current and previous logs are kept, and nothing else is deleted.
  - **Fallback:** if the log can't be opened, it returns `subprocess.DEVNULL`,
    so logging can never block the VLM.
- `close_qwen25_vl_server_log(handle, pid)` writes `===== pid N =====` and
  closes this process's copy of the handle. The server keeps its inherited
  handle.

`dspy_optimizer`'s "exited before becoming healthy" `HandoffError` now names
the log path. Launch arguments, ownership/state handling and teardown are
unchanged.

**Not changed:** `gvd_judge_eval.py`'s own `_launch_logged_vlm` (per-run
`results_*.llama_server.log`), the judge files `video_judge.py` and
`dspy_orchestrator.py`, and `media_accuracy_gate.py`. A separate agent was
actively working on the GVD judge (`2026-09-24q`, `2026-09-24r`), so its files
were left alone. Its `r` entry made no production code change, and neither of
the two files edited here had been modified since 09-14 / 09-16 before this
change.

## Backups and line endings

- `local_agent/capabilities.py.bak_vlmlog_20260924_173810` (pure LF; still LF).
- `local_agent/dspy_optimizer.py.bak_vlmlog_20260924_173810`. The file is
  mixed: 1,555 CRLF lines plus an LF-only `extract_eval_frames` block.
  - An editor pass converted that LF block to CRLF. This was caught in the
    diff against the backup, and the file was rebuilt so every unchanged line
    has its original bytes.
  - `diff` against the backup is now exactly the 12 intended lines, with or
    without `--strip-trailing-cr`.
- `test_qwen25_vl_identity.py`: its `_pin` now also points
  `QWEN25_VL_SERVER_LOG` at a temp file, so mocked launches can't write fake
  launch headers into the real log.

## Evidence

- New `local_agent/test_qwen25_vl_server_log.py` (8 tests, Popen mocked; never
  starts llama.cpp):
  - header and PID lines, append order, 20 MB rotation, DEVNULL fallback
  - watcher launch passes a real log handle with `stderr=STDOUT` and closes
    the parent copy
  - a Popen failure still returns False and closes the log
  - judge launch logs under its own caller name
  - early-exit `HandoffError` names the log
- `python -m unittest test_qwen25_vl_server_log test_qwen25_vl_identity
  test_media_watcher_exact_qwen test_dspy_optimizer` → **41 OK**.
- The judge, GVD, media-watcher, tool-calling and render-announce suites
  (`test_video_judge test_dspy_orchestrator test_media_watcher* test_gvd*
  test_native_tool_calling test_render_media_announce`) → **345 OK**, run
  read-only.
- `runtime/logs/qwen25_vl_llama_server.log` still did not exist after all
  test runs, so tests do not write to the production log.
- **Not verified live.** The VLM was not started for this change, since the
  judge agent owns current VLM runs. The first real judge or media-watcher
  launch will create the log. Check it for the `launch by …` header and the
  llama.cpp startup lines.
