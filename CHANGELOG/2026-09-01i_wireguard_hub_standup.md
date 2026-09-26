# 2026-09-01i — WireGuard hub stood up, Mac joined as first peer

## What happened

Continuation of the multi-node worker-farm setup described in
`docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md` and the scripts
written in `CHANGELOG/2026-09-01h_wireguard_hub_scripts.md`.

All steps executed in one session; nothing was pre-staged.

## Steps completed

### WireGuard installation
- Installed WireGuard 1.1 via `winget install WireGuard.WireGuard`
- Confirmed `wg.exe` and `wireguard.exe` present at `C:\Program Files\WireGuard\`

### Hub keypair + service
- Ran `wireguard\Generate-HubKeypair.ps1` — generated hub keypair, wrote
  `hub.conf` with `Address = 10.90.90.1/28`, `ListenPort = 51820`
- Hub public key: `ABIeyNucK9ctn5hPaDWMkworftoxKfg02kHX9RRl9mM=`
- `wireguard\Install-WireGuardHubService.ps1` (run as Administrator via
  Desktop launcher `InstallWGHub.bat`) — service `WireGuardTunnel$hub`
  already existed and was Running; no reinstall needed
- `Get-NetIPAddress` confirmed `10.90.90.1/28` on interface `hub`

### Firewall
- Added inbound UDP 51820 rule via `AddWGFirewallRule.bat` (run as Admin):
  `Name=WireGuard Hub UDP 51820`, Direction=In, Protocol=UDP, Port=51820,
  Action=Allow, Profiles=Domain,Private,Public — verified OK by netsh output

### Mac peer (node1 / mac_worker)
- Mac ran `Generate-NodeConf.ps1`; generated public key sent back
- First registration used wrong key (`H0IsFuYleREQu...` — `l` and `Q`)
  instead of actual key (`H0IsFuY1eREqu...` — digit `1` and lowercase `q`);
  font ambiguity between `1`/`l` and `Q`/`q` in terminal output
- Corrected directly in `hub.conf` via Edit; hub service restarted via
  `RestartWGHub.bat` (Admin)
- `wg show hub` (Admin) confirmed peer registered:
  `peer: H0IsFuY1eREqu4jWXz94fKR9oC+4qdcBU7d83shvNzo=  allowed ips: 10.90.90.2/32`
- Ping workstation→Mac: 3/3 received, 28-108 ms — tunnel confirmed

### Redis relay
- `netstat` confirmed WireGuard listening on `0.0.0.0:51820` ✓
- Route table confirmed `10.90.90.2/32` on-link via hub interface ✓
- Tunnel relay launched: Python process PID 37428 listening on
  `10.90.90.1:6379 → 127.0.0.1:6379` (max 8 concurrent) — confirmed by
  netstat showing `10.90.90.1:6379 LISTENING`

### Mac credential
- `Add-Phase1SecondaryWorkerCredential.ps1` failed under Windows PowerShell
  5.1: `RandomNumberGenerator.Fill()` is .NET Core/5+ only. Fixed by
  replacing with `$rng.Create() / $rng.GetBytes() / $rng.Dispose()` which
  works in PS 5.1 — see file edit in this session
- Redis broker started via `START_PHASE1_BROKER.ps1` (Docker Desktop was
  stopped; started manually first)
- `mac_worker` ACL user created, scoped to `probe` queue only;
  `.env.mac_worker.generated` written to `local_agent/worker_farm/`

## Files modified

- `local_agent/worker_farm/wireguard/hub.conf` — peer public key corrected
- `local_agent/worker_farm/Add-Phase1SecondaryWorkerCredential.ps1` —
  `RandomNumberGenerator.Fill` → `GetBytes` for PS 5.1 compatibility
- `TODO.md` — worker-farm item updated with completed steps and remaining work

## What remains (not verified)

- Mac: place `.env.mac_worker.generated` as `.env`, install `requirements.txt`,
  run `worker.py --queues probe`
- Workstation: submit `connectivity_probe` task to `probe` queue; confirm
  Mac hostname in result
- ACL DENY probe: verify `mac_worker` cannot read a `distill`-queue or
  `source_*` key
- Record result in same-session CHANGELOG entry per standing rule
- Repeat peer/credential steps for each additional machine (`.3`, `.4`, ...)

## Workstation endpoint reference (for secondary machine node.conf files)

| Item | Value |
|------|-------|
| Hub public key | `ABIeyNucK9ctn5hPaDWMkworftoxKfg02kHX9RRl9mM=` |
| Hub LAN IP | `192.168.50.208` |
| WireGuard port | `51820` |
| Tunnel subnet | `10.90.90.0/28` |
| Next free peer IP | `10.90.90.3` |
