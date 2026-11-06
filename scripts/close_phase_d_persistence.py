#!/usr/bin/env python3
"""Close 2026-09-03az Phase D only after a second distinct cutover boot PASS.

Reads wsl-boot-probe/redis-cutover-proof-result.json. Refuses if verdict is
not PASS, if LastBootUpTime is still the 2026-09-03bh boot, or if mac_worker
is missing. Patches docs/ARCHITECTURE.md and the write_handoff_status.py
Redis/Docker seeds, then regenerates HANDOFF_STATUS.md.

Does not delete the Desktop Redis volume.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIOR_BOOT_PREFIX = "2026-09-03 23:35:43"
PRIOR_STARTED = "2026-09-04T03:36:52.135339577Z"

ARCH_PROVEN_OLD = (
    "Proven at boot: `2026-09-03au` (Docker CE keep-alive), Phase C cutover "
    "`2026-09-03bg`, delayed-login Redis proof `2026-09-03bh`, post-logon "
    "reconfirm `2026-09-04a`."
)

ARCH_CLOSED_OLD = (
    "Workstation Redis-at-boot on Ubuntu CE is closed "
    "(`2026-09-03bg`/`bh`/`2026-09-04a`)."
)

HANDOFF_REDIS_OLD = (
            "Phase C persisted the 23:35:43.500 boot (`2026-09-03bh` PASS; "
            "post-logon reconfirm `2026-09-04a`): Ubuntu-24.04 Docker CE "
            "`local-agent-phase1-redis` (`6ea76294c9cf`) StartedAt 23:36:52 "
            "healthy; Windows `127.0.0.1:6379` is wslrelay (not "
            "`com.docker.backend`). PING PONG; ACL `default` `mac_worker`. "
            "Desktop AutoStart off, HKCU Run Docker Desktop absent, "
            "`docker-desktop` distro Stopped."
        )

HANDOFF_WSL_OLD = (
            "BootTrigger S4U task `\\local-agent-wsl-docker-boot` (RunAs rhine, "
            "PT30S) fired on the 23:35:43.500 boot: Last Run 23:36:27, Docker "
            "29.7.2, `wsl-boot-probe` running, same `SOURCE=boot` instance "
            "through delayed logon 00:18:03 (`RESULT=ALIVE`, `2026-09-04a`). "
            "Farm Redis is on this engine (`2026-09-03bg` / `bh`)."
        )


def load_result(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text)


def require_second_boot(ev: dict) -> None:
    verdict = ev.get("verdict")
    if verdict != "PASS":
        raise SystemExit(f"refuse: verdict={verdict!r} reason={ev.get('reason')!r}")
    boot = str(ev.get("lastBootUpTime") or "")
    if boot.startswith(PRIOR_BOOT_PREFIX):
        raise SystemExit(
            f"refuse: LastBootUpTime={boot!r} is still the 2026-09-03bh boot"
        )
    started = str(ev.get("redisStartedAt") or "")
    if started == PRIOR_STARTED:
        raise SystemExit(
            f"refuse: redisStartedAt={started!r} is still the first-cutover container start"
        )
    if not ev.get("macWorkerPresent"):
        raise SystemExit("refuse: mac_worker not present in ACL USERS")


def patch_file(path: Path, old: str, new: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return f"{label}: already patched"
    if old not in text:
        raise SystemExit(f"{label}: expected text not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"{label}: patched"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--changelog-id", required=True)
    args = parser.parse_args()
    result_path = Path(args.result)
    ev = load_result(result_path)
    require_second_boot(ev)
    cid = args.changelog_id.strip()
    if not cid:
        raise SystemExit("missing --changelog-id")

    arch = REPO_ROOT / "docs" / "ARCHITECTURE.md"
    proven_new = (
        "Proven at boot: `2026-09-03au` (Docker CE keep-alive), Phase C cutover "
        "`2026-09-03bg`, first delayed-login Redis proof `2026-09-03bh` (same boot "
        "reconfirm `2026-09-04a`), **Phase D second-boot persistence proof "
        f"`{cid}`**. Two distinct `LastBootUpTime` values now show Ubuntu CE Redis "
        "StartedAt after boot and before explorer, Windows `127.0.0.1:6379` as "
        "`wslrelay`, and ACL `mac_worker` present. Phase D persistence claim is closed."
    )
    closed_new = (
        "Workstation Redis-at-boot on Ubuntu CE is closed after two boots "
        f"(`2026-09-03bg`/`bh`/`2026-09-04a` first boot; `{cid}` Phase D second boot)."
    )

    notes = [
        patch_file(arch, ARCH_PROVEN_OLD, proven_new, "ARCHITECTURE proven-at-boot"),
        patch_file(arch, ARCH_CLOSED_OLD, closed_new, "ARCHITECTURE closed-sentence"),
    ]

    handoff_py = REPO_ROOT / "scripts" / "write_handoff_status.py"
    redis_new = (
            f"Phase D closed on second boot `{cid}` (first cutover boot was "
            "23:35:43.500 / `2026-09-03bh` + `2026-09-04a`). Ubuntu-24.04 Docker CE "
            f"`local-agent-phase1-redis` StartedAt {ev.get('redisStartedAt')} "
            f"status={ev.get('redisStatus')} health={ev.get('redisHealth')}; "
            "Windows `127.0.0.1:6379` is wslrelay (not `com.docker.backend`). "
            "ACL includes `mac_worker`. Desktop AutoStart off, HKCU Run Docker "
            "Desktop absent. Desktop volume not deleted."
        )
    wsl_new = (
            "BootTrigger S4U task `\\local-agent-wsl-docker-boot` (RunAs rhine, "
            f"PT30S) fired on the Phase D second boot `{cid}` "
            f"(LastBootUpTime {ev.get('lastBootUpTime')}). Farm Redis stays on "
            "this engine (`2026-09-03bg` / `bh` / Phase D). First cutover boot "
            "was 23:35:43.500 (`2026-09-03bh` / `2026-09-04a`)."
        )
    notes.append(patch_file(handoff_py, HANDOFF_REDIS_OLD, redis_new, "handoff Redis seed"))
    notes.append(patch_file(handoff_py, HANDOFF_WSL_OLD, wsl_new, "handoff WSL seed"))

    regen = subprocess.run(
        [sys.executable, str(handoff_py)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if regen.returncode != 0:
        raise SystemExit(
            f"write_handoff_status.py failed: {regen.stderr or regen.stdout}"
        )
    notes.append("HANDOFF_STATUS.md regenerated")
    print("\n".join(notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
