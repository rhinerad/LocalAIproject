# 2026-08-29 — Worker-farm Redis health-check repair

## What changed

`local_agent/worker_farm/compose.yaml` now passes `REDIS_PASSWORD` into the
Redis container's environment, in addition to using it in the Redis command.

## Why

The container correctly required the configured password and accepted loopback
connections, but the Compose health check used `$REDIS_PASSWORD` within the
container where that variable had not been supplied. It therefore stayed
`health: starting` despite a healthy server.

## Safety / verification

- The port remains `127.0.0.1:6379` only.
- The password is not printed, committed, or exported beyond the Redis
  container and the existing local `.env`.
- Recreating the Redis service applies only the checked-in health-check fix;
  its named volume is retained.
