# 2026-09-08 — Production watchdog PID fix

The prompt-pack production supervisor now records `os.getpid()` in its durable
ledger on every start. Previously it reused a stale PID, so a restarted worker
could appear owned by a dead process and the watchdog could not distinguish the
live supervisor. No evidence, model files, or unrelated ComfyUI process was
modified.
