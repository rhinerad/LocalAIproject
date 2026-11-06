# 2026-09-05ai — Pixel edge gateway v1 shipped, server-only, nothing listening

## Scope

🩷 lane, Task #50 build (follows scoping `2026-09-05w`). Reviews Grok's
own build report. No new work from this entry.

## What shipped

`local_agent/edge_gateway/` — SQLite-ledger gateway matching all 10
authorized G1–G10 decisions:

- Phone API (HTTPS + mTLS) bound to `10.90.91.1:8743` only; admin (HTTP)
  bound to `127.0.0.1:8744` only — neither of the forbidden ports
  (6379/8188/11434/11435/8765), confirmed in the design note (G4).
- Claim/complete match the existing inert Termux client contract exactly,
  server-side re-enforcement of all three caps (12,000-char prompt,
  512-token, 16,000-char result) — client checks are not trusted as a
  control, per the design.
- One lease per device; `complete` is idempotent (first result wins,
  a mutating retry gets 409); revoke expires the lease (`complete` after
  revoke returns 401); results stored as untrusted; logs are ids/sizes
  only, never content (G6/G7/G8/G9).
- G3 enforced as a real test, not a comment: a grep-lock confirms
  production sources contain no `FARM_BROKER_URL`/`REDIS_PASSWORD`/
  `celery_app`/`load_dotenv`/`worker_farm` references, plus a
  clean-interpreter import test confirming `celery`/`redis` are never
  loaded.
- Overlay generator (`Generate-EdgePhoneOverlay.ps1`) writes a gitignored
  `runtime/wireguard/` config for the new isolated `10.90.91.0/30`
  overlay (AllowedIPs restricted to the pair) — generation only, not
  `-Install`. Farm hub and Mac WireGuard config were not touched (G1).

19/19 new tests pass; the 3 existing Termux contract tests still pass
unchanged (client file untouched, G10 respected — Termux `--gateway` was
not exercised).

## Confirmed nothing is actually running

`--listen` without `10.90.91.1` bound to a real interface fails closed
(`WinError 10049`, exit 2) — no `0.0.0.0` fallback, and the phone bind is
attempted before the admin bind so admin is never left open alone. After
the attempt, both 8743 and 8744 show `connect_ex` 10061 (nothing
listening). No persistent process is running from this build.

## What was not done

The overlay itself was not brought up (`-Install` is a separate,
deliberate operator step). No real phone contact. Pixel `--once` stays
off per G10 until the workstation service has a real live listen cycle
tested end-to-end, not just unit tests.

## Next

Step 2 of the original PowerInfer-2 mobile edge plan (the actual Pixel
test with `SmallThinker-3B-Preview-abliterated`) is now unblocked at the
design level, but still requires: (1) an operator decision to actually
run `-Install` and bring the overlay up, and (2) the token-ceremony step
(USB/ADB, per G5) before any real device contact.
