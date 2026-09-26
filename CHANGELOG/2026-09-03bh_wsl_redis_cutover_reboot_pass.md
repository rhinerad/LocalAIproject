# 2026-09-03bh - WSL Redis cutover delayed-login proof PASS

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: PASS.** Ubuntu CE Redis StartedAt after LastBootUpTime and before explorer; 127.0.0.1:6379 is wslrelay

Phase C of `2026-09-03az`. Live cutover recorded in `2026-09-03be` launchers + this boot.

## Clock

- Windows LastBootUpTime: 2026-09-03 23:35:43.500
- Evidence at: 2026-09-03 23:38:45.328 (elapsed 182s)
- explorer start: 
- Ubuntu CE redis: status=running StartedAt=2026-09-04T03:36:52.135339577Z health=healthy
- Windows 127.0.0.1:6379 owner: wslrelay pid 4488
- Desktop AutoStart: False  HKCU Run Docker Desktop present: False

Id from next_changelog_id.py: **2026-09-03bh**.
