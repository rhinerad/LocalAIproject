# 2026-09-01h — WireGuard hub scripts for multi-node worker farm

## What changed

Added `local_agent/worker_farm/wireguard/` with six PowerShell scripts
implementing the WireGuard hub-and-spoke setup described in
`docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md`.

No keys were generated, no service was installed, no config files with
real keys exist yet -- the scripts are the preparation the operator needs
to execute the manual steps themselves. `wireguard/*.key` and
`wireguard/*.conf` are added to `.gitignore` so that generated files
(which contain private keys) can never be committed accidentally.

## Files added

| File | Purpose |
|------|---------|
| `wireguard/Generate-HubKeypair.ps1` | Generates the workstation keypair; writes `hub-private.key`, `hub-public.key`, and the initial `hub.conf` skeleton |
| `wireguard/Add-WireGuardPeer.ps1` | Appends one `[Peer]` block per secondary machine to `hub.conf`; also updates the live interface if the service is already running |
| `wireguard/Install-WireGuardHubService.ps1` | Registers `hub.conf` as a Windows WireGuard tunnel service (requires Administrator) |
| `wireguard/Generate-NodeConf.ps1` | Run on each secondary machine; generates that machine's keypair and `node.conf` with the workstation as its sole peer |
| `wireguard/Test-TunnelConnectivity.ps1` | Pings every `/32` peer from `hub.conf`; shows `wg show hub` for handshake confirmation |
| `wireguard/Start-TunnelRelay.ps1` | Starts `relay/tunnel_relay.py --bind-ip 10.90.90.1`; convenience wrapper that checks the hub interface is up first |

## Files modified

- `local_agent/worker_farm/.gitignore` — added `wireguard/*.key` and `wireguard/*.conf`

## Operator sequence (not executed by this agent)

1. Install WireGuard (manual, already planned)
2. `wireguard\Generate-HubKeypair.ps1` — creates hub.conf + keys on workstation
3. `wireguard\Install-WireGuardHubService.ps1` (as Administrator) — registers hub service
4. On each secondary machine: copy `Generate-NodeConf.ps1`; run it with `-HubPublicKey`, `-ThisNodeTunnelIp`, `-HubLanIp`; send back `node-public.key`
5. On workstation: `wireguard\Add-WireGuardPeer.ps1` once per machine (with that machine's public key and assigned IP)
6. On workstation: `wireguard\Start-TunnelRelay.ps1` (keep running during worker sessions)
7. On each secondary machine: install WireGuard service from `node.conf`
8. `wireguard\Test-TunnelConnectivity.ps1` — confirms each peer pings over tunnel
9. Continue with `Add-Phase1SecondaryWorkerCredential.ps1` and `worker.py --queues probe` per the multi-node plan

## What is NOT verified

No key files exist; no service was installed; no secondary machine was contacted.
Verification is the operator's step after executing the sequence above and
confirming each peer shows a non-zero `latest handshake` in `wg show hub`.
