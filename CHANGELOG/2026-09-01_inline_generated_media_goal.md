# 2026-09-01 — Inline generated-media display goal

## What changed

- Added a low-priority roadmap item to `TODO.md` for displaying completed
  generated images and videos directly in their originating local-agent chat.
- Added the same durable UI requirement to `local_agent/OPERATING_MEMORY.md`.

## Why

The operator wants a completed media generation to be immediately visible in
the conversation rather than requiring them to locate a returned filesystem
path manually.

## Boundaries

This is a future UI capability. It must retain the existing output path,
checksum/manifest, and render audit and permit previews only for validated,
allow-listed generated-output paths. It must work after chat refresh and show an
honest unavailable state if an artifact cannot be found. It must not expose
arbitrary local files.

## Evidence

The added TODO and operating-memory entries record the requested scope,
persistence requirement, and file-access boundary. No UI, render path, media
server, generation job, or artifact was changed by this documentation update.

## Verification

- Reviewed both entries for the view/play, persistence, audit-retention, and
  allow-listed-path requirements.

## Still unverified

No chat-media reference format, API endpoint, UI card, playback behavior, or
browser-refresh test has been implemented.
