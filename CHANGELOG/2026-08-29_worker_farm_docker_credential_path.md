# 2026-08-29 — Worker-farm Docker credential-helper path repair

## What changed

`local_agent/worker_farm/START_PHASE1_BROKER.ps1` now prepends Docker Desktop's
installed `resources\\bin` directory to **its own process** `PATH` when the
`docker-credential-desktop.exe` helper exists but is absent from `PATH`.

## Why

After Docker Desktop's runtime-socket recovery, the guarded loopback Redis
launcher reached the engine but Compose could not pull `redis:7-alpine` because
it could not locate `docker-credential-desktop`. The helper was installed at
the standard Docker Desktop location; only the launcher environment lacked its
directory.

## Safety / verification

- No credentials, Docker configuration, or system-wide environment variable was
  changed.
- The path change exists only for the launcher process.
- The failed pre-repair launcher stopped before creating the Redis container.
- The next step is to rerun the guarded broker launcher, verify its loopback
  binding, then start the CPU-only worker and benign sample separately.
