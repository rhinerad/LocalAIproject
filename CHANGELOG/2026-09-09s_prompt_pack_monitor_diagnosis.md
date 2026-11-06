# 2026-09-09 — Prompt-pack monitor diagnosis

- The independent production monitor was run against conversation `3262c1f626974397`.
- It correctly rejected a still whose exact Qwen2.5-VL semantic review found a
  visible camera/lens, preserving the attempt evidence and preventing video work.
- A restart guard falsely treated a dead supervisor as live because Windows
  `tasklist` returned `Access denied`; `_pid_live` now falls back to a
  read-only PowerShell process lookup.
- ComfyUI cleanup also encountered a command-line query denial. The owned
  backend checker now falls back to an exact executable-path check and still
  fails closed for an unknown executable.
- The current task is blocked by an orphaned owned ComfyUI backend record whose
  supervisor PID has been reused by an unrelated Windows process. No process
  was killed blindly; no video phase, model edit, or evidence overwrite was
  started.
