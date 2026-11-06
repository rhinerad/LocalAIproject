# 2026-09-05bu — Status sync: handoff written, disk D confirmed, token staged securely

## Scope

Operator-facing tracking entry for three reports (`2026-09-05br`/disk-D
verification/`2026-09-05bt`). No new production work from this entry.

## Handoff doc written (Green)

`docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-05.md` written, superseding
09-04, `HANDOFF_STATUS.md` regenerated. 68 CHANGELOG letters today
(a-bs). Three reserved-but-unwritten letters found: `h`, `p`, `ab` — no
file exists for any of them. Not concerning: this is the documented risk
of parallel Grok sessions reserving a letter via
`next_changelog_id.py` and then not writing it (aborted attempt,
collision avoidance) — nothing was lost, those letters are just unused.
Two corrections surfaced by the report itself: the Android companion is
further along than assumed when the task was dispatched (PR 1 + PR 2
both shipped, not "underway"), and the farm semantic judge is fully
shipped default-off, not just designed — both are just timing artifacts
of when the handoff task was dispatched vs. when those other lanes
finished, not errors.

## Disk D: confirmed as a real second failure domain (Purple)

D: is a genuinely separate physical disk (Seagate Portable, USB bus,
unique disk ID `3E543346485A464B`) — not a partition/slice of A: (Toshiba
SATA) or C: (Lexar NVMe), confirmed via `Get-Partition` disk-number
mapping and distinct hardware IDs. ~1.2TB free, far past the ~7GB first
evidence pass. Two real caveats, not blockers: (1) D: is currently
plugged into this chassis — for the two-failure-domain story to hold
against a site incident (fire/theft), it needs to be unplugged and
stored elsewhere between backup runs, same requirement as the original
"dedicated USB" option; (2) D: already has unrelated data on it
(home videos, other backups) — the runbook wanted a dedicated destination,
so a new folder for the Restic repo is fine, using the whole volume is
not. exFAT is confirmed fine for a Restic repo since Restic's own
encryption is the confidentiality layer, not the filesystem.

No Restic installed, no key created, no `ARCHIVE_DECISION.md` written —
still waiting on the operator's final confirmation.

## Termux token path found (Pink)

Root cause confirmed: this specific Termux build
(`googleplay.2026.06.21`, targetSdk 37) is not debuggable, so `run-as`
doesn't work, and `/data/local/tmp` is `700 shell` — genuinely
unreadable by Termux regardless of ADB authorization. The secure fix:
`/sdcard/Android/data/com.termux/files/` is app-private external
storage (`2770 u0_a320:ext_data_rw`) that other apps cannot traverse,
even though ADB shell can write to it. Token is now staged there
(`.../powerinfer-edge/`, permissions set so Termux's "other" bits can
read it since `chown` to Termux's uid isn't permitted from shell),
hash-verified. `~/storage` (the broadly-shared path from
`termux-setup-storage`) was correctly avoided.

Remaining: one Termux-side `cp` into `~/.config/local-agent/`, `chmod 600`,
then delete the staging copy. No `--once` run yet.

## Status

Purple needs final operator confirmation on the D:+C: pair (with the
unplug-between-runs caveat) before writing `ARCHIVE_DECISION.md`. Pink
needs one more physical step at the phone.
