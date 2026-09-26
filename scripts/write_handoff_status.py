#!/usr/bin/env python3
"""Overwrite repo-root HANDOFF_STATUS.md from CHANGELOG, TODO.md, and seeded docs.

Usage (from the repository root):

  python scripts/write_handoff_status.py

Always overwrites (never appends). Re-run is idempotent: a fresh file from
current sources, no duplicate sections. Optional --output for tests/debug.

Does not probe live processes, start the GUI, GPU jobs, or farm processes.
Orphan and persistence rows are a reviewable seed, not a scrape of prose.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_DIR = REPO_ROOT / "CHANGELOG"
TODO_PATH = REPO_ROOT / "TODO.md"
DEFAULT_OUTPUT = REPO_ROOT / "HANDOFF_STATUS.md"

# Same filename pattern as scripts/next_changelog_id.py.
_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})([a-z]+)_")
_OPEN_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s*\[(?: |~)\]")
RECENT_LIMIT = 15
NOT_DOCUMENTED = "not documented in recent CHANGELOG/runbook"


def letter_sort_key(letter: str) -> tuple[int, str]:
    """Same letter order as next_changelog_id.py: a < b < … < z < aa."""
    return (len(letter), letter)


@dataclass(frozen=True)
class ChangelogEntry:
    path: Path
    date: str
    letter: str

    @property
    def changelog_id(self) -> str:
        return f"{self.date}{self.letter}"


@dataclass(frozen=True)
class OrphanSeed:
    name: str
    machine: str
    source: str
    status: str


@dataclass(frozen=True)
class PersistenceSeed:
    service: str
    machine: str
    source: str
    status: str


# Seeded from tonight's documented CHANGELOG/runbook text only.
# Do not live-probe. Do not invent extra orphans.
ORPHANS: tuple[OrphanSeed, ...] = (
    OrphanSeed(
        name="Crash-looping leftover Mac LaunchAgent `com.local-agent.celery-worker`",
        machine="Louises-MBP / 10.90.90.2",
        source=(
            "CHANGELOG/2026-09-03e_farm_health_runbook.md; "
            "docs/FARM_HEALTH_RUNBOOK.md"
        ),
        status=(
            "Leftover (not the WG root cause): crash-looping LaunchAgent "
            "`com.local-agent.celery-worker`. Replaced in place with farm `.env` "
            "wrapper, queues `probe,judge,summarize,embed`, `ThrottleInterval` 10."
        ),
    ),
    OrphanSeed(
        name="Pre-existing Mac LaunchDaemon `com.local-agent.wireguard-wg0`",
        machine="Louises-MBP / 10.90.90.2",
        source=(
            "CHANGELOG/2026-09-03e_farm_health_runbook.md; "
            "docs/FARM_HEALTH_RUNBOOK.md"
        ),
        status=(
            "Loaded, had not been running (last exit 1); `/usr/local/bin/wg-quick` "
            "shebang `env bash` hit launchd PATH bash 3.2 vs Homebrew bash 4+. "
            "Later kickstarted; restored ~1:19 AM ET to LaunchDaemon/`wireguard-go`. "
            "Reboot persistence is not confirmed. Do **not** install a second "
            "daemon `com.local-agent.wg-quick`. One label: "
            "`com.local-agent.wireguard-wg0`."
        ),
    ),
    OrphanSeed(
        name=(
            "WireGuard.app login item "
            "`gui/503/com.wireguard.macos.login-item-helper` / "
            "Network Extension `workstation_gateway` owning `utun5`"
        ),
        machine="Louises-MBP / 10.90.90.2",
        source=(
            "CHANGELOG/2026-09-03e_farm_health_runbook.md; "
            "docs/FARM_HEALTH_RUNBOOK.md"
        ),
        status=(
            "Login item was on; app + Network Extension owned `utun5` "
            "(`workstation_gateway`); handshake never completed. Disabled during "
            "datapath restore ~1:19 AM ET (`scutil --nc stop workstation_gateway`; "
            "quit WireGuard.app/NE)."
        ),
    ),
    OrphanSeed(
        name="Leftover `tunnel_relay.py` process (PID 37480 documented)",
        machine="DuranGamingPC / Windows hub",
        source=(
            "CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md"
        ),
        status=(
            "Stopped leftover `python.exe` PID 37480 running "
            "`local_agent/worker_farm/relay/tunnel_relay.py --bind-ip 10.90.90.1`. "
            "Current listener is the logon task from `2026-09-03s` / "
            "`2026-09-04a`, not that leftover PID."
        ),
    ),
    OrphanSeed(
        name="Boot/S4U task `\\local-agent-tunnel-relay` still not registered",
        machine="DuranGamingPC / Windows hub",
        source=(
            "CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md; "
            "CHANGELOG/2026-09-03s_tunnel_relay_logon_interactive_task.md; "
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md"
        ),
        status=(
            "Approved S4U At-startup task was **not** registered (03h Access "
            "Denied / 0x80070005). Fallback is LogonTrigger + InteractiveToken "
            "(`2026-09-03s`). That logon task started at delayed interactive "
            "logon 2026-09-04 00:18:03 (`2026-09-04a`); Listen on "
            "`10.90.90.1:6379`. Pre-login / Session-0 relay remains the gap. "
            "Do not retry `Register-ScheduledTask` without an elevation plan."
        ),
    ),
    OrphanSeed(
        name="Windows Task `\\local-agent-farm-status-daemon`",
        machine="DuranGamingPC / Windows hub",
        source=(
            "CHANGELOG/2026-09-03f_windows_farm_status_daemon_task.md; "
            "CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md; "
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md"
        ),
        status=(
            "03f created the per-user logon task (InteractiveToken, Limited, "
            "Hidden, RestartCount 999 / PT1M, ExecutionTimeLimit PT0S). 03h set "
            "`StopOnIdleEnd` false. Real delayed logon start verified "
            "`2026-09-04a`: Last Run 2026-09-04 00:18:03 with explorer / "
            "User Profile Service session 1 (not `Start-ScheduledTask`)."
        ),
    ),
)


# Prefer the newest lettered changelog that addresses each service (03i > 03h
# where 03i restates it). Do not assume up/down beyond these sentences.
PERSISTENCE: tuple[PersistenceSeed, ...] = (
    PersistenceSeed(
        service="WireGuard",
        machine="DuranGamingPC / Windows hub (`WireGuardTunnel$hub` / 10.90.90.1)",
        source=(
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md "
            "(hub UP also in CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md / "
            "CHANGELOG/2026-09-03e_farm_health_runbook.md / "
            "docs/FARM_HEALTH_RUNBOOK.md)"
        ),
        status=(
            "`2026-09-04a` post-logon of the 23:35:43.500 boot: adapter `hub` "
            "Status Up; `10.90.90.1/28` Preferred; service "
            "`WireGuardTunnel$hub` Running / Automatic."
        ),
    ),
    PersistenceSeed(
        service="WireGuard",
        machine="Louises-MBP / 10.90.90.2 (`utun5` / LaunchDaemon)",
        source=(
            "CHANGELOG/2026-09-03i_session_handoff.md; "
            "docs/FARM_HEALTH_RUNBOOK.md; "
            "CHANGELOG/2026-09-03e_farm_health_runbook.md"
        ),
        status=(
            "Restored ~1:19 AM ET to LaunchDaemon/`wireguard-go` as root; login "
            "item disabled. **Reboot persistence is not confirmed.** Do not "
            "reboot unless Rhine explicitly says to. Loaded launchd job may "
            "still be stale vs the patched plist until `bootout`+`bootstrap` "
            "or a planned reboot."
        ),
    ),
    PersistenceSeed(
        service="Celery worker",
        machine="DuranGamingPC / Windows hub",
        source="",
        status=NOT_DOCUMENTED,
    ),
    PersistenceSeed(
        service="Celery worker",
        machine="Louises-MBP / 10.90.90.2 (`celery@Louises-MBP`)",
        source=(
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md "
            "(03e restore: docs/FARM_HEALTH_RUNBOOK.md / "
            "CHANGELOG/2026-09-03e_farm_health_runbook.md)"
        ),
        status=(
            "After delayed logon 00:18:03, workstation `farm_health --json` "
            "`status=ok`, `workers_responding=true`, worker "
            "`celery@Louises-MBP`, expected tasks registered "
            "(`2026-09-04a`)."
        ),
    ),
    PersistenceSeed(
        service="tunnel_relay",
        machine="DuranGamingPC / Windows hub",
        source=(
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md; "
            "CHANGELOG/2026-09-03s_tunnel_relay_logon_interactive_task.md; "
            "CHANGELOG/2026-09-03am_tunnel_relay_logon_self_start_verified.md"
        ),
        status=(
            "LogonTrigger / InteractiveToken task `\\local-agent-tunnel-relay` "
            "started 2026-09-04 00:18:03 on delayed interactive logon; Listen "
            "`10.90.90.1:6379` python 15260; Mac `10.90.90.2` Established. "
            "Boot/S4U registration still failed (03h); relay is dark until "
            "rhine logs on."
        ),
    ),
    PersistenceSeed(
        service="tunnel_relay",
        machine="Louises-MBP / 10.90.90.2",
        source="",
        status=NOT_DOCUMENTED,
    ),
    PersistenceSeed(
        service="WSL Docker CE (Ubuntu-24.04)",
        machine="DuranGamingPC / Windows hub",
        source=(
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md; "
            "CHANGELOG/2026-09-03au_wsl_docker_boot_delayed_login_watchdog_alive.md"
        ),
        status=(
            "BootTrigger S4U task `\\local-agent-wsl-docker-boot` (RunAs rhine, "
            "PT30S) fired on the 23:35:43.500 boot: Last Run 23:36:27, Docker "
            "29.7.2, `wsl-boot-probe` running, same `SOURCE=boot` instance "
            "through delayed logon 00:18:03 (`RESULT=ALIVE`, `2026-09-04a`). "
            "Farm Redis is on this engine (`2026-09-03bg` / `bh`)."
        ),
    ),
    PersistenceSeed(
        service="Redis/Docker",
        machine="DuranGamingPC / Windows hub",
        source=(
            "CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md; "
            "CHANGELOG/2026-09-03bh_wsl_redis_cutover_reboot_pass.md; "
            "CHANGELOG/2026-09-03bg_wsl_redis_phase_c_cutover.md"
        ),
        status=(
            "Phase C persisted the 23:35:43.500 boot (`2026-09-03bh` PASS; "
            "post-logon reconfirm `2026-09-04a`): Ubuntu-24.04 Docker CE "
            "`local-agent-phase1-redis` (`6ea76294c9cf`) StartedAt 23:36:52 "
            "healthy; Windows `127.0.0.1:6379` is wslrelay (not "
            "`com.docker.backend`). PING PONG; ACL `default` `mac_worker`. "
            "Desktop AutoStart off, HKCU Run Docker Desktop absent, "
            "`docker-desktop` distro Stopped."
        ),
    ),
    PersistenceSeed(
        service="Redis/Docker",
        machine="Louises-MBP / 10.90.90.2",
        source="",
        status=NOT_DOCUMENTED,
    ),
)


def generated_at_local() -> str:
    now = datetime.now().astimezone()
    name = now.tzname() or ""
    offset = now.strftime("%z")
    if offset:
        pretty = f"UTC{offset[:-2]}:{offset[-2:]}"
        label = f"{name} ({pretty})" if name else pretty
    else:
        label = name
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {label}".strip()


def iter_changelog_entries(changelog_dir: Path) -> list[ChangelogEntry]:
    entries: list[ChangelogEntry] = []
    if not changelog_dir.is_dir():
        return entries
    for path in changelog_dir.iterdir():
        if not path.is_file():
            continue
        match = _NAME_RE.match(path.name)
        if not match:
            continue
        entries.append(ChangelogEntry(path=path, date=match.group(1),
                                      letter=match.group(2)))
    # Stable: filename ascending, then newest-first by date then letter.
    entries.sort(key=lambda e: e.path.name)
    entries.sort(key=lambda e: (e.date, letter_sort_key(e.letter)), reverse=True)
    return entries


def first_heading(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.lstrip("\ufeff").rstrip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            return heading or None
    return None


def title_for(entry: ChangelogEntry) -> str:
    heading = first_heading(entry.path)
    if heading:
        return heading
    stem = entry.path.stem
    prefix = entry.changelog_id + "_"
    slug = stem[len(prefix):] if stem.startswith(prefix) else stem
    return slug.replace("_", " ")


def recent_changelog_lines(entries: list[ChangelogEntry],
                           limit: int = RECENT_LIMIT) -> list[str]:
    lines: list[str] = []
    for entry in entries[:limit]:
        title = title_for(entry)
        lines.append(
            f"- {entry.date} · `{entry.changelog_id}` · `{entry.path.name}` — {title}"
        )
    return lines


def open_todo_lines(todo_path: Path) -> list[str]:
    if not todo_path.is_file():
        return []
    try:
        text = todo_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = todo_path.read_text(encoding="utf-8", errors="replace")
    found: list[str] = []
    for line in text.splitlines():
        if _OPEN_ITEM_RE.match(line):
            found.append(line)
    return found


def render_orphans() -> list[str]:
    lines: list[str] = []
    for item in ORPHANS:
        lines.append(f"### {item.name}")
        lines.append("")
        lines.append(f"- **Machine:** {item.machine}")
        lines.append(f"- **Source:** `{item.source}`")
        lines.append(f"- **Documented status:** {item.status}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def render_persistence() -> list[str]:
    lines: list[str] = []
    for item in PERSISTENCE:
        lines.append(f"### {item.service} — {item.machine}")
        lines.append("")
        if item.source:
            lines.append(f"- **Source:** `{item.source}`")
        else:
            lines.append("- **Source:** (none in recent CHANGELOG/runbook)")
        lines.append(f"- **Documented status:** {item.status}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def build_markdown(changelog_dir: Path, todo_path: Path) -> str:
    entries = iter_changelog_entries(changelog_dir)
    recent = recent_changelog_lines(entries)
    open_items = open_todo_lines(todo_path)
    parts: list[str] = [
        "# HANDOFF_STATUS",
        "",
        "This file is **generated** and is overwritten on every run (never append).",
        "Do not edit it by hand.",
        "",
        "Regenerate from the repository root:",
        "",
        "```",
        "python scripts/write_handoff_status.py",
        "```",
        "",
        f"Generated at: {generated_at_local()} (local)",
        "",
        "`TODO.md` is the execution queue. Lettered `CHANGELOG/` entries are "
        "evidence. Farm *procedures* live in `docs/FARM_HEALTH_RUNBOOK.md` and "
        "`docs/RUNBOOK.md` — this file points to those runbooks and does **not** "
        "duplicate their checklists.",
        "",
        "**Caveats (not a live probe):** open TODO items are the checkbox line "
        "only — wrapped continuation lines in `TODO.md` are omitted. Orphan and "
        "persistence sections are seeded from documented CHANGELOG/runbook text, "
        "not from live process/service checks.",
        "",
        "---",
        "",
        "## 1. Recent CHANGELOG (last ~15)",
        "",
        "Newest first, so a new agent sees tonight first. Lettered files matching "
        "`YYYY-MM-DDx_...` only; same letter-order as "
        "`scripts/next_changelog_id.py` (`a` < `b` < … < `z` < `aa`). Same-day "
        "duplicate letters both appear, disambiguated by filename. Title is the "
        "first markdown `#` heading, else the filename slug.",
        "",
    ]
    if recent:
        parts.extend(recent)
    else:
        parts.append("(no lettered CHANGELOG files found)")
    parts.extend([
        "",
        "---",
        "",
        "## 2. Open TODO.md items",
        "",
    ])
    if not todo_path.is_file():
        parts.append("`TODO.md` is missing.")
    else:
        parts.append(
            f"{len(open_items)} open items (`[ ]` or `[~]`; closed `[x]` omitted). "
            "Checkbox lines copied verbatim from `TODO.md` (first line of each "
            "item only — wrapped continuations omitted):"
        )
        parts.append("")
        if open_items:
            parts.extend(open_items)
        else:
            parts.append("(no open checkbox lines)")
    parts.extend([
        "",
        "---",
        "",
        "## 3. Known orphaned / leftover infrastructure",
        "",
        "Seeded from tonight's documented CHANGELOG/runbook text only. "
        "**Not** live-probed. Do not treat this list as current OS state.",
        "",
    ])
    parts.extend(render_orphans())
    parts.extend([
        "",
        "---",
        "",
        "## 4. Persistence / supporting services",
        "",
        "Most recent documented CHANGELOG/runbook sentence for each service on "
        "each machine the docs mention. If a service was not documented: "
        f"`{NOT_DOCUMENTED}`. **Not** live-probed. Procedures: "
        "`docs/FARM_HEALTH_RUNBOOK.md` and `docs/RUNBOOK.md`.",
        "",
    ])
    parts.extend(render_persistence())
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Overwrite HANDOFF_STATUS.md from CHANGELOG, TODO.md, and seeded docs.")
    parser.add_argument(
        "--output",
        default=None,
        help="output path (default: repo-root HANDOFF_STATUS.md)",
    )
    args = parser.parse_args()
    output = Path(args.output) if args.output else DEFAULT_OUTPUT
    text = build_markdown(CHANGELOG_DIR, TODO_PATH)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
