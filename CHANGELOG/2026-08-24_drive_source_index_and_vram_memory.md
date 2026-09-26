# Drive source index and VRAM-arbitration memory — 2026-08-24

## What changed

- Recorded the Google Drive provenance of UPGRADE 09, 12, and 15 in their local
  checked-in copies.
- Added `local_agent/UPGRADE/DRIVE_SOURCE_MANIFEST.md`, mapping local working
  copies to the Drive documents.
- Added the concise UPGRADE 15 VRAM invariant to `local_agent/memory.json`, the
  local assistant's persistent cross-conversation memory.

## Why

The operator identified Google Drive as the location of Claude-authored local
agent designs and required the VRAM-arbitration rule to persist. The exact Drive
source for UPGRADE 15 existed locally but had no recorded source link.

## Evidence

Google Drive search found the exact documents and IDs:

- UPGRADE 09: `1Z3Wdu3Xcj1AAUdEjSQPepQsy7WKvZKbJ5GoC59KmzQU`
- UPGRADE 12: `1sgMlp75p1Y6OysP3laKDXaX5OexP1HS5O1uLAItEhGU`
- UPGRADE 15: `1PJOklNvegWbcGrHplksk0_5C6YbnpYcg41hu_tJM8UA`

## Verification

The local UPGRADE files and persistent-memory JSON remain readable. This change
does not start, stop, load, unload, or modify any model, watcher, queue job, or
render path.

## Still unverified

UPGRADE 15's runtime reclaim ladder has not been reimplemented or live-tested
in this change. The current runtime must be audited against the preserved design
before any further GPU/vision modification.
