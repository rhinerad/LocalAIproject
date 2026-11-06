# 2026-11-06a — the gateway hook shadowed `local_agent/gvd_qa/`; PowerInfer `server.exe` matching was Windows-only

Follow-up to `2026-11-05c` section 4, second bullet: of the three suites
left as "box-specific", two were not. Branch `claude/jolly-dirac-9impbq`.
Id claimed with `scripts/next_changelog_id.py`.

## 1. `router._gateway()` put the repo root ahead of `local_agent/` on `sys.path` (our bug, 2026-11-04a)

The plan-only gateway hook added in `2026-11-04a` lazily imports the root
package `model_gateway` and, to find it, did `sys.path.insert(0, ROOT)`.
The repo root also holds top-level modules whose names collide with this
package's: `gvd_qa.py` (the QA reference layer) versus `local_agent/gvd_qa/`
(the package `tools.py` imports), and `atomic_io.py` (identical copy). After
the first `router.decide()` on a heavy-logic turn, any **later** first import
of `gvd_qa` resolved to the root file, and `import tools` died with
`ModuleNotFoundError: No module named 'gvd_qa.tools'; 'gvd_qa' is not a
package`.

Why it was invisible in the app: `server.py` and `agent.py` import `tools`
at startup, before any `decide()`, so the package is already in
`sys.modules`. Why it was visible in tests: `test_capability_routing`
imports `tools` lazily inside 14 tests, after earlier tests have called
`decide()`. Traced with a `sys.path` wrapper that logs the inserting frame:
`test_coding_routes_to_josiefied_and_flushes_deepseek → router.decide →
_mark_cloud_plan → _gateway`.

Fix: `sys.path.append(root)` instead of `insert(0, …)`, with a comment
naming the collision. `model_gateway` has no twin inside `local_agent/`, so
precedence does not matter for it.

## 2. `server.exe` stem comparison used `Path` on a Windows default path

`_is_powerinfer_compute()`, `_timeshare_powerinfer_procs()` and `gpu_busy()`
compared `Path(p).stem` with `Path(POWERINFER_SERVER_EXE).stem`, where the
default is `A:\PowerInferBuild\bin\server.exe`. `Path` is `PosixPath` on
Linux and keeps the backslashes in the name, so the configured stem became
`a:\powerinferbuild\bin\server` and never matched `server`. On Windows
`Path` is `WindowsPath`, whose parsing is exactly `PureWindowsPath`, so the
code was right there and wrong everywhere else.

Fix: new `_exe_stem()` using `PureWindowsPath`, which parses both
separators identically on every OS, used at all three sites; the
`configured_path` normalisation in `_is_powerinfer_compute()` now goes
through `PureWindowsPath` too, which is what the old `str(Path(..)).replace
("/", "\\")` produced on Windows. Behaviour on the workstation is unchanged
by construction; the two `*_names_only_server_exe_*` tests in
`test_router_comfy_timeshare` are the proof on this box.

No other production code changed. `local_agent/router.py` only. As with
the `agent.py` change in `2026-11-04a`, the file is larger than this cloud
session can push whole, so the change travels as a 70-line patch applied
and committed from the workstation; this entry and its id claim are pushed
from here first. Until that commit lands the branch carries the entry
without the code.

## 3. Evidence (this Linux session, Python 3.13, no GPU, no override)

Before (HEAD `442e33a`, via `git stash` of `router.py`) and after:

    test_capability_routing      Ran 44  FAILED (errors=14)   →  OK
    test_router_comfy_timeshare  Ran 51  FAILED (failures=2)  →  OK
    test_router_switching        Ran 54  OK                   →  OK
    test_router_status_busy      Ran 8   OK                   →  OK
    test_gpu_vram_num_ctx        Ran 7   OK                   →  OK
    test_powerinfer_chat_route 6, test_vram_arbitration 5,
    test_agent_timeshare_gpu_gate 5, test_http_origin_guard 7,
    test_render_story_image 24, model_gateway/test_policy 14,
    model_gateway/test_adapter_mock 16                        all OK

Every suite in `docs/LOCAL_AGENT_REGRESSION_RUNBOOK.md` was then run alone
with the fix. The ones not green fail **identically** before and after and
are this box, not the router: `test_native_tool_calling` (1 failure:
`duration_ladder` needs `outputs/equal_shares/audio_pass_durations.json`,
which is under the ignored `outputs/`), `test_chat_render_jobs` (no chunk
folder), `test_exemplar_embeddings` (no `chromadb`), `test_media_analysis`
(Modelfile/paths on the workstation), `test_powerinfer_pipeline`
(`PermissionError` not raised: this session runs as root),
`test_sideband_tier_b` (no `vendor_sideband/`), `test_run_code`
(`ctypes.WinDLL`). `test_farm_core` and `test_termux_powerinfer2_edge_worker`
are named in the runbook but do not exist in the tree.

## 4. Unverified / next

- Not yet run on the workstation. Expected there, with the machine-wide
  override untouched: `test_capability_routing` `Ran 44 ... OK`,
  `test_router_comfy_timeshare` `Ran 51 ... OK`, and the three
  `2026-11-05c` suites unchanged (54 / 8 / 7 OK). Section 2 predicts no
  behaviour change on Windows; the comfy-timeshare suite there is the check.
- `test_native_tool_calling` on the workstation should be `Ran 118 ... OK`
  since the durations file exists there; it was not run for `2026-11-05c`.
- Root `atomic_io.py` and `local_agent/atomic_io.py` are byte-identical
  today; the root copy is still a collision waiting to happen if they
  diverge. Not touched.
