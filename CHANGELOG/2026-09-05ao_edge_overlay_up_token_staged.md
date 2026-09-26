# 2026-09-05ao — Edge overlay live, token staged, waiting on physical USB

## Scope

🩷 lane. Tracking entry for Grok's own report. No new work from this
entry.

## What's confirmed live

Overlay (`edge-phone`, `10.90.91.1/30`, workstation peer AllowedIPs
restricted to `10.90.91.2/32` only) is up via an isolated installer
(`Desktop\Install-EdgePhoneOverlay.bat`), separate from the farm hub
installer. Farm hub confirmed untouched: still running, `hub.conf`
SHA-256 unchanged, Mac WireGuard config not edited (G1 boundary held).

Both gateway listeners are real this time (not the unit-test
`connect_ex 10061`): `10.90.91.1:8743` (phone API) and `127.0.0.1:8744`
(admin) both show `Listen`/`connect_ex 0`. `0.0.0.0:8743` correctly not
bound. A watcher is monitoring both sockets for drops.

Device token issued for `pixel1` only, scoped to `["edge_text_inference"]`
only, 43-char token (>= the 24-char minimum), ledger stores only the hash
+ cert fingerprint — not the plaintext token. mTLS client cert/key/CA
written to a workstation-only path (ACL: SYSTEM + operator account only).
Zero jobs queued (G6 not started, correctly).

## Where it stopped, and why

USB/ADB delivery (G5) did not complete: `adb` listed no device, so
nothing was pushed to the phone. This is not a failure — it's the
correct behavior (fail-closed, no Wi-Fi/chat fallback copy of the token
was attempted). Termux `--gateway` was not run, no claim/complete cycle,
no prompt injected. Everything stops here until the Pixel is physically
connected.

## What was noted, not concerning

First UAC elevation prompt was canceled (operator action, not an error);
a second elevation via the isolated installer script succeeded. No
Windows Firewall dialog appeared and no new firewall rule was added for
8743 — noted as something that will matter once the phone itself needs
to reach that port, not for the current loopback/overlay-only binds.

## Next physical step needed

Plug the Pixel into the workstation over USB with USB debugging enabled,
then the token push can complete and the first real (still G6-gated,
one benign operator-injected prompt) claim/complete cycle can run.
