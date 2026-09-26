# 2026-09-08 — Watchdog stall recovery

The production watchdog detected the isolated ComfyUI startup had made no
progress for over 15 minutes and had not exposed its API. Only the owned
production worker tree was terminated (PID 6088 and children); the separate
Comfy Desktop process was not touched. The durable ledger and all prior output
files were preserved. Production was restarted with supervisor PID 11728 using
the corrected prompt revision and 600-second bounded readiness window.
