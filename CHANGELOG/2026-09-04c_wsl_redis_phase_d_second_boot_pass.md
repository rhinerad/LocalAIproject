# 2026-09-04c - WSL Redis Phase D second-boot proof PASS

Date: 2026-09-04. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: PASS.** Phase D second boot: Ubuntu CE Redis StartedAt after LastBootUpTime and before explorer; 127.0.0.1:6379 is wslrelay; mac_worker present

Phase D of `2026-09-03az`. First cutover boot was `2026-09-03bh` / `2026-09-04a` (LastBootUpTime 2026-09-03 23:35:43.500). This entry is a distinct reboot.

## Clock

- Windows LastBootUpTime: 2026-09-04 01:24:37.500
- Evidence at: 2026-09-04 01:27:38.687 (elapsed 181s)
- explorer start: 
- Ubuntu CE redis: status=running StartedAt=2026-09-04T05:25:45.041762933Z health=healthy
- Windows 127.0.0.1:6379 owner: wslrelay pid 15448
- ACL mac_worker present: True
- Desktop AutoStart: False  HKCU Run Docker Desktop present: False

Desktop volume not deleted. Id from next_changelog_id.py: **2026-09-04c**.
