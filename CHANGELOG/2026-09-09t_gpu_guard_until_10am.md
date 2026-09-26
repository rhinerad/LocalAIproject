# 2026-09-09 — Overnight GPU guard

- Started `work/gpu_guard_until_10am.ps1`, bounded to the local machine until
  10:00 AM. It polls `nvidia-smi` every 30 seconds.
- Allowlist is limited to Ollama, the registered ComfyUI Python runtimes, and
  this repository's local-agent path. Any other resolvable GPU PID is stopped
  and logged; inaccessible PIDs are left untouched and logged for safety.
- The observed Brave GPU process (PID 25892) was stopped as explicitly
  requested. PID 4256 was not resolvable and was left untouched.
