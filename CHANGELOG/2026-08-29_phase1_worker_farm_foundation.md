# 2026-08-29 — Phase 1 local worker-farm foundation

## What changed

- Added `local_agent/worker_farm/`, a separate CPU-only asynchronous-work
  package. Its checked-in Compose definition binds Redis only to `127.0.0.1`.
- Added an allow-listed historical-export distillation workflow. It stages raw
  JSON/HTML/text sources into AES-256-GCM artifacts and produces only
  `review_required` candidates. It cannot write Chroma or active memory, call
  a render, execute arbitrary commands, load a model, or start remote workers.
- Added an encrypted artifact store with 96-bit random GCM nonces, authenticated
  associated artifact IDs, atomic file replacement, SHA-256 plaintext integrity
  checks, and path/sensitive-value sanitization for review output.
- Added conservative Celery settings (JSON only, authenticated broker URL,
  late acknowledgement, lost-worker rejection, one-item prefetch) and safe
  Windows/Android `solo` worker mode.
- Added `doctor.py`, `.env.example`, a local secret initializer, and guarded
  broker/CPU-worker PowerShell launchers. They refuse example placeholders and
  do not install or start any component automatically. The `.env` is excluded
  from source control; a restrictive custom ACL was removed because it blocked
  the worker process from reading its own configuration.
- Corrected the guarded CPU-worker/sample launchers to use the isolated worker
  `.venv` explicitly rather than whichever global Python happens to be first
  on PATH.
- Corrected artifact-store initialization to validate the AES-256 key before
  creating an artifact directory; malformed keys now fail without any storage
  side effect.
- Corrected generated Redis credentials to use URL-safe random text. This keeps
  Celery's `redis://` broker URLs valid even when random bytes would otherwise
  contain `/` or `+`.
- Added a non-destructive repair for pre-correction `.env` files: it URL-encodes
  only the broker URL password and preserves the existing Redis password and
  AES key, so any encrypted artifacts stay recoverable.
- Added the Phase 1 metadata-only SQLite job ledger and a regression test. It
  de-duplicates work using the stable source idempotency hash (not newly staged
  opaque IDs), permits one atomic claim, and records completion without storing
  raw source text in SQLite.
- Added explicit startup/status output and an engine readiness check to the
  broker, CPU-worker, and sample scripts so a failed or waiting terminal is
  diagnosable rather than silently blank.
- Added `START_PHASE1_BROKER_VISIBLE.cmd`, which opens an intentionally visible
  diagnostic console and pauses after execution when an existing PowerShell
  launch context hides output.
- Added a metadata-only job-status command. It surfaces job state and failure
  code without exposing idempotency hashes, artifact IDs, source text, Redis
  credentials, or encryption keys.
- Added bounded deterministic JSON/HTML export extraction: JSON is flattened,
  HTML uses only visible text, and scripts/styles are discarded before the
  existing sanitizer/candidate reviewer. The original source remains immutable
  in the encrypted artifact.
- Corrected the mocked agentic-evaluation harness: its project-document case
  is explicitly CPU-preferred, preventing an optional GPU planner route from
  making a supposedly deterministic, model-free regression test stall.
- Corrected context trimming so internal system inserts or a one-message turn
  cannot trigger the optional CPU compactor. Genuine older conversation must
  meet a two-message/600-character threshold, and the best-effort compactor
  timeout is now 12 seconds rather than 120.
- Corrected the busy-GPU picker regression expectation to preserve the
  operator-requested 14B model as visible-but-disabled during a render, rather
  than treating its intentionally retained picker entry as a failure.
- Fixed the underlying fresh-busy-start picker behavior: when no verified GPU
  catalogue cache exists, the 14B now appears as an explicit disabled entry
  rather than disappearing. The regression test resets cached GPU state so it
  validates that case deterministically.
- Updated `TODO.md`, the Worker Farm plan, current handoff, and persistent
  memory to distinguish the active local foundation from deferred remote/cluster
  phases.

## Why

The operator requested Phase 1 now, while retaining an RTX-only interactive
control plane and avoiding surprise GPU, render, phone, or network activity.
The prior record was planning-only and had no executable local safety boundary.

## Evidence

- `python -m unittest local_agent.worker_farm.test_farm_core -v` — 6/6 passed:
  encryption/sanitization, review-only output, JSON/HTML visible-text
  extraction, invalid-key refusal, idempotent registration, and one-time job
  claim.
