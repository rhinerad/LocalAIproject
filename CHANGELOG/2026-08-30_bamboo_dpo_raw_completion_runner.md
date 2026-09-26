# 2026-08-30 — Bamboo-DPO bounded raw-completion diagnostic runner

Added `tools/powerinfer/run_bamboo_dpo_raw_completion_diagnostic.ps1` for the
frozen Bamboo-DPO candidate only. It is inert unless explicitly invoked with
`-Execute` after a fresh GPU-owner decision.

Before loading anything it requires the candidate/hash receipts, 32 activation
files, the source-backed raw-completion addendum, no ComfyUI listener on 8188,
no existing native `main`/`server` process, and a GPU below 82 C. It scopes the
PowerInfer virtual environment to one `main.exe` process, captures a
timestamped receipt and logs, and restores the process environment afterward.

The receipt is deliberately `completed_unscored` and hard-codes
`promotion_allowed: false`: the source supports a raw continuation diagnostic,
not an instruction-following or chat-quality claim. The runner cannot launch a
server, edit the candidate, or change a registry, router, proxy, picker, or
ComfyUI process. Its PowerShell syntax was parsed successfully; it was not run.