- The isolated `.venv` now contains Celery 5.6.3, Redis client 6.4.0, and
  Cryptography 46.0.7. Docker Desktop 4.88.1 is installed and its engine
  reports version 29.7.2 when launched under the approved desktop context.
  The local secret initializer generated a non-placeholder Redis password and
  an exact 44-character base64 AES-256 key without printing either secret.
- Local-agent offline regression groups passed: 49/49 core loop/LXMF/scheduler,
  105/105 routing/permission/storage, 57/57 general-assistant/workspace/
  retrieval, and 85/85 media/vision/3D safeguards. No service, render, or
  model workload was started by these mocked/deterministic tests.
- `python local_agent\\validate_h3_prompt.py --dir outputs\\equal_shares\\prompts_native_r2v`
  — `124/124 valid`.
- Expanded the worker-farm doctor into a bounded, read-only diagnostic: it finds
  Docker even before PATH refresh, probes engine access with a five-second cap,
  checks local configuration shape without exposing secrets, and probes only the
  loopback Redis port with a one-second timeout.
- Fixed the Phase 1 transient-retry ledger state: an `OSError` now returns a
  claimed job to `queued` before Celery's bounded retry, rather than leaving a
  retry delivery silently deduplicated as a permanent failure.
- Added `RUN_PHASE1_DOCTOR.ps1`, so the readiness report always runs through
  the isolated worker environment rather than accidentally reporting missing
  optional packages from the system Python installation.
- Verification after the reliability changes: `python -m unittest
  local_agent.worker_farm.test_farm_core -v` passed 12/12, including the
  no-secret doctor report and transient-retry ledger tests. The guarded doctor
  launcher correctly reported valid configuration but unavailable Docker-engine
  access and no loopback Redis listener in the Codex sandbox; it started no
  workload.
- Hardened pre-encryption sanitization for historical exports: bearer headers,
  URL credentials, and recognizable GitHub/Hugging Face token formats are now
  redacted alongside paths, email addresses, and named secret fields.
- Fixed broker-outage submission handling: failed task publication returns the
  durable job to `staged`, so the next operator retry can publish the original
  encrypted artifact instead of reporting a phantom queued job or creating an
  additional source artifact.
- Locked the Phase 1 Celery configuration to authenticated `127.0.0.1:6379`
  Redis URLs (database 0 or 1 only). A changed environment variable can no
  longer quietly redirect this foundation to a LAN or remote broker.
- Hardened encrypted-artifact reads: they now validate the envelope version,
  nonce shape, ciphertext presence, and authenticated decryption before JSON
  decoding, and report stable policy errors for malformed or tampered records.
- Added a 25 MiB Phase 1 source-size ceiling before export staging, so an
  oversized transcript cannot consume unbounded memory or artifact storage
  before review-only extraction applies its text cap.
- Made destructive key rotation explicit: the secret initializer now requires
  `-Force` plus `-AcknowledgeExistingArtifactsBecomeUnreadable` before it can
  replace an existing AES key and Redis password.
- Bounded the guarded broker launcher's Docker engine probe to 15 seconds. A
  stuck Docker Desktop engine now produces a clear actionable error instead of
  leaving a startup window apparently blank.
- Live Phase 1 attempt: the guarded launcher reached its Docker check but the
  engine did not respond, and the independent read-only doctor reported a
  bounded Docker timeout. No Redis container, worker, model, render, or sample
  job was started. The live acceptance item remains open pending Docker
  Desktop's own **Engine running** state.
- Added `docs/CLAUDE_CODE_CONTINUATION_2026-08-29.md`, a concise secret-free
  shared continuation note covering the operator intent, tested boundaries,
  live blocker, and exact next guarded Phase 1 sequence.
- Updated the current local-agent handoff to reflect the verified Phase 1
  boundary and its outstanding live-only broker/sample acceptance step.

## Still unverified

- This Codex sandbox identity is not a Docker Desktop engine user and receives
  access-denied responses for the local Docker pipe. The broker must be started
  from the normal Windows desktop account using `START_PHASE1_BROKER.ps1`.
- The loopback Redis broker, CPU worker, and synthetic `--sample` dispatch have
  not been live-verified from the normal desktop account.
- No laptop, phone, Chroma ingestion, Judge, Researcher, Teacher/Student, or
  ten-node worker has been enabled or tested.
